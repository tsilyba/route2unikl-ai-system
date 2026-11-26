# backend/tests/test_account_lifecycle_hardening.py
"""
M3C: Account Lifecycle Security Hardening (local emulator mode only).

  1. Disable/Enable lock hardening (audit finding M1): lease renewal with an ownership check before every
     step, the takeover grace period for every operation, the stale-operation record check before every
     Firebase Authentication write, and concurrency.
  2. Strict student-data access (core/student_access.py): only an active, well-formed record and a session
     that satisfies sessionsValidAfter (the experimental guard's exact rule) reach the handlers.
  3. Student self-service deletion (routes/account_self_service.py, delete_own_account): recent sign-in,
     own account only, the M3B-3 deletion steps, recovery.

Run from the backend directory with the other backend tests:
    python -m unittest discover -s tests -t . -v

Safety: the in-memory Firebase Authentication and Firestore fakes of test_account_actions.py; token
verification is faked. No network, emulator, credential or AI provider is used: the assessment handlers'
AI and recommendation functions are replaced by stubs.
"""
import json
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402

from core import auth as core_auth  # noqa: E402
from core import student_access  # noqa: E402
from routes import account_self_service as self_service  # noqa: E402
from routes import admin_account_actions as action_routes  # noqa: E402
from routes import assessment as assessment_routes  # noqa: E402
from services import account_access_service as access  # noqa: E402
from services import account_action_service as actions  # noqa: E402
from tests.test_account_actions import (  # noqa: E402
    ACTIVE, DISABLED, EMAIL, OTHER_ADMIN, TARGET, ActionTestBase, FakeDocument)
from tests.test_auth import ADMIN_UID, bearer, fake_verify_id_token  # noqa: E402
from tests.test_firebase_config import VALID_EMULATOR_ENV, firebase_env  # noqa: E402

DATA = actions.STUDENT_DATA_COLLECTIONS
ALL_PRESENT = {name: True for name in DATA}
ALL_ABSENT = {name: False for name in DATA}
NOW = 1_800_000_000          # the server's "now" for recent-sign-in checks (2027-01-15T08:00:00Z)
S = 1_800_000_000            # reference second for the session-threshold boundary cases (as in the rules suite)


def at(seconds, microseconds=0):
    return datetime.fromtimestamp(seconds, tz=timezone.utc) + timedelta(microseconds=microseconds)


def token(uid=TARGET, auth_time=NOW - 10, admin=False):
    """A fake token string carrying uid, auth_time (JSON, or 'none' for no claim) and the admin claim."""
    return f"t|{uid}|{'none' if auth_time is None else json.dumps(auth_time)}|{'admin' if admin else ''}"


def verify_with_auth_time(id_token, check_revoked=False, clock_skew_seconds=0, app=None):
    if id_token.startswith("t|"):
        _, uid, auth_time, flag = id_token.split("|")
        claims = {"uid": uid, "email": EMAIL}
        if auth_time != "none":
            claims["auth_time"] = json.loads(auth_time)
        if flag == "admin":
            claims["admin"] = True
        return claims
    return fake_verify_id_token(id_token, check_revoked, clock_skew_seconds, app)


# =========================================================================== 1. Disable / Enable locks (M1)
class DisableEnableLockHardeningTests(ActionTestBase):
    def steal_lock_after(self, operation_steps, step_name):
        """Steps for an operation where another process takes the lock over right after `step_name` ran."""
        def wrap(name, fn):
            def run_then_steal(run):
                fn(run)
                stolen = self.lock()
                self.store.put("account_operations", TARGET, {**stolen, "operationId": "someone-else"})
            return run_then_steal if name == step_name else fn
        return [(name, wrap(name, fn)) for name, fn in operation_steps]

    def test_the_lease_is_renewed_before_every_disable_and_enable_step(self):
        renewals = []
        original = actions._renew_lock
        self.patch("services.account_action_service._renew_lock",
                   side_effect=lambda db, held: (renewals.append(held.operation), original(db, held))[1])
        self.student(record=ACTIVE)
        actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual(renewals, ["disable"] * (len(actions._DISABLE_STEPS) + 1), "every step and the verification")
        renewals.clear()
        actions.enable_account(TARGET, ADMIN_UID)
        self.assertEqual(renewals, ["enable"] * (len(actions._ENABLE_STEPS) + 1))

    def test_all_operations_share_one_lease_and_grace_period(self):
        for operation in actions.ACTIONS:
            self.assertEqual(actions._lease_seconds(operation), actions.LEASE_SECONDS)
        self.assertGreater(actions.TAKEOVER_GRACE_SECONDS, 2 * 4 * 120, "longer than two Admin SDK calls' retries")

    def test_a_lost_lock_stops_an_enable_before_auth_is_re_enabled(self):
        self.student(record=DISABLED, disabled=True)
        steps = self.steal_lock_after(actions._ENABLE_STEPS, actions.STEP_SET_THRESHOLD)
        with mock.patch.object(actions, "_ENABLE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.enable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_SETTLE, "LOCK_LOST"))
        self.assertNotIn(("auth", "enabled"), self.changes(), "no change after the lock was lost")
        self.assertTrue(self.auth.users[TARGET].disabled)
        self.assertEqual(self.record()["state"], "disabled", "never activated")
        self.assertEqual(self.lock()["operationId"], "someone-else", "the new owner's lock is left alone")
        [audit] = self.audits()
        self.assertEqual((audit["outcome"], audit["reason"]), ("incomplete", "LOCK_LOST"))

    def test_a_lost_lock_stops_a_disable_before_auth_is_changed(self):
        self.student(record=ACTIVE)
        steps = self.steal_lock_after(actions._DISABLE_STEPS, actions.STEP_RESTRICT_RECORD)
        with mock.patch.object(actions, "_DISABLE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_DISABLE_AUTH, "LOCK_LOST"))
        self.assertEqual(self.changes(), [("account_access", "update", "disabled")])

    def test_a_stale_enable_never_re_enables_auth_after_the_record_changed(self):
        # The record is changed by something else after the threshold was set (version + 1): the stale-Enable
        # check right before the Auth write stops the Enable. Auth stays disabled; the record is never activated.
        self.student(record=DISABLED, disabled=True)

        def settle_then_change(run):
            current = self.record()
            self.store.put("account_access", TARGET, {**current, "version": current["version"] + 1})

        steps = [(name, settle_then_change if name == actions.STEP_SETTLE else fn) for name, fn in actions._ENABLE_STEPS]
        with mock.patch.object(actions, "_ENABLE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.enable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_ENABLE_AUTH, "RECORD_CHANGED"))
        self.assertTrue(self.auth.users[TARGET].disabled, "Auth not re-enabled by the stale Enable")
        self.assertEqual(self.record()["state"], "disabled")
        self.assertNotIn(("auth", "enabled"), self.changes())

    def test_a_stale_enable_needs_its_own_threshold(self):
        self.student(record=DISABLED, disabled=True)

        def settle_then_remove_threshold(run):
            current = self.record()
            current.pop("sessionsValidAfter", None)
            self.store.put("account_access", TARGET, current)  # same version, threshold gone

        steps = [(name, settle_then_remove_threshold if name == actions.STEP_SETTLE else fn)
                 for name, fn in actions._ENABLE_STEPS]
        with mock.patch.object(actions, "_ENABLE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.enable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_ENABLE_AUTH, "RECORD_CHANGED"))
        self.assertTrue(self.auth.users[TARGET].disabled)

    def test_a_stale_disable_never_writes_auth_after_the_record_changed(self):
        self.student(record=ACTIVE)
        original = actions._restrict_record

        def restrict_then_change(run):
            original(run)
            self.store.put("account_access", TARGET, {"state": "disabled", "version": run.version + 5})

        steps = [(name, restrict_then_change if name == actions.STEP_RESTRICT_RECORD else fn)
                 for name, fn in actions._DISABLE_STEPS]
        with mock.patch.object(actions, "_DISABLE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_DISABLE_AUTH, "RECORD_CHANGED"))
        self.assertFalse(self.auth.users[TARGET].disabled)

    def test_running_disable_and_enable_locks_are_not_taken_over_within_lease_plus_grace(self):
        for operation, record, disabled, action in (("disable", ACTIVE, False, actions.disable_account),
                                                    ("enable", DISABLED, True, actions.enable_account)):
            with self.subTest(operation=operation):
                self.store.docs.clear()
                self.student(record=record, disabled=disabled)
                self.put_lock(operation, status="running", lease_seconds=-600)  # lease expired 10 minutes ago
                view = actions.get_account_view(TARGET, ADMIN_UID)
                self.assertEqual(view.state, "in_progress")
                self.assertIsNotNone(view.lock.resumable_after)
                described = actions.describe_view(view, ADMIN_UID)["operation"]
                self.assertTrue(described["resumable_after"].endswith("Z"))
                for attempt in (actions.disable_account, actions.enable_account):
                    self.assert_error(actions.OPERATION_IN_PROGRESS, attempt, TARGET, ADMIN_UID)
                self.assertEqual(self.changes(), [])
                self.put_lock(operation, status="running", lease_seconds=-(actions.TAKEOVER_GRACE_SECONDS + 60))
                result = action(TARGET, ADMIN_UID)
                self.assertEqual(result.resumed_operation_id, "earlier-op")
                self.events.clear()

    def test_concurrent_enable_requests_enable_once(self):
        self.student(record=DISABLED, disabled=True)
        outcomes = self.race([actions.enable_account] * 8)
        self.assertEqual(outcomes.count("active"), 1, outcomes)
        self.assertTrue(set(outcomes) <= {"active", actions.OPERATION_IN_PROGRESS, actions.ALREADY_ACTIVE}, outcomes)
        self.assertEqual(self.changes().count(("auth", "enabled")), 1)
        self.assertEqual(self.record()["state"], "active")
        self.assertEqual([a["outcome"] for a in self.audits()], ["completed"])

    def test_concurrent_mixed_disable_and_enable_requests_leave_a_consistent_account(self):
        for record, disabled in ((ACTIVE, False), (DISABLED, True)):
            with self.subTest(start=record["state"]):
                self.store.docs.clear()
                self.events.clear()
                self.student(record=record, disabled=disabled)
                outcomes = self.race([actions.disable_account, actions.enable_account] * 5)
                self.assertTrue(set(outcomes) <= {"active", "disabled", actions.OPERATION_IN_PROGRESS,
                                                  actions.ALREADY_ACTIVE, actions.ALREADY_DISABLED}, outcomes)
                view = actions.get_account_view(TARGET, ADMIN_UID)
                self.assertIn(view.state, ("active", "disabled"), "never inconsistent, incomplete or stuck")
                if view.state == "active":
                    self.assertIsNotNone(view.record.lookup.record.sessions_valid_after)
                self.assertIsNone(self.lock(), "no lock left behind")
                self.assertTrue(all(a["outcome"] == "completed" for a in self.audits()))

    def race(self, functions):
        barrier = threading.Barrier(len(functions))
        outcomes = []

        def attempt(function):
            barrier.wait()
            try:
                outcomes.append(function(TARGET, ADMIN_UID).view.state)
            except actions.AccountActionError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt, args=(function,)) for function in functions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return outcomes

    def test_residual_race_a_late_auth_write_cannot_reopen_data_access(self):
        # Documents the limit that remains (not a fix): a Firebase Authentication write cannot be fenced. Here
        # an Enable's in-flight Auth call is delayed beyond lease + grace, a Disable takes over and completes,
        # and only then does the stale Enable's Auth write land. The stale Enable then stops (LOCK_LOST) and
        # never activates the record, so the account is 'inconsistent' (Auth enabled, record disabled): the
        # guard and the backend's student-data check stay closed, and a new Disable makes it consistent.
        self.student(record=DISABLED, disabled=True)
        original_update = self.auth.update_user
        delayed = {}

        def delayed_enable(uid, **kwargs):
            if kwargs.get("disabled") is False and not delayed:
                delayed["yes"] = True
                lock = self.lock()  # simulate 35+ minutes passing during this call
                self.store.put("account_operations", TARGET, {
                    **lock, "leaseExpiresAt": datetime.now(timezone.utc) - timedelta(
                        seconds=actions.TAKEOVER_GRACE_SECONDS + 60)})
                takeover = actions.disable_account(TARGET, OTHER_ADMIN)
                self.assertEqual(takeover.view.state, "disabled")
            return original_update(uid, **kwargs)

        self.auth.add(OTHER_ADMIN, admin=True)
        self.patch("services.account_action_service.firebase_auth.update_user", side_effect=delayed_enable)
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.enable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_ACTIVATE_RECORD, "LOCK_LOST"))
        self.assertFalse(self.auth.users[TARGET].disabled, "the late Auth write landed (not fenceable)")
        self.assertEqual(self.record()["state"], "disabled", "the record was never re-activated")
        lookup = access.read_access_record(TARGET)
        self.assertEqual(student_access.record_access_refusal(lookup, NOW), student_access.ACCOUNT_ACCESS_DENIED)
        view = actions.get_account_view(TARGET, ADMIN_UID)
        self.assertEqual((view.state, view.issues), ("inconsistent", ("AUTH_ENABLED_RECORD_DISABLED",)))
        actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual(actions.get_account_view(TARGET, ADMIN_UID).state, "disabled")


# ================================================== 1b. lock renewal under Firestore contention (ML10)
RENEWAL_FIELDS = {"leaseExpiresAt", "updatedAt"}


def is_renewal(data):
    return isinstance(data, dict) and set(data) == RENEWAL_FIELDS


class LockRenewalContentionTests(ActionTestBase):
    """ML10: a renewal that Firestore aborts because of contention is not a lost lock. Deterministic: the fake
    Firestore aborts or fails exactly the renewal writes chosen by each test."""

    def setUp(self):
        super().setUp()
        self.renewal_attempts = 0

    def fail_renewals(self, decide):
        """decide(attempt_number) -> exception to raise before the write, or None to let it through."""
        def failure(data):
            if not is_renewal(data):
                return None
            self.renewal_attempts += 1
            return decide(self.renewal_attempts)
        self.store.fail[("update", "account_operations")] = failure

    def aborted(self):
        return google_exceptions.Aborted("Transaction lock timeout")

    def backoffs(self):
        return [s for s in self.sleeps if s in actions.RENEW_BACKOFF_SECONDS]

    def test_transient_contention_is_retried_and_the_disable_completes(self):
        self.student(record=ACTIVE)
        self.fail_renewals(lambda n: self.aborted() if n in (1, 2) else None)
        result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual((result.view.state, result.audit_recorded, result.lock_released), ("disabled", True, True))
        self.assertEqual(self.backoffs(), [0.05, 0.1], "two short backoffs, then success")
        self.assertEqual(self.changes(), [("account_access", "update", "disabled"), ("auth", "disabled")])
        self.assertIsNone(self.lock())
        self.assertEqual([a["outcome"] for a in self.audits()], ["completed"])
        self.assertTrue(any("contended; retrying" in m for m in self.logs.messages))

    def test_contention_before_every_enable_step_is_absorbed(self):
        self.student(record=DISABLED, disabled=True)
        self.fail_renewals(lambda n: self.aborted() if n % 2 == 1 else None)  # every renewal aborts once
        result = actions.enable_account(TARGET, ADMIN_UID)
        self.assertEqual(result.view.state, "active")
        self.assertEqual(self.renewal_attempts, 2 * (len(actions._ENABLE_STEPS) + 1))
        self.assertEqual(self.record()["state"], "active")

    def test_transient_contention_during_a_deletion_is_retried(self):
        self.student(record=ACTIVE)
        for name in actions.STUDENT_DATA_COLLECTIONS:
            self.store.put(name, TARGET, {"marker": "content"})
        self.fail_renewals(lambda n: self.aborted() if n in (3, 4, 5) else None)
        result = actions.delete_account(TARGET, ADMIN_UID, TARGET)
        self.assertEqual(result.view.state, "deleted")
        self.assertEqual(self.backoffs(), list(actions.RENEW_BACKOFF_SECONDS))
        self.assertEqual(self.record(), {"state": "deleted", "version": 4})

    def test_persistent_contention_stops_with_lock_contention_and_is_resumable(self):
        self.student(record=ACTIVE)
        self.fail_renewals(lambda n: self.aborted())
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_RESTRICT_RECORD, "LOCK_CONTENTION"))
        self.assertEqual(self.renewal_attempts, actions.RENEW_MAX_ATTEMPTS, "bounded")
        self.assertEqual(self.backoffs(), list(actions.RENEW_BACKOFF_SECONDS))
        self.assertEqual(self.changes(), [], "no account change")
        self.assertEqual((self.lock()["status"], self.lock()["reason"]), ("incomplete", "LOCK_CONTENTION"),
                         "still owned, so it is recorded as incomplete")
        self.store.fail.clear()
        result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual((result.view.state, result.resumed_operation_id), ("disabled", error.operation_id))

    def test_a_genuine_takeover_during_contention_fails_closed_without_retry(self):
        self.student(record=ACTIVE)

        def taken_over(n):
            if n == 2:  # the renewal before disable_auth: another process has taken the lock meanwhile
                self.store.put("account_operations", TARGET, {**self.lock(), "operationId": "someone-else"})
                return self.aborted()
            return None

        self.fail_renewals(taken_over)
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_DISABLE_AUTH, "LOCK_LOST"))
        self.assertEqual(self.renewal_attempts, 2, "no retry once ownership is lost")
        self.assertEqual(self.backoffs(), [])
        self.assertNotIn(("auth", "disabled"), self.changes())
        self.assertEqual(self.lock()["operationId"], "someone-else", "the new owner's lock is untouched")
        self.assertEqual(self.lock()["status"], "running", "not marked incomplete by the old owner")

    def test_a_precondition_failure_is_a_genuine_loss_and_is_not_retried(self):
        for exception in (google_exceptions.FailedPrecondition("update_time mismatch"),
                          google_exceptions.NotFound("no document")):
            with self.subTest(exception=type(exception).__name__):
                self.store.docs.clear()
                self.events.clear()
                self.sleeps.clear()
                self.renewal_attempts = 0
                self.student(record=ACTIVE)
                self.fail_renewals(lambda n, exception=exception: exception)
                error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
                self.assertEqual(error.reason, "LOCK_LOST")
                self.assertEqual(self.renewal_attempts, 1)
                self.assertEqual(self.backoffs(), [])
                self.assertEqual(self.changes(), [])

    def test_a_lock_changed_by_an_unknown_write_with_the_same_owner_fails_closed(self):
        self.student(record=ACTIVE)

        def changed(n):
            lock = self.lock()  # same operation, but a lease this attempt did not write
            self.store.put("account_operations", TARGET, {**lock, "leaseExpiresAt": lock["leaseExpiresAt"] + timedelta(seconds=1)})
            return self.aborted()

        self.fail_renewals(changed)
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual(error.reason, "LOCK_LOST")
        self.assertEqual(self.renewal_attempts, 1)

    def test_lease_expiry_stops_the_operation_before_it_continues(self):
        self.student(record=ACTIVE)
        real_now = actions._now
        late = {"on": False}
        self.patch("services.account_action_service._now",
                   side_effect=lambda: real_now() + (timedelta(seconds=actions.LEASE_SECONDS + actions.TAKEOVER_GRACE_SECONDS + 60)
                                                     if late["on"] else timedelta(0)))
        original = actions._restrict_record

        def restrict_then_stall(run):
            original(run)
            late["on"] = True  # the process stalls for longer than lease + grace

        steps = [(n, restrict_then_stall if n == actions.STEP_RESTRICT_RECORD else f) for n, f in actions._DISABLE_STEPS]
        with mock.patch.object(actions, "_DISABLE_STEPS", steps):
            error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_DISABLE_AUTH, "LEASE_EXPIRED"))
        self.assertFalse(self.auth.users[TARGET].disabled, "Auth is not changed after the lease expired")
        self.assertEqual((self.lock()["status"], self.lock()["reason"]), ("incomplete", "LEASE_EXPIRED"))
        late["on"] = False
        self.assertEqual(actions.disable_account(TARGET, ADMIN_UID).view.state, "disabled", "resumable")

    def test_an_unknown_outcome_that_was_applied_is_confirmed_by_re_reading(self):
        self.student(record=ACTIVE)
        original_update = FakeDocument.update
        lost_response = {"done": False}

        def apply_then_lose_response(document, data, option=None, retry=None, timeout=None):
            result = original_update(document, data, option=option, retry=retry, timeout=timeout)
            if is_renewal(data) and not lost_response["done"]:
                lost_response["done"] = True
                raise google_exceptions.DeadlineExceeded("no answer")
            return result

        with mock.patch.object(FakeDocument, "update", apply_then_lose_response):
            result = actions.disable_account(TARGET, ADMIN_UID)
        self.assertEqual((result.view.state, result.lock_released), ("disabled", True), "the adopted update time is used later")
        self.assertEqual(self.backoffs(), [], "nothing retried")
        self.assertTrue(any("confirmed by re-reading" in m for m in self.logs.messages))

    def test_an_unknown_outcome_that_was_not_applied_stops_without_retry(self):
        self.student(record=ACTIVE)
        self.fail_renewals(lambda n: google_exceptions.DeadlineExceeded("no answer") if n == 1 else None)
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual((error.failed_step, error.reason), (actions.STEP_RESTRICT_RECORD, "STORE_UNAVAILABLE"))
        self.assertEqual(self.renewal_attempts, 1)
        self.assertEqual(self.changes(), [])
        self.assertEqual(self.lock()["status"], "incomplete")

    def test_an_unreadable_lock_after_a_failed_renewal_fails_closed(self):
        self.student(record=ACTIVE)

        def abort_and_break_reads(n):
            self.store.fail[("get", "account_operations")] = google_exceptions.ServiceUnavailable("down")
            return self.aborted()

        self.fail_renewals(abort_and_break_reads)
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.disable_account, TARGET, ADMIN_UID)
        self.assertEqual(error.reason, "STORE_UNAVAILABLE")
        self.assertEqual((self.renewal_attempts, self.changes()), (1, []))

    def test_concurrent_disable_and_enable_with_contended_renewals_stay_consistent(self):
        for record, disabled in ((ACTIVE, False), (DISABLED, True)):
            with self.subTest(start=record["state"]):
                self.store.docs.clear()
                self.events.clear()
                self.renewal_attempts = 0
                self.student(record=record, disabled=disabled)
                lock = threading.Lock()

                def every_third(n):
                    return self.aborted() if n % 3 == 0 else None

                def failure(data):
                    if not is_renewal(data):
                        return None
                    with lock:
                        self.renewal_attempts += 1
                        n = self.renewal_attempts
                    return every_third(n)

                self.store.fail[("update", "account_operations")] = failure
                functions = [actions.disable_account, actions.enable_account] * 4
                barrier = threading.Barrier(len(functions))
                outcomes = []

                def attempt(function):
                    barrier.wait()
                    try:
                        outcomes.append(function(TARGET, ADMIN_UID).view.state)
                    except actions.AccountActionError as exc:
                        outcomes.append((exc.code, exc.reason))

                threads = [threading.Thread(target=attempt, args=(f,)) for f in functions]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                self.assertTrue(all(o in ("active", "disabled") or o[0] in (actions.OPERATION_IN_PROGRESS,
                                    actions.ALREADY_ACTIVE, actions.ALREADY_DISABLED) for o in outcomes), outcomes)
                self.assertNotIn("LOCK_LOST", repr(outcomes))
                self.store.fail.clear()
                view = actions.get_account_view(TARGET, ADMIN_UID)
                self.assertIn(view.state, ("active", "disabled"))
                self.assertIsNone(self.lock())


# ===================================================================== 2. strict student-data access
class SessionThresholdRuleTests(unittest.TestCase):
    # The rules suite's BOUNDARY_CASES (firestore-tests/account-access.experimental.suite.mjs, section 14):
    # [threshold, auth_time, allowed]. The backend must decide exactly as the guard does.
    BOUNDARY_CASES = [
        (at(S, 250_000), S - 3600, False), (at(S, 250_000), S - 1, False), (at(S, 250_000), S, False),
        (at(S, 250_000), S + 1, False), (at(S, 250_000), S + 2, True), (at(S, 250_000), S + 3600, True),
        (at(S), S - 1, False), (at(S), S, False), (at(S), S + 1, True),
        (at(S, 1), S, False), (at(S, 1), S + 1, False), (at(S, 1), S + 2, True),
        (at(S, 999_999), S + 1, False), (at(S, 999_999), S + 2, True),
    ]

    def test_signed_in_after_matches_the_guard(self):
        for threshold, auth_time, allowed in self.BOUNDARY_CASES:
            with self.subTest(threshold=threshold.isoformat(), auth_time=auth_time - S):
                self.assertEqual(student_access.signed_in_after(auth_time, threshold), allowed)

    def test_invalid_auth_times_and_thresholds_are_refused(self):
        for auth_time in (None, True, False, float(S + 3600), str(S + 3600), 10 ** 20):
            with self.subTest(auth_time=auth_time):
                self.assertFalse(student_access.signed_in_after(auth_time, at(S)))
        self.assertFalse(student_access.signed_in_after(S + 3600, datetime(2027, 1, 1)), "naive threshold")
        self.assertFalse(student_access.signed_in_after(S + 3600, "2027-01-15T08:00:00Z"))

    def test_record_decisions(self):
        valid = lambda state, threshold=None: access.RecordLookup("valid", access.AccessRecord(state, 3, threshold))  # noqa: E731
        cases = [
            (access.RecordLookup("missing"), S, student_access.ACCOUNT_ACCESS_DENIED),
            (access.RecordLookup("malformed", problems=("UNKNOWN_FIELD",)), S, student_access.ACCOUNT_ACCESS_DENIED),
            (valid("disabled"), S, student_access.ACCOUNT_ACCESS_DENIED),
            (valid("disabled", at(S - 9999)), S, student_access.ACCOUNT_ACCESS_DENIED),
            (valid("deleting"), S, student_access.ACCOUNT_DELETED),
            (valid("deleted"), S, student_access.ACCOUNT_DELETED),
            (valid("active"), None, None),                       # no threshold: auth_time not consulted
            (valid("active", at(S)), None, student_access.SESSION_TOO_OLD),
            (valid("active", at(S)), S, student_access.SESSION_TOO_OLD),
            (valid("active", at(S)), S + 1, None),
        ]
        for lookup, auth_time, expected in cases:
            with self.subTest(lookup=lookup, auth_time=auth_time):
                self.assertEqual(student_access.record_access_refusal(lookup, auth_time), expected)


class AuthTimeClaimTests(unittest.TestCase):
    def test_get_current_user_keeps_only_an_integer_auth_time(self):
        for claim, expected in ((S, S), (None, None), (True, None), (float(S), None), (str(S), None)):
            with self.subTest(claim=claim):
                decoded = {"uid": "u1"} if claim is None else {"uid": "u1", "auth_time": claim}
                with mock.patch("core.auth._ensure_firebase_app"), \
                        mock.patch("core.auth.firebase_auth.verify_id_token", return_value=decoded):
                    user = core_auth.get_current_user(mock.Mock(credentials="anything"))
                self.assertEqual(user.auth_time, expected)

    def test_auth_me_does_not_expose_auth_time(self):
        from routes import auth_check
        app = FastAPI()
        app.include_router(auth_check.router, prefix="/api")
        with mock.patch("core.auth._ensure_firebase_app"), \
                mock.patch("core.auth.firebase_auth.verify_id_token", side_effect=verify_with_auth_time):
            body = TestClient(app).get("/api/auth/me", headers=bearer(token(auth_time=S))).json()
        self.assertEqual(body, {"uid": TARGET, "is_admin": False})


class StrictStudentDataAccessTests(ActionTestBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(assessment_routes.router, prefix="/api/assessment")
        self.client = TestClient(app)
        self.patch("core.auth.firebase_auth.verify_id_token", side_effect=verify_with_auth_time)
        self.patch("core.auth._ensure_firebase_app")
        self.emulator = self.patch("core.student_access._emulator_mode", return_value=True)
        self.ai = self.patch("routes.assessment.generate_rag_assessment",
                             new=mock.AsyncMock(return_value={"questions": [], "source": "stub", "model_used": "none"}))
        self.recommend = self.patch("routes.assessment.calculate_program_recommendations", return_value=[])
        self.patch("routes.assessment.initialize_firebase")

    def call(self, auth_time, path="generate-questions"):
        body = {"interests": ["engineering"], "grades": [{"subject": "Math", "grade": "A"}], "assessmentScore": 5}
        return self.client.post(f"/api/assessment/{path}", headers=bearer(token(auth_time=auth_time)), json=body)

    def assert_refused(self, response, status_code, code):
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (status_code, code), response.text)

    def test_states_and_session_thresholds_on_both_endpoints(self):
        threshold = at(S, 250_000)
        cases = [
            (None, S + 3600, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "active", "version": 1, "updatedAt": 1}, S + 3600, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "active", "version": "1"}, S + 3600, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "disabled", "version": 2}, S + 3600, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "disabled", "version": 3, "sessionsValidAfter": threshold}, S + 3600, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "deleting", "version": 3}, S + 3600, 403, "ACCOUNT_DELETED"),
            ({"state": "deleted", "version": 4}, S + 3600, 403, "ACCOUNT_DELETED"),
            ({"state": "active", "version": 4, "sessionsValidAfter": threshold}, S - 60, 401, "SESSION_TOO_OLD"),
            ({"state": "active", "version": 4, "sessionsValidAfter": threshold}, S + 1, 401, "SESSION_TOO_OLD"),
            ({"state": "active", "version": 4, "sessionsValidAfter": threshold}, None, 401, "SESSION_TOO_OLD"),
            ({"state": "active", "version": 4, "sessionsValidAfter": threshold}, S + 2, 200, None),
            ({"state": "active", "version": 1}, None, 200, None),
        ]
        for record, auth_time, status_code, code in cases:
            for path in ("generate-questions", "recommend"):
                with self.subTest(record=record, auth_time=auth_time, path=path):
                    self.store.docs.clear()
                    if record is not None:
                        self.store.put("account_access", TARGET, record)
                    response = self.call(auth_time, path)
                    if code:
                        self.assert_refused(response, status_code, code)
                    else:
                        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.ai.await_count, self.recommend.call_count), (2, 2), "only the allowed cases ran")

    def test_an_old_session_answers_401_so_the_browser_signs_in_again(self):
        self.store.put("account_access", TARGET, {"state": "active", "version": 4, "sessionsValidAfter": at(S)})
        response = self.call(S - 5)
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def test_failures_to_read_the_record_fail_closed(self):
        self.store.fail[("get", "account_access")] = google_exceptions.ServiceUnavailable("down")
        self.assert_refused(self.call(S), 503, "ACCOUNT_STATUS_UNAVAILABLE")
        self.store.fail.clear()
        self.patch("services.account_access_service.initialize_firebase", side_effect=RuntimeError("no firebase"))
        self.assert_refused(self.call(S), 503, "ACCOUNT_STATUS_UNAVAILABLE")
        self.ai.assert_not_called()

    def test_administrators_are_not_exempt(self):
        self.auth.add(OTHER_ADMIN, admin=True)
        response = self.client.post("/api/assessment/generate-questions", headers=bearer(token(OTHER_ADMIN, admin=True)),
                                    json={"interests": []})
        self.assert_refused(response, 403, "ACCOUNT_ACCESS_DENIED")

    def test_production_mode_is_unchanged_and_reads_no_record(self):
        self.emulator.return_value = False
        reads = self.patch("services.account_access_service.read_access_record")
        self.store.put("account_access", TARGET, {"state": "disabled", "version": 2})
        self.assertEqual(self.call(None).status_code, 200)
        reads.assert_not_called()

    def test_no_personal_data_in_responses_or_logs(self):
        self.store.put("account_access", TARGET, {"state": "disabled", "version": 2})
        self.assertNotIn(EMAIL, self.call(S).text)


# ======================================================================== 3. self-service deletion
class SelfDeletionServiceTests(ActionTestBase):
    def with_data(self, uid=TARGET):
        for name in DATA:
            self.store.put(name, uid, {"marker": f"{name}-content"})

    def data(self, uid=TARGET):
        return {name: self.store.data(name, uid) is not None for name in DATA}

    def test_a_student_deletes_their_own_active_account_with_the_m3b3_steps(self):
        self.student(record=ACTIVE)
        self.with_data()
        result = actions.delete_own_account(TARGET, TARGET)
        self.assertEqual((result.view.state, result.view.is_self), ("deleted", False))
        self.assertNotIn(TARGET, self.auth.users)
        self.assertEqual(self.data(), ALL_ABSENT)
        self.assertEqual(self.record(), {"state": "deleted", "version": 4}, "minimal tombstone")
        self.assertIsNone(self.lock())
        [audit] = self.audits()
        self.assertEqual((audit["operation"], audit["outcome"], audit["actorUid"], audit["targetUid"],
                          audit["requestedBy"]), ("delete", "completed", TARGET, TARGET, "student"))
        self.assertEqual((audit["dataPresentBefore"], audit["dataPresentAfter"]), (ALL_PRESENT, ALL_ABSENT))
        self.assertNotIn(EMAIL, repr(audit))

    def test_administrator_deletions_are_audited_as_such(self):
        self.student(record=ACTIVE)
        actions.delete_account(TARGET, ADMIN_UID, TARGET)
        self.assertEqual(self.audits()[0]["requestedBy"], "administrator")

    def test_only_active_accounts_or_the_students_own_unfinished_deletion(self):
        cases = [
            (DISABLED, True, None, actions.DELETE_NOT_ALLOWED),
            (DISABLED, False, None, actions.DELETE_NOT_ALLOWED),          # inconsistent
            (ACTIVE, True, None, actions.DELETE_NOT_ALLOWED),             # inconsistent
            (None, False, None, actions.ACCESS_RECORD_UNSUPPORTED),
            ({"state": "active", "version": 1, "x": 1}, False, None, actions.ACCESS_RECORD_UNSUPPORTED),
            (DISABLED, True, "enable", actions.INCOMPLETE_OPERATION_PENDING),
            (ACTIVE, False, "disable", actions.INCOMPLETE_OPERATION_PENDING),
        ]
        for record, disabled, lock, code in cases:
            with self.subTest(record=record, disabled=disabled, lock=lock):
                self.store.docs.clear()
                self.student(record=record, disabled=disabled)
                self.with_data()
                if lock:
                    self.put_lock(lock, status="incomplete")
                self.assert_error(code, actions.delete_own_account, TARGET, TARGET)
                self.assertEqual(self.record(), record)
                self.assertEqual(self.data(), ALL_PRESENT)
                self.assertIn(TARGET, self.auth.users)

    def test_administrator_accounts_are_refused_even_if_the_claim_is_not_in_the_token(self):
        self.auth.add(OTHER_ADMIN, admin=True)
        self.store.put("account_access", OTHER_ADMIN, ACTIVE)
        self.with_data(OTHER_ADMIN)
        self.assert_error(actions.ADMIN_TARGET_FORBIDDEN, actions.delete_own_account, OTHER_ADMIN, OTHER_ADMIN)
        self.assertEqual(self.data(OTHER_ADMIN), ALL_PRESENT)

    def test_the_confirmation_and_the_api_are_strict(self):
        self.student(record=ACTIVE)
        for confirm in ("someone-else", "", None, 1):
            self.assert_error(actions.DELETE_CONFIRMATION_MISMATCH, actions.delete_own_account, TARGET, confirm)
        with self.assertRaises(ValueError):
            actions._run(actions.DISABLE, TARGET, TARGET, self_service=True)
        with self.assertRaises(ValueError):
            actions._run(actions.DELETE, TARGET, ADMIN_UID, self_service=True)
        self.assertEqual(self.changes(), [])

    def test_an_incomplete_self_deletion_is_listed_for_administrators_and_resumable_by_them(self):
        self.student(record=ACTIVE)
        self.with_data()
        self.auth.fail["delete_user"] = firebase_exceptions.UnavailableError("down")
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.delete_own_account, TARGET, TARGET)
        self.assertEqual(error.failed_step, actions.STEP_DELETE_AUTH)
        self.assertEqual(self.data(), ALL_ABSENT, "data already removed")
        self.assertTrue(self.auth.users[TARGET].disabled, "no sign-in meanwhile")
        listed = actions.list_incomplete_deletions(ADMIN_UID)
        self.assertEqual([(item.uid, item.state) for item in listed], [(TARGET, "deletion_incomplete")])
        self.auth.fail.clear()
        result = actions.delete_account(TARGET, ADMIN_UID, TARGET)
        self.assertEqual(result.resumed_operation_id, error.operation_id)
        self.assertNotIn(TARGET, self.auth.users)
        self.assertEqual(self.record()["state"], "deleted")

    def test_the_student_can_resume_their_own_deletion_while_they_can_still_sign_in(self):
        self.student(record=ACTIVE)
        self.with_data()
        self.auth.fail["update_user"] = firebase_exceptions.UnavailableError("down")
        error = self.assert_error(actions.OPERATION_INCOMPLETE, actions.delete_own_account, TARGET, TARGET)
        self.assertEqual((error.failed_step, self.record()["state"]), (actions.STEP_DISABLE_AUTH, "deleting"))
        self.auth.fail.clear()
        result = actions.delete_own_account(TARGET, TARGET)
        self.assertEqual((result.view.state, result.resumed_operation_id), ("deleted", error.operation_id))

    def test_concurrent_self_and_administrator_deletions_delete_once(self):
        self.student(record=ACTIVE)
        self.with_data()
        functions = [lambda: actions.delete_own_account(TARGET, TARGET),
                     lambda: actions.delete_account(TARGET, ADMIN_UID, TARGET)] * 4
        barrier = threading.Barrier(len(functions))
        outcomes = []

        def attempt(function):
            barrier.wait()
            try:
                outcomes.append(function().view.state)
            except actions.AccountActionError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt, args=(f,)) for f in functions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("deleted"), 1, outcomes)
        self.assertTrue(set(outcomes) <= {"deleted", actions.OPERATION_IN_PROGRESS, actions.ACCOUNT_DELETED}, outcomes)
        self.assertEqual(sum(1 for event in self.events if event == ("auth", "deleted")), 1)


class SelfDeletionRouteTests(ActionTestBase):
    URL = "/api/account/delete"

    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(self_service.router, prefix="/api/account")
        app.include_router(action_routes.router, prefix="/api/admin/users")
        self.client = TestClient(app)
        self.verify = self.patch("core.auth.firebase_auth.verify_id_token", side_effect=verify_with_auth_time)
        self.patch("core.auth._ensure_firebase_app")
        self.ready = self.patch("routes.account_self_service._emulator_ready", return_value=True)
        self.patch("routes.admin_account_actions._emulator_ready", return_value=True)
        self.patch("routes.account_self_service._now_seconds", return_value=NOW)
        self.patch("core.student_access._emulator_mode", return_value=True)
        self.student(record=ACTIVE)
        for name in DATA:
            self.store.put(name, TARGET, {"marker": "content"})

    def post(self, id_token=None, body=None, raw=None, env=VALID_EMULATOR_ENV):
        headers = {} if id_token is False else bearer(id_token or token())
        with firebase_env(env):
            if raw is not None:
                return self.client.post(self.URL, headers={**headers, "Content-Type": "application/json"}, content=raw)
            return self.client.post(self.URL, headers=headers, json={"confirm_uid": TARGET} if body is None else body)

    def data(self):
        return {name: self.store.data(name, TARGET) is not None for name in DATA}

    def assert_untouched(self):
        self.assertIn(TARGET, self.auth.users)
        self.assertEqual(self.data(), ALL_PRESENT)
        self.assertEqual(self.record(), ACTIVE)
        self.assertEqual(self.audits(), [])

    def assert_code(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        self.assertEqual(response.json()["detail"]["code"], code)

    def test_a_recently_signed_in_student_deletes_their_own_account(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"outcome", "operation", "operation_id", "resumed_operation_id", "audit_recorded",
                                     "lock_released"})
        self.assertEqual((body["outcome"], body["audit_recorded"], body["lock_released"]), ("completed", True, True))
        self.assertNotIn(EMAIL, response.text)
        self.assertNotIn(TARGET, self.auth.users)
        self.assertEqual(self.data(), ALL_ABSENT)
        self.assertEqual(self.record(), {"state": "deleted", "version": 4})
        self.assertEqual(self.audits()[0]["requestedBy"], "student")

    def test_the_route_exists_only_in_emulator_mode_and_checks_nothing_first(self):
        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}, {"ROUTE2UNIKL_FIREBASE_MODE": "staging"}):
            with self.subTest(env=env):
                response = self.post(env=env)
                self.assertEqual((response.status_code, response.json()), (404, {"detail": "Not Found"}))
        self.verify.assert_not_called()
        self.ready.assert_not_called()
        self.ready.return_value = False
        self.assert_code(self.post(), 503, "ACCOUNT_ACTION_UNAVAILABLE")
        self.verify.assert_not_called()
        self.assert_untouched()

    def test_authentication_comes_before_the_body(self):
        self.assertEqual(self.post(id_token=False).status_code, 401)
        self.assertEqual(self.post(id_token=False, raw=b"{not json").status_code, 401, "DA7 not repeated")
        self.assertEqual(self.post(id_token="expired-token").status_code, 401)
        self.assertEqual(self.post(id_token="disabled-token").status_code, 403)
        self.assert_untouched()

    def test_the_body_must_confirm_the_callers_own_uid(self):
        for raw in (b"{not json", b"[]", b'{"confirm_uid": 1}', b"{}",
                    json.dumps({"confirm_uid": TARGET, "force": True}).encode(), b"x" * 2000):
            with self.subTest(raw=raw[:30]):
                self.assert_code(self.post(raw=raw), 422, "INVALID_REQUEST")
        self.assert_code(self.post(body={"confirm_uid": "someone-else"}), 422, "DELETE_CONFIRMATION_MISMATCH")
        self.assert_untouched()

    def test_a_student_cannot_delete_another_account(self):
        other = "other-student-uid"
        self.student(record=ACTIVE, uid=other)
        original_read = access.read_access_record
        reads = self.patch("services.account_access_service.read_access_record", side_effect=original_read)
        response = self.post(body={"confirm_uid": other})
        reads.assert_not_called()  # the confirmation is checked before Firestore is read
        self.assert_code(response, 422, "DELETE_CONFIRMATION_MISMATCH")
        response = self.post(id_token=token(uid=other), body={"confirm_uid": TARGET})
        self.assert_code(response, 422, "DELETE_CONFIRMATION_MISMATCH")
        self.assert_untouched()
        self.assertIn(other, self.auth.users)

    def test_a_recent_sign_in_is_required(self):
        for auth_time in (NOW - self_service.RECENT_SIGN_IN_SECONDS - 1, NOW - 86400, NOW + 60, None, "x", float(NOW)):
            with self.subTest(auth_time=auth_time):
                self.assert_code(self.post(id_token=token(auth_time=auth_time)), 403, "RECENT_SIGN_IN_REQUIRED")
        self.assert_untouched()
        self.assertEqual(self.post(id_token=token(auth_time=NOW - self_service.RECENT_SIGN_IN_SECONDS)).status_code, 200)

    def test_administrators_cannot_use_self_deletion(self):
        self.assert_code(self.post(id_token=token(admin=True)), 403, "ADMIN_TARGET_FORBIDDEN")
        self.assert_untouched()

    def test_the_access_record_decides_like_the_student_data_endpoints(self):
        cases = [
            (None, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "active", "version": 1, "updatedAt": 1}, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "disabled", "version": 2}, 403, "ACCOUNT_ACCESS_DENIED"),
            ({"state": "deleted", "version": 4}, 403, "ACCOUNT_DELETED"),
            ({"state": "active", "version": 4, "sessionsValidAfter": at(NOW - 5)}, 401, "SESSION_TOO_OLD"),
        ]
        for record, status_code, code in cases:
            with self.subTest(record=record):
                self.store.docs.pop(("account_access", TARGET), None)
                if record is not None:
                    self.store.put("account_access", TARGET, record)
                self.assert_code(self.post(), status_code, code)
                self.assertEqual(self.data(), ALL_PRESENT)
                self.assertIn(TARGET, self.auth.users)
        self.store.fail[("get", "account_access")] = google_exceptions.ServiceUnavailable("down")
        self.assert_code(self.post(), 503, "ACCOUNT_STATUS_UNAVAILABLE")
        self.assertEqual(self.audits(), [])

    def test_a_partial_failure_is_reported_recorded_and_resumable(self):
        self.auth.fail["delete_user"] = firebase_exceptions.UnavailableError(f"down for {EMAIL}")
        response = self.post()
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual({k: detail[k] for k in ("code", "operation", "failed_step", "reason")},
                         {"code": "OPERATION_INCOMPLETE", "operation": "delete", "failed_step": "delete_auth",
                          "reason": "AUTH_UNAVAILABLE"})
        self.assertNotIn(EMAIL, response.text)
        self.assertEqual(self.data(), ALL_ABSENT)
        self.assertEqual(self.record()["state"], "deleting")
        # The student's token is now refused by Firebase (account disabled), so an administrator resumes it.
        self.auth.fail.clear()
        with firebase_env(VALID_EMULATOR_ENV):
            resumed = self.client.post(f"/api/admin/users/{TARGET}/delete", headers=bearer("admin-token"),
                                       json={"confirm_uid": TARGET})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["resumed_operation_id"], detail["operation_id"])
        self.assertNotIn(TARGET, self.auth.users)

    def test_the_student_resumes_an_unfinished_deletion_while_still_able_to_sign_in(self):
        # Auth could not be disabled, so the student can still sign in: the record is 'deleting' (their data is
        # already closed to them), and their self-deletion request resumes the same deletion.
        self.auth.fail["update_user"] = firebase_exceptions.UnavailableError("down")
        first = self.post()
        self.assertEqual(first.json()["detail"]["failed_step"], "disable_auth")
        self.assertEqual(self.record()["state"], "deleting")
        self.auth.fail.clear()
        again = self.post()
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["resumed_operation_id"], first.json()["detail"]["operation_id"])

    def test_errors_are_mapped_to_fixed_codes(self):
        spy = self.patch("routes.account_self_service.actions.delete_own_account")
        for code, status_code in ((actions.OPERATION_IN_PROGRESS, 409), (actions.DELETE_NOT_ALLOWED, 409),
                                  (actions.INCOMPLETE_OPERATION_PENDING, 409), (actions.ACCOUNT_DELETED, 409),
                                  (actions.ACCOUNT_ACTION_UNAVAILABLE, 503), (actions.ADMIN_TARGET_FORBIDDEN, 403)):
            with self.subTest(code=code):
                spy.side_effect = actions.AccountActionError(code, operation="delete")
                response = self.post()
                self.assert_code(response, status_code, code)
                self.assertEqual(set(response.json()["detail"]), {"code", "message"})


if __name__ == "__main__":
    unittest.main()
