# backend/tests/isolation.py
"""
Fail-closed isolation for every backend test process (M3C test-safety follow-up).

Why this exists: during the M3C mutation check (26 Nov 2026), a deliberately weakened copy of
core/student_access.py removed its emulator-only condition. Existing unit tests that patch only the Firebase
references their own code path normally uses then reached the REAL core.firebase.initialize_firebase() in
production mode: backend/serviceAccountKey.json was loaded and a Firebase app for the production project was
created in the test process (docs/PROJECT_STATUS.md, section 8 M). Per-test patches are not a safety boundary:
a code change (or a mutation) can take a path that no test patched.

install() is called when the test packages are imported (tests/__init__.py, and integration_tests/__init__.py
in "emulator" mode), so it is in force before any test module is imported, for `unittest discover`, for a
single module, and for any harness that loads the suite through the package. It replaces, for the whole
process:

  1. firebase_admin.credentials.Certificate      -> raises: no service-account key can be loaded; so do the
                                                    direct loaders google.oauth2.service_account.Credentials.
                                                    from_service_account_file / _info and google.auth.
                                                    load_credentials_from_file / _dict (audit A2)
  2. firebase_admin.credentials.ApplicationDefault and google.auth.default
                                                 -> raise: no Application Default Credentials
  3. firebase_admin.initialize_app               -> refuses the production project (route2unikl), an app
                                                    without an explicit credential, and, in "emulator" mode,
                                                    any project that is not a demo- project
  4. socket connect/connect_ex and getaddrinfo   -> loopback only: no DNS lookup or connection leaves the
                                                    machine (Python sockets: requests, urllib3, google-auth
                                                    token fetches)

It also refuses to start if GOOGLE_APPLICATION_CREDENTIALS is set, and, in "emulator" mode, unless both
emulator hosts are loopback addresses and the project is a demo- project.

Tests that need a fake credential or app keep patching core.firebase (mock.patch restores THESE guards
afterwards, never the real functions). Limits, stated honestly: gRPC (used by the Firestore client) opens its
own sockets in C and is not covered by layer 4; layers 1-3 still prevent any production credential or app, so
an authenticated production gRPC call cannot be made. Every blocked attempt is recorded in BLOCKED (a kind and
a short label; never a path, token or credential).
"""
import ipaddress
import os
import socket
from typing import List, Tuple

import firebase_admin
import google.auth
from firebase_admin import credentials as fb_credentials
from google.oauth2 import service_account as google_service_account

PRODUCTION_PROJECT_ID = "route2unikl"
UNIT = "unit"
EMULATOR = "emulator"

BLOCKED: List[Tuple[str, str]] = []
_state = {"mode": None}
_real = {}


class IsolationError(RuntimeError):
    """A test tried to reach a production credential, app or network. Never caught as a success."""


def _block(kind: str, label: str):
    BLOCKED.append((kind, label))
    raise IsolationError(f"test isolation: {kind} blocked ({label})")


class BlockedCertificate(fb_credentials.Certificate):
    """Stands in for credentials.Certificate: no service-account key file is ever read in a test process."""

    def __new__(cls, *args, **kwargs):
        _block("service-account credential", "credentials.Certificate")


class BlockedApplicationDefault(fb_credentials.ApplicationDefault):
    def __new__(cls, *args, **kwargs):
        _block("application default credentials", "credentials.ApplicationDefault")


def _blocked_google_auth_default(*args, **kwargs):
    _block("application default credentials", "google.auth.default")


# Direct key loaders that do not go through firebase_admin.credentials.Certificate (M3C audit A2).
def _blocked_service_account_loader(cls, *args, **kwargs):
    _block("service-account credential", "google.oauth2.service_account loader")


def _blocked_credentials_loader(*args, **kwargs):
    _block("service-account credential", "google.auth credentials loader")


def _guarded_initialize_app(credential=None, options=None, name="[DEFAULT]"):
    if credential is None:
        _block("Firebase app", "no explicit credential")
    project = (options or {}).get("projectId") or getattr(credential, "project_id", None)
    if project == PRODUCTION_PROJECT_ID:
        _block("Firebase app", "production project")
    if _state["mode"] == EMULATOR and not (isinstance(project, str) and project.startswith("demo-")):
        _block("Firebase app", "non-demo project in an emulator test")
    return _real["initialize_app"](credential, options, name)


def is_loopback_host(host) -> bool:
    if host is None:
        return True  # getaddrinfo(None, port): the local host
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _address_host(address):
    return address[0] if isinstance(address, tuple) and address else address


def _guarded_connect(sock, address, *args, **kwargs):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback_host(_address_host(address)):
        _block("network", "non-loopback connection")
    return _real["connect"](sock, address, *args, **kwargs)


def _guarded_connect_ex(sock, address, *args, **kwargs):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback_host(_address_host(address)):
        _block("network", "non-loopback connection")
    return _real["connect_ex"](sock, address, *args, **kwargs)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not is_loopback_host(host):
        _block("network", "non-loopback name lookup")
    return _real["getaddrinfo"](host, *args, **kwargs)


def _check_environment(mode: str) -> None:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise IsolationError("test isolation: GOOGLE_APPLICATION_CREDENTIALS must not be set for tests")
    if mode == EMULATOR:
        from core import firebase as core_firebase  # local import: the unit guard does not need it
        hosts = (os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"), os.environ.get("FIRESTORE_EMULATOR_HOST"))
        if not all(core_firebase.is_loopback_host_port(host) for host in hosts):
            raise IsolationError("test isolation: emulator tests need loopback emulator hosts")
        if not core_firebase.is_demo_project_id(os.environ.get("GCLOUD_PROJECT")):
            raise IsolationError("test isolation: emulator tests need a demo- project")


def install(mode: str = UNIT) -> None:
    """Install the guards once per process (idempotent). "emulator" mode may tighten an installed "unit" mode."""
    if mode not in (UNIT, EMULATOR):
        raise ValueError("mode must be 'unit' or 'emulator'")
    _check_environment(mode)
    if _state["mode"] is None:
        _real.update(initialize_app=firebase_admin.initialize_app, connect=socket.socket.connect,
                     connect_ex=socket.socket.connect_ex, getaddrinfo=socket.getaddrinfo)
        fb_credentials.Certificate = BlockedCertificate
        fb_credentials.ApplicationDefault = BlockedApplicationDefault
        google.auth.default = _blocked_google_auth_default
        google.auth.load_credentials_from_file = _blocked_credentials_loader
        google.auth.load_credentials_from_dict = _blocked_credentials_loader
        google_service_account.Credentials.from_service_account_file = classmethod(_blocked_service_account_loader)
        google_service_account.Credentials.from_service_account_info = classmethod(_blocked_service_account_loader)
        firebase_admin.initialize_app = _guarded_initialize_app
        socket.socket.connect = _guarded_connect
        socket.socket.connect_ex = _guarded_connect_ex
        socket.getaddrinfo = _guarded_getaddrinfo
    if _state["mode"] != EMULATOR:
        _state["mode"] = mode


def installed_mode():
    return _state["mode"]


def require_guards(mode: str = UNIT) -> None:
    """Fail closed unless the guards are in place in at least `mode` (M3C audit A2).

    Called at the top of test modules, right after their sys.path set-up and before any Firebase, Google or
    application import, so that executing a test file directly (python tests/test_x.py) cannot run without the
    guards. Importing the `tests` / `integration_tests` package installs them; this only verifies.
    """
    if mode not in (UNIT, EMULATOR):
        raise ValueError("mode must be 'unit' or 'emulator'")
    if not guards_in_place():
        raise IsolationError("test isolation: the guards are not in place; refusing to run")
    if mode == EMULATOR and _state["mode"] != EMULATOR:
        raise IsolationError("test isolation: emulator tests need the emulator-mode guards; refusing to run")


def guards_in_place() -> bool:
    """True only if every guard is still the installed one (checked before a test exercises it)."""
    return (_state["mode"] is not None
            and fb_credentials.Certificate is BlockedCertificate
            and fb_credentials.ApplicationDefault is BlockedApplicationDefault
            and google.auth.default is _blocked_google_auth_default
            and google.auth.load_credentials_from_file is _blocked_credentials_loader
            and google.auth.load_credentials_from_dict is _blocked_credentials_loader
            and google_service_account.Credentials.from_service_account_file.__func__ is _blocked_service_account_loader
            and google_service_account.Credentials.from_service_account_info.__func__ is _blocked_service_account_loader
            and firebase_admin.initialize_app is _guarded_initialize_app
            and socket.socket.connect is _guarded_connect
            and socket.socket.connect_ex is _guarded_connect_ex
            and socket.getaddrinfo is _guarded_getaddrinfo)
