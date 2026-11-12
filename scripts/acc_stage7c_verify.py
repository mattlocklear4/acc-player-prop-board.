#!/usr/bin/env python3
"""Read-only JS/Python matchup parity on deterministic fixtures, with minutes override tests.
Does not claim actual browser runtime parity or automatic browser override sync.
"""
import json, math, subprocess, sys
from pathlib import Path
from research_engine import apply_matchup

FIELDS=['Points','Rebounds','Assists','Threes']

def override_minutes(row, manual_minutes, manual_stats=None):
    """Match app.js projectionValue: per-stat manual value takes precedence over minutes scaling."""
    if not isinstance(manual_minutes,(int,float)) or not math.isfinite(manual_minutes) or manual_minutes<0 or manual_minutes>80:
        raise ValueError('Invalid minutes override')
    result=dict(row); original=row['Minutes']; manual_stats=manual_stats or {}
    for k in FIELDS:
        v=row.get('Baseline'+k)
        if k in manual_stats:
            chosen=manual_stats[k]
            if not isinstance(chosen,(int,float)) or not math.isfinite(chosen) or chosen<0:
                raise ValueError('Invalid stat override')
            result['Baseline'+k]=chosen
        elif v is not None and original>0:
            result['Baseline'+k]=max(0,v*manual_minutes/original)
    result['Minutes']=manual_minutes
    return result

def run():
    team={'AdjT':69.4,'AdjO':115.7,'AdjD':99.2}
    opp={'AdjT':64.8,'AdjO':104.1,'AdjD':108.5}
    kp={'testteam':team,'testopponent':opp}
    base={'Player':'Test Player','Team':'Test Team','Minutes':27.5,**{'Baseline'+k:v for k,v in zip(FIELDS,[14.4,5.1,2.8,1.7])}}
    fixtures=[]; expected=[]
    for minutes,stats in [(27.5,{}),(31.0,{}),(22.0,{'Points':18.0}),(0.0,{})]:
        row=override_minutes(base,minutes,stats)
        for odds in [None,{'total':146.5,'team_spread':-5.5},{'total':175,'team_spread':-20},{'total':110,'team_spread':15}]:
            fixture={'row':row,'team':team,'opponent':opp,'market':odds}
            fixtures.append(fixture)
            expected.append(apply_matchup([row],'Test Team','Test Opponent',kp,odds)[0])
    node=subprocess.run(['node',str(Path(__file__).with_name('acc_stage7c_matchup.js'))],input=json.dumps(fixtures),capture_output=True,text=True,check=True)
    actual=json.loads(node.stdout)
    failures=[];checks=0;maxdiff=0
    for i,(a,b) in enumerate(zip(actual,expected)):
        for model in ['KenPom','Vegas','Combined']:
            for field in FIELDS:
                key=model+field;x=a[key];y=b[key]
                checks+=1
                if x is None or y is None:
                    if x!=y:failures.append({'fixture':i,'key':key,'js':x,'python':y})
                else:
                    diff=abs(x-y);maxdiff=max(maxdiff,diff)
                    if diff>0.01:failures.append({'fixture':i,'key':key,'difference':diff})
    output={'stage':'7C','scope':'independent JavaScript/Python matchup arithmetic; controlled fixtures','fixtures':len(fixtures),'values_checked':checks,'max_absolute_difference':maxdiff,'failures':failures,'passed':not failures,'manual_minutes_override_fixture_cases':4,'manual_minutes_live_sync':False,'actual_browser_runtime_parity':False,'supabase_writes':False}
    dest=Path('research/acc_stage7c_verification.json');dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
    if failures:sys.exit(1)
if __name__=='__main__':run()
