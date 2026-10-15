"""NYSE full-day holiday calendar (rule-based) — replaces the hand-typed list (Task 10B).

Rules (NYSE Rule 7.2 practice):
  New Year's Day, Juneteenth (from 2022), Independence Day, Christmas: Saturday -> preceding
  Friday, Sunday -> following Monday — EXCEPT New Year's Day on a Saturday, which is not
  observed (e.g. 2028: no holiday, Friday 2027-12-31 is a trading day).
  MLK Day (3rd Mon Jan), Washington's Birthday (3rd Mon Feb), Good Friday, Memorial Day
  (last Mon May), Labor Day (1st Mon Sep), Thanksgiving (4th Thu Nov).
Unscheduled closures (national days of mourning etc.) are listed in SPECIAL_CLOSURES.
Verified in tests against NYSE's published calendars for 2025-2028.
Early closes (1 pm) do not change session dates and are not modelled.
"""
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

SPECIAL_CLOSURES = {date(2025, 1, 9)}          # National Day of Mourning, President Carter


def _easter(y: int) -> date:                   # Anonymous Gregorian algorithm
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return date(y, month, (h + l - 7 * m + 114) % 31 + 1)


def _nth_weekday(y, month, weekday, n):
    d = date(y, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y, month, weekday):
    d = date(y + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def holidays(year: int) -> frozenset:
    out = set()
    ny = date(year, 1, 1)
    if ny.weekday() != 5:                      # Saturday New Year's Day: not observed
        out.add(_observed(ny))
    out.add(_nth_weekday(year, 1, 0, 3))       # MLK
    out.add(_nth_weekday(year, 2, 0, 3))       # Washington's Birthday
    out.add(_easter(year) - timedelta(days=2))  # Good Friday
    out.add(_last_weekday(year, 5, 0))         # Memorial Day
    if year >= 2022:
        out.add(_observed(date(year, 6, 19)))  # Juneteenth
    out.add(_observed(date(year, 7, 4)))
    out.add(_nth_weekday(year, 9, 0, 1))       # Labor Day
    out.add(_nth_weekday(year, 11, 3, 4))      # Thanksgiving
    out.add(_observed(date(year, 12, 25)))
    out |= {d for d in SPECIAL_CLOSURES if d.year == year}
    return frozenset(out)


def holiday_list(start_year: int, end_year: int) -> list:
    return sorted(str(d) for y in range(start_year, end_year + 1) for d in holidays(y))


def is_session(day) -> bool:
    d = pd.Timestamp(day).date()
    return d.weekday() < 5 and d not in holidays(d.year)


def next_session(day) -> str:
    d = pd.Timestamp(day).date()
    hol = holiday_list(d.year, d.year + 1)
    return str(np.busday_offset(str(d), 1, roll="forward", holidays=hol))
