import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_availability import allocate_fixed,attach_availability,VERSION

class AvailabilityTests(unittest.TestCase):
    def test_exact_fixed_minutes(self):
        a=allocate_fixed([20,35,35,30,30,25,25],{0:29})
        self.assertEqual(a[0],29)
        self.assertEqual(sum(round(v*10) for v in a),2000)
        self.assertTrue(all(0<=v<=40 for v in a))
        with self.assertRaises(ValueError):allocate_fixed([20]*5,{0:0})
    def test_exclusion_and_control_preserved(self):
        logs=[{'date':'2026-11-24','minutes':29,'points':11},{'date':'2026-11-13','minutes':8,'points':0},{'date':'2026-11-10','minutes':18,'points':16},{'date':'2026-11-07','minutes':23,'points':12},{'date':'2026-11-02','minutes':23,'points':5}]
        ps=[{'AthleteId':str(i),'Minutes':m,'BaselinePoints':8,'KenPomPoints':8,'PaceFactor':1,'OpponentDefenseFactor':1,'CurrentSeasonLog':logs,'CurrentTeamGames':7,'ExperimentalModels':{'v5':{'Minutes':20}}} for i,m in enumerate([18.4,31,30,30,30,30,30.6])]
        before=copy.deepcopy(ps)
        out=attach_availability(ps,[{'game_id':'g','team':'Miami','athlete_id':'0','minutes':29,'status':'returning','reason':'scenario','exclude_dates':['2026-11-13']}],'g','Miami')
        self.assertEqual(ps,before)
        self.assertEqual(out[0]['Minutes'],18.4)
        self.assertAlmostEqual(out[0]['ExperimentalModels'][VERSION]['KenPomPoints'],29*44/93)
        self.assertEqual(out[0]['ExperimentalModels'][VERSION]['ProductionGamesUsed'],4)
        self.assertEqual(sum(round(p['ExperimentalModels'][VERSION]['Minutes']*10) for p in out),2000)
        self.assertTrue(out[0]['MinutesRiskFlags'])
