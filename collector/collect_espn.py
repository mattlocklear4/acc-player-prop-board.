#!/usr/bin/env python3
"""Collect final ACC men's basketball box scores from ESPN's unofficial public API.

Independent of CBBD quota. Keep ESPN records in a separate CSV: ESPN IDs are not
CBBD IDs and advanced CBBD metrics cannot be reconstructed from basic box scores.
"""
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/espn/acc_player_games_2027.csv'
STATUS=ROOT/'data/espn/collector_status.json'
FIELDS=['source','season','game_id','game_date','team','team_id','opponent','home','athlete_id','player','starter','minutes','points','reb','assists','three_pm','fgm','fga','three_pa','ftm','fta','oreb','dreb','steals','blocks','turnovers','fouls']
BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/'
def get(path,params):
    url=BASE+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'ACC-research-boxscores/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as resp:return json.load(resp)
def num(v):
    if v is None or str(v).strip() in ('','--','-'):return ''
    try:return float(v)
    except (TypeError,ValueError):return ''
def pair(v):
    a=str(v or '').split('-')
    return (num(a[0]),num(a[1])) if len(a)==2 else ('','')
def parse_team(group,game_id,date,opponent,home):
    team=group.get('team') or {}
    result=[]
    for stats_group in group.get('statistics') or []:
        keys=[str(k).lower() for k in (stats_group.get('keys') or stats_group.get('names') or [])]
        labels=[str(k).lower() for k in (stats_group.get('labels') or [])]
        for item in stats_group.get('athletes') or []:
            athlete=item.get('athlete') or {}
            values=item.get('stats') or []
            if not athlete.get('displayName') or not values:continue
            fields=dict(zip(keys,values));fields.update(dict(zip(labels,values)))
            def val(*names):
                for n in names:
                    v=fields.get(n.lower())
                    if v is not None:return v
                return None
            minutes=num(val('minutes','min') or values[0])
            if minutes=='':continue
            fg,fa=pair(val('fieldGoalsMade-fieldGoalsAttempted','fg'))
            th,tha=pair(val('threePointFieldGoalsMade-threePointFieldGoalsAttempted','3pt'))
            ft,fta=pair(val('freeThrowsMade-freeThrowsAttempted','ft'))
            row={'source':'ESPN_UNOFFICIAL','season':2027,'game_id':'espn_'+str(game_id),
                 'game_date':date,'team':team.get('displayName') or team.get('location') or '',
                 'team_id':team.get('id'),'opponent':opponent,'home':home,
                 'athlete_id':athlete.get('id'),'player':athlete.get('displayName'),
                 'starter':item.get('starter',''),'minutes':minutes,
                 'points':num(val('points','pts')),'reb':num(val('totalRebounds','reb')),
                 'assists':num(val('assists','ast')),'three_pm':th if th!='' else num(val('threePointFieldGoalsMade','3pm')),
                 'fgm':fg,'fga':fa,'three_pa':tha,'ftm':ft,'fta':fta,
                 'oreb':num(val('offensiveRebounds','oreb')),'dreb':num(val('defensiveRebounds','dreb')),
                 'steals':num(val('steals','stl')),'blocks':num(val('blocks','blk')),
                 'turnovers':num(val('turnovers','to')),'fouls':num(val('fouls','pf'))}
            if row['points']=='' or row['reb']=='' or row['assists']=='':
                continue
            result.append(row)
    return result
def main():
    today=dt.datetime.now(ZoneInfo('America/New_York')).date()
    existing={}
    if OUT.exists():
        with OUT.open(newline='',encoding='utf-8') as f:
            for r in csv.DictReader(f):
                existing[(r['game_id'],str(r['team_id']),str(r['athlete_id']))]=r
    seen=set();problems=[];new=0;finals=0
    for delta in range(1,5):
        day=today-dt.timedelta(days=delta)
        try:board=get('scoreboard',{'dates':day.strftime('%Y%m%d'),'groups':'50','limit':500})
        except Exception as exc:
            problems.append({'date':str(day),'reason':'scoreboard_unavailable','error':type(exc).__name__});continue
        for event in board.get('events') or []:
            eid=str(event.get('id') or '')
            if not eid or eid in seen:continue
            seen.add(eid)
            competitions=event.get('competitions') or []
            if not competitions or not (competitions[0].get('status') or {}).get('type',{}).get('completed'):continue
            try:box=get('summary',{'event':eid})
            except Exception as exc:
                problems.append({'game':eid,'reason':'summary_unavailable','error':type(exc).__name__});continue
            groups=(box.get('boxscore') or {}).get('players') or []
            if len(groups)!=2:
                problems.append({'game':eid,'reason':'missing_two_team_boxscore'});continue
            comps=competitions[0].get('competitors') or []
            by_id={str(c.get('team',{}).get('id')):c for c in comps}
            rows=[]
            for g in groups:
                tid=str((g.get('team') or {}).get('id') or '')
                c=by_id.get(tid,{})
                opponents=[x for x in comps if str(x.get('team',{}).get('id'))!=tid]
                opponent=(opponents[0].get('team') or {}).get('displayName','') if opponents else ''
                rows.extend(parse_team(g,eid,str(day),opponent,c.get('homeAway')=='home'))
            if len(rows)<10:
                problems.append({'game':eid,'reason':'incomplete_or_unparseable_players','parsed':len(rows)});continue
            finals+=1
            for r in rows:
                k=(r['game_id'],str(r['team_id']),str(r['athlete_id']))
                if k not in existing:new+=1
                existing[k]=r
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if existing:
        with OUT.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
            w.writerows(sorted(existing.values(),key=lambda r:(r['game_date'],r['game_id'],r['team'],r['player'])))
    report={'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'source':'ESPN unofficial public scoreboard/summary','completed_games_parsed':finals,
            'new_player_rows':new,'total_player_rows':len(existing),'issues':problems,
            'status':'OK' if not problems else 'PARTIAL_REVIEW_REQUIRED'}
    STATUS.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    if not existing and problems:raise RuntimeError('No usable ESPN results and provider errors; check logs')
if __name__=='__main__':main()
