"""When the weekly legionella protection is due and on which day it runs (pure).

The old rule compared elapsed time: due when `(now - last_run).days >= 7`. The last run is stamped every hour while the water stays
above 60 °C, so a run that started at 13:00 was recorded as 18:30; the next Saturday's cheapest window (14:00) was then 6 days and
19.5 hours later, counted as 6 days, and skipped. The weekday schedule then waited another week: 14 days between two runs.

The rule is now on calendar days: due seven days after the *day* of the last run. The protection still runs only on the owner's weekday,
after the night window; there is no catch-up on other days. Plain functions of the dates, so they can be tested without Home Assistant.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


def due_date(last_run: Optional[datetime], interval_days: int = 7) -> Optional[date]:
    """The first calendar day the protection is due again, or None when it never ran (due at once)."""
    return None if last_run is None else last_run.date() + timedelta(days=interval_days)


def is_due(last_run: Optional[datetime], today: date, interval_days: int = 7) -> bool:
    """Whether the protection is due on `today`: never run, or `interval_days` calendar days after the day of the last run."""
    due = due_date(last_run, interval_days)
    return due is None or due <= today


@dataclass(frozen=True)
class LegionellaDecision:
    """What the evaluation of one moment says about the protection."""
    is_day: bool       # it is the weekday the owner chose, after the night window
    needs: bool        # the protection is due
    use: bool          # run it now: the scheduled day and due


def decide(last_run: Optional[datetime], now: datetime, scheduled_weekday: int, after_night_window: bool,
           interval_days: int = 7) -> LegionellaDecision:
    """The protection decision for `now`: it runs on the scheduled weekday, after the night window, when it is due."""
    needs = is_due(last_run, now.date(), interval_days)
    scheduled = after_night_window and now.weekday() == scheduled_weekday
    return LegionellaDecision(scheduled, needs, scheduled and needs)
