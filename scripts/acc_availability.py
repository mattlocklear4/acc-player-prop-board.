"""Pregame-only, explicitly dated manual availability scenarios; preserve the control."""
import json, math
from datetime import date, datetime, timezone
from research_engine import STATS, canon, clamp
from acc_experimental_models import finite

VERSION='v7-manual-availability'

def load_overrides(root, day, now):
    path=root/'data/player_availability_overrides.json'
    if not path.exists():return []
    entries=json.loads(path.read_text())
    if not isinstance(entries,list):raise ValueError('availability overrides must be a list')
    active=[]
    for e in entries:
        if e.get('date')!=day:continue
        recorded=datetime.fromisoformat(e['recorded_at_utc'].replace('Z','+00:00'))
        if recorded.tzinfo is None or recorded>now:continue
        if not e.get('game_id') or not e.get('team') or not e.get('athlete_id') or not e.get('reason'):
            raise ValueError('availability override requires game, team, player ID and reason')
        if e.get('status') not in ('returning','limited','out','manual'):
            raise ValueError('unknown availability status')
        m=finite(e.get('minutes'))
        if m is None or not 0<=m<=40 or abs(m*10-round(m*10))>1e-8 or (e['status']=='out' and m!=0):
            raise ValueError('invalid availability minutes')
        for d in e.get('exclude_dates',[])+e.get('injury_absence_dates',[]):
            if date.fromisoformat(d)>=date.fromisoformat(day):raise ValueError('excluded date must precede slate')
        active.append(e)
    return active

def risk_flags(p):
    logs=sorted(p.get('CurrentSeasonLog') or [],key=lambda g:g.get('date',''),reverse=True)
    flags=[]
    mins=finite(p.get('Minutes'))
    if p.get('DataCoverageWarning'):flags.append('Incomplete team game coverage')
    if logs and mins is not None:
        latest=finite(logs[0].get('minutes'))
        if latest is not None and latest>=20 and latest-mins>=8:
            flags.append('Latest appearance materially above projected minutes')
        if len(logs)>=2:
            gap=(date.fromisoformat(logs[0]['date'])-date.fromisoformat(logs[1]['date'])).days
            if gap>=9 and latest is not None and latest>=20:
                flags.append('Recent return after a long gap; verify availability')
        if p.get('CurrentTeamGames',0)-len(logs)>=2 and sum(str(g.get('starter')).lower() in ('true','1','yes') for g in logs)>=len(logs)*.6:
            flags.append('Regular starter with nonappearances; verify reason')
        if len(logs)>=3:
            recent=[finite(g.get('minutes')) for g in logs[:3]]
            if all(v is not None for v in recent) and max(recent)-min(recent)>=15:
                flags.append('Volatile recent playing time')
    return flags

def allocate_fixed(raw, locked):
    # Largest-remainder rounding with a hard cap and fixed overrides.
    units={i:round(m*10) for i,m in locked.items()}
    if any(not 0<=v<=400 for v in units.values()):raise ValueError('invalid locked minutes')
    remaining=2000-sum(units.values())
    active=[i for i,m in enumerate(raw) if i not in locked and m>0]
    if remaining<0 or len(active)*400<remaining:raise ValueError('overrides make 200-minute rotation impossible')
    values={i:0. for i in range(len(raw)) if i not in locked}
    while active and remaining>0:
        total=sum(raw[i] for i in active)
        capped=[i for i in active if remaining*raw[i]/total>=400]
        if not capped:
            for i in active:values[i]=remaining*raw[i]/total
            break
        for i in capped:values[i]=400.;remaining-=400
        active=[i for i in active if i not in capped]
    for i,v in values.items():units[i]=math.floor(v+1e-9)
    residue=2000-sum(units.values())
    eligible=sorted((i for i in values if units[i]<400 and raw[i]>0),key=lambda i:(-(values[i]-units[i]),i))
    if not 0<=residue<=len(eligible):raise ValueError('override rounding failed')
    for i in eligible[:residue]:units[i]+=1
    if sum(units.values())!=2000:raise ValueError('invalid adjusted rotation')
    return [units[i]/10 for i in range(len(raw))]

def rate(logs, col):
    pairs=[(finite(g.get(col)),finite(g.get('minutes'))) for g in logs]
    pairs=[(v,m) for v,m in pairs if v is not None and m is not None and m>0]
    return sum(v for v,m in pairs)/sum(m for v,m in pairs) if pairs else None

def attach_availability(players, entries, game_id, team):
    result=[{**p,'MinutesRiskFlags':risk_flags(p)} for p in players]
    relevant=[e for e in entries if e['game_id']==game_id and canon(e['team'])==canon(team)]
    if not relevant:return result
    locked={};settings={}
    for e in relevant:
        matches=[i for i,p in enumerate(players) if str(p['AthleteId'])==str(e['athlete_id'])]
        if len(matches)!=1 or matches[0] in locked:raise ValueError('unmatched or duplicate availability player')
        i=matches[0];locked[i]=float(e['minutes']);settings[i]=e
    allocation=allocate_fixed([float(p['Minutes']) for p in players],locked)
    for i,(p,m) in enumerate(zip(result,allocation)):
        e=settings.get(i);old=float(p['Minutes'])
        excluded=set(e.get('exclude_dates',[])) if e else set()
        logs=sorted([g for g in p.get('CurrentSeasonLog',[]) if g.get('date') not in excluded],key=lambda g:g['date'],reverse=True)
        if e and excluded and not logs:raise ValueError('no production games after exclusions')
        x={'ModelVersion':VERSION,'Minutes':m,'AvailabilityAdjustment':e or {'status':'redistributed','reason':'Team minutes redistributed around manual availability assumptions'},'OriginalMinutes':old,'ProductionGamesUsed':len(logs)}
        for stat,col in STATS.items():
            key='Baseline'+stat
            if e and excluded or old==0 and m>0:
                season=rate(logs,col);recent=rate(logs[:5],col)
                base=m*(.75*season+.25*(recent if recent is not None else season)) if season is not None else None
            else:
                v=finite(p.get(key));base=v*m/old if v is not None and old>0 else 0. if m==0 and v is not None else None
            pace=finite(p.get('PaceFactor'));defense=finite(p.get('OpponentDefenseFactor'));market=finite(p.get('MarketFactor'))
            adj=defense if stat=='Points' else clamp(1+(defense-1)*.20/.35,.92,1.08) if stat=='Assists' and defense is not None else 1.
            # Recover exact original assist matchup factor when available.
            if stat=='Assists' and finite(p.get('BaselineAssists')) not in (None,0) and finite(p.get('KenPomAssists')) is not None and pace:
                adj=p['KenPomAssists']/p['BaselineAssists']/pace
            x[key]=base
            x['KenPom'+stat]=base*pace*adj if base is not None and pace is not None and adj is not None else None
            mult=market if stat=='Points' else 1+.5*(market-1) if stat in ('Assists','Threes') and market is not None else 1.
            x['Vegas'+stat]=base*mult if base is not None and market is not None else None
            x['Combined'+stat]=x['KenPom'+stat]*mult if x['KenPom'+stat] is not None and market is not None else None
        if e:
            p['MinutesRiskFlags']+=['Manual availability scenario: '+e['reason']]
        p['ExperimentalModels']={**(p.get('ExperimentalModels') or {}),VERSION:x}
    return result
