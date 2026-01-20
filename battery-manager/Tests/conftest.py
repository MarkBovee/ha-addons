import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


logger = logging.getLogger("battery-manager-tests")


def pytest_runtest_setup(item):
    logger.info("Running %s", item.nodeid)
