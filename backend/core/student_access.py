# backend/core/student_access.py
"""
Student-data access check for the backend (M3B-3; strict enforcement since M3C).

The FastAPI backend reads student data with the Firebase Admin SDK, which bypasses Firestore Security
Rules, and it authenticates students with get_current_user (core/auth.py), which follows the Firebase
Authentication state only. An ID token stays valid for up to an hour after an account is disabled or
deleted, and a token refreshed from an earlier session keeps that session's sign-in time. This dependency
makes the backend's student-data endpoints apply the SAME decision as the experimental Firestore guard
(firestore-tests/account-access.experimental.rules, hasActiveAccount):

  require_student_data_access  -> get_current_user, then, in Firebase EMULATOR mode only, reads
                                  account_access/{uid} and allows the request only if
    * the record exists and is well-formed (missing or malformed: 403 ACCOUNT_ACCESS_DENIED);
    * its state is 'active' ('disabled': 403 ACCOUNT_ACCESS_DENIED; 'deleting'/'deleted': 403
      ACCOUNT_DELETED);
    * if it has sessionsValidAfter, the token's auth_time is an integer and
          (auth_time - 1 s) >= sessionsValidAfter
      exactly as the guard's signedInAfter(): every sign-in before the threshold is refused, including one
      in the same second, and so is one less than two seconds after it (401 SESSION_TOO_OLD: the student
      must sign in again). A missing or non-integer auth_time is refused when a threshold exists.
  Any failure to read the record answers 503 ACCOUNT_STATUS_UNAVAILABLE: fail closed, never served.

Scope and limits:
  * Emulator mode only, decided from the configuration Firebase was initialised with. In production mode
    the authenticated user is returned unchanged and no record is read: production has no account-access
    records yet (backfill pending, FL5), so production behaviour is unchanged until the production
    migration is approved.
  * Administrators are not exempt: like the guard, a missing record denies (administrators do not use the
    student-data endpoints).
  * Only the student-data endpoints use this dependency (routes/assessment.py). /api/auth/me and the
    Admin endpoints keep get_current_user / require_admin.
  * The comparison uses Firebase-issued auth_time and the Firestore server time of sessionsValidAfter; the
    backend host clock is not involved.
Logs contain the uid, codes and exception types only.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status

from core import firebase as core_firebase
from core.auth import AuthenticatedUser, get_current_user
from services import account_access_service as access

logger = logging.getLogger("student_access")

ACCOUNT_DELETED = "ACCOUNT_DELETED"
ACCOUNT_ACCESS_DENIED = "ACCOUNT_ACCESS_DENIED"
SESSION_TOO_OLD = "SESSION_TOO_OLD"
ACCOUNT_STATUS_UNAVAILABLE = "ACCOUNT_STATUS_UNAVAILABLE"
DELETION_STATES = ("deleting", "deleted")

MESSAGES = {
    ACCOUNT_DELETED: "This account has been deleted.",
    ACCOUNT_ACCESS_DENIED: "Your account can't access student data at the moment. Please contact the Route2UniKL administrator.",
    SESSION_TOO_OLD: "Your session started before your account was last re-enabled. Please sign in again.",
    ACCOUNT_STATUS_UNAVAILABLE: "Your account status could not be checked. Please try again.",
}
STATUS_BY_CODE = {
    ACCOUNT_DELETED: status.HTTP_403_FORBIDDEN,
    ACCOUNT_ACCESS_DENIED: status.HTTP_403_FORBIDDEN,
    SESSION_TOO_OLD: status.HTTP_401_UNAUTHORIZED,
    ACCOUNT_STATUS_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _emulator_mode() -> bool:
    config = core_firebase.initialized_config()
    return config is not None and config.mode == core_firebase.EMULATOR_MODE


def signed_in_after(auth_time: Optional[int], threshold: datetime) -> bool:
    """The guard's signedInAfter(): True only if (auth_time - 1 s) >= threshold, at full precision.

    auth_time is whole seconds since the epoch; the threshold is a timezone-aware timestamp (microseconds).
    """
    if not isinstance(auth_time, int) or isinstance(auth_time, bool):
        return False
    if not isinstance(threshold, datetime) or threshold.tzinfo is None:
        return False
    try:
        session_start = datetime.fromtimestamp(auth_time - 1, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return False
    return session_start >= threshold


def record_access_refusal(lookup: "access.RecordLookup", auth_time: Optional[int]) -> Optional[str]:
    """Why the guard would refuse this session, as a code; None if it would allow it (pure function)."""
    if lookup.status != "valid" or lookup.record is None:
        return ACCOUNT_ACCESS_DENIED
    record = lookup.record
    if record.state in DELETION_STATES:
        return ACCOUNT_DELETED
    if record.state != "active":
        return ACCOUNT_ACCESS_DENIED
    if record.sessions_valid_after is not None and not signed_in_after(auth_time, record.sessions_valid_after):
        return SESSION_TOO_OLD
    return None


def refusal(code: str) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if STATUS_BY_CODE[code] == status.HTTP_401_UNAUTHORIZED else None
    return HTTPException(status_code=STATUS_BY_CODE[code], detail={"code": code, "message": MESSAGES[code]},
                         headers=headers)


def read_record_or_refuse(uid: str) -> "access.RecordLookup":
    """The caller's record; any failure to read it is a 503 refusal (fail closed)."""
    try:
        return access.read_access_record(uid)
    except Exception as exc:
        logger.error("Student data access: account status unreadable (uid=%s): %s", uid, type(exc).__name__)
        raise refusal(ACCOUNT_STATUS_UNAVAILABLE) from None


def require_student_data_access(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """get_current_user, plus (emulator mode) the account-access guard's decision for this session."""
    if not _emulator_mode():
        return user
    code = record_access_refusal(read_record_or_refuse(user.uid), user.auth_time)
    if code is not None:
        logger.warning("Student data access refused (uid=%s, code=%s)", user.uid, code)
        raise refusal(code)
    return user
