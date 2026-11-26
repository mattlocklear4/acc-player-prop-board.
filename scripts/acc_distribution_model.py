"""V10: conditional-on-playing, current-season count distributions.

Same exact V6 means/minutes, new dispersion only. Provisional priors, no fit
to future outcomes. Negative binomial when variance exceeds mean; Poisson
otherwise. Do not infer DNP settlement or model participation probability.
"""
import math,statistics
from acc_experimental_models import SHOOTING,finite
from research_engine import STATS,clamp
VERSION='v10-player-distributions'
PRICING='player-count-dispersion-v1'
PRIOR_GAMES=8
MIN_SAMPLE=3
def var(xs):return statistics.variance(xs) if len(xs)>=2 else 0.
def shrink(observed,prior,n):
    w=n/(n+PRIOR_GAMES) if n>=MIN_SAMPLE else 0.
    return w*observed+(1-w)*prior,w

def shot_variance(logs,shot,minutes,mean_minutes):
    if not shot or mean_minutes<=0:return None
    c=shot.get('components') or {};a=shot.get('projected_attempts') or {}
    if not all(k in c and k in a for k in ('2P','3P','FT')):return None
    rates={k:finite(c[k].get('expected_pct')) for k in c if k in ('2P','3P','FT')}
    if any(v is None or not 0<=v<=1 for v in rates.values()):return None
    weights={'2P':2,'3P':3,'FT':1}
    rows=[]
    for g in logs:
        m,fga,three,fta=[finite(g.get(k)) for k in ('minutes','fga','three_pa','fta')]
        if any(v is None for v in (m,fga,three,fta)) or m<=0 or not 0<=three<=fga or fta<0:continue
        rows.append((m,{'2P':fga-three,'3P':three,'FT':fta}))
    if len(rows)<MIN_SAMPLE or sum(m for m,_ in rows)<.8*sum(finite(g.get('minutes')) or 0 for g in logs):return None
    exposure=sum(m for m,_ in rows)
    observed={k:sum(x[k] for _,x in rows)/exposure for k in weights}
    volume=var([sum(weights[k]*rates[k]*(x[k]-observed[k]*m) for k in weights) for m,x in rows])*minutes/(exposure/len(rows))
    conversion=sum(weights[k]**2*a[k]*rates[k]*(1-rates[k]) for k in weights)
    return {'volume_variance':max(0.,volume),'conversion_variance':max(0.,conversion),'sample':len(rows)}

def distribution(logs,stat,col,mean,minutes,shot=None):
    if mean is None or minutes is None or mean<0 or minutes<0:return None
    if mean==0:
        return {'family':'poisson','mean':0.,'variance':0.,'sd':0.,'dispersion':0.,'sample':0,'status':'zero_mean','conditional_on_playing':True}
    pairs=[]
    for g in logs:
        m,y=finite(g.get('minutes')),finite(g.get(col))
        if m is not None and m>0 and y is not None and y>=0:pairs.append((m,y))
    n=len(pairs)
    prior=max(mean,30.25*min(1.,mean/12.)) if stat=='Points' else mean
    prior_minute_var=16.
    observed_minutes=var([m for m,_ in pairs]) if n>=MIN_SAMPLE else prior_minute_var
    minutes_var,w=shrink(observed_minutes,prior_minute_var,n)
    minutes_var=clamp(minutes_var,0.,100.)
    exposure=sum(m for m,_ in pairs)
    avg_minutes=exposure/n if n else None
    observed_rate=sum(y for _,y in pairs)/exposure if exposure else None
    # Residual conditional production variation, then a separate exposure term.
    residual=None;minute_component=(mean/minutes)**2*minutes_var if minutes>0 else 0.
    if n>=MIN_SAMPLE and avg_minutes and observed_rate is not None:
        residual=var([y-observed_rate*m for m,y in pairs])*minutes/avg_minutes
    structure=shot_variance(logs,shot,minutes,avg_minutes or 0.) if stat=='Points' else None
    # The structural shot term is a shrinkage target, not added on top of
    # empirical scoring residuals (which already include volume and conversion).
    target=prior
    if structure:
        structural=structure['volume_variance']+structure['conversion_variance']+minute_component
        target=.5*prior+.5*structural
    estimate=(residual+minute_component) if residual is not None else target
    variance,_=shrink(estimate,target,n)
    # Small sample safeguards: conservative count variance floor and finite cap.
    variance=clamp(variance,mean,max(mean,4*prior))
    dispersion=max(0.,(variance-mean)/(mean*mean))
    family='negative_binomial' if dispersion>1e-6 else 'poisson'
    if family=='poisson':variance=mean;dispersion=0.
    return {'family':family,'mean':mean,'variance':variance,'sd':math.sqrt(variance),'dispersion':dispersion,
            'sample':n,'sample_weight':w,'prior_variance':prior,'shrinkage_target':target,
            'observed_sd':math.sqrt(var([y for _,y in pairs])) if n>=2 else None,
            'minutes_sd':math.sqrt(minutes_var),'minute_variance_component':minute_component,
            'conditional_residual_variance':residual,'shot_variance':structure,
            'status':'player_shrunk' if n>=MIN_SAMPLE else 'prior_only','conditional_on_playing':True}

def attach_distributions(players):
    # Whole-team version availability so the normal publisher enforces 200 minutes.
    if not players or any(SHOOTING not in (p.get('ExperimentalModels') or {}) for p in players):
        return [{**p,'DistributionModelStatus':'v6_unavailable'} for p in players]
    out=[]
    for p in players:
        v=p['ExperimentalModels'][SHOOTING];logs=p.get('CurrentSeasonLog') or []
        m=finite(v.get('Minutes'));distributions={}
        for stat,col in STATS.items():
            mu=finite(v.get('KenPom'+stat))
            d=distribution(logs,stat,col,mu,m,v.get('ShotInputs'))
            if d is not None:distributions[stat]=d
        x={**v,'ModelVersion':VERSION,'ProbabilityModel':PRICING,'Distributions':distributions,'DistributionBaseModel':SHOOTING}
        out.append({**p,'DistributionModelStatus':'available','ExperimentalModels':{**p['ExperimentalModels'],VERSION:x}})
    return out
