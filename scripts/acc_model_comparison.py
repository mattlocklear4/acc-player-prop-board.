"""Paired prospective comparisons from identical archived snapshots."""
import math, statistics
from acc_grade_daily import norm
from acc_grade_pregame import select_snapshots, grade, summary
from acc_experimental_models import VERSIONS, SHOOTING
from acc_opponent_model import VERSION as OPPONENT_VERSION
from acc_rotation_model import VERSION as ROTATION_VERSION
from acc_distribution_model import VERSION as DISTRIBUTION_VERSION
from acc_combined_model import VERSION as COMBINED_VERSION
from acc_availability import VERSION as AVAILABILITY_VERSION

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

# V7 is a manual availability scenario with intentionally selective coverage.
# Keep its existing paired report, but do not let it shrink the all-model cohort.
COMMON_VERSIONS=('v4',*VERSIONS,OPPONENT_VERSION,ROTATION_VERSION,DISTRIBUTION_VERSION,COMBINED_VERSION)

def quote_key(q):
    return (q.get('game_id'),q.get('team'),norm(q.get('player')),q.get('market'),q.get('bookmaker'),q.get('side'),q.get('line'),q.get('american_odds'),q.get('quote_updated_utc'))

def reliability(rows):
    """Fixed probability buckets; exclude pushes just as in existing calibration."""
    bins=[]
    for lo,hi in ((0,.2),(.2,.4),(.4,.5),(.5,.6),(.6,.7),(.7,.8),(.8,1.0)):
        group=[r for r in rows if r['result'] in ('win','loss') and lo<=float(r['win_probability']) and (float(r['win_probability'])<hi or hi==1)]
        n=len(group)
        bins.append({'range':f'{lo:.0%}–{hi:.0%}','n':n,
                     'mean_probability':round(statistics.mean(float(r['win_probability']) for r in group),5) if n else None,
                     'observed_win_rate':round(sum(r['result']=='win' for r in group)/n,5) if n else None})
    return bins

def common_cohort(latest,odds,logs,today):
    """Rank models on identical prospective forecasts and settled quote sides."""
    forecasts={v:[] for v in COMMON_VERSIONS}
    quoted={v:[] for v in COMMON_VERSIONS}
    for _,r in latest.values():
        teams=[]
        for t in r['game'].get('teams') or []:
            ps=[p for p in t.get('players') or [] if all(v in (p.get('ExperimentalModels') or {}) for v in COMMON_VERSIONS[1:])]
            if ps:teams.append((t,ps))
        if not teams:continue
        for v in COMMON_VERSIONS:
            game={**r['game'],'teams':[{**t,'players':[p if v=='v4' else {**p,**p['ExperimentalModels'][v]} for p in ps]} for t,ps in teams]}
            forecasts[v].append({**r,'game':game,'quotes':[],'experimental_quotes':{}})
    for _,r in odds.values():
        pools={v:{quote_key(q):q for q in (r.get('quotes') or [] if v=='v4' else (r.get('experimental_quotes') or {}).get(v,[]))} for v in COMMON_VERSIONS}
        keys=set.intersection(*(set(p) for p in pools.values()))
        if not keys:continue
        for v in COMMON_VERSIONS:
            quoted[v].append({**r,'quotes':[pools[v][k] for k in sorted(keys,key=str)],'experimental_quotes':{}})
    ps={};qs={}
    for v in COMMON_VERSIONS:
        ps[v]={(p['date'],p['game_id'],p['team'],norm(p['player'])):p for p in grade(forecasts[v],logs,today)['projection_rows']}
        qs[v]={(q['date'],*quote_key(q)):q for q in grade(quoted[v],logs,today)['rows'] if q['result'] in ('win','loss','push')}
    pkeys=set.intersection(*(set(p) for p in ps.values()))
    qkeys=set.intersection(*(set(q) for q in qs.values()))
    qkeys={k for k in qkeys if len({qs[v][k]['result'] for v in COMMON_VERSIONS})==1}
    # Calibration: a single canonical side per player/market/line, regardless
    # of how many books repeat it. Prefer over, then stable lexical book.
    # Keep all matched quote sides for the separate hypothetical ROI report.
    unique={}
    for k in sorted(qkeys,key=lambda k:(qs['v4'][k]['side']!='over',str(k))):
        q=qs['v4'][k]
        outcome=(q['date'],q['game_id'],q['team'],norm(q['player']),q['market'],q['line'])
        unique.setdefault(outcome,k)
    keys_cal=list(unique.values())
    output={}
    for v in COMMON_VERSIONS:
        stats={}
        for stat in ('Minutes','Points','Rebounds','Assists','Threes'):
            keys=[k for k in pkeys if all(stat in ps[w][k]['stats'] for w in COMMON_VERSIONS)]
            stats[stat]=error_metrics([ps[v][k]['stats'][stat]['error'] for k in sorted(keys,key=str)])
        quotes=[qs[v][k] for k in sorted(qkeys,key=str)]
        cal=[qs[v][k] for k in keys_cal]
        output[v]={'projection_metrics':stats,'calibration':calibration(cal),
                   'calibration_by_market':{market:calibration([q for q in cal if q['market']==market]) for market in sorted({q['market'] for q in cal})},
                   'reliability':reliability(cal),
                   'positive_roi':summary([q for q in quotes if q['expected_roi_percent']>0]),
                   'roi_by_tier':{label:summary([q for q in quotes if lo<q['expected_roi_percent']<=hi]) for label,lo,hi in (('0–5%',0,5),('5–10%',5,10),('10–20%',10,20),('20%+',20,float('inf')))}}
    return {'versions':list(COMMON_VERSIONS),'paired_players':len(pkeys),'projection_games':len({k[:2] for k in pkeys}),
            'paired_settled_quote_sides':len(qkeys),'unique_outcomes':len(keys_cal),
            'quote_games':len({k[:2] for k in qkeys}),'models':output,
            'method':'All seven models must exist on the same archived forecast or quote. Calibration uses one side per player/market/line (prefer over), excluding pushes. ROI retains all common sportsbook quote sides; correlated lines and books are not independent. V7 is excluded from the common cohort because manual overrides are selective. No historical backfill.'}

def compare(records,logs,today):
    latest, odds, _=select_snapshots(records,lambda date:date<today)
    output={}
    for version in (*VERSIONS,AVAILABILITY_VERSION,OPPONENT_VERSION,ROTATION_VERSION,DISTRIBUTION_VERSION,COMBINED_VERSION):
        control_version=SHOOTING if version in (OPPONENT_VERSION,ROTATION_VERSION,DISTRIBUTION_VERSION) else None
        pc=[];pe=[];qc=[];qe=[]
        for _,r in latest.values():
            teams=[]
            for t in r['game'].get('teams') or []:
                ps=[p for p in t.get('players') or [] if version in (p.get('ExperimentalModels') or {}) and (not control_version or control_version in p['ExperimentalModels'])]
                if ps:teams.append((t,ps))
            if not teams:continue
            for dest,shadow in ((pc,False),(pe,True)):
                game={**r['game'],'teams':[{**t,'players':[({**p,**p['ExperimentalModels'][version]} if shadow else {**p,**p['ExperimentalModels'][control_version]} if control_version else p) for p in ps]} for t,ps in teams]}
                dest.append({**r,'game':game,'quotes':[]})
        for _,r in odds.values():
            if version not in (r.get('experimental_quotes') or {}):continue
            def key(q):return (q.get('game_id'),q.get('team'),norm(q.get('player')),q.get('market'),q.get('bookmaker'),q.get('side'),q.get('line'),q.get('american_odds'),q.get('quote_updated_utc'))
            c={key(q):q for q in ((r.get('experimental_quotes') or {}).get(control_version,[]) if control_version else r.get('quotes') or [])};e={key(q):q for q in r['experimental_quotes'][version]}
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
        output[version]={'control_model':control_version or 'v4 control','paired_players':len(cm.keys()&em.keys()),'projection_metrics':metrics,'paired_settled_quote_sides':len(cs),
            'control_calibration':calibration(cs),'experimental_calibration':calibration(es),
            'calibration_by_market':{market:{'control':calibration([q for q in cs if q['market']==market]),'experimental':calibration([q for q in es if q['market']==market])} for market in sorted({q['market'] for q in cs})},
            'control_positive_roi':summary([q for q in cs if q['expected_roi_percent']>0]),
            'experimental_positive_roi':summary([q for q in es if q['expected_roi_percent']>0])}
    return {'models':output,'common_cohort':common_cohort(latest,odds,logs,today),'method':'Prospective same-game, same-player and same archived quote comparisons. Lower MAE/RMSE/Brier/log loss is better. Each model selects its own positive ROI sides from the common quote pool; flat one-unit hypothetical results, correlated quotes not independent. No hindsight or backfilled forecasts. V8, V9 and V10 are paired against V6 to isolate opponent, rotation and probability-distribution adjustments; V11 combines the components and compares against V4, along with the earlier availability/rotation experiments. V4 remains the production control.'}
