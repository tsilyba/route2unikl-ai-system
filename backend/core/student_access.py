# backend/core/student_access.py
"""
Student-data access check for the backend (M3B-3).

The FastAPI backend reads student data with the Firebase Admin SDK, which bypasses Firestore Security
Rules, and it authenticates students with get_current_user (core/auth.py). A token issued before an
administrator started deleting the account can remain valid for up to an hour, and the backend did not
consult the account-access record (JL1). This dependency closes that gap for deletion:

  require_student_data_access  -> get_current_user, then, in Firebase EMULATOR mode only, refuses an
                                  account whose account-access record is 'deleting' or 'deleted'
                                  (HTTP 403, ACCOUNT_DELETED), even with a token that is otherwise valid.

Scope and limits:
  * Emulator mode only, decided from the configuration Firebase was initialised with. In production mode
    it returns the authenticated user unchanged: production has no account-access records yet
    (backfill pending), so production behaviour is unchanged until the production migration.
  * Only 'deleting' and 'deleted' are refused. A missing record (an account registered before the
    records existed, or an administrator) and 'active'/'disabled' records are not refused here: disabled
    accounts are already refused by get_current_user (Firebase Authentication), as before.
  * Fails closed: if the record cannot be read, the request is refused (503), never served.
Logs contain the uid and exception types only.
"""
import logging

from fastapi import Depends, HTTPException, status

from core import firebase as core_firebase
from core.auth import AuthenticatedUser, get_current_user
from services import account_access_service as access

logger = logging.getLogger("student_access")

ACCOUNT_DELETED = "ACCOUNT_DELETED"
ACCOUNT_STATUS_UNAVAILABLE = "ACCOUNT_STATUS_UNAVAILABLE"
BLOCKED_STATES = ("deleting", "deleted")


def _emulator_mode() -> bool:
    config = core_firebase.initialized_config()
    return config is not None and config.mode == core_firebase.EMULATOR_MODE


def require_student_data_access(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """get_current_user, plus: refuse an account that is being deleted or has been deleted (emulator mode)."""
    if not _emulator_mode():
        return user
    try:
        lookup = access.read_access_record(user.uid)
    except Exception as exc:
        logger.error("Student data access: account status unreadable (uid=%s): %s", user.uid, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": ACCOUNT_STATUS_UNAVAILABLE,
                    "message": "Your account status could not be checked. Please try again."},
        ) from None
    if lookup.status == "valid" and lookup.record.state in BLOCKED_STATES:
        logger.warning("Student data access refused: account deleted or being deleted (uid=%s)", user.uid)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": ACCOUNT_DELETED, "message": "This account has been deleted."},
        )
    return user
