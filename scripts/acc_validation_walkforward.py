#!/usr/bin/env python3
"""Leakage-safe current-season ACC baseline walk-forward validation (offline).

At each date, rebuild the actual live baseline from strictly earlier games.
No historical sportsbook prices are fabricated. No KenPom snapshot is reused
retroactively. All metrics are descriptive, not betting validation.
"""
import json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from research_engine import ROOT,STATS,build_baselines,read_csv,numeric

def evaluate(root=ROOT, min_prior=1):
    games=read_csv(root/'data/cbbd/acc_player_games_2027.csv')
    dates=sorted({r['game_date'] for r in games if r.get('game_date')})
    bydate=defaultdict(list)
    for r in games:
        if r.get('game_date'):bydate[r['game_date']].append(r)
    prior=defaultdict(int); observations=[]
    for day in dates:
        baselines={str(p['AthleteId']):p for p in build_baselines(day,root)}
        for r in bydate[day]:
            aid=str(r.get('athlete_id') or '')
            b=baselines.get(aid)
            if not b or prior[aid]<min_prior:continue
            row={'date':day,'athlete_id':aid,'player':r.get('player'),
                 'team':r.get('team'),'prior_current_games':prior[aid]}
            for stat,col in [('Minutes','minutes')]+list(STATS.items()):
                actual=numeric(r.get(col))
                if actual is None and stat=='Rebounds':
                    o,d=numeric(r.get('oreb')),numeric(r.get('dreb'))
                    actual=o+d if o is not None and d is not None else None
                pred=numeric(b.get('Minutes' if stat=='Minutes' else 'Baseline'+stat))
                if actual is not None and pred is not None:
                    row[stat]={'predicted':round(pred,4),'actual':actual,'error':round(pred-actual,4)}
            observations.append(row)
        for r in bydate[day]:
            if r.get('athlete_id'):prior[str(r['athlete_id'])]+=1
    metrics={}
    for stat in ['Minutes']+list(STATS):
        pairs=[o[stat] for o in observations if stat in o]
        errors=[p['error'] for p in pairs]
        metrics[stat]={'n':len(errors),'mae':round(statistics.mean(map(abs,errors)),3) if errors else None,
                       'rmse':round(math.sqrt(statistics.mean(x*x for x in errors)),3) if errors else None,
                       'bias':round(statistics.mean(errors),3) if errors else None}
    return {'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'status':'DESCRIPTIVE_WALK_FORWARD_NOT_BETTING_VALIDATED',
            'method':'Live baseline rebuilt per game date, strict earlier-game cutoff; no opponent or retroactive KenPom adjustments',
            'minimum_prior_current_games':min_prior,'dates_evaluated':len(dates),
            'player_game_observations':len(observations),'metrics':metrics,
            'limitations':['Only players with earlier current-season games and a model baseline qualify',
                           'No historical pregame sportsbook lines; ROI/CLV/Brier/log loss not measurable',
                           'Same-date games excluded from inputs; historic prior seasons used by live baseline',
                           'Not a test of live KenPom or injury-adjusted projections'],
            'recent_observations':observations[-100:]}
if __name__=='__main__':
    output=ROOT/'data'/'validation_summary.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    result=evaluate()
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'observations':result['player_game_observations'],'metrics':result['metrics']}))
