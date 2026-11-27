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
from acc_stage8b_multibook import get,ROOT as API,MARKETS,BOOKS,utc,prop_coverage

ROOT=Path(__file__).resolve().parents[1]
CAP=24
RESERVE=50
COST=len(MARKETS)

def initial_collection_due(board, now, lead_minutes=120):
    """Start at 11 ET normally, or earlier for early tipoffs.
    Never collect against a previous day's board or an already-started slate.
    A current-day published slate is required; no paid discovery here.
    """
    local=now.astimezone(ZoneInfo('America/New_York'))
    if board.get('date_eastern')!=local.date().isoformat():return False
    tips=[utc(g.get('tipoff_utc')) for g in board.get('games') or []
          if any(t.get('players') for t in g.get('teams') or [])]
    tips=[t for t in tips if t and t>now and t.astimezone(local.tzinfo).date()==local.date()]
    if not tips:return False
    nominal=local.replace(hour=11,minute=0,second=0,microsecond=0)
    deadline=min(nominal,min(tips)-dt.timedelta(minutes=lead_minutes))
    return now>=deadline

def integer(x):
    try:
        v=int(x)
        return v if v>=0 and str(v)==str(x) else None
    except (ValueError,TypeError):return None

def budget(base,observations,remaining):
    """Count actual debits plus unknown requests conservatively.
    Global remaining delta also covers failed/unpublished requests and other consumers.
    Refuse inconsistent/reset quota headers; never spend against an unknown balance.
    """
    q=base.get('quota') or {}
    morning=integer(q.get('credits_spent_conservative',q.get('credits_spent_reported')))
    initial=integer(q.get('remaining'))
    if None in (morning,initial,remaining) or remaining>initial:return 0
    spent=morning
    for i,row in enumerate(observations):
        charged=integer((row.get('quota') or {}).get('charged'))
        before=integer((row.get('quota') or {}).get('remaining_before'))
        # An unchanged verified balance at the next preflight proves a failed
        # request did not consume credits. Preserve the original failure record.
        after=integer((observations[i+1].get('quota') or {}).get('remaining_before')) if i+1<len(observations) else remaining
        no_debit=(row.get('status')=='REQUEST_FAILED' and before is not None and after==before and initial>=before>=remaining)
        spent+=charged if charged is not None and charged<=COST else 0 if no_debit else COST
    spent=max(spent,morning+initial-remaining)
    return max(0,min(CAP-spent,remaining-RESERVE))

def candidates(base,board,events,observations,now,target_game=None,retry_failed=False,repair_failed=False):
    """Use verified IDs, teams and times; only future games on today's board."""
    games={str(g.get('game_id')):g for g in board.get('games') or []}
    provider={str(e.get('id')):e for e in events}
    seen={(o.get('event_id'),o.get('phase')) for o in observations}
    out=[]
    for e in base.get('events') or []:
        eid=str(e.get('event_id') or '');gid=str(e.get('schedule_game_id') or '')
        g=games.get(gid);p=provider.get(eid)
        if target_game and gid!=target_game:continue
        if not g or not p or not any(t.get('players') for t in g.get('teams') or []):continue
        tip=utc(g.get('tipoff_utc'));ptip=utc(p.get('commence_time'))
        if not tip or not ptip or tip!=ptip or p.get('home_team')!=e.get('home_team') or p.get('away_team')!=e.get('away_team'):continue
        mins=(tip-now).total_seconds()/60
        if mins<10 or (not target_game and mins>180):continue
        phase='close' if mins<=55 else 'manual' if target_game else 'midday' if mins>=90 else None
        if phase and (eid,phase) in seen and repair_failed and target_game:
            attempts=[o for o in observations if o.get('event_id')==eid and o.get('phase') in (phase,phase+'_retry')]
            if attempts and all(o.get('status')=='REQUEST_FAILED' for o in attempts) and any(o.get('http_status')==404 for o in attempts) and (eid,phase+'_repair') not in seen:
                phase+='_repair'
        if phase and (eid,phase) in seen and retry_failed and target_game:
            attempts=[o for o in observations if o.get('event_id')==eid and o.get('phase')==phase]
            if len(attempts)==1 and attempts[0].get('status')=='REQUEST_FAILED' and (eid,phase+'_retry') not in seen:
                phase+='_retry'
        if phase and (eid,phase) not in seen:
            out.append({'event':e,'tip':tip,'minutes':mins,'phase':phase})
    # Most imminent first, with already populated markets preferred on ties.
    return sorted(out,key=lambda x:(x['phase']!='close',x['minutes'],not bool(x['event'].get('props')),str(x['event']['event_id'])))

def choose(targets,available,base,observations,now,board):
    """Preserve room for as many remaining close observations as possible."""
    slots=available//COST
    if slots<=0:return []
    closes=[x for x in targets if x['phase']=='close']
    chosen=closes[:slots]
    if len(chosen)==slots:return chosen
    completed={o.get('event_id') for o in observations if o.get('phase')=='close'}
    completed.update(x['event']['event_id'] for x in chosen)
    future={str(g.get('game_id')) for g in board.get('games') or [] if utc(g.get('tipoff_utc')) and (utc(g['tipoff_utc'])-now).total_seconds()>55*60}
    reserve=sum(e.get('event_id') not in completed and str(e.get('schedule_game_id')) in future for e in base.get('events') or [])
    extra=max(0,slots-len(chosen)-reserve)
    return chosen+[x for x in targets if x['phase']=='midday'][:extra]

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
    if not any(utc(g.get('tipoff_utc')) and (10<=(utc(g['tipoff_utc'])-now).total_seconds()/60) and ((str(g.get('game_id'))==target_game) if target_game else ((utc(g['tipoff_utc'])-now).total_seconds()/60<=180)) for g in board.get('games') or []):
        print('No imminent projected games.');return
    api_events,headers=get(API+'/events',{'apiKey':key})
    remaining=integer(headers.get('x-requests-remaining'))
    available=budget(base,observations,remaining)
    due=candidates(base,board,api_events,observations,now,target_game,retry_failed,repair_failed)
    # Explicitly requested game may spend a remaining slot outside the automatic windows.
    targets=due[:1] if target_game and available>=COST else [] if target_game else choose(due,available,base,observations,now,board)
    print('Conservative remaining daily budget:',available,'selected events:',len(targets))
    for target in targets:
        # Space discovery and odds calls apart; avoid immediate retries on 429.
        time.sleep(3)
        now=dt.datetime.now(dt.timezone.utc)
        if target['tip']-now<dt.timedelta(minutes=5) or budget(base,observations,remaining)<COST:continue
        e=target['event'];eid=str(e['event_id'])
        row={'event_id':eid,'schedule_game_id':e['schedule_game_id'],'home_team':e['home_team'],'away_team':e['away_team'],
             'tipoff_utc':target['tip'].isoformat(),'phase':target['phase'],'generated_at_utc':now.isoformat(),
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
