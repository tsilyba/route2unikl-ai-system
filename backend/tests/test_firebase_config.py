# backend/tests/test_firebase_config.py
"""
M3B-1B-P1-A: Firebase initialization modes, the recorded configuration and the
runtime configuration check (backend/core/firebase.py, backend/core/auth.py).

Run from the backend directory with the other backend tests:
    python -m unittest discover -s tests -t . -v

Safety: no network, emulator or real credential is used. Most tests replace
the Firebase Admin SDK app registry, the service-account loader and the
Firestore client with in-memory fakes. ProductionVerifierTests creates a real
Firebase app with a fake service-account credential (a made-up project, no key
file) so that the real ID-token verifier is exercised; any HTTP request there
fails the test. Every Firebase-related environment variable is replaced for
each test.
"""
import base64
import contextlib
import json
import os
import sys
import time
import unittest
from dataclasses import FrozenInstanceError
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

import firebase_admin  # noqa: E402
import requests  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
from firebase_admin import credentials  # noqa: E402
from google.auth.credentials import AnonymousCredentials  # noqa: E402

from core import auth as core_auth  # noqa: E402
from core import firebase as core_firebase  # noqa: E402
from routes import admin_users as admin_users_routes  # noqa: E402
from routes import auth_check as auth_check_routes  # noqa: E402

PROJECT = "demo-route2unikl"
PRODUCTION_TEST_PROJECT = "route2unikl-unit-test"  # made up for these tests; never contacted
KEY_PATH = str(BACKEND_DIR / "serviceAccountKey.json")
# Used as a configuration value where an error message must not echo it.
SENTINEL = "sentinel-value-7f3a9c"

FIREBASE_ENV_NAMES = (
    core_firebase.MODE_ENV,
    core_firebase.EMULATOR_PROJECT_ENV,
    *core_firebase.EMULATOR_HOST_ENVS,
    *core_firebase.GOOGLE_PROJECT_ENVS,
    core_firebase.GOOGLE_CREDENTIALS_ENV,
)

VALID_EMULATOR_ENV = {
    "ROUTE2UNIKL_FIREBASE_MODE": "emulator",
    "ROUTE2UNIKL_EMULATOR_PROJECT_ID": PROJECT,
    "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
    "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080",
}

PRODUCTION_CONFIG = core_firebase.FirebaseConfig(
    "production", PRODUCTION_TEST_PROJECT, None, None, "service_account")
EMULATOR_CONFIG = core_firebase.FirebaseConfig(
    "emulator", PROJECT, "127.0.0.1:9099", "127.0.0.1:8080", "emulator")

# Endpoints protected by get_current_user (student) or require_admin, with a token allowed on each.
PROTECTED_ENDPOINTS = (
    ("/api/auth/me", "student-token"),
    ("/api/admin/verify", "admin-token"),
    ("/api/admin/users", "admin-token"),
    ("/api/admin/users/student-uid", "admin-token"),
)


@contextlib.contextmanager
def firebase_env(values):
    """Remove every Firebase-related variable, then set `values`; restore afterwards."""
    with mock.patch.dict(os.environ):
        for name in FIREBASE_ENV_NAMES:
            os.environ.pop(name, None)
        os.environ.update(values)
        yield


def emulator_env(**changes):
    """The valid emulator environment with some variables changed (None removes one)."""
    env = dict(VALID_EMULATOR_ENV)
    for name, value in changes.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def mode_label(env):
    return env.get("ROUTE2UNIKL_FIREBASE_MODE", "production")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def fake_claims(token, check_revoked=False, clock_skew_seconds=0, app=None):
    """Stand-in for firebase_admin.auth.verify_id_token keyed by fake token strings."""
    claims = {
        "student-token": {"uid": "student-uid"},
        "admin-token": {"uid": "admin-uid", "admin": True},
        "string-admin-token": {"uid": "string-claim-uid", "admin": "true"},
    }
    if token in claims:
        return dict(claims[token])
    raise firebase_auth.InvalidIdTokenError("Invalid token")


class FakeFirebaseApps:
    """In-memory stand-in for the Firebase Admin SDK's app registry."""

    def __init__(self):
        self.apps = {}

    def initialize_app(self, credential, options=None, name="[DEFAULT]"):
        if name in self.apps:
            raise ValueError("The Firebase app already exists.")
        options = dict(options or {})
        app = SimpleNamespace(name=name, credential=credential, options=options,
                              project_id=options.get("projectId") or getattr(credential, "project_id", None))
        self.apps[name] = app
        return app

    def get_app(self, name="[DEFAULT]"):
        if name not in self.apps:
            raise ValueError("The default Firebase app does not exist.")
        return self.apps[name]

    def delete_app(self, app):
        self.apps.pop(app.name, None)


class FirebaseTestBase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeFirebaseApps()
        self.service_account = SimpleNamespace(project_id=PRODUCTION_TEST_PROJECT)
        self.certificate = self.patch("core.firebase.credentials.Certificate", return_value=self.service_account)
        self.initialize_app = self.patch("core.firebase.firebase_admin.initialize_app",
                                         side_effect=self.fake.initialize_app)
        self.patch("core.firebase.firebase_admin.get_app", side_effect=self.fake.get_app)
        self.delete_app = self.patch("core.firebase.firebase_admin.delete_app", side_effect=self.fake.delete_app)
        self.firestore_client = self.patch("core.firebase.firestore.client", return_value=mock.sentinel.db)
        # A fresh process: no recorded configuration or app (restored after the test).
        state = mock.patch.multiple(core_firebase, _initialized_config=None, _initialized_app=None)
        state.start()
        self.addCleanup(state.stop)

    def patch(self, target, **kwargs):
        patcher = mock.patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def reset_mocks(self):
        for m in (self.certificate, self.initialize_app, self.delete_app, self.firestore_client):
            m.reset_mock()

    def reset_firebase(self):
        """Forget every app and the recorded configuration, as in a new process."""
        self.fake.apps.clear()
        core_firebase._initialized_config = None
        core_firebase._initialized_app = None
        self.reset_mocks()

    def initialize(self, env):
        with firebase_env(env):
            return core_firebase.initialize_firebase()

    def check(self, env):
        with firebase_env(env):
            core_firebase.check_runtime_configuration()

    def assert_config_error(self, call, env):
        """`call` raises FirebaseConfigError under `env`; the message never contains SENTINEL."""
        with firebase_env(env), self.assertRaises(core_firebase.FirebaseConfigError) as ctx:
            call()
        message = str(ctx.exception)
        self.assertNotIn(SENTINEL, message, "error messages name variables, never values")
        return message

    def assert_refused(self, env):
        """Initialization raises FirebaseConfigError without loading a key or creating an app."""
        self.reset_mocks()
        message = self.assert_config_error(core_firebase.initialize_firebase, env)
        self.certificate.assert_not_called()
        self.initialize_app.assert_not_called()
        self.firestore_client.assert_not_called()
        return message


class ProductionModeTests(FirebaseTestBase):
    def test_production_initialization_loads_the_service_account_and_records_the_configuration(self):
        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}):
            with self.subTest(env=env):
                self.reset_firebase()
                self.assertIs(self.initialize(env), mock.sentinel.db)
                self.certificate.assert_called_once_with(KEY_PATH)
                self.initialize_app.assert_called_once_with(self.service_account)
                self.firestore_client.assert_called_once_with()
                self.assertEqual(core_firebase.initialized_config(), PRODUCTION_CONFIG)

    def test_repeated_initialization_reuses_the_recorded_app_without_reloading_the_key(self):
        self.initialize({})
        snapshot = core_firebase.initialized_config()
        self.assertIs(self.initialize({}), mock.sentinel.db)
        self.assertIs(self.initialize({"ROUTE2UNIKL_FIREBASE_MODE": "production"}), mock.sentinel.db)
        self.certificate.assert_called_once_with(KEY_PATH)
        self.initialize_app.assert_called_once()
        self.assertIs(core_firebase.initialized_config(), snapshot)

    def test_refuses_to_start_while_any_emulator_setting_is_present(self):
        for name in ("FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST",
                     "ROUTE2UNIKL_EMULATOR_PROJECT_ID"):
            for value in ("127.0.0.1:9099", "", SENTINEL):
                for mode in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}):
                    with self.subTest(name=name, value=value, mode=mode):
                        message = self.assert_refused({**mode, name: value})
                        self.assertIn(name, message)

    def test_an_app_not_created_by_this_module_is_refused(self):
        self.fake.initialize_app(self.service_account)  # created elsewhere
        self.assert_refused({})
        self.assert_config_error(core_firebase.check_runtime_configuration, {})
        self.assertIsNone(core_firebase.initialized_config())

    def test_service_account_is_loaded_only_in_production_mode(self):
        self.initialize(VALID_EMULATOR_ENV)
        self.certificate.assert_not_called()


class ModeSelectionTests(FirebaseTestBase):
    def test_unknown_or_malformed_mode_is_refused_without_fallback(self):
        for mode in ("", "Emulator", "EMULATOR", "emulator ", " production", "prod",
                     "test", "development", "false", SENTINEL):
            # Alone (a fallback to production would load the service account) and with the
            # emulator settings (a fallback to emulator mode would start the emulator app).
            for env in ({}, VALID_EMULATOR_ENV):
                with self.subTest(mode=mode, with_emulator_settings=bool(env)):
                    message = self.assert_refused({**env, "ROUTE2UNIKL_FIREBASE_MODE": mode})
                    self.assertTrue(message.startswith("ROUTE2UNIKL_FIREBASE_MODE must be"), message)

    def test_emulator_mode_without_its_settings_never_falls_back_to_production(self):
        # No emulator host or project is set, so a fallback would load the service account.
        self.assert_refused({"ROUTE2UNIKL_FIREBASE_MODE": "emulator"})


class EmulatorModeTests(FirebaseTestBase):
    def test_valid_configuration_uses_anonymous_emulator_credential_and_demo_project(self):
        self.assertIs(self.initialize(VALID_EMULATOR_ENV), mock.sentinel.db)
        self.certificate.assert_not_called()
        self.initialize_app.assert_called_once()
        credential, options = self.initialize_app.call_args.args
        self.assertIsInstance(credential, core_firebase.EmulatorCredential)
        self.assertIsInstance(credential.get_credential(), AnonymousCredentials)
        self.assertEqual(options, {"projectId": PROJECT, "httpTimeout": 10})
        self.assertEqual(core_firebase.initialized_config(), EMULATOR_CONFIG)

    def test_accepts_loopback_hosts_and_a_matching_google_project(self):
        accepted = [
            emulator_env(FIREBASE_AUTH_EMULATOR_HOST="localhost:9099"),
            emulator_env(FIRESTORE_EMULATOR_HOST="[::1]:8080"),
            emulator_env(FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:1", FIRESTORE_EMULATOR_HOST="127.0.0.1:65535"),
            emulator_env(GCLOUD_PROJECT=PROJECT, GOOGLE_CLOUD_PROJECT=PROJECT),  # as set by emulators:exec
        ]
        for env in accepted:
            with self.subTest(env=env):
                self.reset_firebase()
                self.initialize(env)
                self.initialize_app.assert_called_once()
                self.certificate.assert_not_called()
                self.check(env)

    def test_existing_emulator_app_is_reused_only_if_this_module_created_it(self):
        self.initialize(VALID_EMULATOR_ENV)
        self.assertIs(self.initialize(VALID_EMULATOR_ENV), mock.sentinel.db)
        self.initialize_app.assert_called_once()

        self.reset_firebase()
        self.fake.initialize_app(core_firebase.EmulatorCredential(), {"projectId": PROJECT})  # created elsewhere
        self.assert_refused(VALID_EMULATOR_ENV)

    def test_refuses_a_missing_or_non_demo_project_id(self):
        for value in (None, "", "route2unikl", "demo-", "demo-Route2UniKL", "demo_route2unikl",
                      "xdemo-route2unikl", "demo-route2unikl ", " demo-route2unikl", "demo-" + "a" * 30,
                      SENTINEL):
            with self.subTest(value=value):
                message = self.assert_refused(emulator_env(ROUTE2UNIKL_EMULATOR_PROJECT_ID=value))
                self.assertIn("ROUTE2UNIKL_EMULATOR_PROJECT_ID", message)

    def test_refuses_missing_or_non_loopback_emulator_hosts(self):
        invalid_hosts = (None, "", "0.0.0.0:9099", "192.168.1.10:9099", "10.0.0.5:9099", "127.0.0.2:9099",
                         "example.com:9099", "localhost.example.test:9099", "http://127.0.0.1:9099",
                         "127.0.0.1", "127.0.0.1:", "127.0.0.1:0", "127.0.0.1:65536", "127.0.0.1:9099/path",
                         " 127.0.0.1:9099", "127.0.0.1:9099 ", "[::]:9099", "::1:9099", SENTINEL)
        for name in ("FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"):
            for value in invalid_hosts:
                with self.subTest(name=name, value=value):
                    message = self.assert_refused(emulator_env(**{name: value}))
                    self.assertIn(name, message)

    def test_refuses_application_default_credentials(self):
        for value in (SENTINEL, ""):
            with self.subTest(value=value):
                message = self.assert_refused(emulator_env(GOOGLE_APPLICATION_CREDENTIALS=value))
                self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", message)

    def test_refuses_a_conflicting_google_project(self):
        for name in ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT"):
            for value in ("route2unikl", "demo-other", "", SENTINEL):
                with self.subTest(name=name, value=value):
                    message = self.assert_refused(emulator_env(**{name: value}))
                    self.assertIn(name, message)


class InitializationLifecycleTests(FirebaseTestBase):
    def test_configuration_is_recorded_after_success_and_is_immutable(self):
        self.assertIsNone(core_firebase.initialized_config())
        self.initialize(VALID_EMULATOR_ENV)
        snapshot = core_firebase.initialized_config()
        self.assertEqual(snapshot, EMULATOR_CONFIG)
        with self.assertRaises(FrozenInstanceError):
            snapshot.auth_emulator_host = "127.0.0.1:9100"

    def test_a_failure_after_creating_the_app_removes_it_and_can_be_retried(self):
        for env in ({}, VALID_EMULATOR_ENV):
            with self.subTest(mode=mode_label(env)):
                self.reset_firebase()
                self.firestore_client.side_effect = RuntimeError("Firestore client unavailable")
                with firebase_env(env), self.assertRaises(RuntimeError):
                    core_firebase.initialize_firebase()
                self.delete_app.assert_called_once()
                self.assertEqual(self.fake.apps, {}, "the half-initialized app is removed")
                self.assertIsNone(core_firebase.initialized_config())
                self.assert_config_error(core_firebase.check_runtime_configuration, env)

                self.firestore_client.side_effect = None
                self.assertIs(self.initialize(env), mock.sentinel.db)
                self.assertIsNotNone(core_firebase.initialized_config())
                self.check(env)

    def test_an_unreadable_key_or_unknown_project_records_nothing_and_can_be_retried(self):
        self.certificate.side_effect = FileNotFoundError("serviceAccountKey.json")
        with firebase_env({}), self.assertRaises(FileNotFoundError):
            core_firebase.initialize_firebase()
        self.initialize_app.assert_not_called()
        self.assertIsNone(core_firebase.initialized_config())

        self.certificate.side_effect = None
        self.service_account.project_id = None
        self.assert_config_error(core_firebase.initialize_firebase, {})
        self.assertEqual(self.fake.apps, {}, "the app with an unknown project is removed")
        self.assertIsNone(core_firebase.initialized_config())

        self.service_account.project_id = PRODUCTION_TEST_PROJECT
        self.initialize({})
        self.assertEqual(core_firebase.initialized_config(), PRODUCTION_CONFIG)

    def test_recreating_a_removed_app_requires_the_recorded_configuration(self):
        self.initialize(VALID_EMULATOR_ENV)
        snapshot = core_firebase.initialized_config()
        self.fake.apps.clear()  # the app was torn down, as in a test
        for env in (emulator_env(FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9100"),
                    emulator_env(FIRESTORE_EMULATOR_HOST="127.0.0.1:8081"),
                    emulator_env(ROUTE2UNIKL_EMULATOR_PROJECT_ID="demo-other"),
                    {}):
            with self.subTest(env=env):
                self.assert_refused(env)
                self.assertIs(core_firebase.initialized_config(), snapshot, "never overwritten")
        self.initialize(VALID_EMULATOR_ENV)
        self.assertIs(core_firebase.initialized_config(), snapshot)
        self.check(VALID_EMULATOR_ENV)

    def test_a_recreated_production_app_must_have_the_recorded_project(self):
        self.initialize({})
        snapshot = core_firebase.initialized_config()
        self.fake.apps.clear()
        self.service_account.project_id = "another-project"
        self.assert_config_error(core_firebase.initialize_firebase, {})
        self.assertEqual(self.fake.apps, {})
        self.assertIs(core_firebase.initialized_config(), snapshot)


class RuntimeConfigurationTests(FirebaseTestBase):
    def test_uninitialized_state_is_refused(self):
        for env in ({}, VALID_EMULATOR_ENV):
            with self.subTest(mode=mode_label(env)):
                self.assert_config_error(core_firebase.check_runtime_configuration, env)

    def test_the_recorded_configuration_passes(self):
        for env in ({}, VALID_EMULATOR_ENV):
            with self.subTest(mode=mode_label(env)):
                self.reset_firebase()
                self.initialize(env)
                self.check(env)

    def test_production_refuses_emulator_settings_introduced_after_initialization(self):
        self.initialize({})
        for name, value in (("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099"),
                            ("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080"),
                            ("ROUTE2UNIKL_EMULATOR_PROJECT_ID", PROJECT),
                            ("FIREBASE_AUTH_EMULATOR_HOST", SENTINEL)):
            for call in (core_firebase.check_runtime_configuration, core_firebase.initialize_firebase):
                with self.subTest(name=name, value=value, call=call.__name__):
                    self.assertIn(name, self.assert_config_error(call, {name: value}))
        self.check({})

    def test_mode_changes_after_initialization_are_refused(self):
        self.initialize({})
        for env in (VALID_EMULATOR_ENV, {"ROUTE2UNIKL_FIREBASE_MODE": SENTINEL}):
            with self.subTest(initialized="production", env=env):
                self.assert_config_error(core_firebase.check_runtime_configuration, env)

        self.reset_firebase()
        self.initialize(VALID_EMULATOR_ENV)
        for env in ({}, {"ROUTE2UNIKL_FIREBASE_MODE": "production"},
                    emulator_env(ROUTE2UNIKL_FIREBASE_MODE="production"),
                    emulator_env(ROUTE2UNIKL_FIREBASE_MODE=SENTINEL)):
            with self.subTest(initialized="emulator", env=env):
                self.assert_config_error(core_firebase.check_runtime_configuration, env)

    def test_emulator_settings_removed_or_changed_after_initialization_are_refused(self):
        self.initialize(VALID_EMULATOR_ENV)
        cases = {
            "Auth emulator host removed": emulator_env(FIREBASE_AUTH_EMULATOR_HOST=None),
            "Firestore emulator host removed": emulator_env(FIRESTORE_EMULATOR_HOST=None),
            "emulator project removed": emulator_env(ROUTE2UNIKL_EMULATOR_PROJECT_ID=None),
            "Auth emulator host changed (port)": emulator_env(FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9100"),
            "Auth emulator host changed (name)": emulator_env(FIREBASE_AUTH_EMULATOR_HOST="localhost:9099"),
            "Auth emulator host changed (IPv6)": emulator_env(FIREBASE_AUTH_EMULATOR_HOST="[::1]:9099"),
            "Auth emulator host made non-loopback": emulator_env(FIREBASE_AUTH_EMULATOR_HOST="0.0.0.0:9099"),
            "Firestore emulator host changed": emulator_env(FIRESTORE_EMULATOR_HOST="127.0.0.1:8081"),
            "emulator project changed": emulator_env(ROUTE2UNIKL_EMULATOR_PROJECT_ID="demo-other"),
            "conflicting Google project": emulator_env(GCLOUD_PROJECT="demo-other"),
            "application-default credentials added": emulator_env(GOOGLE_APPLICATION_CREDENTIALS=SENTINEL),
        }
        for label, env in cases.items():
            for call in (core_firebase.check_runtime_configuration, core_firebase.initialize_firebase):
                with self.subTest(label, call=call.__name__):
                    self.assert_config_error(call, env)
        self.check(VALID_EMULATOR_ENV)

    def test_a_credential_mismatch_is_refused(self):
        self.initialize(VALID_EMULATOR_ENV)
        self.fake.get_app().credential = self.service_account
        self.assert_config_error(core_firebase.check_runtime_configuration, VALID_EMULATOR_ENV)

        self.reset_firebase()
        self.initialize({})
        self.fake.get_app().credential = core_firebase.EmulatorCredential()
        self.assert_config_error(core_firebase.check_runtime_configuration, {})

    def test_a_removed_or_replaced_app_is_refused(self):
        for env in ({}, VALID_EMULATOR_ENV):
            with self.subTest(mode=mode_label(env)):
                self.reset_firebase()
                self.initialize(env)
                recorded = self.fake.get_app()
                self.fake.apps.clear()
                self.assert_config_error(core_firebase.check_runtime_configuration, env)
                # An identical-looking app created elsewhere is still refused.
                self.fake.initialize_app(recorded.credential, recorded.options)
                self.assert_config_error(core_firebase.check_runtime_configuration, env)
                self.assert_config_error(core_firebase.initialize_firebase, env)


class AuthenticationEndpointTests(FirebaseTestBase):
    """The real get_current_user and require_admin, with a fake app registry and token verifier."""

    def setUp(self):
        super().setUp()
        self.verify = self.patch("core.auth.firebase_auth.verify_id_token", side_effect=fake_claims)
        app = FastAPI()
        app.include_router(auth_check_routes.router, prefix="/api")
        app.include_router(admin_users_routes.router, prefix="/api/admin/users")
        self.client = TestClient(app)

    def get(self, path, token, env):
        with firebase_env(env):
            return self.client.get(path, headers=bearer(token))

    def assert_unavailable(self, response):
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "AUTH_SERVICE_UNAVAILABLE")

    def test_the_recorded_configuration_authenticates_and_admin_claims_are_still_enforced(self):
        for env in ({}, VALID_EMULATOR_ENV):
            with self.subTest(mode=mode_label(env)):
                self.reset_firebase()
                self.verify.reset_mock()
                self.initialize(env)
                response = self.get("/api/auth/me", "student-token", env)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), {"uid": "student-uid", "is_admin": False})
                with self.assertLogs("auth", level="WARNING"):  # "Admin access denied" for the two 403s
                    for token, status_code in (("student-token", 403), ("string-admin-token", 403),
                                               ("admin-token", 200)):
                        self.assertEqual(self.get("/api/admin/verify", token, env).status_code, status_code)
                self.verify.assert_called_with("admin-token", check_revoked=True,
                                               clock_skew_seconds=core_auth.CLOCK_SKEW_SECONDS)

    def test_a_configuration_mismatch_returns_503_on_every_protected_endpoint_without_verifying(self):
        scenarios = [
            ("production, Auth emulator host injected", {}, {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099"}),
            ("production, Firestore emulator host injected", {}, {"FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080"}),
            ("production, switched to emulator mode", {}, VALID_EMULATOR_ENV),
            ("emulator, Auth host changed", VALID_EMULATOR_ENV,
             emulator_env(FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9100")),
            ("emulator, Firestore host changed", VALID_EMULATOR_ENV,
             emulator_env(FIRESTORE_EMULATOR_HOST="127.0.0.1:8081")),
            ("emulator, project changed", VALID_EMULATOR_ENV,
             emulator_env(ROUTE2UNIKL_EMULATOR_PROJECT_ID="demo-other")),
            ("emulator, settings removed", VALID_EMULATOR_ENV, {}),
            ("emulator, unknown mode", VALID_EMULATOR_ENV, emulator_env(ROUTE2UNIKL_FIREBASE_MODE=SENTINEL)),
        ]
        for label, initial, changed in scenarios:
            self.reset_firebase()
            self.initialize(initial)
            for path, token in PROTECTED_ENDPOINTS:
                with self.subTest(label, path=path), self.assertLogs("auth", level="ERROR") as logs:
                    self.assert_unavailable(self.get(path, token, changed))
                self.assertTrue(all("FirebaseConfigError" in line and SENTINEL not in line for line in logs.output))
            self.assert_config_error(core_firebase.check_runtime_configuration, changed)
            self.check(initial)  # nothing was recorded or replaced by the refused requests
        self.verify.assert_not_called()

    def test_an_invalid_configuration_before_initialization_returns_503_without_loading_credentials(self):
        cases = {
            "production mode with the Auth emulator host set": {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099"},
            "emulator mode with the production project": emulator_env(ROUTE2UNIKL_EMULATOR_PROJECT_ID="route2unikl"),
            "emulator mode with a non-loopback host": emulator_env(FIREBASE_AUTH_EMULATOR_HOST="0.0.0.0:9099"),
            "emulator mode without the Firestore emulator": emulator_env(FIRESTORE_EMULATOR_HOST=None),
            "unknown mode": {**VALID_EMULATOR_ENV, "ROUTE2UNIKL_FIREBASE_MODE": SENTINEL},
        }
        for label, env in cases.items():
            for path, token in PROTECTED_ENDPOINTS:
                with self.subTest(label, path=path), self.assertLogs("auth", level="ERROR") as logs:
                    self.assert_unavailable(self.get(path, token, env))
                self.assertTrue(all("FirebaseConfigError" in line and SENTINEL not in line for line in logs.output))
        self.verify.assert_not_called()
        self.certificate.assert_not_called()
        self.initialize_app.assert_not_called()

    def test_a_configuration_change_during_verification_rejects_the_verified_identity(self):
        changes = [
            ("production, Auth emulator host injected", {}, {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099"}),
            ("emulator, Auth host changed", VALID_EMULATOR_ENV, {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9100"}),
            ("emulator, switched to production", VALID_EMULATOR_ENV, {"ROUTE2UNIKL_FIREBASE_MODE": "production"}),
        ]
        for label, env, change in changes:
            self.reset_firebase()
            self.initialize(env)

            def verify_then_change(token, change=change, **kwargs):
                claims = fake_claims(token, **kwargs)
                os.environ.update(change)  # the environment changes while the SDK verifies
                return claims

            self.verify.side_effect = verify_then_change
            for path, token in (("/api/auth/me", "student-token"), ("/api/admin/verify", "admin-token")):
                self.verify.reset_mock()
                with self.subTest(label, path=path), self.assertLogs("auth", level="ERROR") as logs:
                    self.assert_unavailable(self.get(path, token, env))
                self.verify.assert_called_once()
                self.assertTrue(any("changed during token verification" in line for line in logs.output))
        self.verify.side_effect = fake_claims


class FakeServiceAccount(credentials.Base):
    """Stands in for the service-account key: a made-up project and anonymous credentials."""
    project_id = PRODUCTION_TEST_PROJECT

    def get_credential(self):
        return AnonymousCredentials()


def make_jwt(header, payload, signature=""):
    def encode(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    return f"{encode(header)}.{encode(payload)}.{signature}"


class ProductionVerifierTests(unittest.TestCase):
    """The real Admin SDK verifier, reached through production-mode initialization, rejects
    forged and invalid tokens. A real app is created with FakeServiceAccount (no key file);
    any HTTP request fails the test, so nothing reaches Google."""

    def setUp(self):
        if firebase_admin._apps:
            self.fail("a Firebase app already exists in this process")
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.multiple(core_firebase, _initialized_config=None, _initialized_app=None))
        stack.enter_context(firebase_env({}))
        stack.enter_context(mock.patch("core.firebase.credentials.Certificate", return_value=FakeServiceAccount()))
        stack.enter_context(mock.patch("core.firebase.firestore.client", return_value=mock.sentinel.db))
        stack.enter_context(mock.patch.object(requests.Session, "send",
                                              side_effect=AssertionError("network request attempted")))
        core_firebase.initialize_firebase()
        stack.callback(firebase_admin.delete_app, firebase_admin.get_app())
        app = FastAPI()
        app.include_router(auth_check_routes.router, prefix="/api")
        self.client = TestClient(app)

    def test_forged_and_invalid_tokens_are_rejected_without_any_network_request(self):
        self.assertEqual(core_firebase.initialized_config(), PRODUCTION_CONFIG)
        now = int(time.time())
        claims = {"iss": f"https://securetoken.google.com/{PRODUCTION_TEST_PROJECT}", "aud": PRODUCTION_TEST_PROJECT,
                  "sub": "admin-uid", "iat": now, "exp": now + 3600, "auth_time": now, "admin": True}
        other_project = {**claims, "aud": "another-project", "iss": "https://securetoken.google.com/another-project"}
        tokens = {
            "unsigned (alg none), as the Auth emulator issues": make_jwt({"alg": "none", "typ": "JWT"}, claims),
            "wrong algorithm (HS256)": make_jwt({"alg": "HS256", "kid": "k1", "typ": "JWT"}, claims, "c2ln"),
            "RS256 for another project": make_jwt({"alg": "RS256", "kid": "k1", "typ": "JWT"}, other_project, "c2ln"),
            "not a JWT": "not-a-jwt",
        }
        for label, token in tokens.items():
            for path in ("/api/auth/me", "/api/admin/verify"):
                with self.subTest(label, path=path):
                    response = self.client.get(path, headers=bearer(token))
                    self.assertEqual(response.status_code, 401, response.text)
                    self.assertEqual(response.json()["detail"], "Invalid authentication token.")


if __name__ == "__main__":
    unittest.main()
