# Backend test package. Run from backend/:  python -m unittest discover -s tests -t . -v
#
# Test isolation (M3C follow-up): importing this package installs fail-closed guards for the whole test
# process before any test module is imported: no service-account key, no Application Default Credentials,
# no Firebase app for the production project, and no network beyond loopback. See tests/isolation.py.
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from tests import isolation  # noqa: E402

isolation.install(isolation.UNIT)
