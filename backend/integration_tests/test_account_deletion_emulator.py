# backend/integration_tests/test_account_deletion_emulator.py
"""
M3B-3: admin Delete Student Account through the real backend application (main.app), against the LOCAL
Firebase Authentication and Firestore emulators (project demo-route2unikl).

Run with the other emulator integration tests, from the backend directory:
    firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\\Scripts\\python.exe -m unittest discover -s integration_tests -t . -v"

Uses the module set-up and teardown of test_auth_emulator.py (loopback emulator hosts, a demo- project,
emulator mode for this process only, a service-account loader that fails if called, every HTTP request
recorded, both emulators wiped before and after). The experimental account-access rules are loaded into
the running Firestore emulator for this module (test_00 proves they are the rules in force) and the
production rules restored afterwards.

Students are registered through the trusted registration route (Auth account, access record and
users/{uid}); their results/{uid} and ai_assessments/{uid} documents are written with the Admin SDK.
Students use Firestore through the REST API with their own ID tokens, as the browser does. Whether data
remains is checked independently of the service code, through the emulator's REST API with its
administrative "owner" credential. No AI provider is called: the assessment handlers' AI and
recommendation functions are replaced by stubs wherever a request could reach them.
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
    HTTP_HOSTS, PRODUCTION_PROJECT_ID, PROJECT_ID, bearer, error_message, new_student, refresh, setUpModule,
    sign_in, tearDownModule)
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
INCOMPLETE = "/api/admin/account-operations/incomplete-deletions"
STUDENT_DATA = ("users", "results", "ai_assessments")
OWNER = {"Authorization": "Bearer owner"}  # the Firestore emulator's administrative credential (emulator only)


class AccountDeletionEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = import_main().app  # emulator mode: registration and account actions are mounted
        cls.client = TestClient(cls.app)
        load_rules(EXPERIMENTAL_RULES)
        cls.admin = new_student()
        firebase_auth.set_custom_user_claims(cls.admin.uid, {"admin": True})
        response = sign_in(cls.admin)  # issued after the claim was set
        assert response.status_code == 200, response.text
        cls.admin_token = response.json()["idToken"]

    @classmethod
    def tearDownClass(cls):
        try:
            load_rules(PRODUCTION_RULES)
        finally:
            sys.modules.pop("main", None)

    def setUp(self):
        self.db = core_firebase.initialize_firebase()
        # No AI provider and no recommendation run in this module: a request that reaches a handler gets a stub.
        self.ai = mock.AsyncMock(return_value={"questions": [], "source": "stub", "model_used": "none"})
        self.recommend = mock.Mock(return_value=[])
        for target, replacement in (("routes.assessment.generate_rag_assessment", self.ai),
                                    ("routes.assessment.calculate_program_recommendations", self.recommend)):
            patcher = mock.patch(target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    # ------------------------------------------------------------------ helpers
    def registered_student(self, with_records=True):
        body = registration_body()
        self.assertEqual(self.client.post(REGISTER_URL, json=body).status_code, 201)
        student = SimpleNamespace(uid=firebase_auth.get_user_by_email(body["email"]).uid,
                                  email=body["email"], password=body["password"])
        if with_records:
            self.db.collection("results").document(student.uid).set(
                {"results": [{"subject": "Mathematics", "grade": "A"}], "status": "submitted"})
            self.db.collection("ai_assessments").document(student.uid).set(
                {"answers": [{"questionId": 1, "isCorrect": True}], "score": 100})
        return student

    def session(self, student):
        response = sign_in(student)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["idToken"], response.json()["refreshToken"]

    def delete(self, uid, body=None, token=None):
        headers = bearer(token or self.admin_token) if token is not False else {}
        return self.client.post(f"{USERS}/{uid}/delete", headers=headers,
                                json={"confirm_uid": uid} if body is None else body)

    def access_state(self, uid):
        return self.client.get(f"{USERS}/{uid}/access", headers=bearer(self.admin_token)).json()

    def incomplete(self, token=None):
        return self.client.get(INCOMPLETE, headers=bearer(token or self.admin_token))

    def remaining(self, uid):
        """Which student documents exist, read through the emulator's REST API (not the service code)."""
        result = {}
        for name in STUDENT_DATA:
            status_code = requests.get(f"{DOCUMENTS}/{name}/{uid}", headers=OWNER, timeout=10).status_code
            self.assertIn(status_code, (200, 404))
            result[name] = status_code == 200
        return result

    def student_request(self, token, method, collection, uid):
        """As the browser SDK would, with the student's own ID token: get, post (create) or patch (update)."""
        url = {"get": f"{DOCUMENTS}/{collection}/{uid}",
               "post": f"{DOCUMENTS}/{collection}?documentId={uid}",
               "patch": f"{DOCUMENTS}/{collection}/{uid}?updateMask.fieldPaths=name"}[method]
        body = None if method == "get" else {"fields": {"name": {"stringValue": "Changed"}}}
        return requests.request(method.upper(), url, json=body, headers=bearer(token), timeout=10).status_code

    def assessment(self, token, path):
        return self.client.post(f"/api/assessment/{path}", headers=bearer(token),
                                json={"interests": ["engineering"],
                                      "grades": [{"subject": "Mathematics", "grade": "A"}], "assessmentScore": 50})

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

    def auth_exists(self, uid):
        try:
            firebase_auth.get_user(uid)
            return True
        except firebase_auth.UserNotFoundError:
            return False

    def assert_incomplete(self, response, failed_step, reason):
        self.assertEqual(response.status_code, 503, response.text)
        detail = response.json()["detail"]
        self.assertEqual((detail["code"], detail["operation"], detail["failed_step"], detail["reason"]),
                         ("OPERATION_INCOMPLETE", "delete", failed_step, reason))
        return detail

    def assert_deleted(self, student, version):
        self.assertFalse(self.auth_exists(student.uid), "Firebase Authentication account deleted")
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, False), "every student document gone")
        self.assertEqual(self.record(student.uid), {"state": "deleted", "version": version}, "minimal tombstone")
        self.assertIsNone(self.lock(student.uid))
        self.assertEqual(error_message(sign_in(student)), "EMAIL_NOT_FOUND")

    # -------------------------------------------------------------------- tests
    def test_00_the_experimental_rules_are_the_rules_in_force(self):
        # Canary: production rules would let a student read their own profile whatever the access record says.
        student = self.registered_student(with_records=False)
        token, _ = self.session(student)
        self.assertEqual(self.student_request(token, "get", "users", student.uid), 200, "active record")
        self.db.collection("account_access").document(student.uid).update({"state": "disabled", "version": 2})
        self.assertEqual(self.student_request(token, "get", "users", student.uid), 403,
                         "a non-active record denies access: the account-access guard is loaded")
        self.assertEqual(self.student_request(token, "get", "account_access", student.uid), 403)

    def test_01_an_active_student_is_deleted_completely(self):
        student = self.registered_student()
        id_token, refresh_token = self.session(student)
        self.assertEqual(self.student_request(id_token, "get", "results", student.uid), 200)
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, True))
        state = self.access_state(student.uid)
        self.assertEqual((state["state"], state["allowed_actions"]), ("active", ["disable", "delete"]))

        response = self.delete(student.uid)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["outcome"], body["operation"], body["account"]["state"], body["account"]["auth_status"]),
                         ("completed", "delete", "deleted", "missing"))
        self.assertNotIn(student.email, response.text)
        self.assert_deleted(student, version=4)

        # The session from before the deletion: Firestore, the backend and token refresh all refuse it.
        for collection in STUDENT_DATA:
            with self.subTest(collection=collection):
                self.assertEqual(self.student_request(id_token, "get", collection, student.uid), 403)
                self.assertEqual(self.student_request(id_token, "post", collection, student.uid), 403, "no recreation")
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, False))
        self.assertEqual(self.me(id_token), 401)
        self.assertEqual(self.assessment(id_token, "recommend").status_code, 401)
        self.assertNotEqual(refresh(refresh_token).status_code, 200, "the refresh token no longer works")
        self.ai.assert_not_called()
        self.recommend.assert_not_called()

        # Admin views: gone from Manage Users (Auth-based); the access state reports the deletion.
        listed = self.client.get(USERS, params={"search": student.email}, headers=bearer(self.admin_token))
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"], [])
        self.assertEqual(self.client.get(f"{USERS}/{student.uid}", headers=bearer(self.admin_token)).status_code, 404)
        self.assertEqual((self.access_state(student.uid)["state"], self.access_state(student.uid)["allowed_actions"]),
                         ("deleted", []))
        again = self.delete(student.uid)
        self.assertEqual((again.status_code, again.json()["detail"]["code"]), (409, "ACCOUNT_DELETED"))

        [audit] = self.audits(student.uid)
        self.assertEqual((audit["operation"], audit["outcome"], audit["actorUid"]), ("delete", "completed", self.admin.uid))
        self.assertEqual((audit["dataPresentBefore"], audit["dataPresentAfter"]),
                         (dict.fromkeys(STUDENT_DATA, True), dict.fromkeys(STUDENT_DATA, False)))
        self.assertNotIn(student.email, repr(audit))
        self.assertNotIn("Mathematics", repr(audit), "no academic content retained")

        # The same email can register again, as a new account; the tombstone is untouched.
        self.assertEqual(self.client.post(REGISTER_URL, json=registration_body(email=student.email)).status_code, 201)
        self.assertNotEqual(firebase_auth.get_user_by_email(student.email).uid, student.uid)
        self.assertEqual(self.record(student.uid), {"state": "deleted", "version": 4})

    def test_02_a_disabled_student_is_deleted(self):
        student = self.registered_student()
        self.assertEqual(self.client.post(f"{USERS}/{student.uid}/disable", headers=bearer(self.admin_token)).status_code, 200)
        self.assertEqual(self.access_state(student.uid)["allowed_actions"], ["enable", "delete"])
        response = self.delete(student.uid)
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_deleted(student, version=5)
        self.assertEqual([(a["operation"], a["outcome"]) for a in self.audits(student.uid)],
                         [("disable", "completed"), ("delete", "completed")])

    def test_03_only_administrators_with_a_matching_confirmation(self):
        student = self.registered_student()
        other = self.registered_student()
        student_token, _ = self.session(student)
        self.assertEqual(self.delete(other.uid, token=student_token).status_code, 403)
        self.assertEqual(self.delete(student.uid, token=student_token).status_code, 403, "not even one's own account")
        self.assertEqual(self.delete(other.uid, token=False).status_code, 401)
        self.assertEqual(self.incomplete(token=student_token).status_code, 403)
        for body in ({"confirm_uid": student.uid}, {}, {"confirm_uid": other.uid, "force": True}):
            with self.subTest(body=body):
                self.assertEqual(self.delete(other.uid, body=body).status_code, 422)
        mismatch = self.delete(other.uid, body={"confirm_uid": student.uid})
        self.assertEqual(mismatch.json()["detail"]["code"], "DELETE_CONFIRMATION_MISMATCH")
        for account in (student, other):
            self.assertTrue(self.auth_exists(account.uid))
            self.assertEqual(self.remaining(account.uid), dict.fromkeys(STUDENT_DATA, True))
            self.assertEqual(self.record(account.uid), {"state": "active", "version": 1})
        self.assertEqual(self.audits(other.uid), [])

    def test_04_administrators_are_never_deleted_even_if_promoted_during_the_deletion(self):
        response = self.delete(self.admin.uid)
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (403, "SELF_ACTION_FORBIDDEN"))
        other_admin = self.registered_student()
        firebase_auth.set_custom_user_claims(other_admin.uid, {"admin": True})
        response = self.delete(other_admin.uid)
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (403, "ADMIN_TARGET_FORBIDDEN"))
        self.assertTrue(self.auth_exists(other_admin.uid))
        self.assertEqual(self.remaining(other_admin.uid), dict.fromkeys(STUDENT_DATA, True))

        # 1. The claim is granted elsewhere after the deletion started, before the data is deleted.
        promoted = self.registered_student()
        original_update = firebase_auth.update_user

        def disable_then_promote(uid, **kwargs):
            result = original_update(uid, **kwargs)
            firebase_auth.set_custom_user_claims(uid, {"admin": True})
            return result

        with mock.patch("services.account_action_service.firebase_auth.update_user", side_effect=disable_then_promote):
            self.assert_incomplete(self.delete(promoted.uid), "check_admin_before_data_deletion", "ADMIN_TARGET")
        self.assertEqual(self.remaining(promoted.uid), dict.fromkeys(STUDENT_DATA, True), "data kept")
        self.assertTrue(self.auth_exists(promoted.uid), "Auth account kept")
        self.assertEqual(self.access_state(promoted.uid)["state"], "protected")
        response = self.delete(promoted.uid)
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (403, "ADMIN_TARGET_FORBIDDEN"))
        self.assertEqual([a["outcome"] for a in self.audits(promoted.uid)], ["incomplete"], "never reported as success")

        # 2. The claim is granted after the data deletion, before the Auth deletion.
        late = self.registered_student()
        original_delete = access.delete_documents_during_deletion

        def delete_then_promote(uid, snapshot, collections):
            change = original_delete(uid, snapshot, collections)
            firebase_auth.set_custom_user_claims(uid, {"admin": True})
            return change

        with mock.patch("services.account_access_service.delete_documents_during_deletion", side_effect=delete_then_promote):
            self.assert_incomplete(self.delete(late.uid), "check_admin_before_auth_deletion", "ADMIN_TARGET")
        self.assertTrue(self.auth_exists(late.uid), "the Auth account of an administrator is never deleted")
        self.assertTrue(firebase_auth.get_user(late.uid).disabled)
        listed = [item["uid"] for item in self.incomplete().json()["items"]]
        self.assertIn(late.uid, listed, "reported for administrator review")

    def test_05_accounts_without_a_usable_record_or_in_an_unclear_state_are_refused(self):
        no_record = new_student()  # the old browser registration: no access record
        malformed = self.registered_student()
        self.db.collection("account_access").document(malformed.uid).update({"updatedAt": SERVER_TIMESTAMP})
        inconsistent = self.registered_student()
        firebase_auth.update_user(inconsistent.uid, disabled=True)  # Auth changed outside the app
        for account, code in ((no_record, "ACCESS_RECORD_UNSUPPORTED"), (malformed, "ACCESS_RECORD_UNSUPPORTED"),
                              (inconsistent, "DELETE_NOT_ALLOWED")):
            with self.subTest(code=code):
                response = self.delete(account.uid)
                self.assertEqual((response.status_code, response.json()["detail"]["code"]), (409, code))
                self.assertTrue(self.auth_exists(account.uid))
        self.assertIsNone(self.record(no_record.uid), "no record is created")
        self.assertIn("updatedAt", self.record(malformed.uid), "a malformed record is not repaired")
        self.assertEqual(self.remaining(malformed.uid), dict.fromkeys(STUDENT_DATA, True))
        self.assertEqual(self.remaining(inconsistent.uid), dict.fromkeys(STUDENT_DATA, True))
        response = self.delete("no-such-account")
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (404, "USER_NOT_FOUND"))

    def test_06_an_account_being_deleted_is_refused_everywhere_even_with_auth_still_enabled(self):
        student = self.registered_student()
        id_token, _ = self.session(student)
        with mock.patch("services.account_action_service.firebase_auth.update_user",
                        side_effect=firebase_exceptions.UnavailableError("Auth down")):
            first = self.assert_incomplete(self.delete(student.uid), "disable_auth", "AUTH_UNAVAILABLE")
        self.assertFalse(firebase_auth.get_user(student.uid).disabled, "Auth is still enabled")
        self.assertEqual(self.record(student.uid)["state"], "deleting")
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, True))

        # JL1 closed for deletion: the backend's student-data endpoints refuse the still-valid token.
        for path in ("recommend", "generate-questions"):
            with self.subTest(path=path):
                response = self.assessment(id_token, path)
                self.assertEqual((response.status_code, response.json()["detail"]["code"]), (403, "ACCOUNT_DELETED"))
        self.ai.assert_not_called()
        self.recommend.assert_not_called()
        self.assertEqual(self.student_request(id_token, "get", "users", student.uid), 403, "Firestore guard")
        self.assertEqual(self.student_request(id_token, "patch", "users", student.uid), 403, "no update either")

        state = self.access_state(student.uid)
        self.assertEqual((state["state"], state["allowed_actions"], state["operation"]["failed_step"]),
                         ("deletion_incomplete", ["delete"], "disable_auth"))
        for action in ("disable", "enable"):
            response = self.client.post(f"{USERS}/{student.uid}/{action}", headers=bearer(self.admin_token))
            self.assertEqual((response.status_code, response.json()["detail"]["code"]),
                             (409, "ACCOUNT_DELETION_IN_PROGRESS"), "a deletion is never undone")

        response = self.delete(student.uid)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["resumed_operation_id"], first["operation_id"])
        self.assert_deleted(student, version=4)
        self.assertEqual([a["outcome"] for a in self.audits(student.uid)], ["incomplete", "completed"])

    def test_07_the_data_deletion_is_atomic_in_firestore(self):
        student = self.registered_student()
        original_delete = access.delete_documents_during_deletion

        def change_record_first(uid, snapshot, collections):
            # Another writer changes the record between the read and the batch: the batch's precondition fails.
            self.db.collection("account_access").document(uid).update({"version": snapshot.lookup.record.version + 7})
            return original_delete(uid, snapshot, collections)

        with mock.patch("services.account_access_service.delete_documents_during_deletion", side_effect=change_record_first):
            self.assert_incomplete(self.delete(student.uid), "delete_student_data", "RECORD_CHANGED")
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, True), "nothing deleted")
        self.assertTrue(self.auth_exists(student.uid))
        self.assertEqual(self.delete(student.uid).status_code, 200)
        self.assert_deleted(student, version=11)

    def test_08_auth_deletion_failures_are_resumable(self):
        student = self.registered_student()
        with mock.patch("services.account_action_service.firebase_auth.delete_user",
                        side_effect=firebase_exceptions.UnavailableError("Auth down")):
            self.assert_incomplete(self.delete(student.uid), "delete_auth", "AUTH_UNAVAILABLE")
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, False), "data already removed")
        self.assertTrue(self.auth_exists(student.uid))
        self.assertTrue(firebase_auth.get_user(student.uid).disabled, "no sign-in meanwhile")
        self.assertEqual(error_message(sign_in(student)), "USER_DISABLED")
        self.assertEqual(self.delete(student.uid).status_code, 200)
        self.assert_deleted(student, version=4)

    def test_09_auth_deleted_but_record_not_finalised_is_found_and_resumed(self):
        student = self.registered_student()
        original_change = access.change_record_state

        def refuse_tombstone(uid, snapshot, *, state, set_threshold=False):
            if state == "deleted":
                raise access.AccountAccessError(access.STORE_UNAVAILABLE)
            return original_change(uid, snapshot, state=state, set_threshold=set_threshold)

        with mock.patch("services.account_access_service.change_record_state", side_effect=refuse_tombstone):
            first = self.assert_incomplete(self.delete(student.uid), "finalize_record", "STORE_UNAVAILABLE")
        self.assertFalse(self.auth_exists(student.uid))
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, False))
        self.assertEqual(self.record(student.uid)["state"], "deleting")

        # No longer in the Auth-based Manage Users views, but listed for recovery.
        self.assertEqual(self.client.get(f"{USERS}/{student.uid}", headers=bearer(self.admin_token)).status_code, 404)
        items = {item["uid"]: item for item in self.incomplete().json()["items"]}
        self.assertIn(student.uid, items)
        item = items[student.uid]
        self.assertEqual((item["state"], item["auth_status"], item["allowed_actions"], item["operation"]["failed_step"]),
                         ("deletion_incomplete", "missing", ["delete"], "finalize_record"))
        self.assertNotIn(student.email, self.incomplete().text)

        response = self.delete(student.uid)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["resumed_operation_id"], first["operation_id"])
        self.assert_deleted(student, version=4)
        self.assertNotIn(student.uid, [item["uid"] for item in self.incomplete().json()["items"]])

    def test_10_concurrent_deletions_delete_once(self):
        student = self.registered_student()
        workers = 6
        barrier = threading.Barrier(workers)
        outcomes = []

        def attempt():
            barrier.wait()
            try:
                outcomes.append(actions.delete_account(student.uid, self.admin.uid, student.uid).view.state)
            except actions.AccountActionError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("deleted"), 1, outcomes)
        self.assertTrue(set(outcomes) <= {"deleted", "OPERATION_IN_PROGRESS", "ACCOUNT_DELETED"}, outcomes)
        self.assert_deleted(student, version=4)
        self.assertEqual([a["outcome"] for a in self.audits(student.uid)], ["completed"])

    def test_11_active_and_disabled_records_reach_the_assessment_handlers_unchanged(self):
        student = self.registered_student()
        id_token, _ = self.session(student)
        self.assertEqual(self.assessment(id_token, "generate-questions").status_code, 200)
        self.assertEqual(self.assessment(id_token, "recommend").status_code, 200)
        self.assertEqual((self.ai.await_count, self.recommend.call_count), (1, 1), "stubs only, no provider")
        legacy = new_student()  # no access record (registered before the records existed)
        response = sign_in(legacy)
        self.assertEqual(self.assessment(response.json()["idToken"], "generate-questions").status_code, 200)

    def test_12_production_mode_has_no_deletion_routes(self):
        student = self.registered_student()
        with mock.patch.dict(os.environ, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}):
            production_app = import_main().app
            paths = sorted(production_app.openapi()["paths"])
            client = TestClient(production_app)
            responses = [client.post(f"{USERS}/{student.uid}/delete", json={"confirm_uid": student.uid},
                                     headers=bearer(self.admin_token)),
                         client.get(INCOMPLETE, headers=bearer(self.admin_token))]
        sys.modules.pop("main", None)
        self.assertFalse([path for path in paths if path.endswith("/delete") or "account-operations" in path], paths)
        self.assertEqual([response.status_code for response in responses], [404, 404])
        self.assertTrue(self.auth_exists(student.uid))
        self.assertEqual(self.record(student.uid), {"state": "active", "version": 1})
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, True))

    def test_13_only_the_emulators_are_used(self):
        app = firebase_admin.get_app()
        self.assertIsInstance(app.credential, core_firebase.EmulatorCredential)
        self.assertEqual(app.project_id, PROJECT_ID)
        self.assertNotEqual(app.project_id, PRODUCTION_PROJECT_ID)
        self.assertTrue(HTTP_HOSTS)
        self.assertTrue(all(core_firebase.is_loopback_host_port(host) for host in HTTP_HOSTS), HTTP_HOSTS)


if __name__ == "__main__":
    unittest.main()
