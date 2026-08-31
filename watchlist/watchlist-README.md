# Daily watchlist

Upload one JSON file here each morning before market open (9:30 AM ET),
named for **today's date in US Eastern time**: `YYYY-MM-DD.json`.

The scanners look up `watchlist/<today's ET date>.json` on every poll (every
60s during market hours), so if you fix a typo mid-session and re-upload,
it takes effect on the next poll -- no restart needed.

## Format

```json
{
  "TICKER": {
    "resistance": 108,
    "support": 98,
    "pivot_level": null,
    "setup": "VCP breakout",
    "description": "3-week tight base, watching for volume breakout"
  },
  "NVDA": {"resistance": null, "support": null, "pivot_level": null}
}
```

- `resistance` / `support` / `pivot_level` are all optional -- use `null`
  (not the string `"null"`) for any you don't have yet.
- A ticker with all three set to `null` is still watched: it just won't
  trigger the breakout / undercut-rally / 30-min-pivot setups, which need a
  level. The RVOL+9EMA and extreme-volume alerts have no level requirement
  and still fire for it.
- `setup` and `description` are also optional (leave them out entirely, or
  set to `""`, if you don't want them). Whatever you put here is appended
  to **every** Telegram alert for that ticker that day -- e.g.
  `setup: "VCP breakout"` and `description: "3-week tight base"` will show
  up as two extra lines under any breakout/RVOL/institutional-flow alert
  that fires for that symbol:
  ```
  • Setup: VCP breakout
  • Note: 3-week tight base
  ```
  Handy for reminding yourself *why* a ticker was on the list when the
  alert actually fires, possibly hours later.
- Keep old dated files around if you like -- they're just a same-day
  reference for the scanners, and double as a free daily log of what you
  were watching.

## Uploading from your phone

GitHub app -> your repo -> `watchlist` folder -> `+` -> Create new file ->
name it `2026-08-31.json` (today's date) -> paste the JSON -> Commit.
Takes under a minute and the next scanner poll (within 60s) will pick it up.

Sample file: `2026-08-31.json` in this folder -- copy its structure for each
new day.
