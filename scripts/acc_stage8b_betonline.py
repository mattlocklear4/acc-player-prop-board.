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

def team_match(schedule_name, api_name):
    """Match a known school prefix, allowing API team nicknames."""
    aliases = {
        'floridastate': 'floridast',
        'texasamcorpuschristi': 'texasamcc',
    }
    school = norm(schedule_name)
    provider = norm(api_name)
    school = aliases.get(school, school)
    return len(school) >= 5 and provider.startswith(school)

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
    if not 1<=a.max_events<=2:
        p.error('Safety cap: at most 2 paid events per manual run')
    if a.min_credits_remaining<30:
        p.error('Safety floor: at least 30 credits must remain')
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
        # Diagnostic-only: capture provider names and times without additional API calls.
        out['discovery_diagnostic'] = {
            'api_event_sample': [
                {'home_team': e.get('home_team'), 'away_team': e.get('away_team'),
                 'commence_time': e.get('commence_time')}
                for e in api_events[:80]
            ],
            'schedule_comparisons': []
        }
        matches=[]
        for game in games:
            home=game.get('home_team') or game.get('homeTeam') or game.get('home')
            away=game.get('away_team') or game.get('awayTeam') or game.get('away')
            if isinstance(home,dict):home=home.get('name') or home.get('school')
            if isinstance(away,dict):away=away.get('name') or away.get('school')
            start=utc(game.get('tipoff_utc') or game.get('start_time') or game.get('commence_time') or game.get('startTime') or game.get('date'))
            if not (home and away and start):
                out['warnings'].append('Schedule game missing recognizable home/away/time; skipped safely.')
                continue
            # Include a short ranked shortlist so mismatched aliases or dates are visible.
            def similarity(event):
                from difflib import SequenceMatcher
                eh, ea = norm(event.get('home_team')), norm(event.get('away_team'))
                gh, ga = norm(home), norm(away)
                direct = (SequenceMatcher(None, eh, gh).ratio() + SequenceMatcher(None, ea, ga).ratio()) / 2
                reverse = (SequenceMatcher(None, eh, ga).ratio() + SequenceMatcher(None, ea, gh).ratio()) / 2
                return max(direct, reverse)
            nearest = sorted(api_events, key=similarity, reverse=True)[:5]
            out['discovery_diagnostic']['schedule_comparisons'].append({
                'schedule_home': home, 'schedule_away': away, 'schedule_tipoff_utc': start.isoformat(),
                'top_candidates': [
                    {'home_team': e.get('home_team'), 'away_team': e.get('away_team'),
                     'commence_time': e.get('commence_time'), 'name_similarity': round(similarity(e), 3),
                     'tipoff_difference_minutes': round((utc(e.get('commence_time')) - start).total_seconds()/60)
                        if utc(e.get('commence_time')) else None}
                    for e in nearest
                ]
            })
            if start<=now:continue
            candidates=[e for e in api_events if team_match(home,e.get('home_team')) and team_match(away,e.get('away_team'))
                        and (utc(e.get('commence_time')) is not None) and abs((utc(e['commence_time'])-start).total_seconds())<=4*3600]
            if len(candidates)==1:matches.append((game,candidates[0]))
            elif len(candidates)>1:out['warnings'].append(f'Ambiguous event match: {home} vs {away}; skipped.')
            else:out['warnings'].append(f'No exact Odds API event match: {home} vs {away}.')
        out['matched_events']=len(matches)
        if not a.fetch_odds:
            out['events']=[{'event_id':e['id'],'home_team':e['home_team'],'away_team':e['away_team'], 'status':'DISCOVERY_ONLY_NO_CREDITS'} for _,e in matches]
            out['warnings'].append('Discovery-only mode; no paid event odds requested.');save();return
        # Only Friday in Eastern time. Manual dispatch only; hard limit 2 events x 4 markets.
        from zoneinfo import ZoneInfo
        today=now.astimezone(ZoneInfo('America/New_York')).date()
        friday=today+dt.timedelta(days=(4-today.weekday())%7)
        friday_matches=[(g,e) for g,e in matches
            if utc(e.get('commence_time')).astimezone(ZoneInfo('America/New_York')).date()==friday]
        out['target_date_eastern']=friday.isoformat()
        out['quota']['estimated_max_credits']=a.max_events*len(MARKETS)
        if not friday_matches:
            out['warnings'].append('No matched upcoming Friday events; zero paid requests.');return
        for game,event in friday_matches[:a.max_events]:
            if out['quota']['requests_sent']>=a.max_events:break
            if out['quota'].get('remaining') is not None and out['quota']['remaining']<a.min_credits_remaining+len(MARKETS):
                out['warnings'].append('Stopped: remaining credits below reserve plus worst-case request cost.');break
            try:
                data,meta=get(ROOT+'/events/'+urllib.parse.quote(str(event['id']),safe='')+'/odds',
                    {'apiKey':key,'bookmakers':BOOK,'markets':','.join(MARKETS),'oddsFormat':'american'})
                out['quota']['requests_sent']+=1
                last=int(meta.get('x-requests-last') or 0)
                out['quota']['credits_spent_reported']+=last
                remaining=meta.get('x-requests-remaining')
                if remaining is not None:out['quota']['remaining']=int(remaining)
                props=[]
                for bookmaker in data.get('bookmakers') or []:
                    if bookmaker.get('key')!=BOOK:continue
                    for market in bookmaker.get('markets') or []:
                        if market.get('key') not in MARKETS:continue
                        for outcome in market.get('outcomes') or []:
                            props.append({'market':market['key'],'player':outcome.get('description'),
                                'side':outcome.get('name'),'line':outcome.get('point'),
                                'odds':outcome.get('price'),'last_update':market.get('last_update')})
                out['events'].append({'event_id':event['id'],'schedule_game_id':game.get('game_id'),
                    'home_team':event['home_team'],'away_team':event['away_team'],
                    'status':'ODDS_RETRIEVED' if props else 'NO_BETONLINE_PROPS_RETURNED','props':props})
            except (OSError,ValueError,urllib.error.HTTPError,urllib.error.URLError) as exc:
                out['warnings'].append('Paid event request failed; stopping to prevent repeated charges: '+str(exc).split('?')[0][:120])
                break
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as ex:
        out['warnings'].append('Preview error: '+str(ex).split('?')[0][:240])
    finally:save()

if __name__=='__main__':main()
