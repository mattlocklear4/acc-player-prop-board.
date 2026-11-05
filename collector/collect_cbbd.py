#!/usr/bin/env python3
"""Collect CBBD ACC player game logs into a deterministic CSV. Requires CBBD_API_KEY."""
import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TEAMS = ["Boston College", "California", "Clemson", "Duke", "Florida State", "Georgia Tech", "Louisville", "Miami", "NC State", "North Carolina", "Notre Dame", "Pittsburgh", "SMU", "Stanford", "Syracuse", "Virginia", "Virginia Tech", "Wake Forest"]
BASE = 'https://api.collegebasketballdata.com'
FIELDS = ['season','game_id','game_date','team','team_id','conference','opponent','opponent_id','home','conference_game','game_minutes','game_pace','athlete_id','athlete_source_id','player','position','starter','minutes','points','fgm','fga','two_pm','two_pa','three_pm','three_pa','ftm','fta','oreb','dreb','reb','assists','steals','blocks','turnovers','fouls','usage_pct','offensive_rating','defensive_rating','net_rating','effective_fg_pct','true_shooting_pct','offensive_rebound_pct','game_score']

def nested(o,k,sub):
    return (o.get(k) or {}).get(sub)

def fetch(team, season, key):
    query=urllib.parse.urlencode({'season':season,'team':team})
    req=urllib.request.Request(f'{BASE}/games/players?{query}',headers={'Authorization':f'Bearer {key}','Accept':'application/json','User-Agent':'acc-player-prop-board/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=40) as resp:
                content=resp.read()
                data=json.loads(content)
                if not isinstance(data,list):
                    raise ValueError(f'{team}: expected JSON list; got {type(data).__name__}')
                return data
        except urllib.error.HTTPError as e:
            detail=e.read(300).decode('utf-8','replace')
            if e.code in (429,500,502,503,504) and attempt<2:
                time.sleep(3*(attempt+1));continue
            raise RuntimeError(f'{team}: HTTP {e.code}: {detail}') from e
        except (urllib.error.URLError,TimeoutError) as e:
            if attempt<2:time.sleep(3*(attempt+1));continue
            raise RuntimeError(f'{team}: network error {e}') from e

def flatten(game,player):
    return dict(season=game.get('season'),game_id=game.get('gameId'),game_date=(game.get('startDate') or '')[:10],team=game.get('team'),team_id=game.get('teamId'),conference=game.get('conference'),opponent=game.get('opponent'),opponent_id=game.get('opponentId'),home=game.get('isHome'),conference_game=game.get('conferenceGame'),game_minutes=game.get('gameMinutes'),game_pace=game.get('gamePace'),athlete_id=player.get('athleteId'),athlete_source_id=player.get('athleteSourceId'),player=player.get('name'),position=player.get('position'),starter=player.get('starter'),minutes=player.get('minutes'),points=player.get('points'),fgm=nested(player,'fieldGoals','made'),fga=nested(player,'fieldGoals','attempted'),two_pm=nested(player,'twoPointFieldGoals','made'),two_pa=nested(player,'twoPointFieldGoals','attempted'),three_pm=nested(player,'threePointFieldGoals','made'),three_pa=nested(player,'threePointFieldGoals','attempted'),ftm=nested(player,'freeThrows','made'),fta=nested(player,'freeThrows','attempted'),oreb=nested(player,'rebounds','offensive'),dreb=nested(player,'rebounds','defensive'),reb=nested(player,'rebounds','total'),assists=player.get('assists'),steals=player.get('steals'),blocks=player.get('blocks'),turnovers=player.get('turnovers'),fouls=player.get('fouls'),usage_pct=player.get('usage'),offensive_rating=player.get('offensiveRating'),defensive_rating=player.get('defensiveRating'),net_rating=player.get('netRating'),effective_fg_pct=player.get('effectiveFieldGoalPct'),true_shooting_pct=player.get('trueShootingPct'),offensive_rebound_pct=player.get('offensiveReboundPct'),game_score=player.get('gameScore'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--season',type=int,default=2027)
    parser.add_argument('--output-dir',default='data/cbbd')
    args=parser.parse_args()
    key=os.environ.get('CBBD_API_KEY','').strip()
    if not key:sys.exit('CBBD_API_KEY secret is missing')
    output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
    dest=output/f'acc_player_games_{args.season}.csv'
    rows={}
    # Existing records retained when API omits a previously captured game.
    if dest.exists():
        with dest.open(newline='',encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('game_id') and (r.get('athlete_id') or r.get('player')):
                    rows[(r['game_id'],r.get('team_id') or r.get('team'),r.get('athlete_id') or r.get('player'))]=r
    counts={};failures=[]
    for team in TEAMS:
        try:
            games=fetch(team,args.season,key)
            if games and not any(isinstance(g,dict) and isinstance(g.get('players'),list) for g in games):
                raise ValueError('No valid game objects with players arrays')
            player_count=0
            for game in games:
                if not isinstance(game,dict) or not isinstance(game.get('players'),list):continue
                for p in game['players']:
                    if not isinstance(p,dict) or not p.get('name'):continue
                    r=flatten(game,p)
                    if not r['game_id']:continue
                    k=(str(r['game_id']),str(r['team_id'] or r['team']),str(r['athlete_id'] or r['player']))
                    rows[k]=r;player_count+=1
            counts[team]={'games':len(games),'players':player_count}
            print(f'{team}: {len(games)} team-game objects; {player_count} player records',flush=True)
        except Exception as e:
            failures.append(f'{team}: {e}')
            print(f'ERROR: {team}: {e}',file=sys.stderr,flush=True)
        time.sleep(0.15)
    if failures:
        sys.exit('Collection incomplete; not overwriting CSV. Errors:\n'+'\n'.join(failures))
    ordered=sorted(rows.values(),key=lambda r:(str(r.get('game_date') or ''),str(r.get('game_id') or ''),str(r.get('team') or ''),str(r.get('player') or '')))
    if not ordered:sys.exit('No player records received; refusing to create empty CSV')
    tmp=dest.with_suffix('.tmp')
    with tmp.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');writer.writeheader();writer.writerows(ordered)
    tmp.replace(dest)
    summary={'season':args.season,'last_successful_run_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'api_requests':len(TEAMS),'team_counts':counts,'total_player_games':len(ordered),'csv_file':str(dest)}
    (output/f'acc_collection_summary_{args.season}.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(f'SUCCESS: {len(ordered)} player-game rows saved to {dest}. API requests: {len(TEAMS)}')

if __name__=='__main__':main()
