# backend/integration_tests/test_account_lifecycle_emulator.py
"""
M3C: Account Lifecycle Security Hardening through the real backend application (main.app), against the LOCAL
Firebase Authentication and Firestore emulators (project demo-route2unikl).

Run with the other emulator integration tests, from the backend directory:
    firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\\Scripts\\python.exe -m unittest discover -s integration_tests -t . -v"

Uses the module set-up and teardown of test_auth_emulator.py (loopback emulator hosts, a demo- project,
emulator mode for this process only, a service-account loader that fails if called, every HTTP request
recorded, both emulators wiped before and after). The experimental account-access rules are loaded into
the running Firestore emulator for this module and the production rules restored afterwards.

Covers: strict student-data enforcement with real emulator tokens (auth_time from the Auth emulator),
old sessions after Enable (including a refreshed earlier session, audit finding M3), missing and malformed
records, Disable/Enable lock hardening and concurrency, stale Enable, and the student self-service
deletion (recent sign-in, own account only, recovery). No AI provider is called: the assessment handlers'
AI and recommendation functions are replaced by stubs.
"""
import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
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
from services import account_action_service as actions  # noqa: E402

USERS = "/api/admin/users"
SELF_DELETE = "/api/account/delete"
INCOMPLETE = "/api/admin/account-operations/incomplete-deletions"
STUDENT_DATA = ("users", "results", "ai_assessments")
OWNER = {"Authorization": "Bearer owner"}  # the Firestore emulator's administrative credential (emulator only)


class AccountLifecycleEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = import_main().app  # emulator mode: registration, account actions and self-deletion are mounted
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
            self.db.collection("results").document(student.uid).set({"results": [{"subject": "Mathematics", "grade": "A"}]})
            self.db.collection("ai_assessments").document(student.uid).set({"answers": [{"isCorrect": True}]})
        return student

    def session(self, student):
        response = sign_in(student)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["idToken"], response.json()["refreshToken"]

    def admin_call(self, method, uid, action, body=None):
        return getattr(self.client, method)(f"{USERS}/{uid}/{action}", headers=bearer(self.admin_token),
                                            **({"json": body} if body is not None else {}))

    def assessment(self, token, path="generate-questions"):
        return self.client.post(f"/api/assessment/{path}", headers=bearer(token),
                                json={"interests": ["engineering"], "grades": [{"subject": "Mathematics", "grade": "A"}],
                                      "assessmentScore": 50})

    def self_delete(self, token, confirm_uid):
        return self.client.post(SELF_DELETE, headers=bearer(token), json={"confirm_uid": confirm_uid})

    def browser(self, token, method, collection, uid):
        return requests.request(method, f"{DOCUMENTS}/{collection}/{uid}", headers=bearer(token), timeout=10).status_code

    def remaining(self, uid):
        result = {}
        for name in STUDENT_DATA:
            status_code = requests.get(f"{DOCUMENTS}/{name}/{uid}", headers=OWNER, timeout=10).status_code
            self.assertIn(status_code, (200, 404))
            result[name] = status_code == 200
        return result

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

    def code(self, response):
        return response.status_code, response.json()["detail"]["code"]

    # ------------------------------------------------------------- strict student-data access
    def test_01_only_an_active_record_reaches_the_student_data_endpoints(self):
        student = self.registered_student()
        token, _ = self.session(student)
        for path in ("generate-questions", "recommend"):
            self.assertEqual(self.assessment(token, path).status_code, 200, path)

        legacy = new_student()  # no access record
        self.assertEqual(self.code(self.assessment(self.session(legacy)[0])), (403, "ACCOUNT_ACCESS_DENIED"))

        malformed = self.registered_student(with_records=False)
        self.db.collection("account_access").document(malformed.uid).update({"updatedAt": SERVER_TIMESTAMP})
        self.assertEqual(self.code(self.assessment(self.session(malformed)[0])), (403, "ACCOUNT_ACCESS_DENIED"))

        # A disabled record with Auth still enabled (a Disable that stopped before disable_auth, KL1/JL1):
        # Firestore and, since M3C, the backend's student-data endpoints are both closed.
        partial = self.registered_student(with_records=False)
        partial_token, _ = self.session(partial)
        with mock.patch("services.account_action_service.firebase_auth.update_user",
                        side_effect=firebase_exceptions.UnavailableError("Auth down")):
            self.assertEqual(self.admin_call("post", partial.uid, "disable").status_code, 503)
        self.assertFalse(firebase_auth.get_user(partial.uid).disabled)
        self.assertEqual(self.record(partial.uid)["state"], "disabled")
        for path in ("generate-questions", "recommend"):
            self.assertEqual(self.code(self.assessment(partial_token, path)), (403, "ACCOUNT_ACCESS_DENIED"), path)
        self.assertEqual(self.browser(partial_token, "GET", "users", partial.uid), 403, "guard agrees")
        self.assertEqual((self.ai.await_count, self.recommend.call_count), (1, 1), "only the active student reached them")

    def test_02_old_sessions_stay_blocked_after_enable_including_a_refreshed_one(self):
        student = self.registered_student()
        old_token, old_refresh = self.session(student)
        self.assertEqual(self.assessment(old_token).status_code, 200)
        self.assertEqual(self.admin_call("post", student.uid, "disable").status_code, 200)
        self.assertEqual(self.admin_call("post", student.uid, "enable").status_code, 200)

        # The old ID token itself is revoked (backend) and below the threshold (guard).
        self.assertEqual(self.assessment(old_token).status_code, 401)
        self.assertEqual(self.browser(old_token, "GET", "users", student.uid), 403)
        # Audit finding M3: the Auth emulator exchanges the old refresh token after Enable (observed in the M3B-2
        # audit; asserted here so this test cannot pass without exercising it). The new ID token keeps the old
        # auth_time, so the student-data endpoints refuse it (401 SESSION_TOO_OLD), like the guard. /api/auth/me
        # (identity only, no student data) still accepts it: M3 remains open for that endpoint.
        refreshed = refresh(old_refresh)
        self.assertEqual(refreshed.status_code, 200, "emulator behaviour changed: review finding M3")
        refreshed_token = refreshed.json()["id_token"]
        self.assertEqual(self.code(self.assessment(refreshed_token)), (401, "SESSION_TOO_OLD"))
        self.assertEqual(self.code(self.assessment(refreshed_token, "recommend")), (401, "SESSION_TOO_OLD"))
        self.assertEqual(self.browser(refreshed_token, "GET", "users", student.uid), 403)
        self.assertEqual(self.client.get("/api/auth/me", headers=bearer(refreshed_token)).status_code, 200)
        fresh, _ = self.session(student)
        self.assertEqual(self.assessment(fresh).status_code, 200, "a sign-in after Enable works")
        self.assertEqual(self.browser(fresh, "GET", "users", student.uid), 200)

    # ------------------------------------------------------------------- Disable/Enable locks
    def test_03_a_running_lock_is_not_taken_over_until_lease_and_grace_have_passed(self):
        student = self.registered_student(with_records=False)
        lock = self.db.collection("account_operations").document(student.uid)
        lock.set({"operationId": "crashed-op", "operation": "disable", "actorUid": "someone", "status": "running",
                  "leaseExpiresAt": datetime.now(timezone.utc) - timedelta(minutes=10), "failedStep": None,
                  "reason": None, "previousOperationId": None, "startedAt": SERVER_TIMESTAMP, "updatedAt": SERVER_TIMESTAMP})
        state = self.admin_call("get", student.uid, "access").json()
        self.assertEqual(state["state"], "in_progress")
        self.assertIsNotNone(state["operation"]["resumable_after"])
        for action in ("disable", "enable"):
            self.assertEqual(self.code(self.admin_call("post", student.uid, action)), (409, "OPERATION_IN_PROGRESS"))
        self.assertEqual(self.record(student.uid), {"state": "active", "version": 1})
        lock.update({"leaseExpiresAt": datetime.now(timezone.utc) - timedelta(seconds=actions.TAKEOVER_GRACE_SECONDS + 60)})
        response = self.admin_call("post", student.uid, "disable")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["resumed_operation_id"], "crashed-op")
        self.assertIsNone(self.lock(student.uid))

    def test_04_a_stale_enable_never_re_enables_auth(self):
        student = self.registered_student(with_records=False)
        self.assertEqual(self.admin_call("post", student.uid, "disable").status_code, 200)
        original_settle = actions._settle

        def settle_then_change(run):
            original_settle(run)
            current = self.record(student.uid)
            self.db.collection("account_access").document(student.uid).update({"version": current["version"] + 1})

        steps = [(name, settle_then_change if name == actions.STEP_SETTLE else fn) for name, fn in actions._ENABLE_STEPS]
        with mock.patch.object(actions, "_ENABLE_STEPS", steps):
            response = self.admin_call("post", student.uid, "enable")
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual((detail["failed_step"], detail["reason"]), ("enable_auth", "RECORD_CHANGED"))
        self.assertTrue(firebase_auth.get_user(student.uid).disabled, "sign-in stays disabled")
        self.assertEqual(self.record(student.uid)["state"], "disabled")
        self.assertEqual(error_message(sign_in(student)), "USER_DISABLED")

    def test_05_concurrent_mixed_disable_and_enable_leave_a_consistent_account(self):
        student = self.registered_student(with_records=False)
        functions = [actions.disable_account, actions.enable_account] * 3
        barrier = threading.Barrier(len(functions))
        outcomes = []

        def attempt(function):
            barrier.wait()
            try:
                outcomes.append(function(student.uid, self.admin.uid).view.state)
            except actions.AccountActionError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt, args=(f,)) for f in functions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertTrue(set(outcomes) <= {"active", "disabled", "OPERATION_IN_PROGRESS", "ALREADY_ACTIVE",
                                          "ALREADY_DISABLED"}, outcomes)
        state = self.admin_call("get", student.uid, "access").json()
        self.assertIn(state["state"], ("active", "disabled"), outcomes)
        self.assertEqual(firebase_auth.get_user(student.uid).disabled, state["state"] == "disabled")
        self.assertIsNone(self.lock(student.uid))
        self.assertTrue(all(a["outcome"] == "completed" for a in self.audits(student.uid)))

    # ------------------------------------------------------------------- self-service deletion
    def test_06_a_student_deletes_their_own_account_completely(self):
        student = self.registered_student()
        token, refresh_token = self.session(student)  # a fresh sign-in: recent
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, True))
        response = self.self_delete(token, student.uid)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["outcome"], "completed")
        self.assertNotIn(student.email, response.text)

        self.assertFalse(self.auth_exists(student.uid))
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, False))
        self.assertEqual(self.record(student.uid), {"state": "deleted", "version": 4}, "minimal tombstone")
        self.assertIsNone(self.lock(student.uid))
        [audit] = self.audits(student.uid)
        self.assertEqual((audit["operation"], audit["outcome"], audit["actorUid"], audit["requestedBy"]),
                         ("delete", "completed", student.uid, "student"))
        self.assertNotIn(student.email, repr(audit))
        # The same session afterwards: Firestore, the backend and token refresh all refuse it.
        self.assertEqual(self.browser(token, "GET", "users", student.uid), 403)
        self.assertEqual(self.assessment(token).status_code, 401)
        self.assertNotEqual(refresh(refresh_token).status_code, 200)
        self.assertEqual(error_message(sign_in(student)), "EMAIL_NOT_FOUND")
        self.ai.assert_not_called()

    def test_07_recent_sign_in_own_account_and_no_administrators(self):
        student = self.registered_student()
        other = self.registered_student()
        token, _ = self.session(student)
        # Not recent: the server's clock moved on by more than RECENT_SIGN_IN_SECONDS.
        with mock.patch("routes.account_self_service._now_seconds",
                        return_value=time.time() + 10 * 60):
            self.assertEqual(self.code(self.self_delete(token, student.uid)), (403, "RECENT_SIGN_IN_REQUIRED"))
        self.assertEqual(self.code(self.self_delete(token, other.uid)), (422, "DELETE_CONFIRMATION_MISMATCH"))
        self.assertEqual(self.client.post(SELF_DELETE, json={"confirm_uid": student.uid}).status_code, 401)
        self.assertEqual(self.code(self.self_delete(self.admin_token, self.admin.uid)), (403, "ADMIN_TARGET_FORBIDDEN"))
        for account in (student, other):
            self.assertTrue(self.auth_exists(account.uid))
            self.assertEqual(self.remaining(account.uid), dict.fromkeys(STUDENT_DATA, True))
            self.assertEqual(self.record(account.uid), {"state": "active", "version": 1})
            self.assertEqual(self.audits(account.uid), [])
        # The browser can no longer delete the profile itself (experimental rules, M3C).
        self.assertEqual(self.browser(token, "DELETE", "users", student.uid), 403)
        self.assertEqual(self.remaining(student.uid)["users"], True)

    def test_08_disabled_legacy_and_old_sessions_cannot_self_delete(self):
        legacy = new_student()  # no access record
        legacy_token, _ = self.session(legacy)
        self.assertEqual(self.code(self.self_delete(legacy_token, legacy.uid)), (403, "ACCOUNT_ACCESS_DENIED"))
        self.assertTrue(self.auth_exists(legacy.uid))

        partial = self.registered_student()
        partial_token, _ = self.session(partial)
        with mock.patch("services.account_action_service.firebase_auth.update_user",
                        side_effect=firebase_exceptions.UnavailableError("Auth down")):
            self.assertEqual(self.admin_call("post", partial.uid, "disable").status_code, 503)
        self.assertEqual(self.code(self.self_delete(partial_token, partial.uid)), (403, "ACCOUNT_ACCESS_DENIED"))
        self.assertEqual(self.remaining(partial.uid), dict.fromkeys(STUDENT_DATA, True))

    def test_09_an_incomplete_self_deletion_is_recorded_listed_and_completed_by_an_administrator(self):
        student = self.registered_student()
        token, _ = self.session(student)
        with mock.patch("services.account_action_service.firebase_auth.delete_user",
                        side_effect=firebase_exceptions.UnavailableError("Auth down")):
            response = self.self_delete(token, student.uid)
        self.assertEqual(response.status_code, 503, response.text)
        detail = response.json()["detail"]
        self.assertEqual((detail["code"], detail["failed_step"], detail["reason"]),
                         ("OPERATION_INCOMPLETE", "delete_auth", "AUTH_UNAVAILABLE"))
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, False), "data already removed")
        self.assertTrue(firebase_auth.get_user(student.uid).disabled, "no sign-in meanwhile")
        self.assertEqual(self.record(student.uid)["state"], "deleting")
        listed = {item["uid"]: item for item in
                  self.client.get(INCOMPLETE, headers=bearer(self.admin_token)).json()["items"]}
        self.assertEqual(listed[student.uid]["state"], "deletion_incomplete")
        resumed = self.admin_call("post", student.uid, "delete", body={"confirm_uid": student.uid})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["resumed_operation_id"], detail["operation_id"])
        self.assertFalse(self.auth_exists(student.uid))
        self.assertEqual(self.record(student.uid)["state"], "deleted")
        self.assertEqual([(a["outcome"], a["requestedBy"]) for a in self.audits(student.uid)],
                         [("incomplete", "student"), ("completed", "administrator")])

    def test_10_production_mode_has_no_self_deletion_route_and_reads_no_record(self):
        student = self.registered_student()
        token, _ = self.session(student)
        with mock.patch.dict(os.environ, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}):
            production_app = import_main().app
            paths = sorted(production_app.openapi()["paths"])
            response = TestClient(production_app).post(SELF_DELETE, headers=bearer(token),
                                                       json={"confirm_uid": student.uid})
        sys.modules.pop("main", None)
        self.assertNotIn(SELF_DELETE, paths)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.auth_exists(student.uid))
        self.assertEqual(self.remaining(student.uid), dict.fromkeys(STUDENT_DATA, True))

    def test_12_lock_renewal_survives_simultaneous_lock_requests(self):
        # ML10: six requests try to take the same lock at once; the winner renews IMMEDIATELY (the window in which
        # the emulator aborted the winner's conditional update in most trials of the root-cause probe). The renewal
        # must never report LOCK_LOST while the lock is still the winner's, and contention must really occur here.
        trials, workers = 25, 6
        results = []
        backoffs = []
        real_sleep = time.sleep

        def recording_sleep(seconds):
            if seconds in actions.RENEW_BACKOFF_SECONDS:
                backoffs.append(seconds)
            real_sleep(seconds)

        with mock.patch.object(actions, "_sleep", side_effect=recording_sleep):
            for trial in range(trials):
                uid = f"ml10-{trial}-{os.urandom(4).hex()}"
                barrier = threading.Barrier(workers)
                trial_results = []

                def worker():
                    barrier.wait()
                    try:
                        held = actions._acquire_lock(self.db, uid, actions.DISABLE, self.admin.uid)
                    except actions.AccountActionError as exc:
                        trial_results.append(exc.code)
                        return
                    try:
                        actions._renew_lock(self.db, held)
                        trial_results.append("renewed")
                    except actions._StepFailure as failure:
                        trial_results.append(failure.reason)
                    self.assertTrue(actions._release(self.db, held))

                threads = [threading.Thread(target=worker) for _ in range(workers)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                results.append(trial_results)
        flat = [outcome for trial_results in results for outcome in trial_results]
        self.assertNotIn("LOCK_LOST", flat, results)
        self.assertEqual(flat.count("renewed"), trials, results)
        self.assertEqual(set(flat) - {"renewed"}, {"OPERATION_IN_PROGRESS"}, results)
        self.assertTrue(backoffs, "contention was exercised (at least one renewal was retried)")

    def test_11_only_the_emulators_are_used(self):
        app = firebase_admin.get_app()
        self.assertIsInstance(app.credential, core_firebase.EmulatorCredential)
        self.assertEqual(app.project_id, PROJECT_ID)
        self.assertNotEqual(app.project_id, PRODUCTION_PROJECT_ID)
        self.assertTrue(HTTP_HOSTS)
        self.assertTrue(all(core_firebase.is_loopback_host_port(host) for host in HTTP_HOSTS), HTTP_HOSTS)


if __name__ == "__main__":
    unittest.main()
