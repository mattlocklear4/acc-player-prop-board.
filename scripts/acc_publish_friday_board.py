#!/usr/bin/env python3
"""Build public, read-only Friday board JSON from diagnostic artifacts. No secrets."""
import json
from pathlib import Path
def load(path):
    p=Path(path)
    return json.loads(p.read_text()) if p.exists() else {}
slate=load('research/acc_friday_slate.json')
value=load('research/acc_draftkings_value_preview.json')
minutes=load('research/acc_friday_minutes_review.json')
odds=load('research/acc_stage8b_draftkings_preview.json')
# Keep original model estimates intact; attach explicit minute-adjusted
# research scenarios. This scales opportunity with minutes but does not
# pretend to estimate injury-driven usage redistribution.
review_index={(str(r.get('game_id')),str(r.get('team')),str(r.get('athlete_id'))):r
              for r in minutes.get('rows',[])}
for game in slate.get('games',[]):
    for team in game.get('teams',[]):
        for player in team.get('players',[]):
            review=review_index.get((str(game.get('game_id')),str(team.get('team')),str(player.get('AthleteId'))))
            if not review:continue
            projected=review.get('rotation_minutes_scenario')
            baseline=player.get('Minutes')
            player['RotationMinutesScenario']=projected
            player['RotationMinutesDelta']=review.get('rotation_minutes_delta')
            player['RecentUsagePct']=review.get('usage_pct_last5')
            player['AvailabilityStatus']=review.get('availability_status')
            player['RotationScenarioVerified']=False
            if projected is None or baseline is None or baseline<=0:continue
            ratio=max(0,min(2,projected/baseline))
            for model in ('Baseline','KenPom','Vegas','Combined'):
                for stat in ('Points','Rebounds','Assists','Threes'):
                    estimate=player.get(model+stat)
                    player['Rotation'+model+stat]=(round(estimate*ratio,3) if isinstance(estimate,(int,float)) else None)
output={'date_eastern':slate.get('date_eastern'),'generated_at_utc':slate.get('generated_at_utc'),
        'schedule_status':slate.get('schedule_status'),'games':slate.get('games',[]),
        'minute_reviews':minutes.get('rows',[]),'value_rows':value.get('rows',[]),
        'value_warnings':value.get('warnings',[]),
        'odds_quota':odds.get('quota',{}),'odds_warnings':odds.get('warnings',[]),
        'odds_generated_at_utc':odds.get('generated_at_utc'),
        'caution':'Unverified research projections. Injury/rotation uncertainty. Estimated ROI is not a calibrated edge.'}
dest=Path('data/friday_board.json')
dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps(output,separators=(',',':'))+'\n')
print('Public Friday board:',len(output['games']),'games;',len(output['value_rows']),'prop lines')
