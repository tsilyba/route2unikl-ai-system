# backend/tests/test_auth.py
"""
Milestone 1.5A: FastAPI authentication & authorization tests.

Run from the backend directory:
    python -m unittest discover -s tests -t . -v

Safety: Firebase token verification, Firestore and the AI orchestrator are
mocked. These tests make no network calls, load no credentials, consume no
AI provider quota, and never open ChromaDB.
"""
import contextlib
import importlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Test isolation (M3C audit A2): installed by importing the tests package, before any Firebase, Google or
# application import, also when this file is executed directly; the import fails if they cannot be installed.
from tests import isolation  # noqa: E402

isolation.require_guards(isolation.UNIT)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402

from core import auth as core_auth  # noqa: E402
from routes import assessment as assessment_routes  # noqa: E402
from routes import auth_check as auth_check_routes  # noqa: E402
from services import rag_orchestrator  # noqa: E402

STUDENT_UID = "student-uid-123"
OTHER_STUDENT_UID = "other-student-uid-456"
ADMIN_UID = "admin-uid-789"

GENERATE_URL = "/api/assessment/generate-questions"
RECOMMEND_URL = "/api/assessment/recommend"
ME_URL = "/api/auth/me"
ADMIN_VERIFY_URL = "/api/admin/verify"

COMPLETE_RECOMMEND_PAYLOAD = {
    "interests": ["Computing"],
    "grades": [{"subject": "Mathematics", "grade": "A"}],
    "assessmentScore": 80,
}

MOCK_AI_RESULT = {
    "status": "success",
    "source": "MOCK_PROVIDER_SOURCE",
    "model_used": "mock-model",
    "declared_interests": ["Computing"],
    "matched_program": {"program_id": "mock_programme", "title": "Mock Programme"},
    "total_questions": 1,
    "questions": [{"id": 1, "question": "Mock question?", "options": ["A", "B"], "correctIndex": 0}],
}
MOCK_RECOMMENDATIONS = [{"program_id": "mock_programme", "match_percentage": 90}]


def fake_verify_id_token(token, check_revoked=False, clock_skew_seconds=0, app=None):
    """Stand-in for firebase_admin.auth.verify_id_token keyed by fake token strings."""
    valid_tokens = {
        "student-token": {"uid": STUDENT_UID, "email": "student@example.test"},
        "admin-token": {"uid": ADMIN_UID, "email": "admin@example.test", "admin": True},
        "string-admin-token": {"uid": "string-claim-uid", "admin": "true"},
        "false-admin-token": {"uid": "false-claim-uid", "admin": False},
    }
    if token in valid_tokens:
        return dict(valid_tokens[token])
    if token == "expired-token":
        raise firebase_auth.ExpiredIdTokenError("Token expired", cause=None)
    if token == "revoked-token":
        raise firebase_auth.RevokedIdTokenError("Token revoked")
    if token == "disabled-token":
        raise firebase_auth.UserDisabledError("User disabled")
    if token == "cert-fetch-failure-token":
        raise firebase_auth.CertificateFetchError("Could not fetch certificates", cause=None)
    if token == "lookup-unavailable-token":
        raise firebase_exceptions.UnavailableError("Revocation lookup unavailable")
    if token == "deleted-user-token":
        # What check_revoked raises for a deleted account's still-unexpired token.
        raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")
    if token == "unexpected-verification-error-token":
        raise RuntimeError("Unexpected failure inside token verification")
    if token == "malformed-token":
        raise ValueError("Malformed token")
    raise firebase_auth.InvalidIdTokenError("Invalid token")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class AuthTestBase(unittest.TestCase):
    """Test app with the real routers; all external services mocked."""

    def setUp(self):
        app = FastAPI()
        app.include_router(assessment_routes.router, prefix="/api/assessment")
        app.include_router(auth_check_routes.router, prefix="/api")
        self.client = TestClient(app)

        self.verify_mock = self.patch("core.auth.firebase_auth.verify_id_token", side_effect=fake_verify_id_token)
        self.patch("core.auth._ensure_firebase_app")  # never load the service account
        self.ai_mock = self.patch(
            "routes.assessment.generate_rag_assessment",
            new_callable=mock.AsyncMock,
            return_value=dict(MOCK_AI_RESULT),
        )
        self.recs_mock = self.patch(
            "routes.assessment.calculate_program_recommendations",
            return_value=list(MOCK_RECOMMENDATIONS),
        )
        self.firestore_init_mock = self.patch("routes.assessment.initialize_firebase")

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def call(self, method, path, body=None, headers=None):
        if method == "post":
            return self.client.post(path, json=body, headers=headers or {})
        return self.client.get(path, headers=headers or {})

    def assert_no_protected_work_done(self):
        self.ai_mock.assert_not_awaited()
        self.recs_mock.assert_not_called()
        self.firestore_init_mock.assert_not_called()


PROTECTED_ENDPOINTS = [
    ("post", GENERATE_URL, {"interests": ["Computing"]}),
    ("post", RECOMMEND_URL, COMPLETE_RECOMMEND_PAYLOAD),
    ("get", ME_URL, None),
    ("get", ADMIN_VERIFY_URL, None),
]


class TokenValidationTests(AuthTestBase):
    """Scenarios 3 & 4: missing, invalid, expired and revoked tokens."""

    def test_missing_token_returns_401_on_every_protected_endpoint(self):
        for method, path, body in PROTECTED_ENDPOINTS:
            with self.subTest(path=path):
                response = self.call(method, path, body)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
        self.verify_mock.assert_not_called()
        self.assert_no_protected_work_done()

    def test_non_bearer_scheme_returns_401(self):
        response = self.call("post", GENERATE_URL, {"interests": []}, {"Authorization": "Basic c3R1ZGVudDpwYXNz"})
        self.assertEqual(response.status_code, 401)
        self.assert_no_protected_work_done()

    def test_rejected_tokens(self):
        cases = {
            "garbage-token": (401, "Invalid authentication token."),
            "malformed-token": (401, "Invalid authentication token."),
            "expired-token": (401, "Session expired. Please sign in again."),
            "revoked-token": (401, "Session revoked. Please sign in again."),
            "deleted-user-token": (401, "Account not found. Please sign in again."),
            "disabled-token": (403, "This account has been disabled."),
        }
        for token, (expected_status, expected_detail) in cases.items():
            for method, path, body in PROTECTED_ENDPOINTS:
                with self.subTest(token=token, path=path):
                    response = self.call(method, path, body, bearer(token))
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(response.json()["detail"], expected_detail)
        self.assert_no_protected_work_done()

    def test_deleted_account_returns_401_not_503(self):
        # Regression: UserNotFoundError is a FirebaseError and was previously mapped to 503.
        for method, path, body in PROTECTED_ENDPOINTS:
            with self.subTest(path=path):
                response = self.call(method, path, body, bearer("deleted-user-token"))
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
        self.assert_no_protected_work_done()

    def test_verification_outage_returns_503_with_machine_readable_code(self):
        expected_detail = {
            "code": core_auth.AUTH_SERVICE_UNAVAILABLE,
            "message": "Authentication service is temporarily unavailable. Please try again.",
        }
        tokens = ("cert-fetch-failure-token", "lookup-unavailable-token", "unexpected-verification-error-token")
        for token in tokens:
            for method, path, body in PROTECTED_ENDPOINTS:
                with self.subTest(token=token, path=path):
                    response = self.call(method, path, body, bearer(token))
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["detail"], expected_detail)
        self.assertEqual(core_auth.AUTH_SERVICE_UNAVAILABLE, "AUTH_SERVICE_UNAVAILABLE")  # frontend contract
        self.assert_no_protected_work_done()

    def test_firebase_app_initialization_failure_returns_503_with_code(self):
        self.patch("core.auth._ensure_firebase_app", side_effect=FileNotFoundError("service account missing"))
        response = self.call("post", GENERATE_URL, {"interests": []}, bearer("student-token"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], core_auth.AUTH_SERVICE_UNAVAILABLE)
        self.verify_mock.assert_not_called()
        self.assert_no_protected_work_done()

    def test_tokens_are_verified_with_revocation_check(self):
        response = self.call("get", ME_URL, headers=bearer("student-token"))
        self.assertEqual(response.status_code, 200)
        self.verify_mock.assert_called_once_with(
            "student-token",
            check_revoked=True,
            clock_skew_seconds=core_auth.CLOCK_SKEW_SECONDS,
        )


class StudentDataAuthorizationTests(AuthTestBase):
    """Scenarios 1, 2 & 5: own data allowed, other students' data rejected."""

    def test_student_generates_questions_and_ai_fields_are_preserved(self):
        response = self.call("post", GENERATE_URL, {"userId": STUDENT_UID, "interests": ["Computing"]}, bearer("student-token"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), MOCK_AI_RESULT)  # incl. `source` and `model_used`, unchanged
        self.ai_mock.assert_awaited_once_with(["Computing"])

    def test_student_generates_questions_without_user_id(self):
        response = self.call("post", GENERATE_URL, {"interests": ["Computing"]}, bearer("student-token"))
        self.assertEqual(response.status_code, 200)

    def test_generate_questions_for_another_user_returns_403(self):
        response = self.call("post", GENERATE_URL, {"userId": OTHER_STUDENT_UID, "interests": []}, bearer("student-token"))
        self.assertEqual(response.status_code, 403)
        self.ai_mock.assert_not_awaited()

    def test_student_gets_own_recommendations(self):
        payload = dict(COMPLETE_RECOMMEND_PAYLOAD, userId=STUDENT_UID)
        response = self.call("post", RECOMMEND_URL, payload, bearer("student-token"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["userId"], STUDENT_UID)
        self.assertEqual(body["recommendations"], MOCK_RECOMMENDATIONS)
        self.recs_mock.assert_called_once_with(
            interests=["Computing"],
            grades=[{"subject": "Mathematics", "grade": "A"}],
            assessment_score=80.0,
        )
        self.firestore_init_mock.assert_not_called()

    def test_student_cannot_read_another_students_records(self):
        # Empty fields previously triggered a Firestore read of the supplied userId.
        response = self.call("post", RECOMMEND_URL, {"userId": OTHER_STUDENT_UID}, bearer("student-token"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "You can only access your own records.")
        self.assert_no_protected_work_done()

    def test_admin_also_cannot_read_student_records_through_student_endpoint(self):
        response = self.call("post", RECOMMEND_URL, {"userId": OTHER_STUDENT_UID}, bearer("admin-token"))
        self.assertEqual(response.status_code, 403)
        self.assert_no_protected_work_done()

    def test_firestore_auto_fetch_reads_only_the_token_uid(self):
        fake_db = mock.MagicMock()
        fake_db.collection.return_value.document.return_value.get.return_value = mock.MagicMock(exists=False)
        self.firestore_init_mock.return_value = fake_db

        response = self.call("post", RECOMMEND_URL, {}, bearer("student-token"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["userId"], STUDENT_UID)
        collections = [c.args[0] for c in fake_db.collection.call_args_list]
        self.assertEqual(collections, ["users", "results", "ai_assessments"])
        documents = [c.args[0] for c in fake_db.collection.return_value.document.call_args_list]
        self.assertEqual(documents, [STUDENT_UID] * 3)


class AdminAuthorizationTests(AuthTestBase):
    """Scenarios 6 & 7: `require_admin` and custom-claim recognition."""

    def test_student_is_denied_admin_endpoint(self):
        response = self.call("get", ADMIN_VERIFY_URL, headers=bearer("student-token"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Administrator privileges required.")

    def test_admin_claim_is_recognized(self):
        response = self.call("get", ADMIN_VERIFY_URL, headers=bearer("admin-token"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "uid": ADMIN_UID, "is_admin": True})

    def test_non_boolean_or_false_admin_claims_are_not_admin(self):
        for token in ("string-admin-token", "false-admin-token"):
            with self.subTest(token=token):
                self.assertEqual(self.call("get", ADMIN_VERIFY_URL, headers=bearer(token)).status_code, 403)
                self.assertIs(self.call("get", ME_URL, headers=bearer(token)).json()["is_admin"], False)

    def test_auth_me_reports_only_the_callers_identity(self):
        self.assertEqual(self.call("get", ME_URL, headers=bearer("student-token")).json(), {"uid": STUDENT_UID, "is_admin": False})
        self.assertEqual(self.call("get", ME_URL, headers=bearer("admin-token")).json(), {"uid": ADMIN_UID, "is_admin": True})


class ErrorDisclosureTests(AuthTestBase):
    """Internal exception details must not reach clients or logs."""

    SECRET = "SECRET-INTERNAL-DETAIL-api_key=abc123"

    def test_ai_failure_returns_generic_500(self):
        self.ai_mock.side_effect = RuntimeError(self.SECRET)
        with self.assertLogs("assessment_route", level="ERROR") as logs:
            response = self.call("post", GENERATE_URL, {"interests": []}, bearer("student-token"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Failed to generate assessment. Please try again later.")
        self.assertNotIn(self.SECRET, response.text)
        self.assertNotIn(self.SECRET, "\n".join(logs.output))

    def test_recommendation_failure_returns_generic_500(self):
        self.recs_mock.side_effect = RuntimeError(self.SECRET)
        with self.assertLogs("assessment_route", level="ERROR") as logs:
            response = self.call("post", RECOMMEND_URL, COMPLETE_RECOMMEND_PAYLOAD, bearer("student-token"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Failed to generate recommendations. Please try again later.")
        self.assertNotIn(self.SECRET, response.text)
        self.assertNotIn(self.SECRET, "\n".join(logs.output))


class StaticFallbackPreservedTests(unittest.TestCase):
    """Authenticated request + every AI provider failing -> the backend's existing
    static fallback questions are still returned.

    Runs the REAL orchestrator (`generate_rag_assessment`, prompt builder and
    static fallback). Only the ChromaDB lookup and the three provider calls are
    mocked, so no AI request is made and ChromaDB is never opened.
    """

    PROGRAM_CONTEXT = {
        "program_id": "unikl_miit_foundation_computer",
        "title": "Foundation in Computer Technology",
        "campuses": "UniKL MIIT",
        "pathway_category": "Computing & Digital Technology",
        "specialisation": "Information Technology",
        "document_text": "Foundation in Computer Technology (test context).",
        "distance": 0.0,
    }

    def setUp(self):
        app = FastAPI()
        app.include_router(assessment_routes.router, prefix="/api/assessment")
        self.client = TestClient(app)

        self.patch("core.auth.firebase_auth.verify_id_token", side_effect=fake_verify_id_token)
        self.patch("core.auth._ensure_firebase_app")
        self.patch("services.rag_orchestrator.retrieve_program_context", return_value=dict(self.PROGRAM_CONTEXT))
        self.provider_mocks = [
            self.patch(f"services.rag_orchestrator.{name}", new_callable=mock.AsyncMock, return_value=None)
            for name in ("call_openai_cloud", "call_gemma_cloud", "call_ollama_cloud")
        ]
        # Mark every provider as configured so each one is attempted (and fails).
        for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_API_KEY"):
            self.patch(f"services.rag_orchestrator.{key}", new="test-placeholder-not-a-real-key")

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def test_route_uses_the_real_orchestrator(self):
        self.assertIs(assessment_routes.generate_rag_assessment, rag_orchestrator.generate_rag_assessment)

    def test_static_fallback_returned_when_all_ai_providers_fail(self):
        # The orchestrator print()s an emoji notice on this path; capture stdout so the
        # test does not depend on the console encoding (pre-existing behaviour, untouched).
        with contextlib.redirect_stdout(io.StringIO()) as console:
            response = self.client.post(GENERATE_URL, json={"interests": ["Computing"]}, headers=bearer("student-token"))
        self.assertIn("static fallback", console.getvalue())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "RAG_CONTEXT_ENHANCED_FALLBACK")
        self.assertEqual(body["model_used"], "static_fallback")
        self.assertEqual(body["total_questions"], len(body["questions"]))
        self.assertEqual(len(body["questions"]), 10)
        for provider in self.provider_mocks:
            provider.assert_awaited_once()

    def test_authentication_is_checked_before_any_ai_provider(self):
        response = self.client.post(GENERATE_URL, json={"interests": ["Computing"]})
        self.assertEqual(response.status_code, 401)
        for provider in self.provider_mocks:
            provider.assert_not_awaited()


class MainAppWiringTests(unittest.TestCase):
    """The real `main.app`: routes are protected and CORS allows the Bearer header."""

    @classmethod
    def setUpClass(cls):
        # Import main without initializing Firebase (no credentials are loaded).
        sys.modules.pop("main", None)
        with mock.patch("core.firebase.initialize_firebase", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            main = importlib.import_module("main")
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("main", None)

    def test_routes_require_authentication(self):
        for method, path, body in PROTECTED_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.post(path, json=body) if method == "post" else self.client.get(path)
                self.assertEqual(response.status_code, 401)

    def test_public_health_endpoint_still_open(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_cors_preflight_allows_authorization_header(self):
        response = self.client.options(
            RECOMMEND_URL,
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")
        self.assertIn("authorization", response.headers.get("access-control-allow-headers", "").lower())


if __name__ == "__main__":
    unittest.main()
