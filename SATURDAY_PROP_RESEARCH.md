# Saturday ACC player prop research (read-only)

## Automated schedule and projections

GitHub Actions **ACC Projection Dry Run (v2.3)** checks the next **96 hours**. It first tries a **single date-filtered ACC request** to CollegeBasketballData; if that provider is rate-limited, it uses ESPN's public scoreboard as a fallback, then **The Odds API's free NCAAB events endpoint** if ESPN is unavailable. A fallback is explicitly labeled `FALLBACK_ESPN_PUBLIC` or `FALLBACK_FREE_ODDS_EVENTS` in the schedule artifact. Free event listings may omit games not covered by sportsbooks. No paid odds endpoint is called.

The projection artifact is `research/acc_projection_dry_run.json` inside the `acc-projection-dry-run` GitHub Actions artifact. Models: Baseline, KenPom, Vegas, Combined. Vegas and Combined may be unavailable without a timestamp-valid game market. Player minutes are estimates, not injury-adjusted confirmed rotations. KenPom ratings should be refreshed and verified before wagering. Never interpret an unavailable schedule as zero games.

## Compare BetOnline lines without paid API requests

1. Copy `data/betonline_player_props_template.csv` to `data/betonline_player_props.csv`.
2. Paste real BetOnline lines into CSV with columns `player,stat,line,over_odds,under_odds,game_id,book`. Use stats `points`, `rebounds`, `assists`, or `threes`. American odds such as `-110`, `+120`. `game_id` may be blank when the player name uniquely identifies one game. `book` may be blank (defaults to BetOnline).
3. Commit the CSV to GitHub. The next diagnostic run generates `research/acc_betonline_value_preview.json` inside the Actions artifact. Or run locally: `python scripts/acc_betonline_value.py --lines data/betonline_player_props.csv`.
4. Compare the model projection to the line, estimated Over/Under probabilities, and ROI at posted American odds. These are **research estimates**, not calibrated probabilities or verified edges. For points/rebounds/assists, ROI is withheld unless at least 8 prior player games support a historical standard deviation. Threes currently use a Poisson assumption. Integer lines are rejected until push handling is supported.

**No paid API calls are authorized.** The Odds API free events endpoint supplies game schedules, **not player prop lines**. Lines must come from a separate authorized source or manual CSV import. This workflow does not save anything to Supabase, place bets, or automatically grade results.

## Reliability caveats

- The fallback uses bookmaker-visible events, so it may not be a complete ACC schedule.
- Some opponents may fail exact KenPom resolution; they are excluded rather than assigned invented ratings.
- The browser's manual minutes overrides are not applied to the scheduled Python diagnostic.
- A stale KenPom snapshot, missing current-season game logs, and injuries can make a model projection unreliable.
- Model MAE and BetOnline-line MAE require separately captured pregame lines and final actual player stats; this comparison tool does not claim historical accuracy.


## Authorized Friday BetOnline fetch (November 20, 2026)

From GitHub Actions, manually run **ACC Projection Dry Run (v2.3)** on `main` with `fetch_betonline_props=true`. This is intentionally **not** enabled for scheduled or push-triggered runs. The script requests all four player markets for every uniquely matched upcoming Friday ACC event in The Odds API, bookmaker `betonlineag`, until the account quota is exhausted or an error stops retrieval. The script records quota usage in `research/acc_stage8b_betonline_preview.json`, converts paired Over/Under quotes to CSV, and generates `research/acc_betonline_value_preview.json`. A sportsbook may not list every market or player. Do not rerun the paid workflow merely to inspect results: retrieve the previous run's artifact first. This workflow still performs no database writes or bet placements.
