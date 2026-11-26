import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_rotation_model import elapsed,validated_game,transfer,attach_rotation,VERSION
from acc_experimental_models import SHOOTING
from acc_availability import VERSION as AVAILABILITY
class RotationTests(unittest.TestCase):
    def test_clock(self):
        self.assertEqual(elapsed({'period':1,'secondsRemaining':1200}),0)
        self.assertEqual(elapsed({'period':2,'secondsRemaining':0}),2400)
        self.assertEqual(elapsed({'period':3,'secondsRemaining':0}),2700)
    def test_reconcile(self):
        def e(p,s):return {'period':p,'secondsRemaining':s,'teamPoints':70,'opponentPoints':65}
        rows=[{'athleteId':i,'position':'G','subIn':e(1,1200),'subOut':e(2,0)} for i in range(1,6)]
        box={str(i):{'minutes':40,'position':'G'} for i in range(1,6)}
        self.assertIsNotNone(validated_game(rows,box))
        self.assertIsNone(validated_game(rows[:-1],box))
        box['1']['minutes']=15
        self.assertIsNone(validated_game(rows,box))
    def test_position_weighting(self):
        ps=[{'AthleteId':str(i)} for i in range(7)]
        mins=[20,30,30,30,30,30,30]
        roles={'0':'B','1':'G','2':'G','3':'W','4':'W','5':'B','6':'B'}
        out=transfer(mins,ps,{0:30},roles,{('0','5'):4})
        self.assertEqual(out[0],30)
        self.assertEqual(sum(round(m*10) for m in out),2000)
        self.assertLess(out[5],out[1])
        self.assertLess(out[6],out[2])
    def test_no_evidence_no_model(self):
        p={'AthleteId':'1','ExperimentalModels':{SHOOTING:{'Minutes':20}}}
        self.assertNotIn(VERSION,attach_rotation([p],'Miami',{})[0]['ExperimentalModels'])
    def test_override_and_control_preserved(self):
        ps=[{'AthleteId':str(i),'ExperimentalModels':{SHOOTING:{'Minutes':m,'KenPomPoints':10}}} for i,m in enumerate([20,30,30,30,30,30,30])]
        ps[0]['ExperimentalModels'][AVAILABILITY]={'AvailabilityAdjustment':{'status':'returning','minutes':30}}
        box={str(i):{'minutes':m,'position':'B' if i in (0,5,6) else 'G','fouls':2} for i,m in enumerate([20,30,30,30,30,30,30])}
        g={'box':box,'positions':{},'swaps':{},'margin':5}
        r=attach_rotation(ps,'Miami',{'miamifl':{'games':[g,g],'candidate_games':2,'snapshot_utc':'2026-11-26T12:00:00Z'}})
        self.assertEqual(r[0]['ExperimentalModels'][VERSION]['Minutes'],30)
        self.assertEqual(ps[0]['ExperimentalModels'][SHOOTING]['Minutes'],20)
        self.assertEqual(sum(round(p['ExperimentalModels'][VERSION]['Minutes']*10) for p in r),2000)
