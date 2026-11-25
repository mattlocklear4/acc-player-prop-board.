"""Regression tests for short-name KenPom opponent resolution and grading fields."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from supabase_kenpom import resolve_opponent
from research_engine import canon
from acc_merge_game_logs import merge_current_games

class OpponentTests(unittest.TestCase):
    def test_njit_mascot(self):
        kp={canon('NJIT'):{'Team':'NJIT'}}
        self.assertEqual(resolve_opponent('NJIT Highlanders',kp),'NJIT')
    def test_unknown_is_not_guessed(self):
        kp={canon('NJIT'):{'Team':'NJIT'}}
        self.assertIsNone(resolve_opponent('Other Highlanders',kp))
    def test_long_school_name(self):
        kp={canon('Boston College'):{'Team':'Boston College'}}
        self.assertEqual(resolve_opponent('Boston College Eagles',kp),'Boston College')

    def test_ole_miss_kenpom_name(self):
        kp={canon('Mississippi'):{'Team':'Mississippi'}, canon('Mississippi State'):{'Team':'Mississippi State'}}
        self.assertEqual(resolve_opponent('Ole Miss Rebels',kp),'Mississippi')
        self.assertEqual(resolve_opponent('Mississippi Rebels',kp),'Mississippi')

    def test_uconn_and_ualbany_aliases(self):
        kp={canon('Connecticut'):{'Team':'Connecticut'},
            canon('Central Connecticut'):{'Team':'Central Connecticut'},
            canon('Albany'):{'Team':'Albany'}}
        self.assertEqual(resolve_opponent('UConn Huskies',kp),'Connecticut')
        self.assertEqual(resolve_opponent('UConn',kp),'Connecticut')
        self.assertEqual(resolve_opponent('UAlbany Great Danes',kp),'Albany')
        self.assertEqual(resolve_opponent('UAlbany',kp),'Albany')
        self.assertIsNone(resolve_opponent('Other Huskies',kp))

class HybridTests(unittest.TestCase):
    def test_dedup_id_mapping_and_date_cutoff(self):
        common=dict(season='2027',team='Wake Forest',opponent='Vanderbilt',player='Kevair Kennedy',
                    minutes='30',points='12',reb='5',assists='3',three_pm='1')
        c={**common,'game_id':'123','game_date':'2026-11-05','athlete_id':'200461','athlete_source_id':'5314298'}
        e={**common,'source':'ESPN_UNOFFICIAL','team':'Wake Forest Demon Deacons',
           'opponent':'Vanderbilt Commodores','game_id':'espn_123','game_date':'2026-11-05','athlete_id':'5314298'}
        newer={**e,'game_id':'espn_456','game_date':'2026-11-21','opponent':'Western Carolina Catamounts','reb':'3'}
        future={**newer,'game_id':'espn_789','game_date':'2026-11-25'}
        nonacc={**newer,'team':'Miami (OH) RedHawks'}
        rows,issues,coverage=merge_current_games([c],[e,newer,future,nonacc],'2026-11-25')
        self.assertEqual(len(rows),2)
        self.assertEqual([r['athlete_id'] for r in rows],['200461','200461'])
        self.assertEqual([r['_source'] for r in rows],['CBBD','ESPN'])
        self.assertEqual(coverage['Wake Forest']['merged_games'],2)
        self.assertEqual(issues,{})
    def test_conflicting_stat_retains_primary(self):
        c=dict(season='2027',team='Duke',opponent='Kansas',player='Test Player',
               minutes='30',points='12',reb='5',assists='3',three_pm='1',
               game_id='123',game_date='2026-11-05',athlete_id='200',athlete_source_id='531')
        e={**c,'source':'ESPN_UNOFFICIAL','team':'Duke Blue Devils','opponent':'Kansas Jayhawks',
           'game_id':'espn_123','athlete_id':'531','reb':'7'}
        rows,issues,_=merge_current_games([c],[e],'2026-11-25')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['reb'],'5')
        self.assertIn('discrepancy',issues['Duke'][0])
    def test_ambiguous_crosswalk_not_guessed(self):
        c=dict(season='2027',team='Duke',opponent='Kansas',player='Test Player',
               minutes='30',points='12',reb='5',assists='3',three_pm='1',
               game_id='123',game_date='2026-11-05',athlete_id='200',athlete_source_id='531')
        e={**c,'source':'ESPN_UNOFFICIAL','team':'Duke Blue Devils','opponent':'Iowa Hawkeyes',
           'game_id':'espn_456','game_date':'2026-11-07','athlete_id':'531'}
        rows,issues,_=merge_current_games([c],[e],'2026-11-25',[{**c,'athlete_id':'201'}])
        self.assertEqual(len(rows),1)
        self.assertIn('ambiguous ESPN',issues['Duke'][0])

if __name__=='__main__':unittest.main()
