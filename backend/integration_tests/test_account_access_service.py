# backend/integration_tests/test_account_access_service.py
"""
M3B-1B-P1-B1: the account-access service against the LOCAL Firebase
Authentication and Firestore emulators (project demo-route2unikl).

Run with the other emulator integration tests, from the backend directory:
    firebase emulators:exec --only auth,firestore --project demo-route2unikl --config ../firebase.json ".venv\\Scripts\\python.exe -m unittest discover -s integration_tests -t . -v"

This module uses the module set-up and teardown of test_auth_emulator.py
(imported below; unittest runs them for this module too): importing it refuses
to run without loopback emulator hosts and a demo- project; emulator mode is
switched on for this process only; the service-account loader fails if
called; every HTTP request is recorded and must stay on loopback; both
emulators are wiped before and after. Only emulator accounts and emulator
documents are created or changed.
"""
import sys
import threading
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# setUpModule / tearDownModule are picked up by unittest for this module.
from integration_tests.test_auth_emulator import (  # noqa: E402,F401
    FIRESTORE_HOST, HTTP_HOSTS, PRODUCTION_PROJECT_ID, PROJECT_ID, new_student, setUpModule, tearDownModule)

import firebase_admin  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402

from core import firebase as core_firebase  # noqa: E402
from services import account_access_service as service  # noqa: E402

THRESHOLD = datetime(2027, 1, 15, 8, 0, tzinfo=timezone.utc)


class AccountAccessServiceEmulatorTests(unittest.TestCase):
    def setUp(self):
        self.db = core_firebase.initialize_firebase()

    def document(self, uid):
        return self.db.collection(service.COLLECTION).document(uid)

    def stored(self, uid):
        """(data or None, update time) as Firestore holds them."""
        snapshot = self.document(uid).get()
        return (snapshot.to_dict() if snapshot.exists else None), snapshot.update_time

    def assert_error(self, code, call, *args):
        with self.assertRaises(service.AccountAccessError) as ctx:
            call(*args)
        self.assertEqual(ctx.exception.code, code)

    def test_01_a_new_enabled_account_gets_an_active_record_of_the_exact_shape(self):
        student = new_student()
        result = service.provision_access_record(student.uid)
        self.assertTrue(result.created)
        self.assertTrue(result.activated)
        self.assertEqual(result.issues, ())
        data, _ = self.stored(student.uid)
        self.assertEqual(data, {"state": "active", "version": 1})
        self.assertEqual(service.validate_access_record(data).status, "valid")
        self.assertTrue(service.inspect_account(student.uid).consistent)

    def test_02_an_auth_disabled_account_gets_a_disabled_record(self):
        student = new_student()
        firebase_auth.update_user(student.uid, disabled=True)
        result = service.provision_access_record(student.uid)
        self.assertTrue(result.created)
        self.assertFalse(result.activated)
        self.assertEqual(self.stored(student.uid)[0], {"state": "disabled", "version": 1})
        self.assertTrue(service.inspect_account(student.uid).consistent)

    def test_03_repeated_requests_never_rewrite_the_record(self):
        student = new_student()
        first = service.provision_access_record(student.uid)
        data_before, time_before = self.stored(student.uid)
        for _ in range(3):
            again = service.provision_access_record(student.uid)
            self.assertFalse(again.created)
            self.assertEqual(again.lookup, first.lookup)
        data_after, time_after = self.stored(student.uid)
        self.assertEqual(data_after, data_before)
        self.assertEqual(time_after, time_before, "the document was not written again")

    def test_04_blocked_records_are_never_reactivated(self):
        for state, extra in (("disabled", {"sessionsValidAfter": THRESHOLD}), ("disabled", {}),
                             ("deleting", {}), ("deleted", {}), ("active", {"sessionsValidAfter": THRESHOLD})):
            with self.subTest(state=state, threshold=bool(extra)):
                student = new_student()  # enabled in Firebase Authentication
                self.document(student.uid).set({"state": state, "version": 4, **extra})
                data_before, time_before = self.stored(student.uid)

                result = service.provision_access_record(student.uid)
                self.assertFalse(result.created)
                self.assertEqual(result.lookup.record.state, state)
                self.assertEqual(result.lookup.record.sessions_valid_after, extra.get("sessionsValidAfter"))
                if state != "active":
                    self.assertFalse(result.activated)
                    self.assertTrue(result.issues)
                data_after, time_after = self.stored(student.uid)
                self.assertEqual(data_after, data_before)
                self.assertEqual(time_after, time_before)

    def test_05_a_malformed_record_is_reported_and_left_unchanged(self):
        student = new_student()
        self.document(student.uid).set({"state": "ACTIVE", "version": "1"})
        data_before, time_before = self.stored(student.uid)
        result = service.provision_access_record(student.uid)
        self.assertFalse(result.created)
        self.assertFalse(result.activated)
        self.assertEqual(result.lookup.status, "malformed")
        self.assertEqual(set(result.lookup.problems), {service.STATE_INVALID, service.VERSION_INVALID})
        self.assertEqual(result.issues, (service.RECORD_MALFORMED,))
        self.assertEqual(self.stored(student.uid), (data_before, time_before))

    def test_06_missing_auth_accounts_get_no_record(self):
        unknown = f"no-such-account-{uuid.uuid4().hex[:8]}"
        self.assert_error(service.AUTH_ACCOUNT_NOT_FOUND, service.provision_access_record, unknown)
        self.assertIsNone(self.stored(unknown)[0])

        deleted = new_student()
        firebase_auth.delete_user(deleted.uid)
        self.assert_error(service.AUTH_ACCOUNT_NOT_FOUND, service.provision_access_record, deleted.uid)
        self.assertIsNone(self.stored(deleted.uid)[0])

    def test_07_concurrent_requests_create_exactly_one_record(self):
        student = new_student()
        workers = 8
        barrier = threading.Barrier(workers)
        results, errors = [], []

        def provision():
            barrier.wait()
            try:
                results.append(service.provision_access_record(student.uid))
            except Exception as exc:  # reported by the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=provision) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), workers)
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(self.stored(student.uid)[0], {"state": "active", "version": 1})

    def test_08_inconsistencies_with_the_real_auth_state_are_detected(self):
        student = new_student()
        service.provision_access_record(student.uid)
        data_before, time_before = self.stored(student.uid)

        firebase_auth.update_user(student.uid, disabled=True)  # e.g. disabled in the console
        assessment = service.inspect_account(student.uid)
        self.assertEqual(assessment.auth_status, service.AUTH_DISABLED)
        self.assertEqual(assessment.issues, (service.AUTH_DISABLED_RECORD_ACTIVE,))

        firebase_auth.delete_user(student.uid)
        self.assertEqual(service.inspect_account(student.uid).issues, (service.AUTH_ACCOUNT_MISSING,))
        self.assertEqual(self.stored(student.uid), (data_before, time_before), "inspection never writes")

    def test_09_only_the_emulators_are_used_and_no_credentials_are_loaded(self):
        app = firebase_admin.get_app()
        self.assertIsInstance(app.credential, core_firebase.EmulatorCredential)
        self.assertEqual(app.project_id, PROJECT_ID)
        self.assertNotEqual(app.project_id, PRODUCTION_PROJECT_ID)
        self.assertEqual(core_firebase.initialized_config().mode, core_firebase.EMULATOR_MODE)
        self.assertEqual(self.db._emulator_host, FIRESTORE_HOST)
        service.provision_access_record(new_student().uid)
        self.assertTrue(HTTP_HOSTS)
        self.assertTrue(all(core_firebase.is_loopback_host_port(host) for host in HTTP_HOSTS), HTTP_HOSTS)


if __name__ == "__main__":
    unittest.main()
