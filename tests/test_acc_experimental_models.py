import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_experimental_models import shooting_rates,attach_experiments,ROTATION,SHOOTING
from research_engine import CURRENT_MODEL_VERSION

class TestExperiments(unittest.TestCase):
    def player(self,i,dates,m=30):
        logs=[dict(date=d,minutes=m,points=16,fgm=6,fga=12,three_pm=2,three_pa=5,ftm=2,fta=2,reb=5,assists=2,starter=True) for d in dates]
        return dict(Player='Player '+str(i),AthleteId=str(i),ModelVersion=CURRENT_MODEL_VERSION,Minutes=m,CurrentTeamGames=3,CurrentSeasonLog=logs,BaselinePoints=16,KenPomPoints=16,BaselineThrees=2,KenPomThrees=2,BaselineRebounds=5,KenPomRebounds=5,BaselineAssists=2,KenPomAssists=2,PaceFactor=1,OpponentDefenseFactor=1)
    def test_rotation_and_shooting(self):
        dates=['2026-11-21','2026-11-20','2026-11-19']
        players=[self.player(i,dates) for i in range(7)]+[self.player(7,dates[-1:],15)]
        before=copy.deepcopy(players);out=attach_experiments(players)
        self.assertEqual(players,before)
        for version in (ROTATION,SHOOTING):
            self.assertEqual(sum(round(p['ExperimentalModels'][version]['Minutes']*10) for p in out),2000)
        bench=out[-1]['ExperimentalModels'][ROTATION]
        self.assertEqual(bench['RotationInputs']['participation_rate'],1/3)
        self.assertLess(bench['Minutes'],out[0]['ExperimentalModels'][ROTATION]['Minutes'])
        shot=out[0]['ExperimentalModels'][SHOOTING]
        self.assertEqual(shot['ShotStatus'],'modeled')
        self.assertTrue(0<shot['ShotInputs']['components']['3P']['expected_pct']<.4)
        self.assertEqual(out[0]['KenPomPoints'],16)
        self.assertTrue(all(not p['ExperimentalModels'] for p in attach_experiments(players[:4])))
    def test_invalid_shots(self):
        p=self.player(1,['2026-11-21'])
        self.assertIsNotNone(shooting_rates(p['CurrentSeasonLog']))
        p['CurrentSeasonLog'][0]['points']=99
        self.assertIsNone(shooting_rates(p['CurrentSeasonLog']))

    def test_paired_grade(self):
        from acc_model_comparison import compare
        date='2026-11-25';stamp=date+'T16:00:00Z';tip=date+'T20:00:00Z';gid='espn_event_1'
        p=self.player(1,['2026-11-21']);p['ExperimentalModels']={ROTATION:{'ModelVersion':ROTATION,'Minutes':28,'KenPomPoints':18}}
        r={'date_eastern':date,'captured_at_utc':stamp,'projection_utc':stamp,'odds_snapshot_utc':None,'game':{'game_id':gid,'tipoff_utc':tip,'teams':[{'team':'Duke','players':[p]}]},'quotes':[]}
        logs={'espn_1':[{'game_date':date,'source':'ESPN_UNOFFICIAL','team':'Duke Blue Devils','player':'Player 1','points':'18','minutes':'28'}]}
        result=compare([r],logs,'2026-11-26')['models'][ROTATION]
        self.assertEqual(result['paired_players'],1)
        self.assertEqual(result['projection_metrics']['Points']['control']['mae'],2)
        self.assertEqual(result['projection_metrics']['Points']['experimental']['mae'],0)
        self.assertEqual(compare([r],logs,date)['models'][ROTATION]['paired_players'],0)
