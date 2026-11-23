# backend/core/auth.py
"""
Firebase ID-token authentication and authorization dependencies for FastAPI.

- get_current_user : verifies `Authorization: Bearer <Firebase ID token>` and
                     returns the authenticated user (HTTP 401 if missing/invalid).
- require_admin    : additionally requires the custom claim `admin: true`
                     (HTTP 403 otherwise). Intended for future Admin APIs.
- ensure_same_user : rejects requests that name another user's ID (HTTP 403).

Identity always comes from the verified token; client-supplied user IDs are
never trusted for authorization. Tokens and exception details are never
logged or returned to clients.

Before and after every token verification, the Firebase configuration is
checked against the one recorded at initialization (see core.firebase). The
Admin SDK reads FIREBASE_AUTH_EMULATOR_HOST during verification and, while it
is set, skips signature checks; a mismatch therefore answers 503 and no
identity is accepted.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exceptions

from core.firebase import check_runtime_configuration, initialize_firebase

logger = logging.getLogger("auth")

# auto_error=False: a missing or non-Bearer header returns None, so we can
# answer with an explicit 401 instead of a framework default.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Firebase ID token from the signed-in user (Authorization: Bearer <token>)",
)

# Tolerate small clock drift between this server and Google's token issuer.
CLOCK_SKEW_SECONDS = 5

# Machine-readable code sent with HTTP 503 when token verification cannot be
# completed (e.g. Google key servers or the revocation lookup are unreachable).
# Clients use it to show a temporary sign-in-service error instead of treating
# the response as an ordinary backend/AI outage.
AUTH_SERVICE_UNAVAILABLE = "AUTH_SERVICE_UNAVAILABLE"


@dataclass(frozen=True)
class AuthenticatedUser:
    uid: str
    email: Optional[str]
    is_admin: bool


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": AUTH_SERVICE_UNAVAILABLE,
            "message": "Authentication service is temporarily unavailable. Please try again.",
        },
    )


def _ensure_firebase_app(initialize_if_missing: bool = True) -> None:
    """Confirm that Firebase is usable under the configuration it was initialized with.

    Reuses the app created by core.firebase (initializing it only if missing and
    `initialize_if_missing`), then checks that the current environment still
    matches the recorded configuration. Raises if it does not.
    """
    if initialize_if_missing:
        try:
            firebase_admin.get_app()
        except ValueError:
            initialize_firebase()
    check_runtime_configuration()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """Verify the Firebase ID token and return the authenticated user.

    Declared as a regular (sync) function so FastAPI runs it in a worker
    thread: `check_revoked=True` performs a network lookup.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Not authenticated.")

    try:
        _ensure_firebase_app()
    except Exception as exc:
        # Verification cannot run at all: fail closed with an explicit 503.
        logger.error("Firebase app unavailable for token verification: %s", type(exc).__name__)
        raise _service_unavailable() from None

    # Order matters: Expired/Revoked are subclasses of InvalidIdTokenError.
    try:
        decoded = firebase_auth.verify_id_token(
            credentials.credentials,
            check_revoked=True,
            clock_skew_seconds=CLOCK_SKEW_SECONDS,
        )
    except firebase_auth.ExpiredIdTokenError:
        raise _unauthorized("Session expired. Please sign in again.") from None
    except firebase_auth.RevokedIdTokenError:
        raise _unauthorized("Session revoked. Please sign in again.") from None
    except firebase_auth.InvalidIdTokenError:
        raise _unauthorized("Invalid authentication token.") from None
    except firebase_auth.UserDisabledError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled.",
        ) from None
    except firebase_auth.UserNotFoundError:
        # check_revoked looks the account up; a deleted account's still-unexpired
        # token ends here. Must be handled before the generic FirebaseError branch.
        raise _unauthorized("Account not found. Please sign in again.") from None
    except ValueError:
        # Malformed token value (e.g. empty or wrong type).
        raise _unauthorized("Invalid authentication token.") from None
    except firebase_exceptions.FirebaseError as exc:
        # Includes CertificateFetchError and failures of the revocation lookup.
        # Infrastructure problem, not the caller's fault: never 401 here.
        logger.error("Token verification unavailable: %s", type(exc).__name__)
        raise _service_unavailable() from None
    except Exception as exc:
        # Any other failure to complete verification: fail closed, never authenticate.
        logger.error("Unexpected token verification failure: %s", type(exc).__name__)
        raise _service_unavailable() from None

    # The SDK read the emulator settings during verification: accept the identity
    # only if the configuration is still the recorded one.
    try:
        _ensure_firebase_app(initialize_if_missing=False)
    except Exception as exc:
        logger.error("Firebase configuration changed during token verification: %s", type(exc).__name__)
        raise _service_unavailable() from None

    return AuthenticatedUser(
        uid=decoded["uid"],
        email=decoded.get("email"),
        # Strict boolean check: a string "true" or any other value is NOT admin.
        is_admin=decoded.get("admin") is True,
    )


def require_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Allow only users whose verified token carries `admin: true`."""
    if not user.is_admin:
        logger.warning("Admin access denied for uid=%s", user.uid)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )
    return user


def ensure_same_user(user: AuthenticatedUser, requested_uid: Optional[str]) -> None:
    """Reject a request that names a different user's ID than the token's uid.

    Applies to administrators too: admin access to student records will be
    provided by dedicated, separately authorized admin endpoints.
    """
    if requested_uid and requested_uid != user.uid:
        logger.warning("Blocked cross-user access attempt by uid=%s", user.uid)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own records.",
        )
