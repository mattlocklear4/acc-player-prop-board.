"""Prepare ACC research matchup candidates from a timestamped Odds API snapshot.

Research-only. Never writes pregame locks. Missing games/odds are not invented.
"""
import argparse
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median
from research_engine import canon, build_baselines, load_kenpom, apply_matchup

ACC = {'bostoncollege','california','clemson','duke','floridast','georgiatech','louisville','miami','ncstate','northcarolina','notredame','pittsburgh','smu','stanford','syracuse','virginia','virginiatech','wakeforest'}
MASCOTS = {'bostoncollege':'eagles','california':'goldenbears','clemson':'tigers','duke':'bluedevils','floridast':'seminoles','georgiatech':'yellowjackets','louisville':'cardinals','miami':'hurricanes','ncstate':'wolfpack','northcarolina':'tarheels','notredame':'fightingirish','pittsburgh':'panthers','smu':'mustangs','stanford':'cardinal','syracuse':'orange','virginia':'cavaliers','virginiatech':'hokies','wakeforest':'demondeacons'}

def team_id(s):
    n=canon(s)
    if n in ACC:return n
    for k,v in MASCOTS.items():
        if n==k+v:return k
    return None

def timestamp(s):
    if not s:return None
    try:
        d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError:return None

def consensus(game, collected_at, team, cutoff=None):
    """Returns only paired pregame spread/total from the same book.

    cutoff is optional explicit as-of time, and cannot be later than tipoff.
    """
    tip=timestamp(game.get('commence_time')); collected=timestamp(collected_at)
    if not tip or not collected or collected>=tip:return None
    if cutoff is not None and (collected>cutoff or cutoff>=tip):return None
    home=team_id(game.get('home_team'));away=team_id(game.get('away_team'))
    if team not in (home,away):return None
    totals=[];spreads=[];books=[]
    for book in game.get('bookmakers') or []:
        markets=book.get('markets') or {}
        t=markets.get('totals') or {};s=markets.get('spreads') or {}
        tt=timestamp(t.get('last_update'));st=timestamp(s.get('last_update'))
        # Require valid market update timestamps, not merely snapshot timestamps.
        if not tt or not st or tt>collected or st>collected or tt>=tip or st>=tip:continue
        tout=next((o.get('point') for o in t.get('outcomes',[]) if o.get('name')=='Over'),None)
        sout=next((o.get('point') for o in s.get('outcomes',[]) if o.get('name')==game.get('home_team')),None)
        try:
            total=float(tout);spread=float(sout)
            if not math.isfinite(total) or not math.isfinite(spread):continue
        except (TypeError,ValueError):continue
        totals.append(total);spreads.append(spread if home==team else -spread)
        books.append(book.get('title') or book.get('key') or 'unknown')
    if not totals:return None
    return {'total':median(totals),'team_spread':median(spreads),'books':books,'odds_collected_at':collected.isoformat(),'tipoff':tip.isoformat()}

def resolve_opponent(name, kp):
    """Resolve sportsbook school+mascot against KenPom school; refuse ambiguous matches."""
    key=canon(name)
    if key in kp:return kp[key]["Team"]
    candidates=[row["Team"] for k,row in kp.items() if key.startswith(k) and len(k)>=4]
    if len(candidates)==1:return candidates[0]
    return None

def prepare(feed, as_of, kp, root, max_age_hours=24):
    """Process ACC teams in odds feed; reject stale snapshots and post-tipoff data.

    No schedule completeness guarantee: the odds feed may omit unpriced games.
    """
    collected=timestamp(feed.get('collected_at'))
    if not collected:raise ValueError('Odds snapshot has no valid collection timestamp')
    baselines=build_baselines(as_of,root)
    out=[]
    for game in feed.get('games') or []:
        tip=timestamp(game.get('commence_time'))
        if not tip:continue
        if tip.date().isoformat()!=as_of:continue
        home=team_id(game.get('home_team'));away=team_id(game.get('away_team'))
        for team,opp in ((home,game.get('away_team')),(away,game.get('home_team'))):
            if team not in ACC:continue
            entry={'game_id':game.get('id'),'team':team,'opponent':opp,'tipoff':tip.isoformat(),'status':'excluded','reason':None,'players':[]}
            if collected>=tip:entry['reason']='snapshot_after_tipoff'
            elif tip-collected>timedelta(hours=max_age_hours):entry['reason']='stale_odds_snapshot'
            elif not consensus(game,feed['collected_at'],team):entry['reason']='no_complete_pregame_market'
            else:
                odds=consensus(game,feed['collected_at'],team)
                try:
                    resolved_opp=resolve_opponent(opp,kp)
                    if resolved_opp is None:raise ValueError('Cannot unambiguously resolve opponent: '+str(opp))
                    rows=apply_matchup(baselines,team,resolved_opp,kp,odds)
                    if rows:
                        entry.update(status='research_ready',reason=None,players=rows,odds=odds)
                    else:entry['reason']='no_eligible_players'
                except (ValueError,KeyError,TypeError) as e:entry['reason']='missing_or_invalid_kenpom:'+str(e)
            out.append(entry)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--as-of',required=True);p.add_argument('--feed',type=Path,required=True)
    p.add_argument('--kenpom',type=Path,required=True);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();feed=json.loads(a.feed.read_text());rows=prepare(feed,a.as_of,load_kenpom(a.kenpom),a.root)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps({'research_only':True,'not_a_pregame_lock':True,'as_of':a.as_of,'games':rows},indent=2)+'\n')
    print(json.dumps({'games':len(rows),'research_ready':sum(x['status']=='research_ready' for x in rows),'excluded':sum(x['status']=='excluded' for x in rows),'output':str(a.output)}))
if __name__=='__main__':main()
