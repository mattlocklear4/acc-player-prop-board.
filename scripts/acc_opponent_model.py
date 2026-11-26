"""V8: prospective current-season opponent-specific matchup adjustment.

Keep V6 minutes and per-minute shooting model fixed to isolate matchup effects.
Raw national totals stay in private cache. No historical backfill.
"""
import json, math
from datetime import datetime,timedelta,timezone
from research_engine import canon,clamp,STATS
from supabase_kenpom import OPPONENT_ALIASES
from acc_experimental_models import SHOOTING,finite

VERSION='v8-opponent-specific'
# Intentionally conservative research priors, not fitted coefficients.
SHRINK_GAMES=8
def ratio(a,b):return a/b if a is not None and b is not None and b>0 else None
def key(name):
    k=canon(name)
    return OPPONENT_ALIASES.get(k,k)
def nested(s,k,f):return finite((s.get(k) or {}).get(f))
def count(s,k):return finite(s.get(k))
def metrics(r):
    a,o=r.get('teamStats') or {},r.get('opponentStats') or {}
    ap,op=count(a,'possessions'),count(o,'possessions')
    if not ap or not op or min(ap,op)<100:return None
    def miss(s,p):
        fa,fm=nested(s,'fieldGoals','attempted'),nested(s,'fieldGoals','made')
        ta,tm=nested(s,'freeThrows','attempted'),nested(s,'freeThrows','made')
        if any(v is None for v in (fa,fm,ta,tm)) or fm>fa or tm>ta or min(fa,fm,ta,tm)<0:return None
        return (fa-fm+.44*(ta-tm))/p
    def fg_pct(s,k):
        m,a=nested(s,k,'made'),nested(s,k,'attempted')
        return ratio(m,a) if m is not None and a is not None and 0<=m<=a else None
    out={'two_pct':fg_pct(o,'twoPointFieldGoals'),'three_pct':fg_pct(o,'threePointFieldGoals'),
         'two_attempt_rate':ratio(nested(o,'twoPointFieldGoals','attempted'),op),
         'three_attempt_rate':ratio(nested(o,'threePointFieldGoals','attempted'),op),
         'ft_attempt_rate':ratio(nested(o,'freeThrows','attempted'),op),
         'assists_rate':ratio(count(o,'assists'),op),
         'off_miss_rate':miss(o,op),'def_miss_rate':miss(a,ap),
         'opp_orb_share':ratio(nested(o,'rebounds','offensive'),(nested(o,'rebounds','offensive') or 0)+(nested(a,'rebounds','defensive') or 0)),
         'team_orb_share':ratio(nested(a,'rebounds','offensive'),(nested(a,'rebounds','offensive') or 0)+(nested(o,'rebounds','defensive') or 0))}
    if any(v is None or not math.isfinite(v) or v<0 or v>2 for v in out.values()):return None
    if any(not 0<v<1 for k,v in out.items() if k.endswith('share') or k.endswith('pct')):return None
    g=finite(r.get('games'))
    if not g or g<3:return None
    return {'games':int(g),'possessions':op,**out}

def load_context(root,now,kp):
    """A dated pregame national snapshot, never use today's later results or stale totals."""
    try:
        path=root/'data/cbbd'
        summary=json.loads((path/'acc_team_collection_summary_2027.json').read_text())
        timestamp=datetime.fromisoformat(summary['last_successful_run_utc'].replace('Z','+00:00'))
        if timestamp.tzinfo is None or not timedelta(0)<=now-timestamp<=timedelta(hours=36):return None
        rows=json.loads((path/'d1_team_stats_2027.json').read_text())
        if summary.get('national_team_count')!=len(rows) or not 300<=len(rows)<=400:return None
        teams={}
        # Match exact canonical school names to verified D1 ratings; ignore non-D1 and ambiguous keys.
        kpkeys={key(x['Team']) for x in kp.values()}
        seen=set()
        for row in rows:
            if row.get('season')!=2027 or not row.get('team'):continue
            k=key(row['team'])
            if k not in kpkeys:continue
            if k in seen:teams.pop(k,None);continue
            seen.add(k)
            m=metrics(row)
            if m:teams[k]=m
        if len(teams)<280:return None
        names=[k for k in next(iter(teams.values())) if k not in ('games','possessions')]
        denom=sum(r['possessions'] for r in teams.values())
        league={k:sum(r[k]*r['possessions'] for r in teams.values())/denom for k in names}
        if any(v<=0 for v in league.values()):return None
        return {'teams':teams,'league':league,'timestamp':timestamp.isoformat(),'coverage':len(teams)}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):return None

def factors(m,league):
    # Per-possession opportunity factors and conversion rates; shrink small samples.
    w=m['games']/(m['games']+SHRINK_GAMES)
    def f(k,strength=.5,lo=.88,hi=1.12):
        return clamp(1+strength*w*(m[k]/league[k]-1),lo,hi)
    def share(k,complement=False):
        a,b=m[k],league[k]
        if complement:a,b=1-a,1-b
        return clamp(1+.5*w*(a/b-1),.92,1.08)
    return {'2P_eff':f('two_pct',.65),'3P_eff':f('three_pct',.65),
            '2PA':f('two_attempt_rate',.35),'3PA':f('three_attempt_rate',.35),
            'FTA':f('ft_attempt_rate',.5),'AST':f('assists_rate',.5),
            'OREB':clamp(f('off_miss_rate')*share('opp_orb_share'),.85,1.15),
            'DREB':clamp(f('def_miss_rate')*share('team_orb_share',True),.85,1.15)}

def attach_matchup(players,opponent,context):
    def absent(reason):return [{**p,'OpponentModelStatus':reason} for p in players]
    if not context:return absent('national_snapshot_unavailable_or_stale')
    m=context['teams'].get(key(opponent))
    if not m:return absent('opponent_missing_or_insufficient_current_season_sample')
    if not players or any(not (p.get('ExperimentalModels') or {}).get(SHOOTING) for p in players):
        return absent('v6_rotation_unavailable')
    f=factors(m,context['league']);out=[]
    for p in players:
        v=p['ExperimentalModels'][SHOOTING]
        x={**v,'ModelVersion':VERSION}
        pace=finite(p.get('PaceFactor'));market=finite(p.get('MarketFactor'))
        if pace is None:return absent('pace_missing')
        # Replace generic defensive factor for points/assists; do not stack it.
        shot=v.get('ShotInputs');fallback=[]
        if shot:
            c=shot['components'];a=shot['projected_attempts']
            threes=a['3P']*f['3PA']*clamp(c['3P']['expected_pct']*f['3P_eff'],0,1)
            twos=a['2P']*f['2PA']*clamp(c['2P']['expected_pct']*f['2P_eff'],0,1)
            ft=a['FT']*f['FTA']*c['FT']['expected_pct']
            x['KenPomPoints']=(2*twos+3*threes+ft)*pace
            x['KenPomThrees']=threes*pace
        else:fallback+=['Points','Threes']
        logs=p.get('CurrentSeasonLog') or []
        pairs=[(finite(g.get('oreb')),finite(g.get('dreb'))) for g in logs]
        valid=[(a,b) for a,b in pairs if a is not None and b is not None and a>=0 and b>=0]
        total=sum(a+b for a,b in valid)
        share=sum(a for a,b in valid)/total if total>0 and len(valid)>=.8*len(logs) else None
        reb=finite(v.get('BaselineRebounds'));ast=finite(v.get('BaselineAssists'))
        if reb is not None and share is not None:
            x['KenPomRebounds']=reb*pace*(share*f['OREB']+(1-share)*f['DREB'])
        else:fallback.append('Rebounds')
        if ast is not None:x['KenPomAssists']=ast*pace*f['AST']
        else:fallback.append('Assists')
        for stat in STATS:
            val=finite(x.get('KenPom'+stat))
            mult=market if stat=='Points' else 1+.5*(market-1) if stat in ('Assists','Threes') and market is not None else 1
            x['Combined'+stat]=val*mult if val is not None and market is not None else None
        x['OpponentAdjustment']={'base_model':SHOOTING,'snapshot_utc':context['timestamp'],'opponent_games':m['games'],
                                 'national_teams':context['coverage'],'factors':{k:round(a,4) for k,a in f.items()},
                                 'offensive_rebound_share':share,'fallback_stats':fallback}
        out.append({**p,'OpponentModelStatus':'available','ExperimentalModels':{**p['ExperimentalModels'],VERSION:x}})
    return out
