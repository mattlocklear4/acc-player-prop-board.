#!/usr/bin/env python3
"""Read-only CBBD team stats diagnostic. Never writes API credentials to output."""
import csv, json, os, urllib.request, urllib.parse, urllib.error, time
from pathlib import Path

BASE='https://api.collegebasketballdata.com'
OUT=Path('data/cbbd/team_test'); OUT.mkdir(parents=True,exist_ok=True)
KEY=os.environ.get('CBBD_API_KEY','').strip()
if not KEY: raise SystemExit('Missing CBBD_API_KEY secret')

def get(path,season):
    url=BASE+path+'?'+urllib.parse.urlencode({'season':season,'conference':'ACC'})
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+KEY,'Accept':'application/json','User-Agent':'acc-player-prop-board/1.7'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429,500,502,503,504) and attempt<2:
                time.sleep(3*(attempt+1));continue
            raise RuntimeError(f'CBBD HTTP {e.code} for season {season}: '+e.read(200).decode('utf-8','replace')) from e

def flatten(obj,prefix=''):
    result={}
    for k,v in obj.items():
        key=prefix+k
        if isinstance(v,dict):result.update(flatten(v,key+'_'))
        elif isinstance(v,(str,int,float,bool)) or v is None:result[key]=v
    return result

report=[]
for season in (2025,2026,2027):
    data=get('/stats/team/season',season)
    if not isinstance(data,list):raise RuntimeError(f'Season {season}: expected list, got {type(data).__name__}')
    if not data:raise RuntimeError(f'Season {season}: no ACC team stats returned; refusing to label as success')
    if not all(isinstance(x,dict) for x in data):raise RuntimeError(f'Season {season}: unexpected response structure')
    flat=[flatten(x) for x in data]
    fields=sorted(set().union(*(r.keys() for r in flat)))
    with (OUT/f'acc_team_stats_{season}.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(flat)
    # JSON preserves the original nested structure for accurate mapping.
    (OUT/f'acc_team_stats_{season}.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    report.append({'season':season,'rows':len(data),'fields':fields,'example':flat[0]})
    print(f'{season}: {len(data)} teams, {len(fields)} flattened fields',flush=True)
(OUT/'schema_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('SUCCESS: team stats test finished; data saved to '+str(OUT))
