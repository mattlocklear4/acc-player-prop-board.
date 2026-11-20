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

def get_games(team, season, key, now=None, horizon_hours=96):
    params={'season':season}
    if team=='ACC':
        params['conference']='ACC'
        if now:
            params['startDateRange']=now.isoformat()
            params['endDateRange']=(now+dt.timedelta(hours=horizon_hours)).isoformat()
    else:
        params['team']=team
    url = BASE + '/games?' + urllib.parse.urlencode(params)
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

def espn_public_schedule(now, horizon_hours):
    """Public ESPN scoreboard fallback, no API key and no paid requests.

    ESPN's scoreboard endpoint is unofficial; failures are explicitly reported.
    """
    import re
    end=now+dt.timedelta(hours=horizon_hours)
    days=(end.date()-now.date()).days+1
    games={}
    for offset in range(days):
        day=(now.date()+dt.timedelta(days=offset)).strftime('%Y%m%d')
        params={'dates':day,'limit':'500','groups':'50'}
        url='https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'User-Agent':'ACC-research-schedule/1.0','Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as response:payload=json.load(response)
        for event in payload.get('events') or []:
            tip=parse_time(event.get('date'))
            if not tip or not now<=tip<=end:continue
            competitions=event.get('competitions') or []
            if len(competitions)!=1:continue
            sides={}
            for entry in competitions[0].get('competitors') or []:
                team=entry.get('team') or {}
                sides[entry.get('homeAway')]=team
            if not sides.get('home') or not sides.get('away'):continue
            home,away=sides['home'],sides['away']
            def school(t):
                n=''.join(c for c in str(t.get('displayName') or '').lower() if c.isalnum())
                if n.startswith('miamiohio'):return None
                aliases={'floridastate':'floridast','miami':'miamihurricanes',
                         'california':'californiagoldenbears'}
                found=[(len(aliases.get(''.join(c for c in team.lower() if c.isalnum()),
                                        ''.join(c for c in team.lower() if c.isalnum()))),team)
                       for team in TEAMS
                       if n.startswith(aliases.get(''.join(c for c in team.lower() if c.isalnum()),
                                                   ''.join(c for c in team.lower() if c.isalnum())))]
                if not found:return None
                longest=max(length for length,_ in found)
                selected=[name for length,name in found if length==longest]
                return selected[0] if len(selected)==1 else None
            acc=[t for t in (school(home),school(away)) if t]
            if not acc:continue
            eid=str(event.get('id') or '')
            if not eid:continue
            games[eid]={'game_id':'espn_event_'+eid,'tipoff_utc':tip.isoformat(),
                        'home_team':home.get('displayName'),'away_team':away.get('displayName'),
                        'acc_teams':sorted(set(acc)),'status':'scheduled',
                        'schedule_source':'espn_public_scoreboard'}
    return sorted(games.values(),key=lambda x:x['tipoff_utc'])

def free_odds_events_fallback(now, horizon_hours):
    """Free event discovery only. No event-odds or player-prop endpoints."""
    key=os.getenv('ODDS_API_KEY','').strip()
    if not key: raise RuntimeError('ODDS_API_KEY missing for free schedule fallback')
    url='https://api.the-odds-api.com/v4/sports/basketball_ncaab/events?' + urllib.parse.urlencode({'apiKey':key})
    req=urllib.request.Request(url,headers={'User-Agent':'acc-player-prop-board/free-schedule'})
    with urllib.request.urlopen(req,timeout=25) as res: events=json.load(res)
    if not isinstance(events,list):raise ValueError('Unexpected free events response')
    # The API appends nicknames. Restrict to distinct ACC school prefixes.
    aliases={'floridastate':'floridast','ncstate':'ncstate','miami':'miamihurricanes',
             'california':'californiagoldenbears','pittsburgh':'pittsburgh'}
    def norm_name(x):
        return ''.join(c for c in str(x or '').lower() if c.isalnum())
    def acc_school(name):
        n=norm_name(name)
        found=[(len(aliases.get(norm_name(team),norm_name(team))),team)
               for team in TEAMS if n.startswith(aliases.get(norm_name(team),norm_name(team)))]
        # Miami is ambiguous without its nickname; never assume Miami (OH) is ACC.
        if n.startswith('miamiohio') or not found:return None
        longest=max(length for length,_ in found)
        winners=[team for length,team in found if length==longest]
        return winners[0] if len(winners)==1 else None
    games=[]
    for e in events:
        tip=parse_time(e.get('commence_time'))
        if not tip or not now<=tip<=now+dt.timedelta(hours=horizon_hours):continue
        home,away=e.get('home_team'),e.get('away_team')
        acc=[x for x in (acc_school(home),acc_school(away)) if x]
        if not acc or not home or not away or not e.get('id'):continue
        games.append({'game_id':'odds_event_'+str(e['id']),'odds_event_id':str(e['id']),
                      'tipoff_utc':tip.isoformat(),'home_team':home,'away_team':away,
                      'acc_teams':sorted(set(acc)),'status':'scheduled',
                      'schedule_source':'odds_api_free_events','team_names_include_nicknames':True})
    return sorted(games,key=lambda x:x['tipoff_utc']),len(events)

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
        provider_error=None
        try:
            # One conference/date-filtered call replaces 18 team calls.
            records['ACC']=get_games('ACC',args.season,key,now,args.horizon_hours)
        except RuntimeError as exc:
            provider_error=str(exc)
    if not args.fixture and provider_error:
        problems=[{'reason':'primary_schedule_provider_unavailable','detail':provider_error}]
        try:
            games=espn_public_schedule(now,args.horizon_hours)
            if not games:raise ValueError('ESPN scoreboard returned no ACC games in window')
            schedule_status='FALLBACK_ESPN_PUBLIC'
            problems.append({'reason':'fallback_used','source':'ESPN public scoreboard',
                             'note':'Unofficial schedule source; confirm tipoffs and opponent names.'})
        except (OSError,ValueError,RuntimeError,urllib.error.HTTPError,urllib.error.URLError) as espn_exc:
            problems.append({'reason':'espn_fallback_unavailable','detail':str(espn_exc).split('?')[0][:150]})
            try:
                games,discovered=free_odds_events_fallback(now,args.horizon_hours)
                schedule_status='FALLBACK_FREE_ODDS_EVENTS'
                problems.append({'reason':'fallback_used','events_discovered':discovered,
                                 'note':'Free Odds API events may omit unlisted games.'})
            except (OSError,ValueError,RuntimeError,urllib.error.HTTPError,urllib.error.URLError) as exc:
                games=[]
                problems.append({'reason':'fallback_unavailable','detail':str(exc).split('?')[0][:150]})
                schedule_status='UNAVAILABLE'
    else:
        games,problems=discover(records,now,args.horizon_hours)
        schedule_status='OK'
    result={'mode':'DRY_RUN_NO_WRITES','schedule_status':schedule_status,'generated_at_utc':now.isoformat(),'season':args.season,'horizon_hours':args.horizon_hours,'games':games,'warnings':problems,'queried_teams':len(records)}
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f'DRY RUN: {len(games)} upcoming ACC games; {len(problems)} incomplete/conflicting records; output {dest}')
    for g in games:print(g['tipoff_utc'],g['home_team'],'vs',g['away_team'],'CBBD ID',g['game_id'])
    if problems:print('WARNING: schedule provider warning or fallback used; inspect schedule_status and warnings.')

if __name__=='__main__':main()
