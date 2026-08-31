# US Live Scanner (GitHub Actions edition)

Intraday Telegram alerting for US markets, using free yfinance data
(~15 min delayed). Runs automatically on GitHub's free Actions runners --
no VM, no server, no cost, as long as this repo is **public**.

## ⚠️ Before you make this repo public

If you ever ran an earlier version of this project, check `config_us.py`
in your git history for a hardcoded Telegram bot token. If one is there,
**revoke it** via @BotFather (`/mybots` -> your bot -> API Token -> Revoke)
and generate a new one -- an old commit with a real token is still
retrievable from a public repo's history even if the current file is clean.
This version's `config_us.py` reads secrets from environment variables only
and never contains a real token, so it's safe to commit.

## One-time setup

1. **Push this folder to a public GitHub repo.**
2. **Add two repository secrets** (Settings -> Secrets and variables ->
   Actions -> New repository secret):
   - `TELEGRAM_BOT_TOKEN` -- from @BotFather
   - `TELEGRAM_CHAT_ID` -- your chat ID
3. **Check Settings -> Actions -> General -> Workflow permissions** is set
   to "Read and write permissions" -- the workflows commit `alerts.db` back
   to the repo after each run, and need this to push.
4. That's it -- no server, no systemd, nothing to install anywhere.

## Daily use

Each morning before 9:30 AM ET, upload today's watchlist as
`watchlist/<YYYY-MM-DD>.json` (see `watchlist/README.md` for the exact
format and an example). Easiest from the GitHub mobile app: repo ->
`watchlist` -> `+` -> new file -> paste -> commit. Takes under a minute.

That's the only daily manual step. From there:

| File | Purpose |
|---|---|
| `config_us.py` | Thresholds + secrets (secrets come from env, not this file) |
| `watchlist/` | Upload today's `<date>.json` here each morning |
| `watchlist_store.py` | Loads today's watchlist file |
| `entry_setups.py` | Shared setup-detection logic |
| `catalyst_us.py` | yfinance news lookup (no API key needed) |
| `alert_enrichment.py` | Chart snapshot + position sizing |
| `alert_logger.py` | SQLite logging of every alert (`alerts.db`, committed back to the repo by each workflow run) |
| `alert_report.py` | Win-rate / R-multiple report |
| `scanner_us.py` | Main scanning bot (breakout / undercut-rally / 30-min-pivot / RVOL+9EMA / extreme volume) |
| `institutional_scanner_us.py` | Separate bot -- RVOL 40x+ institutional flow |
| `run_shift.py` | Runs both bots together for one shift -- what the workflows actually call |

## How the scheduling works

The full US session (9:30 AM-4:00 PM ET, 6.5h) is longer than GitHub
Actions' 6-hour job cap, so it's split into two workflows, each a separate
scheduled job:

- **`.github/workflows/scanner-us-morning.yml`** -- 9:30 AM-1:00 PM ET
- **`.github/workflows/scanner-us-afternoon.yml`** -- 1:00 PM-4:05 PM ET

Both bots (`scanner_us.py` + `institutional_scanner_us.py`) run
concurrently inside each shift via `run_shift.py`. Each workflow's cron
trigger fires a bit before its shift's real start time (to safely cover
both EST and EDT without maintaining two separate cron schedules across the
DST change) -- the scripts themselves wait internally until the real US
Eastern start time, so this just means a few idle minutes at the start of
each shift, not early alerts.

You can also trigger either shift manually any time from the repo's
**Actions** tab -> select the workflow -> **Run workflow** -- useful for
testing without waiting for the next scheduled trigger.

## Local testing

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="123:abc"
export TELEGRAM_CHAT_ID="123456"
python scanner_us.py                 # full session, one bot
python institutional_scanner_us.py   # full session, the other bot
python run_shift.py                  # both together, respects SCAN_START_TIME/SCAN_END_TIME if set
```

## Check performance

```bash
python alert_report.py US
```

## Known limitation

## one liner

From the main scanner (scanner_us.py):

**🔥 Extreme Volume Alert** — "Something unusual is happening in this stock right now." Fires when trading volume is 10x or more than normal for this time of day, regardless of what price level you set. No setup needed — just flags "eyes on this."
📊** RVOL + 9EMA Alert** — "High volume + price sitting right at its trend line." Fires when volume is at least 1.5x normal and the price is hovering close to its 9-day moving average (a common trend-following reference point). Doesn't need a resistance/support level — works for any ticker on your list.
🚀 **Breakout Alert** — "Price broke above your resistance level, with volume backing it up." This is the classic "it broke out, and real buyers showed up" signal — only fires if you set a resistance price for that ticker.
⚡ **Undercut & Rally Alert** — "Price dipped below your support, then recovered above it." This is a shakeout/bear-trap pattern — weak hands get scared out below support, then it rallies back. Only fires if you set a support price.
📈 30-Min Pivot Alert — "Price broke above the high of a green 30-minute candle near your pivot level." A shorter-term momentum trigger. Only fires if you set a pivot_level.

From the institutional scanner (institutional_scanner_us.py):

🏦 **Institutional Flow Alert** — "This looks like big-money buying, not retail noise." The strictest one — needs extreme volume (40x+ normal), the price closing strong near the top of its range, and that volume being sustained over a couple of bars (not just one freak spike). It also checks recent news for a possible catalyst and includes that in the alert.

**Bonus, from either bot, after an alert already fired**:

✅ Target Hit / 🛑 Stop Hit — once alerts #3, #4, #5, or #6 fire (the ones with an actual trade plan — entry/stop/target), the bot keeps watching that trade in the background and pings you again when price later hits your profit target or your stop loss, so you know how it played out.

Any of these can carry your extra setup/description notes if you filled them in for that ticker — so a breakout alert on a ticker you tagged "VCP breakout" will show that context right in the message.


