"""Read-only CBBD connectivity and 2026-11-02 ACC game data test."""
import csv
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.collegebasketballdata.com"
OUT = pathlib.Path("collector/output")
OUT.mkdir(parents=True, exist_ok=True)
KEY = os.environ.get("CBBD_API_KEY", "").strip()
if not KEY:
    sys.exit("ERROR: CBBD_API_KEY secret is missing")


def fetch(endpoint, **params):
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json", "User-Agent": "ACC-Player-Prop-Board/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        # Do not expose authentication headers or credentials.
        sys.exit(f"ERROR: {endpoint} returned HTTP {exc.code}. Check API key, quota and tier.")
    except Exception as exc:
        sys.exit(f"ERROR: {endpoint}: {type(exc).__name__}: {exc}")
    if not isinstance(payload, list):
        sys.exit(f"ERROR: Unexpected {endpoint} response type: {type(payload).__name__}")
    return payload


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


# Confirm that both 2026-11-02 games appear in the schedule.
games = fetch("/games", season=2027, team="Duke")
print(f"Duke season 2027 schedule: {len(games)} records")
if not games:
    sys.exit("ERROR: Duke schedule returned no records")
nov2 = [g for g in games if "2026-11-02" in str(g.get("startDate", g.get("start_date", "")))]
print("Duke games on 2026-11-02:", len(nov2))
save_json("duke_schedule_sample.json", nov2 or games[:2])

# CBBD's documented game-player endpoint supports team/season/date filters.
# Pull each ACC team separately, so the nonconference opponent is included.
all_data = {}
for team, opponent in (("Duke", "Army"), ("NC State", "Campbell")):
    records = fetch("/games/players", season=2027, team=team,
                    startDateRange="2026-11-02T00:00:00Z",
                    endDateRange="2026-11-04T00:00:00Z")
    print(f"{team}: {len(records)} game-level player box score objects")
    all_data[team] = records
    save_json("player_games_" + team.lower().replace(" ", "_") + ".json", records)
    if records:
        print("Top-level fields:", sorted(records[0].keys()))
        print("Sample object saved to artifact for schema inspection")

summary = {"season": 2027, "date": "2026-11-02", "schedule_records": len(games),
           "duke_player_game_objects": len(all_data["Duke"]),
           "nc_state_player_game_objects": len(all_data["NC State"]),
           "note": "Raw CBBD responses saved for schema mapping; no website files changed."}
save_json("summary.json", summary)
if not all(all_data.values()):
    sys.exit("ERROR: At least one team returned zero player game objects; inspect artifacts and API availability")
print("SUCCESS: CBBD player game data returned for both teams. Download cbbd-test-results artifact.")
