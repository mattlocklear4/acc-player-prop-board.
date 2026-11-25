import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_grade_pregame import grade, pending_report

class TestGrade(unittest.TestCase):
    def test_latest_pregame_and_positive_only(self):
        date='2026-11-25';gid='espn_event_1';tip=date+'T20:00:00Z';odds=date+'T16:00:00Z'
        def record(hour,edge,projection):
            stamp=date+f'T{hour}:00:00Z'
            game={'game_id':gid,'tipoff_utc':tip,'teams':[{'team':'Duke','players':[{'Player':'Test Player','KenPomPoints':projection,'ModelVersion':'v2'}]}]}
            q={'game_id':gid,'team':'Duke','player':'Test Player','market':'Points','bookmaker':'fanduel','side':'over','line':14.5,'american_odds':-110,'projection':projection,'model_version':'v2','win_probability':.6,'expected_roi_percent':edge,'projection_utc':stamp,'odds_snapshot_utc':odds,'quote_updated_utc':odds}
            return {'date_eastern':date,'captured_at_utc':stamp,'projection_utc':stamp,'odds_snapshot_utc':odds,'game':game,'quotes':[q]}
        logs={'espn_1':[{'game_date':date,'source':'ESPN_UNOFFICIAL','team':'Duke Blue Devils','player':'Test Player','points':'18'}]}
        a=grade([record('17',-1,14),record('18',12,17),record('21',30,30)],logs,'2026-11-26')
        self.assertEqual(a['players_graded'],1)
        self.assertEqual(a['projection_metrics']['Points']['mae'],1)
        self.assertEqual(a['positive_roi']['wins'],1)
        self.assertEqual(a['by_tier']['10–20%']['settled'],1)
        self.assertAlmostEqual(a['positive_roi']['roi_percent'],90.91)
        self.assertEqual(grade([record('18',12,17)],{},'2026-11-26')['positive_roi']['settled'],0)
        self.assertEqual(grade([record('18',12,17)],logs,date)['quotes_priced'],0)

    def test_pending_matches_next_day_selection(self):
        date='2026-11-25';gid='espn_event_1';tip=date+'T20:00:00Z';odds=date+'T16:00:00Z'
        def rec(hour,edge,version='v4'):
            stamp=date+f'T{hour}:00:00Z'
            q={'game_id':gid,'team':'Duke','player':'Test Player','market':'Points','bookmaker':'fanduel','side':'over','line':14.5,'american_odds':-110,'projection':17,'model_version':version,'win_probability':.6,'expected_roi_percent':edge,'projection_utc':stamp,'odds_snapshot_utc':odds,'quote_updated_utc':odds}
            return {'date_eastern':date,'captured_at_utc':stamp,'projection_utc':stamp,'odds_snapshot_utc':odds,'game':{'game_id':gid,'tipoff_utc':tip,'teams':[{'team':'Duke','players':[{'Player':'Test Player','KenPomPoints':17}]}]},'quotes':[q]}
        old=rec('17',-1,'v3');latest=rec('18',12);invalid=rec('21',99)
        latest['quotes'].append(dict(latest['quotes'][0])) # duplicate must not count
        records=[old,latest,invalid]
        p=pending_report(records,date)
        self.assertEqual(p['games'],1)
        self.assertEqual(p['player_projections'],1)
        self.assertEqual(p['quotes_priced'],1)
        self.assertEqual(p['positive_selections'],1)
        self.assertEqual(p['mean_expected_roi_percent'],12)
        self.assertEqual(p['by_model_version']['v4']['selections'],1)
        self.assertEqual(p['positive_selections'],grade(records,{},'2026-11-26')['positive_roi']['selections'])
        self.assertEqual(grade(records,{},date)['positive_roi']['selections'],0)
        self.assertEqual(pending_report(records,'2026-11-26')['status'],'NO_ARCHIVES')
        self.assertIsNone(pending_report([old],date)['mean_expected_roi_percent'])
