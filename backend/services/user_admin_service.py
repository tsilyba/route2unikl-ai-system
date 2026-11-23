# backend/services/user_admin_service.py
"""
Read-only account information for the Admin "Manage Users" module (Milestone M3A).

Data is read server-side with the Firebase Admin SDK (which bypasses Firestore
Security Rules), using the shared initialisation in core/firebase.py:
  - Firebase Authentication accounts (list_users / get_user);
  - Firestore users/{uid} profiles, read with field masks;
  - metadata of results/{uid} and ai_assessments/{uid}, for one account only (detail).

Privacy: every response is built from explicit allow-lists. Raw SDK user objects,
password hashes and salts, tokens, raw custom claims, provider identifiers, grades,
assessment answers and scores are never returned. Nothing in this module writes to
Firebase Authentication or Firestore.

Listing limits: Auth accounts are read in pages of AUTH_PAGE_SIZE up to ACCOUNT_LIMIT.
If more accounts exist, the response reports `complete: False` instead of silently
truncating. Enumeration is Auth-driven: Auth accounts WITHOUT a Firestore profile are
detected, but Firestore profiles WITHOUT an Auth account are not (reconciling such
orphaned profiles is future work). Each listing request reads one Firestore document
per scanned Auth account.
"""
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from firebase_admin import auth as firebase_auth

from core.firebase import initialize_firebase

logger = logging.getLogger("user_admin_service")

ACCOUNT_LIMIT = 2000
AUTH_PAGE_SIZE = 1000
FIRESTORE_BATCH_SIZE = 200
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_PAGE = 10000
MAX_SEARCH_LENGTH = 100
UID_PATTERN = r"^[A-Za-z0-9_-]{1,128}$"
_UID_RE = re.compile(UID_PATTERN)

STUDENT_TYPES = ("spm_leaver", "form_4_5")
LEGACY_ROLES = ("upper_secondary",)
STUDENT_TYPE_FILTERS = ("spm_leaver", "form_4_5", "legacy", "unknown")
STATUS_FILTERS = ("active", "disabled")
PROFILE_FILTERS = ("present", "missing")

# Firestore field masks: only these fields are fetched.
LIST_PROFILE_FIELDS = ["name", "role", "currentStep"]
DETAIL_PROFILE_FIELDS = [
    "name", "role", "createdAt", "updatedAt", "currentStep", "chosenInterests",
    "hasCompletedProfile", "hasUploadedResults", "hasViewedRecommendations",
    "hasCompletedPreparationPlan",
]
# `results` / `answers` are fetched only to count entries; their contents are never returned.
RESULTS_SUMMARY_FIELDS = ["recordType", "status", "verificationMethod", "updatedAt", "results"]
ASSESSMENT_SUMMARY_FIELDS = ["completedAt", "isDemoMode", "answers"]

PROGRESS_FLAGS = {
    "has_completed_profile": "hasCompletedProfile",
    "has_uploaded_results": "hasUploadedResults",
    "has_viewed_recommendations": "hasViewedRecommendations",
    "has_completed_preparation_plan": "hasCompletedPreparationPlan",
}
KNOWN_PROVIDERS = {"password", "google.com", "phone", "anonymous"}


class UserServiceUnavailable(Exception):
    """Firebase Authentication or Firestore could not be reached or failed."""


class UserNotFound(Exception):
    """No Firebase Authentication account exists for the requested uid."""


def _get_db():
    """Firestore client from the shared Admin SDK initialisation."""
    return initialize_firebase()


# ----------------------------------------------------------------- value helpers

def _iso_from_millis(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _iso_from_datetime(value: Any) -> Optional[str]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean_text(value: Any, max_length: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:max_length] if text else None


def _clean_step(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 5 else None


def _clean_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _clean_count(value: Any) -> Optional[int]:
    return len(value) if isinstance(value, list) else None


def _clean_interests(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clean_text(item, 100) for item in value[:2]]
    return [item for item in cleaned if item]


def student_type_for(profile: Optional[Dict[str, Any]]) -> Optional[str]:
    """Student type from the profile's `role` field (display only, never authorization)."""
    if profile is None:
        return None
    role = profile.get("role")
    if role in STUDENT_TYPES:
        return role
    if role in LEGACY_ROLES:
        return "legacy"
    return "unknown"


def is_admin_account(account: Any) -> bool:
    """Admin status comes ONLY from the Firebase custom claim `admin: true`."""
    claims = getattr(account, "custom_claims", None)
    return isinstance(claims, dict) and claims.get("admin") is True


def _created_millis(account: Any) -> int:
    value = getattr(getattr(account, "user_metadata", None), "creation_timestamp", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _providers(account: Any) -> List[str]:
    providers = []
    for entry in getattr(account, "provider_data", None) or []:
        provider_id = getattr(entry, "provider_id", None)
        if provider_id in KNOWN_PROVIDERS and provider_id not in providers:
            providers.append(provider_id)
    return providers


def _account_fields(account: Any) -> Dict[str, Any]:
    metadata = getattr(account, "user_metadata", None)
    return {
        "uid": account.uid,
        "email": _clean_text(getattr(account, "email", None), 254),
        "is_admin": is_admin_account(account),
        "disabled": getattr(account, "disabled", False) is True,
        "email_verified": getattr(account, "email_verified", False) is True,
        "created_at": _iso_from_millis(getattr(metadata, "creation_timestamp", None)),
        "last_sign_in_at": _iso_from_millis(getattr(metadata, "last_sign_in_timestamp", None)),
    }


def _list_item(account: Any, profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    item = _account_fields(account)
    item.update({
        "name": _clean_text(profile.get("name"), 100) if profile is not None else None,
        "student_type": student_type_for(profile),
        "profile_status": "present" if profile is not None else "missing",
        "current_step": _clean_step(profile.get("currentStep")) if profile is not None else None,
    })
    return item


def normalise_search(search: Optional[str]) -> Optional[str]:
    if not isinstance(search, str):
        return None
    text = " ".join(search.split())[:MAX_SEARCH_LENGTH]
    return text.casefold() or None


def _matches(item: Dict[str, Any], needle: Optional[str], student_type: Optional[str],
             status: Optional[str], profile: Optional[str]) -> bool:
    if needle and not any(needle in (text or "").casefold() for text in (item["email"], item["name"])):
        return False
    if student_type and item["student_type"] != student_type:
        return False
    if status == "active" and item["disabled"]:
        return False
    if status == "disabled" and not item["disabled"]:
        return False
    if profile and item["profile_status"] != profile:
        return False
    return True


# ------------------------------------------------------------------- data access

def _fetch_auth_accounts() -> Tuple[List[Any], bool]:
    """Reads Auth accounts page by page. Returns (accounts, complete)."""
    accounts: List[Any] = []
    page = firebase_auth.list_users(max_results=AUTH_PAGE_SIZE)
    while page is not None:
        for account in page.users:
            if len(accounts) >= ACCOUNT_LIMIT:
                return accounts, False
            accounts.append(account)
        page = page.get_next_page()
    return accounts, True


def _fetch_profiles(db: Any, uids: List[str], field_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """Reads users/{uid} for the given uids in batches, with a field mask."""
    profiles: Dict[str, Dict[str, Any]] = {}
    collection = db.collection("users")
    for start in range(0, len(uids), FIRESTORE_BATCH_SIZE):
        refs = [collection.document(uid) for uid in uids[start:start + FIRESTORE_BATCH_SIZE]]
        for snapshot in db.get_all(refs, field_paths=field_paths):
            if snapshot.exists:
                profiles[snapshot.id] = snapshot.to_dict() or {}
    return profiles


def _results_summary(snapshot: Any) -> Dict[str, Any]:
    if not snapshot.exists:
        return {"exists": False}
    data = snapshot.to_dict() or {}
    return {
        "exists": True,
        "record_type": _clean_text(data.get("recordType"), 40),
        "status": _clean_text(data.get("status"), 40),
        "verification_method": _clean_text(data.get("verificationMethod"), 40),
        "subject_count": _clean_count(data.get("results")),
        "updated_at": _iso_from_datetime(data.get("updatedAt")),
    }


def _assessment_summary(snapshot: Any) -> Dict[str, Any]:
    if not snapshot.exists:
        return {"exists": False}
    data = snapshot.to_dict() or {}
    return {
        "exists": True,
        "question_count": _clean_count(data.get("answers")),
        "completed_at": _iso_from_datetime(data.get("completedAt")),
        "is_demo_mode": _clean_bool(data.get("isDemoMode")),
    }


# ----------------------------------------------------------------- public API

def list_users(*, search: Optional[str] = None, student_type: Optional[str] = None,
               status: Optional[str] = None, profile: Optional[str] = None,
               page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> Dict[str, Any]:
    """Paged, filtered list of accounts, newest registration first (ties by uid)."""
    if student_type is not None and student_type not in STUDENT_TYPE_FILTERS:
        raise ValueError("Unsupported student type filter")
    if status is not None and status not in STATUS_FILTERS:
        raise ValueError("Unsupported status filter")
    if profile is not None and profile not in PROFILE_FILTERS:
        raise ValueError("Unsupported profile filter")
    if not 1 <= page <= MAX_PAGE or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("Unsupported page or page size")

    try:
        db = _get_db()
        accounts, complete = _fetch_auth_accounts()
        profiles = _fetch_profiles(db, [account.uid for account in accounts], LIST_PROFILE_FIELDS)
    except Exception as exc:
        # Log only the exception type: SDK messages can contain identifiers.
        logger.error("Admin user listing unavailable: %s", type(exc).__name__)
        raise UserServiceUnavailable() from None

    needle = normalise_search(search)
    rows = []
    for account in accounts:
        item = _list_item(account, profiles.get(account.uid))
        if _matches(item, needle, student_type, status, profile):
            rows.append((_created_millis(account), item))
    rows.sort(key=lambda row: (-row[0], row[1]["uid"]))

    total = len(rows)
    start = (page - 1) * page_size
    return {
        "items": [item for _, item in rows[start:start + page_size]],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, math.ceil(total / page_size)),
        "complete": complete,
        "account_limit": ACCOUNT_LIMIT,
        "scanned_accounts": len(accounts),
    }


def get_user_detail(uid: str) -> Dict[str, Any]:
    """One account with its profile and a metadata-only summary of its records."""
    if not isinstance(uid, str) or not _UID_RE.match(uid):
        raise UserNotFound()

    try:
        db = _get_db()
        account = firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        raise UserNotFound() from None
    except Exception as exc:
        logger.error("Admin user lookup unavailable: %s", type(exc).__name__)
        raise UserServiceUnavailable() from None

    try:
        profile_snapshot = db.collection("users").document(uid).get(field_paths=DETAIL_PROFILE_FIELDS)
        results_snapshot = db.collection("results").document(uid).get(field_paths=RESULTS_SUMMARY_FIELDS)
        assessment_snapshot = db.collection("ai_assessments").document(uid).get(
            field_paths=ASSESSMENT_SUMMARY_FIELDS
        )
    except Exception as exc:
        logger.error("Admin user records unavailable: %s", type(exc).__name__)
        raise UserServiceUnavailable() from None

    profile = (profile_snapshot.to_dict() or {}) if profile_snapshot.exists else None

    detail = _account_fields(account)
    detail["sign_in_providers"] = _providers(account)
    detail["profile"] = None if profile is None else {
        "name": _clean_text(profile.get("name"), 100),
        "student_type": student_type_for(profile),
        "registered_at": _iso_from_datetime(profile.get("createdAt")),
        "updated_at": _iso_from_datetime(profile.get("updatedAt")),
        "current_step": _clean_step(profile.get("currentStep")),
        "chosen_interests": _clean_interests(profile.get("chosenInterests")),
        "progress": {key: _clean_bool(profile.get(field)) for key, field in PROGRESS_FLAGS.items()},
    }
    detail["records"] = {
        "results": _results_summary(results_snapshot),
        "ai_assessment": _assessment_summary(assessment_snapshot),
    }
    return detail
