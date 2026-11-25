#!/usr/bin/env python3
"""Publish today's ACC pregame projections, never re-project completed games."""
import datetime as dt,json,math
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'research/acc_projection_dry_run.json'
payload=json.loads(source.read_text())
now=dt.datetime.fromisoformat(payload['generated_at_utc'].replace('Z','+00:00'))
day=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
games=[]
for g in payload.get('games') or []:
    try:tip=dt.datetime.fromisoformat(g['tipoff_utc'].replace('Z','+00:00'))
    except (ValueError,KeyError,TypeError):continue
    if tip.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=day:continue
    if tip<=now:continue
    teams=[]
    for t in g.get('teams') or []:
        players=t.get('players') or []
        if players:
            minutes=[p.get('Minutes') for p in players]
            if any(not isinstance(m,(int,float)) or not math.isfinite(m) or not 0<=m<=40 or abs(m*10-round(m*10))>1e-6 for m in minutes) or sum(round(m*10) for m in minutes)!=2000:
                raise ValueError('Refusing non-200-minute rotation for '+str(t.get('team')))
            if any(p.get('MinutesNormalizationStatus')!='normalized' for p in players):
                raise ValueError('Refusing unverified rotation for '+str(t.get('team')))
        teams.append({'team':t.get('team'),'opponent':t.get('opponent'),
                      'status':t.get('status'),'reason':t.get('reason'),
                      'kenpom_snapshot_id':t.get('kenpom_snapshot_id'),
                      'player_count':len(players),'players':players,
                      'projected_team_minutes':200.0 if players else None})
    games.append({'game_id':g.get('game_id'),'tipoff_utc':g['tipoff_utc'],
                  'home_team':g.get('home_team'),'away_team':g.get('away_team'),'teams':teams})
result={'date_eastern':day,'generated_at_utc':payload['generated_at_utc'],
        'schedule_status':payload.get('schedule_status'),
        'kenpom_source':payload.get('kenpom_source'),
        'games':games,'game_count':len(games),
        'projection_player_rows':sum(len(t['players']) for g in games for t in g['teams']),
        'caution':'Research projections; injury and minutes assumptions unverified. No post-tipoff backfill.'}
dest=ROOT/'data/daily_board.json'
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(result,indent=2)+'\n')
print('Daily board',day,len(games),'games',result['projection_player_rows'],'player rows')
