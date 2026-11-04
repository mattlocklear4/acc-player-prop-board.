# ACC Player Prop Board — v1.0

A responsive, static GitHub Pages website for ACC men's basketball game logs, advanced stats, player projections and BetOnline prop lines.

## Deploy (no Netlify)

1. In the public `acc-player-prop-board` GitHub repository, choose **Add file → Upload files**.
2. Upload the **four files inside this package** (`index.html`, `style.css`, `data.js`, `app.js`) plus `README.md` to the repository **root**, not inside a folder.
3. Commit to `main`. GitHub Pages must be set to **Deploy from a branch → main → /(root)**.
4. Visit `https://mattlocklear4.github.io/acc-player-prop-board/` after Pages finishes deploying.

> GitHub's web upload interface may not extract ZIP files automatically. Extract the ZIP first and upload its contents. On a PC this is easiest; on Android, extract in Files then upload individual files.

## Included

- Three November 2, 2026 game box scores, with **ACC players only**, transcribed from user-supplied Bart Torvik screenshots: Duke–Army, NC State–Campbell, Miami–Florida.
- 43 historical BetOnline prop lines from the conversation (Miami–Florida and Duke–Army).
- Sortable game/advanced tables, projection editing, TSV line import, CSV export, and JSON backup/restore.
- A *preliminary*, illustrative pricing baseline: Poisson for rebounds/assists/threes, normal distribution with fixed 5.5-point SD for points. Do not treat these as validated fair odds.

## Important limitations

- **No automatic Bart Torvik import yet.** Automated access is unverified and may be blocked.
- **No cloud sync yet.** Changes are saved only in each browser's `localStorage`. Use JSON backup/restore to move edits between PC and phone.
- **Public website.** Never put secrets, API keys, or sensitive personal information in these files or public GitHub commits.
- Screenshot stats are rounded; some abbreviated bench-player names have not been verified.
- Game-level projections are **not prefilled from postgame stats**, to avoid hindsight bias.
- The supplied odds are historical; the board does not claim to display live prices.

## Next phases

1. Test a compliant, stable source for advanced game stats (and validate game-level data against known screenshots).
2. Add a scheduled GitHub Actions ingestion workflow only after successful validation.
3. Import preseason and exhibition data; implement minutes and opportunity modeling.
4. Add calibrated distributions and backtesting, then secure cross-device syncing if desired.


## v1.1 — automated source diagnostic

This release adds a GitHub Actions workflow (`.github/workflows/acc-collector.yml`) that runs once daily and on demand. It tests `toRvik::bart_player_game(year=2027, stat='advanced'/'box', team=...)` for Duke, NC State and Miami. The collector writes a status report to `collector/status.json` and, if successful, raw CSVs to `collector/output/`. The website displays status in **Imports & Export**.

**Run it:** Repository → Actions → ACC advanced stats source test → Run workflow. Then review the action log, `acc-source-test` artifact and the website status. GitHub Actions may ask you to enable workflows first. The workflow needs `Read and write permissions` for `GITHUB_TOKEN` under Settings → Actions → General to publish status. The test runs independently of the website's existing manually verified data; no player stats or projections are replaced.

**Limitations:** The external source may block access or lag the current season. Successful downloads are *not* automatically accepted as verified; compare Duke–Army, NC State–Campbell and Miami–Florida against the screenshot-based baseline before wiring a full ACC ingestion pipeline. Data is published to a **public** repository; never put credentials or private betting records in the collector. GitHub Actions schedules can be delayed or skipped.
