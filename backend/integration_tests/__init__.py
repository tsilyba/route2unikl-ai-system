# Firebase emulator integration tests (local only). Kept outside tests/ so the
# default backend suite never needs, starts or touches an emulator.
#
# Test isolation (M3C follow-up): importing this package refuses to continue unless both emulator hosts are
# loopback addresses and the project is a demo- project, and installs the fail-closed guards of
# tests/isolation.py in "emulator" mode: no service-account key, no Application Default Credentials, Firebase
# apps for demo- projects only, and no network beyond loopback.
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from tests import isolation  # noqa: E402

isolation.install(isolation.EMULATOR)
