# backend/routes/admin_account_actions.py
"""
Admin account actions (M3B-2): LOCAL EMULATOR TESTING ONLY.

  GET  /api/admin/users/{uid}/access    access state, any unfinished operation, and the allowed actions
  POST /api/admin/users/{uid}/disable   disable a student account
  POST /api/admin/users/{uid}/enable    enable a disabled student account

main.py mounts this router only when the backend starts in Firebase emulator mode. Even when mounted, the
router's first dependency answers 404 unless the backend is still in emulator mode, before any token is
verified or Firebase is touched; its second answers 503 unless Firebase was initialised in emulator mode
(the same checks as routes/registration.py). Then require_admin runs, before the service.

Workflow, locking, audit and recovery: services/account_action_service.py. Responses are allow-listed
by the models below: no email address, name, token, custom claims, or the uid of another administrator.
Errors carry a fixed code and message, and for an incomplete operation its identifier, failed step and
reason code; Firebase error messages are never returned.
"""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel

from core import firebase as core_firebase
from core.auth import AuthenticatedUser, require_admin
from services import account_action_service as actions
from services.user_admin_service import UID_PATTERN

AccountState = Literal["active", "disabled", "inconsistent", "incomplete", "in_progress", "protected", "unsupported"]
Action = Literal["disable", "enable"]

STATUS_BY_CODE = {
    actions.INVALID_UID: 422,
    actions.SELF_ACTION_FORBIDDEN: status.HTTP_403_FORBIDDEN,
    actions.ADMIN_TARGET_FORBIDDEN: status.HTTP_403_FORBIDDEN,
    actions.USER_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    actions.ACCESS_RECORD_UNSUPPORTED: status.HTTP_409_CONFLICT,
    actions.ALREADY_DISABLED: status.HTTP_409_CONFLICT,
    actions.ALREADY_ACTIVE: status.HTTP_409_CONFLICT,
    actions.OPERATION_IN_PROGRESS: status.HTTP_409_CONFLICT,
    actions.INCOMPLETE_OPERATION_PENDING: status.HTTP_409_CONFLICT,
    actions.ACCOUNT_ACTION_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    actions.OPERATION_INCOMPLETE: status.HTTP_503_SERVICE_UNAVAILABLE,
}

MESSAGES = {
    actions.INVALID_UID: "This account ID is not valid.",
    actions.SELF_ACTION_FORBIDDEN: "You cannot disable or enable your own account.",
    actions.ADMIN_TARGET_FORBIDDEN: "Administrator accounts cannot be disabled or enabled here.",
    actions.USER_NOT_FOUND: "No account exists with this ID.",
    actions.ACCESS_RECORD_UNSUPPORTED: "This account has no usable access record, so it cannot be changed here.",
    actions.ALREADY_DISABLED: "This account is already disabled.",
    actions.ALREADY_ACTIVE: "This account is already active.",
    actions.OPERATION_IN_PROGRESS: "Another change to this account is in progress. Try again in a moment.",
    actions.INCOMPLETE_OPERATION_PENDING: "An earlier change to this account did not finish. Resume it first.",
    actions.ACCOUNT_ACTION_UNAVAILABLE: "Account actions are temporarily unavailable. Nothing was changed.",
    actions.OPERATION_INCOMPLETE: "The change did not finish. It has been recorded and can be resumed.",
}

def account_actions_enabled() -> bool:
    """Only in Firebase emulator mode; decided from the environment without touching Firebase.
    Also used by main.py to decide whether to mount this router at all."""
    try:
        return core_firebase.firebase_mode() == core_firebase.EMULATOR_MODE
    except core_firebase.FirebaseConfigError:
        return False


def _emulator_ready() -> bool:
    """Firebase is initialised, still matches its recorded configuration, and that record is emulator mode."""
    try:
        core_firebase.initialize_firebase()
        core_firebase.check_runtime_configuration()
    except Exception:
        return False
    config = core_firebase.initialized_config()
    return config is not None and config.mode == core_firebase.EMULATOR_MODE


def require_local_emulator() -> None:
    """Runs before require_admin: outside emulator mode these routes do not exist."""
    if not account_actions_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not _emulator_ready():
        raise _error(actions.AccountActionError(actions.ACCOUNT_ACTION_UNAVAILABLE))


# Router-level dependencies are solved before each route's own (require_admin).
router = APIRouter(dependencies=[Depends(require_local_emulator)])


class RecordState(BaseModel):
    status: Literal["valid", "missing", "malformed"]
    state: Optional[Literal["active", "disabled", "deleting", "deleted"]]
    version: Optional[int]
    sessions_valid_after: Optional[str]


class OperationState(BaseModel):
    operation_id: Optional[str]
    operation: Optional[Action]
    status: Literal["running", "incomplete"]
    failed_step: Optional[str]
    reason: Optional[str]
    started_at: Optional[str]
    updated_at: Optional[str]
    started_by_you: bool


class AccessState(BaseModel):
    uid: str
    auth_status: Literal["enabled", "disabled"]
    is_admin: bool
    is_self: bool
    record: RecordState
    issues: List[str]
    operation: Optional[OperationState]
    state: AccountState
    allowed_actions: List[Action]


class AccountActionResponse(BaseModel):
    outcome: Literal["completed"]
    operation: Action
    operation_id: str
    resumed_operation_id: Optional[str]
    audit_recorded: bool
    lock_released: bool
    account: AccessState


def _error(exc: "actions.AccountActionError") -> HTTPException:
    detail = {"code": exc.code, "message": MESSAGES.get(exc.code, "The request could not be completed.")}
    if exc.code == actions.OPERATION_INCOMPLETE:
        detail.update({"operation": exc.operation, "operation_id": exc.operation_id,
                       "failed_step": exc.failed_step, "reason": exc.reason})
    return HTTPException(status_code=STATUS_BY_CODE.get(exc.code, status.HTTP_503_SERVICE_UNAVAILABLE), detail=detail)


UidPath = Path(..., min_length=1, max_length=128, pattern=UID_PATTERN)


@router.get("/{uid}/access", response_model=AccessState)
def get_access_state(uid: str = UidPath, admin: AuthenticatedUser = Depends(require_admin)):
    """The account's access state and the actions allowed now. Read-only."""
    try:
        return actions.describe_view(actions.get_account_view(uid, admin.uid), admin.uid)
    except actions.AccountActionError as exc:
        raise _error(exc) from None


def _perform(operation, uid: str, admin: AuthenticatedUser):
    try:
        result = operation(uid, admin.uid)
    except actions.AccountActionError as exc:
        raise _error(exc) from None
    return {
        "outcome": "completed",
        "operation": result.operation,
        "operation_id": result.operation_id,
        "resumed_operation_id": result.resumed_operation_id,
        "audit_recorded": result.audit_recorded,
        "lock_released": result.lock_released,
        "account": actions.describe_view(result.view, admin.uid),
    }


@router.post("/{uid}/disable", response_model=AccountActionResponse)
def disable_account(uid: str = UidPath, admin: AuthenticatedUser = Depends(require_admin)):
    """Disable a student account: access record first, then Firebase Authentication."""
    return _perform(actions.disable_account, uid, admin)


@router.post("/{uid}/enable", response_model=AccountActionResponse)
def enable_account(uid: str = UidPath, admin: AuthenticatedUser = Depends(require_admin)):
    """Enable a disabled student account: earlier sessions stay blocked; the record becomes active last."""
    return _perform(actions.enable_account, uid, admin)
