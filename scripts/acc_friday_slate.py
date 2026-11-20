#!/usr/bin/env python3
"""Read-only Friday ACC slate extracted from the full research diagnostic."""
import json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

src=Path('research/acc_projection_dry_run.json')
payload=json.loads(src.read_text())
now=datetime.fromisoformat(payload['generated_at_utc'].replace('Z','+00:00'))
local=now.astimezone(ZoneInfo('America/New_York')).date()
days=(4-local.weekday())%7
friday=local+timedelta(days=days)
games=[]
for game in payload.get('games') or []:
    tip=datetime.fromisoformat(game['tipoff_utc'].replace('Z','+00:00'))
    if tip.astimezone(ZoneInfo('America/New_York')).date()!=friday:continue
    teams=[{'team':t.get('team'),'opponent':t.get('opponent'),'status':t.get('status'),
            'reason':t.get('reason'),'player_count':len(t.get('players') or []),
            'players':t.get('players') or []} for t in game.get('teams') or []]
    games.append({'game_id':game.get('game_id'),'tipoff_utc':game['tipoff_utc'],
                  'home_team':game.get('home_team'),'away_team':game.get('away_team'),'teams':teams})
out={'mode':'FRIDAY_RESEARCH_NO_WRITES','date_eastern':friday.isoformat(),
     'generated_at_utc':payload['generated_at_utc'],'schedule_status':payload.get('schedule_status'),
     'game_count':len(games),'projection_player_rows':sum(len(t['players']) for g in games for t in g['teams']),
     'warning':'Research only. Unverified minutes/injuries, snapshot freshness, and market prices.',
     'games':games}
dest=Path('research/acc_friday_slate.json')
dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='games'}))
