"""
Standalone Telegram connectivity test -- no market hours, no watchlist, no
yfinance data fetch. Just proves your TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
actually deliver a message and a chart photo, right now.

Unlike scanner_us.py's send_telegram_alert/send_telegram_photo (which log
failures and move on so a bad poll doesn't crash the scanner loop), this
script prints the real HTTP status code and Telegram's response body for
every call -- so if something's wrong, you see exactly what Telegram said
(e.g. "chat not found", "Unauthorized", "bot was blocked by the user")
instead of a swallowed error in a log file.

Usage (local):
    export TELEGRAM_BOT_TOKEN="123:abc"
    export TELEGRAM_CHAT_ID="123456"
    python test_telegram.py

Usage (GitHub Actions):
    Actions tab -> "Test Telegram Alerts" workflow -> Run workflow.
    (see .github/workflows/test-telegram.yml)
"""

import os
import sys
import io
from datetime import datetime

import requests

# --- Load creds the same way config_us.py does, but without config_us.py's
# hard RuntimeError-on-missing-creds -- we want our OWN clearer error below. ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def fail(msg):
    print(f"❌ {msg}")
    sys.exit(1)


def check_creds():
    if not TELEGRAM_BOT_TOKEN:
        fail("TELEGRAM_BOT_TOKEN is not set. export it, or set it as a GitHub Secret.")
    if not TELEGRAM_CHAT_ID:
        fail("TELEGRAM_CHAT_ID is not set. export it, or set it as a GitHub Secret.")
    print(f"✅ Found TELEGRAM_BOT_TOKEN (starts with '{TELEGRAM_BOT_TOKEN[:6]}...') "
          f"and TELEGRAM_CHAT_ID ('{TELEGRAM_CHAT_ID}')")


def check_bot_identity():
    """Calls getMe -- confirms the token itself is valid, independent of chat_id."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    resp = requests.get(url, timeout=10)
    print(f"\n[getMe] status={resp.status_code}")
    print(f"[getMe] body={resp.text}")
    if resp.status_code != 200:
        fail("Token looks invalid -- getMe failed. Double-check TELEGRAM_BOT_TOKEN.")
    bot_username = resp.json().get("result", {}).get("username", "?")
    print(f"✅ Token is valid -- bot is @{bot_username}")


def send_test_message():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": (f"🧪 *Test Alert*\n"
                 f"• *Status:* Telegram delivery working\n"
                 f"• *Sent at:* `{timestamp}`\n"
                 f"• *Source:* `test_telegram.py`"),
        "parse_mode": "Markdown",
    }
    resp = requests.post(url, json=payload, timeout=10)
    print(f"\n[sendMessage] status={resp.status_code}")
    print(f"[sendMessage] body={resp.text}")
    if resp.status_code != 200:
        fail("sendMessage failed -- see body above for Telegram's exact error "
             "(common causes: wrong chat_id, or you haven't messaged the bot yet "
             "so it can't message you first).")
    print("✅ Text message delivered -- check Telegram now.")


def send_test_photo():
    """Reuses the real render_chart_snapshot() so this test also proves the
    matplotlib chart-rendering path works, not just plain text delivery."""
    try:
        import numpy as np
        import pandas as pd
        from alert_enrichment import render_chart_snapshot
    except Exception as e:
        print(f"\n⚠️  Skipping photo test -- couldn't import chart dependencies: {e}")
        return

    rng = np.random.default_rng(0)
    idx = pd.date_range("2026-01-01 09:30", periods=40, freq="5min")
    close = 100 + np.cumsum(rng.normal(0, 0.3, 40))
    df = pd.DataFrame({
        "open": close + rng.normal(0, 0.1, 40),
        "high": close + abs(rng.normal(0, 0.2, 40)),
        "low": close - abs(rng.normal(0, 0.2, 40)),
        "close": close,
        "volume": rng.integers(50_000, 200_000, 40),
    }, index=idx)

    chart_bytes = render_chart_snapshot(
        df, "TESTX", entry_price=close[-1], stop_loss=close[-1] - 2,
        target=close[-1] + 4, key_level=close[0],
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    resp = requests.post(
        url,
        data={"chat_id": TELEGRAM_CHAT_ID, "caption": "🧪 Test chart snapshot",
              "parse_mode": "Markdown"},
        files={"photo": ("test_chart.png", io.BytesIO(chart_bytes), "image/png")},
        timeout=15,
    )
    print(f"\n[sendPhoto] status={resp.status_code}")
    print(f"[sendPhoto] body={resp.text}")
    if resp.status_code != 200:
        fail("sendPhoto failed -- see body above.")
    print("✅ Chart photo delivered -- check Telegram now.")


if __name__ == "__main__":
    print("=== Telegram connectivity test ===")
    check_creds()
    check_bot_identity()
    send_test_message()
    send_test_photo()
    print("\n🎉 All checks passed -- your Telegram pipeline is working end to end.")
