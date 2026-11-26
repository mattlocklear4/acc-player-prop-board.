#!/usr/bin/env python3
"""Grade actual archived browser-priced quotes and latest pregame player forecasts.
Original morning projection and direction-only odds reports remain unchanged.
"""
import argparse, csv, datetime as dt, json, statistics
from collections import defaultdict
from zoneinfo import ZoneInfo
from acc_grade_daily import ROOT, LOGS, norm, num, timestamp, team_matches, FIELDS
from acc_game_identity import canonical_record, load_aliases

ARCHIVES=ROOT/'data/archives/pregame'
OUT=ROOT/'data/pregame_edge_grading.json'
PENDING=ROOT/'data/pregame_pending.json'
MARKETS={'Points':'points','Rebounds':'reb','Assists':'assists','Threes':'three_pm'}

def summary(rows):
    settled=[r for r in rows if r['result'] in ('win','loss','push')]
    profit=sum(r['profit_units'] for r in settled)
    return {'selections':len(rows),'settled':len(settled),'wins':sum(r['result']=='win' for r in settled),
            'losses':sum(r['result']=='loss' for r in settled),'pushes':sum(r['result']=='push' for r in settled),
            'profit_units':round(profit,4),'roi_percent':round(100*profit/len(settled),2) if settled else None,
            'mean_expected_roi_percent':round(statistics.mean(r['expected_roi_percent'] for r in settled),2) if settled else None}

def tier(x):
    return '0–5%' if x<5 else '5–10%' if x<10 else '10–20%' if x<20 else '20%+'

def select_snapshots(records, include_date):
    latest={}; latest_odds={}; issues=[]
    aliases=load_aliases()
    for raw in records:
        r=canonical_record(raw,aliases)
        date=r.get('date_eastern','')
        if not include_date(date):continue
        game=r.get('game') or {}; gid=game.get('game_id')
        captured=timestamp(r.get('captured_at_utc')); projected=timestamp(r.get('projection_utc')); tip=timestamp(game.get('tipoff_utc'))
        if not gid or not captured or not projected or not tip or not projected<=captured<tip:
            issues.append({'date':date,'game_id':gid,'reason':'invalid_pregame_capture'});continue
        key=(date,gid)
        rank=(projected,captured)
        if key not in latest or rank>latest[key][0]:latest[key]=(rank,r)
        odds=timestamp(r.get('odds_snapshot_utc'))
        if odds and odds<=captured and odds<tip and (r.get('quotes') or any((r.get('experimental_quotes') or {}).values())):
            rank=(projected,odds,captured)
            if key not in latest_odds or rank>latest_odds[key][0]:latest_odds[key]=(rank,r)
    return latest, latest_odds, issues

def valid_quotes(date,gid,r,issues):
    seen=set()
    for q in r.get('quotes') or []:
        identity=(q.get('bookmaker'),q.get('market'),norm(q.get('player')),q.get('line'),q.get('side'))
        if identity in seen:
            issues.append({'date':date,'game_id':gid,'reason':'duplicate_archived_quote'});continue
        seen.add(identity)
        expected=num(q.get('expected_roi_percent'));line=num(q.get('line'));price=num(q.get('american_odds'));p=num(q.get('win_probability'))
        side=q.get('side');obs=MARKETS.get(q.get('market'))
        updated=timestamp(q.get('quote_updated_utc')); odds=timestamp(r.get('odds_snapshot_utc'))
        if q.get('game_id')!=gid or not updated or not odds or updated>odds or q.get('projection_utc')!=r.get('projection_utc') or q.get('odds_snapshot_utc')!=r.get('odds_snapshot_utc') or expected is None or line is None or price is None or abs(price)<100 or p is None or not 0<=p<=1 or not obs or side not in ('over','under'):
            issues.append({'date':date,'game_id':gid,'reason':'invalid_archived_quote'});continue
        yield q

def closing_line_report(records,today,window_minutes=60):
    """First positive signal vs last observed same-book pregame market.
    No settlement or repricing needed; report only prior Eastern game dates.
    Repeated captures of old odds never become new market observations.
    """
    from math import isfinite
    aliases=load_aliases()
    entries={}; markets={}
    def identity(date,gid,q):
        return (date,gid,q.get('team'),norm(q.get('player')),q.get('market'),q.get('bookmaker'),q.get('side'))
    def implied(price):
        return -price/(100-price) if price<0 else 100/(100+price)
    def mean(vals):
        return round(statistics.mean(vals),4) if vals else None
    for raw in records:
        r=canonical_record(raw,aliases)
        date=r.get('date_eastern','')
        game=r.get('game') or {};gid=game.get('game_id')
        cap=timestamp(r.get('captured_at_utc'));proj=timestamp(r.get('projection_utc'))
        snap=timestamp(r.get('odds_snapshot_utc'));tip=timestamp(game.get('tipoff_utc'))
        if not date or date>=today or not gid or not all((cap,proj,snap,tip)) or not (proj<=cap<tip and snap<=cap):continue
        pools={'v4':r.get('quotes') or [],**(r.get('experimental_quotes') or {})}
        for version,quotes in pools.items():
            for q in valid_quotes(date,gid,{**r,'quotes':quotes},[]):
                line=num(q['line']);price=num(q['american_odds']);edge=num(q['expected_roi_percent'])
                if not all(isfinite(v) for v in (line,price,edge)):continue
                updated=timestamp(q['quote_updated_utc'])
                k=identity(date,gid,q)
                if not all(k):continue
                # Rank by odds observation, not forecast regeneration time.
                rank=(snap,updated)
                prev=markets.get(k)
                if prev is None or rank>prev[0]:
                    markets[k]=(rank,{(line,price)},tip)
                elif rank==prev[0]:
                    prev[1].add((line,price))
                if edge>0:
                    ek=(version,*k);erank=(cap,snap,updated)
                    prev=entries.get(ek)
                    if prev is None or erank<prev[0]:
                        entries[ek]=(erank,line,price,edge,tip)
    rows=[]
    for (version,*k),entry in sorted(entries.items(),key=lambda item:str(item[0])):
        rank,line,price,edge,tip=entry
        date,gid,team,player,market,book,side=k
        (snap,updated),prices,close_tip=markets[tuple(k)]
        age=(close_tip-snap).total_seconds()/60
        quote_age=(close_tip-updated).total_seconds()/60
        row={'date':date,'game_id':gid,'team':team,'player':player,'market':market,'bookmaker':book,'side':side,'model':version,
             'entry_line':line,'entry_odds':price,'entry_roi_percent':edge,'entry_capture_utc':rank[0].isoformat(),
             'last_snapshot_utc':snap.isoformat(),'minutes_before_tip':round(age,1),'quote_age_minutes':round(quote_age,1)}
        if close_tip!=tip:status='tipoff_mismatch'
        elif snap<=rank[0]:status='no_later_observation'
        elif age>window_minutes or quote_age>window_minutes:status='stale_last_quote'
        elif len(prices)!=1:status='ambiguous_last_market'
        else:
            cl,cp=next(iter(prices));movement=(cl-line)*(1 if side=='over' else -1)
            row.update(last_line=cl,last_odds=cp,line_movement=round(movement,4))
            if movement==0:
                # Raw implied probability movement, not no-vig market EV.
                delta=100*(implied(cp)-implied(price))
                row.update(price_clv_pp=round(delta,4),direction='positive' if delta>1e-9 else 'negative' if delta< -1e-9 else 'unchanged')
            else:
                # Different lines have different payoff events. Never convert
                # raw prices into a common probability or monetary CLV.
                row.update(price_clv_pp=None,direction='line_favorable' if movement>0 else 'line_unfavorable')
            status='matched'
        row['status']=status
        rows.append(row)
    def metrics(rs):
        matched=[x for x in rs if x['status']=='matched']
        same=[x for x in matched if x.get('price_clv_pp') is not None]
        changed=[x for x in matched if x['line_movement']!=0]
        return {'signals':len(rs),'matched':len(matched),'same_line':len(same),'changed_line':len(changed),
                'mean_price_clv_pp':mean([x['price_clv_pp'] for x in same]),
                'price_positive':sum(x['direction']=='positive' for x in same),
                'price_negative':sum(x['direction']=='negative' for x in same),
                'price_unchanged':sum(x['direction']=='unchanged' for x in same),
                'line_favorable':sum(x['direction']=='line_favorable' for x in changed),
                'line_unfavorable':sum(x['direction']=='line_unfavorable' for x in changed),
                'mean_minutes_before_tip':mean([x['minutes_before_tip'] for x in matched]),
                'coverage_reasons':{s:sum(x['status']==s for x in rs) for s in sorted({x['status'] for x in rs})}}
    return {'window_minutes':window_minutes,'overall':metrics(rows),
            'models':{v:metrics([x for x in rows if x['model']==v]) for v in sorted({x['model'] for x in rows})},
            'v11_by_market':{m:metrics([x for x in rows if x['model']=='v11-combined' and x['market']==m]) for m in sorted({x['market'] for x in rows if x['model']=='v11-combined'})},
            'rows':rows,
            'method':'First archived positive signal per model, game, player, market, book and side versus the last observed same-book quote. A later snapshot and quote update within 60 minutes of tipoff are required. Same-line CLV is raw implied probability movement in percentage points, not de-vigged EV. Changed-line direction is reported separately and does not account for juice changes. Not verified official closes; missing or stale quotes are excluded from CLV averages. Model signals and books are correlated.'}

def pending_report(records, today):
    """Only today's genuine immutable captures; no results or repricing."""
    latest, latest_odds, issues=select_snapshots(records, lambda date: date==today)
    quotes=[]
    for (date,gid),(_,r) in sorted(latest_odds.items()):
        for q in valid_quotes(date,gid,r,issues):
            quotes.append(q)
    positive=[q for q in quotes if q['expected_roi_percent']>0]
    def breakdown(key):
        groups=defaultdict(list)
        for q in positive:groups[key(q)].append(q['expected_roi_percent'])
        return {str(k):{'selections':len(v),'mean_expected_roi_percent':round(statistics.mean(v),2)} for k,v in sorted(groups.items())}
    experimental={}
    for _,r in latest.values():
        for t in r['game'].get('teams') or []:
            for p in t.get('players') or []:
                for v,x in (p.get('ExperimentalModels') or {}).items():
                    m=experimental.setdefault(v,{'player_projections':0,'quotes_priced':0,'positive_selections':0,'shot_fallbacks':0,'edges':[]})
                    m['player_projections']+=1
                    m['shot_fallbacks']+=int(x.get('ShotStatus')=='fallback_rotation_only_missing_shots')
    for (date,gid),(_,r) in latest_odds.items():
        for v,qs in (r.get('experimental_quotes') or {}).items():
            m=experimental.setdefault(v,{'player_projections':0,'quotes_priced':0,'positive_selections':0,'shot_fallbacks':0,'edges':[]})
            for q in valid_quotes(date,gid,{**r,'quotes':qs},issues):
                m['quotes_priced']+=1
                if q['expected_roi_percent']>0:m['edges'].append(q['expected_roi_percent'])
    for m in experimental.values():
        edges=m.pop('edges');m['positive_selections']=len(edges);m['mean_expected_roi_percent']=round(statistics.mean(edges),2) if edges else None
    captures=[timestamp(r['captured_at_utc']) for _,r in list(latest.values())+list(latest_odds.values())]
    return {'date_eastern':today,'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'status':'PARTIAL' if issues else 'OK' if latest else 'NO_ARCHIVES',
            'latest_capture_utc':max(captures).isoformat() if captures else None,
            'games':len(latest),'games_with_priced_quotes':len({q['game_id'] for q in quotes}),
            'player_projections':sum(len(t.get('players') or []) for _,r in latest.values() for t in r['game'].get('teams') or []),
            'quotes_priced':len(quotes),'positive_selections':len(positive),
            'mean_expected_roi_percent':round(statistics.mean(q['expected_roi_percent'] for q in positive),2) if positive else None,
            'by_tier':breakdown(lambda q:tier(q['expected_roi_percent'])),
            'by_model_version':breakdown(lambda q:q.get('model_version') or 'unknown'),
            'issues':issues,'experimental_models':experimental,
            'method':'Latest valid archived pregame projection and latest odds-backed capture per game, same selection and validation as grading. Today is pending until the next-day grading run. Individual sportsbook quote sides are hypothetical opportunities, not placed bets.'}

def grade(records, logs, today):
    latest, latest_odds, issues=select_snapshots(records, lambda date: date<today)
    projections=[]; quotes=[]
    def actual(date,gid,team,player):
        if not gid.startswith('espn_event_'):return None
        candidates=[a for a in logs.get('espn_'+gid.removeprefix('espn_event_'),[]) if a.get('game_date')==date and a.get('source')=='ESPN_UNOFFICIAL' and team_matches(team,a.get('team')) and norm(player)==norm(a.get('player'))]
        return candidates[0] if len(candidates)==1 else None
    for (date,gid),(_,r) in sorted(latest.items()):
        for t in r['game'].get('teams') or []:
            for p in t.get('players') or []:
                a=actual(date,gid,t.get('team'),p.get('Player'))
                if a is None:
                    issues.append({'date':date,'game_id':gid,'player':p.get('Player'),'reason':'missing_or_ambiguous_final_player'});continue
                stats={}
                for field,(pred,obs) in FIELDS.items():
                    x=num(p.get(pred));y=num(a.get(obs))
                    if x is not None and y is not None:stats[field]={'projection':x,'actual':y,'error':x-y}
                if stats:projections.append({'date':date,'game_id':gid,'player':p.get('Player'),'team':t.get('team'),'model_version':p.get('ModelVersion','unknown'),'projection_utc':r['projection_utc'],'stats':stats})
    for (date,gid),(_,r) in sorted(latest_odds.items()):
        for q in valid_quotes(date,gid,r,issues):
            line=num(q.get('line')); price=num(q.get('american_odds')); side=q.get('side'); obs=MARKETS[q['market']]
            a=actual(date,gid,q.get('team'),q.get('player'))
            value=num(a.get(obs)) if a else None
            if value is None:result='ungraded';pnl=None
            elif value==line:result='push';pnl=0
            else:
                result='win' if (value>line)==(side=='over') else 'loss'
                pnl=(price/100 if price>0 else 100/abs(price)) if result=='win' else -1
            quotes.append({**q,'date':date,'captured_at_utc':r['captured_at_utc'],'pricing_version':r.get('pricing_version'),'actual':value,'result':result,'profit_units':round(pnl,6) if pnl is not None else None})
    pos=[q for q in quotes if q['expected_roi_percent']>0]
    def groups(key):
        out=defaultdict(list)
        for q in pos:out[key(q)].append(q)
        return {str(k):summary(v) for k,v in sorted(out.items())}
    metrics={}
    for field in FIELDS:
        errors=[p['stats'][field]['error'] for p in projections if field in p['stats']]
        metrics[field]={'n':len(errors),'mae':round(statistics.mean(map(abs,errors)),3) if errors else None,'bias':round(statistics.mean(errors),3) if errors else None}
    return {'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'method':'Latest actually captured pre-tipoff projection per game; latest odds-backed capture per game. Each distinct sportsbook/market/player/line/side priced quote is graded independently; positive expected ROI only in summaries. Flat 1-unit hypothetical stake; correlated quotes are not independent bets. No backfill or post-tipoff repricing.','status':'PARTIAL' if issues or any(q['result']=='ungraded' for q in pos) else 'OK','games':len(latest),'players_graded':len(projections),'projection_metrics':metrics,'quotes_priced':len(quotes),'positive_roi':summary(pos),'by_tier':groups(lambda q:tier(q['expected_roi_percent'])),'by_bookmaker':groups(lambda q:q['bookmaker']),'by_market':groups(lambda q:q['market']),'by_model_version':groups(lambda q:q.get('model_version') or 'unknown'),'by_date':groups(lambda q:q['date']),'issues':issues,'projection_rows':projections,'rows':quotes}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pending-only',action='store_true')
    args=parser.parse_args()
    records=[json.loads(p.read_text()) for p in sorted(ARCHIVES.glob('*/*.json'))]
    today=dt.datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    pending=pending_report(records,today)
    # A no-change 15-minute poll must not trigger a new deployment solely
    # because the report generation timestamp advanced.
    previous={}
    if PENDING.exists():
        try:previous=json.loads(PENDING.read_text())
        except (ValueError,OSError):pass
    comparable=lambda d:{k:v for k,v in d.items() if k!='generated_at_utc'}
    if comparable(previous)!=comparable(pending):
        PENDING.write_text(json.dumps(pending,indent=2)+'\n')
    print(json.dumps({k:pending[k] for k in ('date_eastern','games','player_projections','quotes_priced','positive_selections','mean_expected_roi_percent')}))
    if args.pending_only:return
    logs=defaultdict(list)
    if LOGS.exists():
        with LOGS.open(newline='',encoding='utf-8') as f:
            for r in csv.DictReader(f):logs[r['game_id']].append(r)
    result=grade(records,logs,today)
    from acc_model_comparison import compare
    result['experimental_comparison']=compare(records,logs,today)
    result['closing_line_value']=closing_line_report(records,today)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'games':result['games'],'players_graded':result['players_graded'],'positive_roi':result['positive_roi']}))
if __name__=='__main__':main()
