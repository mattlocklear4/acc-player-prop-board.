# ACC Player Prop Board — Project Handoff

Last updated: 2026-11-20. This document is a continuation guide, not a claim that every feature is validated.

## Critical repository identity
- GitHub repository: `mattlocklear4/acc-player-prop-board.` **including the trailing period**. Omitting it causes a 404 through the connected GitHub integration.
- Default branch: `main`. GitHub Pages is the intended host; avoid consuming Netlify credits.
- Existing application: static `index.html`, `style.css`, `app.js`, `data.js` plus supporting data, Python scripts, and GitHub Actions.
- Never create a replacement repository or overwrite working app features merely to resume development.

## User's goal
An actionable 2026–27 ACC men's basketball player prop board on mobile and desktop. Collect box-score histories; project minutes, usage/opportunity, points, rebounds, assists and made threes; incorporate team/opponent pace and strength, KenPom and market context, and verified injuries; compare with sportsbook lines, fair odds and ROI; sort/filter value opportunities. Sportsbooks of interest include DraftKings, FanDuel, Caesars, Fanatics, and BetOnline.

## Implemented / observed in repository
- Existing site tabs: Games, Advanced Stats, Projections, Accuracy, Team Stats, KenPom Ratings, BetOnline Odds, Imports & Export.
- Browser-local editing and JSON backup/restore; Supabase cloud research/archive integration is present in UI. Verify current connectivity before asserting writes work.
- CBBD data ingestion and schedule/projection diagnostic scripts.
- KenPom and Vegas matchup comparison; research adjustments are preliminary, not calibrated betting edges.
- Friday research slate and public `data/friday_board.json`; original and rotation-adjusted minute scenarios.
- `scripts/acc_friday_minutes_review.py` creates a read-only minutes review using last-three/last-five game history, starting frequency, usage signals, and availability flags. Scenario targets 200 regulation team-minutes with a 40-minute/player cap when enough active players exist.
- `scripts/acc_publish_friday_board.py` packages research outputs for the public board.
- Workflow `.github/workflows/acc-projection-dry-run.yml`: schedule retrieval, projection diagnostics, matchup/parity checks, Friday/Saturday slate, minutes review, odds discovery, value self-test, and public board publishing. Workflow concurrency and push-retry handling were added to mitigate competing publishes.
- Published Friday board observed timestamp: `2026-11-20T04:58:02Z`; schedule source was `FALLBACK_ESPN_PUBLIC`. Some teams marked `research_candidate_unverified` due to pending browser parity and manual minutes verification. Do not call these validated bets.
- Historical commit `5bdc599`: CBBD HTTP 429 rate-limit diagnostics. `c379321`: BetOnline team-name matching and disabling paid player-prop API calls.
- Recent observed commits: `81e2378` 200-minute rotation and injury redistribution; `8a5d75d` show rotation-adjusted scenarios; `2016cb9` questionable-player safeguards; `01be3dd` serialize research runs; `3d551d3` Friday board update.
- Commit `3ed47c8` normalized availability-status case and whitespace in Friday minutes review so 'OUT' and 'out' are handled consistently.

## Safeguards
1. Do not treat questionable/reported injuries as confirmed out without a verified source; only confirmed-out status can force zero-minute scenarios.
2. Avoid paid Odds API calls without explicit authorization. The workflow has a manual `fetch_betonline_props` flag and a date-guarded Nov 20, 2026 10 AM EST event; inspect before changing.
3. Do not expose API keys or Supabase credentials in code, artifacts, logs, or public board JSON.
4. Preserve pregame timing and walk-forward evaluation to avoid hindsight leakage.
5. Keep experimental fair odds/ROI clearly labeled until distributions and calibration have been backtested.
6. Preserve existing data and UI; test changes before claiming success.

## Immediate next tasks
1. Check latest `main` and GitHub Actions results, especially `ACC Projection Dry Run (v2.3)`; inspect failed job logs and remaining CBBD 429 issues.
2. Validate team-minute totals, player-minute caps, DNP handling, questionable/out statuses, identity matching, and parity between Python outputs and browser displays.
3. Verify Friday slate and current player availability with dated primary sources. Do not extrapolate old injuries into future games.
4. Verify whether sportsbook lines were actually fetched; compare against projections only for matched player, team, market, game, and tipoff.
5. Improve minutes model: starter/rotation signals, close-game vs blowout samples, foul trouble, transfers, availability redistribution, and uncertainty.
6. Backtest minutes and stat forecasts prospectively, calibrate prop distributions, and only then label pricing as model fair odds.
7. Update this handoff after material architecture or modeling decisions and record actual commit/test results.

## Working practice for future chats
Read this file and inspect the actual latest GitHub repository before coding. The old chat titled 'ACC Props Modelling Plan' is read-only, but its decisions are summarized here. Do not ask the user to click UI handoff buttons: they did not work on their Android app. Use connected GitHub tools directly where available, make safe incremental changes, and distinguish committed work from untested or planned work.
