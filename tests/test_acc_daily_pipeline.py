"""Regression tests for short-name KenPom opponent resolution and grading fields."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from supabase_kenpom import resolve_opponent
from research_engine import canon, allocate_team_minutes, normalize_team_baselines, apply_matchup, CURRENT_MODEL_VERSION
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

class RegulationMinutesTests(unittest.TestCase):
    def check_rotation(self, raw):
        allocated=allocate_team_minutes(raw)
        self.assertEqual(sum(round(x*10) for x in allocated),2000)
        self.assertTrue(all(0<=x<=40 for x in allocated))
        self.assertTrue(all(x==round(x,1) for x in allocated))
        self.assertTrue(all(x==0 for r,x in zip(raw,allocated) if r==0))
        return allocated

    def test_reduce_and_increase(self):
        self.check_rotation([35,34,33,30,25,22,18,15,8])
        self.check_rotation([31,29,24,20,18,15,12,6,0])

    def test_capped_redistribution_and_exact_five(self):
        a=self.check_rotation([40,39,32,20,15,10,1,0])
        self.assertEqual(a[0],40)
        self.assertEqual(a[1],40)
        self.assertEqual(self.check_rotation([35,31,21,11,1,0]),[40,40,40,40,40,0])

    def test_insufficient_rotation_fails_closed(self):
        for raw in ([40,39,25,10,0],[],[40,39,30,25,float('nan')]):
            with self.assertRaises(ValueError):allocate_team_minutes(raw)

    def test_stat_scaling_and_version(self):
        raw=[34,32,29,27,24,22,18,15,9]
        rows=[{'Player':str(i),'Team':'Duke','Minutes':m,'BaselinePoints':m*.5,
               'BaselineRebounds':m*.2,'BaselineAssists':m*.1,'BaselineThrees':None} for i,m in enumerate(raw)]
        result=normalize_team_baselines(rows)
        self.assertEqual(sum(round(p['Minutes']*10) for p in result),2000)
        for old,p in zip(rows,result):
            self.assertEqual(p['RawMinutes'],old['Minutes'])
            self.assertEqual(p['ModelVersion'],CURRENT_MODEL_VERSION)
            self.assertAlmostEqual(p['BaselinePoints'],p['Minutes']*.5)
            self.assertAlmostEqual(p['BaselineRebounds'],p['Minutes']*.2)
            self.assertAlmostEqual(p['BaselineAssists'],p['Minutes']*.1)
            self.assertIsNone(p['BaselineThrees'])
            self.assertEqual(old['Minutes'],p['RawMinutes'])
        kp={'duke':{'AdjT':70,'AdjO':110,'AdjD':100},'opponent':{'AdjT':70,'AdjO':100,'AdjD':105}}
        projected=apply_matchup(result,'Duke','Opponent',kp)
        self.assertEqual(sum(round(p['Minutes']*10) for p in projected),2000)
        self.assertAlmostEqual(sum(p['KenPomPoints'] for p in projected),100)
        with self.assertRaises(ValueError):
            apply_matchup([{**rows[0],'MinutesNormalizationStatus':'unavailable'}],'Duke','Opponent',kp)

if __name__=='__main__':unittest.main()
