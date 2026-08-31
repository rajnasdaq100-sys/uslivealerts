import time
import logging
from datetime import datetime, time as dtime
import requests
import pandas as pd
import yfinance as yf

from config_us import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RVOL_THRESHOLD, EXTREME_RVOL_THRESHOLD, MIN_ELAPSED_MINS_FOR_RVOL,
    EMA_TOLERANCE_PCT, POLL_INTERVAL_SECONDS,
    SCAN_START_TIME, SCAN_END_TIME,
    ACCOUNT_CAPITAL, RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE, SEND_CHART_SNAPSHOT,
)
from entry_setups import (
    relative_volume, near_ema, check_breakout_entry,
    check_undercut_rally, check_30min_pivot,
)
from alert_enrichment import compute_trade_plan, format_trade_plan_line, render_chart_snapshot
from alert_logger import log_alert, check_outcomes
from watchlist_store import load_watchlist

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def format_setup_note(levels: dict) -> str:
    """Appends the optional 'setup' and 'description' fields from the
    watchlist entry to an alert message, if present. Both are optional --
    omit either or both from a ticker's watchlist entry and this returns
    just what's there (or an empty string if neither is set)."""
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


class USSwingScanner:
    def __init__(self):
        # tracks the last bar timestamp we already alerted on, per symbol+setup,
        # so we re-alert on each NEW bar where the condition holds, but don't
        # spam every poll within the same still-forming bar.
        self.last_alert_bar = {}

    # -----------------------------------------------------------------
    # Data fetch
    # -----------------------------------------------------------------

    def fetch_bars(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval)
            if df.empty:
                return df
            df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                     "Close": "close", "Volume": "volume"})
            df.index = df.index.tz_convert(US_TZ) if df.index.tz else df.index.tz_localize(US_TZ)
            return df[["open", "high", "low", "close", "volume"]]
        except Exception as e:
            logging.error(f"Fetch failed for {symbol} [{interval}]: {e}")
            return pd.DataFrame()

    def fetch_all_timeframes(self, symbol: str):
        df_5m = self.fetch_bars(symbol, period="5d", interval="5m")
        df_30m = self.fetch_bars(symbol, period="5d", interval="30m")
        df_daily = self.fetch_bars(symbol, period="90d", interval="1d")
        return df_5m, df_30m, df_daily

    # -----------------------------------------------------------------
    # Alerting
    # -----------------------------------------------------------------

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

    def send_alert(self, message: str, df=None, symbol="", entry=None, stop=None, target=None, key_level=None):
        if SEND_CHART_SNAPSHOT and df is not None and not df.empty:
            try:
                chart = render_chart_snapshot(df, symbol, entry_price=entry, stop_loss=stop,
                                               target=target, key_level=key_level)
                self.send_telegram_photo(chart, message)
                return
            except Exception as e:
                logging.error(f"Chart render failed for {symbol}, falling back to text: {e}")
        self.send_telegram_alert(message)

    def dispatch_if_new_bar(self, symbol: str, setup_name: str, bar_timestamp, message: str,
                             df=None, entry=None, stop=None, target=None, key_level=None,
                             quantity=None, rvol=None, catalyst_found=None):
        key = f"{symbol}_{setup_name}"
        if self.last_alert_bar.get(key) != bar_timestamp:
            if entry is not None:
                log_alert(market="US", symbol=symbol, setup_type=setup_name, entry_price=entry,
                          stop_loss=stop, target_price=target, quantity=quantity, rvol=rvol,
                          catalyst_found=catalyst_found, bar_timestamp=str(bar_timestamp))
            self.send_alert(message, df=df, symbol=symbol, entry=entry, stop=stop,
                             target=target, key_level=key_level)
            self.last_alert_bar[key] = bar_timestamp

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

    # -----------------------------------------------------------------
    # Strategy evaluation
    # -----------------------------------------------------------------

    def evaluate_symbol(self, symbol: str, levels: dict):
        df_5m, df_30m, df_daily = self.fetch_all_timeframes(symbol)
        if df_5m.empty or len(df_5m) < 15 or df_daily.empty or len(df_daily) < 30:
            return

        # today's 5m bars only -- yfinance returns the last 5 days for intraday
        today = pd.Timestamp.now(tz=US_TZ).date()
        df_5m_today = df_5m[df_5m.index.date == today]
        if df_5m_today.empty:
            return

        last_bar_5m_ts = df_5m_today.index[-1]
        daily_avg_vol = df_daily["volume"].iloc[-51:-1].mean()  # 50 days, excluding today

        rvol = relative_volume(df_5m_today, daily_avg_vol,
                                session_start=US_SESSION_START, session_end=US_SESSION_END, tz=US_TZ)
        ema9_daily = near_ema(df_daily, length=9, tolerance_pct=EMA_TOLERANCE_PCT)        # daily 9EMA
        ema9_intraday = near_ema(df_5m_today, length=9, tolerance_pct=EMA_TOLERANCE_PCT)  # intraday 9EMA

        # Pacing-projected RVOL is noisy right after open (tiny time-elapsed
        # denominator inflates modest early volume into huge projected ratios).
        # Suppress all RVOL-based alerts until the session has enough data.
        rvol_is_reliable = rvol["elapsed_mins"] >= MIN_ELAPSED_MINS_FOR_RVOL
        high_volume = rvol_is_reliable and rvol["rvol_ratio"] >= RVOL_THRESHOLD

        # --- Extreme Volume Alert: fires on very high RVOL alone ---
        if rvol_is_reliable and rvol["rvol_ratio"] >= EXTREME_RVOL_THRESHOLD:
            msg = (f"🔥 *US EXTREME VOLUME ALERT*\n"
                   f"• *Symbol:* `{symbol}`\n"
                   f"• *RVOL:* `{rvol['rvol_ratio']}x` (`{rvol['rvol_pct']}%` vs avg)\n"
                   f"• *{rvol['elapsed_mins']:.0f} min into session*\n"
                   f"• *Last Close:* `${df_5m_today['close'].iloc[-1]:.2f}`")
            msg += format_setup_note(levels)
            self.dispatch_if_new_bar(symbol, "extreme_rvol", last_bar_5m_ts, msg, df=df_5m_today)

        # --- Generic Alert: high RVOL + near intraday 9EMA, independent of any level ---
        if high_volume and ema9_intraday["is_near"]:
            msg = (f"📊 *US RVOL + 9EMA ALERT*\n"
                   f"• *Symbol:* `{symbol}`\n"
                   f"• *RVOL:* `{rvol['rvol_ratio']}x` (`{rvol['rvol_pct']}%` vs avg)\n"
                   f"• *Price vs Intraday 9EMA:* `{ema9_intraday['pct_diff']}%` "
                   f"({'above' if ema9_intraday['above_ema'] else 'below'})\n"
                   f"• *Last Close:* `${ema9_intraday['last_close']:.2f}`")
            msg += format_setup_note(levels)
            self.dispatch_if_new_bar(symbol, "rvol_ema_generic", last_bar_5m_ts, msg, df=df_5m_today)

        # --- Setup 1: Breakout ---
        resistance = levels.get("resistance")
        if resistance:
            result = check_breakout_entry(df_daily, df_5m_today, key_resistance=resistance)
            if result["triggered"] and high_volume:
                entry_price = df_5m_today["close"].iloc[-1]
                plan = compute_trade_plan(entry_price, result["stop_loss"], ACCOUNT_CAPITAL,
                                           RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE)
                msg = (f"🚀 *US BREAKOUT ALERT*\n"
                       f"• *Symbol:* `{symbol}`\n"
                       f"• *Trigger:* Broke resistance `${resistance}` with volume spike\n"
                       f"• *RVOL:* `{rvol['rvol_ratio']}x`\n"
                       f"• *Near 9EMA(D):* `{ema9_daily['is_near']}`\n"
                       f"{format_trade_plan_line(plan, currency_symbol='$')}")
                msg += format_setup_note(levels)
                self.dispatch_if_new_bar(symbol, "breakout", last_bar_5m_ts, msg,
                                          df=df_5m_today, entry=entry_price, stop=result["stop_loss"],
                                          target=plan.get("target"), key_level=resistance,
                                          quantity=plan.get("quantity"), rvol=rvol["rvol_ratio"])

        # --- Setup 2: Undercut & Rally ---
        support = levels.get("support")
        if support:
            result = check_undercut_rally(df_5m_today, key_support=support)
            if result["triggered"] and high_volume:
                entry_price = df_5m_today["close"].iloc[-1]
                plan = compute_trade_plan(entry_price, result["stop_loss"], ACCOUNT_CAPITAL,
                                           RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE)
                msg = (f"⚡ *US UNDERCUT & RALLY ALERT*\n"
                       f"• *Symbol:* `{symbol}`\n"
                       f"• *Trigger:* Reclaimed support `${support}` after undercut\n"
                       f"• *RVOL:* `{rvol['rvol_ratio']}x`\n"
                       f"• *Near 9EMA(D):* `{ema9_daily['is_near']}`\n"
                       f"{format_trade_plan_line(plan, currency_symbol='$')}")
                msg += format_setup_note(levels)
                self.dispatch_if_new_bar(symbol, "unr", last_bar_5m_ts, msg,
                                          df=df_5m_today, entry=entry_price, stop=result["stop_loss"],
                                          target=plan.get("target"), key_level=support,
                                          quantity=plan.get("quantity"), rvol=rvol["rvol_ratio"])

        # --- Setup 3: 30-Min Pivot ---
        pivot_level = levels.get("pivot_level")
        if pivot_level and not df_30m.empty:
            today_30m = df_30m[df_30m.index.date == today]
            result = check_30min_pivot(today_30m, key_level=pivot_level)
            if result.get("triggered"):
                last_bar_30m_ts = today_30m.index[-1]
                entry_price = today_30m["close"].iloc[-1]
                plan = compute_trade_plan(entry_price, result["stop_loss"], ACCOUNT_CAPITAL,
                                           RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE)
                msg = (f"📈 *US 30-MIN PIVOT ALERT*\n"
                       f"• *Symbol:* `{symbol}`\n"
                       f"• *Trigger:* Broke green candle high off `${pivot_level}`\n"
                       f"• *RVOL:* `{rvol['rvol_ratio']}x`\n"
                       f"{format_trade_plan_line(plan, currency_symbol='$')}")
                msg += format_setup_note(levels)
                self.dispatch_if_new_bar(symbol, "30m_pivot", last_bar_30m_ts, msg,
                                          df=today_30m, entry=entry_price, stop=result["stop_loss"],
                                          target=plan.get("target"), key_level=pivot_level,
                                          quantity=plan.get("quantity"), rvol=rvol["rvol_ratio"])

        # --- Check open alerts against this bar for target/stop resolution ---
        self.notify_resolved_alerts(symbol, df_5m_today)

    # -----------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------

    def run_scanner_loop(self):
        logging.info("Starting US Swing Trading Scanner Loop...")
        start_h, start_m = map(int, SCAN_START_TIME.split(":"))
        end_h, end_m = map(int, SCAN_END_TIME.split(":"))
        scan_start = dtime(start_h, start_m)
        scan_end = dtime(end_h, end_m)

        while True:
            now = pd.Timestamp.now(tz=US_TZ).time()
            if scan_start <= now <= scan_end:
                watchlist = load_watchlist()  # re-read every poll -- picks up bot updates live
                if not watchlist:
                    logging.info("Watchlist is empty -- send today's list to the Telegram bot.")
                for symbol, levels in watchlist.items():
                    self.evaluate_symbol(symbol, levels)
                time.sleep(POLL_INTERVAL_SECONDS)
            elif now < scan_start:
                logging.info("Market not open yet, sleeping 60s...")
                time.sleep(60)
            else:
                logging.info("Scan window closed for the day. Exiting.")
                break


if __name__ == "__main__":
    scanner = USSwingScanner()
    scanner.run_scanner_loop()
