"""Offline health-audit tests; no token, network or paid sportsbook calls."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from acc_pipeline_health import audit

NOW = dt.datetime(2026, 11, 23, 20, 0, tzinfo=dt.timezone.utc)
RUNS = {key: {'conclusion': 'success'} for key in ('espn', 'grading', 'projections', 'odds', 'pages')}


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put('data/espn/collector_status.json', {'status': 'OK', 'checked_at_utc': '2026-11-23T12:30:00Z', 'total_player_rows': 5000})
        self.put('data/archives/daily/2026-11-22.json', {'date_eastern': '2026-11-22', 'generated_at_utc': '2026-11-22T13:00:00Z', 'games': [{'tipoff_utc': '2026-11-22T20:00:00Z'}]})
        self.put('data/archives/daily/2026-11-23.json', {'date_eastern': '2026-11-23', 'generated_at_utc': '2026-11-23T13:00:00Z', 'games': [{'tipoff_utc': '2026-11-23T23:00:00Z', 'teams': [{'team': 'Duke', 'players': [{'Player': 'Example'}]}]}]})
        self.put('data/daily_grading.json', {'status': 'PARTIAL', 'players_graded': 10, 'issues': [{'reason': 'not_matched'}], 'days': [{'date': '2026-11-22'}]})
        self.put('data/daily_board.json', {'date_eastern': '2026-11-23', 'game_count': 1, 'projection_player_rows': 8, 'games': [{'teams': [{'team': 'Duke', 'players': [{'Player': 'Example'}]}]}]})
        self.put('data/daily_odds_evaluation.json', {'quotes_offered': 2, 'settled': 0, 'roi_percent': None, 'days': [{'date': '2026-11-22'}]})
        self.put('data/odds_snapshots/2026-11-22.json', {'daily_credit_cap': 24, 'monthly_reserve_credits': 50, 'quota': {'credits_spent_reported': 4, 'remaining': 394}})

    def put(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data))

    def checks(self):
        return {c['code']: c for c in audit(self.root, NOW, RUNS)['checks']}

    def test_partial_grading_is_warning_not_failure(self):
        report = audit(self.root, NOW, RUNS)
        self.assertEqual(report['failures'], 0)
        self.assertEqual(self.checks()['grading']['level'], 'warn')
        self.assertEqual(self.checks()['roi']['level'], 'warn')

    def test_archive_post_tipoff_is_failure(self):
        path = 'data/archives/daily/2026-11-22.json'
        data = json.loads((self.root / path).read_text())
        data['generated_at_utc'] = '2026-11-22T21:00:00Z'
        self.put(path, data)
        self.assertEqual(self.checks()['archives']['level'], 'fail')

    def test_api_credit_cap_and_reserve_breaches_fail(self):
        self.put('data/odds_snapshots/2026-11-22.json', {'daily_credit_cap': 24, 'monthly_reserve_credits': 50, 'quota': {'credits_spent_reported': 25, 'remaining': 49}})
        self.assertEqual(self.checks()['api_credits']['level'], 'fail')

    def test_stale_board_and_failed_workflow_fail(self):
        self.put('data/daily_board.json', {'date_eastern': '2026-11-22', 'games': []})
        runs = {**RUNS, 'pages': {'conclusion': 'failure'}}
        checks = {c['code']: c for c in audit(self.root, NOW, runs)['checks']}
        self.assertEqual(checks['projections']['level'], 'fail')
        self.assertEqual(checks['workflow_pages']['level'], 'fail')

    def test_empty_team_projections_warn(self):
        self.put('data/daily_board.json', {'date_eastern': '2026-11-23', 'games': [{'teams': [{'team': 'Boston College', 'players': []}]}]})
        self.assertEqual(self.checks()['projections']['level'], 'warn')


if __name__ == '__main__':
    unittest.main()
