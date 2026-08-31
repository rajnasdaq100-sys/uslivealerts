"""
Separate bot: institutional-flow scanner for US markets.

Same composite logic as institutional_scanner_in.py (see that file's
docstring), but using yfinance for both price data and the news catalyst
check instead of Fyers + the nse package.
"""

import time
import logging
from datetime import datetime, time as dtime
import requests
import pandas as pd
import yfinance as yf

from config_us import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    INSTITUTIONAL_RVOL_THRESHOLD, CLOSE_STRENGTH_PCT,
    SUSTAINED_VOL_BARS, SUSTAINED_VOL_MULT,
    MIN_ELAPSED_MINS_FOR_RVOL, CATALYST_LOOKBACK_MINS, POLL_INTERVAL_SECONDS,
    SCAN_START_TIME, SCAN_END_TIME,
    ACCOUNT_CAPITAL, RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE, SEND_CHART_SNAPSHOT,
)
from entry_setups import institutional_flow_signal
from catalyst_us import get_recent_news, format_catalyst_summary
from alert_enrichment import compute_trade_plan, format_trade_plan_line, render_chart_snapshot
from alert_logger import log_alert, check_outcomes
from watchlist_store import load_watchlist

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def format_setup_note(levels: dict) -> str:
    """Appends the optional 'setup' and 'description' fields from the
    watchlist entry to an alert message, if present."""
    lines = ""
    setup = levels.get("setup")
    description = levels.get("description")
    if setup:
        lines += f"\n• *Setup:* {setup}"
    if description:
        lines += f"\n• *Note:* {description}"
    return lines

US_TZ = "America/New_York"
US_SESSION_START = "09:30"
US_SESSION_END = "16:00"


class InstitutionalFlowScannerUS:
    def __init__(self):
        self.last_alert_bar = {}

    def fetch_5m_and_daily(self, symbol: str):
        try:
            df_5m = yf.Ticker(symbol).history(period="5d", interval="5m")
            df_daily = yf.Ticker(symbol).history(period="90d", interval="1d")
        except Exception as e:
            logging.error(f"Fetch failed for {symbol}: {e}")
            return pd.DataFrame(), pd.DataFrame()

        def clean(df):
            if df.empty:
                return df
            df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                     "Close": "close", "Volume": "volume"})
            df.index = df.index.tz_convert(US_TZ) if df.index.tz else df.index.tz_localize(US_TZ)
            return df[["open", "high", "low", "close", "volume"]]

        return clean(df_5m), clean(df_daily)

    def send_telegram_alert(self, message: str):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logging.error(f"Telegram alert failed: {e}")

    def send_telegram_photo(self, image_bytes: bytes, caption: str):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        try:
            requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": ("chart.png", image_bytes, "image/png")},
                timeout=10,
            )
        except Exception as e:
            logging.error(f"Telegram photo failed: {e}")

    def send_alert(self, message: str, df=None, symbol="", entry=None, stop=None, target=None):
        if SEND_CHART_SNAPSHOT and df is not None and not df.empty:
            try:
                chart = render_chart_snapshot(df, symbol, entry_price=entry, stop_loss=stop, target=target)
                self.send_telegram_photo(chart, message)
                return
            except Exception as e:
                logging.error(f"Chart render failed for {symbol}, falling back to text: {e}")
        self.send_telegram_alert(message)

    def notify_resolved_alerts(self, symbol: str, df: pd.DataFrame):
        if df.empty:
            return
        for alert in check_outcomes("US", symbol, df.iloc[-1]):
            hit_target = alert["new_status"] == "target_hit"
            emoji = "✅" if hit_target else "🛑"
            label = "TARGET HIT" if hit_target else "STOP HIT"
            r_txt = f"{alert['r_multiple']:.2f}R" if alert.get("r_multiple") is not None else "n/a"
            msg = (f"{emoji} *{label}*\n"
                   f"• *Symbol:* `{symbol}`\n"
                   f"• *Setup:* `{alert['setup_type']}`\n"
                   f"• *Entry:* `${alert['entry_price']:.2f}` → *Exit:* `${alert['exit_price']:.2f}`\n"
                   f"• *Result:* `{r_txt}`")
            self.send_telegram_alert(msg)

    def evaluate_symbol(self, symbol: str, levels: dict):
        df_5m, df_daily = self.fetch_5m_and_daily(symbol)
        if df_5m.empty or len(df_5m) < 15 or df_daily.empty or len(df_daily) < 15:
            return

        today = pd.Timestamp.now(tz=US_TZ).date()
        df_5m_today = df_5m[df_5m.index.date == today]
        if df_5m_today.empty:
            return

        # Check open alerts against this bar first -- runs every poll regardless
        # of whether a new signal triggers below.
        self.notify_resolved_alerts(symbol, df_5m_today)

        daily_avg_vol = df_daily["volume"].iloc[-51:-1].mean()
        signal = institutional_flow_signal(
            df_5m_today, daily_avg_vol,
            rvol_threshold=INSTITUTIONAL_RVOL_THRESHOLD,
            close_strength_pct=CLOSE_STRENGTH_PCT,
            sustained_bars=SUSTAINED_VOL_BARS,
            sustained_mult=SUSTAINED_VOL_MULT,
            session_start=US_SESSION_START, session_end=US_SESSION_END, tz=US_TZ,
        )

        if signal["rvol"]["elapsed_mins"] < MIN_ELAPSED_MINS_FOR_RVOL:
            return

        if not signal["triggered"]:
            return

        last_bar_ts = df_5m_today.index[-1]
        key = f"{symbol}_institutional"
        if self.last_alert_bar.get(key) == last_bar_ts:
            return

        news_items = get_recent_news(symbol, lookback_mins=CATALYST_LOOKBACK_MINS)
        catalyst_line = format_catalyst_summary(news_items)

        entry_price = signal["last_close"]
        stop_loss = round(df_5m_today["low"].min(), 2)  # session low so far -- same convention as the other setups
        plan = compute_trade_plan(entry_price, stop_loss, ACCOUNT_CAPITAL, RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE)

        msg = (f"🏦 *US INSTITUTIONAL FLOW ALERT*\n"
               f"• *Symbol:* `{symbol}`\n"
               f"• *RVOL:* `{signal['rvol']['rvol_ratio']}x`\n"
               f"• *Strong Close:* `{signal['close_strong']}`\n"
               f"• *Sustained Volume:* `{signal['volume_sustained']['sustained']}`\n"
               f"• *Fresh Session High:* `{signal['fresh_high']}`\n"
               f"• *Catalyst:* {catalyst_line}\n"
               f"{format_trade_plan_line(plan, currency_symbol='$')}")
        msg += format_setup_note(levels)

        log_alert(market="US", symbol=symbol, setup_type="institutional", entry_price=entry_price,
                  stop_loss=stop_loss, target_price=plan.get("target"), quantity=plan.get("quantity"),
                  rvol=signal["rvol"]["rvol_ratio"], catalyst_found=int(bool(news_items)),
                  bar_timestamp=str(last_bar_ts))
        self.send_alert(msg, df=df_5m_today, symbol=symbol, entry=entry_price, stop=stop_loss, target=plan.get("target"))
        self.last_alert_bar[key] = last_bar_ts

    def run_scanner_loop(self):
        logging.info("Starting US Institutional Flow Scanner...")
        start_h, start_m = map(int, SCAN_START_TIME.split(":"))
        end_h, end_m = map(int, SCAN_END_TIME.split(":"))
        scan_start, scan_end = dtime(start_h, start_m), dtime(end_h, end_m)

        while True:
            now = pd.Timestamp.now(tz=US_TZ).time()
            if scan_start <= now <= scan_end:
                watchlist = load_watchlist()  # re-read every poll -- picks up bot updates live
                for symbol, levels in watchlist.items():
                    self.evaluate_symbol(symbol, levels)
                time.sleep(POLL_INTERVAL_SECONDS)
            elif now < scan_start:
                time.sleep(60)
            else:
                logging.info("Scan window closed for the day. Exiting.")
                break


if __name__ == "__main__":
    scanner = InstitutionalFlowScannerUS()
    scanner.run_scanner_loop()
