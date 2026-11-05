#!/usr/bin/env python3
"""Collect matched previous-school player games in bounded, manual batches."""
import argparse
import csv
import json
import os
from pathlib import Path
import sys
import time

from collect_cbbd import fetch, flatten, FIELDS, TEAMS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', default='data/cbbd/transfer_discovery_report.csv')
    ap.add_argument('--output-dir', default='data/cbbd/transfer_history')
    ap.add_argument('--offset', type=int, default=0)
    ap.add_argument('--limit', type=int, default=12)
    args = ap.parse_args()
    if args.offset < 0 or not 1 <= args.limit <= 20:
        ap.error('offset must be nonnegative; limit must be 1..20')
    key = os.getenv('CBBD_API_KEY', '').strip()
    if not key:
        sys.exit('Missing CBBD_API_KEY')
    with open(args.report, newline='', encoding='utf-8-sig') as f:
        report = list(csv.DictReader(f))
    target = {}
    for r in report:
        athlete = str(r['athlete_id']).strip()
        if not athlete:
            continue
        for season, field in ((2025, 'season_2025_teams'), (2026, 'season_2026_teams')):
            for team in r[field].split('|'):
                team = team.strip()
                if team and team not in TEAMS:
                    target.setdefault((season, team), set()).add(athlete)
    jobs = sorted(target)
    selected = jobs[args.offset:args.offset + args.limit]
    if not selected:
        sys.exit(f'No jobs at offset {args.offset}; total={len(jobs)}')
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_rows = {}
    results = []
    failures = []
    for season, team in selected:
        try:
            games = fetch(team, season, key)
            if games and not any(isinstance(g, dict) and isinstance(g.get('players'), list) for g in games):
                raise ValueError('Unexpected response: no player arrays')
            matched = 0
            for game in games:
                if not isinstance(game, dict) or not isinstance(game.get('players'), list):
                    continue
                for player in game['players']:
                    if not isinstance(player, dict) or str(player.get('athleteId', '')).strip() not in target[(season, team)]:
                        continue
                    row = flatten(game, player)
                    if not row['game_id']:
                        continue
                    k = (str(row['game_id']), str(row['team_id'] or row['team']), str(row['athlete_id']))
                    all_rows[k] = row
                    matched += 1
            results.append({'season': season, 'team': team, 'matched_player_games': matched, 'status': 'ok'})
            print(f'{season} {team}: {matched} matching player-games', flush=True)
        except Exception as exc:
            failures.append(f'{season} {team}: {exc}')
            results.append({'season': season, 'team': team, 'matched_player_games': 0, 'status': 'failed'})
            print(f'ERROR {season} {team}: {exc}', file=sys.stderr, flush=True)
        time.sleep(0.2)
    rows = sorted(all_rows.values(), key=lambda r: (str(r['season']), str(r['game_date']), str(r['game_id']), str(r['player'])))
    dest = out / f'transfer_player_games_offset_{args.offset:03d}.csv'
    with dest.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {'offset': args.offset, 'limit': args.limit, 'total_team_season_jobs': len(jobs), 'processed': results, 'matched_player_games': len(rows), 'failures': failures, 'next_offset': args.offset + len(selected)}
    (out / f'transfer_summary_offset_{args.offset:03d}.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if failures:
        sys.exit('One or more team-season requests failed; inspect summary and retry the batch')


if __name__ == '__main__':
    main()
