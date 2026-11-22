# backend/routes/auth_check.py
"""
Read-only endpoints for verifying authentication and admin authorization.
They expose no student data and perform no writes.
"""
from fastapi import APIRouter, Depends

from core.auth import AuthenticatedUser, get_current_user, require_admin

router = APIRouter()


@router.get("/auth/me")
def read_current_user(user: AuthenticatedUser = Depends(get_current_user)):
    """Return the caller's own uid and whether their token carries `admin: true`."""
    return {"uid": user.uid, "is_admin": user.is_admin}


@router.get("/admin/verify")
def verify_admin_access(user: AuthenticatedUser = Depends(require_admin)):
    """200 only for administrators; 403 for any other authenticated user."""
    return {"status": "ok", "uid": user.uid, "is_admin": True}
