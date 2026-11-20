#!/usr/bin/env python3
"""Friday minutes/usage diagnostic from existing box-score data. Read-only.
Does NOT silently change official projections or assume an injury is confirmed.
"""
import csv,json,statistics
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

def num(x):
    try:return float(x) if str(x or '').strip() else None
    except ValueError:return None
def avg(v):
    return round(sum(v)/len(v),2) if v else None
root=Path('data/cbbd')
with (root/'acc_player_games_2027.csv').open(newline='',encoding='utf-8-sig') as f:logs=list(csv.DictReader(f))
slate=json.loads(Path('research/acc_friday_slate.json').read_text())
date=slate['date_eastern']
by_player=defaultdict(list)
for r in logs:
    if r.get('game_date','')<date and r.get('athlete_id'):by_player[(r['team'],r['athlete_id'])].append(r)
flags=[]
flagpath=Path('data/acc_friday_availability_review.csv')
if flagpath.exists():
    with flagpath.open(newline='',encoding='utf-8-sig') as f:flags=list(csv.DictReader(f))
flagmap={(r['team'].strip().lower(),r['player'].strip().lower()):r for r in flags}
rows=[]
for game in slate['games']:
    for team in game['teams']:
        for p in team['players']:
            history=sorted(by_player.get((team['team'],str(p.get('AthleteId'))),[]),key=lambda r:r['game_date'],reverse=True)
            minutes=[num(r.get('minutes')) for r in history]
            minutes=[v for v in minutes if v is not None]
            usage=[num(r.get('usage_pct')) for r in history[:5]]
            usage=[v for v in usage if v is not None]
            starts=sum(str(r.get('starter')).lower()=='true' for r in history[:5])
            # Weighted recent-game signal, not an injury-adjusted minute projection.
            last3=minutes[:3];last5=minutes[:5]
            recent=avg(last3);season=avg(minutes)
            sample=(0.65*recent+0.35*season) if recent is not None and season is not None else season
            flag=flagmap.get((team['team'].lower(),p['Player'].lower()))
            risk='availability_review' if flag else ('limited_sample' if len(minutes)<4 else 'minutes_volatile' if len(last5)>=3 and statistics.pstdev(last5)>7 else 'normal')
            rows.append({'game_id':game['game_id'],'team':team['team'],'player':p['Player'],'athlete_id':p.get('AthleteId'),
                         'model_minutes':round(p['Minutes'],2) if p.get('Minutes') is not None else None,
                         'season_minutes':season,'last3_minutes':recent,'last5_minutes':avg(last5),
                         'last5_minutes_sd':round(statistics.pstdev(last5),2) if len(last5)>=2 else None,
                         'recent_weighted_minutes_signal':round(sample,2) if sample is not None else None,
                         'starts_last5':starts,'games_last5':len(history[:5]),'usage_pct_last5':avg(usage),
                         'minutes_sample_size':len(minutes),'risk':risk,
                         'availability_status':flag.get('status') if flag else None,
                         'availability_source':flag.get('source_url') if flag else None})
# Exploratory rotation-adjusted scenario. Never overwrite verified baseline.
# Keep known-out players at zero; leave reported injuries as review flags.
by_team=defaultdict(list)
for row in rows:by_team[(row['game_id'],row['team'])].append(row)
for teamrows in by_team.values():
    for row in teamrows:
        model=row['model_minutes']
        signal=row['recent_weighted_minutes_signal']
        if row['availability_status']=='out':candidate=0.0
        elif model is None:candidate=0.0
        elif signal is None:candidate=model
        else:
            candidate=.45*model+.55*signal
            if row['starts_last5']>=3 and row['games_last5']>=3:candidate+=.7
        row['rotation_minutes_raw']=round(max(0,min(40,candidate)),2)
    # Regulation basketball provides 200 team-minutes. Scale only when
    # at least eight players have a meaningful sample; cap any player at 40.
    active=[r for r in teamrows if r['rotation_minutes_raw']>0]
    if len(active)<8:
        for r in teamrows:r['rotation_minutes_scenario']=None
        continue
    allocation={id(r):r['rotation_minutes_raw'] for r in active}
    for _ in range(20):
        deficit=200-sum(allocation.values())
        if abs(deficit)<.01:break
        eligible=[r for r in active if (allocation[id(r)]<39.99 if deficit>0 else allocation[id(r)]>0.01)]
        if not eligible:break
        weights=[max(1,r['rotation_minutes_raw']) for r in eligible]
        total=sum(weights)
        for r,w in zip(eligible,weights):
            old=allocation[id(r)]
            allocation[id(r)]=max(0,min(40,old+deficit*w/total))
    for r in teamrows:
        r['rotation_minutes_scenario']=round(allocation.get(id(r),0),2)
        r['rotation_minutes_delta']=round(r['rotation_minutes_scenario']-(r['model_minutes'] or 0),2)
dest=Path('research/acc_friday_minutes_review.json')
dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps({'date_eastern':date,'rows':rows,'flagged':sum(r['risk']!='normal' for r in rows),
                            'note':'Research-only 200-minute rotation scenarios use last 3/5 games, starting frequency and confirmed out statuses. Reported injuries require confirmation. Do not overwrite official projections without review.'},indent=2)+'\n')
print(json.dumps({'minute_rows':len(rows),'flagged_for_review':sum(r['risk']!='normal' for r in rows)}))
