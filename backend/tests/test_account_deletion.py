# backend/tests/test_account_deletion.py
"""
M3B-3: admin Delete Student Account (services/account_action_service.py delete_account and
list_incomplete_deletions, services/account_access_service.py delete_documents_during_deletion,
routes/admin_account_actions.py POST .../delete and GET .../incomplete-deletions) and the student-data
access check (core/student_access.py) applied to routes/assessment.py.

Run from the backend directory with the other backend tests:
    python -m unittest discover -s tests -t . -v

Safety: Firebase Authentication and Firestore are the in-memory fakes of test_account_actions.py (atomic
batches with preconditions, create-if-absent, update-time preconditions). No network, emulator,
credential or AI provider is used: the assessment handlers' AI and recommendation calls are replaced by
spies that fail the test if reached when they must not be.
"""
import contextlib
import importlib
import io
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
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402

from core import student_access  # noqa: E402
from routes import admin_account_actions as action_routes  # noqa: E402
from routes import assessment as assessment_routes  # noqa: E402
from services import account_access_service as access  # noqa: E402
from services import account_action_service as actions  # noqa: E402
from tests.test_account_actions import (  # noqa: E402
    ACTIVE, DISABLED, EMAIL, OTHER_ADMIN, TARGET, ActionTestBase)
from tests.test_auth import ADMIN_UID, STUDENT_UID, bearer, fake_verify_id_token  # noqa: E402
from tests.test_firebase_config import VALID_EMULATOR_ENV, firebase_env  # noqa: E402

DATA = actions.STUDENT_DATA_COLLECTIONS
ALL_PRESENT = {name: True for name in DATA}
ALL_ABSENT = {name: False for name in DATA}
EMULATOR_MODE_CHECK = student_access._emulator_mode


class DeletionTestBase(ActionTestBase):
    def with_data(self, uid=TARGET, collections=DATA):
        for name in collections:
            self.store.put(name, uid, {"marker": f"{name}-content"})

    def data(self, uid=TARGET):
        return {name: self.store.data(name, uid) is not None for name in DATA}

    def delete(self, uid=TARGET, confirm=None):
        return actions.delete_account(uid, ADMIN_UID, uid if confirm is None else confirm)

    def timeline(self):
        """Every change to Auth, the record and the student's documents, in order."""
        kept = ("auth", "account_access", *DATA)
        return [event[:3] if event[0] == "account_access" else event[:2] for event in self.events if event[0] in kept]


# ------------------------------------------------------------------------- deletion flow
class DeletionFlowTests(DeletionTestBase):
    def test_an_active_student_is_deleted_in_order_and_verified(self):
        self.student(record=ACTIVE)
        self.with_data()
        result = actions.delete_account(TARGET, ADMIN_UID, TARGET)

        self.assertEqual(self.timeline(), [
            ("account_access", "update", "deleting"),   # Firestore and backend access closed first
            ("auth", "disabled"),                       # no sign-in, no token refresh
            ("users", "delete"), ("results", "delete"), ("ai_assessments", "delete"),
            ("account_access", "update", "deleting"),   # the same atomic batch fences the record
            ("auth", "deleted"),                        # only after the data is confirmed gone
            ("account_access", "update", "deleted"),    # the tombstone, last
        ])
        self.assertNotIn(TARGET, self.auth.users)
        self.assertEqual(self.data(), ALL_ABSENT)
        self.assertEqual(self.record(), {"state": "deleted", "version": 4})
        self.assertIsNone(self.lock())
        self.assertEqual((result.operation, result.view.state, result.view.auth_status, result.audit_recorded,
                          result.lock_released), ("delete", "deleted", "missing", True, True))
        [audit] = self.audits()
        self.assertEqual((audit["operation"], audit["outcome"], audit["targetUid"], audit["actorUid"]),
                         ("delete", "completed", TARGET, ADMIN_UID))
        self.assertEqual((audit["dataPresentBefore"], audit["dataPresentAfter"]), (ALL_PRESENT, ALL_ABSENT))
        self.assertEqual(audit["after"], {"auth": "missing", "record": "deleted", "version": 4,
                                          "sessionsValidAfterSet": False})

    def test_a_disabled_student_is_deleted(self):
        self.student(record=DISABLED, disabled=True)
        self.with_data(collections=("users",))
        self.delete()
        self.assertNotIn(("auth", "disabled"), self.timeline(), "already disabled")
        self.assertEqual(self.data(), ALL_ABSENT)
        self.assertEqual(self.record(), {"state": "deleted", "version": 5})
        self.assertEqual(self.audits()[0]["dataPresentBefore"], {"users": True, "results": False, "ai_assessments": False})

    def test_a_student_without_documents_is_deleted_without_an_empty_batch(self):
        self.student(record=ACTIVE)
        self.delete()
        self.assertEqual(self.record(), {"state": "deleted", "version": 3})
        self.assertNotIn(TARGET, self.auth.users)

    def test_the_confirmation_must_name_the_target_and_is_checked_before_firebase(self):
        self.student(record=ACTIVE)
        self.with_data()
        for confirm in ("other-uid", "", TARGET.upper(), f" {TARGET}", 123, None):
            with self.subTest(confirm=confirm):
                with self.assertRaises(actions.AccountActionError) as ctx:
                    actions.delete_account(TARGET, ADMIN_UID, confirm)
                self.assertEqual(ctx.exception.code, actions.DELETE_CONFIRMATION_MISMATCH)
        self.init_actions.assert_not_called()
        self.assertEqual(self.timeline(), [])
        self.assertEqual(self.data(), ALL_PRESENT)

    def test_the_caller_and_administrators_are_never_deleted(self):
        self.assert_error(actions.SELF_ACTION_FORBIDDEN, actions.delete_account, ADMIN_UID, ADMIN_UID, ADMIN_UID)
        self.init_actions.assert_not_called()
        self.auth.add(OTHER_ADMIN, admin=True)
        self.store.put("account_access", OTHER_ADMIN, ACTIVE)
        self.with_data(OTHER_ADMIN)
        self.assert_error(actions.ADMIN_TARGET_FORBIDDEN, actions.delete_account, OTHER_ADMIN, ADMIN_UID, OTHER_ADMIN)
        self.assertIn(OTHER_ADMIN, self.auth.users)
        self.assertEqual(self.data(OTHER_ADMIN), ALL_PRESENT)
        self.assertEqual(self.timeline(), [])
        self.assertEqual(self.audits(), [])

    def test_unsupported_inconsistent_and_busy_accounts_are_refused(self):
        cases = [
            (None, False, None, actions.ACCESS_RECORD_UNSUPPORTED),                          # legacy: no record
            ({"state": "active", "version": 1, "x": 1}, False, None, actions.ACCESS_RECORD_UNSUPPORTED),
            (DISABLED, False, None, actions.DELETE_NOT_ALLOWED),                             # inconsistent
            (ACTIVE, True, None, actions.DELETE_NOT_ALLOWED),                                # inconsistent
            (DISABLED, True, "disable", actions.INCOMPLETE_OPERATION_PENDING),               # finish it first
            (DISABLED, True, "enable", actions.INCOMPLETE_OPERATION_PENDING),
        ]
        for record, disabled, lock, code in cases:
            with self.subTest(record=record, disabled=disabled, lock=lock):
                self.store.docs.clear()
                self.student(record=record, disabled=disabled)
                self.with_data()
                if lock:
                    self.put_lock(lock, status="incomplete")
                self.assert_error(code, self.delete)
                self.assertEqual(self.record(), record, "records are never created, repaired or deleted here")
                self.assertEqual(self.data(), ALL_PRESENT)
                self.assertIn(TARGET, self.auth.users)
        self.assert_error(actions.USER_NOT_FOUND, self.delete, "no-such-uid")
        self.assertEqual(self.timeline(), [])

    def test_a_deleted_account_cannot_be_deleted_again_or_disabled_or_enabled(self):
        self.student(record=ACTIVE)
        self.delete()
        self.assert_error(actions.ACCOUNT_DELETED, self.delete)
        for action in (actions.disable_account, actions.enable_account):
            self.assert_error(actions.ACCOUNT_DELETED, action, TARGET, ADMIN_UID)
        self.assertEqual(self.record(), {"state": "deleted", "version": 3})

    def test_the_data_batch_is_only_fenced_by_a_record_in_deleting(self):
        # The primitive refuses by itself, whatever the caller checked: no data deleted, nothing written.
        self.with_data()
        for record in (ACTIVE, DISABLED, {"state": "deleted", "version": 4}, {"state": "deleting", "version": 2, "x": 1}):
            with self.subTest(record=record):
                self.store.put("account_access", TARGET, record)
                snapshot = access.read_record_snapshot(TARGET)
                with self.assertRaises(ValueError):
                    access.delete_documents_during_deletion(TARGET, snapshot, DATA)
                self.assertEqual(self.data(), ALL_PRESENT)
                self.assertEqual(self.record(), record)
        self.store.put("account_access", TARGET, {"state": "deleting", "version": 2})
        with self.assertRaises(ValueError):
            access.delete_documents_during_deletion(TARGET, access.read_record_snapshot(TARGET), ())
        change = access.delete_documents_during_deletion(TARGET, access.read_record_snapshot(TARGET), DATA)
        self.assertEqual((change.version, self.data(), self.record()), (3, ALL_ABSENT, {"state": "deleting", "version": 3}))

    def test_the_tombstone_and_deleting_records_are_never_reactivated(self):
        self.student(record={"state": "deleting", "version": 2})
        snapshot = access.read_record_snapshot(TARGET)
        for state in ("active", "disabled", "deleting"):
            with self.assertRaises(ValueError):
                access.change_record_state(TARGET, snapshot, state=state)
        self.store.put("account_access", TARGET, {"state": "deleted", "version": 3})
        snapshot = access.read_record_snapshot(TARGET)
        for state in ("active", "disabled", "deleting", "deleted"):
            with self.assertRaises(ValueError):
                access.change_record_state(TARGET, snapshot, state=state)
        self.assertFalse(access.reconcile_access_record(TARGET).downgraded)
        self.assertEqual(self.record(), {"state": "deleted", "version": 3})


# ------------------------------------------------------------- failures and recovery
class DeletionRecoveryTests(DeletionTestBase):
    STEP_NAMES = [name for name, _ in actions._DELETE_STEPS]

    def assert_invariants_after_failure(self, failed_step):
        index = self.STEP_NAMES.index(failed_step)
        record = self.record()
        if index > self.STEP_NAMES.index(actions.STEP_MARK_DELETING):
            self.assertIn(record["state"], ("deleting", "deleted"), "never reopened after mark_deleting")
        if index <= self.STEP_NAMES.index(actions.STEP_DELETE_DATA):
            self.assertEqual(self.data(), ALL_PRESENT, "data untouched before (or in) a failed deletion batch")
        if index <= self.STEP_NAMES.index(actions.STEP_DELETE_AUTH):
            self.assertIn(TARGET, self.auth.users, "Auth is deleted only after the data removal is confirmed")
        self.assertEqual(self.lock()["status"], "incomplete")
        self.assertEqual(self.lock()["failedStep"], failed_step)
        [audit] = [a for a in self.audits() if a["outcome"] == "incomplete"]
        self.assertEqual(audit["failedStep"], failed_step)

    def assert_completed(self):
        self.assertNotIn(TARGET, self.auth.users)
        self.assertEqual(self.data(), ALL_ABSENT)
        self.assertEqual(self.record()["state"], "deleted")
        self.assertIsNone(self.lock())

    def test_a_failure_at_every_step_is_recorded_and_the_same_delete_resumes_it(self):
        original_steps = list(actions._DELETE_STEPS)
        for failing in self.STEP_NAMES:
            with self.subTest(step=failing):
                self.store.docs.clear()
                self.auth.users.pop(TARGET, None)
                self.student(record=ACTIVE)
                self.with_data()
                calls = {"n": 0}

                def fail_once(run, failing=failing, original=dict(original_steps)):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        raise actions._StepFailure(actions.REASON_STORE_UNAVAILABLE)
                    return original[failing](run)

                steps = [(name, fail_once if name == failing else fn) for name, fn in original_steps]
                with mock.patch.object(actions, "_DELETE_STEPS", steps):
                    error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
                    self.assertEqual((error.failed_step, error.reason), (failing, "STORE_UNAVAILABLE"))
                    self.assert_invariants_after_failure(failing)
                    view = actions.get_account_view(TARGET, ADMIN_UID)
                    self.assertEqual(view.allowed_actions, ("delete",), "only the deletion can continue")
                    result = self.delete()
                self.assertEqual(result.resumed_operation_id, error.operation_id)
                self.assert_completed()

    def test_auth_deleted_but_the_final_update_failed_is_still_found_and_resumable(self):
        self.student(record=ACTIVE)
        self.with_data()
        self.store.fail[("update", "account_access")] = (
            lambda data: google_exceptions.ServiceUnavailable("down") if data.get("state") == "deleted" else None)
        error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual(error.failed_step, actions.STEP_FINALIZE_RECORD)
        self.assertNotIn(TARGET, self.auth.users, "Auth already deleted")
        self.assertEqual(self.data(), ALL_ABSENT)
        self.assertEqual(self.record()["state"], "deleting")

        view = actions.get_account_view(TARGET, ADMIN_UID)
        self.assertEqual((view.state, view.auth_status, view.allowed_actions),
                         ("deletion_incomplete", "missing", ("delete",)))
        listed = actions.list_incomplete_deletions(ADMIN_UID)
        self.assertEqual([item.uid for item in listed], [TARGET])

        self.store.fail.clear()
        self.delete()
        self.assert_completed()
        self.assertEqual(actions.list_incomplete_deletions(ADMIN_UID), [])

    def test_the_data_deletion_is_all_or_nothing(self):
        self.student(record=ACTIVE)
        self.with_data()
        self.store.fail[("commit", "batch")] = google_exceptions.DeadlineExceeded("no answer")
        error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_DELETE_DATA, "STORE_UNAVAILABLE"))
        self.assertEqual(self.data(), ALL_PRESENT, "no document deleted")
        self.assertIn(TARGET, self.auth.users)

    def test_a_record_changed_before_the_batch_stops_the_deletion_without_deleting(self):
        self.student(record=ACTIVE)
        self.with_data()
        original = access.delete_documents_during_deletion

        def change_then_delete(uid, snapshot, collections):
            self.store.put("account_access", TARGET, {"state": "deleting", "version": 9})
            return original(uid, snapshot, collections)

        with mock.patch("services.account_access_service.delete_documents_during_deletion", side_effect=change_then_delete):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_DELETE_DATA, "RECORD_CHANGED"))
        self.assertEqual(self.data(), ALL_PRESENT)
        self.assertIn(TARGET, self.auth.users)

    def test_nested_data_stops_the_deletion_before_anything_is_deleted(self):
        self.student(record=ACTIVE)
        self.with_data()
        self.store.subcollections[("users", TARGET)] = ["notes"]
        error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_CHECK_NESTED_DATA, "NESTED_DATA"))
        self.assertEqual(self.data(), ALL_PRESENT)
        self.assertIn(TARGET, self.auth.users)

    def test_remaining_data_is_detected_and_auth_is_not_deleted(self):
        self.student(record=ACTIVE)
        self.with_data()
        original = access.delete_documents_during_deletion
        # a batch that (wrongly) misses one document: the independent re-read must catch it
        with mock.patch("services.account_access_service.delete_documents_during_deletion",
                        side_effect=lambda uid, snapshot, collections: original(uid, snapshot, ("users", "ai_assessments"))):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_CONFIRM_DATA_REMOVED, "DATA_REMAINS"))
        self.assertIn(TARGET, self.auth.users)
        self.delete()  # resumed: the remaining document is deleted, then Auth
        self.assert_completed()

    def test_a_step_that_silently_does_nothing_is_caught_by_the_verification(self):
        for silent in (actions.STEP_DELETE_AUTH, actions.STEP_FINALIZE_RECORD):
            with self.subTest(step=silent):
                self.store.docs.clear()
                self.auth.users.pop(TARGET, None)
                self.student(record=ACTIVE)
                steps = [(name, (lambda run: None) if name == silent else fn) for name, fn in actions._DELETE_STEPS]
                with mock.patch.object(actions, "_DELETE_STEPS", steps):
                    error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
                self.assertEqual((error.failed_step, error.reason), (actions.STEP_VERIFY, "UNEXPECTED_STATE"))
                self.assertEqual([a["outcome"] for a in self.audits()], ["incomplete"], "never reported as success")
                self.delete()  # resumed with the real steps
                self.assert_completed()

    def test_data_reappearing_before_verification_is_never_reported_as_success(self):
        # Not reachable through the application (the guard denies browser writes once the record is
        # 'deleting', and no backend route writes these documents), but never hidden if it happens.
        self.student(record=ACTIVE)
        self.with_data()
        original = actions._delete_auth

        def delete_auth_then_reappear(run):
            original(run)
            self.store.put("results", TARGET, {"marker": "late write"})

        steps = [(name, delete_auth_then_reappear if name == actions.STEP_DELETE_AUTH else fn)
                 for name, fn in actions._DELETE_STEPS]
        with mock.patch.object(actions, "_DELETE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_VERIFY, "DATA_REMAINS"))
        [audit] = self.audits()
        self.assertEqual(audit["dataPresentAfter"], {"users": False, "results": True, "ai_assessments": False})
        # The tombstone is final, so a resume does not delete the late document: it reports it, never success.
        error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_CONFIRM_DATA_REMOVED, "DATA_REMAINS"))
        self.assertEqual(actions.get_account_view(TARGET, ADMIN_UID).state, "deletion_incomplete")

    def test_real_failures_of_auth_and_store_calls_are_resumable(self):
        cases = {
            actions.STEP_MARK_DELETING: lambda: self.store.fail.__setitem__(
                ("update", "account_access"),
                lambda data: google_exceptions.ServiceUnavailable("down") if data.get("state") == "deleting" else None),
            actions.STEP_DISABLE_AUTH: lambda: self.auth.fail.__setitem__(
                "update_user", firebase_exceptions.UnavailableError("down")),
            actions.STEP_CHECK_NESTED_DATA: lambda: self.store.fail.__setitem__(
                ("collections", "users"), google_exceptions.ServiceUnavailable("down")),
            actions.STEP_DELETE_AUTH: lambda: self.auth.fail.__setitem__(
                "delete_user", firebase_exceptions.UnavailableError("down")),
        }
        for step, inject in cases.items():
            with self.subTest(step=step):
                self.store.docs.clear()
                self.store.fail.clear()
                self.auth.fail.clear()
                self.auth.users.pop(TARGET, None)
                self.student(record=ACTIVE)
                self.with_data()
                inject()
                error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
                self.assertEqual(error.failed_step, step)
                self.store.fail.clear()
                self.auth.fail.clear()
                self.delete()
                self.assert_completed()


# ------------------------------------------------------- administrator claim during deletion
class AdminClaimDuringDeletionTests(DeletionTestBase):
    def test_an_admin_claim_appearing_before_data_deletion_stops_it_with_data_intact(self):
        self.student(record=ACTIVE)
        self.with_data()
        original = self.auth.update_user

        def disable_then_promote(uid, **kwargs):
            original(uid, **kwargs)
            self.auth.users[uid].custom_claims = {"admin": True}  # granted elsewhere, mid-deletion

        self.patch("services.account_action_service.firebase_auth.update_user", side_effect=disable_then_promote)
        error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_CHECK_ADMIN_BEFORE_DATA, "ADMIN_TARGET"))
        self.assertEqual(self.data(), ALL_PRESENT, "an administrator's data is never deleted")
        self.assertIn(TARGET, self.auth.users)
        self.assertEqual(actions.get_account_view(TARGET, ADMIN_UID).state, "protected")
        self.assert_error(actions.ADMIN_TARGET_FORBIDDEN, self.delete)
        self.assertEqual([a["outcome"] for a in self.audits()], ["incomplete"], "never reported as success")

    def test_an_admin_claim_appearing_before_auth_deletion_keeps_the_auth_account(self):
        self.student(record=ACTIVE)
        self.with_data()
        original = access.delete_documents_during_deletion

        def delete_then_promote(uid, snapshot, collections):
            change = original(uid, snapshot, collections)
            self.auth.users[uid].custom_claims = {"admin": True}
            return change

        with mock.patch("services.account_access_service.delete_documents_during_deletion", side_effect=delete_then_promote):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_CHECK_ADMIN_BEFORE_AUTH, "ADMIN_TARGET"))
        self.assertIn(TARGET, self.auth.users, "the Auth account of an administrator is never deleted")
        self.assertNotIn(("auth", "deleted"), self.timeline())


# ----------------------------------------------------------------------- locks (M1)
class DeletionLockTests(DeletionTestBase):
    def put_delete_lock(self, status, lease_offset_seconds):
        self.put_lock("delete", status=status, lease_seconds=lease_offset_seconds, operation_id="other-deletion")

    def test_a_running_deletion_cannot_be_taken_over_until_lease_and_grace_have_passed(self):
        self.student(record={"state": "deleting", "version": 2}, disabled=True)
        self.with_data()
        # lease expired 10 minutes ago, but the grace period (30 min) has not passed: may still be running
        self.put_delete_lock("running", -600)
        self.assert_error(actions.OPERATION_IN_PROGRESS, self.delete)
        self.assertEqual(actions.get_account_view(TARGET, ADMIN_UID).state, "in_progress")
        self.assertEqual(self.data(), ALL_PRESENT)
        # beyond lease + grace: treated as abandoned and resumed
        self.put_delete_lock("running", -(actions.DELETE_TAKEOVER_GRACE_SECONDS + 60))
        result = self.delete()
        self.assertEqual(result.resumed_operation_id, "other-deletion")
        self.assertEqual(self.data(), ALL_ABSENT)

    def test_the_lease_is_renewed_before_every_step(self):
        self.student(record=ACTIVE)
        renewals = []
        original = actions._renew_lock
        self.patch("services.account_action_service._renew_lock",
                   side_effect=lambda db, held: (renewals.append(1), original(db, held))[1])
        self.delete()
        self.assertEqual(len(renewals), len(actions._DELETE_STEPS) + 1, "every step and the verification")

    def test_a_lost_lock_stops_the_deletion_before_its_next_change(self):
        self.student(record=ACTIVE)
        self.with_data()
        original = actions._mark_deleting

        def mark_then_lose_lock(run):
            original(run)
            stolen = self.lock()
            self.store.put("account_operations", TARGET, {**stolen, "operationId": "someone-else"})

        steps = [(name, mark_then_lose_lock if name == actions.STEP_MARK_DELETING else fn)
                 for name, fn in actions._DELETE_STEPS]
        with mock.patch.object(actions, "_DELETE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, self.delete)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_DISABLE_AUTH, "LOCK_LOST"))
        self.assertNotIn(("auth", "disabled"), self.timeline(), "no change after the lock was lost")
        self.assertEqual(self.lock()["operationId"], "someone-else", "the other process's lock is left alone")
        self.assertEqual(self.audits()[0]["reason"], "LOCK_LOST")

    def test_other_operations_never_take_over_a_deletion(self):
        self.student(record={"state": "deleting", "version": 2}, disabled=True)
        self.put_delete_lock("incomplete", None)
        for action in (actions.disable_account, actions.enable_account):
            self.assert_error(actions.ACCOUNT_DELETION_IN_PROGRESS, action, TARGET, ADMIN_UID)
        self.assertEqual(self.lock()["operationId"], "other-deletion")

    def test_a_lock_that_appears_after_the_check_is_never_touched(self):
        # Another administrator's incomplete lock appears between this request's check and its lock
        # acquisition. Disable/Enable never take over a deletion; Delete never takes over another operation.
        delete = lambda uid, actor: actions.delete_account(uid, actor, uid)  # noqa: E731
        cases = ((actions.disable_account, ACTIVE, False, "delete", actions.ACCOUNT_DELETION_IN_PROGRESS),
                 (actions.enable_account, DISABLED, True, "delete", actions.ACCOUNT_DELETION_IN_PROGRESS),
                 (delete, ACTIVE, False, "disable", actions.INCOMPLETE_OPERATION_PENDING),
                 (delete, DISABLED, True, "enable", actions.INCOMPLETE_OPERATION_PENDING))
        for action, record, disabled, lock_operation, code in cases:
            with self.subTest(lock=lock_operation, code=code):
                self.store.docs.clear()
                self.store.fail.clear()
                self.student(record=record, disabled=disabled)
                self.with_data()
                appeared = {}

                def appear(data, lock_operation=lock_operation, appeared=appeared):
                    if appeared:
                        return None
                    self.put_lock(lock_operation, status="incomplete", operation_id="other-admin-op")
                    appeared["entry"] = dict(self.store.docs[("account_operations", TARGET)])
                    return google_exceptions.AlreadyExists("Document already exists")

                self.store.fail[("create", "account_operations")] = appear
                self.assert_error(code, action, TARGET, ADMIN_UID)
                self.assertEqual(self.store.docs[("account_operations", TARGET)], appeared["entry"],
                                 "the other lock is not overwritten, even temporarily (same data and update time)")
                self.assertEqual(self.record(), record)
                self.assertEqual(self.data(), ALL_PRESENT)

    def test_concurrent_deletions_delete_once(self):
        self.student(record=ACTIVE)
        self.with_data()
        workers = 10
        barrier = threading.Barrier(workers)
        outcomes = []

        def attempt():
            barrier.wait()
            try:
                outcomes.append(self.delete().view.state)
            except actions.AccountActionError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("deleted"), 1, outcomes)
        self.assertTrue(set(outcomes) <= {"deleted", actions.OPERATION_IN_PROGRESS, actions.ACCOUNT_DELETED}, outcomes)
        self.assertEqual(self.timeline().count(("auth", "deleted")), 1)
        self.assertEqual([a["outcome"] for a in self.audits()], ["completed"])


# -------------------------------------------------------------- listing and privacy
class IncompleteDeletionListTests(DeletionTestBase):
    def test_only_unfinished_deletions_are_listed_without_personal_data(self):
        self.student(record=ACTIVE, uid="active-student")
        self.student(record={"state": "deleting", "version": 2}, disabled=True, uid="deleting-with-auth")
        self.store.put("account_access", "deleting-no-auth", {"state": "deleting", "version": 3})
        self.store.put("account_access", "fully-deleted", {"state": "deleted", "version": 4})
        self.put_lock("delete", status="incomplete", uid="deleting-no-auth", operation_id="op-x")
        self.put_lock("disable", status="incomplete", uid="active-student")
        items = actions.list_incomplete_deletions(ADMIN_UID)
        self.assertEqual([(i.uid, i.state, i.auth_status) for i in items],
                         [("deleting-no-auth", "deletion_incomplete", "missing"),
                          ("deleting-with-auth", "deletion_incomplete", "disabled")])
        described = [actions.describe_view(i, ADMIN_UID) for i in items]
        self.assertNotIn(EMAIL, repr(described))

    def test_audit_records_hold_no_personal_data_or_content(self):
        self.student(record=ACTIVE)
        self.with_data()
        self.delete()
        [audit] = self.audits()
        self.assertNotIn(EMAIL, repr(audit))
        self.assertNotIn("content", repr(audit), "document contents are never copied")
        self.assertEqual(set(audit["dataPresentBefore"]), set(DATA))


# ---------------------------------------------------------------------------- routes
class DeletionRouteTests(DeletionTestBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(action_routes.router, prefix="/api/admin/users")
        app.include_router(action_routes.operations_router, prefix="/api/admin/account-operations")
        self.client = TestClient(app)
        self.verify = self.patch("core.auth.firebase_auth.verify_id_token", side_effect=fake_verify_id_token)
        self.patch("core.auth._ensure_firebase_app")
        self.ready = self.patch("routes.admin_account_actions._emulator_ready", return_value=True)

    def post_delete(self, uid=TARGET, body=None, token="admin-token", env=VALID_EMULATOR_ENV):
        with firebase_env(env):
            return self.client.post(f"/api/admin/users/{uid}/delete", headers=bearer(token) if token else {},
                                    json={"confirm_uid": uid} if body is None else body)

    def test_delete_through_the_route(self):
        self.student(record=ACTIVE)
        self.with_data()
        response = self.post_delete()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["operation"], body["account"]["state"], body["account"]["auth_status"]),
                         ("delete", "deleted", "missing"))
        self.assertNotIn(EMAIL, response.text)
        self.assertEqual(self.data(), ALL_ABSENT)

    def test_the_body_must_confirm_the_same_account(self):
        self.student(record=ACTIVE)
        self.with_data()
        for body, status_code, code in (({"confirm_uid": "other"}, 422, "DELETE_CONFIRMATION_MISMATCH"),
                                        ({}, 422, None), ({"confirm_uid": TARGET, "force": True}, 422, None),
                                        ({"confirm_uid": ""}, 422, None)):
            with self.subTest(body=body):
                response = self.post_delete(body=body)
                self.assertEqual(response.status_code, status_code)
                if code:
                    self.assertEqual(response.json()["detail"]["code"], code)
        with firebase_env(VALID_EMULATOR_ENV):
            self.assertEqual(self.client.post(f"/api/admin/users/{TARGET}/delete", headers=bearer("admin-token")).status_code, 422)
        self.assertEqual(self.data(), ALL_PRESENT)
        self.assertIn(TARGET, self.auth.users)

    def test_only_administrators_and_only_in_emulator_mode(self):
        self.student(record=ACTIVE)
        self.with_data()
        self.assertEqual(self.post_delete(token=None).status_code, 401)
        self.assertEqual(self.post_delete(token="student-token").status_code, 403)
        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}):
            with self.subTest(env=env):
                self.assertEqual(self.post_delete(env=env).status_code, 404)
                with firebase_env(env):
                    listed = self.client.get("/api/admin/account-operations/incomplete-deletions",
                                             headers=bearer("admin-token"))
                self.assertEqual(listed.status_code, 404)
        self.assertEqual(self.data(), ALL_PRESENT)

    def test_incomplete_deletions_route(self):
        self.store.put("account_access", "gone-student", {"state": "deleting", "version": 3})
        with firebase_env(VALID_EMULATOR_ENV):
            response = self.client.get("/api/admin/account-operations/incomplete-deletions", headers=bearer("admin-token"))
            student = self.client.get("/api/admin/account-operations/incomplete-deletions", headers=bearer("student-token"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([(i["uid"], i["state"], i["allowed_actions"]) for i in response.json()["items"]],
                         [("gone-student", "deletion_incomplete", ["delete"])])
        self.assertEqual(student.status_code, 403)

    def test_main_mounts_the_deletion_routes_only_in_emulator_mode(self):
        def paths(env):
            sys.modules.pop("main", None)
            try:
                with firebase_env(env), mock.patch("core.firebase.initialize_firebase", return_value=None), \
                        contextlib.redirect_stdout(io.StringIO()):
                    main = importlib.import_module("main")
                return sorted(p for p in main.app.openapi()["paths"] if p.endswith(("/delete", "/incomplete-deletions")))
            finally:
                sys.modules.pop("main", None)

        self.assertEqual(paths({"ROUTE2UNIKL_FIREBASE_MODE": "production"}), [])
        self.assertEqual(paths(VALID_EMULATOR_ENV), ["/api/admin/account-operations/incomplete-deletions",
                                                     "/api/admin/users/{uid}/delete"])


# ------------------------------------------------- backend student-data access (JL1)
class StudentDataAccessTests(DeletionTestBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(assessment_routes.router, prefix="/api/assessment")
        self.client = TestClient(app)
        self.patch("core.auth.firebase_auth.verify_id_token", side_effect=fake_verify_id_token)
        self.patch("core.auth._ensure_firebase_app")
        self.emulator = self.patch("core.student_access._emulator_mode", return_value=True)
        self.ai = self.patch("routes.assessment.generate_rag_assessment",
                             new=mock.AsyncMock(return_value={"questions": [], "source": "test", "model_used": "none"}))
        self.recommend = self.patch("routes.assessment.calculate_program_recommendations", return_value=[])
        self.reads = []
        original = access.read_access_record
        self.patch("services.account_access_service.read_access_record",
                   side_effect=lambda uid: (self.reads.append(uid), original(uid))[1])

    def call(self, path, body):
        return self.client.post(f"/api/assessment/{path}", headers=bearer("student-token"),
                                json={"userId": STUDENT_UID, **body})

    def test_accounts_being_deleted_or_deleted_are_refused_before_the_handlers(self):
        for state in ("deleting", "deleted"):
            with self.subTest(state=state):
                self.store.put("account_access", STUDENT_UID, {"state": state, "version": 3})
                for path, body in (("generate-questions", {"interests": ["engineering"]}),
                                   ("recommend", {"interests": ["engineering"], "grades": [{"subject": "Math", "grade": "A"}],
                                                  "assessmentScore": 5})):
                    response = self.call(path, body)
                    self.assertEqual(response.status_code, 403, path)
                    self.assertEqual(response.json()["detail"]["code"], "ACCOUNT_DELETED")
        self.ai.assert_not_called()
        self.recommend.assert_not_called()

    def test_active_disabled_and_missing_records_reach_the_handlers_unchanged(self):
        for record in (ACTIVE, {"state": "disabled", "version": 2}, None):
            with self.subTest(record=record):
                self.store.docs.clear()
                if record:
                    self.store.put("account_access", STUDENT_UID, record)
                self.assertEqual(self.call("generate-questions", {"interests": ["engineering"]}).status_code, 200)
        self.assertEqual(self.ai.await_count, 3)

    def test_an_unreadable_record_fails_closed(self):
        self.store.fail[("get", "account_access")] = google_exceptions.ServiceUnavailable("down")
        response = self.call("generate-questions", {"interests": ["engineering"]})
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (503, "ACCOUNT_STATUS_UNAVAILABLE"))
        self.ai.assert_not_called()

    def test_production_mode_is_unchanged_and_reads_no_record(self):
        self.emulator.return_value = False
        self.store.put("account_access", STUDENT_UID, {"state": "deleted", "version": 3})
        self.assertEqual(self.call("generate-questions", {"interests": ["engineering"]}).status_code, 200)
        self.assertEqual(self.reads, [], "no Firestore read in production mode")

    def test_emulator_mode_is_taken_from_the_initialised_configuration(self):
        # the unpatched function (setUp replaces student_access._emulator_mode for the route tests)
        with mock.patch("core.student_access.core_firebase.initialized_config", return_value=None):
            self.assertFalse(EMULATOR_MODE_CHECK())
        for mode, expected in (("emulator", True), ("production", False)):
            with mock.patch("core.student_access.core_firebase.initialized_config",
                            return_value=SimpleNamespace(mode=mode)):
                self.assertEqual(EMULATOR_MODE_CHECK(), expected)


if __name__ == "__main__":
    unittest.main()
