import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_combined_model import attach_combined,VERSION
from acc_rotation_model import VERSION as ROTATION
from acc_opponent_model import VERSION as OPPONENT
from acc_availability import VERSION as AVAILABILITY
from acc_experimental_models import SHOOTING
KEYS=('two_pct','three_pct','two_attempt_rate','three_attempt_rate','ft_attempt_rate','assists_rate','off_miss_rate','def_miss_rate','opp_orb_share','team_orb_share')

class CombinedTests(unittest.TestCase):
    def sample(self):
        league={k:.4 for k in KEYS}
        opp={**league,'games':6,'possessions':420}
        context={'teams':{'michigan':opp},'league':league,'timestamp':'2026-11-26T12:00:00Z','coverage':350}
        ps=[]
        for i in range(6):
            m=[29,35,35,35,35,31][i]
            logs=[{'date':f'2026-11-{j:02d}','minutes':30,'points':12,'reb':6,'assists':3,'three_pm':1,'oreb':2,'dreb':4,'fga':10,'three_pa':3,'fta':4} for j in range(2,8)]
            if i==0:logs.append({'date':'2026-11-13','minutes':8,'points':0,'reb':0,'assists':0,'three_pm':0,'oreb':0,'dreb':0})
            shot={'components':{k:{'expected_pct':v} for k,v in [('2P',.5),('3P',.3),('FT',.75)]},'projected_attempts':{'2P':8*m/29,'3P':4*m/29,'FT':2*m/29}}
            v={'Minutes':m,'BaselinePoints':13.1*m/29,'KenPomPoints':11*m/29,'BaselineThrees':1.2*m/29,'KenPomThrees':1.2*m/29,'BaselineRebounds':6*m/29,'KenPomRebounds':6*m/29,'BaselineAssists':3*m/29,'KenPomAssists':3*m/29,'ShotInputs':shot,'IntelligentRotation':{'v6_minutes':12.5 if i==0 else m,'manual_excluded_games':['2026-11-13'] if i==0 else [],'role_weighted_redistribution':True}}
            p={'AthleteId':str(i),'Minutes':m,'PaceFactor':1.,'CurrentSeasonLog':logs,'ExperimentalModels':{SHOOTING:{'Minutes':12.5,'KenPomPoints':5.1},ROTATION:v,OPPONENT:{'Minutes':12.5,'KenPomPoints':5.0}}}
            if i==0:p['ExperimentalModels'][AVAILABILITY]={'AvailabilityAdjustment':{'status':'returning','minutes':29,'reason':'manual injury exclusion','exclude_dates':['2026-11-13']}}
            ps.append(p)
        return ps,context
    def test_pipeline_preserves_locked_minutes_and_reprices(self):
        ps,c=self.sample();before=copy.deepcopy(ps)
        out=attach_combined(ps,'Michigan',c)
        x=out[0]['ExperimentalModels'][VERSION]
        self.assertEqual(sum(round(p['ExperimentalModels'][VERSION]['Minutes']*10) for p in out),2000)
        self.assertEqual(x['Minutes'],29)
        self.assertAlmostEqual(x['KenPomPoints'],13.1)
        self.assertEqual(x['Distributions']['Points']['mean'],x['KenPomPoints'])
        self.assertEqual(x['Distributions']['Points']['sample'],6)
        self.assertEqual(x['Distributions']['Rebounds']['sample'],6)
        self.assertEqual(x['CombinedModelInputs']['excluded_games'],['2026-11-13'])
        self.assertEqual(x['AvailabilityAdjustment']['minutes'],29)
        self.assertEqual(ps,before)
        self.assertNotIn('_v11_matchup_internal',out[0]['ExperimentalModels'])
    def test_opponent_changes_mean_and_distribution_together(self):
        ps,c=self.sample()
        c['teams']['michigan']['two_pct']=.2
        x=attach_combined(ps,'Michigan',c)[0]['ExperimentalModels'][VERSION]
        self.assertLess(x['KenPomPoints'],13.1)
        self.assertAlmostEqual(x['Distributions']['Points']['mean'],x['KenPomPoints'])
        self.assertEqual(x['Minutes'],29)
    def test_missing_inputs_and_manual_mismatch(self):
        ps,c=self.sample()
        self.assertNotIn(VERSION,attach_combined(ps,'Michigan',None)[0]['ExperimentalModels'])
        ps[0]['ExperimentalModels'].pop(ROTATION)
        self.assertNotIn(VERSION,attach_combined(ps,'Michigan',c)[0]['ExperimentalModels'])
        ps,c=self.sample();ps[0]['ExperimentalModels'][AVAILABILITY]['AvailabilityAdjustment']['minutes']=25
        self.assertEqual(attach_combined(ps,'Michigan',c)[0]['CombinedModelStatus'],'manual_minutes_mismatch')
    def test_out_player(self):
        ps,c=self.sample()
        # Reallocate to 5 remaining players (40 each).
        for i,p in enumerate(ps):
            v=p['ExperimentalModels'][ROTATION];v['Minutes']=0 if i==0 else 40
            if i==0:
                for k in ('BaselinePoints','BaselineRebounds','BaselineAssists','BaselineThrees','KenPomPoints','KenPomRebounds','KenPomAssists','KenPomThrees'):v[k]=0
                v['ShotInputs']['projected_attempts']={'2P':0,'3P':0,'FT':0}
        ps[0]['ExperimentalModels'][AVAILABILITY]['AvailabilityAdjustment'].update(minutes=0,status='out')
        x=attach_combined(ps,'Michigan',c)[0]['ExperimentalModels'][VERSION]
        self.assertEqual(x['CombinedModelInputs']['pricing_status'],'excluded_zero_minutes')
        self.assertEqual(x['Distributions']['Points']['mean'],0)
