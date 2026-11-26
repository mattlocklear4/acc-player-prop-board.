import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from acc_grade_pregame import grade, pending_report

class TestGrade(unittest.TestCase):
    def test_latest_pregame_and_positive_only(self):
        date='2026-11-25';gid='espn_event_1';tip=date+'T20:00:00Z';odds=date+'T16:00:00Z'
        def record(hour,edge,projection):
            stamp=date+f'T{hour}:00:00Z'
            game={'game_id':gid,'tipoff_utc':tip,'teams':[{'team':'Duke','players':[{'Player':'Test Player','KenPomPoints':projection,'ModelVersion':'v2'}]}]}
            q={'game_id':gid,'team':'Duke','player':'Test Player','market':'Points','bookmaker':'fanduel','side':'over','line':14.5,'american_odds':-110,'projection':projection,'model_version':'v2','win_probability':.6,'expected_roi_percent':edge,'projection_utc':stamp,'odds_snapshot_utc':odds,'quote_updated_utc':odds}
            return {'date_eastern':date,'captured_at_utc':stamp,'projection_utc':stamp,'odds_snapshot_utc':odds,'game':game,'quotes':[q]}
        logs={'espn_1':[{'game_date':date,'source':'ESPN_UNOFFICIAL','team':'Duke Blue Devils','player':'Test Player','points':'18'}]}
        a=grade([record('17',-1,14),record('18',12,17),record('21',30,30)],logs,'2026-11-26')
        self.assertEqual(a['players_graded'],1)
        self.assertEqual(a['projection_metrics']['Points']['mae'],1)
        self.assertEqual(a['positive_roi']['wins'],1)
        self.assertEqual(a['by_tier']['10–20%']['settled'],1)
        self.assertAlmostEqual(a['positive_roi']['roi_percent'],90.91)
        self.assertEqual(grade([record('18',12,17)],{},'2026-11-26')['positive_roi']['settled'],0)
        self.assertEqual(grade([record('18',12,17)],logs,date)['quotes_priced'],0)

    def test_pending_matches_next_day_selection(self):
        date='2026-11-25';gid='espn_event_1';tip=date+'T20:00:00Z';odds=date+'T16:00:00Z'
        def rec(hour,edge,version='v4'):
            stamp=date+f'T{hour}:00:00Z'
            q={'game_id':gid,'team':'Duke','player':'Test Player','market':'Points','bookmaker':'fanduel','side':'over','line':14.5,'american_odds':-110,'projection':17,'model_version':version,'win_probability':.6,'expected_roi_percent':edge,'projection_utc':stamp,'odds_snapshot_utc':odds,'quote_updated_utc':odds}
            return {'date_eastern':date,'captured_at_utc':stamp,'projection_utc':stamp,'odds_snapshot_utc':odds,'game':{'game_id':gid,'tipoff_utc':tip,'teams':[{'team':'Duke','players':[{'Player':'Test Player','KenPomPoints':17}]}]},'quotes':[q]}
        old=rec('17',-1,'v3');latest=rec('18',12);invalid=rec('21',99)
        latest['quotes'].append(dict(latest['quotes'][0])) # duplicate must not count
        records=[old,latest,invalid]
        p=pending_report(records,date)
        self.assertEqual(p['games'],1)
        self.assertEqual(p['player_projections'],1)
        self.assertEqual(p['quotes_priced'],1)
        self.assertEqual(p['positive_selections'],1)
        self.assertEqual(p['mean_expected_roi_percent'],12)
        self.assertEqual(p['by_model_version']['v4']['selections'],1)
        self.assertEqual(p['positive_selections'],grade(records,{},'2026-11-26')['positive_roi']['selections'])
        self.assertEqual(grade(records,{},date)['positive_roi']['selections'],0)
        self.assertEqual(pending_report(records,'2026-11-26')['status'],'NO_ARCHIVES')
        self.assertIsNone(pending_report([old],date)['mean_expected_roi_percent'])

class GameIdentityTests(unittest.TestCase):
    def test_verified_alias_deduplicates_and_keeps_priced_capture(self):
        from acc_game_identity import load_aliases,canonical_record
        from acc_grade_pregame import select_snapshots
        date='2026-11-26';tip='2026-11-26T20:30:00Z'
        a={'date_eastern':date,'game':{'game_id':'espn_event_401920537','home_team':'Michigan Wolverines','away_team':'Miami Hurricanes','tipoff_utc':tip},'captured_at_utc':date+'T17:01:00Z','projection_utc':date+'T17:00:00Z','odds_snapshot_utc':date+'T15:54:00Z','quotes':[{'game_id':'espn_event_401920537'}]}
        b={**a,'game':{'game_id':'378713','home_team':'Michigan','away_team':'Miami','tipoff_utc':tip},'captured_at_utc':date+'T19:01:00Z','projection_utc':date+'T19:00:00Z','quotes':[]}
        latest,priced,issues=select_snapshots([a,b],lambda d:d==date)
        key=(date,'espn_event_401920537')
        self.assertEqual(len(latest),1)
        self.assertEqual(latest[key][1]['game']['provider_game_id'],'378713')
        self.assertEqual(priced[key][1]['projection_utc'],a['projection_utc'])
        self.assertEqual(b['game']['game_id'],'378713')
        self.assertEqual(issues,[])
        for g in ({**b['game'],'home_team':'Other school'},{**b['game'],'tipoff_utc':date+'T21:30:00Z'}):
            self.assertEqual(canonical_record({**b,'game':g},load_aliases())['game']['game_id'],'378713')


class CommonCohortTests(unittest.TestCase):
    def test_same_sample_duplicate_books_and_missing_models(self):
        from acc_model_comparison import compare, COMMON_VERSIONS
        date='2026-11-25';gid='espn_event_1';stamp=date+'T17:00:00Z';odds=date+'T16:00:00Z'
        versions=COMMON_VERSIONS[1:]
        def player(name,complete):
            return {'Player':name,'KenPomPoints':10,'ExperimentalModels':{v:{'KenPomPoints':12} for v in (versions if complete else versions[:-1])}}
        def quote(name,book,side,prob):
            return {'game_id':gid,'team':'Duke','player':name,'market':'Points','bookmaker':book,'side':side,'line':11.5,'american_odds':-110,'win_probability':prob,'expected_roi_percent':10,'projection_utc':stamp,'odds_snapshot_utc':odds,'quote_updated_utc':odds}
        base=[quote('Test Player',book,side,.6 if side=='over' else .4) for book in ('fanduel','draftkings') for side in ('over','under')]
        base.append(quote('Missing Model','fanduel','over',.6))
        exp={v:[{**q,'win_probability':.7 if q['side']=='over' else .3} for q in base if v!=versions[-1] or q['player']!='Missing Model'] for v in versions}
        r={'date_eastern':date,'captured_at_utc':stamp,'projection_utc':stamp,'odds_snapshot_utc':odds,'game':{'game_id':gid,'tipoff_utc':date+'T20:00:00Z','teams':[{'team':'Duke','players':[player('Test Player',True),player('Missing Model',False)]}]},'quotes':base,'experimental_quotes':exp}
        logs={'espn_1':[{'game_date':date,'source':'ESPN_UNOFFICIAL','team':'Duke Blue Devils','player':name,'points':'13'} for name in ('Test Player','Missing Model')]}
        c=compare([r],logs,'2026-11-26')['common_cohort']
        self.assertEqual(c['paired_players'],1)
        self.assertEqual(c['paired_settled_quote_sides'],4)
        self.assertEqual(c['unique_outcomes'],1)
        self.assertEqual(c['projection_games'],1)
        self.assertEqual(c['models']['v4']['projection_metrics']['Points']['mae'],3)
        self.assertEqual(c['models'][versions[-1]]['projection_metrics']['Points']['mae'],1)
        self.assertEqual(c['models']['v4']['calibration']['n'],1)
        self.assertEqual(c['models']['v4']['calibration']['brier'],.16)
        self.assertEqual(c['models'][versions[-1]]['calibration']['brier'],.09)
        self.assertEqual(c['models']['v4']['positive_roi']['settled'],4)
        self.assertEqual(sum(x['n'] for x in c['models']['v4']['reliability']),1)
        self.assertEqual(compare([r],logs,date)['common_cohort']['paired_players'],0)
        self.assertEqual(compare([],{},'2026-11-26')['common_cohort']['unique_outcomes'],0)
