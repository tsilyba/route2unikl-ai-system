# backend/routes/admin_users.py
"""
Admin "Manage Users" endpoints — READ ONLY (Milestone M3A).

  GET /api/admin/users          paged list of accounts (search, filters, pagination)
  GET /api/admin/users/{uid}    one account with a metadata-only records summary

Both require a verified Firebase ID token carrying `admin: true` (require_admin),
which runs before any Firebase Admin SDK call. Responses are validated against the
response models below, so only allow-listed fields are ever returned even if the
service layer returned more. Nothing here changes accounts, profiles, claims or
sessions; account actions (M3B) are deferred.
"""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from core.auth import AuthenticatedUser, require_admin
from services import user_admin_service as users_service

router = APIRouter()

USER_SERVICE_UNAVAILABLE = "USER_SERVICE_UNAVAILABLE"
USER_NOT_FOUND = "USER_NOT_FOUND"

StudentType = Literal["spm_leaver", "form_4_5", "legacy", "unknown"]


class UserListItem(BaseModel):
    uid: str
    email: Optional[str]
    name: Optional[str]
    student_type: Optional[StudentType]
    is_admin: bool
    disabled: bool
    email_verified: bool
    created_at: Optional[str]
    last_sign_in_at: Optional[str]
    profile_status: Literal["present", "missing"]
    current_step: Optional[int]


class UserListResponse(BaseModel):
    items: List[UserListItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    complete: bool
    account_limit: int
    scanned_accounts: int


class UserProgress(BaseModel):
    has_completed_profile: Optional[bool]
    has_uploaded_results: Optional[bool]
    has_viewed_recommendations: Optional[bool]
    has_completed_preparation_plan: Optional[bool]


class UserProfileSummary(BaseModel):
    name: Optional[str]
    student_type: StudentType
    registered_at: Optional[str]
    updated_at: Optional[str]
    current_step: Optional[int]
    chosen_interests: List[str]
    progress: UserProgress


class ResultsSummary(BaseModel):
    exists: bool
    record_type: Optional[str] = None
    status: Optional[str] = None
    verification_method: Optional[str] = None
    subject_count: Optional[int] = None
    updated_at: Optional[str] = None


class AssessmentSummary(BaseModel):
    exists: bool
    question_count: Optional[int] = None
    completed_at: Optional[str] = None
    is_demo_mode: Optional[bool] = None


class RecordsSummary(BaseModel):
    results: ResultsSummary
    ai_assessment: AssessmentSummary


class UserDetailResponse(BaseModel):
    uid: str
    email: Optional[str]
    is_admin: bool
    disabled: bool
    email_verified: bool
    created_at: Optional[str]
    last_sign_in_at: Optional[str]
    sign_in_providers: List[str]
    profile: Optional[UserProfileSummary]
    records: RecordsSummary


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _service_unavailable() -> HTTPException:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        USER_SERVICE_UNAVAILABLE,
        "User information is temporarily unavailable. Please try again.",
    )


@router.get("", response_model=UserListResponse)
def list_users(
    search: Optional[str] = Query(default=None, max_length=users_service.MAX_SEARCH_LENGTH),
    student_type: Optional[StudentType] = Query(default=None),
    account_status: Optional[Literal["active", "disabled"]] = Query(default=None, alias="status"),
    profile: Optional[Literal["present", "missing"]] = Query(default=None),
    page: int = Query(default=1, ge=1, le=users_service.MAX_PAGE),
    page_size: int = Query(default=users_service.DEFAULT_PAGE_SIZE, ge=1, le=users_service.MAX_PAGE_SIZE),
    _admin: AuthenticatedUser = Depends(require_admin),
):
    """Accounts, newest registration first. Read-only."""
    try:
        return users_service.list_users(
            search=search,
            student_type=student_type,
            status=account_status,
            profile=profile,
            page=page,
            page_size=page_size,
        )
    except users_service.UserServiceUnavailable:
        raise _service_unavailable() from None


@router.get("/{uid}", response_model=UserDetailResponse)
def get_user(
    uid: str = Path(..., min_length=1, max_length=128, pattern=users_service.UID_PATTERN),
    _admin: AuthenticatedUser = Depends(require_admin),
):
    """One account with a metadata-only summary of its academic records. Read-only."""
    try:
        return users_service.get_user_detail(uid)
    except users_service.UserNotFound:
        raise _error(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND, "No account exists with this ID.") from None
    except users_service.UserServiceUnavailable:
        raise _service_unavailable() from None
