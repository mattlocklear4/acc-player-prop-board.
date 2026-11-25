"""Paired prospective comparisons from identical archived snapshots."""
import math, statistics
from acc_grade_daily import norm
from acc_grade_pregame import select_snapshots, grade, summary
from acc_experimental_models import VERSIONS

def error_metrics(errors):
    return {'n':len(errors),'mae':round(statistics.mean(map(abs,errors)),3) if errors else None,
            'rmse':round(math.sqrt(statistics.mean(e*e for e in errors)),3) if errors else None,
            'bias':round(statistics.mean(errors),3) if errors else None}

def calibration(rows):
    brier=[];loss=[]
    for r in rows:
        if r['result'] not in ('win','loss'):continue
        y=int(r['result']=='win');p=float(r['win_probability']);c=min(1-1e-12,max(1e-12,p))
        brier.append((p-y)**2);loss.append(-(y*math.log(c)+(1-y)*math.log(1-c)))
    return {'n':len(brier),'brier':round(statistics.mean(brier),5) if brier else None,'log_loss':round(statistics.mean(loss),5) if loss else None}

def compare(records,logs,today):
    latest, odds, _=select_snapshots(records,lambda date:date<today)
    output={}
    for version in VERSIONS:
        pc=[];pe=[];qc=[];qe=[]
        for _,r in latest.values():
            teams=[]
            for t in r['game'].get('teams') or []:
                ps=[p for p in t.get('players') or [] if version in (p.get('ExperimentalModels') or {})]
                if ps:teams.append((t,ps))
            if not teams:continue
            for dest,shadow in ((pc,False),(pe,True)):
                game={**r['game'],'teams':[{**t,'players':[({**p,**p['ExperimentalModels'][version]} if shadow else p) for p in ps]} for t,ps in teams]}
                dest.append({**r,'game':game,'quotes':[]})
        for _,r in odds.values():
            if version not in (r.get('experimental_quotes') or {}):continue
            def key(q):return (q.get('game_id'),q.get('team'),norm(q.get('player')),q.get('market'),q.get('bookmaker'),q.get('side'),q.get('line'),q.get('american_odds'),q.get('quote_updated_utc'))
            c={key(q):q for q in r.get('quotes') or []};e={key(q):q for q in r['experimental_quotes'][version]}
            common=c.keys()&e.keys()
            qc.append({**r,'quotes':[c[k] for k in common]});qe.append({**r,'quotes':[e[k] for k in common]})
        c=grade(pc,logs,today);e=grade(pe,logs,today)
        def pkey(p):return (p['date'],p['game_id'],p['team'],norm(p['player']))
        cm={pkey(p):p for p in c['projection_rows']};em={pkey(p):p for p in e['projection_rows']}
        metrics={}
        for stat in ('Minutes','Points','Rebounds','Assists','Threes'):
            pairs=[(cm[k]['stats'][stat]['error'],em[k]['stats'][stat]['error']) for k in cm.keys()&em.keys() if stat in cm[k]['stats'] and stat in em[k]['stats']]
            metrics[stat]={'control':error_metrics([a for a,b in pairs]),'experimental':error_metrics([b for a,b in pairs])}
        cq=grade(qc,logs,today)['rows'];eq=grade(qe,logs,today)['rows']
        def qkey(q):return (q['date'],q['game_id'],q['team'],norm(q['player']),q['market'],q['bookmaker'],q['side'],q['line'],q['american_odds'],q['quote_updated_utc'])
        ca={qkey(q):q for q in cq};ea={qkey(q):q for q in eq};keys=ca.keys()&ea.keys()
        cs=[ca[k] for k in keys if ca[k]['result'] in ('win','loss','push') and ea[k]['result']==ca[k]['result']]
        es=[ea[qkey(q)] for q in cs]
        output[version]={'paired_players':len(cm.keys()&em.keys()),'projection_metrics':metrics,'paired_settled_quote_sides':len(cs),
            'control_calibration':calibration(cs),'experimental_calibration':calibration(es),
            'control_positive_roi':summary([q for q in cs if q['expected_roi_percent']>0]),
            'experimental_positive_roi':summary([q for q in es if q['expected_roi_percent']>0])}
    return {'models':output,'method':'Prospective same-game, same-player and same archived quote comparisons. Lower MAE/RMSE/Brier/log loss is better. Each model selects its own positive ROI sides from the common quote pool; flat one-unit hypothetical results, correlated quotes not independent. No hindsight or backfilled forecasts. v4 remains production.'}
