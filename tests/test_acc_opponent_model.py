import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_opponent_model import VERSION,attach_matchup,factors,metrics,load_context
from acc_experimental_models import SHOOTING
from datetime import datetime,timezone
from tempfile import TemporaryDirectory
import json
KEYS=('two_pct','three_pct','two_attempt_rate','three_attempt_rate','ft_attempt_rate','assists_rate','off_miss_rate','def_miss_rate','opp_orb_share','team_orb_share')
class OpponentModelTests(unittest.TestCase):
    def sample(self):
        league={k:.4 for k in KEYS}
        m={**league,'games':6,'possessions':420}
        p={'Minutes':30,'PaceFactor':1.,'CurrentSeasonLog':[{'oreb':2,'dreb':4}],'ExperimentalModels':{SHOOTING:{'Minutes':32,'BaselinePoints':12,'KenPomPoints':11,'BaselineThrees':1,'KenPomThrees':1,'BaselineRebounds':6,'KenPomRebounds':6,'BaselineAssists':3,'KenPomAssists':3,'ShotInputs':{'components':{k:{'expected_pct':v} for k,v in [('2P',.5),('3P',.3),('FT',.75)]},'projected_attempts':{'2P':8,'3P':4,'FT':2}}}}}
        return league,m,p
    def test_neutral_matchup_and_no_double_defense(self):
        league,m,p=self.sample()
        before=copy.deepcopy(p)
        a=attach_matchup([p],'Michigan',{'teams':{'michigan':m},'league':league,'timestamp':'2026-11-26T12:00:00Z','coverage':350})[0]
        v=a['ExperimentalModels'][VERSION]
        self.assertEqual(v['Minutes'],32)
        self.assertAlmostEqual(v['KenPomPoints'],13.1)
        self.assertAlmostEqual(v['KenPomThrees'],1.2)
        self.assertAlmostEqual(v['KenPomRebounds'],6)
        self.assertAlmostEqual(v['KenPomAssists'],3)
        self.assertEqual(p,before)
    def test_specific_direction(self):
        league,m,p=self.sample()
        m['three_pct']=.25;m['three_attempt_rate']=.2;m['assists_rate']=.2;m['team_orb_share']=.55
        f=factors(m,league)
        self.assertLess(f['3P_eff'],1)
        self.assertLess(f['3PA'],1)
        self.assertLess(f['AST'],1)
        self.assertLess(f['DREB'],1)
        self.assertEqual(f['2P_eff'],1)
    def test_missing_context_and_missing_opponent(self):
        league,m,p=self.sample()
        self.assertNotIn(VERSION,attach_matchup([p],'Michigan',None)[0]['ExperimentalModels'])
        self.assertNotIn(VERSION,attach_matchup([p],'Michigan',{'teams':{}})[0]['ExperimentalModels'])
    def test_future_snapshot_rejected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'data/cbbd';path.mkdir(parents=True)
            (path/'acc_team_collection_summary_2027.json').write_text(json.dumps({'last_successful_run_utc':'2026-11-27T12:00:00Z'}))
            self.assertIsNone(load_context(root,datetime(2026,11,26,tzinfo=timezone.utc),{}))
    def test_missing_metrics_not_zero(self):
        self.assertIsNone(metrics({'games':6,'teamStats':{'possessions':420},'opponentStats':{'possessions':420}}))
