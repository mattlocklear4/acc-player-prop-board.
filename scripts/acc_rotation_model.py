"""V9: role-aware rotation experiment, paired against V6.

Use only reconciled current-season completed game stints before the slate.
No inference of a player's availability from absent substitution rows.
"""
import csv,json,math
from collections import defaultdict,Counter
from datetime import datetime,timedelta
from research_engine import canon,STATS,clamp,allocate_team_minutes
from acc_experimental_models import SHOOTING,finite,shooting_rates
from acc_availability import VERSION as AVAILABILITY,allocate_fixed,rate
VERSION='v9-intelligent-rotation'
def elapsed(event):
    if not isinstance(event,dict):return None
    p=finite(event.get('period'));s=finite(event.get('secondsRemaining'))
    if p is None or s is None or p!=int(p) or p<1:return None
    length=1200 if p<=2 else 300
    if not 0<=s<=length:return None
    return (p-1)*1200+1200-s if p<=2 else 2400+(p-2)*300-s

def role(pos):
    n=str(pos or '').strip().upper().replace(' ','')
    if n in ('PG','SG','G','GUARD'):return 'G'
    if n in ('C','CENTER','F-C','C-F','FC','CF','PF'):return 'B'
    if n in ('F','SF','FORWARD','G-F','F-G','GF','FG','W','WING'):return 'W'
    return None

def validated_game(rows,box):
    """Reject missing, overlapping or inconsistent stints; reconcile with box minutes."""
    by=defaultdict(list);starts=defaultdict(list);ends=defaultdict(list);positions=defaultdict(list);endmargin=[]
    if not box or not rows:return None
    for r in rows:
        aid=str(r.get('athleteId') or '')
        a,b=elapsed(r.get('subIn')),elapsed(r.get('subOut'))
        if aid not in box or a is None or b is None or b<a:return None
        if a==b:continue
        by[aid].append((a,b));starts[a].append(aid);ends[b].append(aid)
        positions[aid].append(role(r.get('position')))
        e=r['subOut'];s,t=finite(e.get('teamPoints')),finite(e.get('opponentPoints'))
        if s is not None and t is not None and b>=2100:endmargin.append((b,s-t))
    if not by:return None
    end=max(ends)
    if end<2400 or end>3600 or (end-2400)%300:return None
    if set(by)!=set(box):return None
    for aid,intervals in by.items():
        intervals.sort()
        if any(a<prev[1] for prev,(a,b) in zip(intervals,intervals[1:])):return None
        if abs(sum(b-a for a,b in intervals)/60-box[aid]['minutes'])>2:return None
    # All five-player intervals must be accounted for. Permit <=30 seconds of feed artifacts.
    active=0;prev=0;bad=0
    for t in sorted(set(starts)|set(ends)):
        if active!=5:bad+=t-prev
        active+=len(starts[t])-len(ends[t]);prev=t
    if bad>30 or active!=0:return None
    swaps=Counter()
    for t,outs in ends.items():
        if t<=0 or t>=end or t in (1200,2400):continue
        ins=starts.get(t,[])
        for a in outs:
            for b in ins:
                if a!=b:swaps[tuple(sorted((a,b)))]+=1/max(1,len(outs),len(ins))
    # Use only actual end-of-game score snapshots for close/blowout classification.
    margins=[m for t,m in endmargin if t==end]
    margin=margins[0] if margins and len(set(margins))==1 else None
    return {'box':box,'positions':{k:Counter(v for v in vs if v).most_common(1)[0][0] for k,vs in positions.items() if any(vs)},'swaps':swaps,'margin':margin}

def load_rotation(root,now,day):
    try:
        path=root/'data/cbbd'
        summary=json.loads((path/'acc_substitution_summary_2027.json').read_text())
        ts=datetime.fromisoformat(summary['last_successful_run_utc'].replace('Z','+00:00'))
        if ts.tzinfo is None or not timedelta(0)<=now-ts<=timedelta(hours=36) or summary.get('season')!=2027:return {}
        data=json.loads((path/'acc_substitutions_2027.json').read_text())
        boxes=defaultdict(dict);teamids={}
        with (path/'acc_player_games_2027.csv').open(newline='',encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('season')!='2027' or not r.get('game_date') or r['game_date']>=day:continue
                mins=finite(r.get('minutes'));aid=str(r.get('athlete_id') or '')
                if mins is None or mins<=0 or not aid:continue
                k=(canon(r['team']),str(r['game_id']))
                boxes[k][aid]={'minutes':mins,'date':r['game_date'],'fouls':finite(r.get('fouls')),'position':role(r.get('position'))}
                teamids[k]=str(r.get('team_id'))
        result={}
        for team,rows in data.items():
            k=canon(team);games=defaultdict(list)
            for r in rows:
                gid=str(r.get('gameId'));ident=(k,gid)
                if ident in boxes and str(r.get('teamId'))==teamids[ident] and canon(r.get('team'))==k:
                    games[gid].append(r)
            good=[]
            for gid,rs in games.items():
                v=validated_game(rs,boxes[k,gid])
                if v:good.append(v)
            if good:result[k]={'games':good,'snapshot_utc':ts.isoformat(),'candidate_games':len([x for x in boxes if x[0]==k])}
        return result
    except (OSError,ValueError,TypeError,KeyError,AttributeError):return {}

def transfer(minutes,players,locks,positions,swaps):
    """Adjust unlocked players by role and empirical simultaneous substitution affinity."""
    raw=list(minutes);free=[i for i in range(len(raw)) if i not in locks]
    for i,target in locks.items():
        delta=target-raw[i];raw[i]=target
        if abs(delta)<1e-8:continue
        aid=str(players[i]['AthleteId']);remaining=abs(delta)
        while remaining>1e-7:
            candidates=[j for j in free if (raw[j]>1e-7 if delta>0 else raw[j]<40-1e-7)]
            if not candidates:raise ValueError('Insufficient rotation capacity')
            weights={}
            for j in candidates:
                bid=str(players[j]['AthleteId']);a,b=positions.get(aid),positions.get(bid)
                similarity=1 if not a or not b else 4 if a==b else 1.5 if 'W' in (a,b) else .15
                evidence=swaps.get(tuple(sorted((aid,bid))),0)
                capacity=raw[j] if delta>0 else 40-raw[j]
                weights[j]=capacity*(similarity+min(8,evidence))
            total=sum(weights.values())
            if total<=0:raise ValueError('No substitution capacity')
            taken=0
            for j in candidates:
                cap=raw[j] if delta>0 else 40-raw[j]
                amount=min(cap,remaining*weights[j]/total)
                raw[j]+=(-amount if delta>0 else amount);taken+=amount
            if taken<1e-9:raise ValueError('No progress allocating rotation')
            remaining-=taken
    return allocate_fixed(raw,locks)

def attach_rotation(players,team,context,market=None):
    def absent(reason):return [{**p,'RotationModelStatus':reason} for p in players]
    data=context.get(canon(team))
    if not data or len(data['games'])<2:return absent('insufficient_reconciled_substitution_games')
    if not players or any(SHOOTING not in p.get('ExperimentalModels',{}) for p in players):return absent('v6_rotation_unavailable')
    games=data['games'];pos=defaultdict(list);swaps=Counter()
    for g in games:
        swaps.update(g['swaps'])
        for aid,r in g['box'].items():
            if g['positions'].get(aid) or r['position']:pos[aid].append(g['positions'].get(aid) or r['position'])
    positions={aid:Counter(v).most_common(1)[0][0] for aid,v in pos.items()}
    base=[p['ExperimentalModels'][SHOOTING]['Minutes'] for p in players]
    locked={};manual={};raw=[];details=[]
    spread=finite((market or {}).get('team_spread'))
    for i,p in enumerate(players):
        aid=str(p['AthleteId']);v7=p['ExperimentalModels'].get(AVAILABILITY,{})
        e=v7.get('AvailabilityAdjustment') or {}
        if e and e.get('status')!='redistributed':
            locked[i]=float(e['minutes']);manual[i]=e
        rows=[g['box'][aid] for g in games if aid in g['box']]
        close=[g['box'][aid]['minutes'] for g in games if aid in g['box'] and g['margin'] is not None and abs(g['margin'])<=12]
        blow=[g['box'][aid]['minutes'] for g in games if aid in g['box'] and g['margin'] is not None and abs(g['margin'])>=18]
        signal=base[i];adjustment=0
        # Only adjust for spread when both game contexts have enough samples;
        # do not infer a projected blowout from a stale or absent market.
        if spread is not None and len(close)>=2 and len(blow)>=2:
            target=sum((blow if abs(spread)>=14 else close))/len(blow if abs(spread)>=14 else close)
            adjustment=clamp(.25*(target-signal),-3,3)
            signal=clamp(signal+adjustment,0,40)
        foul=[r['fouls'] for r in rows if r['fouls'] is not None]
        raw.append(signal)
        details.append({'role':positions.get(aid),'matched_appearances':len(rows),'close_games':len(close),'blowout_games':len(blow),'spread_adjustment_minutes':round(adjustment,2),'high_foul_games':sum(f>=4 for f in foul),'foul_sample':len(foul)})
    try:
        baseline=allocate_team_minutes(raw)
        mins=transfer(baseline,players,locked,positions,swaps) if locked else baseline
    except ValueError:return absent('rotation_capacity_unavailable')
    out=[]
    for i,(p,m) in enumerate(zip(players,mins)):
        v=p['ExperimentalModels'][SHOOTING];old=v['Minutes']
        if old<=0 and m>0:return absent('missing_rate_for_new_minutes')
        x={**v,'ModelVersion':VERSION,'Minutes':m}
        for stat in STATS:
            for prefix in ('Baseline','KenPom','Vegas','Combined'):
                k=prefix+stat;val=finite(v.get(k))
                x[k]=val*m/old if val is not None and old>0 else 0. if val is not None and m==0 else None
        e=manual.get(i);excluded=set(e.get('exclude_dates',[])) if e else set()
        if excluded:
            logs=sorted([g for g in p.get('CurrentSeasonLog',[]) if g['date'] not in excluded],key=lambda g:g['date'],reverse=True)
            if not logs:return absent('no_production_after_manual_exclusion')
            # Refit V6 shot volume on the remaining current-season games.
            shot=shooting_rates(logs)
            for stat,col in STATS.items():
                a,b=rate(logs,col),rate(logs[:5],col)
                x['Baseline'+stat]=m*(.75*a+.25*(b if b is not None else a)) if a is not None else None
            if shot:
                c=shot['components'];att={k:m*z['attempts_per_minute'] for k,z in c.items()}
                x['BaselinePoints']=2*att['2P']*c['2P']['expected_pct']+3*att['3P']*c['3P']['expected_pct']+att['FT']*c['FT']['expected_pct']
                x['BaselineThrees']=att['3P']*c['3P']['expected_pct'];x['ShotInputs']={**shot,'projected_attempts':att}
            else:
                x.pop('ShotInputs',None);x['ShotStatus']='fallback_rotation_only_missing_shots'
            pace=finite(p.get('PaceFactor'));defense=finite(p.get('OpponentDefenseFactor'));mf=finite(p.get('MarketFactor'))
            for stat in STATS:
                b=x['Baseline'+stat]
                d=defense if stat=='Points' else clamp(1+(defense-1)*.20/.35,.92,1.08) if stat=='Assists' and defense is not None else 1.
                if stat=='Assists' and finite(p.get('BaselineAssists')) not in (None,0) and finite(p.get('KenPomAssists')) is not None and pace:d=p['KenPomAssists']/p['BaselineAssists']/pace
                x['KenPom'+stat]=b*pace*d if b is not None and pace is not None and d is not None else None
                mult=mf if stat=='Points' else 1+.5*(mf-1) if stat in ('Assists','Threes') and mf is not None else 1.
                x['Vegas'+stat]=b*mult if b is not None and mf is not None else None
                x['Combined'+stat]=x['KenPom'+stat]*mult if x['KenPom'+stat] is not None and mf is not None else None
        elif x.get('ShotInputs') and old>0:
            shot=x['ShotInputs'];x['ShotInputs']={**shot,'projected_attempts':{k:a*m/old for k,a in shot['projected_attempts'].items()}}
        x['IntelligentRotation']={**details[i],'source_utc':data['snapshot_utc'],'reconciled_games':len(games),'candidate_games':data['candidate_games'],'v6_minutes':old,'manual_minutes':locked.get(i),'manual_excluded_games':sorted(excluded),'role_weighted_redistribution':bool(locked),'spread_available':spread is not None,'direct_swap_pairs':sum(1 for pair in swaps if str(p['AthleteId']) in pair),'foul_context':'Box-score 4+ fouls, not timing of foul trouble'}
        out.append({**p,'RotationModelStatus':'available','ExperimentalModels':{**p['ExperimentalModels'],VERSION:x}})
    return out
