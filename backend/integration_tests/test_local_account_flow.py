# backend/integration_tests/test_local_account_flow.py
"""
M3B-1B-P1-B2B/C: the local student account flow through the real backend
application (main.app), against the LOCAL Firebase Authentication and Firestore
emulators (project demo-route2unikl).

Run with the other emulator integration tests, from the backend directory:
    firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\\Scripts\\python.exe -m unittest discover -s integration_tests -t . -v"

Uses the module set-up and teardown of test_auth_emulator.py (imported below):
loopback emulator hosts and a demo- project are required, emulator mode is
switched on for this process only, the service-account loader fails if
called, every HTTP request is recorded (all must stay on loopback) and both
emulators are wiped before and after.

The experimental account-access rules (firestore-tests/account-access.experimental.rules)
are loaded into the running Firestore emulator for this module only, and the
production rules (firestore.rules) are restored afterwards. Students act
through the Firestore REST API with their own ID tokens, as the browser does.
Account state changes (disable, delete) are simulated with the Admin SDK on
emulator accounts, record first, as the planned M3B account actions would do.
"""
import contextlib
import importlib
import io
import os
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# setUpModule / tearDownModule are picked up by unittest for this module.
from integration_tests.test_auth_emulator import (  # noqa: E402,F401
    FIRESTORE_HOST, HTTP_HOSTS, PRODUCTION_PROJECT_ID, PROJECT_ID, bearer, error_message, new_student, setUpModule,
    sign_in, tearDownModule)

import firebase_admin  # noqa: E402
import requests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402

from core import firebase as core_firebase  # noqa: E402
from services import account_access_service  # noqa: E402

REPO_DIR = BACKEND_DIR.parent
EXPERIMENTAL_RULES = REPO_DIR / "firestore-tests" / "account-access.experimental.rules"
PRODUCTION_RULES = REPO_DIR / "firestore.rules"
REGISTER_URL = "/api/account/register"
DOCUMENTS = f"http://{FIRESTORE_HOST}/v1/projects/{PROJECT_ID}/databases/(default)/documents"


def load_rules(path):
    """Replace the rules of the running Firestore emulator (emulator API; never production)."""
    body = {"rules": {"files": [{"name": "firestore.rules", "content": path.read_text(encoding="utf-8")}]}}
    response = requests.put(f"http://{FIRESTORE_HOST}/emulator/v1/projects/{PROJECT_ID}:securityRules",
                            json=body, timeout=10)
    response.raise_for_status()


def import_main():
    """A fresh import of the real application under the current environment."""
    sys.modules.pop("main", None)
    with contextlib.redirect_stdout(io.StringIO()):
        return importlib.import_module("main")


def registration_body(**overrides):
    return {"name": "Local Student", "email": f"local-{uuid.uuid4().hex[:10]}@example.test",
            "password": f"Pw-{uuid.uuid4().hex}", "role": "spm_leaver", **overrides}


class LocalAccountFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = import_main().app  # emulator mode: the registration route is mounted
        cls.client = TestClient(cls.app)
        load_rules(EXPERIMENTAL_RULES)

    @classmethod
    def tearDownClass(cls):
        try:
            load_rules(PRODUCTION_RULES)
        finally:
            sys.modules.pop("main", None)

    def setUp(self):
        self.db = core_firebase.initialize_firebase()

    # ------------------------------------------------------------------ helpers
    def register(self, body):
        return self.client.post(REGISTER_URL, json=body)

    def registered_student(self):
        body = registration_body()
        self.assertEqual(self.register(body).status_code, 201)
        uid = firebase_auth.get_user_by_email(body["email"]).uid
        return SimpleNamespace(uid=uid, body=body, token=self.sign_in_token(body))

    def sign_in_token(self, body):
        response = sign_in(SimpleNamespace(email=body["email"], password=body["password"]))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["idToken"]

    def read_doc(self, token, collection, doc_id):
        return requests.get(f"{DOCUMENTS}/{collection}/{doc_id}", headers=bearer(token), timeout=10).status_code

    def create_profile(self, token, uid, email):
        """The current browser registration write (users/{uid}) with the student's own token."""
        fields = {"name": {"stringValue": "Browser Student"}, "email": {"stringValue": email},
                  "role": {"stringValue": "spm_leaver"}, "createdAt": {"timestampValue": "2026-11-24T00:00:00Z"}}
        return requests.post(f"{DOCUMENTS}/users?documentId={uid}", json={"fields": fields},
                             headers=bearer(token), timeout=10).status_code

    def me(self, token):
        return self.client.get("/api/auth/me", headers=bearer(token))

    def record(self, uid):
        snapshot = self.db.collection("account_access").document(uid).get()
        return (snapshot.to_dict() if snapshot.exists else None), snapshot.update_time

    # -------------------------------------------------------------------- tests
    def test_01_registration_and_login_through_the_application(self):
        student = self.registered_student()
        self.assertEqual(self.me(student.token).json(), {"uid": student.uid, "is_admin": False})
        self.assertEqual(self.read_doc(student.token, "users", student.uid), 200, "own profile through the guard")
        self.assertEqual(self.read_doc(student.token, "account_access", student.uid), 403, "record is backend-only")
        other = self.registered_student()
        self.assertEqual(self.read_doc(student.token, "users", other.uid), 403, "another student's profile")

    def test_02_a_duplicate_email_is_refused(self):
        body = registration_body()
        self.assertEqual(self.register(body).status_code, 201)
        self.assertEqual(self.register({**body, "name": "Someone Else"}).json(), {"code": "EMAIL_IN_USE"})

    def test_03_an_incomplete_registration_leaves_a_blocked_account(self):
        body = registration_body()
        with mock.patch("services.registration_service._create_profile",
                        side_effect=google_exceptions.ServiceUnavailable("Firestore unavailable")):
            response = self.register(body)
        self.assertEqual((response.status_code, response.json()), (503, {"code": "REGISTRATION_INCOMPLETE"}))
        self.assertEqual(error_message(sign_in(SimpleNamespace(email=body["email"], password=body["password"]))),
                         "USER_DISABLED")
        self.assertIsNone(self.record(firebase_auth.get_user_by_email(body["email"]).uid)[0])

    def test_04_a_disabled_student_is_blocked_even_with_an_earlier_token(self):
        student = self.registered_student()
        self.assertEqual(self.read_doc(student.token, "users", student.uid), 200)
        # Disable as the planned account action would: the access record first, then Firebase Authentication.
        self.db.collection("account_access").document(student.uid).update({"state": "disabled", "version": 2})
        firebase_auth.update_user(student.uid, disabled=True)

        self.assertEqual(self.read_doc(student.token, "users", student.uid), 403, "earlier token, Firestore guard")
        self.assertEqual(self.me(student.token).status_code, 403, "earlier token, backend")
        self.assertEqual(error_message(sign_in(SimpleNamespace(email=student.body["email"],
                                                               password=student.body["password"]))), "USER_DISABLED")

    def test_05_a_deleted_student_cannot_read_or_recreate_data_with_an_earlier_token(self):
        student = self.registered_student()
        # Delete as the planned account action would: block the record, remove data, delete the account.
        self.db.collection("account_access").document(student.uid).update({"state": "deleting", "version": 2})
        self.db.collection("users").document(student.uid).delete()
        firebase_auth.delete_user(student.uid)
        self.db.collection("account_access").document(student.uid).update({"state": "deleted", "version": 3})

        self.assertEqual(self.read_doc(student.token, "users", student.uid), 403)
        self.assertEqual(self.create_profile(student.token, student.uid, student.body["email"]), 403,
                         "the deleted profile cannot be recreated")
        self.assertEqual(self.me(student.token).status_code, 401)
        self.assertEqual(error_message(sign_in(SimpleNamespace(email=student.body["email"],
                                                               password=student.body["password"]))), "EMAIL_NOT_FOUND")

    def test_06_an_account_without_a_record_is_blocked_and_login_never_creates_one(self):
        old = new_student()  # registered the current browser way: no access record
        token = self.sign_in_token({"email": old.email, "password": old.password})
        self.assertEqual(self.create_profile(token, old.uid, old.email), 403,
                         "with the guard, browser registration can no longer create the profile")
        self.assertEqual(self.read_doc(token, "users", old.uid), 403)
        self.assertEqual(self.me(token).status_code, 200, "the backend itself does not consult the record")
        self.assertIsNone(self.record(old.uid)[0], "neither sign-in nor the backend created a record")

    def test_07_login_never_changes_a_blocked_record(self):
        student = self.registered_student()
        self.db.collection("account_access").document(student.uid).update({"state": "disabled", "version": 2})
        before = self.record(student.uid)  # inconsistent on purpose: Auth is still enabled
        token = self.sign_in_token(student.body)
        self.assertEqual(self.me(token).status_code, 200)
        self.assertEqual(self.read_doc(token, "users", student.uid), 403)
        self.assertEqual(self.record(student.uid), before, "sign-in and backend calls never reactivate it")

    def test_08_production_mode_has_no_registration_route(self):
        before = sum(1 for _ in firebase_auth.list_users().iterate_all())
        with mock.patch.dict(os.environ, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}):
            production_app = import_main().app
            self.assertNotIn(REGISTER_URL, production_app.openapi()["paths"])
            response = TestClient(production_app).post(REGISTER_URL, json=registration_body())
        sys.modules.pop("main", None)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(sum(1 for _ in firebase_auth.list_users().iterate_all()), before)
        self.assertIn(REGISTER_URL, self.app.openapi()["paths"], "mounted in the emulator-mode application")

    def test_09_only_the_emulators_are_used(self):
        app = firebase_admin.get_app()
        self.assertIsInstance(app.credential, core_firebase.EmulatorCredential)
        self.assertEqual(app.project_id, PROJECT_ID)
        self.assertNotEqual(app.project_id, PRODUCTION_PROJECT_ID)
        self.assertTrue(HTTP_HOSTS)
        self.assertTrue(all(core_firebase.is_loopback_host_port(host) for host in HTTP_HOSTS), HTTP_HOSTS)
        self.assertTrue(account_access_service.inspect_account(self.registered_student().uid).consistent)


if __name__ == "__main__":
    unittest.main()
