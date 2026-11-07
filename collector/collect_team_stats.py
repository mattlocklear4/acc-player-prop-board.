#!/usr/bin/env python3
"""Nightly CBBD ACC team-season stats. One API request; no secrets in output."""
import argparse, csv, datetime as dt, json, os, time
from pathlib import Path
from urllib import request, parse, error

TEAMS = {"Boston College","California","Clemson","Duke","Florida State","Georgia Tech",
         "Louisville","Miami","NC State","North Carolina","Notre Dame","Pittsburgh",
         "SMU","Stanford","Syracuse","Virginia","Virginia Tech","Wake Forest"}
BASE = "https://api.collegebasketballdata.com/stats/team/season"

def flatten(obj, prefix=""):
    result = {}
    for key, value in obj.items():
        label = prefix + key
        if isinstance(value, dict):
            result.update(flatten(value, label + "_"))
        elif value is None or isinstance(value, (str, int, float, bool)):
            result[label] = value
    return result

def collect(season, key):
    url = BASE + "?" + parse.urlencode({"season":season, "conference":"ACC"})
    req = request.Request(url, headers={"Authorization":"Bearer "+key,
       "Accept":"application/json","User-Agent":"acc-player-prop-board/1.7"})
    for attempt in range(3):
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except error.HTTPError as exc:
            if exc.code in (429,500,502,503,504) and attempt < 2:
                time.sleep(3*(attempt+1))
                continue
            raise RuntimeError("CBBD HTTP "+str(exc.code)) from exc
        except (error.URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(3*(attempt+1))
                continue
            raise RuntimeError("CBBD request failed") from exc

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int, default=2027)
    p.add_argument("--output-dir", default="data/cbbd")
    args = p.parse_args()
    key = os.environ.get("CBBD_API_KEY", "").strip()
    if not key:
        raise SystemExit("CBBD_API_KEY secret is missing")
    data = collect(args.season, key)
    if not isinstance(data,list) or any(not isinstance(item,dict) for item in data):
        raise SystemExit("Unexpected CBBD response; existing files untouched")
    names = [x.get("team") for x in data]
    if len(data) != len(TEAMS) or set(names) != TEAMS:
        raise SystemExit("Expected 18 unique ACC teams; got "+str(len(data))+
                         " rows and "+str(len(set(names)))+" unique teams. Existing files untouched.")
    if any(x.get("season") != args.season or not isinstance(x.get("teamStats"),dict)
           or not isinstance(x.get("opponentStats"),dict) for x in data):
        raise SystemExit("Invalid season or missing team/opponent statistics; existing files untouched")
    data.sort(key=lambda x:x["team"])
    flat = [flatten(x) for x in data]
    fields = sorted(set().union(*(r.keys() for r in flat)))
    output = Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=True)
    csvpath = output / f"acc_team_stats_{args.season}.csv"
    jsonpath = output / f"acc_team_stats_{args.season}.json"
    # Write temporary files, then replace the published files only after validation.
    tmpcsv = csvpath.with_suffix(".csv.tmp")
    tmpjson = jsonpath.with_suffix(".json.tmp")
    with tmpcsv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flat)
    tmpjson.write_text(json.dumps(data,indent=2)+"\\n",encoding="utf-8")
    tmpcsv.replace(csvpath)
    tmpjson.replace(jsonpath)
    summary = {
        "season":args.season,
        "last_successful_run_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "api_requests":1,
        "team_count":len(data),
        "teams":names,
        "csv_file":str(csvpath),
        "json_file":str(jsonpath),
        "notes":"Season-to-date raw team and opponent ratings; not opponent-adjusted."
    }
    (output / f"acc_team_collection_summary_{args.season}.json").write_text(
        json.dumps(summary,indent=2)+"\\n",encoding="utf-8")
    print(f"SUCCESS: {len(data)} ACC teams for season {args.season}; one CBBD request")

if __name__ == "__main__":
    main()
