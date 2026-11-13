#!/usr/bin/env python3
"""Read-only, quota-capped BetOnline NCAAB prop preview. No database writes.

Default: discovery only (free events endpoint); paid odds require --fetch-odds.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

SPORT = 'basketball_ncaab'
MARKETS = ('player_points', 'player_rebounds', 'player_assists', 'player_threes')
BOOK = 'betonlineag'
ROOT = f'https://api.the-odds-api.com/v4/sports/{SPORT}'

def utc(s):
    if not s: return None
    try: return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00')).astimezone(dt.timezone.utc)
    except (ValueError, TypeError): return None

def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower().replace('university', '').replace('college', ''))

def get(url, params):
    request = urllib.request.Request(url + '?' + urllib.parse.urlencode(params), headers={'User-Agent':'ACC-Prop-Preview/1.0'})
    with urllib.request.urlopen(request, timeout=25) as resp:
        return json.load(resp), {k.lower():v for k,v in resp.headers.items()}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--schedule', default='research/acc_schedule_dry_run.json')
    p.add_argument('--output', default='research/acc_stage8b_betonline_preview.json')
    p.add_argument('--fetch-odds', action='store_true', help='Spend credits; disabled by default')
    p.add_argument('--max-events', type=int, default=2)
    p.add_argument('--min-credits-remaining', type=int, default=30)
    a=p.parse_args()
    out={'mode':'READ_ONLY','generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'bookmaker':BOOK,
         'markets':list(MARKETS),'paid_requests_enabled':a.fetch_odds,'events':[], 'warnings':[],
         'quota':{'estimated_max_credits':max(0,min(a.max_events,10))*len(MARKETS),'requests_sent':0,'credits_spent_reported':0}}
    def save():
        path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    try:
        schedule=json.loads(Path(a.schedule).read_text())
        games=schedule.get('games',[])
        if not games:
            out['warnings'].append('No scheduled ACC games; skipped all API calls.');save();return
        key=os.environ.get('ODDS_API_KEY','').strip()
        if not key:
            out['warnings'].append('ODDS_API_KEY secret missing; no API calls made.');save();return
        now=dt.datetime.now(dt.timezone.utc)
        api_events,headers=get(ROOT+'/events',{'apiKey':key}) # Free endpoint
        out['discovered_ncaab_events']=len(api_events)
        matches=[]
        for game in games:
            home=game.get('home_team') or game.get('homeTeam') or game.get('home')
            away=game.get('away_team') or game.get('awayTeam') or game.get('away')
            if isinstance(home,dict):home=home.get('name') or home.get('school')
            if isinstance(away,dict):away=away.get('name') or away.get('school')
            start=utc(game.get('start_time') or game.get('commence_time') or game.get('startTime') or game.get('date'))
            if not (home and away and start):
                out['warnings'].append('Schedule game missing recognizable home/away/time; skipped safely.')
                continue
            if start<=now:continue
            candidates=[e for e in api_events if norm(e.get('home_team'))==norm(home) and norm(e.get('away_team'))==norm(away)
                        and (utc(e.get('commence_time')) is not None) and abs((utc(e['commence_time'])-start).total_seconds())<=4*3600]
            if len(candidates)==1:matches.append((game,candidates[0]))
            elif len(candidates)>1:out['warnings'].append(f'Ambiguous event match: {home} vs {away}; skipped.')
            else:out['warnings'].append(f'No exact Odds API event match: {home} vs {away}.')
        out['matched_events']=len(matches)
        if not a.fetch_odds:
            out['events']=[{'event_id':e['id'],'home_team':e['home_team'],'away_team':e['away_team'], 'status':'DISCOVERY_ONLY_NO_CREDITS'} for _,e in matches]
            out['warnings'].append('Discovery-only mode: use --fetch-odds to explicitly authorize paid calls.');save();return
        if a.max_events<1 or a.max_events>10:raise ValueError('max-events must be 1..10')
        for _,e in matches[:a.max_events]:
            # one region, 4 markets; only BetOnline returned (bookmaker filter)
            params={'apiKey':key,'regions':'us','bookmakers':BOOK,'markets':','.join(MARKETS),'oddsFormat':'american'}
            data,h=get(ROOT+'/events/'+urllib.parse.quote(e['id'],safe='')+'/odds',params)
            out['quota']['requests_sent']+=1
            cost=int(h.get('x-requests-last','0'))
            out['quota']['credits_spent_reported']+=cost
            remaining=int(h.get('x-requests-remaining','-1'))
            out['quota']['remaining_after_last_request']=remaining
            record={'event_id':e['id'],'home_team':e['home_team'],'away_team':e['away_team'],
                    'commence_time':e.get('commence_time'),'markets':{},'bookmaker_found':False}
            for book in data.get('bookmakers',[]):
                if book.get('key')!=BOOK:continue
                record['bookmaker_found']=True
                for market in book.get('markets',[]):
                    if market.get('key') not in MARKETS:continue
                    grouped={}
                    for o in market.get('outcomes',[]):
                        side=o.get('name','').lower()
                        player=o.get('description')
                        if not player or side not in ('over','under'):continue
                        line=o.get('point')
                        k=(player,line)
                        item=grouped.setdefault(k,{'player':player,'line':line,'last_update':market.get('last_update')})
                        item[side+'_odds']=o.get('price')
                    record['markets'][market['key']]=list(grouped.values())
            out['events'].append(record)
            if remaining>=0 and remaining<a.min_credits_remaining:
                out['warnings'].append('Stopped: remaining API credits below safety threshold.');break
        if len(matches)>a.max_events:out['warnings'].append('Additional matched events skipped due to max-events cap.')
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as ex:
        out['warnings'].append('Preview error: '+str(ex).split('?')[0][:240])
    finally:save()

if __name__=='__main__':main()
