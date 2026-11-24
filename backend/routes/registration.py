# backend/routes/registration.py
"""
Trusted student registration endpoint (M3B-1B-P1-B2A): LOCAL EMULATOR TESTING ONLY.

This router is deliberately NOT mounted by main.py. Even when mounted, it
answers 404 unless the backend runs in Firebase emulator mode
(ROUTE2UNIKL_FIREBASE_MODE=emulator, see core.firebase), and in any other mode
it never touches Firebase. Before it can serve real users it needs HTTPS, rate
limiting and abuse protection (docs/PROJECT_STATUS.md, section 8 I).

The request body is read and validated here rather than by FastAPI, because
FastAPI's default 422 response repeats the submitted input, which would include
the password. Responses carry a code and invalid field names only; a successful
response carries no uid, email or password.
"""
import json
from typing import List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError
from starlette.concurrency import run_in_threadpool

from core import firebase as core_firebase
from services import registration_service as registration

router = APIRouter()

MAX_BODY_BYTES = 4096
REQUEST_FIELDS = ("name", "email", "password", "role")
STATUS_BY_CODE = {
    registration.INVALID_REGISTRATION: 422,
    registration.EMAIL_IN_USE: 409,
    registration.REGISTRATION_UNAVAILABLE: 503,
    registration.REGISTRATION_INCOMPLETE: 503,
}


class RegistrationRequest(BaseModel):
    """Exactly these four string fields; anything else (uid, claims, flags) is refused."""
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    email: str
    password: SecretStr
    role: str


def _error(status_code: int, code: str, fields: List[str] = ()) -> JSONResponse:
    content = {"code": code}
    if fields:
        content["fields"] = list(fields)
    return JSONResponse(status_code=status_code, content=content)


def _invalid_fields(exc: ValidationError) -> List[str]:
    """Field names only (never values); unexpected fields are reported generically."""
    names = set()
    for error in exc.errors():
        location = error.get("loc") or ()
        field = location[0] if location else None
        names.add(field if field in REQUEST_FIELDS and error.get("type") != "extra_forbidden" else "unexpected_field")
    return sorted(names)


def _registration_enabled() -> bool:
    """Only in Firebase emulator mode; decided from the environment without touching Firebase."""
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


@router.post("/register", status_code=201)
async def register_student(request: Request):
    if not _registration_enabled():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    declared_length = request.headers.get("content-length")
    if declared_length is not None and (not declared_length.isdigit() or int(declared_length) > MAX_BODY_BYTES):
        return _error(413, registration.INVALID_REGISTRATION)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return _error(413, registration.INVALID_REGISTRATION)
    try:
        payload = json.loads(body)
    except ValueError:
        return _error(422, registration.INVALID_REGISTRATION)
    if not isinstance(payload, dict):
        return _error(422, registration.INVALID_REGISTRATION)
    try:
        data = RegistrationRequest.model_validate(payload)
    except ValidationError as exc:
        return _error(422, registration.INVALID_REGISTRATION, _invalid_fields(exc))

    if not await run_in_threadpool(_emulator_ready):
        return _error(503, registration.REGISTRATION_UNAVAILABLE)
    try:
        await run_in_threadpool(registration.register_student, name=data.name, email=data.email,
                                password=data.password.get_secret_value(), role=data.role)
    except registration.RegistrationError as exc:
        return _error(STATUS_BY_CODE[exc.code], exc.code, list(exc.fields))
    return JSONResponse(status_code=201, content={"status": "registered"})
