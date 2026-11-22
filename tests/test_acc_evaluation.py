"""No-network regression tests for immutable pregame grading and odds settlement."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_evaluate_odds import evaluate, american_profit
from acc_grade_daily import team_matches
from acc_stage8b_multibook import team_match

class EvaluationTests(unittest.TestCase):
    def test_duke_school_name_matches_espn_nickname_without_guessing(self):
        self.assertTrue(team_matches('Duke','Duke Blue Devils'))
        self.assertFalse(team_matches('Duke','Duquesne Dukes'))
    def test_state_abbreviation_event_matching(self):
        self.assertTrue(team_match('Washington State Cougars','Washington St Cougars'))
        self.assertTrue(team_match('Florida State Seminoles','Florida St Seminoles'))
        self.assertFalse(team_match('Washington State Cougars','Washington Huskies'))
    def setUp(self):
        self.row={'date':'2026-11-21','game_id':'espn_event_123','team':'Boston College',
                  'player':'Example Player','tipoff_utc':'2026-11-21T19:00:00Z',
                  'stats':{'Points':{'projection':16.2,'actual':20}}}
        self.snapshot={'generated_at_utc':'2026-11-21T17:00:00Z',
                       'events':[{'schedule_game_id':'espn_event_123','props':[
                           {'bookmaker':'fanduel','market':'player_points','player':'Example Player',
                            'side':'Over','line':15.5,'odds':-110,'last_update':'2026-11-21T16:55:00Z'},
                           {'bookmaker':'fanduel','market':'player_points','player':'Example Player',
                            'side':'Under','line':15.5,'odds':-110,'last_update':'2026-11-21T16:55:00Z'}]}]}
    def run_eval(self):
        return evaluate({'rows':[self.row]},{'2026-11-21':self.snapshot})
    def test_real_american_odds_and_one_selected_direction(self):
        result=self.run_eval()
        self.assertEqual((result['wins'],result['losses'],result['settled']),(1,0,1))
        self.assertEqual(result['roi_percent'],90.91)
        self.assertEqual(american_profit(-110),round(100/110,6))
    def test_after_tipoff_quote_is_excluded(self):
        self.snapshot['generated_at_utc']='2026-11-21T20:00:00Z'
        self.assertIsNone(self.run_eval()['roi_percent'])
    def test_provider_timestamp_is_required(self):
        self.snapshot['events'][0]['props'][0]['last_update']=None
        self.assertEqual(self.run_eval()['selections'],0)
    def test_missing_results_never_count_as_losses(self):
        self.row['stats']={}
        self.assertEqual(self.run_eval()['settled'],0)
    def test_push_refunds_stake(self):
        self.row['stats']['Points']['actual']=15.5
        result=self.run_eval()
        self.assertEqual((result['pushes'],result['settled'],result['profit_units']),(1,0,0))
    def test_ambiguous_player_refused(self):
        result=evaluate({'rows':[self.row,self.row]},{'2026-11-21':self.snapshot})
        self.assertEqual(result['settled'],0)

if __name__=='__main__':unittest.main()
