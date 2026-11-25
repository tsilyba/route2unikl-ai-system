# backend/services/registration_service.py
"""
Trusted, backend-mediated student registration (M3B-1B-P1-B2A).

LOCAL EMULATOR TESTING ONLY: main.py mounts the route in routes/registration.py
only in Firebase emulator mode, and the route answers 404 outside that mode.

One server operation creates, in this order:
  1. the Firebase Authentication account (Admin SDK create_user). The uid comes
     from Firebase, never from the caller, and the email must not be in use:
     an existing account is refused before anything is written, so it can
     never be modified or activated here;
  2. the student profile users/{uid} with exactly the fields firestore.rules
     requires for registration (name, email, role, createdAt), created only if
     absent;
  3. the account-access record, through account_access_service, which must
     report a newly created 'active' record whose Auth account was still
     enabled afterwards (`activated`).
The account is known to be new because this operation created it: steps 2 and
3 use the uid that create_user returned. The access record is written last, so
the Firestore guard opens only once the account and profile exist.

If a step fails after the account was created, that account is disabled (never
deleted) and REGISTRATION_INCOMPLETE is reported: it stays restricted until an
administrator completes or removes it. Success is reported only after step 3 is
confirmed.

Passwords go straight to Firebase Authentication, which stores them; they are
never stored, logged, returned or put into an exception here. Logs contain the
uid, the step and codes or exception types only: never the password, email
address or name.
"""
import logging
import re
import unicodedata
from typing import Optional, Sequence, Tuple

from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exceptions
from google.cloud.firestore import SERVER_TIMESTAMP

from core.firebase import initialize_firebase
from services import account_access_service
from services.user_admin_service import STUDENT_TYPES

logger = logging.getLogger("registration_service")

PROFILE_COLLECTION = "users"
NAME_MAX_LENGTH = 100          # firestore.rules: isNonEmptyString(name, 100)
EMAIL_MAX_LENGTH = 254         # firestore.rules: isNonEmptyString(email, 254)
PASSWORD_MIN_LENGTH = 6        # Firebase Authentication's own minimum
PASSWORD_MAX_LENGTH = 128
WRITE_TIMEOUT_SECONDS = 10
_EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s.]+(?:\.[^@\s.]+)+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Error codes (RegistrationError.code)
INVALID_REGISTRATION = "INVALID_REGISTRATION"          # nothing was created
EMAIL_IN_USE = "EMAIL_IN_USE"                          # nothing was created or changed
REGISTRATION_UNAVAILABLE = "REGISTRATION_UNAVAILABLE"  # no account confirmed as created
REGISTRATION_INCOMPLETE = "REGISTRATION_INCOMPLETE"    # account created but not completed; disabled


class RegistrationError(Exception):
    """A controlled registration failure. The message is the code only."""

    def __init__(self, code: str, *, fields: Sequence[str] = (), uid: Optional[str] = None,
                 restricted: Optional[bool] = None):
        super().__init__(code)
        self.code = code
        self.fields = tuple(fields)   # names of invalid input fields, never their values
        self.uid = uid                # REGISTRATION_INCOMPLETE only; for server-side recovery
        self.restricted = restricted  # REGISTRATION_INCOMPLETE only: whether the account was disabled


def _has_control_character(value: str) -> bool:
    """True if any character is in Unicode category Cc (U+0000-U+001F and U+007F-U+009F: TAB, line feed,
    carriage return, DEL and the other control characters), which cannot be seen in a password field."""
    return any(unicodedata.category(character) == "Cc" for character in value)


def validate_registration(name, email, password, role) -> Tuple[str, str]:
    """Return the cleaned (name, email), or raise INVALID_REGISTRATION naming the invalid fields.

    The password is checked as received and never trimmed or changed: 6 to 128 characters (code points)
    and no control characters. Only the field name is reported, never the password or its characters.
    """
    invalid = []
    clean_name = name.strip() if isinstance(name, str) else ""
    if not clean_name or len(clean_name) > NAME_MAX_LENGTH or _CONTROL_RE.search(clean_name):
        invalid.append("name")
    clean_email = email.strip() if isinstance(email, str) else ""
    if len(clean_email) > EMAIL_MAX_LENGTH or not _EMAIL_RE.fullmatch(clean_email):
        invalid.append("email")
    if (not isinstance(password, str) or not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
            or _has_control_character(password)):
        invalid.append("password")
    if not isinstance(role, str) or role not in STUDENT_TYPES:
        invalid.append("role")
    if invalid:
        raise RegistrationError(INVALID_REGISTRATION, fields=invalid)
    return clean_name, clean_email


def _create_profile(db, uid: str, name: str, email: str, role: str) -> None:
    db.collection(PROFILE_COLLECTION).document(uid).create(
        {"name": name, "email": email, "role": role, "createdAt": SERVER_TIMESTAMP},
        retry=None, timeout=WRITE_TIMEOUT_SECONDS)


def _restrict(uid: str) -> bool:
    """Disable an account this operation created (never deletes it)."""
    try:
        firebase_auth.update_user(uid, disabled=True)
        return True
    except Exception as exc:
        logger.error("Registration: could not disable the incomplete account (uid=%s): %s", uid, type(exc).__name__)
        return False


def _incomplete(uid: str, step: str, detail: str) -> RegistrationError:
    restricted = _restrict(uid)
    logger.error("Registration incomplete (uid=%s, step=%s, detail=%s, account_disabled=%s)",
                 uid, step, detail, restricted)
    return RegistrationError(REGISTRATION_INCOMPLETE, uid=uid, restricted=restricted)


def register_student(*, name, email, password, role) -> str:
    """Create a student account, profile and active access record; return the new uid.

    Raises RegistrationError: INVALID_REGISTRATION, EMAIL_IN_USE, REGISTRATION_UNAVAILABLE
    (nothing confirmed as created) or REGISTRATION_INCOMPLETE (account created and disabled).
    """
    clean_name, clean_email = validate_registration(name, email, password, role)
    try:
        db = initialize_firebase()
    except Exception as exc:
        logger.error("Registration: Firebase unavailable: %s", type(exc).__name__)
        raise RegistrationError(REGISTRATION_UNAVAILABLE) from None

    # 1. The Firebase Authentication account. Its uid is chosen by Firebase.
    try:
        user = firebase_auth.create_user(email=clean_email, password=password, email_verified=False, disabled=False)
    except firebase_auth.EmailAlreadyExistsError:
        logger.info("Registration refused: email already in use")
        raise RegistrationError(EMAIL_IN_USE) from None
    except (ValueError, firebase_exceptions.InvalidArgumentError) as exc:
        logger.info("Registration refused by Firebase Authentication: %s", type(exc).__name__)
        raise RegistrationError(INVALID_REGISTRATION) from None
    except Exception as exc:
        # The account may or may not exist; without its uid nothing can be restricted.
        logger.error("Registration: account creation not confirmed: %s", type(exc).__name__)
        raise RegistrationError(REGISTRATION_UNAVAILABLE) from None
    uid = user.uid

    # 2. The student profile, with the email exactly as Firebase Authentication stored it.
    try:
        _create_profile(db, uid, clean_name, user.email, role)
    except Exception as exc:
        raise _incomplete(uid, "profile", type(exc).__name__) from None

    # 3. The account-access record: last, so the Firestore guard opens only for a complete account.
    try:
        result = account_access_service.provision_access_record(uid)
    except account_access_service.AccountAccessError as exc:
        raise _incomplete(uid, "access_record", exc.code) from None
    if not result.activated:
        detail = f"created={result.created};status={result.lookup.status};issues={','.join(result.issues) or 'none'}"
        raise _incomplete(uid, "access_record", detail) from None

    logger.info("Student registered (uid=%s)", uid)
    return uid
