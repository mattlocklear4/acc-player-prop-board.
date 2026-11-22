#!/usr/bin/env python3
"""Evaluate saved pregame sportsbook quotes against archived predictions and ESPN finals.

No network requests, no orders and no re-projection. A hypothetical $1 wager is
selected only when the archived prediction is strictly above/below a quoted line.
Every bookmaker/market/player quote is a separate hypothetical opportunity.
"""
import datetime as dt
import json
from collections import Counter
from pathlib import Path

from acc_grade_daily import ROOT, norm, num, timestamp

GRADING=ROOT/'data/daily_grading.json'
SNAPSHOTS=ROOT/'data/odds_snapshots'
OUT=ROOT/'data/daily_odds_evaluation.json'
MARKETS={'player_points':'Points','player_rebounds':'Rebounds',
         'player_assists':'Assists','player_threes':'Threes'}

def american_profit(odds):
    value=num(odds)
    if value is None or value==0 or (-100<value<100):return None
    return round(value/100 if value>0 else 100/abs(value),6)

def evaluate(grading, snapshots):
    graded={(r['date'],r['game_id'],norm(r['player'])):r for r in grading.get('rows',[])}
    # Uniqueness must hold: ambiguous player names cannot silently be settled.
    counts=Counter((r['date'],r['game_id'],norm(r['player'])) for r in grading.get('rows',[]))
    bets=[];issues=[];coverage=[]
    for date,snapshot in sorted(snapshots.items()):
        snapshot_time=timestamp(snapshot.get('generated_at_utc'))
        seen=set();day_issues=Counter();offered=0
        if snapshot.get('snapshot_date_eastern',date)!=date:
            issues.append({'date':date,'reason':'snapshot_date_mismatch','count':1})
            coverage.append({'date':date,'events':0,'quotes_offered':0,
                             'hypothetical_selections':0,'issues':{'snapshot_date_mismatch':1}})
            continue
        for event in snapshot.get('events') or []:
            gid=str(event.get('schedule_game_id') or '')
            for prop in event.get('props') or []:
                offered+=1
                market=MARKETS.get(prop.get('market'))
                player=norm(prop.get('player'))
                key=(date,gid,player)
                identity=(gid,prop.get('bookmaker'),prop.get('market'),player,prop.get('line'),prop.get('side'))
                if identity in seen:
                    day_issues['duplicate_quote']+=1;continue
                seen.add(identity)
                row=graded.get(key)
                if not market or not player or counts[key]!=1 or row is None:
                    day_issues['unmatched_player_or_market']+=1;continue
                tipoff=timestamp(row.get('tipoff_utc'))
                updated=timestamp(prop.get('last_update'))
                # Both saved file and provider quote must demonstrably precede tipoff.
                if (not tipoff or not snapshot_time or snapshot_time>=tipoff or not updated
                        or updated>snapshot_time or updated>=tipoff):
                    day_issues['unverifiable_pregame_quote']+=1;continue
                stat=row.get('stats',{}).get(market)
                line=num(prop.get('line'))
                price=american_profit(prop.get('odds'))
                side=str(prop.get('side') or '').lower()
                if not stat or line is None or line<0 or price is None or side not in ('over','under'):
                    day_issues['invalid_line_or_actual']+=1;continue
                projected=num(stat.get('projection'));actual=num(stat.get('actual'))
                if projected is None or actual is None:
                    day_issues['missing_projection_or_actual']+=1;continue
                # Select direction using only the archived model projection.
                selected='over' if projected>line else 'under' if projected<line else None
                if selected!=side:
                    day_issues['not_selected_by_projection']+=1;continue
                result='push' if actual==line else 'win' if (actual>line)==(side=='over') else 'loss'
                pnl=0 if result=='push' else price if result=='win' else -1
                bets.append({'date':date,'game_id':gid,'player':row['player'],
                             'bookmaker':prop['bookmaker'],'market':market,'side':side,
                             'line':line,'american_odds':prop['odds'],'projection':projected,
                             'actual':actual,'result':result,'profit_units':round(pnl,6),
                             'snapshot_utc':snapshot['generated_at_utc'],'quote_updated_utc':prop['last_update']})
        for reason,count in day_issues.items():
            if reason!='not_selected_by_projection':
                issues.append({'date':date,'reason':reason,'count':count})
        coverage.append({'date':date,'events':len(snapshot.get('events') or []),
                         'quotes_offered':offered,'hypothetical_selections':sum(b['date']==date for b in bets),
                         'issues':dict(day_issues)})
    settled=[b for b in bets if b['result']!='push']
    profit=round(sum(b['profit_units'] for b in bets),4)
    return {'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'status':'PARTIAL' if issues or not settled else 'OK',
            'method':'Flat $1 hypothetical stake per distinct sportsbook quote, direction from immutable archived projection vs line; ties skipped; pushes refunded. All qualifying quotes are included, not an executable betting strategy.',
            'snapshots':len(snapshots),'quotes_offered':sum(d['quotes_offered'] for d in coverage),
            'selections':len(bets),'settled':len(settled),
            'wins':sum(b['result']=='win' for b in bets),
            'losses':sum(b['result']=='loss' for b in bets),
            'pushes':sum(b['result']=='push' for b in bets),
            'profit_units':profit,'roi_percent':round(100*profit/len(settled),2) if settled else None,
            'days':coverage,'issues':issues,'rows':bets,
            'caution':'Historical research only. Quotes may not have been bettable or available to the user; no actual wagers, no fabricated odds, and missing matches excluded.'}

def main():
    grading=json.loads(GRADING.read_text())
    snapshots={p.stem:json.loads(p.read_text()) for p in sorted(SNAPSHOTS.glob('????-??-??.json'))}
    result=evaluate(grading,snapshots)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('snapshots','quotes_offered','selections','settled','roi_percent')}))

if __name__=='__main__':main()
