import sys,unittest,copy,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_distribution_model import distribution,attach_distributions,VERSION,shot_variance
from acc_experimental_models import SHOOTING
class DistributionTests(unittest.TestCase):
    def test_low_sample_prior(self):
        d=distribution([{'minutes':30,'points':1}],'Points','points',12.,30.)
        self.assertEqual(d['status'],'prior_only')
        self.assertAlmostEqual(d['sd'],5.5)
        self.assertEqual(d['mean'],12.)
    def test_volatility_changes_variance(self):
        stable=[{'minutes':30,'points':x} for x in [11,12,13,11,12,13,12]]
        volatile=[{'minutes':30,'points':x} for x in [1,23,2,22,3,21,12]]
        a=distribution(stable,'Points','points',12.,30.)
        b=distribution(volatile,'Points','points',12.,30.)
        self.assertGreater(b['variance'],a['variance'])
        self.assertEqual(a['mean'],b['mean'])
        self.assertGreaterEqual(a['variance'],12.)
        self.assertEqual(b['family'],'negative_binomial')
    def test_minutes_volatility(self):
        stable=[{'minutes':30,'points':12} for _ in range(6)]
        volatile=[{'minutes':m,'points':m*.4} for m in [10,40,20,40,10,40]]
        a=distribution(stable,'Points','points',12.,30.)
        b=distribution(volatile,'Points','points',12.,30.)
        self.assertGreater(b['minute_variance_component'],a['minute_variance_component'])
    def test_missing_and_zero(self):
        self.assertIsNone(distribution([], 'Points','points',None,30))
        d=distribution([], 'Threes','three_pm',0,30)
        self.assertEqual(d['variance'],0)
    def test_shot_variance(self):
        logs=[{'minutes':30,'fga':x,'three_pa':3,'fta':4} for x in [8,12,9,13]]
        shot={'components':{k:{'expected_pct':v} for k,v in [('2P',.5),('3P',.34),('FT',.75)]},'projected_attempts':{'2P':8,'3P':3,'FT':4}}
        v=shot_variance(logs,shot,30,30)
        self.assertGreater(v['volume_variance'],0)
        self.assertGreater(v['conversion_variance'],0)
    def test_same_means_and_minutes(self):
        ps=[{'AthleteId':str(i),'CurrentSeasonLog':[{'minutes':40,'points':12,'reb':5,'assists':2,'three_pm':1}]*5,'ExperimentalModels':{SHOOTING:{'Minutes':40,'KenPomPoints':12.,'KenPomRebounds':5.,'KenPomAssists':2.,'KenPomThrees':1.}}} for i in range(5)]
        before=copy.deepcopy(ps);out=attach_distributions(ps)
        self.assertEqual(before,ps)
        self.assertEqual(sum(p['ExperimentalModels'][VERSION]['Minutes'] for p in out),200)
        for p in out:
            for k in ('Points','Rebounds','Assists','Threes'):
                self.assertEqual(p['ExperimentalModels'][VERSION]['KenPom'+k],p['ExperimentalModels'][SHOOTING]['KenPom'+k])
                self.assertEqual(p['ExperimentalModels'][VERSION]['Distributions'][k]['mean'],p['ExperimentalModels'][SHOOTING]['KenPom'+k])
