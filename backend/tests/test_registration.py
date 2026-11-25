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
import contextlib
import importlib
import io
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


def password_of(length):
    """A distinctive test password of exactly `length` characters."""
    return ("Zq9-" * 40)[:length]


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


class PasswordCaptureBase(RegistrationTestBase):
    """Records the password each create_user call receives (to prove it is passed on unchanged)."""

    def setUp(self):
        super().setUp()
        self.passwords_sent = []

        def capture(**kwargs):
            self.passwords_sent.append(kwargs.get("password"))
            return self.auth.create_user(**kwargs)

        self.patch("services.registration_service.firebase_auth.create_user", side_effect=capture)

    def assert_password_not_logged(self, password):
        for message in self.logs.messages:
            self.assertNotIn(password, message)


class PasswordLengthBoundaryTests(PasswordCaptureBase):
    """Regression for browser check M5 (26 Nov 2026): the 6-128 character password rule at its boundaries.

    Length is the number of characters (code points) of the password exactly as received: it is never
    trimmed or changed. Invalid lengths create no Auth account, profile or access record.
    """

    def test_5_and_129_characters_are_refused_before_any_firebase_call(self):
        for password in (password_of(5), password_of(129), "\U0001F600" * 129):
            with self.subTest(length=len(password)):
                error = self.assert_registration_error(registration.INVALID_REGISTRATION, password=password)
                self.assertEqual(list(error.fields), ["password"])
                self.assertNotIn(password, repr(vars(error)))
                self.assert_password_not_logged(password)
        self.init.assert_not_called()
        self.assertEqual(self.passwords_sent, [], "Firebase Authentication is never called")
        self.assertEqual(self.auth.users, {}, "no Auth account")
        self.assertEqual(self.store.docs, {}, "no profile and no access record")

    def test_6_and_128_characters_register_with_the_password_unchanged(self):
        for password in (password_of(6), password_of(128), "ab cd1", "\U0001F600" * 128):
            with self.subTest(length=len(password)):
                self.fresh()
                self.passwords_sent.clear()
                uid = self.register(password=password)
                self.assertEqual(self.passwords_sent, [password], "sent to Firebase exactly as received")
                self.assertEqual(self.store.doc("account_access", uid), {"state": "active", "version": 1})
                self.assert_password_not_logged(password)

    def test_spaces_count_and_are_never_trimmed(self):
        # Spaces are ordinary characters: they count towards the length and are kept. (The M5 input, a
        # leading TAB plus 5 characters, is refused since the JL9 control-character rule; see below.)
        for password in (" " + password_of(5), password_of(5) + " ", "Test 123"):
            with self.subTest(password=repr(password)):
                self.fresh()
                self.passwords_sent.clear()
                self.register(password=password)
                self.assertEqual(self.passwords_sent, [password], "sent to Firebase exactly as received")
        self.fresh()
        self.passwords_sent.clear()
        self.assert_registration_error(registration.INVALID_REGISTRATION, password="   " + password_of(2))
        self.assertEqual(self.passwords_sent, [], "5 characters including spaces: refused, not padded or trimmed")
        self.assertEqual(self.auth.users, {})
        self.assertEqual(self.store.docs, {})


class PasswordControlCharacterTests(PasswordCaptureBase):
    """JL9 (26 Nov 2026): passwords containing Unicode control characters (category Cc) are refused.

    Checked on the password exactly as received (never trimmed, normalised or stripped), before any
    Firebase call; only the field name is reported, never the password or its characters.
    """

    # Every one of these is otherwise valid (6 to 128 characters).
    CONTROL_PASSWORDS = (
        "\tTest1",            # the M5 input: a leading TAB
        "Test1\t",            # trailing TAB
        "Test\n123",          # line feed
        "Test\r123",          # carriage return
        "Test\r\n123",        # CRLF
        "Test\x7f123",        # DEL
        "\x00Test123",        # NUL
        "Test\x1b123",        # ESC
        "Test\x85123",        # NEL (C1 control)
        "Test\x9f123",        # last C1 control
    )

    def test_control_characters_are_refused_before_any_firebase_call(self):
        for password in self.CONTROL_PASSWORDS:
            with self.subTest(password=repr(password)):
                error = self.assert_registration_error(registration.INVALID_REGISTRATION, password=password)
                self.assertEqual(list(error.fields), ["password"])
                self.assertNotIn(password, repr(vars(error)))
                self.assert_password_not_logged(password)
        self.init.assert_not_called()
        self.assertEqual(self.passwords_sent, [], "Firebase Authentication is never called")
        self.assertEqual(self.auth.users, {}, "no Auth account")
        self.assertEqual(self.store.docs, {}, "no profile and no access record")

    def test_the_owner_cases(self):
        self.assert_registration_error(registration.INVALID_REGISTRATION, password="Test1")   # 5 characters
        self.assert_registration_error(registration.INVALID_REGISTRATION, password="\tTest1")  # TAB + Test1
        self.assertEqual(self.passwords_sent, [])
        self.register(password="Test123")                                                       # 7 characters
        self.assertEqual(self.passwords_sent, ["Test123"])

    def test_every_code_point_in_category_cc_is_refused(self):
        import unicodedata
        control = [code for code in range(0x110000) if unicodedata.category(chr(code)) == "Cc"]
        self.assertEqual(control, list(range(0x00, 0x20)) + list(range(0x7F, 0xA0)),
                         "category Cc is exactly U+0000-U+001F and U+007F-U+009F (the frontend uses the same set)")
        for code in control:
            with self.subTest(code=f"U+{code:04X}"), self.assertRaises(registration.RegistrationError) as ctx:
                registration.validate_registration(NAME, EMAIL, f"Test{chr(code)}12", "spm_leaver")
            self.assertEqual(list(ctx.exception.fields), ["password"])
        self.init.assert_not_called()

    def test_printable_characters_next_to_the_control_ranges_are_accepted(self):
        # U+0020 (space), U+007E (~), U+00A0 (no-break space) and U+00A1 are not category Cc.
        for password in ("Test 123", "Test~123", "Test 123", "Test¡123"):
            with self.subTest(password=repr(password)):
                self.fresh()
                self.passwords_sent.clear()
                self.register(password=password)
                self.assertEqual(self.passwords_sent, [password])


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

    def test_password_length_boundaries(self):
        """Regression (M5): 5 and 129 characters → 422 naming only the field, nothing created; 6 and 128 → 201."""
        for length, status in ((5, 422), (129, 422), (6, 201), (128, 201)):
            with self.subTest(length=length):
                self.fresh()
                password = password_of(length)
                response = self.post({"name": NAME, "email": EMAIL, "password": password, "role": "spm_leaver"})
                self.assertEqual(response.status_code, status)
                self.assertNotIn(password, response.text)
                self.assert_no_secrets(response)
                if status == 422:
                    self.assertEqual(response.json(), {"code": "INVALID_REGISTRATION", "fields": ["password"]})
                    self.assertEqual(self.auth.create_kwargs, [], "no Firebase Authentication call")
                    self.assertEqual(self.auth.users, {}, "no Auth account")
                    self.assertEqual(self.store.docs, {}, "no profile and no access record")
                else:
                    self.assertEqual(response.json(), {"status": "registered"})
                    user = self.only_user()
                    self.assertEqual(self.store.doc("account_access", user.uid), {"state": "active", "version": 1})
                for message in self.logs.messages:
                    self.assertNotIn(password, message)

    def test_passwords_with_control_characters_are_refused(self):
        """JL9: TAB, line feed, carriage return, DEL → 422 naming only the field; nothing created; not echoed."""
        for password in ("\tTest1", "Test\n123", "Test\r123", "Test\x7f123", "Test1\t"):
            with self.subTest(password=repr(password)):
                response = self.post({"name": NAME, "email": EMAIL, "password": password, "role": "spm_leaver"})
                self.assertEqual((response.status_code, response.json()),
                                 (422, {"code": "INVALID_REGISTRATION", "fields": ["password"]}))
                self.assertNotIn(password, response.text)
                self.assertNotIn("Test", response.text)
                for message in self.logs.messages:
                    self.assertNotIn(password, message)
        self.assertEqual(self.auth.create_kwargs, [], "no Firebase Authentication call")
        self.assertEqual(self.auth.users, {}, "no Auth account")
        self.assertEqual(self.store.docs, {}, "no profile and no access record")
        response = self.post({"name": NAME, "email": EMAIL, "password": "Test 123", "role": "spm_leaver"})
        self.assertEqual(response.status_code, 201, "an internal space is an ordinary character")

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

    def test_main_mounts_the_router_only_in_emulator_mode(self):
        def registration_paths(env):
            sys.modules.pop("main", None)
            try:
                with firebase_env(env), mock.patch("core.firebase.initialize_firebase", return_value=None), \
                        contextlib.redirect_stdout(io.StringIO()):
                    main = importlib.import_module("main")
                # Included routers are not plain routes in app.routes here; the OpenAPI schema lists every path.
                return [path for path in main.app.openapi()["paths"] if "register" in path]
            finally:
                sys.modules.pop("main", None)

        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}, {"ROUTE2UNIKL_FIREBASE_MODE": "staging"}):
            with self.subTest(env=env):
                self.assertEqual(registration_paths(env), [], "no registration route outside emulator mode")
        self.assertEqual(registration_paths(VALID_EMULATOR_ENV), [URL])

    def test_only_the_registration_route_uses_the_service(self):
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
