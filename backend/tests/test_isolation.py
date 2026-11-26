# backend/tests/test_isolation.py
"""
M3C test-safety follow-up: the fail-closed guards of tests/isolation.py.

Run from the backend directory with the other backend tests:
    python -m unittest discover -s tests -t . -v

Every test first asserts that the guards are in place (precondition) and only then exercises a path that
would need a credential or the network without them; nothing here can contact Google. The incident test
reproduces the path of the 26 Nov 2026 mutation-check incident (section 8 M of docs/PROJECT_STATUS.md)
WITHOUT any mutation: production-mode initialisation reached from the student-data check, with no test patch
on initialize_firebase.
"""
import ast
import concurrent.futures
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests import isolation  # noqa: E402  (installs the guards first, also when this file is run directly)

isolation.require_guards(isolation.UNIT)

import firebase_admin  # noqa: E402
import google.auth  # noqa: E402
import requests  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from firebase_admin import credentials as fb_credentials  # noqa: E402
from google.auth.credentials import AnonymousCredentials  # noqa: E402

from core import firebase as core_firebase  # noqa: E402
from core import student_access  # noqa: E402
from services import account_access_service as access  # noqa: E402
from tests.test_firebase_config import firebase_env  # noqa: E402

KEY_PATH = str(BACKEND_DIR / "serviceAccountKey.json")


class FakeCredential(fb_credentials.Base):
    def __init__(self, project_id):
        self.project_id = project_id

    def get_credential(self):
        return AnonymousCredentials()


class IsolationTestBase(unittest.TestCase):
    def setUp(self):
        # Precondition for every test: if any guard were missing, stop BEFORE exercising the path.
        if not isolation.guards_in_place():
            self.fail("test isolation guards are not in place; refusing to exercise production paths")
        if firebase_admin._apps:
            self.fail("a Firebase app already exists in this process")
        self.blocked_before = len(isolation.BLOCKED)

    def tearDown(self):
        self.assertEqual(firebase_admin._apps, {}, "no Firebase app may be left behind")
        self.assertTrue(isolation.guards_in_place(), "the guards are still in place afterwards")

    def assert_blocked(self, kind, call, *args, **kwargs):
        with self.assertRaises(isolation.IsolationError):
            call(*args, **kwargs)
        self.assertEqual(isolation.BLOCKED[-1][0], kind)


class GuardTests(IsolationTestBase):
    def test_the_guards_are_installed_for_the_whole_test_process(self):
        self.assertEqual(isolation.installed_mode(), isolation.UNIT)
        self.assertIs(core_firebase.credentials.Certificate, isolation.BlockedCertificate,
                      "core.firebase reaches the guarded class")

    def test_no_service_account_key_can_be_loaded(self):
        opened = []
        real_open = open

        def spy_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=spy_open):
            self.assert_blocked("service-account credential", fb_credentials.Certificate, KEY_PATH)
            self.assert_blocked("service-account credential", core_firebase.credentials.Certificate, KEY_PATH)
        self.assertNotIn(KEY_PATH, opened, "the key file is never opened")

    def test_direct_key_loaders_are_refused_before_the_key_is_read(self):
        from google.oauth2 import service_account as google_service_account
        opened = []
        real_open = open

        def spy_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        with mock.patch("builtins.open", side_effect=spy_open):
            self.assert_blocked("service-account credential",
                                google_service_account.Credentials.from_service_account_file, KEY_PATH)
            self.assert_blocked("service-account credential",
                                google_service_account.Credentials.from_service_account_info, {"type": "service_account"})
            self.assert_blocked("service-account credential", google.auth.load_credentials_from_file, KEY_PATH)
            self.assert_blocked("service-account credential", google.auth.load_credentials_from_dict, {})
        self.assertNotIn(KEY_PATH, opened, "the key file is never opened")

    def test_no_application_default_credentials(self):
        self.assert_blocked("application default credentials", fb_credentials.ApplicationDefault)
        self.assert_blocked("application default credentials", google.auth.default)
        self.assert_blocked("Firebase app", firebase_admin.initialize_app)  # no explicit credential

    def test_no_firebase_app_for_the_production_project(self):
        self.assert_blocked("Firebase app", firebase_admin.initialize_app, FakeCredential("route2unikl"))
        self.assert_blocked("Firebase app", firebase_admin.initialize_app, FakeCredential("route2unikl-unit-test"),
                            {"projectId": "route2unikl"})
        # Control: a made-up project with a fake credential is still allowed (used by test_firebase_config).
        app = firebase_admin.initialize_app(FakeCredential("route2unikl-unit-test"), name="isolation-control")
        firebase_admin.delete_app(app)

    def test_emulator_mode_allows_demo_projects_only(self):
        with mock.patch.dict(isolation._state, {"mode": isolation.EMULATOR}):
            self.assert_blocked("Firebase app", firebase_admin.initialize_app, FakeCredential("route2unikl-unit-test"),
                                name="isolation-emulator")
            app = firebase_admin.initialize_app(FakeCredential("demo-route2unikl"), name="isolation-demo")
            firebase_admin.delete_app(app)

    def test_the_environment_checks_refuse_to_start(self):
        with mock.patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "any-path"}):
            with self.assertRaises(isolation.IsolationError):
                isolation._check_environment(isolation.UNIT)
        bad = [{"FIREBASE_AUTH_EMULATOR_HOST": "10.0.0.5:9099", "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080",
                "GCLOUD_PROJECT": "demo-route2unikl"},
               {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099", "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080",
                "GCLOUD_PROJECT": "route2unikl"},
               {}]
        for env in bad:
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(isolation.IsolationError):
                    isolation._check_environment(isolation.EMULATOR)
        good = {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9199", "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8180",
                "GCLOUD_PROJECT": "demo-route2unikl"}
        with mock.patch.dict(os.environ, good, clear=True):
            isolation._check_environment(isolation.EMULATOR)

    def test_network_beyond_loopback_is_refused_before_any_lookup_or_connection(self):
        self.assert_blocked("network", socket.getaddrinfo, "firestore.googleapis.com", 443)
        self.assert_blocked("network", socket.create_connection, ("firestore.googleapis.com", 443), 1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            self.assert_blocked("network", sock.connect, ("192.0.2.1", 443))  # TEST-NET-1 (documentation range)
            self.assert_blocked("network", sock.connect_ex, ("192.0.2.1", 443))
        self.assert_blocked("network", requests.get, "https://firestore.googleapis.com/", timeout=1)

    def test_loopback_still_works(self):
        left, right = socket.socketpair()
        with left, right:
            left.sendall(b"ok")
            self.assertEqual(right.recv(2), b"ok")
        self.assertTrue(socket.getaddrinfo("127.0.0.1", 0))
        for host in ("127.0.0.1", "::1", "localhost", None, b"127.0.0.1", "127.5.6.7"):
            self.assertTrue(isolation.is_loopback_host(host), host)
        for host in ("firestore.googleapis.com", "10.0.0.5", "0.0.0.0", "", 5):
            self.assertFalse(isolation.is_loopback_host(host), host)

    def test_test_patches_restore_the_guards_not_the_real_functions(self):
        with mock.patch("core.firebase.credentials.Certificate", return_value=FakeCredential("route2unikl-unit-test")):
            self.assertIsNot(core_firebase.credentials.Certificate, isolation.BlockedCertificate)
        with mock.patch("core.firebase.firebase_admin.initialize_app"):
            pass
        self.assertTrue(isolation.guards_in_place())


class IncidentPathTests(IsolationTestBase):
    """The 26 Nov 2026 incident path, reproduced WITHOUT a mutation: production mode, and no test patch on
    initialize_firebase anywhere on the path from the student-data check to core.firebase."""

    def production_mode(self):
        stack = mock.patch.multiple(core_firebase, _initialized_config=None, _initialized_app=None)
        stack.start()
        self.addCleanup(stack.stop)
        env = firebase_env({})  # production mode: no ROUTE2UNIKL_FIREBASE_MODE, no emulator hosts
        env.__enter__()
        self.addCleanup(env.__exit__, None, None, None)

    def test_production_initialisation_is_refused_before_the_key_is_read(self):
        self.production_mode()
        self.assert_blocked("service-account credential", core_firebase.initialize_firebase)
        self.assertIsNone(core_firebase.initialized_config(), "nothing recorded as initialised")

    def test_the_student_data_check_fails_closed_instead_of_reaching_production(self):
        self.production_mode()
        with self.assertRaises(access.AccountAccessError) as ctx:
            access.read_access_record("student-uid-123")
        self.assertEqual(ctx.exception.code, access.FIREBASE_UNAVAILABLE)
        with self.assertRaises(HTTPException) as refused:
            student_access.read_record_or_refuse("student-uid-123")
        self.assertEqual((refused.exception.status_code, refused.exception.detail["code"]),
                         (503, "ACCOUNT_STATUS_UNAVAILABLE"))
        self.assertEqual(isolation.BLOCKED[-1], ("service-account credential", "credentials.Certificate"))
        self.assertGreaterEqual(len(isolation.BLOCKED) - self.blocked_before, 2)


TEST_MODULES = sorted(list((BACKEND_DIR / "tests").glob("test_*.py"))
                      + list((BACKEND_DIR / "integration_tests").glob("test_*.py")))
AUDITED_MODULES = {"tests/test_auth.py", "tests/test_firebase_config.py", "tests/test_account_access_service.py",
                   "integration_tests/test_auth_emulator.py"}
GUARD_PACKAGES = ("tests", "integration_tests")
GUARDED_ROOTS = ("core", "routes", "services", "main", "firebase_admin", "google")
FIREBASE_ENV = ("ROUTE2UNIKL_FIREBASE_MODE", "ROUTE2UNIKL_EMULATOR_PROJECT_ID", "FIREBASE_AUTH_EMULATOR_HOST",
                "FIRESTORE_EMULATOR_HOST", "GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS")
# Emulator settings for importing integration modules only: nothing connects at import time (port 9 is unused).
FAKE_EMULATOR_ENV = {"FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9", "FIRESTORE_EMULATOR_HOST": "127.0.0.1:9",
                     "GCLOUD_PROJECT": "demo-route2unikl"}

# Runs ONE test file as a direct execution would (its own folder first on sys.path, a fresh process), without
# running its tests. It verifies the guards BEFORE anything else and stops at once if they are missing, so a
# regression is reported as UNGUARDED without any Firebase initialisation being attempted.
DIRECT_EXECUTION_PROBE = r'''
import os, runpy, sys
path = sys.argv[1]
sys.path[0] = os.path.dirname(path)
try:
    runpy.run_path(path, run_name="direct_execution_probe")
except BaseException as exc:
    print("IMPORT_REFUSED", type(exc).__name__)
    sys.exit(10)
iso = sys.modules.get("tests.isolation")
if iso is None or not iso.guards_in_place():
    print("UNGUARDED")
    sys.exit(20)
import firebase_admin
from firebase_admin import credentials
if iso.BLOCKED or firebase_admin._apps:
    print("TOUCHED_AT_IMPORT")
    sys.exit(30)
class Fake(credentials.Base):
    project_id = "route2unikl"
    def get_credential(self):
        from google.auth.credentials import AnonymousCredentials
        return AnonymousCredentials()
import google.auth
from google.oauth2 import service_account
refused = 0
for attempt in (lambda: credentials.Certificate("serviceAccountKey.json"),
                lambda: service_account.Credentials.from_service_account_file("serviceAccountKey.json"),
                lambda: google.auth.load_credentials_from_file("serviceAccountKey.json"),
                lambda: firebase_admin.initialize_app(Fake())):
    try:
        attempt()
    except iso.IsolationError:
        refused += 1
for name in ("ROUTE2UNIKL_FIREBASE_MODE", "ROUTE2UNIKL_EMULATOR_PROJECT_ID", "FIREBASE_AUTH_EMULATOR_HOST",
             "FIRESTORE_EMULATOR_HOST", "GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT"):
    os.environ.pop(name, None)
from core import firebase as core_firebase
try:
    core_firebase.initialize_firebase()  # production mode: must be refused before the key is read
except iso.IsolationError:
    refused += 1
except Exception as exc:
    print("UNEXPECTED", type(exc).__name__)
    sys.exit(40)
if refused != 5 or firebase_admin._apps or core_firebase.initialized_config() is not None:
    print("NOT_REFUSED", refused)
    sys.exit(50)
print("PROTECTED", iso.installed_mode(), sorted({kind for kind, _ in iso.BLOCKED}))
'''


def relative(path):
    return path.relative_to(BACKEND_DIR).as_posix()


def run_probe(path, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k not in FIREBASE_ENV}
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", DIRECT_EXECUTION_PROBE, str(path)], cwd=str(path.parent), env=env,
                          capture_output=True, text=True, timeout=180)


class DirectExecutionTests(unittest.TestCase):
    """M3C audit A2: executing a test file directly (python tests/test_x.py) cannot bypass the guards."""

    @staticmethod
    def module_level_imports(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                names.extend((node.lineno, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.append((node.lineno, node.module))
        return names

    def test_every_test_module_installs_the_guards_at_import(self):
        self.assertEqual(len(TEST_MODULES), 16)  # 9 unit and 7 emulator integration modules
        for path in TEST_MODULES:
            with self.subTest(module=relative(path)):
                imports = self.module_level_imports(path)
                roots = [(line, name.split(".")[0]) for line, name in imports]
                guard_lines = [line for line, root in roots if root in GUARD_PACKAGES]
                self.assertTrue(guard_lines, "imports the tests / integration_tests package at module level")
                self.assertNotIn("main", [root for _, root in roots], "never imports main (it initialises Firebase)")
                if relative(path) in AUDITED_MODULES:
                    first_guarded = min((line for line, root in roots if root in GUARDED_ROOTS), default=None)
                    self.assertLess(min(guard_lines), first_guarded,
                                    "the guards come before any Firebase, Google or application import")
                    self.assertIn("isolation.require_guards(", path.read_text(encoding="utf-8"))

    def test_no_test_module_captures_the_real_credential_functions_by_name(self):
        for path in TEST_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in ("firebase_admin.credentials", "google.auth"):
                    with self.subTest(module=relative(path), line=node.lineno):
                        self.assertFalse({a.name for a in node.names} & {"Certificate", "ApplicationDefault", "default"})

    def test_executing_each_unit_test_file_directly_is_protected(self):
        unit_modules = [p for p in TEST_MODULES if p.parent.name == "tests"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = dict(zip(unit_modules, pool.map(run_probe, unit_modules)))
        for path, result in results.items():
            with self.subTest(module=relative(path)):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-2000:])
                self.assertIn("PROTECTED unit", result.stdout)

    def test_executing_each_integration_test_file_directly_is_protected(self):
        modules = [p for p in TEST_MODULES if p.parent.name == "integration_tests"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = dict(zip(modules, pool.map(lambda p: run_probe(p, FAKE_EMULATOR_ENV), modules)))
        for path, result in results.items():
            with self.subTest(module=relative(path)):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-2000:])
                self.assertIn("PROTECTED emulator", result.stdout)

    def test_integration_files_refuse_to_load_outside_the_emulator_environment(self):
        path = BACKEND_DIR / "integration_tests" / "test_auth_emulator.py"
        for label, env in (("no emulator settings", {}),
                           ("production project", {**FAKE_EMULATOR_ENV, "GCLOUD_PROJECT": "route2unikl"}),
                           ("non-loopback host", {**FAKE_EMULATOR_ENV, "FIRESTORE_EMULATOR_HOST": "10.0.0.5:8080"})):
            with self.subTest(label):
                result = run_probe(path, env)
                self.assertEqual(result.returncode, 10, result.stdout)
                self.assertIn("IMPORT_REFUSED IsolationError", result.stdout)

    def test_a_credentials_variable_refuses_every_direct_execution(self):
        result = run_probe(BACKEND_DIR / "tests" / "test_auth.py", {"GOOGLE_APPLICATION_CREDENTIALS": "any-path"})
        self.assertEqual((result.returncode, result.stdout.strip()), (10, "IMPORT_REFUSED IsolationError"))

    def test_require_guards_fails_closed(self):
        with mock.patch.dict(isolation._state, {"mode": None}):
            with self.assertRaises(isolation.IsolationError):
                isolation.require_guards(isolation.UNIT)
        with self.assertRaises(isolation.IsolationError):
            isolation.require_guards(isolation.EMULATOR)  # this process has the unit-mode guards only
        with self.assertRaises(ValueError):
            isolation.require_guards("production")
        isolation.require_guards(isolation.UNIT)


if __name__ == "__main__":
    unittest.main()
