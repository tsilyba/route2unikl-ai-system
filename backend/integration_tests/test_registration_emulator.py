# backend/integration_tests/test_registration_emulator.py
"""
M3B-1B-P1-B2A: trusted student registration against the LOCAL Firebase
Authentication and Firestore emulators (project demo-route2unikl).

Run with the other emulator integration tests, from the backend directory:
    firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\\Scripts\\python.exe -m unittest discover -s integration_tests -t . -v"

Uses the module set-up and teardown of test_auth_emulator.py (imported below;
unittest runs them for this module too): it refuses to run without loopback
emulator hosts and a demo- project, switches emulator mode on for this process
only, makes the service-account loader fail if called, records every HTTP
request (all must stay on loopback) and wipes both emulators before and after.
The registration router is mounted only in the test app built here.
"""
import base64
import json
import logging
import os
import sys
import threading
import unittest
import uuid
from datetime import datetime
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
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402

from core import firebase as core_firebase  # noqa: E402
from routes import auth_check as auth_check_routes  # noqa: E402
from routes import registration as registration_routes  # noqa: E402
from services import account_access_service  # noqa: E402

URL = "/api/account/register"


def registration_body(**overrides):
    return {"name": "Emulator Student", "email": f"reg-{uuid.uuid4().hex[:10]}@example.test",
            "password": f"Pw-{uuid.uuid4().hex}", "role": "spm_leaver", **overrides}


class CapturedLogs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class RegistrationEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(registration_routes.router, prefix="/api/account")
        app.include_router(auth_check_routes.router, prefix="/api")
        cls.client = TestClient(app)

    def setUp(self):
        self.db = core_firebase.initialize_firebase()

    def register(self, body):
        return self.client.post(URL, json=body)

    def account_count(self):
        return sum(1 for _ in firebase_auth.list_users().iterate_all())

    def stored(self, collection, uid):
        snapshot = self.db.collection(collection).document(uid).get()
        return (snapshot.to_dict() if snapshot.exists else None), snapshot.update_time

    def sign_in_token(self, body):
        response = sign_in(SimpleNamespace(email=body["email"], password=body["password"]))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["idToken"]

    def assert_incomplete_and_disabled(self, response, body):
        self.assertEqual((response.status_code, response.json()), (503, {"code": "REGISTRATION_INCOMPLETE"}))
        user = firebase_auth.get_user_by_email(body["email"])
        self.assertTrue(user.disabled, "the incomplete account is disabled, not deleted")
        self.assertEqual(error_message(sign_in(SimpleNamespace(email=body["email"], password=body["password"]))),
                         "USER_DISABLED")
        return user

    def test_01_both_roles_register_and_the_student_can_sign_in(self):
        for role in ("spm_leaver", "form_4_5"):
            with self.subTest(role=role):
                body = registration_body(role=role)
                response = self.register(body)
                self.assertEqual((response.status_code, response.json()), (201, {"status": "registered"}))
                self.assertNotIn(body["password"], response.text)

                user = firebase_auth.get_user_by_email(body["email"])
                self.assertFalse(user.disabled)
                profile, _ = self.stored("users", user.uid)
                self.assertEqual({k: profile[k] for k in ("name", "email", "role")},
                                 {"name": "Emulator Student", "email": body["email"], "role": role})
                self.assertEqual(set(profile), {"name", "email", "role", "createdAt"})
                self.assertIsInstance(profile["createdAt"], datetime)
                self.assertEqual(self.stored("account_access", user.uid)[0], {"state": "active", "version": 1})
                self.assertTrue(account_access_service.inspect_account(user.uid).consistent)

                me = self.client.get("/api/auth/me", headers=bearer(self.sign_in_token(body)))
                self.assertEqual((me.status_code, me.json()), (200, {"uid": user.uid, "is_admin": False}))

    def test_02_privileged_fields_and_roles_are_refused_and_nothing_is_created(self):
        before = self.account_count()
        for extra in ({"uid": "chosen-uid"}, {"admin": True}, {"customClaims": {"admin": True}},
                      {"disabled": False}, {"emailVerified": True}, {"state": "active"}):
            with self.subTest(extra=extra):
                response = self.register({**registration_body(), **extra})
                self.assertEqual(response.json(), {"code": "INVALID_REGISTRATION", "fields": ["unexpected_field"]})
        for role in ("admin", "upper_secondary"):
            with self.subTest(role=role):
                response = self.register(registration_body(role=role))
                self.assertEqual(response.json(), {"code": "INVALID_REGISTRATION", "fields": ["role"]})
        for body in (registration_body(password="short"), registration_body(email="not-an-email"),
                     registration_body(name="  "), {"email": "x@example.test"}):
            with self.subTest(body=sorted(body)):
                self.assertEqual(self.register(body).status_code, 422)
        self.assertEqual(self.account_count(), before)

    def test_03_an_existing_account_is_never_activated(self):
        old = new_student()  # created the current way (browser sign-up), without an access record
        before = self.account_count()
        response = self.register(registration_body(email=old.email))
        self.assertEqual((response.status_code, response.json()), (409, {"code": "EMAIL_IN_USE"}))
        self.assertEqual(account_access_service.read_access_record(old.uid).status, "missing")
        self.assertIsNone(self.stored("users", old.uid)[0])
        self.assertFalse(firebase_auth.get_user(old.uid).disabled)
        self.assertEqual(self.account_count(), before)

    def test_04_an_existing_blocked_record_is_unchanged(self):
        old = new_student()
        firebase_auth.update_user(old.uid, disabled=True)
        self.db.collection("account_access").document(old.uid).set({"state": "disabled", "version": 3})
        record_before = self.stored("account_access", old.uid)
        response = self.register(registration_body(email=old.email))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stored("account_access", old.uid), record_before)
        self.assertTrue(firebase_auth.get_user(old.uid).disabled)

    def test_05_a_duplicate_or_retried_request_creates_one_account(self):
        body = registration_body()
        self.assertEqual(self.register(body).status_code, 201)
        uid = firebase_auth.get_user_by_email(body["email"]).uid
        record_before = self.stored("account_access", uid)
        count = self.account_count()
        # A retry after a lost response: refused, and the account it created still works.
        self.assertEqual(self.register(body).json(), {"code": "EMAIL_IN_USE"})
        self.assertEqual(self.account_count(), count)
        self.assertEqual(self.stored("account_access", uid), record_before)
        me = self.client.get("/api/auth/me", headers=bearer(self.sign_in_token(body)))
        self.assertEqual(me.status_code, 200)

    def test_06_concurrent_requests_for_one_email_create_one_account(self):
        body = registration_body()
        workers = 8
        barrier = threading.Barrier(workers)
        statuses = []

        def attempt():
            barrier.wait()
            statuses.append(self.register(body).status_code)

        threads = [threading.Thread(target=attempt) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(statuses), [201] + [409] * (workers - 1))
        uid = firebase_auth.get_user_by_email(body["email"]).uid
        self.assertEqual(self.stored("account_access", uid)[0], {"state": "active", "version": 1})

    def test_07_a_profile_failure_leaves_a_disabled_account_without_record(self):
        body = registration_body()
        with mock.patch("services.registration_service._create_profile",
                        side_effect=google_exceptions.ServiceUnavailable("Firestore unavailable")):
            response = self.register(body)
        user = self.assert_incomplete_and_disabled(response, body)
        self.assertIsNone(self.stored("users", user.uid)[0])
        self.assertIsNone(self.stored("account_access", user.uid)[0])
        # Unlike a lost success response (test 5), a retry here gets 409 and the account stays disabled:
        # the student cannot sign in, and the retry never completes or re-enables the account.
        self.assertEqual(self.register(body).json(), {"code": "EMAIL_IN_USE"})
        self.assertTrue(firebase_auth.get_user(user.uid).disabled)
        self.assertIsNone(self.stored("account_access", user.uid)[0])
        self.assertEqual(error_message(sign_in(SimpleNamespace(email=body["email"], password=body["password"]))),
                         "USER_DISABLED")

    def test_08_an_access_record_failure_leaves_a_disabled_account(self):
        body = registration_body()
        with mock.patch("services.account_access_service.provision_access_record",
                        side_effect=account_access_service.AccountAccessError(account_access_service.STORE_UNAVAILABLE)):
            response = self.register(body)
        user = self.assert_incomplete_and_disabled(response, body)
        self.assertIsNotNone(self.stored("users", user.uid)[0])
        self.assertIsNone(self.stored("account_access", user.uid)[0])

    def test_09_an_auth_change_during_provisioning_is_not_reported_as_success(self):
        body = registration_body()
        real_get_user = firebase_auth.get_user
        calls = {"n": 0}

        def get_user(uid, *args, **kwargs):
            account = real_get_user(uid, *args, **kwargs)
            calls["n"] += 1
            if calls["n"] == 1:
                firebase_auth.update_user(uid, disabled=True)  # changed before the record is written
            return account

        with mock.patch("services.account_access_service.firebase_auth.get_user", side_effect=get_user):
            response = self.register(body)
        user = self.assert_incomplete_and_disabled(response, body)
        # The record written in the meantime stays 'active' (HL2); inspection reports the mismatch.
        self.assertEqual(self.stored("account_access", user.uid)[0], {"state": "active", "version": 1})
        self.assertEqual(account_access_service.inspect_account(user.uid).issues,
                         (account_access_service.AUTH_DISABLED_RECORD_ACTIVE,))

    def test_10_the_route_does_not_exist_outside_emulator_mode(self):
        before = self.account_count()
        with mock.patch("routes.registration.registration.register_student") as service:
            for changes in ({"ROUTE2UNIKL_FIREBASE_MODE": "production"}, {"ROUTE2UNIKL_FIREBASE_MODE": None}):
                with self.subTest(changes=changes), mock.patch.dict(os.environ):
                    for name, value in changes.items():
                        if value is None:
                            os.environ.pop(name, None)
                        else:
                            os.environ[name] = value
                    response = self.register(registration_body())
                    self.assertEqual((response.status_code, response.json()), (404, {"detail": "Not Found"}))
            service.assert_not_called()
        self.assertEqual(self.account_count(), before)

    def test_11_passwords_never_appear_in_logs_responses_or_documents(self):
        root = logging.getLogger()
        logs = CapturedLogs()
        saved = root.level
        root.addHandler(logs)
        root.setLevel(logging.DEBUG)
        try:
            ok = registration_body()
            responses = [self.register(ok), self.register(ok), self.register(registration_body(role="admin"))]
            incomplete = registration_body()
            with mock.patch("services.registration_service._create_profile",
                            side_effect=google_exceptions.ServiceUnavailable("down")):
                responses.append(self.register(incomplete))
        finally:
            root.removeHandler(logs)
            root.setLevel(saved)
        self.assertEqual([r.status_code for r in responses], [201, 409, 422, 503])
        secrets = (ok["password"], incomplete["password"], ok["email"], incomplete["email"])
        for text in [r.text for r in responses] + logs.messages:
            for secret in secrets:
                self.assertNotIn(secret, text)
        uid = firebase_auth.get_user_by_email(ok["email"]).uid
        for collection in ("users", "account_access"):
            self.assertNotIn(ok["password"], repr(self.stored(collection, uid)[0]))

    def test_13_the_profile_matches_the_registration_schema_and_works_under_the_production_rules(self):
        # The Firestore emulator enforces firestore.rules (the deployed production rules) for requests made
        # with the student's own ID token, as the browser would make them.
        for role in ("spm_leaver", "form_4_5"):
            with self.subTest(role=role):
                body = registration_body(role=role)
                self.assertEqual(self.register(body).status_code, 201)
                token = self.sign_in_token(body)
                segment = token.split(".")[1]
                claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
                uid = claims["user_id"]
                profile, _ = self.stored("users", uid)
                # Exactly the fields and types the registration rule (isValidNewUser) requires.
                self.assertEqual(set(profile), {"name", "email", "role", "createdAt"})
                self.assertTrue(isinstance(profile["name"], str) and 0 < len(profile["name"]) <= 100)
                self.assertEqual(profile["email"], claims["email"], "equals the token's email claim")
                self.assertEqual(profile["role"], role)
                self.assertIsInstance(profile["createdAt"], datetime)

                url = f"http://{FIRESTORE_HOST}/v1/projects/{PROJECT_ID}/databases/(default)/documents/users/{uid}"
                headers = bearer(token)
                self.assertEqual(requests.get(url, headers=headers, timeout=10).status_code, 200)
                # The ProfileIngestion update the app makes next is allowed...
                update = {"fields": {"currentStep": {"integerValue": "2"}, "hasCompletedProfile": {"booleanValue": True},
                                     "chosenInterests": {"arrayValue": {"values": [{"stringValue": "Engineering"}]}},
                                     "updatedAt": {"timestampValue": "2026-11-24T00:00:00Z"}}}
                mask = "&".join(f"updateMask.fieldPaths={f}" for f in update["fields"])
                self.assertEqual(requests.patch(f"{url}?{mask}", json=update, headers=headers, timeout=10).status_code,
                                 200)
                # ...and the rules still protect the role.
                denied = {"fields": {"role": {"stringValue": "form_4_5" if role == "spm_leaver" else "spm_leaver"}}}
                self.assertEqual(requests.patch(f"{url}?updateMask.fieldPaths=role", json=denied, headers=headers,
                                                timeout=10).status_code, 403)
                # Another student cannot read it.
                other = registration_body()
                self.assertEqual(self.register(other).status_code, 201)
                self.assertEqual(requests.get(url, headers=bearer(self.sign_in_token(other)), timeout=10).status_code,
                                 403)

    def test_12_only_the_emulators_are_used(self):
        app = firebase_admin.get_app()
        self.assertIsInstance(app.credential, core_firebase.EmulatorCredential)
        self.assertEqual(app.project_id, PROJECT_ID)
        self.assertNotEqual(app.project_id, PRODUCTION_PROJECT_ID)
        self.assertEqual(core_firebase.initialized_config().mode, core_firebase.EMULATOR_MODE)
        self.assertEqual(self.register(registration_body()).status_code, 201)
        self.assertTrue(HTTP_HOSTS)
        self.assertTrue(all(core_firebase.is_loopback_host_port(host) for host in HTTP_HOSTS), HTTP_HOSTS)


if __name__ == "__main__":
    unittest.main()
