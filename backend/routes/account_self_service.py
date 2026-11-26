# backend/routes/account_self_service.py
"""
Student self-service account deletion (M3C): LOCAL EMULATOR TESTING ONLY.

  POST /api/account/delete   body {"confirm_uid": "<the caller's own uid>"}
                             permanently deletes the signed-in student's own account (Firebase
                             Authentication account, users/, results/ and ai_assessments/{uid}), or resumes
                             the student's own unfinished deletion. Replaces the unsafe browser deletion in
                             Profile.jsx (S4, FL6, DL5).

main.py mounts this router only when the backend starts in Firebase emulator mode. Even when mounted, its
first dependency answers 404 unless the backend is still in emulator mode, before any token is verified or
Firebase is touched, and 503 unless Firebase was initialised in emulator mode (the checks of
routes/admin_account_actions.py). Then, in this order:

  1. get_current_user: a valid, unrevoked ID token for an enabled account. The uid comes ONLY from it.
  2. Administrators (token claim admin: true) are refused: 403 ADMIN_TARGET_FORBIDDEN.
  3. The body is read and validated only now (after authentication, so a malformed body never answers
     before the caller is authenticated; audit DA7): exactly {"confirm_uid": <string>}, equal to the
     token's uid, else 422.
  4. Recent sign-in: the token's auth_time must be within RECENT_SIGN_IN_SECONDS of the server's time
     (and not in the future beyond a small skew), else 403 RECENT_SIGN_IN_REQUIRED. The browser
     re-authenticates with the student's password and refreshes the token just before the request.
  5. The access record decides, exactly as for the student-data endpoints (core/student_access.py): an
     'active' record whose sessionsValidAfter the session satisfies; or a 'deleting' record (the student's
     own unfinished deletion, resumed). Missing, malformed or 'disabled' records: 403
     ACCOUNT_ACCESS_DENIED; 'deleted': 403 ACCOUNT_DELETED; an old session: 401 SESSION_TOO_OLD; record
     unreadable: 503 ACCOUNT_STATUS_UNAVAILABLE. Fail closed.
  6. services/account_action_service.delete_own_account(): the M3B-3 deletion steps (access closed first,
     data deleted in one atomic batch, Auth deleted only after the data removal is confirmed, tombstone and
     audit kept, locks renewed before every step). Any partial failure is 503 OPERATION_INCOMPLETE with
     its operation identifier, failed step and reason; it is recorded and resumable.

Responses contain codes, fixed messages and operation identifiers only: no email address, name, token or
Firebase error text. Logs contain the uid and codes only. No rate limiting yet (L7): emulator only.
"""
import json
import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from core import student_access
from core.auth import AuthenticatedUser, get_current_user
from routes.admin_account_actions import _emulator_ready, account_actions_enabled
from services import account_action_service as actions

logger = logging.getLogger("account_self_service")

RECENT_SIGN_IN_SECONDS = 300     # the sign-in (or re-authentication) must be at most 5 minutes old
FUTURE_SKEW_SECONDS = 5          # tolerated clock difference for an auth_time slightly ahead of this server
MAX_BODY_BYTES = 1024
_now_seconds = time.time         # replaced in tests

INVALID_REQUEST = "INVALID_REQUEST"
RECENT_SIGN_IN_REQUIRED = "RECENT_SIGN_IN_REQUIRED"
SELF_DELETE_UNAVAILABLE = "ACCOUNT_ACTION_UNAVAILABLE"

STATUS_BY_CODE = {
    INVALID_REQUEST: 422,
    actions.DELETE_CONFIRMATION_MISMATCH: 422,
    RECENT_SIGN_IN_REQUIRED: status.HTTP_403_FORBIDDEN,
    actions.ADMIN_TARGET_FORBIDDEN: status.HTTP_403_FORBIDDEN,
    actions.ACCESS_RECORD_UNSUPPORTED: status.HTTP_403_FORBIDDEN,
    actions.USER_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    actions.DELETE_NOT_ALLOWED: status.HTTP_409_CONFLICT,
    actions.OPERATION_IN_PROGRESS: status.HTTP_409_CONFLICT,
    actions.INCOMPLETE_OPERATION_PENDING: status.HTTP_409_CONFLICT,
    actions.ACCOUNT_DELETION_IN_PROGRESS: status.HTTP_409_CONFLICT,
    actions.ACCOUNT_DELETED: status.HTTP_409_CONFLICT,
    actions.ACCOUNT_ACTION_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    actions.OPERATION_INCOMPLETE: status.HTTP_503_SERVICE_UNAVAILABLE,
}

MESSAGES = {
    INVALID_REQUEST: "The deletion request was not valid. Nothing was changed.",
    actions.DELETE_CONFIRMATION_MISMATCH: "The deletion was not confirmed for your account. Nothing was changed.",
    RECENT_SIGN_IN_REQUIRED: "Please confirm your password again to delete your account. Nothing was changed.",
    actions.ADMIN_TARGET_FORBIDDEN: "Administrator accounts cannot be deleted here. Nothing was changed.",
    actions.ACCESS_RECORD_UNSUPPORTED: "Your account cannot be deleted here. Please contact the Route2UniKL administrator.",
    actions.USER_NOT_FOUND: "Your account could not be found.",
    actions.DELETE_NOT_ALLOWED: "Your account cannot be deleted in its current state. Please contact the Route2UniKL administrator.",
    actions.OPERATION_IN_PROGRESS: "Another change to your account is in progress. Try again in a few minutes. Nothing was changed.",
    actions.INCOMPLETE_OPERATION_PENDING: "An earlier change to your account has not finished. Please contact the Route2UniKL administrator.",
    actions.ACCOUNT_DELETION_IN_PROGRESS: "Your account is already being deleted.",
    actions.ACCOUNT_DELETED: "Your account has already been deleted.",
    actions.ACCOUNT_ACTION_UNAVAILABLE: "Account deletion is temporarily unavailable. Nothing was changed. Please try again.",
    actions.OPERATION_INCOMPLETE: "The deletion did not finish. It has been recorded and can be completed later.",
}


def _error(code: str, extra: Dict[str, Any] = None) -> HTTPException:
    detail = {"code": code, "message": MESSAGES.get(code, "The request could not be completed.")}
    detail.update(extra or {})
    return HTTPException(status_code=STATUS_BY_CODE.get(code, status.HTTP_503_SERVICE_UNAVAILABLE), detail=detail)


def self_service_enabled() -> bool:
    """Only in Firebase emulator mode (decided from the environment). Also used by main.py."""
    return account_actions_enabled()


def require_local_emulator() -> None:
    """Runs before authentication: outside emulator mode this route does not exist."""
    if not self_service_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not _emulator_ready():
        raise _error(SELF_DELETE_UNAVAILABLE)


router = APIRouter(dependencies=[Depends(require_local_emulator)])


def is_recent_sign_in(auth_time: Any, now: float) -> bool:
    if not isinstance(auth_time, int) or isinstance(auth_time, bool):
        return False
    return now - RECENT_SIGN_IN_SECONDS <= auth_time <= now + FUTURE_SKEW_SECONDS


async def _confirm_uid(request: Request) -> str:
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
        raise _error(INVALID_REQUEST)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise _error(INVALID_REQUEST)
    try:
        payload = json.loads(body)
    except ValueError:
        raise _error(INVALID_REQUEST) from None
    if not isinstance(payload, dict) or set(payload) != {"confirm_uid"} or not isinstance(payload["confirm_uid"], str):
        raise _error(INVALID_REQUEST)
    return payload["confirm_uid"]


def _check_record(user: AuthenticatedUser) -> None:
    """The student-data decision (core/student_access.py), except that the student's own unfinished
    deletion ('deleting') may be resumed. Fails closed."""
    lookup = student_access.read_record_or_refuse(user.uid)
    if lookup.status == "valid" and lookup.record.state == "deleting":
        return
    code = student_access.record_access_refusal(lookup, user.auth_time)
    if code is not None:
        logger.warning("Self-service deletion refused by the access record (uid=%s, code=%s)", user.uid, code)
        raise student_access.refusal(code)


@router.post("/delete")
async def delete_own_account(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    """Permanently delete the signed-in student's own account (or resume its unfinished deletion)."""
    if user.is_admin:
        logger.warning("Self-service deletion refused: administrator account (uid=%s)", user.uid)
        raise _error(actions.ADMIN_TARGET_FORBIDDEN)
    confirm_uid = await _confirm_uid(request)
    if confirm_uid != user.uid:
        raise _error(actions.DELETE_CONFIRMATION_MISMATCH)
    if not is_recent_sign_in(user.auth_time, _now_seconds()):
        logger.info("Self-service deletion refused: sign-in not recent (uid=%s)", user.uid)
        raise _error(RECENT_SIGN_IN_REQUIRED)
    await run_in_threadpool(_check_record, user)
    try:
        result = await run_in_threadpool(actions.delete_own_account, user.uid, confirm_uid)
    except actions.AccountActionError as exc:
        extra = None
        if exc.code == actions.OPERATION_INCOMPLETE:
            extra = {"operation": exc.operation, "operation_id": exc.operation_id,
                     "failed_step": exc.failed_step, "reason": exc.reason}
        raise _error(exc.code, extra) from None
    return JSONResponse(status_code=200, content={
        "outcome": "completed",
        "operation": "delete",
        "operation_id": result.operation_id,
        "resumed_operation_id": result.resumed_operation_id,
        "audit_recorded": result.audit_recorded,
        "lock_released": result.lock_released,
    })
