#!/usr/bin/env python3
"""Read-only CBBD ACC schedule discovery. No Supabase writes or pregame locks."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request
import urllib.error

TEAMS = ["Boston College", "California", "Clemson", "Duke", "Florida State", "Georgia Tech", "Louisville", "Miami", "NC State", "North Carolina", "Notre Dame", "Pittsburgh", "SMU", "Stanford", "Syracuse", "Virginia", "Virginia Tech", "Wake Forest"]
BASE = "https://api.collegebasketballdata.com"

def parse_time(value):
    if not value: return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None: return None  # refuse ambiguous tipoff
        return parsed.astimezone(dt.timezone.utc)
    except ValueError: return None

def get_games(team, season, key):
    url = BASE + '/games?' + urllib.parse.urlencode({'season': season, 'team': team})
    req = urllib.request.Request(url, headers={'Authorization':'Bearer '+key, 'Accept':'application/json', 'User-Agent':'acc-player-prop-board/2.3'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=35) as res: data=json.load(res)
            if not isinstance(data,list): raise ValueError('Expected list from CBBD /games')
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429,500,502,503,504) and attempt<2:
                time.sleep(2*(attempt+1)); continue
            raise RuntimeError(f'CBBD /games HTTP {e.code} for {team}') from e
        except (TimeoutError,urllib.error.URLError) as e:
            if attempt<2: time.sleep(2*(attempt+1)); continue
            raise RuntimeError(f'CBBD /games network error for {team}: {type(e).__name__}') from e

def pick(g, *keys):
    for key in keys:
        if g.get(key) is not None: return g[key]
    return None

def normalize(g, queried_team):
    gid=pick(g,'id','gameId','game_id')
    start=parse_time(pick(g,'startDate','start_date','startTime','start_time'))
    home=pick(g,'homeTeam','home_team'); away=pick(g,'awayTeam','away_team')
    # Some CBBD versions return team/opponent/isHome instead of homeTeam/awayTeam.
    if not home or not away:
        team=pick(g,'team'); opp=pick(g,'opponent'); is_home=pick(g,'isHome','home')
        if team and opp and isinstance(is_home,bool):
            home,away=(team,opp) if is_home else (opp,team)
    return {'game_id':str(gid) if gid is not None else None,'tipoff_utc':start.isoformat() if start else None,'home_team':home,'away_team':away,'matched_acc_team':queried_team,'status':pick(g,'status','gameStatus','game_status')}

def discover(records, now, horizon_hours):
    by_id={}; problems=[]
    for team,games in records.items():
        for raw in games:
            if not isinstance(raw,dict):continue
            g=normalize(raw,team)
            if not g['game_id'] or not g['tipoff_utc'] or not g['home_team'] or not g['away_team']:
                problems.append({'team':team,'game_id':g['game_id'],'reason':'missing game ID, timezone-aware tipoff, or teams'})
                continue
            tip=parse_time(g['tipoff_utc'])
            if not now <= tip <= now+dt.timedelta(hours=horizon_hours):continue
            existing=by_id.get(g['game_id'])
            if existing:
                if any(existing[k]!=g[k] for k in ('tipoff_utc','home_team','away_team')):
                    problems.append({'game_id':g['game_id'],'reason':'conflicting CBBD schedule records'})
                    by_id.pop(g['game_id'],None)
                else: existing['acc_teams'].append(team)
            else:
                g['acc_teams']=[team]
                by_id[g['game_id']]=g
    return sorted(by_id.values(),key=lambda x:(x['tipoff_utc'],x['game_id'])),problems

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--season',type=int,default=2027)
    p.add_argument('--horizon-hours',type=int,default=72)
    p.add_argument('--output',default='research/acc_schedule_dry_run.json')
    p.add_argument('--fixture',help='Optional local JSON mapping team names to CBBD response arrays (testing only)')
    args=p.parse_args()
    now=dt.datetime.now(dt.timezone.utc)
    if args.fixture: records=json.loads(Path(args.fixture).read_text(encoding='utf-8'))
    else:
        key=os.getenv('CBBD_API_KEY','').strip()
        if not key: p.error('CBBD_API_KEY secret is required')
        records={}
        for team in TEAMS:
            records[team]=get_games(team,args.season,key)
            time.sleep(.15)
    games,problems=discover(records,now,args.horizon_hours)
    result={'mode':'DRY_RUN_NO_WRITES','generated_at_utc':now.isoformat(),'season':args.season,'horizon_hours':args.horizon_hours,'games':games,'warnings':problems,'queried_teams':len(records)}
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f'DRY RUN: {len(games)} upcoming ACC games; {len(problems)} incomplete/conflicting records; output {dest}')
    for g in games:print(g['tipoff_utc'],g['home_team'],'vs',g['away_team'],'CBBD ID',g['game_id'])
    if problems:print('WARNING: some schedule records require review; see artifact')

if __name__=='__main__':main()
