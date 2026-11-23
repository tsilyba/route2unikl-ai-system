# backend/services/account_access_service.py
"""
Backend-only account-access records, account_access/{uid} (M3B-1B-P1-B1).

The experimental Firestore guard (firestore-tests/account-access.experimental.rules)
lets a browser reach a student's private documents only while this record is
well-formed and in state 'active'. This module reads and creates these records
with the Firebase Admin SDK through core.firebase, which re-validates the
Firebase configuration on every call. Firestore Security Rules do not apply to
it. No HTTP route calls this module.

Record schema, exactly as the guard requires:
    state               'active' | 'disabled' | 'deleting' | 'deleted'
    version             int >= 0
    sessionsValidAfter  optional timestamp
Locks, audit history and other operational data are kept elsewhere.

provision_access_record() is a trusted, server-only operation. It creates the
record only if none exists (one atomic Firestore create, never retried
automatically), with the state taken from Firebase Authentication: 'active'
for an enabled account, 'disabled' for a disabled one. It never modifies an
existing record (whatever its state, sessionsValidAfter included), never
repairs a malformed one, and refuses accounts that do not exist. An
authenticated ID token alone does not prove that an account is newly
registered, so there is no self-provisioning path; the callers (registration
and the migration backfill) are designed in P1-B2.

Failures raise AccountAccessError with a fixed code; nothing is reported as a
successful activation unless the record was created and Firebase
Authentication still showed the account enabled afterwards. Logs contain the
uid, codes and exception types only: never an email address, token,
credential or academic data.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Tuple

from firebase_admin import auth as firebase_auth
from google.api_core import exceptions as google_exceptions

from core.firebase import initialize_firebase
from services.user_admin_service import UID_PATTERN

logger = logging.getLogger("account_access_service")

COLLECTION = "account_access"
STATES = ("active", "disabled", "deleting", "deleted")
ALLOWED_FIELDS = ("state", "version", "sessionsValidAfter")
INITIAL_VERSION = 1
WRITE_TIMEOUT_SECONDS = 10
_UID_RE = re.compile(UID_PATTERN)

# Error codes (AccountAccessError.code)
INVALID_UID = "INVALID_UID"
FIREBASE_UNAVAILABLE = "FIREBASE_UNAVAILABLE"      # initialisation or configuration check failed
AUTH_ACCOUNT_NOT_FOUND = "AUTH_ACCOUNT_NOT_FOUND"  # provisioning refused; nothing written
AUTH_UNAVAILABLE = "AUTH_UNAVAILABLE"
STORE_UNAVAILABLE = "STORE_UNAVAILABLE"            # includes a create whose outcome is unknown

# Why a stored record is malformed (RecordLookup.problems)
NOT_A_MAP = "NOT_A_MAP"
UNKNOWN_FIELD = "UNKNOWN_FIELD"
STATE_MISSING = "STATE_MISSING"
STATE_INVALID = "STATE_INVALID"
VERSION_MISSING = "VERSION_MISSING"
VERSION_INVALID = "VERSION_INVALID"
SESSIONS_VALID_AFTER_INVALID = "SESSIONS_VALID_AFTER_INVALID"

# Firebase Authentication account status
AUTH_ENABLED = "enabled"
AUTH_DISABLED = "disabled"
AUTH_MISSING = "missing"

# Inconsistencies between Firebase Authentication and the record
RECORD_MISSING = "RECORD_MISSING"
RECORD_MALFORMED = "RECORD_MALFORMED"
AUTH_ACCOUNT_MISSING = "AUTH_ACCOUNT_MISSING"
AUTH_DISABLED_RECORD_ACTIVE = "AUTH_DISABLED_RECORD_ACTIVE"
AUTH_ENABLED_RECORD_DISABLED = "AUTH_ENABLED_RECORD_DISABLED"
DELETION_IN_PROGRESS = "DELETION_IN_PROGRESS"
RECORD_DELETED_AUTH_PRESENT = "RECORD_DELETED_AUTH_PRESENT"
AUTH_STATE_UNVERIFIED = "AUTH_STATE_UNVERIFIED"


class AccountAccessError(Exception):
    """A controlled failure; `code` is one of the error codes above."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AccessRecord:
    state: str
    version: int
    sessions_valid_after: Optional[datetime] = None


@dataclass(frozen=True)
class RecordLookup:
    status: str  # "valid" | "missing" | "malformed"
    record: Optional[AccessRecord] = None
    problems: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountAssessment:
    uid: str
    auth_status: str  # AUTH_ENABLED | AUTH_DISABLED | AUTH_MISSING
    lookup: RecordLookup
    issues: Tuple[str, ...]

    @property
    def consistent(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class ProvisionResult:
    uid: str
    created: bool          # True only if this call created the record
    lookup: RecordLookup   # the record as created, or as found (never modified)
    issues: Tuple[str, ...]

    @property
    def activated(self) -> bool:
        """True only for a newly created 'active' record whose Auth account was still enabled afterwards."""
        return (self.created and self.lookup.status == "valid"
                and self.lookup.record.state == "active" and not self.issues)


# ----------------------------------------------------------------------- validation
def validate_access_record(data: Any) -> RecordLookup:
    """Check stored data against the schema the Firestore guard enforces."""
    if not isinstance(data, dict):
        return RecordLookup("malformed", problems=(NOT_A_MAP,))
    problems = []
    if any(key not in ALLOWED_FIELDS for key in data):
        problems.append(UNKNOWN_FIELD)
    state = data.get("state")
    if "state" not in data:
        problems.append(STATE_MISSING)
    elif not isinstance(state, str) or state not in STATES:
        problems.append(STATE_INVALID)
    version = data.get("version")
    if "version" not in data:
        problems.append(VERSION_MISSING)
    elif isinstance(version, bool) or not isinstance(version, int) or version < 0:
        problems.append(VERSION_INVALID)
    threshold = data.get("sessionsValidAfter")
    if "sessionsValidAfter" in data and not (isinstance(threshold, datetime) and threshold.tzinfo is not None):
        problems.append(SESSIONS_VALID_AFTER_INVALID)
    if problems:
        return RecordLookup("malformed", problems=tuple(problems))
    return RecordLookup("valid", AccessRecord(state, version, threshold))


def _require_valid_uid(uid: Any) -> str:
    if not isinstance(uid, str) or _UID_RE.fullmatch(uid) is None:
        raise AccountAccessError(INVALID_UID)
    return uid


def _issues(auth_status: str, lookup: RecordLookup) -> Tuple[str, ...]:
    """Inconsistencies between the Auth account status and the record."""
    if lookup.status == "missing":
        return (RECORD_MISSING, AUTH_ACCOUNT_MISSING) if auth_status == AUTH_MISSING else (RECORD_MISSING,)
    if lookup.status != "valid":
        return (RECORD_MALFORMED,)
    state = lookup.record.state
    if state == "deleting":
        return (DELETION_IN_PROGRESS,)
    if state == "deleted":
        return () if auth_status == AUTH_MISSING else (RECORD_DELETED_AUTH_PRESENT,)
    if auth_status == AUTH_MISSING:
        return (AUTH_ACCOUNT_MISSING,)
    if state == "active" and auth_status == AUTH_DISABLED:
        return (AUTH_DISABLED_RECORD_ACTIVE,)
    if state == "disabled" and auth_status == AUTH_ENABLED:
        return (AUTH_ENABLED_RECORD_DISABLED,)
    return ()


# ------------------------------------------------------------------- Firebase access
def _db():
    """Firestore client from the shared, validated Admin SDK initialisation."""
    try:
        return initialize_firebase()
    except Exception as exc:
        logger.error("Firebase unavailable for account access: %s", type(exc).__name__)
        raise AccountAccessError(FIREBASE_UNAVAILABLE) from None


def _document(db, uid: str):
    return db.collection(COLLECTION).document(uid)


def _auth_status(uid: str) -> str:
    try:
        account = firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        return AUTH_MISSING
    except Exception as exc:
        logger.error("Firebase Authentication unavailable (uid=%s): %s", uid, type(exc).__name__)
        raise AccountAccessError(AUTH_UNAVAILABLE) from None
    # Anything other than an explicit False is treated as disabled (fail closed).
    return AUTH_ENABLED if account.disabled is False else AUTH_DISABLED


def _read(db, uid: str) -> RecordLookup:
    try:
        snapshot = _document(db, uid).get()
    except Exception as exc:
        logger.error("Firestore unavailable reading account access (uid=%s): %s", uid, type(exc).__name__)
        raise AccountAccessError(STORE_UNAVAILABLE) from None
    if not snapshot.exists:
        return RecordLookup("missing")
    return validate_access_record(snapshot.to_dict())


# -------------------------------------------------------------------- public API
def read_access_record(uid: str) -> RecordLookup:
    """The stored record for `uid`: valid, missing or malformed (never repaired)."""
    uid = _require_valid_uid(uid)
    return _read(_db(), uid)


def inspect_account(uid: str) -> AccountAssessment:
    """The record together with the Firebase Authentication status, and any inconsistency between them."""
    uid = _require_valid_uid(uid)
    db = _db()
    auth_status = _auth_status(uid)
    lookup = _read(db, uid)
    return AccountAssessment(uid, auth_status, lookup, _issues(auth_status, lookup))


def provision_access_record(uid: str) -> ProvisionResult:
    """Trusted server-only provisioning: create account_access/{uid} if, and only if, it does not exist.

    Never call this from a request handler on the strength of an ID token alone
    (see the module docstring). Raises AccountAccessError:
      INVALID_UID, FIREBASE_UNAVAILABLE, AUTH_UNAVAILABLE;
      AUTH_ACCOUNT_NOT_FOUND: there is no Auth account, and nothing is written;
      STORE_UNAVAILABLE: the record could not be read, or a create failed or its
        outcome is unknown. Never reported as success; retrying is safe because an
        existing record is never overwritten.
    A create refused because a record exists, or aborted by a concurrent write to the
    same document, returns the stored record with created=False.
    """
    uid = _require_valid_uid(uid)
    db = _db()
    auth_status = _auth_status(uid)
    if auth_status == AUTH_MISSING:
        logger.warning("Account access provisioning refused: no Auth account (uid=%s)", uid)
        raise AccountAccessError(AUTH_ACCOUNT_NOT_FOUND)

    record = {"state": "active" if auth_status == AUTH_ENABLED else "disabled", "version": INITIAL_VERSION}
    try:
        _document(db, uid).create(record, retry=None, timeout=WRITE_TIMEOUT_SECONDS)
    except (google_exceptions.AlreadyExists, google_exceptions.Aborted) as exc:
        # AlreadyExists: a record is stored. Aborted: Firestore refused the write because of a
        # concurrent write to the same document. Either way, report what is stored now, never
        # as created by this call; if nothing is stored, the outcome is not confirmed.
        lookup = _read(db, uid)
        if lookup.status == "missing":
            logger.error("Account access record not confirmed (uid=%s): %s", uid, type(exc).__name__)
            raise AccountAccessError(STORE_UNAVAILABLE) from None
        issues = _issues(auth_status, lookup)
        logger.info("Account access record already exists, not modified (uid=%s, reason=%s, status=%s, issues=%s)",
                    uid, type(exc).__name__, lookup.status, ",".join(issues) or "none")
        return ProvisionResult(uid, False, lookup, issues)
    except Exception as exc:
        logger.error("Account access record not confirmed (uid=%s): %s", uid, type(exc).__name__)
        raise AccountAccessError(STORE_UNAVAILABLE) from None

    created = validate_access_record(record)
    # Firebase Authentication may have changed while the record was being written.
    try:
        issues = _issues(_auth_status(uid), created)
    except AccountAccessError:
        issues = (AUTH_STATE_UNVERIFIED,)
    logger.info("Account access record created (uid=%s, state=%s, issues=%s)",
                uid, record["state"], ",".join(issues) or "none")
    return ProvisionResult(uid, True, created, issues)
