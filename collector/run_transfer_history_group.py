#!/usr/bin/env python3
"""Run a bounded group of transfer-history jobs and combine their CSV outputs."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

from collect_cbbd import FIELDS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offset', type=int, required=True)
    parser.add_argument('--count', type=int, required=True)
    args = parser.parse_args()
    if args.offset < 0 or not 1 <= args.count <= 40:
        parser.error('offset must be >= 0; count must be between 1 and 40')
    out = Path('data/cbbd/transfer_history')
    out.mkdir(parents=True, exist_ok=True)
    merged = {}
    summaries = []
    failures = []
    for start in range(args.offset, args.offset + args.count, 12):
        limit = min(12, args.offset + args.count - start)
        cmd = [sys.executable, 'collector/collect_transfer_history.py', '--offset', str(start), '--limit', str(limit)]
        print('Running:', ' '.join(cmd), flush=True)
        result = subprocess.run(cmd, check=False)
        summary_path = out / f'transfer_summary_offset_{start:03d}.json'
        csv_path = out / f'transfer_player_games_offset_{start:03d}.csv'
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            summaries.append(summary)
            failures.extend(summary.get('failures', []))
        if csv_path.exists():
            with csv_path.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    key = (row['season'], row['game_id'], row['team_id'] or row['team'], row['athlete_id'])
                    merged[key] = row
        if result.returncode != 0:
            failures.append(f'Batch starting at {start} exited with code {result.returncode}')
            break
    destination = out / f'transfer_group_{args.offset:03d}_{args.count:02d}.csv'
    with destination.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(merged.values(), key=lambda r: (r['season'], r['game_date'], r['game_id'], r['player'])))
    report = {'offset': args.offset, 'requested_jobs': args.count, 'processed_jobs': sum(len(s['processed']) for s in summaries), 'matched_player_games': len(merged), 'failures': failures, 'batches': summaries}
    (out / f'transfer_group_{args.offset:03d}_{args.count:02d}_summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'batches'}, indent=2))
    if failures:
        sys.exit('Some requests failed. Download the artifact and inspect the group summary; do not skip failed jobs.')
    if report['processed_jobs'] != args.count:
        sys.exit('Unexpected job count; check requested offset/count.')


if __name__ == '__main__':
    main()
