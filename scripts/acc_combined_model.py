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
    return out
