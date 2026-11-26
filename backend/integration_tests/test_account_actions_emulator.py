# backend/integration_tests/test_account_actions_emulator.py
"""
M3B-2: admin Disable / Enable account actions through the real backend application (main.app), against
the LOCAL Firebase Authentication and Firestore emulators (project demo-route2unikl).

Run with the other emulator integration tests, from the backend directory:
    firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\\Scripts\\python.exe -m unittest discover -s integration_tests -t . -v"

Uses the module set-up and teardown of test_auth_emulator.py (loopback emulator hosts, a demo- project,
emulator mode for this process only, a service-account loader that fails if called, every HTTP request
recorded, both emulators wiped before and after). The experimental account-access rules are loaded into
the running Firestore emulator for this module and the production rules restored afterwards. Students
are registered through the trusted registration route, so they have well-formed access records; they
read Firestore through the REST API with their own ID tokens, as the browser does. The administrator is
an emulator account given the admin custom claim with the Admin SDK (emulator only).
"""
import os
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# setUpModule / tearDownModule are picked up by unittest for this module.
from integration_tests.test_auth_emulator import (  # noqa: E402,F401
    HTTP_HOSTS, PRODUCTION_PROJECT_ID, PROJECT_ID, bearer, error_message, new_student, setUpModule, sign_in,
    tearDownModule, tokens)
from integration_tests.test_local_account_flow import (  # noqa: E402
    DOCUMENTS, EXPERIMENTAL_RULES, PRODUCTION_RULES, REGISTER_URL, import_main, load_rules, registration_body)

import firebase_admin  # noqa: E402
import requests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from google.cloud.firestore import SERVER_TIMESTAMP  # noqa: E402

from core import firebase as core_firebase  # noqa: E402
from services import account_access_service as access  # noqa: E402
from services import account_action_service as actions  # noqa: E402

USERS = "/api/admin/users"


class AccountActionEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = import_main().app  # emulator mode: registration and account actions are mounted
        cls.client = TestClient(cls.app)
        load_rules(EXPERIMENTAL_RULES)
        cls.admin = new_student()
        firebase_auth.set_custom_user_claims(cls.admin.uid, {"admin": True})
        cls.admin_token = tokens(cls.admin)[0]  # issued after the claim was set

    @classmethod
    def tearDownClass(cls):
        try:
            load_rules(PRODUCTION_RULES)
        finally:
            sys.modules.pop("main", None)

    def setUp(self):
        self.db = core_firebase.initialize_firebase()

    # ------------------------------------------------------------------ helpers
    def registered_student(self):
        body = registration_body()
        self.assertEqual(self.client.post(REGISTER_URL, json=body).status_code, 201)
        return SimpleNamespace(uid=firebase_auth.get_user_by_email(body["email"]).uid,
                               email=body["email"], password=body["password"])

    def token(self, student):
        response = sign_in(student)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["idToken"]

    def call(self, method, uid, action, token=None):
        headers = bearer(token or self.admin_token) if token is not False else {}
        return getattr(self.client, method)(f"{USERS}/{uid}/{action}", headers=headers)

    def read_profile(self, token, uid):
        return requests.get(f"{DOCUMENTS}/users/{uid}", headers=bearer(token), timeout=10).status_code

    def me(self, token):
        return self.client.get("/api/auth/me", headers=bearer(token)).status_code

    def record(self, uid):
        snapshot = self.db.collection("account_access").document(uid).get()
        return snapshot.to_dict() if snapshot.exists else None

    def lock(self, uid):
        snapshot = self.db.collection("account_operations").document(uid).get()
        return snapshot.to_dict() if snapshot.exists else None

    def audits(self, uid):
        rows = [doc.to_dict() for doc in self.db.collection("account_audit").stream()]
        return sorted((row for row in rows if row["targetUid"] == uid), key=lambda row: row["startedAt"])

    def disabled(self, uid):
        return firebase_auth.get_user(uid).disabled

    # -------------------------------------------------------------------- tests
    def test_01_disable_then_enable_end_to_end(self):
        student = self.registered_student()
        old_token = self.token(student)
        self.assertEqual(self.read_profile(old_token, student.uid), 200)

        state = self.call("get", student.uid, "access").json()
        self.assertEqual((state["state"], state["allowed_actions"]), ("active", ["disable", "delete"]))

        response = self.call("post", student.uid, "disable")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["account"]["state"], "disabled")
        self.assertEqual(self.record(student.uid), {"state": "disabled", "version": 2})
        self.assertTrue(self.disabled(student.uid))
        self.assertIsNone(self.lock(student.uid))
        self.assertEqual(self.read_profile(old_token, student.uid), 403, "earlier token, Firestore guard")
        self.assertEqual(self.me(old_token), 403, "earlier token, backend")
        self.assertEqual(error_message(sign_in(student)), "USER_DISABLED")

        response = self.call("post", student.uid, "enable")
        self.assertEqual(response.status_code, 200, response.text)
        record = self.record(student.uid)
        self.assertEqual((record["state"], record["version"], set(record)),
                         ("active", 4, {"state", "version", "sessionsValidAfter"}))
        self.assertFalse(self.disabled(student.uid))
        self.assertEqual(self.read_profile(old_token, student.uid), 403, "the old session stays blocked (threshold)")
        self.assertEqual(self.me(old_token), 401, "the old session stays blocked (revoked)")
        fresh = self.token(student)
        self.assertEqual(self.read_profile(fresh, student.uid), 200, "a fresh sign-in after enable works")
        self.assertEqual(self.me(fresh), 200)

        audits = self.audits(student.uid)
        self.assertEqual([(a["operation"], a["outcome"], a["actorUid"]) for a in audits],
                         [("disable", "completed", self.admin.uid), ("enable", "completed", self.admin.uid)])
        self.assertNotIn(student.email, repr(audits))

    def test_02_students_and_anonymous_callers_cannot_use_the_actions(self):
        student = self.registered_student()
        other = self.registered_student()
        student_token = self.token(student)
        for method, action in (("get", "access"), ("post", "disable"), ("post", "enable")):
            with self.subTest(action=action):
                self.assertEqual(self.call(method, other.uid, action, token=student_token).status_code, 403)
                self.assertEqual(self.call(method, other.uid, action, token=False).status_code, 401)
        self.assertEqual(self.call("post", student.uid, "disable", token=student_token).status_code, 403)
        self.assertEqual(self.record(other.uid), {"state": "active", "version": 1})
        self.assertFalse(self.disabled(other.uid))

    def test_03_the_caller_and_other_administrators_are_refused(self):
        response = self.call("post", self.admin.uid, "disable")
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (403, "SELF_ACTION_FORBIDDEN"))
        other_admin = new_student()
        firebase_auth.set_custom_user_claims(other_admin.uid, {"admin": True})
        for action in ("disable", "enable"):
            response = self.call("post", other_admin.uid, action)
            self.assertEqual((response.status_code, response.json()["detail"]["code"]), (403, "ADMIN_TARGET_FORBIDDEN"))
        self.assertEqual(self.call("get", other_admin.uid, "access").json()["state"], "protected")
        self.assertFalse(self.disabled(other_admin.uid))
        self.assertFalse(self.disabled(self.admin.uid))

    def test_04_missing_malformed_and_deletion_records_are_refused(self):
        no_record = new_student()  # the old browser registration: no access record
        malformed = self.registered_student()
        self.db.collection("account_access").document(malformed.uid).update({"updatedAt": SERVER_TIMESTAMP})
        deleting = self.registered_student()
        self.db.collection("account_access").document(deleting.uid).update({"state": "deleting", "version": 2})
        for uid, code in ((no_record.uid, "ACCESS_RECORD_UNSUPPORTED"), (malformed.uid, "ACCESS_RECORD_UNSUPPORTED"),
                          (deleting.uid, "ACCOUNT_DELETION_IN_PROGRESS")):  # M3B-3: only Delete continues a deletion
            for action in ("disable", "enable"):
                with self.subTest(uid=uid, action=action):
                    response = self.call("post", uid, action)
                    self.assertEqual((response.status_code, response.json()["detail"]["code"]), (409, code))
            self.assertFalse(self.disabled(uid))
        self.assertIsNone(self.record(no_record.uid), "no record is created")
        self.assertIn("updatedAt", self.record(malformed.uid), "a malformed record is not repaired")
        self.assertEqual(self.record(deleting.uid)["state"], "deleting", "never reactivated")

    def test_05_concurrent_disable_requests_change_the_account_once(self):
        student = self.registered_student()
        workers = 6
        barrier = threading.Barrier(workers)
        outcomes = []

        def attempt():
            barrier.wait()
            try:
                outcomes.append(actions.disable_account(student.uid, self.admin.uid).view.state)
            except actions.AccountActionError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("disabled"), 1, outcomes)
        self.assertTrue(set(outcomes) <= {"disabled", "OPERATION_IN_PROGRESS", "ALREADY_DISABLED"}, outcomes)
        self.assertEqual(self.record(student.uid), {"state": "disabled", "version": 2})
        self.assertEqual([a["outcome"] for a in self.audits(student.uid)], ["completed"])
        self.assertIsNone(self.lock(student.uid))

    def test_06_a_partial_disable_is_recorded_blocks_firestore_and_can_be_resumed(self):
        student = self.registered_student()
        token = self.token(student)
        with mock.patch("services.account_action_service.firebase_auth.update_user",
                        side_effect=firebase_exceptions.UnavailableError("Auth down")):
            response = self.call("post", student.uid, "disable")
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual((detail["code"], detail["failed_step"], detail["reason"]),
                         ("OPERATION_INCOMPLETE", "disable_auth", "AUTH_UNAVAILABLE"))
        self.assertEqual(self.record(student.uid), {"state": "disabled", "version": 2})
        self.assertFalse(self.disabled(student.uid))
        self.assertEqual(self.read_profile(token, student.uid), 403, "Firestore is already closed (fail closed)")
        self.assertEqual(self.me(token), 200, "the backend follows Auth, which is still enabled (JL1)")
        self.assertEqual(self.lock(student.uid)["status"], "incomplete")
        [audit] = self.audits(student.uid)
        self.assertEqual((audit["outcome"], audit["failedStep"]), ("incomplete", "disable_auth"))

        state = self.call("get", student.uid, "access").json()
        self.assertEqual((state["state"], state["allowed_actions"], state["operation"]["failed_step"]),
                         ("incomplete", ["disable"], "disable_auth"))
        response = self.call("post", student.uid, "enable")
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (409, "INCOMPLETE_OPERATION_PENDING"))

        response = self.call("post", student.uid, "disable")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["resumed_operation_id"], detail["operation_id"])
        self.assertTrue(self.disabled(student.uid))
        self.assertIsNone(self.lock(student.uid))
        self.assertEqual([a["outcome"] for a in self.audits(student.uid)], ["incomplete", "completed"])

    def test_07_a_partial_enable_never_opens_firestore_early_and_old_sessions_stay_blocked(self):
        student = self.registered_student()
        self.assertEqual(self.call("post", student.uid, "disable").status_code, 200)

        # 1. Auth cannot be enabled: the record keeps 'disabled' (with a threshold), Auth stays disabled.
        original_update = firebase_auth.update_user

        def refuse_enable(uid, **kwargs):
            if kwargs.get("disabled") is False:
                raise firebase_exceptions.UnavailableError("Auth down")
            return original_update(uid, **kwargs)

        with mock.patch("services.account_action_service.firebase_auth.update_user", side_effect=refuse_enable):
            response = self.call("post", student.uid, "enable")
        self.assertEqual((response.status_code, response.json()["detail"]["failed_step"]), (503, "enable_auth"))
        record = self.record(student.uid)
        self.assertEqual((record["state"], "sessionsValidAfter" in record), ("disabled", True))
        self.assertTrue(self.disabled(student.uid))
        self.assertEqual(self.call("get", student.uid, "access").json()["allowed_actions"], ["enable", "disable"])

        # 2. The record cannot be activated: Auth is enabled but Firestore stays closed.
        original_change = access.change_record_state

        def refuse_activation(uid, snapshot, *, state, set_threshold=False):
            if state == "active":
                raise access.AccountAccessError(access.STORE_UNAVAILABLE)
            return original_change(uid, snapshot, state=state, set_threshold=set_threshold)

        with mock.patch("services.account_access_service.change_record_state", side_effect=refuse_activation):
            response = self.call("post", student.uid, "enable")
        self.assertEqual((response.status_code, response.json()["detail"]["failed_step"]), (503, "activate_record"))
        self.assertFalse(self.disabled(student.uid))
        self.assertEqual(self.record(student.uid)["state"], "disabled")
        early_token = self.token(student)
        self.assertEqual(self.read_profile(early_token, student.uid), 403, "Firestore stays closed until activation")

        # 3. Resumed: completes; the session from step 2 is blocked; a fresh sign-in works.
        response = self.call("post", student.uid, "enable")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.record(student.uid)["state"], "active")
        self.assertEqual(self.read_profile(early_token, student.uid), 403, "a session from before the resume")
        self.assertEqual(self.me(early_token), 401)
        fresh = self.token(student)
        self.assertEqual(self.read_profile(fresh, student.uid), 200)
        self.assertEqual([(a["operation"], a["outcome"]) for a in self.audits(student.uid)],
                         [("disable", "completed"), ("enable", "incomplete"), ("enable", "incomplete"),
                          ("enable", "completed")])

    def test_08_reconciliation_only_downgrades(self):
        # Auth disabled outside the app (as in the Firebase console): Disable completes it by downgrading.
        student = self.registered_student()
        firebase_auth.update_user(student.uid, disabled=True)
        state = self.call("get", student.uid, "access").json()
        self.assertEqual((state["state"], state["issues"]), ("inconsistent", ["AUTH_DISABLED_RECORD_ACTIVE"]))
        self.assertEqual(self.call("post", student.uid, "disable").status_code, 200)
        self.assertEqual(self.record(student.uid), {"state": "disabled", "version": 2})

        # Auth account deleted outside the app: the service function downgrades the record once.
        gone = self.registered_student()
        firebase_auth.delete_user(gone.uid)
        self.assertTrue(access.reconcile_access_record(gone.uid).downgraded)
        self.assertEqual(self.record(gone.uid), {"state": "disabled", "version": 2})
        self.assertFalse(access.reconcile_access_record(gone.uid).downgraded)

        # Never upgrades: Auth enabled with a disabled record is left alone.
        blocked = self.registered_student()
        self.db.collection("account_access").document(blocked.uid).update({"state": "disabled", "version": 2})
        self.assertFalse(access.reconcile_access_record(blocked.uid).downgraded)
        self.assertEqual(self.record(blocked.uid), {"state": "disabled", "version": 2})

    def test_09_production_mode_has_no_account_action_routes(self):
        student = self.registered_student()
        with mock.patch.dict(os.environ, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}):
            production_app = import_main().app
            paths = [path for path in production_app.openapi()["paths"] if path.startswith(USERS)]
            client = TestClient(production_app)
            responses = [client.post(f"{USERS}/{student.uid}/{action}", headers=bearer(self.admin_token))
                         for action in ("disable", "enable")]
            responses.append(client.get(f"{USERS}/{student.uid}/access", headers=bearer(self.admin_token)))
        sys.modules.pop("main", None)
        self.assertEqual(sorted(paths), [USERS, f"{USERS}/{{uid}}"], "only the read-only M3A routes")
        self.assertEqual([response.status_code for response in responses], [404, 404, 404])
        self.assertEqual(self.record(student.uid), {"state": "active", "version": 1})
        self.assertFalse(self.disabled(student.uid))

    def test_10_only_the_emulators_are_used(self):
        app = firebase_admin.get_app()
        self.assertIsInstance(app.credential, core_firebase.EmulatorCredential)
        self.assertEqual(app.project_id, PROJECT_ID)
        self.assertNotEqual(app.project_id, PRODUCTION_PROJECT_ID)
        self.assertTrue(HTTP_HOSTS)
        self.assertTrue(all(core_firebase.is_loopback_host_port(host) for host in HTTP_HOSTS), HTTP_HOSTS)


if __name__ == "__main__":
    unittest.main()
