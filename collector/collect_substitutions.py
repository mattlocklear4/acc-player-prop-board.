"""Fetch documented CBBD team-season substitution stints; private storage only."""
import json,datetime as dt,os,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
from collect_cbbd import TEAMS

def collect(folder,key):
    result={};issues=[]
    for team in TEAMS:
        url='https://api.collegebasketballdata.com/substitutions/team?'+urlencode({'season':2027,'team':team})
        try:
            with urlopen(Request(url,headers={'Authorization':'Bearer '+key,'Accept':'application/json'}),timeout=50) as r:data=json.load(r)
            if not isinstance(data,list) or any(not isinstance(x,dict) for x in data):raise ValueError('invalid response')
            if not data:issues.append(team+': empty response')
            else:result[team]=data
        except HTTPError as e:
            issues.append(team+': HTTP '+str(e.code))
            if e.code in (401,403,429):break
        except Exception as e:issues.append(team+': '+type(e).__name__)
    if issues or len(result)!=18:raise ValueError('Incomplete substitution collection: '+', '.join(issues))
    summary={'season':2027,'last_successful_run_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'team_count':len(result),'stints':sum(len(v) for v in result.values()),'api_requests':18}
    (folder/'acc_substitutions_2027.json').write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')
    (folder/'acc_substitution_summary_2027.json').write_text(json.dumps(summary),encoding='utf-8')
    return summary
