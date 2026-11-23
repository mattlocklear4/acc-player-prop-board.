"""Read-only daily operational audit. Never calls a sportsbook or changes archives."""
import argparse
import datetime as dt
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
EASTERN = ZoneInfo('America/New_York')
WORKFLOWS = {
    'espn': 'acc-espn-collector.yml',
    'grading': 'acc-daily-grading.yml',
    'projections': 'acc-daily-projections.yml',
    'odds': 'acc-daily-odds.yml',
    'pages': 'deploy-pages.yml',
}


def read_json(root, relative):
    path = root / relative
    return json.loads(path.read_text()) if path.is_file() else None


def timestamp(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def run_history(repo, token):
    """Read the latest real Actions conclusions; never dispatch a workflow."""
    if not token or not repo:
        return {}
    results = {}
    for key, filename in WORKFLOWS.items():
        url = f'https://api.github.com/repos/{repo}/actions/workflows/{filename}/runs?per_page=10&branch=main'
        request = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
            'User-Agent': 'acc-pipeline-health',
        })
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                runs = json.load(response).get('workflow_runs', [])
            # A current workflow may be queued; report that without hiding its last completed run.
            completed = next((r for r in runs if r.get('status') == 'completed'), None)
            results[key] = {
                'conclusion': completed.get('conclusion') if completed else None,
                'completed_at': completed.get('updated_at') if completed else None,
                'url': completed.get('html_url') if completed else None,
                'latest_status': runs[0].get('status') if runs else 'missing',
            }
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            results[key] = {'error': str(exc)}
    return results


def audit(root=ROOT, now=None, workflow_runs=None, check_git=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(EASTERN).date()
    yesterday = today - dt.timedelta(days=1)
    checks = []

    def add(code, level, detail, **extra):
        checks.append({'code': code, 'level': level, 'detail': detail, **extra})

    espn = read_json(root, 'data/espn/collector_status.json')
    age = (now - timestamp(espn.get('checked_at_utc'))).total_seconds() / 3600 if espn and timestamp(espn.get('checked_at_utc')) else None
    if not espn or age is None or age > 36 or espn.get('status') != 'OK':
        add('espn', 'fail', f'ESPN status missing, unhealthy, or older than 36h (age={age}).')
    else:
        add('espn', 'pass', f"ESPN collector OK {age:.1f}h ago; {espn.get('total_player_rows', 0)} player rows.")

    archives = sorted((root / 'data/archives/daily').glob('*.json'))
    invalid = []
    revisions = []
    archived_dates = []
    for archive in archives:
        try:
            data = json.loads(archive.read_text())
            date = dt.date.fromisoformat(archive.stem)
            archived_dates.append(date.isoformat())
            snapshot = timestamp(data.get('generated_at_utc'))
            if data.get('date_eastern') != archive.stem or snapshot is None:
                invalid.append(archive.name + ': invalid date or timestamp')
            for game in data.get('games', []):
                tip = timestamp(game.get('tipoff_utc'))
                if tip is None or snapshot is None or snapshot >= tip:
                    invalid.append(archive.name + ': archive not before tipoff')
            if check_git:
                result = subprocess.run(['git', 'log', '--format=%H', '--', str(archive.relative_to(root))],
                                        cwd=root, capture_output=True, text=True, check=True)
                if len(result.stdout.splitlines()) > 1:
                    revisions.append(archive.name)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
            invalid.append(archive.name + ': ' + str(exc))
    if invalid or revisions:
        add('archives', 'fail', f'Archive integrity failures: {invalid}; modified historical paths: {revisions}.')
    elif not archives:
        add('archives', 'fail', 'No immutable pregame archives found.')
    else:
        add('archives', 'pass', f'{len(archives)} pregame archive dates checked; no post-tipoff timestamps or revisions detected.')

    grading = read_json(root, 'data/daily_grading.json')
    grade_dates = {x.get('date') for x in (grading or {}).get('days', [])}
    if not grading or str(grading.get('status', '')).upper() not in ('OK', 'PARTIAL'):
        add('grading', 'fail', 'Daily grading report missing or not OK.')
    elif yesterday.isoformat() in archived_dates and yesterday.isoformat() not in grade_dates:
        add('grading', 'fail', f'Archived {yesterday} has not appeared in grading coverage.')
    else:
        issues = len(grading.get('issues', []))
        add('grading', 'warn' if issues else 'pass',
            f"{grading.get('players_graded', 0)} players graded; {issues} unresolved matching issues.")

    board = read_json(root, 'data/daily_board.json')
    if not board or board.get('date_eastern') != today.isoformat():
        add('projections', 'fail', f"Today's board missing/stale; found {(board or {}).get('date_eastern')} instead of {today}.")
    else:
        missing = [t.get('team') for g in board.get('games', []) for t in g.get('teams', []) if not t.get('players')]
        if missing:
            add('projections', 'warn', f"{len(missing)} listed ACC teams lack player projections: {', '.join(missing)}.")
        else:
            add('projections', 'pass', f"{board.get('game_count', 0)} scheduled games; {board.get('projection_player_rows', 0)} player projections.")
        if board.get('games') and today.isoformat() not in archived_dates:
            add('today_archive', 'fail', 'Today has projected games but no saved immutable pregame archive.')
        elif today.isoformat() in archived_dates:
            archived_today = read_json(root, f'data/archives/daily/{today}.json')
            archived_players = sum(len(t.get('players') or []) for g in (archived_today or {}).get('games', []) for t in g.get('teams', []))
            if archived_players < board.get('projection_player_rows', 0):
                add('today_archive_coverage', 'warn', f'Immutable first snapshot has {archived_players} players vs live board {board.get("projection_player_rows", 0)}; later additions cannot be graded retrospectively.')

    odds = read_json(root, 'data/daily_odds_evaluation.json')
    odds_dates = {x.get('date') for x in (odds or {}).get('days', [])}
    if not odds:
        add('roi', 'fail', 'Historical odds evaluation missing.')
    else:
        add('roi', 'pass' if odds.get('settled', 0) else 'warn',
            f"{odds.get('quotes_offered', 0)} actual saved quotes, {odds.get('settled', 0)} settled selections; ROI={odds.get('roi_percent')} (no inferred odds).")
        if yesterday.isoformat() in archived_dates and yesterday.isoformat() not in odds_dates:
            add('odds_coverage', 'warn', f'No odds evaluation coverage row for {yesterday}.')

    snapshot_paths = sorted((root / 'data/odds_snapshots').glob('*.json'))
    if board and board.get('date_eastern') == today.isoformat() and board.get('games'):
        if not (root / f'data/odds_snapshots/{today}.json').exists():
            add('today_odds_snapshot', 'warn', 'No immutable sportsbook snapshot for today; check scheduled collection and quota gate.')
    quota_violations = []
    for path in snapshot_paths:
        try:
            snapshot = json.loads(path.read_text())
            quota = snapshot.get('quota') or {}
            if snapshot.get('daily_credit_cap') != 24 or snapshot.get('monthly_reserve_credits') != 50:
                quota_violations.append(path.name + ': declared cap mismatch')
            spent = quota.get('credits_spent_reported')
            remaining = quota.get('remaining')
            if isinstance(spent, (int, float)) and spent > 24:
                quota_violations.append(path.name + ': spent above daily cap')
            if isinstance(remaining, (int, float)) and remaining < 50:
                quota_violations.append(path.name + ': reserve below 50')
        except (OSError, ValueError) as exc:
            quota_violations.append(path.name + ': ' + str(exc))
    if quota_violations:
        add('api_credits', 'fail', '; '.join(quota_violations))
    else:
        add('api_credits', 'pass' if snapshot_paths else 'warn',
            f'{len(snapshot_paths)} stored snapshots checked for 24/day cap and 50-credit reserve; no paid calls made by health check.')

    runs = workflow_runs if workflow_runs is not None else {}
    for name in ('espn', 'grading', 'projections', 'odds', 'pages'):
        item = runs.get(name)
        if item is None:
            add('workflow_' + name, 'warn', 'GitHub workflow status not available (offline audit).')
        elif item.get('error'):
            add('workflow_' + name, 'fail', 'Unable to inspect GitHub Actions: ' + item['error'])
        elif item.get('conclusion') != 'success':
            add('workflow_' + name, 'fail', f"Last completed {name} run: {item.get('conclusion') or 'none'}.", url=item.get('url'))
        else:
            add('workflow_' + name, 'pass', 'Last completed run succeeded.', url=item.get('url'))

    failures = sum(c['level'] == 'fail' for c in checks)
    warnings = sum(c['level'] == 'warn' for c in checks)
    return {
        'generated_at_utc': now.isoformat(), 'date_eastern': today.isoformat(),
        'status': 'fail' if failures else 'warn' if warnings else 'pass',
        'failures': failures, 'warnings': warnings, 'checks': checks,
        'note': 'Read-only diagnostic; workflow success alone does not prove ongoing unattended reliability.',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='data/pipeline_health.json')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if not args.offline and (not os.getenv('GITHUB_REPOSITORY') or not os.getenv('GITHUB_TOKEN')):
        raise SystemExit('GITHUB_REPOSITORY and GITHUB_TOKEN required for scheduled workflow audit')
    runs = {} if args.offline else run_history(os.getenv('GITHUB_REPOSITORY'), os.getenv('GITHUB_TOKEN'))
    report = audit(workflow_runs=runs, check_git=not args.offline)
    destination = ROOT / args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'failures': report['failures'], 'warnings': report['warnings']}))
    for check in report['checks']:
        print(check['level'].upper(), check['code'], check['detail'])
    if report['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
