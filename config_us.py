"""
GitHub Actions version -- credentials come from environment variables
(set as GitHub Secrets), never hardcoded here. This file is safe to commit
to a public repo.

Secrets required (Settings -> Secrets and variables -> Actions -> New repository secret):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

For local testing, export these in your shell before running a scanner:
    export TELEGRAM_BOT_TOKEN="123:abc"
    export TELEGRAM_CHAT_ID="123456"
"""

import os

# --- Telegram (from @BotFather) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set. "
        "Set them as GitHub Secrets (Actions workflow) or export them locally."
    )

# --- Scanner tuning ---
RVOL_THRESHOLD = 1.5           # min relative volume to count as "high volume" (used by the 3 setups + generic alert)
EXTREME_RVOL_THRESHOLD = 10.0  # min relative volume to fire the standalone "extreme volume" alert, regardless of price/level
MIN_ELAPSED_MINS_FOR_RVOL = 15   # ignore RVOL-based alerts before this many minutes into the session --
                                  # pacing-projected RVOL is unstable/noisy right after open (small time
                                  # denominator -> huge projected swings from modest early volume)
EMA_TOLERANCE_PCT = 0.3        # how close price must be to 9EMA to count as "near"
POLL_INTERVAL_SECONDS = 60     # how often to poll each symbol

# US market hours: 09:30 - 16:00 ET. Overridable per-shift by the GitHub Actions
# workflow (each shift job sets SCAN_START_TIME/SCAN_END_TIME env vars so a
# single scanner run stays under GitHub's 6-hour job limit -- see
# .github/workflows/). Falls back to the full session for local runs.
SCAN_START_TIME = os.environ.get("SCAN_START_TIME", "09:30")
SCAN_END_TIME = os.environ.get("SCAN_END_TIME", "16:00")

# --- Institutional Flow scanner (separate bot -- see institutional_scanner_us.py) ---
INSTITUTIONAL_RVOL_THRESHOLD = 40    # extreme RVOL floor for this scanner
CLOSE_STRENGTH_PCT = 75              # close must be in the top X% of the bar's range
SUSTAINED_VOL_BARS = 2               # this many consecutive bars must show elevated volume
SUSTAINED_VOL_MULT = 1.3             # ...at least this multiple of the preceding baseline
CATALYST_LOOKBACK_MINS = 30          # how far back to check for a news match

# --- Alert enrichment ---
ACCOUNT_CAPITAL = 1000         # your trading capital, used for position sizing
RISK_PER_TRADE_PCT = 1.0       # % of capital to risk per trade
TARGET_R_MULTIPLE = 2.0        # target = entry + (entry - stop) * this multiple
SEND_CHART_SNAPSHOT = True     # attach a candlestick image to each alert

# --- Watchlist ---
# Loaded from watchlist/<YYYY-MM-DD>.json (US Eastern date) each poll --
# see watchlist_store.py and watchlist/README.md. Upload that day's file
# to the watchlist/ folder before market open (GitHub web UI or app).
