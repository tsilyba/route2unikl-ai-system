# backend/services/account_action_service.py
"""
Admin account actions: Disable and Enable student accounts (M3B-2).

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

Every record change is version-checked: the version must be the one this operation expects, and the
write carries a precondition on the document's update time, so a record changed by anyone else is never
overwritten (account_access_service.change_record_state). The record never gets extra fields: operation
locks live in account_operations/{uid} and audit records in account_audit/{operationId}, both
backend-only (the experimental rules deny every browser access to unknown collections).

Locks: one per target account, created atomically with a lease. A running lock refuses every other
action (409). If an operation stops part-way, its lock stays as 'incomplete' (also when the process dies
and the lease expires) with the failed step and a reason code: the account shows as incomplete, and the
same action resumes it from the current state (every step is idempotent). Disable may also take over an
incomplete Enable (the restricting direction); Enable may not take over an incomplete Disable.

Refused without any change: the caller's own account, accounts with the admin custom claim, Auth
accounts that do not exist, and missing, malformed, 'deleting' or 'deleted' records (records are never
created, repaired or reactivated here). Outcomes are truthful: an operation is reported as completed only
after verification; any partial failure is OPERATION_INCOMPLETE. Logs and audit records contain uids,
operation identifiers, steps and codes only: never email addresses, names, tokens or passwords.
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

from core.firebase import initialize_firebase
from services import account_access_service as access
from services.user_admin_service import UID_PATTERN, is_admin_account

logger = logging.getLogger("account_action_service")

LOCK_COLLECTION = "account_operations"
AUDIT_COLLECTION = "account_audit"
LEASE_SECONDS = 120
ENABLE_SETTLE_SECONDS = 3.0
REVOCATION_MARGIN_SECONDS = 1.1
WRITE_TIMEOUT_SECONDS = 10
_UID_RE = re.compile(UID_PATTERN)
_sleep = time.sleep  # replaced in tests

DISABLE = "disable"
ENABLE = "enable"
ACTIONS = (DISABLE, ENABLE)

# Account states shown to administrators
STATE_ACTIVE = "active"
STATE_DISABLED = "disabled"
STATE_INCONSISTENT = "inconsistent"   # Auth and the record disagree, no operation recorded
STATE_INCOMPLETE = "incomplete"       # an operation stopped part-way and can be resumed
STATE_IN_PROGRESS = "in_progress"     # an operation is running
STATE_PROTECTED = "protected"         # the caller's own account or an administrator account
STATE_UNSUPPORTED = "unsupported"     # missing, malformed, 'deleting' or 'deleted' record

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

# Why an operation stopped (AccountActionError.reason)
REASON_AUTH_UNAVAILABLE = "AUTH_UNAVAILABLE"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_RECORD_CHANGED = "RECORD_CHANGED"
REASON_ACCOUNT_REMOVED = "ACCOUNT_REMOVED"
REASON_UNEXPECTED_STATE = "UNEXPECTED_STATE"
REASON_INTERNAL = "INTERNAL_ERROR"

# Steps
STEP_RESTRICT_RECORD = "restrict_record"
STEP_DISABLE_AUTH = "disable_auth"
STEP_REVOKE_SESSIONS = "revoke_sessions"
STEP_SET_THRESHOLD = "set_session_threshold"
STEP_SETTLE = "settle"
STEP_ENABLE_AUTH = "enable_auth"
STEP_ACTIVATE_RECORD = "activate_record"
STEP_VERIFY = "verify"

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


def _lock_from_data(data: Dict[str, Any], now: datetime) -> OperationLock:
    status = data.get("status")
    lease = data.get("leaseExpiresAt")
    if status == LOCK_RUNNING and not (isinstance(lease, datetime) and lease.tzinfo is not None and lease > now):
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
    if lookup.status != "valid" or lookup.record.state not in ("active", "disabled"):
        return STATE_UNSUPPORTED, ()
    if lock is not None:
        if lock.status == LOCK_RUNNING:
            return STATE_IN_PROGRESS, ()
        # An unfinished Enable can be resumed or cancelled by Disable; an unfinished Disable only resumed.
        return STATE_INCOMPLETE, (ENABLE, DISABLE) if lock.operation == ENABLE else (DISABLE,)
    record_state = lookup.record.state
    if auth_status == access.AUTH_ENABLED and record_state == "active":
        return STATE_ACTIVE, (DISABLE,)
    if auth_status == access.AUTH_DISABLED and record_state == "disabled":
        return STATE_DISABLED, (ENABLE,)
    return STATE_INCONSISTENT, (DISABLE, ENABLE)


def _load_view(db, uid: str, actor_uid: str, *, lock: Any = _STORED) -> AccountView:
    try:
        account = firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        raise AccountActionError(USER_NOT_FOUND) from None
    except Exception as exc:
        logger.error("Account actions: Firebase Authentication unavailable (uid=%s): %s", uid, type(exc).__name__)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE) from None
    # Anything other than an explicit False is treated as disabled (fail closed), as in account_access_service.
    auth_status = access.AUTH_ENABLED if account.disabled is False else access.AUTH_DISABLED
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
    is_admin = is_admin_account(account)
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
    elif view.state == STATE_INCOMPLETE:
        code = INCOMPLETE_OPERATION_PENDING
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
            "leaseExpiresAt": _now() + timedelta(seconds=LEASE_SECONDS), "failedStep": None, "reason": None,
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


def _audit_start(db, held: _HeldLock, uid: str, actor_uid: str, view: AccountView):
    ref = db.collection(AUDIT_COLLECTION).document(held.operation_id)
    ref.create({
        "operationId": held.operation_id, "operation": held.operation, "actorUid": actor_uid, "targetUid": uid,
        "outcome": "started", "failedStep": None, "reason": None,
        "resumesOperationId": held.previous.operation_id if held.previous else None,
        "resumesOperation": held.previous.operation if held.previous else None,
        "before": _state_summary(view), "after": None,
        "startedAt": SERVER_TIMESTAMP, "finishedAt": None,
    }, retry=None, timeout=WRITE_TIMEOUT_SECONDS)
    return ref


def _audit_finish(ref, outcome: str, after: Optional[AccountView], step: Optional[str], reason: Optional[str]) -> bool:
    try:
        ref.update({"outcome": outcome, "failedStep": step, "reason": reason, "after": _state_summary(after),
                    "finishedAt": SERVER_TIMESTAMP}, retry=None, timeout=WRITE_TIMEOUT_SECONDS)
        return True
    except Exception as exc:
        logger.error("Account actions: audit outcome not recorded (operation_id=%s): %s", ref.id, type(exc).__name__)
        return False


# ------------------------------------------------------------------------------- steps
class _Run:
    """Progress of one operation: the record version it expects next."""

    def __init__(self, uid: str, version: int):
        self.uid = uid
        self.version = version


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
    # A resumed Enable whose account changes all completed only needs verification.
    if held.previous is not None and held.previous.operation == ENABLE and _fully_enabled(view):
        return []
    return _ENABLE_STEPS


def _reached(operation: str, view: AccountView) -> bool:
    if operation == DISABLE:
        return view.state == STATE_DISABLED
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
    try:
        audit = _audit_start(db, held, uid, actor_uid, view)
    except Exception as exc:
        logger.error("Account actions: audit record not created; nothing changed (uid=%s): %s", uid, type(exc).__name__)
        _abandon(db, held)
        raise AccountActionError(ACCOUNT_ACTION_UNAVAILABLE, operation=operation) from None

    resumed = held.previous.operation_id if held.previous else None
    logger.info("Account %s started (operation_id=%s, target=%s, actor=%s, resumes=%s)",
                operation, held.operation_id, uid, actor_uid, resumed or "none")
    run = _Run(uid, view.record.lookup.record.version)
    step: Optional[str] = None
    after: Optional[AccountView] = None
    try:
        for step, action in _steps_for(operation, view, held):
            action(run)
        step = STEP_VERIFY
        try:
            after = _load_view(db, uid, actor_uid, lock=None)
        except AccountActionError:
            raise _StepFailure(REASON_STORE_UNAVAILABLE) from None
        if not _reached(operation, after):
            raise _StepFailure(REASON_UNEXPECTED_STATE)
    except _StepFailure as failure:
        reason = failure.reason
    except Exception as exc:  # never leave an unexplained partial state
        logger.error("Account actions: unexpected failure (operation_id=%s, step=%s): %s",
                     held.operation_id, step, type(exc).__name__)
        reason = REASON_INTERNAL
    else:
        audit_recorded = _audit_finish(audit, "completed", after, None, None)
        lock_released = _release(db, held)
        logger.info("Account %s completed (operation_id=%s, target=%s, audit_recorded=%s, lock_released=%s)",
                    operation, held.operation_id, uid, audit_recorded, lock_released)
        return ActionResult(operation, held.operation_id, after, resumed, audit_recorded, lock_released)

    _mark_incomplete(db, held, step, reason)
    try:
        current = _load_view(db, uid, actor_uid, lock=None)
    except AccountActionError:
        current = None
    _audit_finish(audit, "incomplete", current, step, reason)
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
