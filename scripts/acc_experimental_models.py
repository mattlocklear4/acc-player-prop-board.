"""Current-season shadow models: participation-based minutes and shot volume."""
import math
from research_engine import allocate_team_minutes, numeric, STATS, CURRENT_MODEL_VERSION
ROTATION='v5-rotation-participation'
SHOOTING='v6-rotation-shot-volume'
VERSIONS=(ROTATION,SHOOTING)
# Provisional population priors (not previous-season player performance).
PRIORS={'2P':(.50,30),'3P':(.34,40),'FT':(.72,20)}

def finite(v):
    x=numeric(v)
    return x if x is not None and math.isfinite(x) else None

def shooting_rates(logs):
    valid=[]
    total=sum(finite(g.get('minutes')) or 0 for g in logs)
    for g in logs:
        m,fgm,fga,tm,ta,ftm,fta,pts=[finite(g.get(k)) for k in ('minutes','fgm','fga','three_pm','three_pa','ftm','fta','points')]
        if any(v is None for v in (m,fgm,fga,tm,ta,ftm,fta,pts)) or m<=0:continue
        shots={'2P':(fgm-tm,fga-ta),'3P':(tm,ta),'FT':(ftm,fta)}
        if any(x<0 or a<0 or x>a for x,a in shots.values()) or abs(2*(fgm-tm)+3*tm+ftm-pts)>1e-6:continue
        valid.append((m,shots,g.get('date')))
    covered=sum(x[0] for x in valid)
    if not total or covered/total<.8 or not valid:return None
    recent_dates={g.get('date') for g in logs[:5]}
    recent=[x for x in valid if x[2] in recent_dates]
    recent_minutes=sum(x[0] for x in recent)
    out={}
    for k,(prior,weight) in PRIORS.items():
        made=sum(x[1][k][0] for x in valid);attempts=sum(x[1][k][1] for x in valid)
        season=attempts/covered
        last=sum(x[1][k][1] for x in recent)/recent_minutes if recent_minutes else season
        out[k]={'attempts_per_minute':.75*season+.25*last,'observed_attempts':attempts,'observed_makes':made,
                'observed_pct':made/attempts if attempts else None,'expected_pct':(made+weight*prior)/(attempts+weight),
                'prior_pct':prior,'prior_attempts':weight}
    return {'components':out,'coverage':covered/total,'games':len(valid)}

def attach_experiments(players):
    """Same observed team games, no assumed injuries; all variants sum to 200.
    Skip experimental rotation if observed team dates cannot reconcile.
    """
    empty=[{**p,'ExperimentalModels':{}} for p in players]
    if not players or any(p.get('ModelVersion')!=CURRENT_MODEL_VERSION for p in players):return empty
    dates=sorted({str(g['date']) for p in players for g in p.get('CurrentSeasonLog',[]) if g.get('date')},reverse=True)
    if not dates or any(p.get('CurrentTeamGames')!=len(dates) for p in players):return empty
    raw=[];inputs=[]
    for p in players:
        logs=p.get('CurrentSeasonLog') or []
        by_date={str(g['date']):finite(g.get('minutes')) for g in logs if g.get('date')}
        if len(by_date)!=len(logs) or any(v is None or v<=0 for v in by_date.values()):return empty
        season=sum(min(40,by_date.get(d,0)) for d in dates)/len(dates)
        recent=sum(min(40,by_date.get(d,0)) for d in dates[:3])/len(dates[:3])
        raw.append(.60*season+.40*recent)
        inputs.append({'team_games':len(dates),'appearances':len(logs),'participation_rate':len(logs)/len(dates),
                       'starts':sum(str(g.get('starter','')).lower() in ('true','1','yes') for g in logs),
                       'season_minutes_including_nonappearances':season,'recent_team_game_minutes':recent})
    try:allocation=allocate_team_minutes(raw)
    except ValueError:return empty
    out=[]
    for p,m,signal,inp in zip(players,allocation,raw,inputs):
        old=finite(p.get('Minutes'))
        if old is None or (old==0 and m>0):return empty
        rot={'ModelVersion':ROTATION,'Minutes':m,'RawMinutes':signal,'RotationInputs':inp}
        for stat in STATS:
            for prefix in ('Baseline','KenPom','Vegas','Combined'):
                key=prefix+stat;v=finite(p.get(key))
                rot[key]=v*m/old if v is not None and old>0 else (0.0 if v is not None and m==0 else None)
        shot=dict(rot,ModelVersion=SHOOTING)
        info=shooting_rates(sorted(p.get('CurrentSeasonLog') or [],key=lambda g:str(g.get('date')),reverse=True))
        if info:
            c=info['components'];attempts={k:m*v['attempts_per_minute'] for k,v in c.items()}
            threes=attempts['3P']*c['3P']['expected_pct']
            pts=2*attempts['2P']*c['2P']['expected_pct']+3*threes+attempts['FT']*c['FT']['expected_pct']
            shot.update(BaselinePoints=pts,BaselineThrees=threes,ShotInputs={**info,'projected_attempts':attempts},ShotStatus='modeled')
            pace=finite(p.get('PaceFactor'));defense=finite(p.get('OpponentDefenseFactor'));market=finite(p.get('MarketFactor'))
            shot['KenPomPoints']=pts*pace*defense if pace is not None and defense is not None else None
            shot['KenPomThrees']=threes*pace if pace is not None else None
            shot['VegasPoints']=pts*market if market is not None else None
            shot['VegasThrees']=threes*(1+.5*(market-1)) if market is not None else None
            shot['CombinedPoints']=shot['KenPomPoints']*market if market is not None and shot['KenPomPoints'] is not None else None
            shot['CombinedThrees']=shot['KenPomThrees']*(1+.5*(market-1)) if market is not None and shot['KenPomThrees'] is not None else None
        else:shot['ShotStatus']='fallback_rotation_only_missing_shots'
        out.append({**p,'ExperimentalModels':{ROTATION:rot,SHOOTING:shot}})
    return out
