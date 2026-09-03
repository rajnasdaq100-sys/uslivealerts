# Daily watchlist

Upload one file here each morning before market open (9:30 AM ET), named
for **today's date in US Eastern time** -- **either format works**:

    watchlist/YYYY-MM-DD.json
    watchlist/YYYY-MM-DD.xlsx

Pick whichever is easier that day. The scanners look up today's date on
every poll (every 60s during market hours), so if you fix a typo mid-session
and re-upload, it takes effect on the next poll -- no restart needed. If
both files exist for the same day, the `.json` one is used.

## Format -- JSON

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

## Format -- Excel

One row per ticker, with a header row. Column order doesn't matter, only
the names (not case-sensitive) -- see `template.xlsx` in this folder, ready
to copy and fill in:

| Symbol | Resistance | Support | Pivot Level | Setup | Description |
|---|---|---|---|---|---|
| SYRE | 108 | 98 | | VCP breakout | 3-week tight base |
| NVDA | | | | | |

`Symbol` (or `Ticker`) is the only required column. Leave any cell blank
for "not set" -- no need to type anything, just leave it empty.

## Both formats

- `resistance` / `support` / `pivot_level` are all optional -- leave blank
  (Excel) or use `null` (JSON, not the string `"null"`) for any you don't
  have yet.
- A ticker with all three unset is still watched: it just won't trigger the
  breakout / undercut-rally / 30-min-pivot / pivot-cross setups, which need
  a level. The RVOL-based and institutional-flow alerts have no level
  requirement and still fire for it.
- `setup` and `description` are also optional. Whatever you put here is
  appended to **every** Telegram alert for that ticker that day -- e.g.
  `setup: "VCP breakout"` and `description: "3-week tight base"` will show
  up as two extra lines under any alert that fires for that symbol:
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
For Excel, use "Upload files" instead and rename it to today's date before
committing (see the main README for the exact rename-on-upload steps).
Takes under a minute either way, and the next scanner poll (within 60s)
will pick it up.

Sample files in this folder: `2026-08-31.json` and `template.xlsx` --
copy either one's structure for each new day.
