import subprocess
import sys
from pathlib import Path

SYNC = Path(__file__).resolve().parents[3] / "scripts" / "sync_hems_core.py"


def test_vendored_engine_matches_the_core():
    """The engine copy inside custom_components/hems must be regenerated whenever hems/core changes."""
    done = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
