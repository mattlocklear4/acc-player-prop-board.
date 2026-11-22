#!/usr/bin/env python3
"""Grade immutable ACC daily pregame archives against completed ESPN player logs.

No postgame re-projections. Match ESPN event ID, ACC team, and uniquely matched
player name; missing games/players remain ungraded, never assigned zero.
"""
import csv
import datetime as dt
import json
import statistics
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
ARCHIVES=ROOT/'data/archives/daily'
LOGS=ROOT/'data/espn/acc_player_games_2027.csv'
OUT=ROOT/'data/daily_grading.json'
FIELDS={'Minutes':('Minutes','minutes'),'Points':('KenPomPoints','points'),
        'Rebounds':('KenPomRebounds','reb'),'Assists':('KenPomAssists','assists'),
        'Threes':('KenPomThrees','three_pm')}
def norm(s):
    return ''.join(c for c in str(s or '').lower() if c.isalnum())
def num(v):
    try:return float(v) if v is not None and str(v).strip() else None
    except (ValueError,TypeError):return None
def timestamp(v):
    try:
        parsed=dt.datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None
    except (ValueError,TypeError):return None
def main():
    today=dt.datetime.now(ZoneInfo('America/New_York')).date()
    logs={}
    if LOGS.exists():
        with LOGS.open(newline='',encoding='utf-8') as f:
            for row in csv.DictReader(f):
                logs.setdefault(row['game_id'],[]).append(row)
    daily=[];rows=[];issues=[]
    for file in sorted(ARCHIVES.glob('????-??-??.json')):
        day=dt.date.fromisoformat(file.stem)
        if day>=today:continue
        archive=json.loads(file.read_text())
        if archive.get('date_eastern')!=file.stem:
            issues.append({'date':file.stem,'reason':'archive_date_mismatch'});continue
        day_rows=[];day_issues=[];completed_games=0
        projected_players=sum(len(t.get('players') or []) for g in archive.get('games') or [] for t in g.get('teams') or [])
        archived_at=timestamp(archive.get('generated_at_utc'))
        for game in archive.get('games') or []:
            gid=str(game.get('game_id') or '')
            tipoff=timestamp(game.get('tipoff_utc'))
            if archived_at is None or tipoff is None or archived_at>=tipoff:
                day_issues.append({'game_id':gid,'reason':'unverifiable_pregame_timestamp'});continue
            event_id=gid.removeprefix('espn_event_')
            if not event_id.isdigit():
                day_issues.append({'game_id':gid,'reason':'unsupported_event_id'});continue
            actuals=[r for r in logs.get('espn_'+event_id,[]) if r.get('game_date')==file.stem
                     and r.get('source')=='ESPN_UNOFFICIAL']
            if not actuals:
                day_issues.append({'game_id':gid,'reason':'final_boxscore_not_collected'});continue
            completed_games+=1
            for team in game.get('teams') or []:
                players=team.get('players') or []
                # ESPN logs use full team names; projection uses school names.
                team_name=norm(team.get('team'))
                team_actuals=[a for a in actuals if norm(a.get('team'))==team_name or
                              (len(team_name)>=5 and norm(a.get('team')).startswith(team_name))]
                if players and not team_actuals:
                    day_issues.append({'game_id':gid,'team':team.get('team'),'reason':'team_not_matched'});continue
                for p in players:
                    matched=[a for a in team_actuals if norm(a.get('player'))==norm(p.get('Player'))]
                    if len(matched)!=1:
                        day_issues.append({'game_id':gid,'player':p.get('Player'),
                                           'reason':'player_not_uniquely_matched'});continue
                    actual=matched[0];stats={}
                    for field,(projected,observed) in FIELDS.items():
                        x,y=num(p.get(projected)),num(actual.get(observed))
                        if x is not None and y is not None:
                            stats[field]={'projection':round(x,3),'actual':y,'error':round(x-y,3)}
                    if not stats:continue
                    day_rows.append({'date':file.stem,'game_id':gid,'team':team.get('team'),
                                     'player':p.get('Player'),'snapshot_utc':archive.get('generated_at_utc'),
                                     'tipoff_utc':game.get('tipoff_utc'),'stats':stats})
        daily.append({'date':file.stem,'games':len(archive.get('games') or []),
                      'games_with_final_logs':completed_games,'players_graded':len(day_rows),
                      'projected_players':projected_players,
                      'issues':len(day_issues),'snapshot_utc':archive.get('generated_at_utc')})
        rows.extend(day_rows);issues.extend([{'date':file.stem,**i} for i in day_issues])
    metrics={}
    for field in FIELDS:
        errs=[r['stats'][field]['error'] for r in rows if field in r['stats']]
        metrics[field]={'n':len(errs),'mae':round(statistics.mean(abs(x) for x in errs),3) if errs else None,
                        'bias':round(statistics.mean(errs),3) if errs else None}
    result={'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'status':'PARTIAL' if issues else 'OK','players_graded':len(rows),
            'projected_players':sum(d['projected_players'] for d in daily),
            'days':daily,'metrics':metrics,'issues':issues,'rows':rows,
            'caution':'Research-only grading from archived pregame projections and unofficial ESPN box scores. Missing player/game data excluded, not scored as zero. No sportsbook ROI inferred.'}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'days':len(daily),'players_graded':len(rows),'issues':len(issues),'metrics':metrics}))
if __name__=='__main__':main()
