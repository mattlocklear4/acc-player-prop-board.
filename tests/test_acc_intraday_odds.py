import sys, unittest, datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_intraday_odds import budget,candidates,choose,initial_collection_due

class IntradayTests(unittest.TestCase):
    def test_initial_collection(self):
        from zoneinfo import ZoneInfo
        z=ZoneInfo('America/New_York')
        def at(h,m=0):return dt.datetime(2026,11,27,h,m,tzinfo=z)
        def board(h,day='2026-11-27'):
            return {'date_eastern':day,'games':[{'tipoff_utc':at(h).isoformat(),'teams':[{'players':[{}]}]}]}
        self.assertFalse(initial_collection_due(board(19),at(7,59)))
        self.assertTrue(initial_collection_due(board(19),at(8)))
        self.assertTrue(initial_collection_due(board(9),at(7)))
        self.assertFalse(initial_collection_due(board(11),at(11)))
        self.assertFalse(initial_collection_due(board(11,'2026-11-26'),at(9)))
    def test_provider_balance_only(self):
        b={'quota':{'remaining':100,'credits_spent_reported':24}}
        self.assertEqual(budget(b,[],100),50)
        self.assertEqual(budget(b,[{'quota':{'charged':60}}],5000),4950)
        self.assertEqual(budget(b,[],52),2)
        self.assertEqual(budget(b,[],None),0)
        self.assertEqual(budget(b,[],49),0)
    def test_full_slate_and_refresh(self):
        now=dt.datetime(2026,11,27,18,tzinfo=dt.timezone.utc)
        def game(i,mins):
            tip=(now+dt.timedelta(minutes=mins)).isoformat()
            h='School'+i;a='Visitor'+i
            return ({'game_id':i,'home_team':h,'away_team':a,'tipoff_utc':tip,'teams':[{'players':[{}]}]},
                    {'id':i,'home_team':h,'away_team':a,'commence_time':tip},
                    {'event_id':i,'schedule_game_id':i,'home_team':h,'away_team':a,'props':[{}]})
        a,b,c,d,e=[game(str(i),m) for i,m in enumerate((25,120,420,-5,3))]
        base={'generated_at_utc':(now-dt.timedelta(minutes=190)).isoformat(),'events':[a[2],b[2]]}
        board={'games':[x[0] for x in (a,b,c,d,e)]}
        api=[x[1] for x in (a,b,c,d,e)]
        due=candidates(base,board,api,[],now)
        self.assertEqual([(x['event']['event_id'],x['phase']) for x in due],[('2','opening'),('0','close'),('1','refresh')])
        self.assertEqual(len(choose(due,100,base,[],now,board)),3)
        self.assertEqual(len(choose(due,4,base,[],now,board)),1)
        empty={**c[2],'props':[],'status':'NO_REQUESTED_BOOK_PROPS_RETURNED','generated_at_utc':(now-dt.timedelta(minutes=30)).isoformat()}
        self.assertEqual(candidates(base,board,api,[empty],now)[0]['phase'],'opening')
        self.assertNotIn('2',[x['event']['event_id'] for x in candidates(base,board,api,[{**empty,'generated_at_utc':now.isoformat()}],now)])
        self.assertEqual(candidates(base,board,api,[],now,'2')[0]['phase'],'manual')
        self.assertEqual(candidates(base,board,api+[dict(c[1],id='ambiguous')],[],now,'2'),[])
        self.assertEqual(candidates(base,board,[dict(c[1],commence_time=b[1]['commence_time'])],[],now,'2'),[])
if __name__=='__main__':unittest.main()
