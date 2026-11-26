# backend/tests/test_account_actions.py
"""
M3B-2: admin Disable / Enable account actions (services/account_action_service.py,
routes/admin_account_actions.py) and the record primitives they use in
services/account_access_service.py (change_record_state, reconcile_access_record).

Run from the backend directory with the other backend tests:
    python -m unittest discover -s tests -t . -v

Safety: Firebase Authentication and Firestore are in-memory fakes. The fake Firestore implements
create-if-absent, update-time preconditions on update and delete, and server timestamps; every change
to Auth or Firestore is appended to one event log so the order of the steps can be checked. No network,
emulator or credential is used.
"""
import contextlib
import importlib
import io
import logging
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402
from google.cloud.firestore import SERVER_TIMESTAMP  # noqa: E402

from routes import admin_account_actions as action_routes  # noqa: E402
from services import account_access_service as access  # noqa: E402
from services import account_action_service as actions  # noqa: E402
from tests.test_auth import ADMIN_UID, STUDENT_UID, bearer, fake_verify_id_token  # noqa: E402
from tests.test_firebase_config import VALID_EMULATOR_ENV, firebase_env  # noqa: E402

TARGET = "target-student-uid"
OTHER_ADMIN = "other-admin-uid"
EMAIL = "sentinel.target@example.test"
BASE = "/api/admin/users"


# ----------------------------------------------------------------------------- fakes
class Events(list):
    """Every change to Auth or Firestore, in order."""


class FakeAuth:
    def __init__(self, events):
        self.events = events
        self.users = {}
        self.fail = {}          # method -> exception, or callable(kwargs) -> exception | None
        self.lock = threading.Lock()

    def add(self, uid, disabled=False, admin=False):
        self.users[uid] = SimpleNamespace(uid=uid, email=EMAIL, disabled=disabled,
                                          custom_claims={"admin": True} if admin else None)

    def _maybe_fail(self, method, **kwargs):
        failure = self.fail.get(method)
        if callable(failure) and not isinstance(failure, BaseException):
            failure = failure(kwargs)
        if failure:
            raise failure

    def get_user(self, uid, app=None):
        self._maybe_fail("get_user", uid=uid)
        if uid not in self.users:
            raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")
        return self.users[uid]

    def update_user(self, uid, **kwargs):
        self._maybe_fail("update_user", **kwargs)
        if uid not in self.users:
            raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")
        with self.lock:
            self.users[uid].disabled = kwargs["disabled"]
            self.events.append(("auth", "disabled" if kwargs["disabled"] else "enabled"))

    def revoke_refresh_tokens(self, uid, app=None):
        self._maybe_fail("revoke_refresh_tokens", uid=uid)
        if uid not in self.users:
            raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")
        self.events.append(("auth", "revoked"))

    def delete_user(self, uid, app=None):
        self._maybe_fail("delete_user", uid=uid)
        with self.lock:
            if uid not in self.users:
                raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")
            del self.users[uid]
            self.events.append(("auth", "deleted"))


class FakeOption:
    def __init__(self, last_update_time):
        self.last_update_time = last_update_time


class FakeSnapshot:
    def __init__(self, doc_id, entry):
        self.id = doc_id
        self._data = None if entry is None else dict(entry["data"])
        self.update_time = None if entry is None else entry["time"]

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class FakeDocument:
    def __init__(self, store, collection, doc_id):
        self.store, self.key, self.id = store, (collection, doc_id), doc_id

    def _resolve(self, data):
        return {key: (self.store.server_time() if value is SERVER_TIMESTAMP else value) for key, value in data.items()}

    def get(self, **kwargs):
        self.store.maybe_fail("get", self.key)
        with self.store.lock:
            return FakeSnapshot(self.id, self.store.docs.get(self.key))

    def create(self, data, retry=None, timeout=None):
        self.store.maybe_fail("create", self.key)
        with self.store.lock:
            if self.key in self.store.docs:
                raise google_exceptions.AlreadyExists("Document already exists")
            return self.store.write(self.key, self._resolve(data), "create")

    def update(self, data, option=None, retry=None, timeout=None):
        self.store.maybe_fail("update", self.key, data)
        with self.store.lock:
            entry = self.store.docs.get(self.key)
            if entry is None:
                raise google_exceptions.NotFound("No document to update")
            if option is not None and option.last_update_time != entry["time"]:
                raise google_exceptions.FailedPrecondition("update_time mismatch")
            return self.store.write(self.key, {**entry["data"], **self._resolve(data)}, "update")

    def collections(self):
        self.store.maybe_fail("collections", self.key)
        return list(self.store.subcollections.get(self.key, []))

    def delete(self, option=None, retry=None, timeout=None):
        self.store.maybe_fail("delete", self.key)
        with self.store.lock:
            entry = self.store.docs.get(self.key)
            if entry is not None and option is not None and option.last_update_time != entry["time"]:
                raise google_exceptions.FailedPrecondition("update_time mismatch")
            self.store.docs.pop(self.key, None)
            self.store.events.append((self.key[0], "delete"))


class FakeFirestore:
    def __init__(self, events):
        self.events = events
        self.docs = {}
        self.lock = threading.RLock()
        self.clock = 0
        self.fail = {}            # (operation, collection) -> exception or callable(data) -> exception | None
        self.before_write = None  # hook(key, operation) called before a write is applied
        self.subcollections = {}  # (collection, id) -> list of subcollection names

    def server_time(self):
        return datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc) + timedelta(microseconds=self.clock)

    def maybe_fail(self, operation, key, data=None):
        failure = self.fail.get((operation, key[0]))
        if callable(failure) and not isinstance(failure, BaseException):
            failure = failure(data)
        if failure:
            raise failure

    def write(self, key, data, operation):
        if self.before_write:
            self.before_write(key, operation)
        self.clock += 1
        self.docs[key] = {"data": data, "time": self.clock}
        label = data.get("state") if key[0] == "account_access" else data.get("status") or data.get("outcome")
        self.events.append((key[0], operation, label))
        return SimpleNamespace(update_time=self.clock)

    def collection(self, name):
        return FakeCollection(self, name)

    def batch(self):
        return FakeBatch(self)

    def write_option(self, last_update_time=None):
        return FakeOption(last_update_time)

    # test helpers
    def put(self, collection, doc_id, data):
        with self.lock:
            self.clock += 1
            self.docs[(collection, doc_id)] = {"data": dict(data), "time": self.clock}

    def data(self, collection, doc_id):
        entry = self.docs.get((collection, doc_id))
        return None if entry is None else dict(entry["data"])

    def all(self, collection):
        return {key[1]: dict(entry["data"]) for key, entry in self.docs.items() if key[0] == collection}


class FakeCollection:
    def __init__(self, store, name, field_filter=None):
        self.store, self.name, self.field_filter = store, name, field_filter

    def document(self, doc_id):
        return FakeDocument(self.store, self.name, doc_id)

    def where(self, filter=None):
        return FakeCollection(self.store, self.name, filter)

    def stream(self):
        self.store.maybe_fail("stream", (self.name,))
        with self.store.lock:
            entries = [(key[1], entry) for key, entry in self.store.docs.items() if key[0] == self.name]
        for doc_id, entry in entries:
            if self.field_filter is not None:
                assert self.field_filter.op_string == "=="
                if entry["data"].get(self.field_filter.field_path) != self.field_filter.value:
                    continue
            yield FakeSnapshot(doc_id, entry)


class FakeBatch:
    """An atomic batch: every precondition is checked before any write is applied."""

    def __init__(self, store):
        self.store, self.ops = store, []

    def delete(self, reference, option=None):
        self.ops.append(("delete", reference, None, option))

    def update(self, reference, data, option=None):
        self.ops.append(("update", reference, data, option))

    def commit(self, retry=None, timeout=None):
        self.store.maybe_fail("commit", ("batch",))
        with self.store.lock:
            for kind, reference, _, option in self.ops:
                entry = self.store.docs.get(reference.key)
                if kind == "update" and entry is None:
                    raise google_exceptions.NotFound("No document to update")
                if option is not None and entry is not None and option.last_update_time != entry["time"]:
                    raise google_exceptions.FailedPrecondition("update_time mismatch")
            results = []
            for kind, reference, data, _ in self.ops:
                if kind == "delete":
                    if self.store.docs.pop(reference.key, None) is not None:
                        self.store.events.append((reference.key[0], "delete"))
                    results.append(SimpleNamespace(update_time=None))
                else:
                    entry = self.store.docs[reference.key]
                    results.append(self.store.write(reference.key, {**entry["data"], **reference._resolve(data)}, "update"))
            return results


class CapturedLogs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


# ------------------------------------------------------------------------------ base
class ActionTestBase(unittest.TestCase):
    def setUp(self):
        self.events = Events()
        self.auth = FakeAuth(self.events)
        self.store = FakeFirestore(self.events)
        self.init_actions = self.patch("services.account_action_service.initialize_firebase", return_value=self.store)
        self.patch("services.account_access_service.initialize_firebase", return_value=self.store)
        for name in ("get_user", "update_user", "revoke_refresh_tokens", "delete_user"):
            self.patch(f"services.account_action_service.firebase_auth.{name}", side_effect=getattr(self.auth, name))
        self.sleeps = []
        self.patch("services.account_action_service._sleep", side_effect=lambda seconds: self.sleeps.append(seconds))
        root = logging.getLogger()
        self.logs = CapturedLogs()
        saved_level = root.level
        root.addHandler(self.logs)
        root.setLevel(logging.DEBUG)
        self.addCleanup(lambda: (root.removeHandler(self.logs), root.setLevel(saved_level)))
        self.addCleanup(self.assert_nothing_private_logged)
        self.auth.add(ADMIN_UID, admin=True)

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def assert_nothing_private_logged(self):
        for message in self.logs.messages:
            self.assertNotIn(EMAIL, message)

    def student(self, record=None, disabled=False, uid=TARGET):
        self.auth.add(uid, disabled=disabled)
        if record is not None:
            self.store.put("account_access", uid, record)
        return uid

    def record(self, uid=TARGET):
        return self.store.data("account_access", uid)

    def lock(self, uid=TARGET):
        return self.store.data("account_operations", uid)

    def audits(self):
        return list(self.store.all("account_audit").values())

    def put_lock(self, operation, status="incomplete", lease_seconds=None, uid=TARGET, operation_id="earlier-op"):
        lease = None if lease_seconds is None else datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        self.store.put("account_operations", uid, {
            "operationId": operation_id, "operation": operation, "actorUid": OTHER_ADMIN, "status": status,
            "leaseExpiresAt": lease, "failedStep": "disable_auth" if status == "incomplete" else None,
            "reason": "AUTH_UNAVAILABLE" if status == "incomplete" else None, "previousOperationId": None,
            "startedAt": self.store.server_time(), "updatedAt": self.store.server_time()})

    def assert_error(self, code, function, *args):
        with self.assertRaises(actions.AccountActionError) as ctx:
            function(*args)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(str(ctx.exception), code)
        return ctx.exception

    def changes(self):
        """Account changes only (Auth and account_access), in order."""
        return [event for event in self.events if event[0] in ("auth", "account_access")]


ACTIVE = {"state": "active", "version": 1}
DISABLED = {"state": "disabled", "version": 2}


# ------------------------------------------------------------------------------ view
class ViewTests(ActionTestBase):
    def view(self, uid=TARGET, actor=ADMIN_UID):
        return actions.get_account_view(uid, actor)

    def test_states_and_allowed_actions(self):
        threshold = {"sessionsValidAfter": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        cases = [
            (False, ACTIVE, None, "active", ["disable", "delete"]),
            (True, DISABLED, None, "disabled", ["enable", "delete"]),
            (True, ACTIVE, None, "inconsistent", ["disable", "enable"]),
            (False, DISABLED, None, "inconsistent", ["disable", "enable"]),
            (False, {**ACTIVE, **threshold}, None, "active", ["disable", "delete"]),
            (False, None, None, "unsupported", []),
            (False, {"state": "active", "version": 1, "extra": True}, None, "unsupported", []),
            # M3B-3: a started deletion can only be continued by Delete (never undone).
            (True, {"state": "deleting", "version": 3}, None, "deletion_incomplete", ["delete"]),
            (True, {"state": "deleted", "version": 4}, None, "deletion_incomplete", ["delete"]),
            (False, ACTIVE, ("disable", "running", 60), "in_progress", []),
            (False, ACTIVE, ("disable", "running", -1), "incomplete", ["disable"]),
            (False, DISABLED, ("disable", "incomplete", None), "incomplete", ["disable"]),
            (True, DISABLED, ("enable", "incomplete", None), "incomplete", ["enable", "disable"]),
        ]
        for disabled, record, lock, state, allowed in cases:
            with self.subTest(disabled=disabled, record=record, lock=lock):
                self.store.docs.clear()
                self.student(record=record, disabled=disabled)
                if lock:
                    self.put_lock(lock[0], status=lock[1], lease_seconds=lock[2])
                view = self.view()
                self.assertEqual((view.state, list(view.allowed_actions)), (state, allowed))

    def test_administrators_and_the_caller_are_protected(self):
        self.auth.add(OTHER_ADMIN, admin=True)
        self.store.put("account_access", OTHER_ADMIN, ACTIVE)
        self.assertEqual(self.view(OTHER_ADMIN).state, "protected")
        self.assertEqual(self.view(ADMIN_UID).state, "protected")
        self.assertEqual(self.view(ADMIN_UID).allowed_actions, ())

    def test_the_view_writes_nothing_and_describes_only_allow_listed_fields(self):
        self.student(record={**ACTIVE, "sessionsValidAfter": datetime(2026, 11, 26, 1, 2, 3, tzinfo=timezone.utc)})
        self.put_lock("enable", status="incomplete")
        before = dict(self.store.docs)
        described = actions.describe_view(self.view(), ADMIN_UID)
        self.assertEqual(self.store.docs, before)
        self.assertEqual(set(described), {"uid", "auth_status", "is_admin", "is_self", "record", "issues", "operation",
                                          "state", "allowed_actions"})
        self.assertEqual(described["record"], {"status": "valid", "state": "active", "version": 1,
                                               "sessions_valid_after": "2026-11-26T01:02:03Z"})
        self.assertEqual(set(described["operation"]), {"operation_id", "operation", "status", "failed_step", "reason",
                                                       "started_at", "updated_at", "started_by_you"})
        self.assertFalse(described["operation"]["started_by_you"])
        self.assertNotIn(EMAIL, repr(described))
        self.assertNotIn(OTHER_ADMIN, repr(described), "another administrator's uid is not disclosed")

    def test_lookup_failures(self):
        self.assert_error(actions.USER_NOT_FOUND, self.view)
        self.student(record=ACTIVE)
        self.auth.fail["get_user"] = firebase_exceptions.UnavailableError("down")
        self.assert_error(actions.ACCOUNT_ACTION_UNAVAILABLE, self.view)
        self.auth.fail.clear()
        self.store.fail[("get", "account_access")] = google_exceptions.ServiceUnavailable("down")
        self.assert_error(actions.ACCOUNT_ACTION_UNAVAILABLE, self.view)
        self.store.fail.clear()
        self.store.fail[("get", "account_operations")] = google_exceptions.ServiceUnavailable("down")
        self.assert_error(actions.ACCOUNT_ACTION_UNAVAILABLE, self.view)
        self.assert_error(actions.INVALID_UID, actions.get_account_view, "bad uid\n", ADMIN_UID)


# --------------------------------------------------------------------------- disable
class DisableTests(ActionTestBase):
    def test_disable_restricts_the_record_before_auth_and_records_the_audit(self):
        self.student(record=ACTIVE)
        result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual(self.changes(), [("account_access", "update", "disabled"), ("auth", "disabled")])
        self.assertEqual(self.record(), {"state": "disabled", "version": 2})
        self.assertTrue(self.auth.users[TARGET].disabled)
        self.assertIsNone(self.lock(), "the lock is released")
        self.assertEqual((result.view.state, result.audit_recorded, result.lock_released), ("disabled", True, True))
        [audit] = self.audits()
        self.assertEqual({key: audit[key] for key in ("operationId", "operation", "actorUid", "targetUid", "outcome",
                                                      "failedStep", "reason", "resumesOperationId")},
                         {"operationId": result.operation_id, "operation": "disable", "actorUid": ADMIN_UID,
                          "targetUid": TARGET, "outcome": "completed", "failedStep": None, "reason": None,
                          "resumesOperationId": None})
        self.assertEqual(audit["before"], {"auth": "enabled", "record": "active", "version": 1,
                                           "sessionsValidAfterSet": False})
        self.assertEqual(audit["after"], {"auth": "disabled", "record": "disabled", "version": 2,
                                          "sessionsValidAfterSet": False})
        self.assertIsInstance(audit["startedAt"], datetime)
        self.assertIsInstance(audit["finishedAt"], datetime)
        self.assertNotIn(EMAIL, repr(audit))

    def test_the_caller_and_administrators_are_refused_before_any_change(self):
        self.store.put("account_access", ADMIN_UID, ACTIVE)
        self.assert_error(actions.SELF_ACTION_FORBIDDEN, actions.disable_account, ADMIN_UID, ADMIN_UID)
        self.init_actions.assert_not_called()
        self.auth.add(OTHER_ADMIN, admin=True)
        self.store.put("account_access", OTHER_ADMIN, ACTIVE)
        self.assert_error(actions.ADMIN_TARGET_FORBIDDEN, actions.disable_account, OTHER_ADMIN, ADMIN_UID)
        self.assert_error(actions.ADMIN_TARGET_FORBIDDEN, actions.enable_account, OTHER_ADMIN, ADMIN_UID)
        self.assertEqual(self.changes(), [])
        self.assertFalse(self.auth.users[OTHER_ADMIN].disabled)
        self.assertEqual(self.store.all("account_operations"), {})
        self.assertEqual(self.audits(), [])

    def test_unsupported_records_and_missing_accounts_are_refused(self):
        # Missing and malformed records are unsupported; deletion states (M3B-3) refuse Disable and Enable:
        # a deletion is never undone. Neither kind of record is ever created, repaired or reactivated.
        for record, disabled, code in (
                (None, False, actions.ACCESS_RECORD_UNSUPPORTED),
                ({"state": "active", "version": 1, "updatedAt": 1}, False, actions.ACCESS_RECORD_UNSUPPORTED),
                ({"state": "active", "version": "1"}, False, actions.ACCESS_RECORD_UNSUPPORTED),
                ({"state": "deleting", "version": 3}, True, actions.ACCOUNT_DELETION_IN_PROGRESS),
                ({"state": "deleted", "version": 4}, True, actions.ACCOUNT_DELETION_IN_PROGRESS)):
            with self.subTest(record=record):
                self.store.docs.clear()
                self.student(record=record, disabled=disabled)
                for action in (actions.disable_account, actions.enable_account):
                    self.assert_error(code, action, TARGET, ADMIN_UID)
                self.assertEqual(self.record(), record, "never created, repaired or reactivated")
        self.assert_error(actions.USER_NOT_FOUND, actions.disable_account, "no-such-uid", ADMIN_UID)
        self.assertEqual(self.changes(), [])
        self.assertEqual(self.audits(), [])

    def test_disabling_a_disabled_account_changes_nothing(self):
        self.student(record=DISABLED, disabled=True)
        self.assert_error(actions.ALREADY_DISABLED, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual(self.events, [])

    def test_auth_disabled_with_an_active_record_is_completed_by_downgrading_the_record(self):
        self.student(record=ACTIVE, disabled=True)
        actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual(self.changes(), [("account_access", "update", "disabled")])
        self.assertEqual(self.record(), {"state": "disabled", "version": 2})

    def test_an_auth_failure_leaves_the_record_restricted_and_can_be_resumed(self):
        self.student(record=ACTIVE)
        self.auth.fail["update_user"] = firebase_exceptions.UnavailableError(f"down {EMAIL}")
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.operation, error.failed_step, error.reason), ("disable", "disable_auth", "AUTH_UNAVAILABLE"))
        self.assertEqual(self.record(), {"state": "disabled", "version": 2}, "Firestore access is already closed")
        self.assertFalse(self.auth.users[TARGET].disabled)
        lock = self.lock()
        self.assertEqual((lock["status"], lock["failedStep"], lock["reason"], lock["operationId"]),
                         ("incomplete", "disable_auth", "AUTH_UNAVAILABLE", error.operation_id))
        [audit] = self.audits()
        self.assertEqual((audit["outcome"], audit["failedStep"], audit["reason"]),
                         ("incomplete", "disable_auth", "AUTH_UNAVAILABLE"))
        self.assertEqual(audit["after"]["record"], "disabled")

        view = actions.get_account_view(TARGET, ADMIN_UID)
        self.assertEqual((view.state, view.allowed_actions), ("incomplete", ("disable",)))
        self.assert_error(actions.INCOMPLETE_OPERATION_PENDING, actions.enable_account, TARGET, ADMIN_UID)

        self.auth.fail.clear()
        result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual(result.resumed_operation_id, error.operation_id)
        self.assertTrue(self.auth.users[TARGET].disabled)
        self.assertEqual(self.record(), {"state": "disabled", "version": 2}, "the record is not changed twice")
        self.assertIsNone(self.lock())
        resumed = self.store.data("account_audit", result.operation_id)
        self.assertEqual((resumed["outcome"], resumed["resumesOperationId"], resumed["resumesOperation"]),
                         ("completed", error.operation_id, "disable"))

    def test_a_record_write_failure_is_incomplete_and_changes_nothing_else(self):
        self.student(record=ACTIVE)
        self.store.fail[("update", "account_access")] = google_exceptions.DeadlineExceeded("no answer")
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), ("restrict_record", "STORE_UNAVAILABLE"))
        self.assertFalse(self.auth.users[TARGET].disabled, "Auth is not changed after a failed record write")
        self.assertEqual(self.changes(), [])

    def test_a_record_changed_by_someone_else_is_never_overwritten(self):
        # Reads: 1 = before the lock, 2 = under the lock, 3 = in restrict_record just before its write.
        # A change after read 2 fails the version check; after read 3, the update-time precondition.
        original_read = access.read_record_snapshot
        for change_after_read, version in ((2, 7), (3, 1)):
            with self.subTest(change_after_read=change_after_read):
                self.store.docs.clear()
                self.student(record=ACTIVE)
                reads = []

                def read_then_change(uid, change_after_read=change_after_read, version=version):
                    snapshot = original_read(uid)
                    reads.append(uid)
                    if len(reads) == change_after_read:
                        self.store.put("account_access", TARGET, {"state": "active", "version": version})
                    return snapshot

                with mock.patch("services.account_access_service.read_record_snapshot", side_effect=read_then_change):
                    error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
                self.assertEqual((error.failed_step, error.reason), ("restrict_record", "RECORD_CHANGED"))
                self.assertEqual(self.record(), {"state": "active", "version": version}, "not overwritten")
                self.assertFalse(self.auth.users[TARGET].disabled, "Auth is not changed after the record step failed")
                self.store.docs.pop(("account_operations", TARGET), None)


# ---------------------------------------------------------------------------- enable
class EnableTests(ActionTestBase):
    def test_enable_revokes_sets_the_threshold_waits_and_activates_the_record_last(self):
        self.student(record=DISABLED, disabled=True)
        result = actions.enable_account(TARGET, ADMIN_UID)
        self.assertEqual(self.changes(), [
            ("auth", "revoked"),
            ("account_access", "update", "disabled"),  # sessionsValidAfter set, still disabled
            ("auth", "enabled"),
            ("account_access", "update", "active"),
        ])
        self.assertEqual(self.sleeps, [actions.REVOCATION_MARGIN_SECONDS, actions.ENABLE_SETTLE_SECONDS])
        self.assertGreaterEqual(actions.REVOCATION_MARGIN_SECONDS, 1.0, "revocation is compared in whole seconds")
        self.assertGreaterEqual(actions.ENABLE_SETTLE_SECONDS, 2.0, "the guard's margin after the threshold (FL3)")
        record = self.record()
        self.assertEqual((record["state"], record["version"]), ("active", 4))
        self.assertIsInstance(record["sessionsValidAfter"], datetime)
        self.assertEqual(set(record), {"state", "version", "sessionsValidAfter"}, "no extra fields")
        self.assertFalse(self.auth.users[TARGET].disabled)
        self.assertEqual((result.view.state, result.lock_released), ("active", True))
        self.assertEqual(self.store.data("account_audit", result.operation_id)["after"],
                         {"auth": "enabled", "record": "active", "version": 4, "sessionsValidAfterSet": True})

    def test_the_waits_come_before_the_revocation_and_between_the_threshold_and_auth(self):
        self.student(record=DISABLED, disabled=True)
        self.patch("services.account_action_service._sleep",
                   side_effect=lambda seconds: self.events.append(("sleep", seconds)))
        actions.enable_account(TARGET, ADMIN_UID)
        order = [f"record:{event[2]}" if event[0] == "account_access" else
                 f"sleep:{event[1]}" if event[0] == "sleep" else f"auth:{event[1]}"
                 for event in self.events if event[0] in ("auth", "account_access", "sleep")]
        self.assertEqual(order, [f"sleep:{actions.REVOCATION_MARGIN_SECONDS}", "auth:revoked", "record:disabled",
                                 f"sleep:{actions.ENABLE_SETTLE_SECONDS}", "auth:enabled", "record:active"])

    def test_enabling_an_active_account_changes_nothing(self):
        self.student(record=ACTIVE)
        self.assert_error(actions.ALREADY_ACTIVE, actions.enable_account, TARGET, ADMIN_UID)
        self.assertEqual(self.events, [])

    def test_a_failure_at_any_step_never_leaves_an_active_record(self):
        failures = {
            "revoke_sessions": lambda: self.auth.fail.__setitem__("revoke_refresh_tokens",
                                                                  firebase_exceptions.UnavailableError("down")),
            "set_session_threshold": lambda: self.store.fail.__setitem__(
                ("update", "account_access"), google_exceptions.ServiceUnavailable("down")),
            "enable_auth": lambda: self.auth.fail.__setitem__(
                "update_user", lambda kwargs: firebase_exceptions.UnavailableError("down") if kwargs["disabled"] is False else None),
            "activate_record": lambda: self.store.fail.__setitem__(
                ("update", "account_access"),
                lambda data: google_exceptions.ServiceUnavailable("down") if data.get("state") == "active" else None),
        }
        for step, inject in failures.items():
            with self.subTest(step=step):
                self.store.docs.clear()
                self.auth.fail.clear()
                self.store.fail.clear()
                self.student(record=DISABLED, disabled=True)
                inject()
                error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.enable_account, TARGET, ADMIN_UID)
                self.assertEqual(error.failed_step, step)
                self.assertEqual(self.record()["state"], "disabled", "Firestore access stays closed")
                self.assertEqual(self.lock()["status"], "incomplete")
                view = actions.get_account_view(TARGET, ADMIN_UID)
                self.assertEqual((view.state, view.allowed_actions), ("incomplete", ("enable", "disable")))

    def test_an_incomplete_enable_is_resumed_from_a_fully_disabled_state(self):
        self.student(record=DISABLED, disabled=True)
        self.store.fail[("update", "account_access")] = (
            lambda data: google_exceptions.ServiceUnavailable("down") if data.get("state") == "active" else None)
        first = self.assert_error(actions.OPERATION_INCOMPLETE, actions.enable_account, TARGET, ADMIN_UID)
        self.assertFalse(self.auth.users[TARGET].disabled, "Auth was enabled before the failed activation")
        self.assertEqual(self.record()["state"], "disabled")

        self.store.fail.clear()
        self.events.clear()
        result = actions.enable_account(TARGET, ADMIN_UID)
        self.assertEqual(result.resumed_operation_id, first.operation_id)
        self.assertEqual([event[:3] for event in self.changes()], [
            ("auth", "disabled"),                      # normalised to fully disabled first
            ("auth", "revoked"),
            ("account_access", "update", "disabled"),  # a new threshold
            ("auth", "enabled"),
            ("account_access", "update", "active"),
        ])
        self.assertEqual(self.record()["state"], "active")

    def test_disable_can_cancel_an_incomplete_enable(self):
        self.student(record=DISABLED, disabled=True)
        self.store.fail[("update", "account_access")] = (
            lambda data: google_exceptions.ServiceUnavailable("down") if data.get("state") == "active" else None)
        self.assert_error(actions.OPERATION_INCOMPLETE, actions.enable_account, TARGET, ADMIN_UID)
        self.store.fail.clear()
        result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual(result.view.state, "disabled")
        self.assertTrue(self.auth.users[TARGET].disabled)
        self.assertEqual(self.record()["state"], "disabled")

    def test_a_resumed_enable_that_had_finished_its_changes_is_only_verified(self):
        self.student(record={"state": "active", "version": 4,
                             "sessionsValidAfter": datetime(2026, 11, 26, tzinfo=timezone.utc)})
        self.put_lock("enable", status="incomplete")
        result = actions.enable_account(TARGET, ADMIN_UID)
        self.assertEqual(self.changes(), [])
        self.assertEqual((result.view.state, result.resumed_operation_id), ("active", "earlier-op"))

    def test_enable_from_an_inconsistent_state_restricts_auth_first(self):
        self.student(record=DISABLED, disabled=False)
        actions.enable_account(TARGET, ADMIN_UID)
        self.assertEqual(self.changes()[0], ("auth", "disabled"))
        self.assertEqual(self.record()["state"], "active")


# ----------------------------------------------------------------- locks and audit
class LockAndAuditTests(ActionTestBase):
    def test_a_running_operation_refuses_every_other_action(self):
        self.student(record=ACTIVE)
        self.put_lock("disable", status="running", lease_seconds=60)
        for action in (actions.disable_account, actions.enable_account):
            self.assert_error(actions.OPERATION_IN_PROGRESS, action, TARGET, ADMIN_UID)
        self.assertEqual(self.changes(), [])

    def test_an_expired_lease_counts_as_incomplete_and_can_be_resumed(self):
        self.student(record=ACTIVE)
        self.put_lock("disable", status="running", lease_seconds=-5)
        result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual((result.view.state, result.resumed_operation_id), ("disabled", "earlier-op"))

    def test_a_lock_taken_over_concurrently_is_refused(self):
        # Lock reads: 1 = the view before the lock, 2 = the takeover decision. Another administrator takes
        # the lock over right after read 2, so the takeover's update-time precondition fails.
        self.student(record=ACTIVE)
        self.put_lock("disable", status="incomplete")
        original_get = FakeDocument.get
        store = self.store
        lock_reads = []

        def get_then_race(document, **kwargs):
            snapshot = original_get(document, **kwargs)
            if document.key == ("account_operations", TARGET):
                lock_reads.append(1)
                if len(lock_reads) == 2:
                    store.put("account_operations", TARGET, {**snapshot.to_dict(), "operationId": "someone-else"})
            return snapshot

        with mock.patch.object(FakeDocument, "get", get_then_race):
            self.assert_error(actions.OPERATION_IN_PROGRESS, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual(self.lock()["operationId"], "someone-else", "the other takeover is kept")
        self.assertEqual(self.changes(), [])

    def test_a_lock_that_appears_after_the_check_is_never_touched(self):
        # Another administrator's lock appears between this request's check and its lock acquisition:
        # a running one (any action) or an incomplete Disable (for Enable). It must stay exactly as stored.
        cases = (("running", 60, actions.disable_account, ACTIVE, False, actions.OPERATION_IN_PROGRESS),
                 ("incomplete", None, actions.enable_account, DISABLED, True, actions.INCOMPLETE_OPERATION_PENDING))
        for status, lease, action, record, disabled, code in cases:
            with self.subTest(status=status):
                self.store.docs.clear()
                self.store.fail.clear()
                self.student(record=record, disabled=disabled)
                appeared = {}

                def appear(data, status=status, lease=lease, appeared=appeared):
                    if appeared:
                        return None
                    self.put_lock("disable", status=status, lease_seconds=lease, operation_id="other-admin-op")
                    appeared["entry"] = dict(self.store.docs[("account_operations", TARGET)])
                    return google_exceptions.AlreadyExists("Document already exists")

                self.store.fail[("create", "account_operations")] = appear
                self.assert_error(code, action, TARGET, ADMIN_UID)
                self.assertEqual(self.store.docs[("account_operations", TARGET)], appeared["entry"],
                                 "the other lock is not overwritten, even temporarily (same data and update time)")
                self.assertEqual(self.changes(), [])

    def test_concurrent_requests_change_the_account_once(self):
        self.student(record=ACTIVE)
        workers = 12
        barrier = threading.Barrier(workers)
        outcomes = []

        def attempt():
            barrier.wait()
            try:
                outcomes.append(actions.disable_account(TARGET, ADMIN_UID).view.state)
            except actions.AccountActionError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("disabled"), 1, outcomes)
        self.assertTrue(set(outcomes) <= {"disabled", actions.OPERATION_IN_PROGRESS, actions.ALREADY_DISABLED}, outcomes)
        self.assertEqual(self.record(), {"state": "disabled", "version": 2})
        self.assertEqual(self.changes(), [("account_access", "update", "disabled"), ("auth", "disabled")])
        self.assertEqual([audit["outcome"] for audit in self.audits()], ["completed"])

    def test_no_change_is_made_without_an_audit_record(self):
        self.student(record=ACTIVE)
        self.store.fail[("create", "account_audit")] = google_exceptions.ServiceUnavailable("down")
        self.assert_error(actions.ACCOUNT_ACTION_UNAVAILABLE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual(self.changes(), [])
        self.assertIsNone(self.lock(), "the lock is given back")

    def test_an_incomplete_lock_is_restored_when_a_takeover_cannot_start(self):
        self.student(record=DISABLED)
        self.put_lock("disable", status="incomplete")
        before = self.lock()
        self.store.fail[("create", "account_audit")] = google_exceptions.ServiceUnavailable("down")
        self.assert_error(actions.ACCOUNT_ACTION_UNAVAILABLE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual(self.lock(), before)
        self.assertEqual(self.changes(), [])

    def test_a_missing_audit_outcome_or_lock_release_is_reported_not_hidden(self):
        self.student(record=ACTIVE)
        self.store.fail[("update", "account_audit")] = google_exceptions.ServiceUnavailable("down")
        self.store.fail[("delete", "account_operations")] = google_exceptions.ServiceUnavailable("down")
        result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual((result.view.state, result.audit_recorded, result.lock_released), ("disabled", False, False))

    def test_a_failure_to_record_the_incomplete_state_still_reports_incomplete(self):
        self.student(record=ACTIVE)
        self.auth.fail["update_user"] = firebase_exceptions.UnavailableError("down")
        self.store.fail[("update", "account_operations")] = google_exceptions.ServiceUnavailable("down")
        self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)

    def test_locks_and_audit_records_never_reach_the_access_record(self):
        self.student(record=DISABLED, disabled=True)
        actions.enable_account(TARGET, ADMIN_UID)
        actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual(set(self.record()), {"state", "version", "sessionsValidAfter"})
        self.assertEqual(len(self.audits()), 2)
        for audit in self.audits():
            self.assertEqual(set(audit), {"operationId", "operation", "actorUid", "targetUid", "outcome", "failedStep",
                                          "reason", "resumesOperationId", "resumesOperation", "before", "after",
                                          "startedAt", "finishedAt"})


# -------------------------------------------------------------- record primitives
class RecordPrimitiveTests(ActionTestBase):
    def test_reconciliation_only_downgrades_an_active_record_whose_auth_account_is_inactive(self):
        threshold = datetime(2026, 11, 1, tzinfo=timezone.utc)
        cases = [
            ("disabled", {"state": "active", "version": 3, "sessionsValidAfter": threshold},
             {"state": "disabled", "version": 4, "sessionsValidAfter": threshold}),
            ("missing", ACTIVE, {"state": "disabled", "version": 2}),
            ("enabled", ACTIVE, ACTIVE),
            ("enabled", DISABLED, DISABLED),
            ("disabled", DISABLED, DISABLED),
            ("disabled", {"state": "deleting", "version": 3}, {"state": "deleting", "version": 3}),
            ("missing", {"state": "deleted", "version": 4}, {"state": "deleted", "version": 4}),
            ("disabled", {"state": "active", "version": -1}, {"state": "active", "version": -1}),
            ("disabled", None, None),
        ]
        for auth_state, record, expected in cases:
            with self.subTest(auth=auth_state, record=record):
                self.store.docs.clear()
                self.auth.users.pop(TARGET, None)
                if auth_state != "missing":
                    self.auth.add(TARGET, disabled=auth_state == "disabled")
                if record is not None:
                    self.store.put("account_access", TARGET, record)
                result = access.reconcile_access_record(TARGET)
                self.assertEqual(self.record(), expected)
                self.assertEqual(result.downgraded, expected != record)

    def test_reconciliation_writes_nothing_when_auth_cannot_be_read(self):
        self.student(record=ACTIVE, disabled=True)
        self.auth.fail["get_user"] = firebase_exceptions.UnavailableError("down")
        with self.assertRaises(access.AccountAccessError) as ctx:
            access.reconcile_access_record(TARGET)
        self.assertEqual(ctx.exception.code, access.AUTH_UNAVAILABLE)
        self.assertEqual(self.record(), ACTIVE)

    def test_change_record_state_never_overwrites_a_changed_record(self):
        self.student(record=ACTIVE)
        snapshot = access.read_record_snapshot(TARGET)
        self.store.put("account_access", TARGET, {"state": "deleted", "version": 9})
        with self.assertRaises(access.AccountAccessError) as ctx:
            access.change_record_state(TARGET, snapshot, state="disabled")
        self.assertEqual(ctx.exception.code, access.STALE_RECORD)
        self.assertEqual(self.record(), {"state": "deleted", "version": 9})
        self.store.docs.clear()
        with self.assertRaises(access.AccountAccessError) as ctx:
            access.change_record_state(TARGET, snapshot, state="disabled")
        self.assertEqual(ctx.exception.code, access.STALE_RECORD, "a deleted record is not recreated")
        self.assertIsNone(self.record())

    def test_change_record_state_rejects_other_states_and_unreadable_records(self):
        self.student(record=ACTIVE)
        snapshot = access.read_record_snapshot(TARGET)
        # M3B-3: 'active' may become 'disabled' or 'deleting'; never 'deleted' directly, 'active' again, or unknown.
        for state in ("deleted", "active", "unknown"):
            with self.assertRaises(ValueError):
                access.change_record_state(TARGET, snapshot, state=state)
        with self.assertRaises(ValueError):
            access.change_record_state(TARGET, access.RecordSnapshot(access.RecordLookup("missing")), state="active")
        self.assertEqual(self.record(), ACTIVE)


# --------------------------------------------------------------------------- routes
class RouteTests(ActionTestBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(action_routes.router, prefix=BASE)
        self.client = TestClient(app)
        self.verify = self.patch("core.auth.firebase_auth.verify_id_token", side_effect=fake_verify_id_token)
        self.patch("core.auth._ensure_firebase_app")
        self.ready = self.patch("routes.admin_account_actions._emulator_ready", return_value=True)

    def call(self, method, path, token="admin-token", env=VALID_EMULATOR_ENV):
        headers = bearer(token) if token else {}
        with firebase_env(env):
            return getattr(self.client, method)(f"{BASE}/{path}", headers=headers)

    def test_the_routes_do_not_exist_outside_emulator_mode_and_check_nothing_first(self):
        service = [self.patch(f"routes.admin_account_actions.actions.{name}")
                   for name in ("get_account_view", "disable_account", "enable_account")]
        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}, {"ROUTE2UNIKL_FIREBASE_MODE": "staging"}):
            for method, path in (("get", f"{TARGET}/access"), ("post", f"{TARGET}/disable"), ("post", f"{TARGET}/enable")):
                with self.subTest(env=env, path=path):
                    response = self.call(method, path, env=env)
                    self.assertEqual((response.status_code, response.json()), (404, {"detail": "Not Found"}))
        self.verify.assert_not_called()
        self.ready.assert_not_called()
        for spy in service:
            spy.assert_not_called()

    def test_an_unready_emulator_environment_is_refused(self):
        self.ready.return_value = False
        response = self.call("post", f"{TARGET}/disable")
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (503, "ACCOUNT_ACTION_UNAVAILABLE"))
        self.verify.assert_not_called()

    def test_only_administrators_can_call_the_routes(self):
        self.student(record=ACTIVE)
        for token, status_code in ((None, 401), ("student-token", 403), ("string-admin-token", 403),
                                   ("false-admin-token", 403), ("expired-token", 401)):
            for method, path in (("get", f"{TARGET}/access"), ("post", f"{TARGET}/disable"), ("post", f"{TARGET}/enable")):
                with self.subTest(token=token, path=path):
                    self.assertEqual(self.call(method, path, token=token).status_code, status_code)
        self.assertEqual(self.changes(), [])
        self.assertEqual(self.record(), ACTIVE)

    def test_invalid_uids_are_refused_before_the_service(self):
        spy = self.patch("routes.admin_account_actions.actions.disable_account")
        for uid in ("bad.uid", "x" * 129, "a%20b"):
            with self.subTest(uid=uid):
                self.assertEqual(self.call("post", f"{uid}/disable").status_code, 422)
        spy.assert_not_called()

    def test_access_state_and_actions_through_the_routes(self):
        self.student(record=ACTIVE)
        state = self.call("get", f"{TARGET}/access")
        self.assertEqual(state.status_code, 200)
        self.assertEqual((state.json()["state"], state.json()["allowed_actions"]), ("active", ["disable", "delete"]))

        disabled = self.call("post", f"{TARGET}/disable")
        self.assertEqual(disabled.status_code, 200)
        body = disabled.json()
        self.assertEqual(set(body), {"outcome", "operation", "operation_id", "resumed_operation_id", "audit_recorded",
                                     "lock_released", "account"})
        self.assertEqual((body["outcome"], body["operation"], body["account"]["state"]), ("completed", "disable", "disabled"))
        self.assertNotIn(EMAIL, disabled.text)

        enabled = self.call("post", f"{TARGET}/enable")
        self.assertEqual((enabled.status_code, enabled.json()["account"]["state"]), (200, "active"))
        self.assertIsNotNone(enabled.json()["account"]["record"]["sessions_valid_after"])

    def test_refusals_and_failures_map_to_fixed_codes(self):
        cases = {
            actions.SELF_ACTION_FORBIDDEN: 403, actions.ADMIN_TARGET_FORBIDDEN: 403, actions.USER_NOT_FOUND: 404,
            actions.ACCESS_RECORD_UNSUPPORTED: 409, actions.ALREADY_DISABLED: 409, actions.ALREADY_ACTIVE: 409,
            actions.OPERATION_IN_PROGRESS: 409, actions.INCOMPLETE_OPERATION_PENDING: 409,
            actions.ACCOUNT_ACTION_UNAVAILABLE: 503,
        }
        spy = self.patch("routes.admin_account_actions.actions.disable_account")
        for code, status_code in cases.items():
            with self.subTest(code=code):
                spy.side_effect = actions.AccountActionError(code, operation="disable")
                response = self.call("post", f"{TARGET}/disable")
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(set(response.json()["detail"]), {"code", "message"})
                self.assertEqual(response.json()["detail"]["code"], code)

    def test_an_incomplete_operation_is_reported_with_its_step_and_reason(self):
        self.student(record=ACTIVE)
        self.auth.fail["update_user"] = firebase_exceptions.UnavailableError(f"Firebase says {EMAIL}")
        response = self.call("post", f"{TARGET}/disable")
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual({key: detail[key] for key in ("code", "operation", "failed_step", "reason")},
                         {"code": "OPERATION_INCOMPLETE", "operation": "disable", "failed_step": "disable_auth",
                          "reason": "AUTH_UNAVAILABLE"})
        self.assertEqual(detail["operation_id"], self.lock()["operationId"])
        self.assertNotIn(EMAIL, response.text)
        self.assertNotIn("Firebase says", response.text)

        access_state = self.call("get", f"{TARGET}/access").json()
        self.assertEqual((access_state["state"], access_state["operation"]["status"], access_state["operation"]["started_by_you"]),
                         ("incomplete", "incomplete", True))

    def test_main_mounts_the_routes_only_in_emulator_mode(self):
        def action_paths(env):
            sys.modules.pop("main", None)
            try:
                with firebase_env(env), mock.patch("core.firebase.initialize_firebase", return_value=None), \
                        contextlib.redirect_stdout(io.StringIO()):
                    main = importlib.import_module("main")
                return sorted(path for path in main.app.openapi()["paths"]
                              if path.endswith(("/access", "/disable", "/enable")))
            finally:
                sys.modules.pop("main", None)

        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}, {"ROUTE2UNIKL_FIREBASE_MODE": "staging"}):
            with self.subTest(env=env):
                self.assertEqual(action_paths(env), [])
        self.assertEqual(action_paths(VALID_EMULATOR_ENV), [f"{BASE}/{{uid}}/access", f"{BASE}/{{uid}}/disable",
                                                            f"{BASE}/{{uid}}/enable"])


if __name__ == "__main__":
    unittest.main()
