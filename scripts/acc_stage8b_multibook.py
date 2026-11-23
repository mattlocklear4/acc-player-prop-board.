#!/usr/bin/env python3
"""Read-only, quota-capped Multi-book NCAAB prop preview. No database writes.

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
from collections import Counter

SPORT = 'basketball_ncaab'
MARKETS = ('player_points', 'player_rebounds', 'player_assists', 'player_threes')
BOOKS = ('draftkings', 'fanduel', 'williamhill_us', 'fanatics', 'betonlineag')
ROOT = f'https://api.the-odds-api.com/v4/sports/{SPORT}'

def utc(s):
    if not s: return None
    try: return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00')).astimezone(dt.timezone.utc)
    except (ValueError, TypeError): return None

def norm(s):
    return re.sub(r'[^a-z0-9]', '', re.sub(r'\bstate\b', 'st', str(s or '').lower()).replace('university', '').replace('college', ''))

def team_match(schedule_name, api_name):
    """Match a known school prefix, allowing API team nicknames."""
    aliases = {
        'floridastate': 'floridast',
        'loyolamaryland': 'loyolamd',
        'texasamcorpuschristi': 'texasamcc',
        'northcarolina': 'northcarolina',
    }
    school = norm(schedule_name)
    provider = norm(api_name)
    school = aliases.get(school, school)
    return len(school) >= 5 and (provider.startswith(school) or school.startswith(provider) and len(provider)>=6)

def get(url, params):
    request = urllib.request.Request(url + '?' + urllib.parse.urlencode(params), headers={'User-Agent':'ACC-Prop-Preview/1.0'})
    with urllib.request.urlopen(request, timeout=25) as resp:
        return json.load(resp), {k.lower():v for k,v in resp.headers.items()}

def prop_coverage(props):
    """Summarize actual returned quotes, never inferred sportsbook availability."""
    books=Counter(p['bookmaker'] for p in props)
    markets=Counter(p['market'] for p in props)
    return {'quotes':len(props), 'unique_players':len({p['player'] for p in props if p.get('player')}),
            'quotes_by_bookmaker':dict(sorted(books.items())),
            'quotes_by_market':dict(sorted(markets.items())),
            'requested_books_with_no_returned_quotes':sorted(set(BOOKS)-set(books))}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--schedule', default='research/acc_schedule_dry_run.json')
    p.add_argument('--output', default='research/acc_stage8b_multibook_preview.json')
    p.add_argument('--fetch-odds', action='store_true', help='Spend credits; disabled by default')
    p.add_argument('--max-events', type=int, default=100)
    p.add_argument('--daily', action='store_true', help='Target only today in Eastern time, not Friday')
    p.add_argument('--max-credits', type=int, default=24, help='Conservative maximum charged credits this invocation')
    p.add_argument('--min-credits-remaining', type=int, default=30)
    a=p.parse_args()
    if not 1<=a.max_events<=100:
        p.error('max-events must be between 1 and 100')
    if a.min_credits_remaining<0:
        p.error('min-credits-remaining must be nonnegative')
    out={'mode':'READ_ONLY','generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'bookmakers':list(BOOKS),
         'markets':list(MARKETS),'paid_requests_enabled':a.fetch_odds,'events':[], 'warnings':[],
         'quota':{'estimated_max_credits':a.max_events*len(MARKETS),'requests_sent':0,'credits_spent_reported':0}}
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
        if a.fetch_odds:
            remaining=headers.get('x-requests-remaining')
            if remaining is None:
                out['warnings'].append('Missing quota header; refusing paid calls.');save();return
            out['quota']['remaining']=int(remaining)
            if int(remaining)<a.min_credits_remaining+len(MARKETS):
                out['warnings'].append('Monthly credit reserve reached; no paid calls.');save();return
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
            candidates=[e for e in api_events
                        if ((team_match(home,e.get('home_team')) and team_match(away,e.get('away_team')))
                            or (team_match(home,e.get('away_team')) and team_match(away,e.get('home_team'))))
                        and utc(e.get('commence_time')) is not None
                        and abs((utc(e['commence_time'])-start).total_seconds())<=4*3600]
            if len(candidates)==1:matches.append((game,candidates[0]))
            elif len(candidates)>1:out['warnings'].append(f'Ambiguous event match: {home} vs {away}; skipped.')
            else:out['warnings'].append(f'No exact Odds API event match: {home} vs {away}.')
        matches=list({str(e['id']):(g,e) for g,e in matches}.values())
        out['matched_events']=len(matches)
        if not a.fetch_odds:
            out['events']=[{'event_id':e['id'],'home_team':e['home_team'],'away_team':e['away_team'], 'status':'DISCOVERY_ONLY_NO_CREDITS'} for _,e in matches]
            out['warnings'].append('Discovery-only mode; no paid event odds requested.');save();return
        # Date-scoped retrieval; daily mode must never retrieve a future Friday slate.
        from zoneinfo import ZoneInfo
        today=now.astimezone(ZoneInfo('America/New_York')).date()
        friday=today+dt.timedelta(days=(4-today.weekday())%7)
        friday_matches=[(g,e) for g,e in matches
            if utc(e.get('commence_time')).astimezone(ZoneInfo('America/New_York')).date()==(today if a.daily else friday)]
        out['target_date_eastern']=(today if a.daily else friday).isoformat()
        out['quota']['estimated_max_credits']=min(a.max_events,len(friday_matches),a.max_credits//len(MARKETS))*len(MARKETS)
        if not friday_matches:
            out['warnings'].append('No matched eligible events on target date; zero paid requests.');save();return
        for game,event in friday_matches[:a.max_events]:
            if out['quota']['credits_spent_reported']+len(MARKETS)>a.max_credits:
                out['warnings'].append('Daily credit cap reached; remaining events skipped.');break
            if out['quota']['requests_sent']>=a.max_events:break
            if out['quota'].get('remaining') is not None and out['quota']['remaining']<a.min_credits_remaining+len(MARKETS):
                out['warnings'].append('Stopped: remaining credits below reserve plus worst-case request cost.');break
            try:
                data,meta=get(ROOT+'/events/'+urllib.parse.quote(str(event['id']),safe='')+'/odds',
                    {'apiKey':key,'bookmakers':','.join(BOOKS),'markets':','.join(MARKETS),'oddsFormat':'american'})
                out['quota']['requests_sent']+=1
                last=int(meta.get('x-requests-last') or 0)
                out['quota']['credits_spent_reported']+=last
                remaining=meta.get('x-requests-remaining')
                if remaining is not None:out['quota']['remaining']=int(remaining)
                props=[]
                for bookmaker in data.get('bookmakers') or []:
                    if bookmaker.get('key') not in BOOKS:continue
                    for market in bookmaker.get('markets') or []:
                        if market.get('key') not in MARKETS:continue
                        for outcome in market.get('outcomes') or []:
                            props.append({'bookmaker':bookmaker.get('key'),'market':market['key'],'player':outcome.get('description'),
                                'side':outcome.get('name'),'line':outcome.get('point'),
                                'odds':outcome.get('price'),'last_update':market.get('last_update')})
                out['events'].append({'event_id':event['id'],'schedule_game_id':game.get('game_id'),
                    'home_team':event['home_team'],'away_team':event['away_team'],
                    'status':'ODDS_RETRIEVED' if props else 'NO_REQUESTED_BOOK_PROPS_RETURNED',
                    'coverage':prop_coverage(props),'props':props})
            except (OSError,ValueError,urllib.error.HTTPError,urllib.error.URLError) as exc:
                out['warnings'].append('Paid event request failed; stopping to prevent repeated charges: '+str(exc).split('?')[0][:120])
                break
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as ex:
        out['warnings'].append('Preview error: '+str(ex).split('?')[0][:240])
    finally:save()

if __name__=='__main__':main()
