# backend/core/firebase.py
"""
Firebase Admin SDK initialization in one of two explicit modes, selected by
ROUTE2UNIKL_FIREBASE_MODE:

- production (the default, variable unset): loads backend/serviceAccountKey.json
  and connects to the real Firebase project. It refuses to start while any
  emulator setting is present: the Admin SDK reads FIREBASE_AUTH_EMULATOR_HOST
  and FIRESTORE_EMULATOR_HOST by itself, and with FIREBASE_AUTH_EMULATOR_HOST
  set it no longer checks ID-token signatures.

- emulator (local development and tests only): never loads a service-account
  key or application-default credentials. Requires a demo- project ID
  (ROUTE2UNIKL_EMULATOR_PROJECT_ID) and loopback hosts for both the
  Authentication and Firestore emulators.

The first successful initialization records an immutable FirebaseConfig (mode,
project, emulator hosts, credential type) and the app it created. Later calls
to initialize_firebase() and check_runtime_configuration() accept only that
app, under an environment that still matches the record; the record is never
overwritten. A failed initialization records nothing and removes any app it
created.

Missing, malformed, conflicting or changed settings raise FirebaseConfigError.
There is no fallback from one mode to the other. Error messages name variables
only, never their values.
"""
import os
import re
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.auth.credentials import AnonymousCredentials

MODE_ENV = "ROUTE2UNIKL_FIREBASE_MODE"
EMULATOR_PROJECT_ENV = "ROUTE2UNIKL_EMULATOR_PROJECT_ID"
AUTH_EMULATOR_ENV = "FIREBASE_AUTH_EMULATOR_HOST"
FIRESTORE_EMULATOR_ENV = "FIRESTORE_EMULATOR_HOST"
EMULATOR_HOST_ENVS = (AUTH_EMULATOR_ENV, FIRESTORE_EMULATOR_ENV)
GOOGLE_PROJECT_ENVS = ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT")
GOOGLE_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"

PRODUCTION_MODE = "production"
EMULATOR_MODE = "emulator"
SERVICE_ACCOUNT_CREDENTIAL = "service_account"
EMULATOR_CREDENTIAL = "emulator"

_DEMO_PROJECT_ID = re.compile(r"demo-[a-z0-9][a-z0-9-]{0,24}")
_LOOPBACK_HOST_PORT = re.compile(r"(?:127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})")


class FirebaseConfigError(RuntimeError):
    """The Firebase configuration is missing, malformed, conflicting or has changed."""


class EmulatorCredential(credentials.Base):
    """Anonymous credential for the local emulators. Never reads a key file."""

    def get_credential(self):
        return AnonymousCredentials()


@dataclass(frozen=True)
class FirebaseConfig:
    """The Firebase configuration of this process (immutable)."""
    mode: str
    project_id: Optional[str]
    auth_emulator_host: Optional[str]
    firestore_emulator_host: Optional[str]
    credential: str


# Recorded by the first successful initialize_firebase(); never overwritten.
_lock = threading.RLock()
_initialized_config: Optional[FirebaseConfig] = None
_initialized_app = None


def is_demo_project_id(value) -> bool:
    return isinstance(value, str) and _DEMO_PROJECT_ID.fullmatch(value) is not None


def is_loopback_host_port(value) -> bool:
    match = _LOOPBACK_HOST_PORT.fullmatch(value) if isinstance(value, str) else None
    return match is not None and 1 <= int(match.group(1)) <= 65535


def firebase_mode() -> str:
    """Return the configured mode. Unset means production; anything unknown is an error."""
    mode = os.environ.get(MODE_ENV)
    if mode is None:
        return PRODUCTION_MODE
    if mode in (PRODUCTION_MODE, EMULATOR_MODE):
        return mode
    raise FirebaseConfigError(f"{MODE_ENV} must be '{PRODUCTION_MODE}' or '{EMULATOR_MODE}'.")


def emulator_project_id() -> str:
    """Validate the complete emulator environment and return its demo- project ID."""
    project_id = os.environ.get(EMULATOR_PROJECT_ENV)
    if not is_demo_project_id(project_id):
        raise FirebaseConfigError(
            f"{EMULATOR_PROJECT_ENV} must be a demo- project ID, for example demo-route2unikl.")
    for name in EMULATOR_HOST_ENVS:
        if not is_loopback_host_port(os.environ.get(name)):
            raise FirebaseConfigError(
                f"{name} must be a loopback host and port, for example 127.0.0.1:9099.")
    if GOOGLE_CREDENTIALS_ENV in os.environ:
        raise FirebaseConfigError(f"{GOOGLE_CREDENTIALS_ENV} must not be set in emulator mode.")
    for name in GOOGLE_PROJECT_ENVS:
        if name in os.environ and os.environ[name] != project_id:
            raise FirebaseConfigError(f"{name} conflicts with {EMULATOR_PROJECT_ENV}.")
    return project_id


def _refuse_emulator_settings_in_production():
    present = [name for name in (*EMULATOR_HOST_ENVS, EMULATOR_PROJECT_ENV) if name in os.environ]
    if present:
        raise FirebaseConfigError(
            "Production Firebase mode refuses to start while emulator settings are present: "
            f"{', '.join(present)}. Unset them, or set {MODE_ENV}={EMULATOR_MODE} for the local emulators.")


def _environment_config() -> FirebaseConfig:
    """The configuration the current environment requires. Raises if the environment is invalid."""
    if firebase_mode() == EMULATOR_MODE:
        project_id = emulator_project_id()
        return FirebaseConfig(EMULATOR_MODE, project_id, os.environ[AUTH_EMULATOR_ENV],
                              os.environ[FIRESTORE_EMULATOR_ENV], EMULATOR_CREDENTIAL)
    _refuse_emulator_settings_in_production()
    # In production the project comes from the service-account key, not from the environment.
    return FirebaseConfig(PRODUCTION_MODE, None, None, None, SERVICE_ACCOUNT_CREDENTIAL)


def _app_config(app, required: FirebaseConfig) -> FirebaseConfig:
    """The configuration of a running app, which must have the credential and project `required` asks for."""
    credential = EMULATOR_CREDENTIAL if isinstance(app.credential, EmulatorCredential) else SERVICE_ACCOUNT_CREDENTIAL
    if credential != required.credential:
        raise FirebaseConfigError("The Firebase app's credential does not match the configured mode.")
    try:
        project_id = app.project_id
    except Exception:
        project_id = None
    if not isinstance(project_id, str) or not project_id:
        raise FirebaseConfigError("The Firebase app's project cannot be determined.")
    if required.project_id is not None and project_id != required.project_id:
        raise FirebaseConfigError("The Firebase app's project does not match the configuration.")
    return replace(required, project_id=project_id)


def _check_recorded_app(app, required: FirebaseConfig) -> None:
    """`app` must be the app this module created, under the recorded configuration."""
    if _initialized_config is None or app is not _initialized_app:
        raise FirebaseConfigError("The Firebase app was not initialized by this module.")
    if _app_config(app, required) != _initialized_config:
        raise FirebaseConfigError("The Firebase configuration changed after initialization.")


def _default_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        return None


def _create_app(required: FirebaseConfig):
    """Create the default app. The configuration is recorded only after everything has succeeded."""
    global _initialized_config, _initialized_app
    if _initialized_config is not None:
        # The production project is known only once the key is loaded; it is compared below.
        recorded = _initialized_config if required.project_id is not None \
            else replace(_initialized_config, project_id=None)
        if required != recorded:
            raise FirebaseConfigError(
                "The Firebase configuration differs from the one this process was initialized with.")

    if required.mode == EMULATOR_MODE:
        app = firebase_admin.initialize_app(EmulatorCredential(),
                                            {"projectId": required.project_id, "httpTimeout": 10})
    else:
        backend_dir = Path(__file__).resolve().parent.parent
        key_path = backend_dir / "serviceAccountKey.json"
        cred = credentials.Certificate(str(key_path))
        app = firebase_admin.initialize_app(cred)

    try:
        actual = _app_config(app, required)
        if _initialized_config is not None and actual != _initialized_config:
            raise FirebaseConfigError(
                "The Firebase configuration differs from the one this process was initialized with.")
        db = firestore.client()
    except Exception:
        # Leave no half-initialized app behind for a later call to trust.
        firebase_admin.delete_app(app)
        raise

    _initialized_app = app
    if _initialized_config is None:
        _initialized_config = actual
    return db


def initialize_firebase():
    """
    Initializes the Firebase app for the configured mode (see the module docstring),
    or validates the app this module already initialized.
    Returns the Firestore database client so we can save and read data.
    """
    with _lock:
        required = _environment_config()
        app = _default_app()
        if app is None:
            return _create_app(required)
        _check_recorded_app(app, required)
        return firestore.client()


def check_runtime_configuration() -> None:
    """Raise FirebaseConfigError unless the running Firebase app is the one this module
    initialized and the current environment still matches the recorded configuration.

    Call before trusting any Firebase result that depends on the environment, such as
    ID-token verification."""
    with _lock:
        if _initialized_config is None:
            raise FirebaseConfigError("Firebase has not been initialized by this module.")
        required = _environment_config()
        app = _default_app()
        if app is None:
            raise FirebaseConfigError("The Firebase app is not available.")
        _check_recorded_app(app, required)


def initialized_config() -> Optional[FirebaseConfig]:
    """The configuration recorded at the first successful initialization (read-only), or None."""
    return _initialized_config
