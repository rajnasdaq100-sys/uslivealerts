# Daily watchlist

Upload one JSON file here each morning before market open (9:30 AM ET),
named for **today's date in US Eastern time**: `YYYY-MM-DD.json`.

The scanners look up `watchlist/<today's ET date>.json` on every poll (every
60s during market hours), so if you fix a typo mid-session and re-upload,
it takes effect on the next poll -- no restart needed.

## Format

```json
{
  "TICKER": {"resistance": 108, "support": 98, "pivot_level": null},
  "NVDA": {"resistance": null, "support": null, "pivot_level": null}
}
```

- `resistance` / `support` / `pivot_level` are all optional -- use `null`
  (not the string `"null"`) for any you don't have yet.
- A ticker with all three set to `null` is still watched: it just won't
  trigger the breakout / undercut-rally / 30-min-pivot setups, which need a
  level. The RVOL+9EMA and extreme-volume alerts have no level requirement
  and still fire for it.
- Keep old dated files around if you like -- they're just a same-day
  reference for the scanners, and double as a free daily log of what you
  were watching.

## Uploading from your phone

GitHub app -> your repo -> `watchlist` folder -> `+` -> Create new file ->
name it `2026-08-31.json` (today's date) -> paste the JSON -> Commit.
Takes under a minute and the next scanner poll (within 60s) will pick it up.

Sample file: `2026-08-31.json` in this folder -- copy its structure for each
new day.
