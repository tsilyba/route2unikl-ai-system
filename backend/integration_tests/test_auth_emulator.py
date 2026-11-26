# backend/integration_tests/test_auth_emulator.py
"""
M3B-1B-P1-A: backend authentication against the LOCAL Firebase Authentication
and Firestore emulators (project demo-route2unikl).

Run from the backend directory; the Firebase CLI starts both emulators, runs the
tests and stops the emulators (Windows path to the venv's Python shown):
    firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\\Scripts\\python.exe -m unittest discover -s integration_tests -t . -v"

This module is not part of the default backend suite (tests/). It refuses to
load unless both emulator hosts are loopback addresses and the project is a
demo- project. Emulator mode is switched on only inside this process. Every
account is created in the Auth emulator, and both emulators are wiped before
and after the run. No service-account key, real account or production project
is used, and the tests assert this. The runtime configuration check is also
exercised: emulator settings changed after initialization, or during token
verification, must never authenticate anyone.
"""
import base64
import json
import os
import sys
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlsplit

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Test isolation (M3C audit A2): importing the integration_tests package refuses to continue unless both emulator
# hosts are loopback and the project is a demo- project, and installs the emulator-mode guards, before any
# Firebase, Google or application import, also when this file is executed directly. The checks below are kept.
import integration_tests  # noqa: E402,F401
from tests import isolation  # noqa: E402

isolation.require_guards(isolation.EMULATOR)

from core import firebase as core_firebase  # noqa: E402

AUTH_HOST = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST")
FIRESTORE_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")
PROJECT_ID = os.environ.get("GCLOUD_PROJECT")
if not (core_firebase.is_loopback_host_port(AUTH_HOST)
        and core_firebase.is_loopback_host_port(FIRESTORE_HOST)
        and core_firebase.is_demo_project_id(PROJECT_ID)):
    raise RuntimeError(
        "Refusing to run: start these tests with `firebase emulators:exec --only auth,firestore "
        "--project demo-route2unikl` (loopback emulator hosts and a demo- project are required).")

import firebase_admin  # noqa: E402
import requests  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402

from routes import admin_users as admin_users_routes  # noqa: E402
from routes import auth_check as auth_check_routes  # noqa: E402

PRODUCTION_PROJECT_ID = "route2unikl"
API_KEY = "emulator-only-placeholder"  # the Auth emulator accepts any API key
HTTP_HOSTS = []  # host:port of every HTTP request made through `requests` in this process
_patchers = []


def _recording_send(original_send):
    def send(session, request, **kwargs):
        HTTP_HOSTS.append(urlsplit(request.url).netloc)
        return original_send(session, request, **kwargs)
    return send


def reset_emulators():
    requests.delete(f"http://{AUTH_HOST}/emulator/v1/projects/{PROJECT_ID}/accounts",
                    timeout=10).raise_for_status()
    requests.delete(f"http://{FIRESTORE_HOST}/emulator/v1/projects/{PROJECT_ID}/databases/(default)/documents",
                    timeout=10).raise_for_status()


def setUpModule():
    patchers = [
        # Emulator mode for this process only; the hosts and project come from emulators:exec.
        mock.patch.dict(os.environ, {"ROUTE2UNIKL_FIREBASE_MODE": "emulator",
                                     "ROUTE2UNIKL_EMULATOR_PROJECT_ID": PROJECT_ID}),
        # Any attempt to load a service-account key fails loudly.
        mock.patch("core.firebase.credentials.Certificate",
                   side_effect=AssertionError("a service-account key must never be loaded")),
        mock.patch.object(requests.Session, "send", _recording_send(requests.Session.send)),
    ]
    for patcher in patchers:
        patcher.start()
        _patchers.append(patcher)
    if firebase_admin._apps:
        raise RuntimeError("Refusing to run: a Firebase app already exists in this process.")
    reset_emulators()
    core_firebase.initialize_firebase()


def tearDownModule():
    try:
        reset_emulators()
        non_loopback = sorted({h for h in HTTP_HOSTS if not core_firebase.is_loopback_host_port(h)})
        if non_loopback:
            raise AssertionError(f"HTTP requests left the machine: {non_loopback}")
    finally:
        try:
            firebase_admin.delete_app(firebase_admin.get_app())
        except ValueError:
            pass
        while _patchers:
            _patchers.pop().stop()


# ------------------------------------------------- client-side helpers (REST, like the browser SDK)
def identity(path, **body):
    return requests.post(f"http://{AUTH_HOST}/identitytoolkit.googleapis.com/v1/{path}?key={API_KEY}",
                         json=body, timeout=10)


def refresh(refresh_token):
    return requests.post(f"http://{AUTH_HOST}/securetoken.googleapis.com/v1/token?key={API_KEY}",
                         data={"grant_type": "refresh_token", "refresh_token": refresh_token}, timeout=10)


def error_message(response):
    return (response.json().get("error") or {}).get("message")


def new_student():
    """Register a new account through the emulator's sign-up endpoint."""
    account = SimpleNamespace(email=f"student-{uuid.uuid4().hex[:12]}@example.test",
                              password=f"Pw-{uuid.uuid4().hex}")
    response = identity("accounts:signUp", email=account.email, password=account.password, returnSecureToken=True)
    assert response.status_code == 200, response.text
    account.uid = response.json()["localId"]
    return account


def sign_in(account):
    return identity("accounts:signInWithPassword", email=account.email, password=account.password,
                    returnSecureToken=True)


def tokens(account):
    response = sign_in(account)
    assert response.status_code == 200, response.text
    return response.json()["idToken"], response.json()["refreshToken"]


def unsigned_token(**claims):
    """An unsigned JWT in the emulator's format (alg "none")."""
    def encode(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    now = int(time.time())
    payload = {"iss": f"https://securetoken.google.com/{PROJECT_ID}", "aud": PROJECT_ID,
               "iat": now, "exp": now + 3600, "auth_time": now, **claims}
    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}."


def jwt_header(token):
    segment = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def build_app():
    """The production routers, mounted with the same prefixes as main.py (no AI or ChromaDB imports)."""
    app = FastAPI()
    app.include_router(auth_check_routes.router, prefix="/api")
    app.include_router(admin_users_routes.router, prefix="/api/admin/users")
    return app


class EmulatorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(build_app())

    def me(self, token):
        return self.client.get("/api/auth/me", headers=bearer(token))

    def assert_status(self, response, status_code, detail=None):
        self.assertEqual(response.status_code, status_code, response.text)
        if detail is not None:
            self.assertEqual(response.json()["detail"], detail)


class AuthenticationTests(EmulatorTestCase):
    def test_01_student_created_signed_in_and_authenticated(self):
        student = new_student()
        token, _ = tokens(student)
        self.assertEqual(jwt_header(token)["alg"], "none", "emulator ID tokens are unsigned")
        response = self.me(token)
        self.assert_status(response, 200)
        self.assertEqual(response.json(), {"uid": student.uid, "is_admin": False})

    def test_02_missing_or_invalid_credentials_are_rejected(self):
        student = new_student()
        cases = {
            "no Authorization header": {},
            "Basic scheme": {"Authorization": "Basic c3R1ZGVudDpwYXNz"},
            "empty Bearer": {"Authorization": "Bearer "},
            "not a JWT": bearer("not-a-jwt"),
            "token for another demo project": bearer(unsigned_token(sub=student.uid, aud="demo-other",
                                                                    iss="https://securetoken.google.com/demo-other")),
            "token for the production project": bearer(unsigned_token(
                sub=student.uid, aud=PRODUCTION_PROJECT_ID,
                iss=f"https://securetoken.google.com/{PRODUCTION_PROJECT_ID}")),
            "token for an unknown account": bearer(unsigned_token(sub="no-such-account")),
        }
        for label, headers in cases.items():
            with self.subTest(label):
                response = self.client.get("/api/auth/me", headers=headers)
                self.assert_status(response, 401)

    def test_03_non_admin_cannot_access_admin_apis(self):
        student = new_student()
        string_claim = new_student()
        firebase_auth.set_custom_user_claims(string_claim.uid, {"admin": "true"})
        for label, account in (("student", student), ('string claim "true"', string_claim)):
            token, _ = tokens(account)
            for path in ("/api/admin/verify", "/api/admin/users", f"/api/admin/users/{student.uid}"):
                with self.subTest(label, path=path):
                    response = self.client.get(path, headers=bearer(token))
                    self.assert_status(response, 403, "Administrator privileges required.")

    def test_04_emulator_admin_claim_is_recognised(self):
        admin = new_student()
        student = new_student()
        old_token, _ = tokens(admin)
        firebase_auth.set_custom_user_claims(admin.uid, {"admin": True})

        # A token issued before the claim was set does not carry it.
        self.assert_status(self.client.get("/api/admin/verify", headers=bearer(old_token)), 403)

        token, _ = tokens(admin)
        self.assert_status(self.client.get("/api/admin/verify", headers=bearer(token)), 200)
        self.assertEqual(self.me(token).json(), {"uid": admin.uid, "is_admin": True})

        # The M3A list endpoint reads accounts from the Auth emulator and profiles from the Firestore emulator.
        core_firebase.initialize_firebase().collection("users").document(student.uid).set(
            {"name": "Emulator Student", "email": student.email, "role": "spm_leaver"})
        response = self.client.get("/api/admin/users", headers=bearer(token))
        self.assert_status(response, 200)
        items = {item["uid"]: item for item in response.json()["items"]}
        self.assertTrue(items[admin.uid]["is_admin"])
        self.assertEqual((items[student.uid]["name"], items[student.uid]["student_type"],
                          items[student.uid]["profile_status"]), ("Emulator Student", "spm_leaver", "present"))

    def test_05_disabled_account_is_rejected(self):
        student = new_student()
        token, refresh_token = tokens(student)
        self.assert_status(self.me(token), 200)
        firebase_auth.update_user(student.uid, disabled=True)
        self.assert_status(self.me(token), 403, "This account has been disabled.")
        self.assertEqual(error_message(sign_in(student)), "USER_DISABLED")
        self.assertEqual(error_message(refresh(refresh_token)), "USER_DISABLED")

    def test_06_reenabled_account_old_session_returns_until_tokens_are_revoked(self):
        student = new_student()
        old_token, _ = tokens(student)
        time.sleep(1.1)  # revocation compares whole seconds
        firebase_auth.update_user(student.uid, disabled=True)
        firebase_auth.update_user(student.uid, disabled=False)

        new_token, _ = tokens(student)
        self.assert_status(self.me(new_token), 200)
        # Re-enabling alone restores the old session (no revocation happened);
        # account actions must therefore revoke tokens when re-enabling.
        self.assert_status(self.me(old_token), 200)
        firebase_auth.revoke_refresh_tokens(student.uid)
        self.assert_status(self.me(old_token), 401, "Session revoked. Please sign in again.")

    def test_07_revoked_tokens_are_rejected_and_a_new_sign_in_works(self):
        student = new_student()
        token, _ = tokens(student)
        self.assert_status(self.me(token), 200)
        time.sleep(1.1)  # revocation compares whole seconds
        firebase_auth.revoke_refresh_tokens(student.uid)
        self.assert_status(self.me(token), 401, "Session revoked. Please sign in again.")
        new_token, _ = tokens(student)
        self.assert_status(self.me(new_token), 200)

    def test_08_deleted_account_can_no_longer_authenticate(self):
        student = new_student()
        token, refresh_token = tokens(student)
        firebase_auth.delete_user(student.uid)
        self.assert_status(self.me(token), 401, "Account not found. Please sign in again.")
        self.assertEqual(error_message(sign_in(student)), "EMAIL_NOT_FOUND")
        self.assertNotEqual(refresh(refresh_token).status_code, 200)


class EmulatorLimitationTests(EmulatorTestCase):
    """Emulator behaviour that differs from production. Recorded so that a change is noticed."""

    def test_unsigned_forged_tokens_are_accepted_in_emulator_mode(self):
        # The Admin SDK skips signature (and expiry) checks whenever FIREBASE_AUTH_EMULATOR_HOST
        # is set. This is why production mode refuses to start with any emulator setting
        # (tests/test_firebase_config.py).
        student = new_student()
        forged = unsigned_token(sub=student.uid, admin=True)
        self.assert_status(self.client.get("/api/admin/verify", headers=bearer(forged)), 200)

    def test_refresh_token_still_works_after_revocation_in_the_emulator(self):
        # Firebase documents that revoking ends refresh tokens; the emulator still exchanges them.
        student = new_student()
        _, refresh_token = tokens(student)
        time.sleep(1.1)
        firebase_auth.revoke_refresh_tokens(student.uid)
        self.assertEqual(refresh(refresh_token).status_code, 200)


class IsolationTests(EmulatorTestCase):
    def test_09_no_real_credentials_or_production_project_are_used(self):
        app = firebase_admin.get_app()
        self.assertEqual(app.project_id, PROJECT_ID)
        self.assertTrue(app.project_id.startswith("demo-"))
        self.assertNotEqual(app.project_id, PRODUCTION_PROJECT_ID)
        self.assertIsInstance(app.credential, core_firebase.EmulatorCredential)
        self.assertEqual(core_firebase.initialized_config(), core_firebase.FirebaseConfig(
            "emulator", PROJECT_ID, AUTH_HOST, FIRESTORE_HOST, "emulator"))
        core_firebase.check_runtime_configuration()
        self.assertTrue(firebase_auth.Client(app).emulated)
        self.assertEqual(core_firebase.initialize_firebase()._emulator_host, FIRESTORE_HOST)
        tokens(new_student())  # at least one request through the recorder
        self.assertTrue(HTTP_HOSTS)
        self.assertTrue(all(core_firebase.is_loopback_host_port(host) for host in HTTP_HOSTS), HTTP_HOSTS)


class InvalidConfigurationTests(EmulatorTestCase):
    """An invalid configuration stops before any connection; it never falls back to production."""

    def setUp(self):
        self.token, _ = tokens(new_student())
        firebase_admin.delete_app(firebase_admin.get_app())  # force re-initialization per request

    def tearDown(self):
        core_firebase.initialize_firebase()  # restore the valid emulator app

    def test_10_invalid_configuration_returns_503_without_connecting(self):
        cases = {
            "production mode while the emulator hosts are set": {"ROUTE2UNIKL_FIREBASE_MODE": None},
            "emulator mode with the production project": {"ROUTE2UNIKL_EMULATOR_PROJECT_ID": PRODUCTION_PROJECT_ID},
            "emulator mode with a non-loopback Auth host": {"FIREBASE_AUTH_EMULATOR_HOST": "0.0.0.0:9099"},
            "emulator mode with application-default credentials": {"GOOGLE_APPLICATION_CREDENTIALS": "key.json"},
            "unknown mode": {"ROUTE2UNIKL_FIREBASE_MODE": "staging"},
        }
        for label, changes in cases.items():
            with self.subTest(label), mock.patch.dict(os.environ):
                for name, value in changes.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
                requests_before = len(HTTP_HOSTS)
                with self.assertRaises(core_firebase.FirebaseConfigError):
                    core_firebase.initialize_firebase()
                with self.assertLogs("auth", level="ERROR"):
                    self.assert_status(self.me(self.token), 503)
                self.assertEqual(len(HTTP_HOSTS), requests_before, "no request was made")
                with self.assertRaises(ValueError):
                    firebase_admin.get_app()  # no app was created


def changed_env(changes):
    """Apply `changes` to os.environ (None removes a variable); use inside mock.patch.dict(os.environ)."""
    for name, value in changes.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class RuntimeConfigurationTests(EmulatorTestCase):
    """Settings changed after initialization, or during verification, never authenticate anyone."""

    def setUp(self):
        self.student_token, _ = tokens(new_student())
        admin = new_student()
        firebase_auth.set_custom_user_claims(admin.uid, {"admin": True})
        self.admin_token, _ = tokens(admin)
        self.endpoints = (("/api/auth/me", self.student_token), ("/api/admin/verify", self.admin_token),
                          ("/api/admin/users", self.admin_token))

    def assert_all_endpoints(self, status_code):
        for path, token in self.endpoints:
            self.assert_status(self.client.get(path, headers=bearer(token)), status_code)

    def test_11_settings_changed_after_initialization_return_503_without_verifying(self):
        self.assert_all_endpoints(200)
        cases = {
            "Auth emulator host changed": {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9100"},
            "Auth emulator host removed": {"FIREBASE_AUTH_EMULATOR_HOST": None},
            "Firestore emulator host changed": {"FIRESTORE_EMULATOR_HOST": "127.0.0.1:8081"},
            "Firestore emulator host removed": {"FIRESTORE_EMULATOR_HOST": None},
            "emulator project changed": {"ROUTE2UNIKL_EMULATOR_PROJECT_ID": "demo-other", "GCLOUD_PROJECT": "demo-other"},
            "mode switched to production": {"ROUTE2UNIKL_FIREBASE_MODE": "production"},
            "all emulator settings removed": {"ROUTE2UNIKL_FIREBASE_MODE": None, "ROUTE2UNIKL_EMULATOR_PROJECT_ID": None,
                                              "FIREBASE_AUTH_EMULATOR_HOST": None, "FIRESTORE_EMULATOR_HOST": None,
                                              "GCLOUD_PROJECT": None},
        }
        with mock.patch("core.auth.firebase_auth.verify_id_token", wraps=firebase_auth.verify_id_token) as verify:
            for label, changes in cases.items():
                with self.subTest(label), mock.patch.dict(os.environ):
                    changed_env(changes)
                    with self.assertLogs("auth", level="ERROR"):
                        self.assert_all_endpoints(503)
            verify.assert_not_called()
        self.assert_all_endpoints(200)  # the restored configuration works again

    def test_12_settings_changed_during_verification_reject_the_verified_identity(self):
        real_verify = firebase_auth.verify_id_token

        def verify_then_change(token, **kwargs):
            claims = real_verify(token, **kwargs)
            os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = "127.0.0.1:9100"
            return claims

        for path, token in self.endpoints:
            with self.subTest(path=path), mock.patch.dict(os.environ), \
                    mock.patch("core.auth.firebase_auth.verify_id_token", side_effect=verify_then_change) as verify, \
                    self.assertLogs("auth", level="ERROR") as logs:
                self.assert_status(self.client.get(path, headers=bearer(token)), 503)
            verify.assert_called_once()
            self.assertTrue(any("changed during token verification" in line for line in logs.output))
        self.assert_all_endpoints(200)


if __name__ == "__main__":
    unittest.main()
