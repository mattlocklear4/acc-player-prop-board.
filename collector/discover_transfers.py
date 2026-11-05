#!/usr/bin/env python3
"""Discover previous-school player seasons without modifying the live data."""
import csv, json, os, sys, urllib.parse, urllib.request, urllib.error
from collections import defaultdict
from pathlib import Path

ROOT = Path('data/cbbd')
OUT = Path('data/transfer_discovery')
OUT.mkdir(parents=True, exist_ok=True)

def read_csv(season):
    path = ROOT / f'acc_player_games_{season}.csv'
    if not path.exists():
        raise RuntimeError(f'Missing required repository file: {path}')
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def fetch(season):
    key = os.getenv('CBBD_API_KEY')
    if not key:
        raise RuntimeError('CBBD_API_KEY GitHub repository secret is missing')
    url = 'https://api.collegebasketballdata.com/stats/player/season?' + urllib.parse.urlencode({'season': season})
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json', 'User-Agent': 'ACC-Transfer-Discovery/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'CBBD returned HTTP {e.code} for season {season}; do not assume zero players. Check access or filters.') from e
    if not isinstance(payload, list):
        raise RuntimeError(f'Unexpected CBBD response type: {type(payload).__name__}; expected a JSON array')
    print(f'CBBD season {season}: {len(payload)} season-stat objects')
    if payload:
        print('Sample object keys:', sorted(payload[0].keys()))
        (OUT / f'sample_{season}.json').write_text(json.dumps(payload[0], indent=2), encoding='utf-8')
    return payload

def val(d, *keys):
    for k in keys:
        if d.get(k) is not None and str(d[k]).strip():
            return str(d[k]).strip()
    return ''

def main():
    current = read_csv(2027)
    old = read_csv(2025) + read_csv(2026)
    current_by_id = {r['athlete_id']: r for r in current if r.get('athlete_id')}
    old_ids = {r['athlete_id'] for r in old if r.get('athlete_id')}
    print(f'Current players: {len(current_by_id)}; without existing ACC history: {sum(k not in old_ids for k in current_by_id)}')
    matches = defaultdict(list)
    counts = {}
    for season in (2025, 2026):
        data = fetch(season)
        counts[str(season)] = len(data)
        for obj in data:
            if not isinstance(obj, dict):
                continue
            athlete_id = val(obj, 'athleteId', 'playerId', 'athlete_id')
            if athlete_id in current_by_id:
                matches[athlete_id].append({'season': season, 'team': val(obj, 'team', 'school', 'teamName'), 'name': val(obj, 'athlete', 'player', 'name'), 'source': 'CBBD season stats'})
    fields = ['athlete_id','player','current_team','in_existing_acc_history','season_2025_teams','season_2026_teams','status']
    report = []
    for aid, row in sorted(current_by_id.items(), key=lambda x: (x[1]['team'], x[1]['player'])):
        m = matches.get(aid, [])
        t25 = sorted({x['team'] for x in m if x['season'] == 2025 and x['team']})
        t26 = sorted({x['team'] for x in m if x['season'] == 2026 and x['team']})
        has_acc = aid in old_ids
        status = 'Matched in CBBD season stats' if m else 'Not found in CBBD season stats (unresolved)'
        report.append({'athlete_id':aid,'player':row['player'],'current_team':row['team'], 'in_existing_acc_history':str(has_acc).lower(),'season_2025_teams':'; '.join(t25),'season_2026_teams':'; '.join(t26),'status':status})
    with (OUT / 'transfer_discovery_report.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(report)
    summary = {'current_players':len(current_by_id),'already_in_acc_history':sum(k in old_ids for k in current_by_id),'matched_in_season_endpoint':sum(bool(matches.get(k)) for k in current_by_id),'unresolved':sum(not matches.get(k) for k in current_by_id),'api_requests':2,'season_response_counts':counts}
    (OUT / 'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print('Output saved to data/transfer_discovery/ (artifact only; no repository commit)')

if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('ERROR:',e,file=sys.stderr); sys.exit(1)
