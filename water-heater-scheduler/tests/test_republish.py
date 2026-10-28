import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main


class ShouldPublishTest(unittest.TestCase):
    """REST states vanish on a Home Assistant restart, so unchanged entities must still be reposted hourly."""

    NOW = datetime(2026, 10, 28, 12, 0)

    # A first post always goes out.
    def test_first_post(self):
        self.assertTrue(main.should_publish({'signature': None, 'at': None}, ('x',), self.NOW))

    # Unchanged within the hour: skip.
    def test_unchanged_recent_is_skipped(self):
        previous = {'signature': ('x',), 'at': self.NOW - timedelta(minutes=59)}
        self.assertFalse(main.should_publish(previous, ('x',), self.NOW))

    # Unchanged but an hour old: repost, so the sensor returns after a restart.
    def test_unchanged_after_an_hour_is_reposted(self):
        previous = {'signature': ('x',), 'at': self.NOW - timedelta(hours=1)}
        self.assertTrue(main.should_publish(previous, ('x',), self.NOW))

    # Changed content: post at once.
    def test_changed_is_posted(self):
        previous = {'signature': ('x',), 'at': self.NOW}
        self.assertTrue(main.should_publish(previous, ('y',), self.NOW))


if __name__ == '__main__':
    unittest.main()
