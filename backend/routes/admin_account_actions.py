# backend/routes/admin_account_actions.py
"""
Admin account actions (M3B-2, M3B-3): LOCAL EMULATOR TESTING ONLY.

  GET  /api/admin/users/{uid}/access    access state, any unfinished operation, and the allowed actions
  POST /api/admin/users/{uid}/disable   disable a student account
  POST /api/admin/users/{uid}/enable    enable a disabled student account
  POST /api/admin/users/{uid}/delete    permanently delete a student account, or resume an unfinished
                                        deletion; body {"confirm_uid": "<the same uid>"} (M3B-3)
  GET  /api/admin/account-operations/incomplete-deletions
                                        unfinished deletions, including accounts whose Firebase
                                        Authentication account is already gone (M3B-3)

main.py mounts these routers only when the backend starts in Firebase emulator mode. Even when mounted,
each router's first dependency answers 404 unless the backend is still in emulator mode, before any token
is verified or Firebase is touched; its second answers 503 unless Firebase was initialised in emulator mode
(the same checks as routes/registration.py). Then require_admin runs, before the service.

Workflow, locking, audit and recovery: services/account_action_service.py. Responses are allow-listed
by the models below: no email address, name, token, custom claims, or the uid of another administrator.
Errors carry a fixed code and message, and for an incomplete operation its identifier, failed step and
reason code; Firebase error messages are never returned.
"""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field

from core import firebase as core_firebase
from core.auth import AuthenticatedUser, require_admin
from services import account_action_service as actions
from services.user_admin_service import UID_PATTERN

AccountState = Literal["active", "disabled", "inconsistent", "incomplete", "in_progress", "protected", "unsupported",
                       "deletion_incomplete", "deleted"]
Action = Literal["disable", "enable", "delete"]

STATUS_BY_CODE = {
    actions.INVALID_UID: 422,
    actions.DELETE_CONFIRMATION_MISMATCH: 422,
    actions.SELF_ACTION_FORBIDDEN: status.HTTP_403_FORBIDDEN,
    actions.ADMIN_TARGET_FORBIDDEN: status.HTTP_403_FORBIDDEN,
    actions.USER_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    actions.ACCESS_RECORD_UNSUPPORTED: status.HTTP_409_CONFLICT,
    actions.ALREADY_DISABLED: status.HTTP_409_CONFLICT,
    actions.ALREADY_ACTIVE: status.HTTP_409_CONFLICT,
    actions.OPERATION_IN_PROGRESS: status.HTTP_409_CONFLICT,
    actions.INCOMPLETE_OPERATION_PENDING: status.HTTP_409_CONFLICT,
    actions.ACCOUNT_DELETION_IN_PROGRESS: status.HTTP_409_CONFLICT,
    actions.ACCOUNT_DELETED: status.HTTP_409_CONFLICT,
    actions.DELETE_NOT_ALLOWED: status.HTTP_409_CONFLICT,
    actions.ACCOUNT_ACTION_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    actions.OPERATION_INCOMPLETE: status.HTTP_503_SERVICE_UNAVAILABLE,
}

MESSAGES = {
    actions.INVALID_UID: "This account ID is not valid.",
    actions.DELETE_CONFIRMATION_MISMATCH: "The deletion was not confirmed for this account. Nothing was changed.",
    actions.SELF_ACTION_FORBIDDEN: "You cannot disable, enable or delete your own account.",
    actions.ADMIN_TARGET_FORBIDDEN: "Administrator accounts cannot be disabled, enabled or deleted here.",
    actions.USER_NOT_FOUND: "No account exists with this ID.",
    actions.ACCESS_RECORD_UNSUPPORTED: "This account has no usable access record, so it cannot be changed here.",
    actions.ALREADY_DISABLED: "This account is already disabled.",
    actions.ALREADY_ACTIVE: "This account is already active.",
    actions.OPERATION_IN_PROGRESS: "Another change to this account is in progress. Try again in a moment.",
    actions.INCOMPLETE_OPERATION_PENDING: "An earlier change to this account did not finish. Resume it first.",
    actions.ACCOUNT_DELETION_IN_PROGRESS: "This account is being deleted. Only the deletion can be resumed.",
    actions.ACCOUNT_DELETED: "This account has already been deleted.",
    actions.DELETE_NOT_ALLOWED: "Only an active or disabled account can be deleted. Resolve its state first.",
    actions.ACCOUNT_ACTION_UNAVAILABLE: "Account actions are temporarily unavailable. Nothing was changed.",
    actions.OPERATION_INCOMPLETE: "The change did not finish. It has been recorded and can be resumed.",
}


def account_actions_enabled() -> bool:
    """Only in Firebase emulator mode; decided from the environment without touching Firebase.
    Also used by main.py to decide whether to mount these routers at all."""
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
operations_router = APIRouter(dependencies=[Depends(require_local_emulator)])


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
    resumable_after: Optional[str]  # M3C (DL14): for a running lock, when it can be resumed if it has stopped
    started_by_you: bool


class AccessState(BaseModel):
    uid: str
    auth_status: Literal["enabled", "disabled", "missing"]
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


class IncompleteDeletions(BaseModel):
    items: List[AccessState]


class DeleteRequest(BaseModel):
    """The server-side confirmation: the request must name the same account as the path."""
    model_config = ConfigDict(extra="forbid")

    confirm_uid: str = Field(..., min_length=1, max_length=128)


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


@router.post("/{uid}/delete", response_model=AccountActionResponse)
def delete_account(body: DeleteRequest, uid: str = UidPath, admin: AuthenticatedUser = Depends(require_admin)):
    """Permanently delete a student account (M3B-3), or resume an unfinished deletion.

    Reported as completed only after the student's documents and Firebase Authentication account are
    confirmed gone and the record is 'deleted'; any partial failure is OPERATION_INCOMPLETE (resumable).
    """
    return _perform(lambda target, actor: actions.delete_account(target, actor, body.confirm_uid), uid, admin)


@operations_router.get("/incomplete-deletions", response_model=IncompleteDeletions)
def list_incomplete_deletions(admin: AuthenticatedUser = Depends(require_admin)):
    """Unfinished deletions, including accounts no longer in Firebase Authentication. Read-only."""
    try:
        views = actions.list_incomplete_deletions(admin.uid)
    except actions.AccountActionError as exc:
        raise _error(exc) from None
    return {"items": [actions.describe_view(view, admin.uid) for view in views]}
