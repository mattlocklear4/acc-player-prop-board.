"""V11 combined prospective challenger.

V9 minutes + V6 production at those minutes + V8 matchup + V10 count pricing.
Never overwrite controls or silently substitute missing team-level inputs.
"""
from copy import deepcopy
from acc_experimental_models import SHOOTING,finite
from acc_rotation_model import VERSION as ROTATION
from acc_availability import VERSION as AVAILABILITY
from acc_opponent_model import attach_matchup,VERSION as OPPONENT,factors,key
from acc_distribution_model import distribution,PRICING,VERSION as DISTRIBUTION
from research_engine import STATS,clamp

VERSION='v11-combined'
ACTIVE_VERSION='v12-active-minutes'
INTERMEDIATE='_v11_matchup_internal'

def attach_combined(players,opponent,context):
    def absent(reason):return [{**p,'CombinedModelStatus':reason} for p in players]
    if not players:return []
    if any(ROTATION not in (p.get('ExperimentalModels') or {}) for p in players):
        return absent('v9_rotation_unavailable')
    if any(OPPONENT not in (p.get('ExperimentalModels') or {}) for p in players):
        return absent('v8_opponent_unavailable')
    if not context or key(opponent) not in context['teams']:
        return absent('opponent_context_unavailable')
    # V9 already recomputes production after any direct injury-game exclusion.
    # V8 replaces the generic defensive multiplier, never multiplies it twice.
    adjusted=attach_matchup(players,opponent,context,base_version=ROTATION,output_version=INTERMEDIATE,exclude_manual=True)
    if any(INTERMEDIATE not in (p.get('ExperimentalModels') or {}) for p in adjusted):
        return absent('combined_matchup_unavailable')
    f=factors(context['teams'][key(opponent)],context['league'])
    out=[]
    for p,a in zip(players,adjusted):
        v=a['ExperimentalModels'][INTERMEDIATE]
        r=p['ExperimentalModels'][ROTATION]
        m=finite(v.get('Minutes'))
        if m is None or not 0<=m<=40:return absent('invalid_rotation')
        manual=p['ExperimentalModels'].get(AVAILABILITY,{}).get('AvailabilityAdjustment') or {}
        direct=bool(manual and manual.get('status')!='redistributed')
        if direct and abs(m-float(manual['minutes']))>1e-7:return absent('manual_minutes_mismatch')
        excluded=set((r.get('IntelligentRotation') or {}).get('manual_excluded_games') or [])
        logs=[g for g in p.get('CurrentSeasonLog') or [] if g.get('date') not in excluded]
        # Structural variance uses the adjusted attempts/efficiencies and pace
        # that generated V11's mean; historical residuals still come only from
        # the prior current-season appearance logs.
        shot=deepcopy(v.get('ShotInputs'))
        if shot and 'Points' not in v['OpponentAdjustment']['fallback_stats']:
            pace=finite(p.get('PaceFactor'))
            if pace is None or pace<=0:return absent('pace_missing')
            for k,rate,eff in (('2P','2PA','2P_eff'),('3P','3PA','3P_eff'),('FT','FTA',None)):
                shot['projected_attempts'][k]*=f[rate]*pace
                if eff:shot['components'][k]['expected_pct']=clamp(shot['components'][k]['expected_pct']*f[eff],0,1)
        else:shot=None
        ds={}
        for stat,col in STATS.items():
            d=distribution(logs,stat,col,finite(v.get('KenPom'+stat)),m,shot if stat=='Points' else None)
            if d is not None:ds[stat]=d
        x={**v,'ModelVersion':VERSION,'ProbabilityModel':PRICING,'Distributions':ds,
           'DistributionBaseModel':ROTATION+' + '+OPPONENT,
           'CombinedModelInputs':{'rotation':ROTATION,'production':SHOOTING,'opponent':OPPONENT,'probability':DISTRIBUTION,
              'excluded_games':sorted(excluded),'distribution_games':len(logs),
              'fallback_stats':v['OpponentAdjustment']['fallback_stats'],'manual_minutes':m if direct else None,
              'rotation_adjusted':bool(r.get('IntelligentRotation',{}).get('role_weighted_redistribution')),
              'pricing_status':'excluded_zero_minutes' if m==0 else 'available',
              'conditional_on_playing':True}}
        # Display provenance of published overrides, not local browser previews.
        if manual:
            x.update(AvailabilityAdjustment=manual,OriginalMinutes=r.get('IntelligentRotation',{}).get('v6_minutes',p.get('Minutes')),
                     ProductionGamesUsed=len(logs),ScenarioType='published')
        out.append({**p,'CombinedModelStatus':'available','ExperimentalModels':{**p['ExperimentalModels'],VERSION:x}})
    if sum(round(p['ExperimentalModels'][VERSION]['Minutes']*10) for p in out)!=2000:
        return absent('invalid_team_minutes')
    return attach_active_minutes(out,f)


def attach_active_minutes(players, matchup_factors):
    """V12: individual minutes conditional on appearing, not an all-active team lineup.

    V11 stays frozen. Its 200-minute allocation represents the expected rotation.
    For players with observed nonappearances, replace the participation-weighted
    raw minutes signal with the same 60/40 blend over appearances only, retaining
    V11's allocation factor. Do not infer injury or exclude short appearances.
    Manual availability/minutes overrides always win.
    """
    out=[]
    for p in players:
        v=p['ExperimentalModels'][VERSION]
        x=deepcopy(v)
        m=float(v['Minutes'])
        inp=v.get('RotationInputs') or {}
        excluded=set(v['CombinedModelInputs'].get('excluded_games') or [])
        logs=sorted([g for g in p.get('CurrentSeasonLog') or [] if g.get('date') not in excluded and (finite(g.get('minutes')) or 0)>0],key=lambda g:g.get('date',''),reverse=True)
        total=finite(inp.get('team_games'))
        appearances=finite(inp.get('appearances'))
        season=finite(inp.get('season_minutes_including_nonappearances'))
        recent=finite(inp.get('recent_team_game_minutes'))
        raw=.6*season+.4*recent if season is not None and recent is not None else None
        active_raw=None
        manual=v['CombinedModelInputs'].get('manual_minutes') is not None
        corrected=False
        if not manual and m>0 and total and appearances is not None and 0<appearances<total and len(logs)>=3 and raw and raw>0:
            ms=[min(40,float(g['minutes'])) for g in logs]
            active_raw=.6*sum(ms)/len(ms)+.4*sum(ms[:3])/len(ms[:3])
            m=round(clamp(m*active_raw/raw,0,40),1)
            corrected=True
        x['TeamRotationMinutes']=v['Minutes']
        x['Minutes']=m
        x['ModelVersion']=ACTIVE_VERSION
        x['ConditionalMinutesInputs']={'observed_appearances':appearances,'observed_team_games':total,
            'observed_participation_rate':appearances/total if total and appearances is not None else None,
            'participation_weighted_raw_minutes':raw,'appearance_only_raw_minutes':active_raw,
            'team_rotation_minutes':v['Minutes'],'conditional_minutes':m,'adjusted':corrected,
            'manual_override':manual,'conditional_on_playing':True,
            'note':'Individual active-player scenario; conditional minutes across players need not sum to 200.'}
        if corrected:
            ratio=m/v['Minutes']
            for stat in STATS:
                for prefix in ('Baseline','KenPom','Vegas','Combined'):
                    k=prefix+stat
                    val=finite(v.get(k))
                    x[k]=val*ratio if val is not None else None
            shot=deepcopy(v.get('ShotInputs'))
            if shot:
                shot['projected_attempts']={k:a*ratio for k,a in shot['projected_attempts'].items()}
                x['ShotInputs']=deepcopy(shot)
            if shot and 'Points' not in v['OpponentAdjustment']['fallback_stats']:
                pace=finite(p.get('PaceFactor'))
                if pace is not None and pace>0:
                    for k,rate,eff in (('2P','2PA','2P_eff'),('3P','3PA','3P_eff'),('FT','FTA',None)):
                        shot['projected_attempts'][k]*=matchup_factors[rate]*pace
                        if eff:shot['components'][k]['expected_pct']=clamp(shot['components'][k]['expected_pct']*matchup_factors[eff],0,1)
                else:shot=None
            else:shot=None
            x['Distributions']={}
            for stat,col in STATS.items():
                d=distribution(logs,stat,col,finite(x.get('KenPom'+stat)),m,shot if stat=='Points' else None)
                if d is not None:x['Distributions'][stat]=d
        x['DistributionBaseModel']=VERSION+' active-player scenario'
        out.append({**p,'ExperimentalModels':{**p['ExperimentalModels'],ACTIVE_VERSION:x}})
    return out
