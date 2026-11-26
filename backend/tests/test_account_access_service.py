# backend/tests/test_account_access_service.py
"""
M3B-1B-P1-B1: backend account-access service (backend/services/account_access_service.py).

Run from the backend directory with the other backend tests:
    python -m unittest discover -s tests -t . -v

Safety: Firebase Authentication and Firestore are replaced by in-memory fakes
(the fake collection has Firestore's create-if-absent semantics). No network,
emulator or credential is used.
"""
import logging
import re
import sys
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Test isolation (M3C audit A2): installed by importing the tests package, before any Firebase, Google or
# application import, also when this file is executed directly; the import fails if they cannot be installed.
from tests import isolation  # noqa: E402

isolation.require_guards(isolation.UNIT)

from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402

from core.firebase import FirebaseConfigError  # noqa: E402
from services import account_access_service as service  # noqa: E402

UID = "student-uid-123"
EMAIL = "private.student@example.test"  # must never appear in logs or errors
THRESHOLD = datetime(2027, 1, 15, 8, 0, 0, tzinfo=timezone.utc)


# ----------------------------------------------------------------------- fakes
class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class FakeDocument:
    def __init__(self, store, collection, uid):
        self.store, self.collection, self.uid = store, collection, uid

    def get(self):
        if self.store.get_error:
            raise self.store.get_error
        with self.store.lock:
            return FakeSnapshot(self.store.docs.get(self.uid))

    def create(self, data, retry=None, timeout=None):
        self.store.create_calls.append({"uid": self.uid, "data": dict(data), "retry": retry, "timeout": timeout})
        if self.store.create_error:
            raise self.store.create_error
        with self.store.lock:
            if self.uid in self.store.docs:
                raise google_exceptions.AlreadyExists("Document already exists")
            self.store.docs[self.uid] = dict(data)
            self.store.writes += 1
        if self.store.error_after_commit:
            raise self.store.error_after_commit  # written, but the caller cannot know


class FakeCollection:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def document(self, uid):
        return FakeDocument(self.store, self.name, uid)


class FakeFirestore:
    """account_access documents in memory, with Firestore's create-if-absent semantics."""

    def __init__(self):
        self.docs = {}
        self.lock = threading.Lock()
        self.create_calls = []
        self.writes = 0
        self.collections = set()
        self.get_error = None
        self.create_error = None
        self.error_after_commit = None

    def collection(self, name):
        self.collections.add(name)
        return FakeCollection(self, name)


class FakeAuth:
    def __init__(self):
        self.accounts = {}
        self.calls = 0
        self.error = None
        self.after_first_call = None  # callable run once, after the first lookup

    def add(self, uid, disabled=False):
        self.accounts[uid] = SimpleNamespace(uid=uid, email=EMAIL, disabled=disabled)

    def get_user(self, uid, app=None):
        self.calls += 1
        if self.calls == 2 and self.after_first_call:
            self.after_first_call()
        if self.error:
            raise self.error
        if uid not in self.accounts:
            raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")
        return self.accounts[uid]


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class AccountAccessTestBase(unittest.TestCase):
    def setUp(self):
        self.store = FakeFirestore()
        self.auth = FakeAuth()
        self.initialize = self.patch("services.account_access_service.initialize_firebase", return_value=self.store)
        self.patch("services.account_access_service.firebase_auth.get_user", side_effect=self.auth.get_user)
        logger = logging.getLogger("account_access_service")
        self.logs = ListHandler()
        saved = (logger.level, logger.propagate)
        logger.addHandler(self.logs)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        self.addCleanup(lambda: (logger.removeHandler(self.logs), logger.setLevel(saved[0]),
                                 setattr(logger, "propagate", saved[1])))
        self.addCleanup(self.assert_no_private_data_logged)

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def assert_no_private_data_logged(self):
        for message in self.logs.messages:
            self.assertNotIn(EMAIL, message)

    def assert_error(self, code, call, *args):
        with self.assertRaises(service.AccountAccessError) as ctx:
            call(*args)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(str(ctx.exception), code)  # the message is the code only
        return ctx.exception


# ----------------------------------------------------------------- validation
class RecordValidationTests(unittest.TestCase):
    def test_well_formed_records(self):
        cases = [
            ({"state": "active", "version": 1}, service.AccessRecord("active", 1)),
            ({"state": "disabled", "version": 0}, service.AccessRecord("disabled", 0)),
            ({"state": "deleting", "version": 7}, service.AccessRecord("deleting", 7)),
            ({"state": "deleted", "version": 9}, service.AccessRecord("deleted", 9)),
            ({"state": "active", "version": 4, "sessionsValidAfter": THRESHOLD},
             service.AccessRecord("active", 4, THRESHOLD)),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(service.validate_access_record(data), service.RecordLookup("valid", expected))

    def test_malformed_records_are_reported_with_problem_codes(self):
        cases = [
            (None, {service.NOT_A_MAP}),
            ("active", {service.NOT_A_MAP}),
            (["state", "active"], {service.NOT_A_MAP}),
            ({}, {service.STATE_MISSING, service.VERSION_MISSING}),
            ({"version": 1}, {service.STATE_MISSING}),
            ({"state": "active"}, {service.VERSION_MISSING}),
            ({"state": True, "version": 1}, {service.STATE_INVALID}),
            ({"state": "enabled", "version": 1}, {service.STATE_INVALID}),
            ({"state": "Active", "version": 1}, {service.STATE_INVALID}),
            ({"state": "active ", "version": 1}, {service.STATE_INVALID}),
            ({"state": "active", "version": "1"}, {service.VERSION_INVALID}),
            ({"state": "active", "version": 1.5}, {service.VERSION_INVALID}),
            ({"state": "active", "version": -1}, {service.VERSION_INVALID}),
            ({"state": "active", "version": True}, {service.VERSION_INVALID}),
            ({"state": "active", "version": 1, "sessionsValidAfter": None}, {service.SESSIONS_VALID_AFTER_INVALID}),
            ({"state": "active", "version": 1, "sessionsValidAfter": "2027-01-15T08:00:00Z"},
             {service.SESSIONS_VALID_AFTER_INVALID}),
            ({"state": "active", "version": 1, "sessionsValidAfter": 1800000000000}, {service.SESSIONS_VALID_AFTER_INVALID}),
            ({"state": "active", "version": 1, "sessionsValidAfter": datetime(2027, 1, 15, 8, 0)},
             {service.SESSIONS_VALID_AFTER_INVALID}),  # no time zone
            ({"state": "active", "version": 1, "sessionValidAfter": THRESHOLD}, {service.UNKNOWN_FIELD}),
            ({"state": "active", "version": 1, "updatedAt": THRESHOLD}, {service.UNKNOWN_FIELD}),
            ({"state": "active", "version": 1, "admin": True}, {service.UNKNOWN_FIELD}),
        ]
        for data, problems in cases:
            with self.subTest(data=data):
                lookup = service.validate_access_record(data)
                self.assertEqual(lookup.status, "malformed")
                self.assertIsNone(lookup.record)
                self.assertEqual(set(lookup.problems), problems)


class UidValidationTests(AccountAccessTestBase):
    def test_invalid_uids_are_refused_before_any_firebase_call(self):
        invalid = (None, "", 123, "a" * 129, "a/b", "a b", "../x", "x\n", "x\x00", "uü", "x.y")
        for call in (service.read_access_record, service.inspect_account, service.provision_access_record):
            for uid in invalid:
                with self.subTest(call=call.__name__, uid=uid):
                    self.assert_error(service.INVALID_UID, call, uid)
        self.initialize.assert_not_called()
        self.assertEqual(self.auth.calls, 0)
        self.assertEqual(self.store.create_calls, [])

    def test_valid_uid_forms_are_accepted(self):
        for uid in ("a", "A1_b-2", "x" * 128):
            with self.subTest(uid=uid):
                self.assertEqual(service.read_access_record(uid).status, "missing")


# ---------------------------------------------------------------- provisioning
class ProvisioningTests(AccountAccessTestBase):
    def test_a_new_enabled_account_gets_an_active_record(self):
        self.auth.add(UID)
        result = service.provision_access_record(UID)
        self.assertTrue(result.created)
        self.assertTrue(result.activated)
        self.assertEqual(result.issues, ())
        self.assertEqual(result.lookup, service.RecordLookup("valid", service.AccessRecord("active", 1)))
        self.assertEqual(self.store.docs[UID], {"state": "active", "version": 1})
        self.assertEqual(self.store.create_calls,
                         [{"uid": UID, "data": {"state": "active", "version": 1}, "retry": None, "timeout": 10}])
        self.assertEqual(self.store.collections, {"account_access"})

    def test_an_auth_disabled_account_without_a_record_gets_a_disabled_record(self):
        self.auth.add(UID, disabled=True)
        result = service.provision_access_record(UID)
        self.assertTrue(result.created)
        self.assertFalse(result.activated)
        self.assertEqual(result.issues, ())
        self.assertEqual(self.store.docs[UID], {"state": "disabled", "version": 1})

    def test_existing_records_are_never_modified_whatever_their_state(self):
        expected_issues = {
            ("active", False): (), ("active", True): (service.AUTH_DISABLED_RECORD_ACTIVE,),
            ("disabled", False): (service.AUTH_ENABLED_RECORD_DISABLED,), ("disabled", True): (),
            ("deleting", False): (service.DELETION_IN_PROGRESS,), ("deleting", True): (service.DELETION_IN_PROGRESS,),
            ("deleted", False): (service.RECORD_DELETED_AUTH_PRESENT,),
            ("deleted", True): (service.RECORD_DELETED_AUTH_PRESENT,),
        }
        for (state, auth_disabled), issues in expected_issues.items():
            for with_threshold in (False, True):
                with self.subTest(state=state, auth_disabled=auth_disabled, threshold=with_threshold):
                    self.store.docs.clear()
                    self.auth.add(UID, disabled=auth_disabled)
                    stored = {"state": state, "version": 5}
                    if with_threshold:
                        stored["sessionsValidAfter"] = THRESHOLD
                    self.store.docs[UID] = dict(stored)
                    writes_before = self.store.writes

                    result = service.provision_access_record(UID)
                    self.assertFalse(result.created)
                    self.assertFalse(result.activated)
                    self.assertEqual(result.issues, issues)
                    self.assertEqual(result.lookup.record,
                                     service.AccessRecord(state, 5, THRESHOLD if with_threshold else None))
                    self.assertEqual(self.store.docs[UID], stored, "the record (and sessionsValidAfter) is unchanged")
                    self.assertEqual(self.store.writes, writes_before)

    def test_a_malformed_record_is_reported_and_never_repaired(self):
        self.auth.add(UID)
        for stored in ({"state": "ACTIVE", "version": 1}, {"state": "active"}, {"state": "active", "version": 1, "x": 1},
                       {"state": "deleted", "version": "2"}):
            with self.subTest(stored=stored):
                self.store.docs[UID] = dict(stored)
                result = service.provision_access_record(UID)
                self.assertFalse(result.created)
                self.assertFalse(result.activated)
                self.assertEqual(result.lookup.status, "malformed")
                self.assertEqual(result.issues, (service.RECORD_MALFORMED,))
                self.assertEqual(self.store.docs[UID], stored)
        self.assertEqual(self.store.writes, 0)

    def test_a_missing_auth_account_is_refused_and_nothing_is_written(self):
        self.assert_error(service.AUTH_ACCOUNT_NOT_FOUND, service.provision_access_record, UID)
        self.assertEqual(self.store.create_calls, [])
        self.assertEqual(self.store.docs, {})
        # Even with a leftover record, nothing is created or changed.
        self.store.docs[UID] = {"state": "deleted", "version": 3}
        self.assert_error(service.AUTH_ACCOUNT_NOT_FOUND, service.provision_access_record, UID)
        self.assertEqual(self.store.docs[UID], {"state": "deleted", "version": 3})
        self.assertEqual(self.store.create_calls, [])

    def test_auth_unavailable_fails_closed(self):
        self.auth.add(UID)
        for error in (firebase_exceptions.UnavailableError(f"lookup failed for {EMAIL}"),
                      firebase_exceptions.DeadlineExceededError("timeout"), RuntimeError(EMAIL)):
            with self.subTest(error=type(error).__name__):
                self.auth.error = error
                exc = self.assert_error(service.AUTH_UNAVAILABLE, service.provision_access_record, UID)
                self.assertNotIn(EMAIL, str(exc))
        self.assertEqual(self.store.create_calls, [])

    def test_a_firebase_configuration_failure_fails_closed(self):
        self.auth.add(UID)
        self.initialize.side_effect = FirebaseConfigError("FIREBASE_AUTH_EMULATOR_HOST must be ...")
        for call in (service.read_access_record, service.inspect_account, service.provision_access_record):
            with self.subTest(call=call.__name__):
                self.assert_error(service.FIREBASE_UNAVAILABLE, call, UID)
        self.assertEqual(self.auth.calls, 0)
        self.assertEqual(self.store.create_calls, [])

    def test_firestore_unavailable_during_create_is_never_reported_as_success(self):
        self.auth.add(UID)
        for error in (google_exceptions.ServiceUnavailable("down"), google_exceptions.DeadlineExceeded("slow"),
                      google_exceptions.PermissionDenied("denied"), RuntimeError("unexpected")):
            with self.subTest(error=type(error).__name__):
                self.store.create_error = error
                self.assert_error(service.STORE_UNAVAILABLE, service.provision_access_record, UID)
                self.assertEqual(self.store.docs, {})

    def test_a_create_with_an_unknown_outcome_is_safe_to_retry(self):
        self.auth.add(UID)
        self.store.error_after_commit = google_exceptions.DeadlineExceeded("no response")
        self.assert_error(service.STORE_UNAVAILABLE, service.provision_access_record, UID)
        self.assertEqual(self.store.docs[UID], {"state": "active", "version": 1}, "the write did happen")

        self.store.error_after_commit = None
        retry = service.provision_access_record(UID)
        self.assertFalse(retry.created)
        self.assertFalse(retry.activated)
        self.assertEqual(retry.lookup.record, service.AccessRecord("active", 1))
        self.assertEqual(retry.issues, ())
        self.assertEqual(self.store.writes, 1)

    def test_a_create_aborted_by_a_concurrent_write_reports_the_stored_record(self):
        # Firestore answers ABORTED when concurrent writes contend for the same document.
        self.auth.add(UID)
        self.store.docs[UID] = {"state": "active", "version": 1}  # written by the concurrent request
        self.store.create_error = google_exceptions.Aborted("Transaction lock timeout")
        result = service.provision_access_record(UID)
        self.assertFalse(result.created)
        self.assertFalse(result.activated)
        self.assertEqual(result.lookup.record, service.AccessRecord("active", 1))
        self.assertEqual(self.store.docs[UID], {"state": "active", "version": 1})

    def test_a_refused_create_with_nothing_stored_is_not_confirmed(self):
        # Aborted with no record stored, or AlreadyExists for a record removed in the meantime.
        self.auth.add(UID)
        for error in (google_exceptions.Aborted("contention"), google_exceptions.AlreadyExists("exists")):
            with self.subTest(error=type(error).__name__):
                self.store.create_error = error
                self.assert_error(service.STORE_UNAVAILABLE, service.provision_access_record, UID)
                self.assertEqual(self.store.docs, {})

    def test_firestore_unavailable_when_reading_an_existing_record(self):
        self.auth.add(UID)
        self.store.docs[UID] = {"state": "disabled", "version": 2}
        self.store.get_error = google_exceptions.ServiceUnavailable("down")
        self.assert_error(service.STORE_UNAVAILABLE, service.provision_access_record, UID)
        self.assertEqual(self.store.docs[UID], {"state": "disabled", "version": 2})

    def test_an_auth_change_during_provisioning_is_reported_not_activated(self):
        def disable():
            self.auth.accounts[UID].disabled = True

        def delete():
            del self.auth.accounts[UID]

        def unavailable():
            self.auth.error = firebase_exceptions.UnavailableError("down")

        cases = ((disable, (service.AUTH_DISABLED_RECORD_ACTIVE,)), (delete, (service.AUTH_ACCOUNT_MISSING,)),
                 (unavailable, (service.AUTH_STATE_UNVERIFIED,)))
        for change, issues in cases:
            with self.subTest(change=change.__name__):
                self.store.docs.clear()
                self.auth = FakeAuth()
                self.auth.add(UID)
                self.auth.after_first_call = change
                self.patch("services.account_access_service.firebase_auth.get_user", side_effect=self.auth.get_user)
                result = service.provision_access_record(UID)
                self.assertTrue(result.created)
                self.assertFalse(result.activated)
                self.assertEqual(result.issues, issues)

    def test_duplicate_requests_write_once(self):
        self.auth.add(UID)
        first = service.provision_access_record(UID)
        second = service.provision_access_record(UID)
        self.assertTrue(first.created and first.activated)
        self.assertFalse(second.created or second.activated)
        self.assertEqual(second.lookup, first.lookup)
        self.assertEqual(self.store.writes, 1)

    def test_concurrent_requests_create_exactly_one_record(self):
        self.auth.add(UID)
        workers = 16
        barrier = threading.Barrier(workers)
        results, errors = [], []

        def provision():
            barrier.wait()
            try:
                results.append(service.provision_access_record(UID))
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=provision) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(sum(result.activated for result in results), 1)
        self.assertTrue(all(result.lookup.record == service.AccessRecord("active", 1) for result in results))
        self.assertEqual(self.store.writes, 1)
        self.assertEqual(len(self.store.create_calls), workers)


# ------------------------------------------------------------------ inspection
class InspectionTests(AccountAccessTestBase):
    def test_consistency_between_auth_and_the_record(self):
        records = {
            "missing": None,
            "malformed": {"state": "active"},
            "active": {"state": "active", "version": 1},
            "disabled": {"state": "disabled", "version": 1},
            "deleting": {"state": "deleting", "version": 1},
            "deleted": {"state": "deleted", "version": 1},
        }
        expected = {
            "enabled": {"missing": (service.RECORD_MISSING,), "malformed": (service.RECORD_MALFORMED,),
                        "active": (), "disabled": (service.AUTH_ENABLED_RECORD_DISABLED,),
                        "deleting": (service.DELETION_IN_PROGRESS,), "deleted": (service.RECORD_DELETED_AUTH_PRESENT,)},
            "disabled": {"missing": (service.RECORD_MISSING,), "malformed": (service.RECORD_MALFORMED,),
                         "active": (service.AUTH_DISABLED_RECORD_ACTIVE,), "disabled": (),
                         "deleting": (service.DELETION_IN_PROGRESS,), "deleted": (service.RECORD_DELETED_AUTH_PRESENT,)},
            "missing": {"missing": (service.RECORD_MISSING, service.AUTH_ACCOUNT_MISSING),
                        "malformed": (service.RECORD_MALFORMED,), "active": (service.AUTH_ACCOUNT_MISSING,),
                        "disabled": (service.AUTH_ACCOUNT_MISSING,), "deleting": (service.DELETION_IN_PROGRESS,),
                        "deleted": ()},
        }
        for auth_status, by_record in expected.items():
            for record_name, issues in by_record.items():
                with self.subTest(auth=auth_status, record=record_name):
                    self.auth.accounts.clear()
                    self.store.docs.clear()
                    if auth_status != "missing":
                        self.auth.add(UID, disabled=auth_status == "disabled")
                    if records[record_name] is not None:
                        self.store.docs[UID] = dict(records[record_name])
                    assessment = service.inspect_account(UID)
                    self.assertEqual(assessment.auth_status, auth_status)
                    self.assertEqual(assessment.issues, issues)
                    self.assertEqual(assessment.consistent, issues == ())
        self.assertEqual(self.store.create_calls, [], "inspection never writes")

    def test_read_access_record_reports_valid_missing_and_malformed_without_auth_calls(self):
        self.assertEqual(service.read_access_record(UID), service.RecordLookup("missing"))
        self.store.docs[UID] = {"state": "disabled", "version": 2, "sessionsValidAfter": THRESHOLD}
        self.assertEqual(service.read_access_record(UID).record, service.AccessRecord("disabled", 2, THRESHOLD))
        self.store.docs[UID] = {"state": "disabled"}
        self.assertEqual(service.read_access_record(UID).problems, (service.VERSION_MISSING,))
        self.store.get_error = google_exceptions.ServiceUnavailable("down")
        self.assert_error(service.STORE_UNAVAILABLE, service.read_access_record, UID)
        self.assertEqual(self.auth.calls, 0)

    def test_inspection_fails_closed_when_auth_or_firestore_is_unavailable(self):
        self.auth.add(UID)
        self.auth.error = firebase_exceptions.UnavailableError("down")
        self.assert_error(service.AUTH_UNAVAILABLE, service.inspect_account, UID)
        self.auth.error = None
        self.store.get_error = google_exceptions.ServiceUnavailable("down")
        self.assert_error(service.STORE_UNAVAILABLE, service.inspect_account, UID)


# ------------------------------------------------------------- no public route
class NoPublicEndpointTests(unittest.TestCase):
    def test_no_route_or_the_application_uses_the_service(self):
        sources = [BACKEND_DIR / "main.py", *sorted((BACKEND_DIR / "routes").glob("*.py"))]
        for path in sources:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"account_access", text), f"{path.name} references account access")


if __name__ == "__main__":
    unittest.main()
