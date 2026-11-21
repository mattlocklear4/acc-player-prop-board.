#!/usr/bin/env python3
"""Grade archived Friday ACC pregame projections using ESPN public box scores.

ESPN is an unofficial public feed; unverified/unavailable games are omitted.
Never re-project with postgame data. Network failures do not fabricate results.
"""
import json,urllib.request,datetime as dt,statistics
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE_DIR=ROOT/'data/archives'
OUT=ROOT/'data/friday_grading.json'
FIELDS={'Points':'points','Rebounds':'rebounds','Assists':'assists','Threes':'threePointFieldGoalsMade'}
def number(v):
    try:return float(v)
    except (ValueError,TypeError):return None
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ACC-validation/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def statmap(keys,values):
    return dict(zip(keys,values))
def boxplayers(payload):
    found=defaultdict(list)
    for team in (payload.get('boxscore') or {}).get('players') or []:
        for group in team.get('statistics') or []:
            keys=group.get('keys') or group.get('names') or group.get('labels') or []
            labels=group.get('labels') or []
            for a in group.get('athletes') or []:
                athlete=a.get('athlete') or {}
                stats=a.get('stats') or []
                if not stats:continue
                raw=statmap(keys,stats)
                raw.update(statmap(labels,stats))
                raw={str(k).lower():v for k,v in raw.items()}
                row={'name':athlete.get('displayName') or athlete.get('fullName'),'id':str(athlete.get('id') or ''),
                     'minutes':number(raw.get('minutes') or raw.get('min') or stats[0])}
                for field,key in FIELDS.items():
                    val=raw.get(key.lower())
                    if val is None:
                        # ESPN commonly supplies 3PM-3PA as '3PT' string.
                        if field=='Threes':
                            val=raw.get('threepointfieldgoalsmade') or raw.get('3pm')
                            if val is None:
                                pair=raw.get('threepointfieldgoalsmade-threepointfieldgoalsattempted') or raw.get('3pt')
                                if isinstance(pair,str) and '-' in pair:val=pair.split('-')[0]
                        elif field=='Rebounds':val=raw.get('totalrebounds') or raw.get('reb')
                        else:val=raw.get(field.lower())
                    row[field]=number(val)
                if any(row.get(k) is not None for k in FIELDS):found[team.get('team',{}).get('id') or 'unknown'].append(row)
    return found
def norm(s):return ''.join(c for c in str(s or '').lower() if c.isalnum())
def main():
    today_et=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=5)).date()
    candidates=[p for p in ARCHIVE_DIR.glob('friday_????-??-??.json')
                if dt.date.fromisoformat(p.stem.replace('friday_','')) < today_et]
    if not candidates:
        raise RuntimeError('No past Friday pregame archive exists; cannot grade an overwritten upcoming board')
    source=max(candidates)
    archive=json.loads(source.read_text())
    if not archive.get('games') or archive.get('date_eastern')!=source.stem.replace('friday_',''):
        raise RuntimeError('Invalid immutable pregame snapshot: '+str(source))
    results=[];issues=[]
    for game in archive.get('games') or []:
        eid=str(game.get('game_id') or '').replace('espn_event_','')
        if not eid.isdigit():
            issues.append({'game_id':game.get('game_id'),'reason':'not_espn_event_id'});continue
        try:box=get('https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event='+eid)
        except Exception as exc:
            issues.append({'game_id':game.get('game_id'),'reason':'boxscore_unavailable','error_type':type(exc).__name__});continue
        if not (box.get('header') or {}).get('competitions'):
            issues.append({'game_id':game.get('game_id'),'reason':'no_competition_header'});continue
        status=(box['header']['competitions'][0].get('status') or {}).get('type') or {}
        if not status.get('completed'):
            issues.append({'game_id':game.get('game_id'),'reason':'game_not_final'});continue
        players=boxplayers(box)
        allplayers=[p for group in players.values() for p in group]
        if not allplayers:
            issues.append({'game_id':game.get('game_id'),'reason':'no_parseable_boxscore'});continue
        for team in game.get('teams') or []:
            for p in team.get('players') or []:
                matches=[a for a in allplayers if norm(a['name'])==norm(p.get('Player'))]
                if len(matches)!=1:continue
                actual=matches[0]
                row={'game_id':game['game_id'],'player':p.get('Player'),'team':team.get('team'),'actual':actual,
                     'baseline':{},'kenpom':{},'rotation_kenpom':{}}
                for field in ['Minutes']+list(FIELDS):
                    y=actual.get('minutes' if field=='Minutes' else field)
                    if y is None:continue
                    for model,prefix in [('baseline','Baseline'),('kenpom','KenPom'),('rotation_kenpom','RotationKenPom')]:
                        predicted=p.get('Minutes' if field=='Minutes' and model!='rotation_kenpom' else 'RotationMinutesScenario' if field=='Minutes' else prefix+field)
                        if isinstance(predicted,(int,float)):
                            row[model][field]={'projection':round(predicted,3),'actual':y,'error':round(predicted-y,3)}
                results.append(row)
    metrics={}
    for model in ['baseline','kenpom','rotation_kenpom']:
        metrics[model]={}
        for stat in ['Minutes']+list(FIELDS):
            errs=[r[model][stat]['error'] for r in results if stat in r[model]]
            metrics[model][stat]={'n':len(errs),'mae':round(statistics.mean(map(abs,errs)),3) if errs else None,
                'bias':round(statistics.mean(errs),3) if errs else None}
    output={'graded_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'projection_snapshot_utc':archive.get('generated_at_utc'),
            'slate_date_eastern':archive.get('date_eastern'),'status':'RESEARCH_GRADED_FROM_PUBLIC_ESPN',
            'games_in_snapshot':len(archive.get('games') or []),'players_graded':len(results),
            'metrics':metrics,'issues':issues,'rows':results,
            'caution':'Player names matched uniquely within game; ESPN public stats unofficial. No betting ROI or historical odds grading.'}
    if not results:
        raise RuntimeError('No player box scores matched; refusing to publish empty grading. Issues: '+json.dumps(issues))
    OUT.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'players_graded':len(results),'games_unavailable':len(issues),'metrics':metrics}))
if __name__=='__main__':main()
