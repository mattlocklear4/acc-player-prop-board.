#!/usr/bin/env python3
"""Read-only schedule-led ACC projection diagnostic. Never writes to Supabase.

Uses repository KenPom CSV as an explicitly labeled fallback; not a live Supabase snapshot.
Never claims a pregame lock. Skips markets without pregame timestamp integrity.
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from acc_schedule import TEAMS, discover, get_games, parse_time
from research_engine import build_baselines, load_kenpom, apply_matchup, canon
from pregame_prepare import consensus, resolve_opponent, team_id, timestamp

ACC_CANON = {canon(x):x for x in TEAMS}

def game_team(name):
    return ACC_CANON.get(canon(name))

def school_match(odds_name, scheduled_name):
    a,b=canon(odds_name),canon(scheduled_name)
    return a==b or (a.startswith(b) and len(a)>len(b) and len(b)>=3)

def matchup(schedule, odds_feed, now, root, kp, lock_lead_minutes=None, max_odds_age_hours=24):
    results=[]
    collected=timestamp(odds_feed.get('collected_at'))
    feed_games=odds_feed.get('games') or []
    baselines_by_day={}
    for g in schedule:
        tip=parse_time(g.get('tipoff_utc'))
        if not tip:continue
        acc=[x for x in (game_team(g['home_team']),game_team(g['away_team'])) if x]
        if not acc:continue
        base={'game_id':g['game_id'],'tipoff_utc':g['tipoff_utc'],'home_team':g['home_team'],'away_team':g['away_team'],'teams':[]}
        for team in sorted(set(acc)):
            opponent=g['away_team'] if game_team(g['home_team'])==team else g['home_team']
            item={'team':team,'opponent':opponent,'status':'excluded','reason':None,'players':[]}
            if now >= tip: item['reason']='game_already_started'
            elif lock_lead_minutes is not None and tip-now>timedelta(minutes=lock_lead_minutes): item['reason']='outside_pregame_lock_window'
            else:
                local_date=tip.astimezone(ZoneInfo('America/New_York')).date().isoformat()
                try:
                    opponent_kp=resolve_opponent(opponent,kp)
                    if not opponent_kp:raise ValueError('unresolved_opponent')
                    if local_date not in baselines_by_day:baselines_by_day[local_date]=build_baselines(local_date,root)
                    market=None
                    market_issue=None
                    if not collected:market_issue='odds_snapshot_missing_timestamp'
                    elif collected>now:market_issue='odds_snapshot_from_future'
                    elif collected>=tip:market_issue='odds_snapshot_after_tipoff'
                    elif now-collected>timedelta(hours=max_odds_age_hours):market_issue='odds_snapshot_too_old'
                    else:
                        matching=[o for o in feed_games if school_match(o.get('home_team'),g['home_team']) and school_match(o.get('away_team'),g['away_team']) and timestamp(o.get('commence_time'))==tip]
                        if len(matching)!=1:market_issue='odds_game_missing_or_ambiguous'
                        else:
                            market=consensus(matching[0],odds_feed['collected_at'],team,cutoff=now)
                            if not market:market_issue='no_complete_pregame_market'
                    players=apply_matchup(baselines_by_day[local_date],team,opponent_kp,kp,market)
                    if not players:raise ValueError('no_eligible_players')
                    item.update(status='research_candidate_unverified',reason='kenpom_freshness_and_browser_parity_not_verified',players=players,odds=market,odds_status=market_issue or 'available',kenpom_source='repository_csv_unverified_age')
                except (KeyError,ValueError,FileNotFoundError,TypeError) as exc:item['reason']='projection_input_error:'+str(exc)
            base['teams'].append(item)
        results.append(base)
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schedule',type=Path,required=True,help='JSON output from acc_schedule.py')
    p.add_argument('--odds',type=Path,default=Path('data/acc_odds.json'))
    p.add_argument('--kenpom',type=Path,default=Path('data/cbbd/kenpom_2027_initial.csv'))
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,default=Path('research/acc_projection_dry_run.json'))
    p.add_argument('--now',help='ISO8601 aware timestamp for fixture testing')
    p.add_argument('--today-only',action='store_true',help='Include only games on the current US Eastern calendar day')
    a=p.parse_args()
    now=timestamp(a.now) if a.now else datetime.now(timezone.utc)
    if not now:p.error('--now must be timezone aware')
    schedule=json.loads(a.schedule.read_text())
    if schedule.get('mode')!='DRY_RUN_NO_WRITES':p.error('Expected read-only schedule artifact')
    odds=json.loads(a.odds.read_text())
    kp=load_kenpom(a.kenpom)
    eligible=schedule['games']
    if a.today_only:
        today=now.astimezone(ZoneInfo('America/New_York')).date()
        eligible=[g for g in eligible if parse_time(g.get('tipoff_utc')) and parse_time(g['tipoff_utc']).astimezone(ZoneInfo('America/New_York')).date()==today]
    games=matchup(eligible,odds,now,a.root,kp)
    counts={}
    for g in games:
        for t in g['teams']:
            key=t['status'] if t['status'].startswith('research_candidate') else t['reason']
            counts[key]=counts.get(key,0)+1
    payload={'mode':'DRY_RUN_NO_WRITES','not_a_pregame_lock':True,'generated_at_utc':now.isoformat(),
             'kenpom_source':str(a.kenpom),'projection_stage':'EARLY_DAY_RESEARCH','kenpom_freshness_verified':False,
             'browser_parity_verified':False,'manual_minutes_overrides_applied':False,
             'warning':'Early-day research only. No Supabase writes; no pregame lock. Repository KenPom may be stale; manual minutes overrides not applied. Vegas/Combined unavailable if no valid odds.',
             'summary':counts,'games':games}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(payload,indent=2)+'\n')
    print('DRY RUN: '+json.dumps(counts,sort_keys=True))
    print('NO SUPABASE WRITES; NO PREGAME LOCKS; KENPOM FRESHNESS UNVERIFIED')

if __name__=='__main__':main()
