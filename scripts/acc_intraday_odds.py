#!/usr/bin/env python3
"""Quota-safe intraday ACC odds observations; immutable morning files are untouched."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
from zoneinfo import ZoneInfo
from acc_stage8b_multibook import get,ROOT as API,MARKETS,BOOKS,utc,prop_coverage,team_match

ROOT=Path(__file__).resolve().parents[1]
RESERVE=50
COST=len(MARKETS)

def initial_collection_due(board, now, lead_minutes=120):
    """Start at 8 ET normally, or earlier for early tipoffs.
    Never collect against a previous day's board or an already-started slate.
    A current-day published slate is required; no paid discovery here.
    """
    local=now.astimezone(ZoneInfo('America/New_York'))
    if board.get('date_eastern')!=local.date().isoformat():return False
    tips=[utc(g.get('tipoff_utc')) for g in board.get('games') or []
          if any(t.get('players') for t in g.get('teams') or [])]
    tips=[t for t in tips if t and t>now and t.astimezone(local.tzinfo).date()==local.date()]
    if not tips:return False
    nominal=local.replace(hour=8,minute=0,second=0,microsecond=0)
    deadline=min(nominal,min(tips)-dt.timedelta(minutes=lead_minutes))
    return now>=deadline

def integer(x):
    try:
        v=int(x)
        return v if v>=0 and str(v)==str(x) else None
    except (ValueError,TypeError):return None

def budget(base,observations,remaining):
    """No daily cap; use the verified current provider balance."""
    return max(0,remaining-RESERVE) if integer(remaining) is not None else 0

def candidates(base,board,events,observations,now,target_game=None,retry_failed=False,repair_failed=False):
    """Full slate, unique provider identity, opening odds before refreshes."""
    provider={str(e.get('id')):e for e in events}
    known={str(e.get('schedule_game_id')):e for e in base.get('events') or []}
    for o in observations:
        known.setdefault(str(o.get('schedule_game_id')),o)
    out=[]
    for g in board.get('games') or []:
        gid=str(g.get('game_id') or '')
        if target_game and gid!=target_game:continue
        if not gid or not any(t.get('players') for t in g.get('teams') or []):continue
        tip=utc(g.get('tipoff_utc'))
        if not tip or tip.astimezone(ZoneInfo('America/New_York')).date()!=now.astimezone(ZoneInfo('America/New_York')).date():continue
        mins=(tip-now).total_seconds()/60
        if mins<10:continue
        e=known.get(gid)
        if e:
            p=provider.get(str(e.get('event_id')))
            if not p or utc(p.get('commence_time'))!=tip or p.get('home_team')!=e.get('home_team') or p.get('away_team')!=e.get('away_team'):continue
        else:
            h,a=g.get('home_team'),g.get('away_team')
            if not h or not a:continue
            matches=[p for p in events if utc(p.get('commence_time'))==tip and
                ((team_match(h,p.get('home_team')) and team_match(a,p.get('away_team'))) or
                 (team_match(h,p.get('away_team')) and team_match(a,p.get('home_team'))))]
            if len(matches)!=1:continue
            p=matches[0]
            if any(str(x.get('event_id'))==str(p.get('id')) for k,x in known.items() if k!=gid):continue
            e={'event_id':p['id'],'schedule_game_id':gid,'home_team':p['home_team'],'away_team':p['away_team'],'props':[]}
        eid=str(e['event_id'])
        history=[o for o in observations if str(o.get('event_id'))==eid]
        def stamp(o):return utc(o.get('generated_at_utc')) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        latest=max(history,key=stamp,default=None)
        valid=[o for o in history if o.get('status') in ('ODDS_RETRIEVED','NO_REQUESTED_BOOK_PROPS_RETURNED')]
        last_valid=max(valid,key=stamp,default=None)
        has_props=bool(last_valid.get('props')) if last_valid else bool(e.get('props'))
        last_attempt=utc(latest.get('generated_at_utc')) if latest else utc(base.get('generated_at_utc')) if gid in known else None
        last_success=utc(last_valid.get('generated_at_utc')) if last_valid else utc(base.get('generated_at_utc')) if gid in known else None
        age=(now-last_attempt).total_seconds()/60 if last_attempt else float('inf')
        quote_age=(now-last_success).total_seconds()/60 if last_success else float('inf')
        if target_game:
            if age<5:continue
            phase='manual'
        elif age<25:continue
        elif not has_props:phase='opening'
        elif mins<=55 and not any(o.get('phase')=='close' and o.get('status')=='ODDS_RETRIEVED' for o in history):phase='close'
        elif mins>55 and quote_age>=180:phase='refresh'
        else:continue
        out.append({'event':e,'tip':tip,'minutes':mins,'phase':phase,'schedule_home_team':g.get('home_team'),'schedule_away_team':g.get('away_team')})
    counts={}
    for x in out:
        eid=str(x['event']['event_id']);counts[eid]=counts.get(eid,0)+1
    return sorted([x for x in out if counts[str(x['event']['event_id'])]==1],key=lambda x:({'opening':0,'manual':0,'close':1,'refresh':2}[x['phase']],x['minutes']))

def choose(targets,available,base,observations,now,board):
    return targets[:available//COST]

def atomic_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2)+'\n')
    tmp.replace(path)

def main():
    now=dt.datetime.now(dt.timezone.utc)
    today=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    base_path=ROOT/'data/odds_snapshots'/f'{today}.json'
    manifest_path=ROOT/'data/odds_snapshots/intraday'/f'{today}.json'
    if not base_path.exists():print('Morning snapshot missing; no refresh.');return
    base=json.loads(base_path.read_text())
    board=json.loads((ROOT/'data/daily_board.json').read_text())
    if board.get('date_eastern')!=today:print('Current-date projections not published; no refresh.');return
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {'date_eastern':today,'observations':[]}
    if manifest.get('date_eastern')!=today:raise RuntimeError('Intraday manifest date mismatch')
    observations=manifest['observations']
    key=os.environ.get('ODDS_API_KEY','').strip()
    if not key:raise RuntimeError('Odds secret missing')
    target_game=None
    retry_failed=False
    repair_failed=False
    if os.environ.get('TARGETED_REQUEST','').lower()=='true':
        request=json.loads((ROOT/'research/odds_refresh_request.json').read_text())
        if request.get('date_eastern')!=today:print('Expired request.');return
        target_game=request.get('schedule_game_id') or None
        retry_failed=request.get('retry_failed') is True
        repair_failed=request.get('repair_failed') is True
        if target_game and not isinstance(target_game,str):raise RuntimeError('Invalid requested game ID')
    # Cheap local check before even making a free discovery request.
    if not any(utc(g.get('tipoff_utc')) and (10<=(utc(g['tipoff_utc'])-now).total_seconds()/60) and ((str(g.get('game_id'))==target_game) if target_game else True) for g in board.get('games') or []):
        print('No upcoming projected games.');return
    api_events,headers=get(API+'/events',{'apiKey':key})
    remaining=integer(headers.get('x-requests-remaining'))
    available=budget(base,observations,remaining)
    due=candidates(base,board,api_events,observations,now,target_game,retry_failed,repair_failed)
    # Explicitly requested game may spend a remaining slot outside the automatic windows.
    targets=due[:1] if target_game and available>=COST else [] if target_game else choose(due,available,base,observations,now,board)
    print('Provider credits above reserve:',available,'selected events:',len(targets))
    for target in targets:
        # Space discovery and odds calls apart; avoid immediate retries on 429.
        time.sleep(3)
        now=dt.datetime.now(dt.timezone.utc)
        if target['tip']-now<dt.timedelta(minutes=5) or budget(base,observations,remaining)<COST:continue
        e=target['event'];eid=str(e['event_id'])
        row={'event_id':eid,'schedule_game_id':e['schedule_game_id'],'home_team':e['home_team'],'away_team':e['away_team'],
             'tipoff_utc':target['tip'].isoformat(),'schedule_home_team':target['schedule_home_team'],'schedule_away_team':target['schedule_away_team'],'identity_verified':True,'phase':target['phase'],'generated_at_utc':now.isoformat(),
             'status':'REQUEST_STARTED','props':[],'quota':{'charged':None,'remaining_before':remaining}}
        observations.append(row)
        atomic_json(manifest_path,manifest)
        try:
            data,meta=get(API+'/events/'+urllib.parse.quote(eid,safe='')+'/odds',
                          {'apiKey':key,'bookmakers':','.join(BOOKS),'markets':','.join(MARKETS),'oddsFormat':'american'})
            captured=dt.datetime.now(dt.timezone.utc)
            charged=integer(meta.get('x-requests-last'));after=integer(meta.get('x-requests-remaining'))
            row['generated_at_utc']=captured.isoformat()
            row['quota'].update(charged=charged,remaining_after=after)
            valid=(charged is not None and charged<=COST and after is not None and remaining-after==charged)
            if not valid or captured>=target['tip'] or data.get('id')!=eid or data.get('home_team')!=e['home_team'] or data.get('away_team')!=e['away_team'] or utc(data.get('commence_time'))!=target['tip']:
                row['status']='UNVERIFIED_RESPONSE';atomic_json(manifest_path,manifest);break
            props=[{'bookmaker':b['key'],'market':m['key'],'player':o.get('description'),'side':o.get('name'),'line':o.get('point'),'odds':o.get('price'),'last_update':m.get('last_update')} for b in data.get('bookmakers') or [] if b.get('key') in BOOKS for m in b.get('markets') or [] if m.get('key') in MARKETS for o in m.get('outcomes') or []]
            row.update(status='ODDS_RETRIEVED' if props else 'NO_REQUESTED_BOOK_PROPS_RETURNED',props=props,coverage=prop_coverage(props))
            remaining=after
            atomic_json(manifest_path,manifest)
            print('Archived',eid,target['phase'],'quotes',len(props),'credits',charged)
        except Exception as exc:
            # Do not log provider URLs or credentials. Unknown charges count at maximum cost.
            row['status']='REQUEST_FAILED';row['error_type']=type(exc).__name__
            if isinstance(getattr(exc,'code',None),int):row['http_status']=exc.code
            # Only persist a structured provider error code, never the body or URL.
            try:
                payload=json.loads(exc.read(16384))
                code=payload.get('error_code') or payload.get('code')
                if isinstance(code,str) and re.fullmatch(r'[A-Z][A-Z_0-9]{1,79}',code):row['provider_error_code']=code
            except Exception:pass
            atomic_json(manifest_path,manifest)
            print('Request failed; stopped without retry:',type(exc).__name__,row.get('http_status',''),row.get('provider_error_code',''))
            break

if __name__=='__main__':main()
