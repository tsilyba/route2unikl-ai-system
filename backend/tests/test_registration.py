# backend/tests/test_registration.py
"""
M3B-1B-P1-B2A: trusted student registration (services/registration_service.py,
routes/registration.py).

Run from the backend directory with the other backend tests:
    python -m unittest discover -s tests -t . -v

Safety: Firebase Authentication and Firestore are in-memory fakes (the fake
Firestore has create-if-absent semantics; the fake Auth enforces unique
emails). No network, emulator or credential is used.
"""
import logging
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

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import exceptions as firebase_exceptions  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402
from google.cloud.firestore import SERVER_TIMESTAMP  # noqa: E402

from core.firebase import FirebaseConfigError  # noqa: E402
from routes import registration as registration_routes  # noqa: E402
from services import registration_service as registration  # noqa: E402
from tests.test_firebase_config import VALID_EMULATOR_ENV, firebase_env  # noqa: E402

# Sentinels that must never appear in logs, errors or responses.
PASSWORD = "Sentinel-Pass-91f2"
NAME = "Sentinel Student Name"
EMAIL = "sentinel.student@example.test"
URL = "/api/account/register"


# ----------------------------------------------------------------------- fakes
class FakeAuth:
    """Firebase Authentication in memory: unique (lower-cased) emails, uids chosen here."""

    def __init__(self):
        self.users = {}
        self.lock = threading.Lock()
        self.create_kwargs = []
        self.updates = []
        self.create_error = None
        self.update_error = None
        self.get_user_calls = 0
        self.on_second_get_user = None

    def add_existing(self, uid, email, disabled=False):
        self.users[uid] = SimpleNamespace(uid=uid, email=email.lower(), disabled=disabled)

    def create_user(self, **kwargs):
        self.create_kwargs.append(sorted(kwargs))
        if self.create_error:
            raise self.create_error
        with self.lock:
            email = kwargs["email"].lower()
            if any(user.email == email for user in self.users.values()):
                raise firebase_auth.EmailAlreadyExistsError("The user with the provided email already exists.",
                                                            None, None)
            uid = f"new-uid-{len(self.users) + 1:03d}"
            self.users[uid] = SimpleNamespace(uid=uid, email=email, disabled=kwargs.get("disabled", False))
            return self.users[uid]

    def get_user(self, uid, app=None):
        self.get_user_calls += 1
        if self.get_user_calls == 2 and self.on_second_get_user:
            self.on_second_get_user(uid)
        if uid not in self.users:
            raise firebase_auth.UserNotFoundError("No user record found for the provided user ID")
        return self.users[uid]

    def update_user(self, uid, **kwargs):
        self.updates.append((uid, dict(kwargs)))
        if self.update_error:
            raise self.update_error
        for key, value in kwargs.items():
            setattr(self.users[uid], key, value)
        return self.users[uid]


class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class FakeDocument:
    def __init__(self, store, collection, doc_id):
        self.store, self.key = store, (collection, doc_id)

    def get(self):
        with self.store.lock:
            return FakeSnapshot(self.store.docs.get(self.key))

    def create(self, data, retry=None, timeout=None):
        error = self.store.create_errors.get(self.key[0])
        if error:
            raise error
        with self.store.lock:
            if self.key in self.store.docs:
                raise google_exceptions.AlreadyExists("Document already exists")
            self.store.docs[self.key] = dict(data)
            self.store.write_order.append(self.key[0])


class FakeFirestore:
    def __init__(self):
        self.docs = {}
        self.lock = threading.Lock()
        self.create_errors = {}
        self.write_order = []

    def collection(self, name):
        return SimpleNamespace(document=lambda doc_id: FakeDocument(self, name, doc_id))

    def doc(self, collection, doc_id):
        return self.docs.get((collection, doc_id))


class CapturedLogs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class RegistrationTestBase(unittest.TestCase):
    def setUp(self):
        self.auth = FakeAuth()
        self.store = FakeFirestore()
        self.init = self.patch("services.registration_service.initialize_firebase", return_value=self.store)
        self.patch("services.account_access_service.initialize_firebase", return_value=self.store)
        for name in ("create_user", "get_user", "update_user"):
            self.patch(f"services.registration_service.firebase_auth.{name}", side_effect=getattr(self.auth, name))
        root = logging.getLogger()
        self.logs = CapturedLogs()
        saved_level = root.level
        root.addHandler(self.logs)
        root.setLevel(logging.DEBUG)
        self.addCleanup(lambda: (root.removeHandler(self.logs), root.setLevel(saved_level)))
        self.addCleanup(self.assert_nothing_private_logged)

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def fresh(self):
        """Empty Auth and Firestore again (the patches keep pointing at these objects)."""
        self.auth.__init__()
        self.store.__init__()

    def assert_nothing_private_logged(self):
        for message in self.logs.messages:
            for secret in (PASSWORD, NAME, EMAIL):
                self.assertNotIn(secret, message)

    def register(self, **overrides):
        values = {"name": NAME, "email": EMAIL, "password": PASSWORD, "role": "spm_leaver", **overrides}
        return registration.register_student(**values)

    def assert_registration_error(self, code, **overrides):
        with self.assertRaises(registration.RegistrationError) as ctx:
            self.register(**overrides)
        error = ctx.exception
        self.assertEqual(error.code, code)
        self.assertEqual(str(error), code)
        for secret in (PASSWORD, NAME, EMAIL):
            self.assertNotIn(secret, repr(error))
            self.assertNotIn(secret, repr(vars(error)))
        return error

    def only_user(self):
        self.assertEqual(len(self.auth.users), 1)
        return next(iter(self.auth.users.values()))


# ------------------------------------------------------------------ service
class SuccessfulRegistrationTests(RegistrationTestBase):
    def test_both_student_roles_get_account_profile_and_active_record(self):
        for role in ("spm_leaver", "form_4_5"):
            with self.subTest(role=role):
                self.fresh()
                uid = self.register(role=role, name=f"  {NAME}  ", email=f"  {EMAIL.upper()} ")
                user = self.only_user()
                self.assertEqual(uid, user.uid)
                self.assertFalse(user.disabled)
                self.assertEqual(self.store.doc("users", uid),
                                 {"name": NAME, "email": EMAIL, "role": role, "createdAt": SERVER_TIMESTAMP})
                self.assertEqual(self.store.doc("account_access", uid), {"state": "active", "version": 1})
                self.assertEqual(self.store.write_order, ["users", "account_access"], "access record written last")
                self.assertEqual(self.auth.create_kwargs, [["disabled", "email", "email_verified", "password"]])
                self.assertEqual(self.auth.updates, [], "a completed registration changes nothing afterwards")


class InputValidationTests(RegistrationTestBase):
    def test_invalid_input_is_refused_before_any_firebase_call(self):
        cases = [
            ({"name": ""}, ["name"]), ({"name": "   "}, ["name"]), ({"name": "x" * 101}, ["name"]),
            ({"name": "bad\nname"}, ["name"]), ({"name": 123}, ["name"]), ({"name": None}, ["name"]),
            ({"email": ""}, ["email"]), ({"email": "no-at-sign"}, ["email"]), ({"email": "a@b"}, ["email"]),
            ({"email": "two@@example.test"}, ["email"]), ({"email": "sp ace@example.test"}, ["email"]),
            ({"email": "a" * 250 + "@example.test"}, ["email"]), ({"email": ["x@example.test"]}, ["email"]),
            ({"password": "12345"}, ["password"]), ({"password": "x" * 129}, ["password"]),
            ({"password": 12345678}, ["password"]), ({"password": None}, ["password"]),
            ({"role": "admin"}, ["role"]), ({"role": "upper_secondary"}, ["role"]), ({"role": "SPM_LEAVER"}, ["role"]),
            ({"role": ""}, ["role"]), ({"role": None}, ["role"]),
            ({"name": "", "role": "admin", "password": "1"}, ["name", "password", "role"]),
        ]
        for overrides, fields in cases:
            with self.subTest(overrides=overrides):
                error = self.assert_registration_error(registration.INVALID_REGISTRATION, **overrides)
                self.assertEqual(list(error.fields), fields)
        self.init.assert_not_called()
        self.assertEqual(self.auth.create_kwargs, [])
        self.assertEqual(self.store.docs, {})


class ExistingAccountTests(RegistrationTestBase):
    def test_an_email_already_in_use_is_refused_and_the_existing_account_is_untouched(self):
        for disabled, record in ((False, None), (True, None), (False, {"state": "disabled", "version": 3}),
                                 (False, {"state": "deleted", "version": 4})):
            with self.subTest(disabled=disabled, record=record):
                self.fresh()
                self.auth.add_existing("existing-uid", EMAIL, disabled=disabled)
                if record:
                    self.store.docs[("account_access", "existing-uid")] = dict(record)
                before = dict(self.store.docs)
                self.assert_registration_error(registration.EMAIL_IN_USE, email=EMAIL.upper())
                self.assertEqual(self.store.docs, before, "no profile or record is created or changed")
                self.assertEqual(self.auth.users["existing-uid"].disabled, disabled)
                self.assertEqual(self.auth.updates, [])

    def test_duplicate_requests_create_one_account(self):
        first = self.register()
        snapshot = dict(self.store.docs)
        self.assert_registration_error(registration.EMAIL_IN_USE)
        self.assertEqual(list(self.auth.users), [first])
        self.assertEqual(self.store.docs, snapshot)

    def test_concurrent_requests_for_one_email_create_one_account(self):
        workers = 16
        barrier = threading.Barrier(workers)
        uids, codes = [], []

        def attempt():
            barrier.wait()
            try:
                uids.append(self.register())
            except registration.RegistrationError as exc:
                codes.append(exc.code)

        threads = [threading.Thread(target=attempt) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(uids), 1)
        self.assertEqual(codes, [registration.EMAIL_IN_USE] * (workers - 1))
        self.assertEqual(self.store.doc("account_access", uids[0]), {"state": "active", "version": 1})


class AccountCreationFailureTests(RegistrationTestBase):
    def test_firebase_unavailable_before_creation(self):
        self.init.side_effect = FirebaseConfigError("configuration")
        self.assert_registration_error(registration.REGISTRATION_UNAVAILABLE)
        self.assertEqual(self.auth.create_kwargs, [])

    def test_auth_creation_failures_create_nothing_else(self):
        cases = [
            (firebase_exceptions.InvalidArgumentError("rejected"), registration.INVALID_REGISTRATION),
            (ValueError(f'Invalid email: "{EMAIL}"'), registration.INVALID_REGISTRATION),
            (firebase_exceptions.UnavailableError("down"), registration.REGISTRATION_UNAVAILABLE),
            (firebase_exceptions.DeadlineExceededError("timeout"), registration.REGISTRATION_UNAVAILABLE),
            (RuntimeError(PASSWORD), registration.REGISTRATION_UNAVAILABLE),
        ]
        for error, code in cases:
            with self.subTest(error=type(error).__name__):
                self.auth.create_error = error
                self.assert_registration_error(code)
                self.assertEqual(self.store.docs, {})
                self.assertEqual(self.auth.updates, [], "no account uid is known, so nothing is restricted")


class PartialRegistrationTests(RegistrationTestBase):
    """After the account exists, any failure disables it (never deletes it) and reports INCOMPLETE."""

    def assert_incomplete_and_disabled(self):
        error = self.assert_registration_error(registration.REGISTRATION_INCOMPLETE)
        user = self.only_user()
        self.assertEqual(error.uid, user.uid)
        self.assertTrue(error.restricted)
        self.assertTrue(user.disabled, "the incomplete account is disabled")
        self.assertEqual(self.auth.updates, [(user.uid, {"disabled": True})])
        return user

    def test_profile_creation_fails(self):
        self.store.create_errors["users"] = google_exceptions.ServiceUnavailable("Firestore down")
        user = self.assert_incomplete_and_disabled()
        self.assertIsNone(self.store.doc("users", user.uid))
        self.assertIsNone(self.store.doc("account_access", user.uid), "the guard stays closed")

    def test_profile_unexpectedly_exists(self):
        self.store.docs[("users", "new-uid-001")] = {"name": "Someone else"}
        user = self.assert_incomplete_and_disabled()
        self.assertEqual(self.store.doc("users", user.uid), {"name": "Someone else"})
        self.assertIsNone(self.store.doc("account_access", user.uid))

    def test_access_record_cannot_be_written(self):
        self.store.create_errors["account_access"] = google_exceptions.DeadlineExceeded("no response")
        user = self.assert_incomplete_and_disabled()
        self.assertIsNotNone(self.store.doc("users", user.uid))
        self.assertIsNone(self.store.doc("account_access", user.uid))

    def test_access_record_unexpectedly_exists(self):
        self.store.docs[("account_access", "new-uid-001")] = {"state": "disabled", "version": 2}
        user = self.assert_incomplete_and_disabled()
        self.assertEqual(self.store.doc("account_access", user.uid), {"state": "disabled", "version": 2})

    def test_auth_account_changes_during_provisioning(self):
        # Disabled in Auth after the access record was written: reported, and the record stays 'active' (HL2).
        self.auth.on_second_get_user = lambda uid: setattr(self.auth.users[uid], "disabled", True)
        user = self.assert_incomplete_and_disabled()
        self.assertEqual(self.store.doc("account_access", user.uid), {"state": "active", "version": 1})

    def test_a_failure_to_restrict_is_reported(self):
        self.store.create_errors["users"] = google_exceptions.ServiceUnavailable("Firestore down")
        self.auth.update_error = firebase_exceptions.UnavailableError("Auth down")
        error = self.assert_registration_error(registration.REGISTRATION_INCOMPLETE)
        self.assertFalse(error.restricted)
        self.assertFalse(self.only_user().disabled)
        self.assertTrue(any("could not disable" in message for message in self.logs.messages))


# -------------------------------------------------------------------- route
class RegistrationRouteTests(RegistrationTestBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(registration_routes.router, prefix="/api/account")
        self.client = TestClient(app)
        self.ready = self.patch("routes.registration._emulator_ready", return_value=True)

    def post(self, body=None, env=VALID_EMULATOR_ENV, **kwargs):
        if body is None:
            body = {"name": NAME, "email": EMAIL, "password": PASSWORD, "role": "form_4_5"}
        with firebase_env(env):
            return self.client.post(URL, json=body, **kwargs)

    def assert_no_secrets(self, response):
        for secret in (PASSWORD, NAME, EMAIL):
            self.assertNotIn(secret, response.text)

    def test_a_valid_request_registers_and_returns_only_a_status(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"status": "registered"})
        self.assert_no_secrets(response)
        user = self.only_user()
        self.assertEqual(self.store.doc("users", user.uid)["role"], "form_4_5")

    def test_the_route_does_not_exist_outside_emulator_mode(self):
        init = self.patch("core.firebase.initialize_firebase", side_effect=AssertionError("Firebase touched"))
        service = self.patch("routes.registration.registration.register_student")
        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}, {"ROUTE2UNIKL_FIREBASE_MODE": "staging"}):
            with self.subTest(env=env):
                response = self.post(env=env)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Not Found"})
        service.assert_not_called()
        self.ready.assert_not_called()
        init.assert_not_called()
        self.assertEqual(self.auth.create_kwargs, [])

    def test_an_unready_emulator_environment_is_refused(self):
        self.ready.return_value = False
        response = self.post()
        self.assertEqual((response.status_code, response.json()), (503, {"code": "REGISTRATION_UNAVAILABLE"}))
        self.assertEqual(self.auth.create_kwargs, [])

    def test_uids_claims_and_other_privileged_fields_are_refused(self):
        base = {"name": NAME, "email": EMAIL, "password": PASSWORD, "role": "spm_leaver"}
        for extra in ({"uid": "chosen-uid"}, {"admin": True}, {"customClaims": {"admin": True}},
                      {"disabled": False}, {"emailVerified": True}, {"state": "active"},
                      {"sessionsValidAfter": 0}):
            with self.subTest(extra=extra):
                response = self.post({**base, **extra})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"code": "INVALID_REGISTRATION", "fields": ["unexpected_field"]})
                self.assert_no_secrets(response)
        response = self.post({**base, "role": "admin"})
        self.assertEqual(response.json(), {"code": "INVALID_REGISTRATION", "fields": ["role"]})
        self.assertEqual(self.auth.create_kwargs, [])

    def test_malformed_requests_are_refused_without_echoing_input(self):
        cases = [
            ({"name": NAME, "email": EMAIL, "password": PASSWORD}, ["role"]),
            ({"name": 123, "email": EMAIL, "password": PASSWORD, "role": "spm_leaver"}, ["name"]),
            ({"name": NAME, "email": EMAIL, "password": 12345678, "role": "spm_leaver"}, ["password"]),
            ({"name": NAME, "email": EMAIL, "password": "short", "role": "spm_leaver"}, ["password"]),
            ({"name": NAME, "email": "not-an-email", "password": PASSWORD, "role": "spm_leaver"}, ["email"]),
        ]
        for body, fields in cases:
            with self.subTest(fields=fields):
                response = self.post(body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"code": "INVALID_REGISTRATION", "fields": fields})
                self.assert_no_secrets(response)
        for raw in (b"not json", b"[1, 2]", b'"text"', b"null"):
            with self.subTest(raw=raw), firebase_env(VALID_EMULATOR_ENV):
                response = self.client.post(URL, content=raw, headers={"content-type": "application/json"})
                self.assertEqual((response.status_code, response.json()), (422, {"code": "INVALID_REGISTRATION"}))
        self.assertEqual(self.auth.create_kwargs, [])

    def test_oversized_requests_are_refused(self):
        response = self.post({"name": NAME, "email": EMAIL, "password": PASSWORD, "role": "spm_leaver",
                              "padding": "x" * 5000})
        self.assertEqual((response.status_code, response.json()), (413, {"code": "INVALID_REGISTRATION"}))
        self.assertEqual(self.auth.create_kwargs, [])

    def test_service_outcomes_map_to_codes_without_identifiers(self):
        self.auth.add_existing("existing-uid", EMAIL)
        response = self.post()
        self.assertEqual((response.status_code, response.json()), (409, {"code": "EMAIL_IN_USE"}))

        self.auth.users.clear()
        self.store.create_errors["users"] = google_exceptions.ServiceUnavailable("down")
        response = self.post()
        self.assertEqual((response.status_code, response.json()), (503, {"code": "REGISTRATION_INCOMPLETE"}))
        self.assertNotIn(self.only_user().uid, response.text, "the uid of an incomplete account is not returned")

        self.auth.create_error = firebase_exceptions.UnavailableError("down")
        response = self.post({"name": NAME, "email": "other@example.test", "password": PASSWORD, "role": "spm_leaver"})
        self.assertEqual((response.status_code, response.json()), (503, {"code": "REGISTRATION_UNAVAILABLE"}))

    def test_the_incomplete_registration_response_differs_from_success(self):
        self.store.create_errors["users"] = google_exceptions.ServiceUnavailable("down")
        incomplete = self.post()
        self.assertEqual((incomplete.status_code, incomplete.json()), (503, {"code": "REGISTRATION_INCOMPLETE"}))
        self.assertTrue(self.only_user().disabled)
        # A retry is refused like any email in use; it never completes or re-enables the account.
        self.store.create_errors.clear()
        retry = self.post()
        self.assertEqual((retry.status_code, retry.json()), (409, {"code": "EMAIL_IN_USE"}))
        self.assertTrue(self.only_user().disabled)
        self.assertEqual(len(self.auth.updates), 1)

    def test_the_router_is_not_mounted_and_only_this_route_uses_the_service(self):
        self.assertNotIn("registration", (BACKEND_DIR / "main.py").read_text(encoding="utf-8"))
        for path in sorted((BACKEND_DIR / "routes").glob("*.py")):
            if path.name != "registration.py":
                with self.subTest(path=path.name):
                    self.assertNotIn("registration_service", path.read_text(encoding="utf-8"))


class EmulatorReadinessTests(unittest.TestCase):
    """The real readiness check: the recorded Firebase configuration must be emulator mode, whatever the
    environment says, before the registration service can run."""

    def setUp(self):
        patches = {
            "initialize": mock.patch("core.firebase.initialize_firebase"),
            "check": mock.patch("core.firebase.check_runtime_configuration"),
            "config": mock.patch("core.firebase.initialized_config",
                                 return_value=SimpleNamespace(mode="emulator")),
            "service": mock.patch("routes.registration.registration.register_student"),
        }
        self.mocks = {name: patcher.start() for name, patcher in patches.items()}
        for patcher in patches.values():
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(registration_routes.router, prefix="/api/account")
        self.client = TestClient(app)

    def test_readiness_requires_a_valid_recorded_emulator_configuration(self):
        self.assertTrue(registration_routes._emulator_ready())
        cases = {
            "initialisation fails": ("initialize", {"side_effect": FirebaseConfigError("x")}),
            "runtime check fails": ("check", {"side_effect": FirebaseConfigError("x")}),
            "nothing recorded": ("config", {"return_value": None}),
            "recorded in production mode": ("config", {"return_value": SimpleNamespace(mode="production")}),
        }
        for label, (name, settings) in cases.items():
            with self.subTest(label):
                self.mocks[name].configure_mock(**settings)
                self.assertFalse(registration_routes._emulator_ready())
                self.mocks[name].configure_mock(side_effect=None, return_value=SimpleNamespace(mode="emulator"))

    def test_a_production_initialised_process_never_runs_the_service(self):
        # The environment claims emulator mode, but Firebase was initialised in production mode.
        self.mocks["config"].return_value = SimpleNamespace(mode="production")
        with firebase_env(VALID_EMULATOR_ENV):
            response = self.client.post(URL, json={"name": NAME, "email": EMAIL, "password": PASSWORD,
                                                   "role": "spm_leaver"})
        self.assertEqual((response.status_code, response.json()), (503, {"code": "REGISTRATION_UNAVAILABLE"}))
        self.mocks["service"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
