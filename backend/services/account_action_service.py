# backend/services/account_action_service.py
"""
Admin account actions: Disable and Enable (M3B-2) and Delete (M3B-3) student accounts.

LOCAL EMULATOR TESTING ONLY: main.py mounts the routes in routes/admin_account_actions.py only when the
backend starts in Firebase emulator mode, and those routes answer 404 outside that mode.

Each action coordinates two stores that cannot be updated atomically: the account-access record
account_access/{uid} (read by the experimental Firestore guard) and the Firebase Authentication account.
The order of the steps is chosen so that a failure at any point leaves the record NOT 'active' unless
the whole operation succeeded:

  Disable  restrict_record   record 'active' -> 'disabled' (Firestore access closes first)
           disable_auth      Auth account disabled (no new sign-in; backend refuses its tokens)
  Enable   restrict_record   } first normalise to fully disabled (only needed when resuming or when
           disable_auth      } Auth and the record disagree)
           revoke_sessions   wait REVOCATION_MARGIN_SECONDS, then revoke refresh tokens: earlier ID tokens
                             fail the backend's revocation check. Firebase compares a token's issue time
                             and the revocation time in whole seconds, and a token issued in the same
                             second as the revocation is NOT revoked; the wait (after Auth is confirmed
                             disabled) puts every earlier token in an earlier second
           set_session_threshold   sessionsValidAfter = Firestore server time (record still 'disabled'):
                             earlier sessions fail the guard's auth_time check
           settle            wait ENABLE_SETTLE_SECONDS, so that a new sign-in cannot fall within the
                             guard's one-second margin after the threshold (FL3)
           enable_auth       Auth account enabled
           activate_record   record 'disabled' -> 'active', LAST: Firestore opens only after every other
                             step succeeded
  Both     verify            Auth and the record re-read; anything unexpected is reported as incomplete

  Delete (M3B-3, permanent; the account must be 'active' or 'disabled', or an unfinished deletion):
           mark_deleting     record -> 'deleting': Firestore access closes, and the backend's student-data
                             endpoints refuse the account (core/student_access.py)
           disable_auth      Auth account disabled: no new sign-in or token refresh; the backend refuses
                             its tokens
           check_admin_before_data_deletion   the admin claim is re-read: never delete an administrator
           check_no_nested_data   none of the student's documents has subcollections (deleting a document
                             would orphan them); otherwise stop
           delete_student_data   ONE atomic Firestore batch deletes users/, results/ and ai_assessments/{uid},
                             fenced by the record (version + 1 with a precondition): all or nothing
           confirm_data_removed   the documents are re-read and must all be absent
           check_admin_before_auth_deletion   the admin claim is re-read again
           delete_auth       the Firebase Authentication account is deleted (already gone counts as done)
           finalize_record   record 'deleting' -> 'deleted' (the tombstone; never changed again)
           verify            Auth gone, the documents absent, the record 'deleted'
  Firestore and Firebase Authentication cannot be changed atomically. Auth is deleted only after the data
  removal is confirmed, and the record is finalised after Auth. If a step after the Auth deletion fails, the
  account no longer appears in the Auth-based Manage Users list; list_incomplete_deletions() finds it (from
  its lock and its 'deleting' record) and the same Delete resumes it.

Every record change is version-checked: the version must be the one this operation expects, and the
write carries a precondition on the document's update time, so a record changed by anyone else is never
overwritten (account_access_service.change_record_state). The record never gets extra fields: operation
locks live in account_operations/{uid} and audit records in account_audit/{operationId}, both
backend-only (the experimental rules deny every browser access to unknown collections).

Locks: one per target account, created atomically with a lease. A running lock refuses every other
action (409). If an operation stops part-way, its lock stays as 'incomplete' (also when the process dies
and the lease expires) with the failed step and a reason code: the account shows as incomplete, and the
same action resumes it from the current state (every step is idempotent). Disable may also take over an
incomplete Enable (the restricting direction); Enable may not take over an incomplete Disable. Delete
never takes over another operation, and no other operation takes over a deletion. Delete locks have a
longer lease that is renewed, with a precondition, before every step: if another process has taken the
lock, the deletion stops (LOCK_LOST). A renewal cannot interrupt a Firebase call already in flight, so a
running deletion lock can be taken over only after its lease AND a grace period longer than the
slowest step's worst-case Admin SDK calls have passed. This is a timing assumption, not a fence for
Firebase Authentication writes; it is safe because every Auth write of a deletion moves the same way
(disable, delete), Enable never runs on an account in deletion, and Firestore writes are version-checked.

Refused without any change: the caller's own account, accounts with the admin custom claim, Auth
accounts that do not exist (except an unfinished deletion), and missing or malformed records (records are
never created, repaired or reactivated here). Disable and Enable also refuse 'deleting' and 'deleted'
records. Outcomes are truthful: an operation is reported as completed only after verification; any
partial failure is OPERATION_INCOMPLETE. Logs and audit records contain uids, operation identifiers, steps
and codes only: never email addresses, names, tokens, passwords or academic data.
"""
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from firebase_admin import auth as firebase_auth
from google.api_core import exceptions as google_exceptions
from google.cloud.firestore import SERVER_TIMESTAMP
from google.cloud.firestore_v1.base_query import FieldFilter

from core.firebase import initialize_firebase
from services import account_access_service as access
from services.user_admin_service import UID_PATTERN, is_admin_account

logger = logging.getLogger("account_action_service")

LOCK_COLLECTION = "account_operations"
AUDIT_COLLECTION = "account_audit"
LEASE_SECONDS = 120
DELETE_LEASE_SECONDS = 300            # renewed before every deletion step
# A running deletion is taken over only after its lease AND this grace period (35 minutes after its last
# renewal): longer than the slowest step, which makes two Admin SDK calls of up to about 10 minutes each
# (120 s per attempt, up to 4 retries). A timing assumption, not a fence (see the module docstring).
DELETE_TAKEOVER_GRACE_SECONDS = 1800
ENABLE_SETTLE_SECONDS = 3.0
REVOCATION_MARGIN_SECONDS = 1.1
WRITE_TIMEOUT_SECONDS = 10
INCOMPLETE_DELETIONS_LIMIT = 100
_UID_RE = re.compile(UID_PATTERN)
_sleep = time.sleep  # replaced in tests

DISABLE = "disable"
ENABLE = "enable"
DELETE = "delete"
ACTIONS = (DISABLE, ENABLE, DELETE)

# The student-owned documents a deletion removes: {collection}/{uid}. No other student data store exists
# (no Firebase Storage, Realtime Database, backend files or ChromaDB student data; see PROJECT_STATUS.md).
STUDENT_DATA_COLLECTIONS = ("users", "results", "ai_assessments")

# Account states shown to administrators
STATE_ACTIVE = "active"
STATE_DISABLED = "disabled"
STATE_INCONSISTENT = "inconsistent"   # Auth and the record disagree, no operation recorded
STATE_INCOMPLETE = "incomplete"       # an operation stopped part-way and can be resumed
STATE_IN_PROGRESS = "in_progress"     # an operation is running
STATE_PROTECTED = "protected"         # the caller's own account or an administrator account
STATE_UNSUPPORTED = "unsupported"     # missing or malformed record
STATE_DELETION_INCOMPLETE = "deletion_incomplete"  # a deletion started and must be resumed
STATE_DELETED = "deleted"             # deletion complete: Auth gone, record 'deleted'

LOCK_RUNNING = "running"
LOCK_INCOMPLETE = "incomplete"

# Error codes (AccountActionError.code)
INVALID_UID = "INVALID_UID"
SELF_ACTION_FORBIDDEN = "SELF_ACTION_FORBIDDEN"
ADMIN_TARGET_FORBIDDEN = "ADMIN_TARGET_FORBIDDEN"
USER_NOT_FOUND = "USER_NOT_FOUND"
ACCESS_RECORD_UNSUPPORTED = "ACCESS_RECORD_UNSUPPORTED"
ALREADY_DISABLED = "ALREADY_DISABLED"
ALREADY_ACTIVE = "ALREADY_ACTIVE"
OPERATION_IN_PROGRESS = "OPERATION_IN_PROGRESS"
INCOMPLETE_OPERATION_PENDING = "INCOMPLETE_OPERATION_PENDING"
ACCOUNT_ACTION_UNAVAILABLE = "ACCOUNT_ACTION_UNAVAILABLE"  # nothing was changed
OPERATION_INCOMPLETE = "OPERATION_INCOMPLETE"              # stopped part-way; recorded for resumption
ACCOUNT_DELETION_IN_PROGRESS = "ACCOUNT_DELETION_IN_PROGRESS"  # Disable/Enable on an unfinished deletion
ACCOUNT_DELETED = "ACCOUNT_DELETED"                        # the account has already been deleted
DELETE_NOT_ALLOWED = "DELETE_NOT_ALLOWED"                  # only 'active' or 'disabled' accounts
DELETE_CONFIRMATION_MISMATCH = "DELETE_CONFIRMATION_MISMATCH"  # the confirmation does not name the target

# Why an operation stopped (AccountActionError.reason)
REASON_AUTH_UNAVAILABLE = "AUTH_UNAVAILABLE"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_RECORD_CHANGED = "RECORD_CHANGED"
REASON_ACCOUNT_REMOVED = "ACCOUNT_REMOVED"
REASON_UNEXPECTED_STATE = "UNEXPECTED_STATE"
REASON_INTERNAL = "INTERNAL_ERROR"
REASON_ADMIN_TARGET = "ADMIN_TARGET"            # an admin claim appeared during the deletion
REASON_LOCK_LOST = "LOCK_LOST"                  # another process took the lock; this one stopped
REASON_NESTED_DATA = "NESTED_DATA"              # a student document has subcollections
REASON_DATA_REMAINS = "DATA_REMAINS"            # a student document still exists after the deletion

# Steps
STEP_RESTRICT_RECORD = "restrict_record"
STEP_DISABLE_AUTH = "disable_auth"
STEP_REVOKE_SESSIONS = "revoke_sessions"
STEP_SET_THRESHOLD = "set_session_threshold"
STEP_SETTLE = "settle"
STEP_ENABLE_AUTH = "enable_auth"
STEP_ACTIVATE_RECORD = "activate_record"
STEP_VERIFY = "verify"
STEP_MARK_DELETING = "mark_deleting"
STEP_CHECK_ADMIN_BEFORE_DATA = "check_admin_before_data_deletion"
STEP_CHECK_NESTED_DATA = "check_no_nested_data"
STEP_DELETE_DATA = "delete_student_data"
STEP_CONFIRM_DATA_REMOVED = "confirm_data_removed"
STEP_CHECK_ADMIN_BEFORE_AUTH = "check_admin_before_auth_deletion"
STEP_DELETE_AUTH = "delete_auth"
STEP_FINALIZE_RECORD = "finalize_record"

_STORED = object()  # _load_view: read the lock from Firestore


class AccountActionError(Exception):
    """A controlled refusal or failure. The message is the code only."""

    def __init__(self, code: str, *, operation: Optional[str] = None, operation_id: Optional[str] = None,
                 failed_step: Optional[str] = None, reason: Optional[str] = None):
        super().__init__(code)
        self.code = code
        self.operation = operation
        self.operation_id = operation_id
        self.failed_step = failed_step
        self.reason = reason


class _StepFailure(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OperationLock:
    operation_id: Optional[str]
    operation: Optional[str]        # DISABLE | ENABLE | None (unreadable lock)
    status: str                     # LOCK_RUNNING | LOCK_INCOMPLETE (an expired lease counts as incomplete)
    actor_uid: Optional[str]
    failed_step: Optional[str]
    reason: Optional[str]
    started_at: Optional[datetime]
    updated_at: Optional[datetime]


@dataclass(frozen=True)
class AccountView:
    uid: str
    auth_status: str                # access.AUTH_ENABLED | access.AUTH_DISABLED
    is_admin: bool
    is_self: bool
    record: access.RecordSnapshot
    lock: Optional[OperationLock]
    issues: Tuple[str, ...]
    state: str
    allowed_actions: Tuple[str, ...]


@dataclass(frozen=True)
class ActionResult:
    operation: str
    operation_id: str
    view: AccountView               # the verified state after the operation
    resumed_operation_id: Optional[str]
    audit_recorded: bool
    lock_released: bool


@dataclass
class _HeldLock:
    ref: Any
    operation_id: str
    operation: str
    update_time: Any
    previous: Optional[OperationLock]
    previous_data: Optional[Dict[str, Any]]


# --------------------------------------------------------------------------- helpers
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_uid(uid: Any) -> str:
    if not isinstance(uid, str) or _UID_RE.fullmatch(uid) is None:
        raise AccountActionError(INVALID_UID)
    return uid


def _db():
    try:
        return initialize_firebase()
    except Exception as exc:
        logger.error("Firebase unavailable for account actions: %s", type(exc).__name__)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE) from None


def _precondition(db, update_time):
    return db.write_option(last_update_time=update_time)


def _lease_seconds(operation: str) -> int:
    return DELETE_LEASE_SECONDS if operation == DELETE else LEASE_SECONDS


def _lock_from_data(data: Dict[str, Any], now: datetime) -> OperationLock:
    status = data.get("status")
    lease = data.get("leaseExpiresAt")
    # A deletion's lock counts as abandoned only after its lease AND a grace period longer than any
    # Firebase call it may still have in flight (a lease renewal cannot interrupt such a call).
    grace = timedelta(seconds=DELETE_TAKEOVER_GRACE_SECONDS if data.get("operation") == DELETE else 0)
    if status == LOCK_RUNNING and not (isinstance(lease, datetime) and lease.tzinfo is not None
                                       and lease + grace > now):
        status = LOCK_INCOMPLETE  # the process stopped without recording an outcome
    if status not in (LOCK_RUNNING, LOCK_INCOMPLETE):
        status = LOCK_INCOMPLETE
    operation = data.get("operation")
    text = lambda key: data.get(key) if isinstance(data.get(key), str) else None  # noqa: E731
    stamp = lambda key: data.get(key) if isinstance(data.get(key), datetime) else None  # noqa: E731
    return OperationLock(text("operationId"), operation if operation in ACTIONS else None, status,
                         text("actorUid"), text("failedStep"), text("reason"), stamp("startedAt"), stamp("updatedAt"))


def _classify(auth_status: str, is_admin: bool, is_self: bool, lookup: access.RecordLookup,
              lock: Optional[OperationLock]) -> Tuple[str, Tuple[str, ...]]:
    """The account state shown to administrators and the actions allowed from it."""
    if is_self or is_admin:
        return STATE_PROTECTED, ()
    if lookup.status != "valid":
        return STATE_UNSUPPORTED, ()
    record_state = lookup.record.state
    deletion_lock = lock is not None and lock.operation == DELETE
    if record_state in ("deleting", "deleted") or deletion_lock:
        if lock is not None and lock.status == LOCK_RUNNING:
            return STATE_IN_PROGRESS, ()
        if record_state == "deleted" and auth_status == access.AUTH_MISSING and not deletion_lock:
            return STATE_DELETED, ()
        # A deletion started: only Delete may continue it (no undo, no other action).
        return STATE_DELETION_INCOMPLETE, (DELETE,)
    if lock is not None:
        if lock.status == LOCK_RUNNING:
            return STATE_IN_PROGRESS, ()
        # An unfinished Enable can be resumed or cancelled by Disable; an unfinished Disable only resumed.
        return STATE_INCOMPLETE, (ENABLE, DISABLE) if lock.operation == ENABLE else (DISABLE,)
    if auth_status == access.AUTH_ENABLED and record_state == "active":
        return STATE_ACTIVE, (DISABLE, DELETE)
    if auth_status == access.AUTH_DISABLED and record_state == "disabled":
        return STATE_DISABLED, (ENABLE, DELETE)
    return STATE_INCONSISTENT, (DISABLE, ENABLE)


def _load_view(db, uid: str, actor_uid: str, *, lock: Any = _STORED) -> AccountView:
    try:
        account = firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        account = None  # allowed below only for an unfinished or completed deletion
    except Exception as exc:
        logger.error("Account actions: Firebase Authentication unavailable (uid=%s): %s", uid, type(exc).__name__)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE) from None
    try:
        record = access.read_record_snapshot(uid)
    except access.AccountAccessError:
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE) from None
    if lock is _STORED:
        try:
            snapshot = db.collection(LOCK_COLLECTION).document(uid).get()
        except Exception as exc:
            logger.error("Account actions: Firestore unavailable reading the lock (uid=%s): %s", uid, type(exc).__name__)
            raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE) from None
        lock = _lock_from_data(snapshot.to_dict() or {}, _now()) if snapshot.exists else None
    if account is None:
        # The Auth account is gone. Only a deletion explains that here (its record is 'deleting' or
        # 'deleted', or it holds a deletion lock); anything else is an account that does not exist.
        lookup = record.lookup
        in_deletion = lookup.status == "valid" and lookup.record.state in ("deleting", "deleted")
        if not (in_deletion or (lock is not None and lock.operation == DELETE)):
            raise AccountActionError(USER_NOT_FOUND)
        auth_status = access.AUTH_MISSING
    else:
        # Anything other than an explicit False is treated as disabled (fail closed), as in account_access_service.
        auth_status = access.AUTH_ENABLED if account.disabled is False else access.AUTH_DISABLED
    is_admin = account is not None and is_admin_account(account)
    is_self = uid == actor_uid
    state, allowed = _classify(auth_status, is_admin, is_self, record.lookup, lock)
    return AccountView(uid, auth_status, is_admin, is_self, record, lock,
                       access.consistency_issues(auth_status, record.lookup), state, allowed)


def _refusal(view: AccountView, operation: str) -> AccountActionError:
    if view.is_self:
        code = SELF_ACTION_FORBIDDEN
    elif view.is_admin:
        code = ADMIN_TARGET_FORBIDDEN
    elif view.state == STATE_UNSUPPORTED:
        code = ACCESS_RECORD_UNSUPPORTED
    elif view.state == STATE_IN_PROGRESS:
        code = OPERATION_IN_PROGRESS
    elif view.state == STATE_DELETED:
        code = ACCOUNT_DELETED
    elif view.state == STATE_DELETION_INCOMPLETE:
        code = ACCOUNT_DELETION_IN_PROGRESS
    elif view.state == STATE_INCOMPLETE:
        code = INCOMPLETE_OPERATION_PENDING
    elif operation == DELETE:
        code = DELETE_NOT_ALLOWED
    elif operation == DISABLE:
        code = ALREADY_DISABLED
    else:
        code = ALREADY_ACTIVE
    return AccountActionError(code, operation=operation)


def _state_summary(view: Optional[AccountView]) -> Optional[Dict[str, Any]]:
    if view is None:
        return None
    lookup = view.record.lookup
    record = lookup.record if lookup.status == "valid" else None
    return {"auth": view.auth_status, "record": record.state if record else lookup.status,
            "version": record.version if record else None,
            "sessionsValidAfterSet": bool(record and record.sessions_valid_after is not None)}


# ------------------------------------------------------------------------ locks and audit
def _acquire_lock(db, uid: str, operation: str, actor_uid: str) -> _HeldLock:
    ref = db.collection(LOCK_COLLECTION).document(uid)
    operation_id = uuid.uuid4().hex
    data = {"operationId": operation_id, "operation": operation, "actorUid": actor_uid, "status": LOCK_RUNNING,
            "leaseExpiresAt": _now() + timedelta(seconds=_lease_seconds(operation)), "failedStep": None, "reason": None,
            "previousOperationId": None, "startedAt": SERVER_TIMESTAMP, "updatedAt": SERVER_TIMESTAMP}
    try:
        result = ref.create(data, retry=None, timeout=WRITE_TIMEOUT_SECONDS)
        return _HeldLock(ref, operation_id, operation, result.update_time, None, None)
    except (google_exceptions.AlreadyExists, google_exceptions.Aborted):
        pass  # a lock exists (or a concurrent create): decide below from what is stored
    except Exception as exc:
        logger.error("Account actions: lock not acquired (uid=%s): %s", uid, type(exc).__name__)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE, operation=operation) from None

    try:
        snapshot = ref.get()
    except Exception as exc:
        logger.error("Account actions: lock not readable (uid=%s): %s", uid, type(exc).__name__)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE, operation=operation) from None
    if not snapshot.exists:
        raise AccountActionError(OPERATION_IN_PROGRESS, operation=operation)  # contention: try again
    stored = snapshot.to_dict() or {}
    existing = _lock_from_data(stored, _now())
    if existing.status == LOCK_RUNNING:
        raise AccountActionError(OPERATION_IN_PROGRESS, operation=operation)
    if existing.operation == DELETE and operation != DELETE:
        raise AccountActionError(ACCOUNT_DELETION_IN_PROGRESS, operation=operation)  # a deletion is never undone
    if operation == DELETE and existing.operation != DELETE:
        raise AccountActionError(INCOMPLETE_OPERATION_PENDING, operation=operation)  # finish the other first
    if operation == ENABLE and existing.operation != ENABLE:
        raise AccountActionError(INCOMPLETE_OPERATION_PENDING, operation=operation)
    data["previousOperationId"] = existing.operation_id
    try:
        result = ref.update(data, option=_precondition(db, snapshot.update_time),
                            retry=None, timeout=WRITE_TIMEOUT_SECONDS)
    except (google_exceptions.FailedPrecondition, google_exceptions.NotFound, google_exceptions.Aborted):
        raise AccountActionError(OPERATION_IN_PROGRESS, operation=operation) from None
    except Exception as exc:
        logger.error("Account actions: lock not taken over (uid=%s): %s", uid, type(exc).__name__)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE, operation=operation) from None
    return _HeldLock(ref, operation_id, operation, result.update_time, existing, stored)


def _abandon(db, held: _HeldLock) -> None:
    """Give a lock back before any account change: delete it, or restore the incomplete one taken over."""
    try:
        if held.previous_data is None:
            held.ref.delete(option=_precondition(db, held.update_time), retry=None, timeout=WRITE_TIMEOUT_SECONDS)
        else:
            held.ref.update(held.previous_data, option=_precondition(db, held.update_time),
                            retry=None, timeout=WRITE_TIMEOUT_SECONDS)
    except Exception as exc:
        # The lease expires on its own; the lock then reads as incomplete with no account change made.
        logger.error("Account actions: lock not given back (operation_id=%s): %s", held.operation_id, type(exc).__name__)


def _release(db, held: _HeldLock) -> bool:
    try:
        held.ref.delete(option=_precondition(db, held.update_time), retry=None, timeout=WRITE_TIMEOUT_SECONDS)
        return True
    except Exception as exc:
        logger.error("Account actions: lock not released (operation_id=%s): %s", held.operation_id, type(exc).__name__)
        return False


def _renew_lock(db, held: _HeldLock) -> None:
    """Extend the lease, only if this operation still owns the lock (precondition on its update time).

    Used before every deletion step: if another process has taken the lock over, the deletion stops here
    (LOCK_LOST) before making any further change. It cannot stop a Firebase call that is already in flight;
    the takeover grace period (DELETE_TAKEOVER_GRACE_SECONDS) covers that.
    """
    try:
        result = held.ref.update({"leaseExpiresAt": _now() + timedelta(seconds=_lease_seconds(held.operation)),
                                  "updatedAt": SERVER_TIMESTAMP},
                                 option=_precondition(db, held.update_time), retry=None, timeout=WRITE_TIMEOUT_SECONDS)
    except (google_exceptions.FailedPrecondition, google_exceptions.NotFound, google_exceptions.Aborted):
        logger.error("Account actions: lock lost; stopping (operation_id=%s)", held.operation_id)
        raise _StepFailure(REASON_LOCK_LOST) from None
    except Exception as exc:
        logger.error("Account actions: lock renewal failed (operation_id=%s): %s", held.operation_id, type(exc).__name__)
        raise _StepFailure(REASON_STORE_UNAVAILABLE) from None
    held.update_time = result.update_time


def _mark_incomplete(db, held: _HeldLock, step: Optional[str], reason: str) -> bool:
    try:
        held.ref.update({"status": LOCK_INCOMPLETE, "failedStep": step, "reason": reason, "leaseExpiresAt": None,
                         "updatedAt": SERVER_TIMESTAMP},
                        option=_precondition(db, held.update_time), retry=None, timeout=WRITE_TIMEOUT_SECONDS)
        return True
    except Exception as exc:
        logger.error("Account actions: incomplete operation not recorded on its lock (operation_id=%s): %s",
                     held.operation_id, type(exc).__name__)
        return False


def _audit_start(db, held: _HeldLock, uid: str, actor_uid: str, view: AccountView,
                 extra: Optional[Dict[str, Any]] = None):
    ref = db.collection(AUDIT_COLLECTION).document(held.operation_id)
    ref.create({
        "operationId": held.operation_id, "operation": held.operation, "actorUid": actor_uid, "targetUid": uid,
        "outcome": "started", "failedStep": None, "reason": None,
        "resumesOperationId": held.previous.operation_id if held.previous else None,
        "resumesOperation": held.previous.operation if held.previous else None,
        "before": _state_summary(view), "after": None,
        "startedAt": SERVER_TIMESTAMP, "finishedAt": None,
        **(extra or {}),
    }, retry=None, timeout=WRITE_TIMEOUT_SECONDS)
    return ref


def _audit_finish(ref, outcome: str, after: Optional[AccountView], step: Optional[str], reason: Optional[str],
                  extra: Optional[Dict[str, Any]] = None) -> bool:
    try:
        ref.update({"outcome": outcome, "failedStep": step, "reason": reason, "after": _state_summary(after),
                    "finishedAt": SERVER_TIMESTAMP, **(extra or {})}, retry=None, timeout=WRITE_TIMEOUT_SECONDS)
        return True
    except Exception as exc:
        logger.error("Account actions: audit outcome not recorded (operation_id=%s): %s", ref.id, type(exc).__name__)
        return False


# ------------------------------------------------------------------------------- steps
class _Run:
    """Progress of one operation: the record version it expects next."""

    def __init__(self, uid: str, version: int, db: Any = None):
        self.uid = uid
        self.version = version
        self.db = db


def _current_record(run: _Run, *, states: Tuple[str, ...]) -> access.RecordSnapshot:
    try:
        snapshot = access.read_record_snapshot(run.uid)
    except access.AccountAccessError:
        raise _StepFailure(REASON_STORE_UNAVAILABLE) from None
    lookup = snapshot.lookup
    if lookup.status != "valid" or lookup.record.state not in states or lookup.record.version != run.version:
        raise _StepFailure(REASON_RECORD_CHANGED)
    return snapshot


def _change_record(run: _Run, snapshot: access.RecordSnapshot, state: str, *, set_threshold: bool = False) -> None:
    try:
        change = access.change_record_state(run.uid, snapshot, state=state, set_threshold=set_threshold)
    except access.AccountAccessError as exc:
        raise _StepFailure(REASON_RECORD_CHANGED if exc.code == access.STALE_RECORD else REASON_STORE_UNAVAILABLE) from None
    run.version = change.version


def _auth_enabled(uid: str) -> bool:
    try:
        return firebase_auth.get_user(uid).disabled is False
    except firebase_auth.UserNotFoundError:
        raise _StepFailure(REASON_ACCOUNT_REMOVED) from None
    except Exception:
        raise _StepFailure(REASON_AUTH_UNAVAILABLE) from None


def _set_auth_disabled(uid: str, disabled: bool) -> None:
    try:
        firebase_auth.update_user(uid, disabled=disabled)
    except firebase_auth.UserNotFoundError:
        raise _StepFailure(REASON_ACCOUNT_REMOVED) from None
    except Exception as exc:
        logger.error("Account actions: Auth update failed (uid=%s): %s", uid, type(exc).__name__)
        raise _StepFailure(REASON_AUTH_UNAVAILABLE) from None


def _restrict_record(run: _Run) -> None:
    snapshot = _current_record(run, states=("active", "disabled"))
    if snapshot.lookup.record.state == "active":
        _change_record(run, snapshot, "disabled")


def _disable_auth(run: _Run) -> None:
    if _auth_enabled(run.uid):
        _set_auth_disabled(run.uid, True)


def _revoke_sessions(run: _Run) -> None:
    # Auth is disabled now (previous step), so no new token can be issued. Tokens issued before have an
    # issue time no later than this second; after the wait, the revocation falls in a later second.
    _sleep(REVOCATION_MARGIN_SECONDS)
    try:
        firebase_auth.revoke_refresh_tokens(run.uid)
    except firebase_auth.UserNotFoundError:
        raise _StepFailure(REASON_ACCOUNT_REMOVED) from None
    except Exception as exc:
        logger.error("Account actions: session revocation failed (uid=%s): %s", run.uid, type(exc).__name__)
        raise _StepFailure(REASON_AUTH_UNAVAILABLE) from None


def _set_threshold(run: _Run) -> None:
    _change_record(run, _current_record(run, states=("disabled",)), "disabled", set_threshold=True)


def _settle(run: _Run) -> None:
    _sleep(ENABLE_SETTLE_SECONDS)


def _enable_auth(run: _Run) -> None:
    _set_auth_disabled(run.uid, False)


def _activate_record(run: _Run) -> None:
    snapshot = _current_record(run, states=("disabled",))
    if snapshot.lookup.record.sessions_valid_after is None:
        raise _StepFailure(REASON_RECORD_CHANGED)
    _change_record(run, snapshot, "active")


# ---------------------------------------------------------------------- deletion steps (M3B-3)
def _data_present(db, uid: str) -> Dict[str, bool]:
    """Which student-owned documents exist (existence only; their contents are never used)."""
    try:
        return {name: db.collection(name).document(uid).get().exists for name in STUDENT_DATA_COLLECTIONS}
    except Exception as exc:
        logger.error("Account actions: Firestore unavailable reading student data (uid=%s): %s", uid, type(exc).__name__)
        raise _StepFailure(REASON_STORE_UNAVAILABLE) from None


def _mark_deleting(run: _Run) -> None:
    snapshot = _current_record(run, states=("active", "disabled", "deleting", "deleted"))
    if snapshot.lookup.record.state in ("active", "disabled"):
        _change_record(run, snapshot, "deleting")


def _disable_auth_if_present(run: _Run) -> None:
    try:
        account = firebase_auth.get_user(run.uid)
    except firebase_auth.UserNotFoundError:
        return  # already deleted (a resumed deletion)
    except Exception:
        raise _StepFailure(REASON_AUTH_UNAVAILABLE) from None
    if account.disabled is False:
        _set_auth_disabled(run.uid, True)


def _check_not_admin(run: _Run) -> None:
    """Never delete an administrator: the claim is re-read from Firebase Authentication."""
    try:
        account = firebase_auth.get_user(run.uid)
    except firebase_auth.UserNotFoundError:
        return
    except Exception:
        raise _StepFailure(REASON_AUTH_UNAVAILABLE) from None
    if is_admin_account(account):
        logger.error("Account actions: the target gained the admin claim during deletion; stopped (uid=%s)", run.uid)
        raise _StepFailure(REASON_ADMIN_TARGET)


def _check_no_nested_data(run: _Run) -> None:
    """Deleting a Firestore document does not delete its subcollections; none must exist."""
    try:
        for name in STUDENT_DATA_COLLECTIONS:
            if any(True for _ in run.db.collection(name).document(run.uid).collections()):
                logger.error("Account actions: student document has subcollections; stopped (uid=%s, collection=%s)",
                             run.uid, name)
                raise _StepFailure(REASON_NESTED_DATA)
    except _StepFailure:
        raise
    except Exception as exc:
        logger.error("Account actions: subcollection check failed (uid=%s): %s", run.uid, type(exc).__name__)
        raise _StepFailure(REASON_STORE_UNAVAILABLE) from None


def _delete_data(run: _Run) -> None:
    snapshot = _current_record(run, states=("deleting", "deleted"))
    if snapshot.lookup.record.state != "deleting":
        return  # already finalised: nothing left to delete under this record
    if not any(_data_present(run.db, run.uid).values()):
        return  # deleted by an earlier attempt
    try:
        change = access.delete_documents_during_deletion(run.uid, snapshot, STUDENT_DATA_COLLECTIONS)
    except access.AccountAccessError as exc:
        raise _StepFailure(REASON_RECORD_CHANGED if exc.code == access.STALE_RECORD else REASON_STORE_UNAVAILABLE) from None
    run.version = change.version


def _confirm_data_removed(run: _Run) -> None:
    if any(_data_present(run.db, run.uid).values()):
        raise _StepFailure(REASON_DATA_REMAINS)


def _delete_auth(run: _Run) -> None:
    try:
        firebase_auth.delete_user(run.uid)
    except firebase_auth.UserNotFoundError:
        return  # already deleted
    except Exception as exc:
        logger.error("Account actions: Auth deletion failed (uid=%s): %s", run.uid, type(exc).__name__)
        raise _StepFailure(REASON_AUTH_UNAVAILABLE) from None


def _finalize_record(run: _Run) -> None:
    snapshot = _current_record(run, states=("deleting", "deleted"))
    if snapshot.lookup.record.state == "deleting":
        _change_record(run, snapshot, "deleted")


_DELETE_STEPS: List[Tuple[str, Callable[[_Run], None]]] = [
    (STEP_MARK_DELETING, _mark_deleting),
    (STEP_DISABLE_AUTH, _disable_auth_if_present),
    (STEP_CHECK_ADMIN_BEFORE_DATA, _check_not_admin),
    (STEP_CHECK_NESTED_DATA, _check_no_nested_data),
    (STEP_DELETE_DATA, _delete_data),
    (STEP_CONFIRM_DATA_REMOVED, _confirm_data_removed),
    (STEP_CHECK_ADMIN_BEFORE_AUTH, _check_not_admin),
    (STEP_DELETE_AUTH, _delete_auth),
    (STEP_FINALIZE_RECORD, _finalize_record),
]

_DISABLE_STEPS: List[Tuple[str, Callable[[_Run], None]]] = [
    (STEP_RESTRICT_RECORD, _restrict_record),
    (STEP_DISABLE_AUTH, _disable_auth),
]
_ENABLE_STEPS: List[Tuple[str, Callable[[_Run], None]]] = [
    (STEP_RESTRICT_RECORD, _restrict_record),
    (STEP_DISABLE_AUTH, _disable_auth),
    (STEP_REVOKE_SESSIONS, _revoke_sessions),
    (STEP_SET_THRESHOLD, _set_threshold),
    (STEP_SETTLE, _settle),
    (STEP_ENABLE_AUTH, _enable_auth),
    (STEP_ACTIVATE_RECORD, _activate_record),
]


def _fully_enabled(view: AccountView) -> bool:
    lookup = view.record.lookup
    return (view.auth_status == access.AUTH_ENABLED and lookup.status == "valid"
            and lookup.record.state == "active" and lookup.record.sessions_valid_after is not None)


def _steps_for(operation: str, view: AccountView, held: _HeldLock):
    if operation == DISABLE:
        return _DISABLE_STEPS
    if operation == DELETE:
        return _DELETE_STEPS
    # A resumed Enable whose account changes all completed only needs verification.
    if held.previous is not None and held.previous.operation == ENABLE and _fully_enabled(view):
        return []
    return _ENABLE_STEPS


def _reached(operation: str, view: AccountView) -> bool:
    if operation == DISABLE:
        return view.state == STATE_DISABLED
    if operation == DELETE:
        lookup = view.record.lookup
        return (view.auth_status == access.AUTH_MISSING and lookup.status == "valid"
                and lookup.record.state == "deleted")
    return view.state == STATE_ACTIVE and _fully_enabled(view)


# -------------------------------------------------------------------------- public API
def get_account_view(uid: str, actor_uid: str) -> AccountView:
    """The account's Auth status, access record, any operation lock, and the actions allowed now. Read-only."""
    uid = _validate_uid(uid)
    return _load_view(_db(), uid, actor_uid)


def disable_account(uid: str, actor_uid: str) -> ActionResult:
    return _run(DISABLE, uid, actor_uid)


def enable_account(uid: str, actor_uid: str) -> ActionResult:
    return _run(ENABLE, uid, actor_uid)


def delete_account(uid: str, actor_uid: str, confirm_uid: Any) -> ActionResult:
    """Permanently delete a student account (M3B-3), or resume an unfinished deletion.

    `confirm_uid` must name the same account: the server-side confirmation, checked before Firebase is
    touched. The browser's typed-email confirmation is a usability safeguard only.
    """
    uid = _validate_uid(uid)
    if not isinstance(confirm_uid, str) or confirm_uid != uid:
        raise AccountActionError(DELETE_CONFIRMATION_MISMATCH, operation=DELETE)
    return _run(DELETE, uid, actor_uid)


def list_incomplete_deletions(actor_uid: str) -> List[AccountView]:
    """Accounts whose deletion started but did not finish, including those whose Auth account is already
    gone (and which therefore no longer appear in the Auth-based Manage Users list). Read-only.

    Found from deletion locks and from records in 'deleting'; at most INCOMPLETE_DELETIONS_LIMIT entries.
    """
    db = _db()
    uids = set()
    try:
        for snapshot in db.collection(LOCK_COLLECTION).stream():
            if (snapshot.to_dict() or {}).get("operation") == DELETE:
                uids.add(snapshot.id)
        for snapshot in db.collection(access.COLLECTION).where(filter=FieldFilter("state", "==", "deleting")).stream():
            uids.add(snapshot.id)
    except Exception as exc:
        logger.error("Account actions: incomplete deletions not listable: %s", type(exc).__name__)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE) from None
    views = []
    for uid in sorted(uid for uid in uids if _UID_RE.fullmatch(uid))[:INCOMPLETE_DELETIONS_LIMIT]:
        try:
            view = _load_view(db, uid, actor_uid)
        except AccountActionError as exc:
            if exc.code == USER_NOT_FOUND:
                continue
            raise
        if view.state in (STATE_DELETION_INCOMPLETE, STATE_IN_PROGRESS, STATE_PROTECTED):
            views.append(view)
    return views


def _run(operation: str, uid: str, actor_uid: str) -> ActionResult:
    uid = _validate_uid(uid)
    if not isinstance(actor_uid, str) or not actor_uid:
        raise ValueError("The acting administrator's uid is required")
    if uid == actor_uid:
        raise AccountActionError(SELF_ACTION_FORBIDDEN, operation=operation)
    db = _db()
    view = _load_view(db, uid, actor_uid)
    if operation not in view.allowed_actions:
        raise _refusal(view, operation)

    held = _acquire_lock(db, uid, operation, actor_uid)
    # Re-read under the lock: another operation may have finished in between.
    try:
        view = _load_view(db, uid, actor_uid, lock=held.previous)
    except AccountActionError:
        _abandon(db, held)
        raise
    if operation not in view.allowed_actions:
        _abandon(db, held)
        raise _refusal(view, operation)
    deleting = operation == DELETE
    try:
        # A deletion records which student documents existed (existence only, never their contents).
        extra = {"dataPresentBefore": _data_present(db, uid)} if deleting else None
        audit = _audit_start(db, held, uid, actor_uid, view, extra)
    except Exception as exc:
        logger.error("Account actions: audit record not created; nothing changed (uid=%s): %s", uid, type(exc).__name__)
        _abandon(db, held)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE, operation=operation) from None

    resumed = held.previous.operation_id if held.previous else None
    logger.info("Account %s started (operation_id=%s, target=%s, actor=%s, resumes=%s)",
                operation, held.operation_id, uid, actor_uid, resumed or "none")
    run = _Run(uid, view.record.lookup.record.version, db)
    step: Optional[str] = None
    after: Optional[AccountView] = None
    data_after: Optional[Dict[str, bool]] = None
    try:
        for step, action in _steps_for(operation, view, held):
            if deleting:
                _renew_lock(db, held)  # stop before this step if another process took the lock
            action(run)
        step = STEP_VERIFY
        if deleting:
            _renew_lock(db, held)
        try:
            after = _load_view(db, uid, actor_uid, lock=None)
        except AccountActionError as exc:
            raise _StepFailure(REASON_ACCOUNT_REMOVED if exc.code == USER_NOT_FOUND else REASON_STORE_UNAVAILABLE) from None
        if not _reached(operation, after):
            raise _StepFailure(REASON_UNEXPECTED_STATE)
        if deleting:
            data_after = _data_present(db, uid)
            if any(data_after.values()):
                raise _StepFailure(REASON_DATA_REMAINS)
    except _StepFailure as failure:
        reason = failure.reason
    except Exception as exc:  # never leave an unexplained partial state
        logger.error("Account actions: unexpected failure (operation_id=%s, step=%s): %s",
                     held.operation_id, step, type(exc).__name__)
        reason = REASON_INTERNAL
    else:
        audit_recorded = _audit_finish(audit, "completed", after, None, None,
                                       {"dataPresentAfter": data_after} if deleting else None)
        lock_released = _release(db, held)
        logger.info("Account %s completed (operation_id=%s, target=%s, audit_recorded=%s, lock_released=%s)",
                    operation, held.operation_id, uid, audit_recorded, lock_released)
        return ActionResult(operation, held.operation_id, after, resumed, audit_recorded, lock_released)

    if reason != REASON_LOCK_LOST:  # a lost lock belongs to another process now
        _mark_incomplete(db, held, step, reason)
    try:
        current = _load_view(db, uid, actor_uid, lock=None)
    except AccountActionError:
        current = None
    extra = None
    if deleting:
        try:
            extra = {"dataPresentAfter": _data_present(db, uid)}
        except _StepFailure:
            extra = {"dataPresentAfter": None}
    _audit_finish(audit, "incomplete", current, step, reason, extra)
    logger.error("Account %s incomplete (operation_id=%s, target=%s, step=%s, reason=%s)",
                 operation, held.operation_id, uid, step, reason)
    raise AccountActionError(OPERATION_INCOMPLETE, operation=operation, operation_id=held.operation_id,
                             failed_step=step, reason=reason)


def describe_view(view: AccountView, actor_uid: str) -> Dict[str, Any]:
    """An allow-listed description of the view for administrators (no email, name, token, claims or the
    uid of the administrator who started an operation; only whether it was the caller)."""
    def iso(value):
        if not isinstance(value, datetime):
            return None
        value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    lookup = view.record.lookup
    record = lookup.record if lookup.status == "valid" else None
    lock = view.lock
    return {
        "uid": view.uid,
        "auth_status": view.auth_status,
        "is_admin": view.is_admin,
        "is_self": view.is_self,
        "record": {
            "status": lookup.status,
            "state": record.state if record else None,
            "version": record.version if record else None,
            "sessions_valid_after": iso(record.sessions_valid_after) if record else None,
        },
        "issues": list(view.issues),
        "operation": None if lock is None else {
            "operation_id": lock.operation_id,
            "operation": lock.operation,
            "status": lock.status,
            "failed_step": lock.failed_step,
            "reason": lock.reason,
            "started_at": iso(lock.started_at),
            "updated_at": iso(lock.updated_at),
            "started_by_you": lock.actor_uid is not None and lock.actor_uid == actor_uid,
        },
        "state": view.state,
        "allowed_actions": list(view.allowed_actions),
    }
