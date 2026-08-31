"""
Watchlist load, backed by a dated JSON file in watchlist/, uploaded manually
each day (GitHub web UI or app) before market open.

File naming: watchlist/<YYYY-MM-DD>.json using the US Eastern calendar date
(so it lines up with the trading session regardless of what timezone/date it
is where you upload from). See watchlist/README.md for the exact format.

Both scanner_us.py and institutional_scanner_us.py re-read this at the top
of every polling loop iteration, so if you fix a typo mid-session and
re-upload the file, it takes effect on the next poll -- no restart needed.
"""

import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

WATCHLIST_DIR = "watchlist"
US_TZ = ZoneInfo("America/New_York")

_warned_missing_today = False  # only log the "no file yet" warning once per process


def _today_path() -> str:
    today = datetime.now(US_TZ).strftime("%Y-%m-%d")
    return os.path.join(WATCHLIST_DIR, f"{today}.json")


def load_watchlist() -> dict:
    """Returns {} if today's file doesn't exist yet -- callers should treat
    an empty watchlist as "nothing to scan yet" and just wait for the next
    poll (e.g. file uploaded a few minutes late)."""
    global _warned_missing_today
    path = _today_path()

    if not os.path.exists(path):
        if not _warned_missing_today:
            logging.warning(f"No watchlist file found at {path} -- upload today's "
                             f"list to watchlist/ before market open.")
            _warned_missing_today = True
        return {}

    try:
        with open(path, "r") as f:
            data = json.load(f)
        _warned_missing_today = False
        return data
    except (json.JSONDecodeError, OSError) as e:
        logging.error(f"Couldn't parse {path}: {e}")
        return {}


def parse_watchlist_text(text: str):
    """
    Kept for convenience if you ever want to hand-convert a pasted list into
    JSON locally. Parses one ticker per line, comma or tab separated:
        SYRE,108,98
        CRWD,219,202,
        DFTX,46.17,44.45,49.47
        NVDA
    A ticker alone (no levels) is still watched -- it just won't trigger the
    breakout/undercut-rally/30min-pivot setups, which need a level. The
    RVOL+9EMA and extreme-volume alerts have no level requirement and still
    fire for it.

    Returns (watchlist_dict, errors).
    """
    result = {}
    errors = []

    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("/"):
            continue

        parts = [p.strip() for p in line.replace("\t", ",").split(",")]
        ticker = parts[0].upper()
        if not ticker.isalnum():
            errors.append(f"Skipped invalid ticker: '{raw_line}'")
            continue

        def to_float(s):
            return float(s) if s not in ("", "none", "None", "-", "null") else None

        try:
            resistance = to_float(parts[1]) if len(parts) > 1 else None
            support = to_float(parts[2]) if len(parts) > 2 else None
            pivot = to_float(parts[3]) if len(parts) > 3 else None
        except ValueError:
            errors.append(f"Skipped '{raw_line}' -- couldn't parse a number")
            continue

        result[ticker] = {"resistance": resistance, "support": support, "pivot_level": pivot}

    return result, errors
