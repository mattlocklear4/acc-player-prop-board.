import sys, unittest, datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_intraday_odds import budget,candidates,choose

class IntradayTests(unittest.TestCase):
    def test_credit_cap_reserve_and_unknowns(self):
        b={'quota':{'credits_spent_reported':16,'remaining':100}}
        self.assertEqual(budget(b,[],100),8)
        self.assertEqual(budget({'quota':{'credits_spent_reported':12,'credits_spent_conservative':16,'remaining':100}},[],100),8)
        self.assertEqual(budget(b,[],96),4)
        self.assertEqual(budget(b,[{'quota':{'charged':None}}],100),4)
        self.assertEqual(budget(b,[{'quota':{'charged':4}}],96),4)
        self.assertEqual(budget(b,[],92),0)
        self.assertEqual(budget(b,[],101),0)
        self.assertEqual(budget(b,[],None),0)
        self.assertEqual(budget({'quota':{'credits_spent_reported':8,'remaining':52}},[],52),2)

    def test_due_games_and_reserve(self):
        now=dt.datetime(2026,11,26,18,tzinfo=dt.timezone.utc)
        def game(i,mins):
            tip=(now+dt.timedelta(minutes=mins)).isoformat()
            return ({'game_id':i,'tipoff_utc':tip,'teams':[{'players':[{'Player':'P'}]}]},
                    {'id':i,'home_team':'Home','away_team':'Away','commence_time':tip},
                    {'event_id':i,'schedule_game_id':i,'home_team':'Home','away_team':'Away','props':[{}]})
        a,b,c,d,e=[game(str(i),m) for i,m in enumerate((25,120,240,-5,3))]
        base={'events':[x[2] for x in (a,b,c,d,e)]}
        board={'games':[x[0] for x in (a,b,c,d,e)]}
        api=[x[1] for x in (a,b,c,d,e)]
        due=candidates(base,board,api,[],now)
        self.assertEqual([(x['event']['event_id'],x['phase']) for x in due],[('0','close'),('1','midday')])
        self.assertEqual([x['event']['event_id'] for x in choose(due,8,base,[],now,board)],['0'])
        self.assertEqual([x['event']['event_id'] for x in choose(due,16,base,[],now,board)],['0','1'])
        self.assertEqual(candidates(base,board,api,[{'event_id':'0','phase':'close'},{'event_id':'1','phase':'midday'}],now),[])
        wrong=[{**a[1],'commence_time':b[1]['commence_time']}]
        self.assertEqual(candidates(base,board,wrong,[],now),[])

if __name__=='__main__':unittest.main()
