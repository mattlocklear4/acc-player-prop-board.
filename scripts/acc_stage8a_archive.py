#!/usr/bin/env python3
"""Stage 8A: validate a morning projection artifact and optionally archive it.

Default: PREVIEW ONLY. Database writes require both --commit and
ACC_ARCHIVE_WRITES_ENABLED=true. No updates/deletes, no retroactive writes.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STATS = ('Points', 'Rebounds', 'Assists', 'Threes')
MODELS = ('Baseline', 'KenPom', 'Vegas', 'Combined')
MODEL_VERSION = 'acc-v2.3-stage8a-morning-default-minutes'


def parse_time(s):
    if not isinstance(s, str):
        raise ValueError('Missing timestamp')
    dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timezone required')
    return dt.astimezone(timezone.utc)


def build_rows(payload, now):
    if payload.get('mode') != 'DRY_RUN_NO_WRITES':
        raise ValueError('Unexpected diagnostic mode')
    if payload.get('manual_minutes_overrides_applied') is not False:
        raise ValueError('Unexpected minutes provenance')
    meta = payload.get('kenpom_source') or {}
    if meta.get('source') != 'supabase_snapshot' or not meta.get('snapshot_id'):
        raise ValueError('Only verified Supabase snapshot IDs accepted')
    generated = parse_time(payload['generated_at_utc'])
    if generated > now or now - generated > __import__('datetime').timedelta(hours=3):
        raise ValueError('Diagnostic is future-dated or older than 3 hours')
    rows = []
    for game in payload.get('games') or []:
        tip = parse_time(game['tipoff_utc'])
        if generated >= tip or now >= tip:
            continue  # Never archive projections after tipoff.
        for team in game.get('teams') or []:
            if team.get('status') != 'research_candidate_unverified':
                continue
            if team.get('kenpom_snapshot_id') != meta['snapshot_id']:
                raise ValueError('KenPom snapshot mismatch')
            for player in team.get('players') or []:
                pid = str(player.get('AthleteId') or '').strip()
                name = str(player.get('Player') or '').strip()
                if not pid or not name or not player.get('Team'):
                    raise ValueError('Missing player identity')
                baseline = {s: player.get('Baseline' + s) for s in STATS}
                if any(v is None or not isinstance(v, (int, float)) or v < 0 for v in baseline.values()):
                    continue  # No invented stats; exclude incomplete players.
                adjusted = {model: {s: player.get(model + s) for s in STATS} for model in MODELS if model != 'Baseline'}
                # None means missing odds/model, not zero.
                rows.append({
                    'game_id': str(game['game_id']), 'game_start_at': tip.isoformat(),
                    'season': 2027, 'team': team['team'], 'opponent': team['opponent'],
                    'player_id': pid, 'player_name': name,
                    'model_version': MODEL_VERSION, 'kenpom_snapshot_id': meta['snapshot_id'],
                    'baseline': baseline, 'adjusted': adjusted,
                    'assumptions': {
                        'snapshot_type': 'morning', 'generated_at_utc': generated.isoformat(),
                        'minutes': player.get('Minutes'), 'manual_minutes_overrides_applied': False,
                        'odds_status': team.get('odds_status'),
                        'kenpom_imported_at': meta.get('imported_at'),
                        'projection_status': team['status'],
                        'model_verification': 'controlled_tests_only',
                        'market_odds': team.get('odds'),
                    },
                })
    ids = [(r['game_id'], r['team'], r['player_id']) for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate players within a single archive batch')
    return rows


def request_json(url, key, method='GET', data=None):
    body = json.dumps(data).encode('utf-8') if data is not None else None
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
    if body is not None:
        headers.update({'Content-Type': 'application/json', 'Prefer': 'return=minimal'})
    req = Request(url, data=body, headers=headers, method=method)
    with urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, default=Path('research/acc_projection_dry_run.json'))
    p.add_argument('--output', type=Path, default=Path('research/acc_stage8a_archive_preview.json'))
    p.add_argument('--commit', action='store_true', help='Requires ACC_ARCHIVE_WRITES_ENABLED=true')
    a = p.parse_args()
    now = datetime.now(timezone.utc)
    rows = build_rows(json.loads(a.input.read_text()), now)
    summary = {'mode': 'PREVIEW_NO_WRITES', 'generated_at_utc': now.isoformat(),
               'candidate_rows': len(rows), 'sample': rows[:2], 'saved': 0,
               'warning': 'Research projections, default minutes; not verified live-odds or manual overrides.'}
    if a.commit:
        if os.getenv('ACC_ARCHIVE_WRITES_ENABLED') != 'true':
            raise RuntimeError('Archive writes disabled; set ACC_ARCHIVE_WRITES_ENABLED=true explicitly')
        url = os.environ['SUPABASE_URL'].rstrip('/')
        key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
        if not url.startswith('https://') or not key:
            raise ValueError('Missing Supabase credentials')
        # Confirm ownership from the saved KenPom snapshot, not a guessed user ID.
        snapshot_id = (json.loads(a.input.read_text()).get('kenpom_source') or {}).get('snapshot_id')
        owners = request_json(url + '/rest/v1/acc_kenpom_snapshots?' + urlencode({
            'select': 'id,user_id', 'id': 'eq.' + snapshot_id, 'limit': '2'}), key)
        if not owners or len(owners) != 1 or not owners[0].get('user_id'):
            raise ValueError('Cannot resolve unique KenPom snapshot owner')
        user_id = owners[0]['user_id']
        saved = skipped = 0
        for row in rows:
            params = {'select': 'id', 'user_id': 'eq.' + user_id,
                      'game_id': 'eq.' + row['game_id'], 'player_id': 'eq.' + row['player_id'],
                      'team': 'eq.' + row['team'], 'model_version': 'eq.' + MODEL_VERSION, 'limit': '1'}
            existing = request_json(url + '/rest/v1/acc_pregame_projections?' + urlencode(params), key)
            if existing:
                skipped += 1
                continue
            request_json(url + '/rest/v1/acc_pregame_projections', key, 'POST', [{**row, 'user_id': user_id}])
            saved += 1
        summary.update(mode='COMMITTED_INSERT_ONLY', saved=saved, skipped_existing=skipped)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k:v for k,v in summary.items() if k != 'sample'}))

if __name__ == '__main__':
    main()
