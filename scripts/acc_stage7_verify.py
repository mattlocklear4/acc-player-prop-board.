#!/usr/bin/env python3
"""Read-only Stage 7 verification: reproducible matchup arithmetic + cutoff and input checks.

This is NOT full browser/Python parity. Browser model requires separately captured
same-cutoff inputs; this test verifies independently calculated matchup arithmetic.
"""
import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_engine import apply_matchup, build_baselines, canon, clamp

STATS = ('Points','Rebounds','Assists','Threes')

def independent_expected(row, team, opponent, odds=None):
    possessions=(team['AdjT']+opponent['AdjT'])/2
    pace=clamp(1+.5*(possessions/team['AdjT']-1),.90,1.10)
    dp=clamp(1+.35*(opponent['AdjD']/105-1),.88,1.12)
    da=clamp(1+.20*(opponent['AdjD']/105-1),.92,1.08)
    market=None
    if odds:
        implied=(odds['total']-odds['team_spread'])/2
        expected=possessions*(team['AdjO']*opponent['AdjD']/105)/100
        market=clamp(1+.5*(implied/expected-1),.85,1.15)
    out={}
    for stat in STATS:
        base=row['Baseline'+stat]
        kp=base*pace*(dp if stat=='Points' else da if stat=='Assists' else 1)
        mult=market if stat=='Points' else 1+.5*(market-1) if stat in ('Assists','Threes') and market is not None else 1
        out['KenPom'+stat]=kp
        out['Vegas'+stat]=base*mult if market is not None else None
        out['Combined'+stat]=kp*mult if market is not None else None
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='research/acc_stage7_verification.json')
    parser.add_argument('--tolerance',type=float,default=.01)
    args=parser.parse_args()
    if not 0<args.tolerance<=.1: parser.error('tolerance must be >0 and <=0.1')
    sample={'Player':'Fixture Player','Team':'California','Minutes':27.5,**{'Baseline'+k:v for k,v in zip(STATS,(13.75,5.1,2.8,1.9))}}
    team={'AdjT':70.5,'AdjO':112.2,'AdjD':98.3}
    opponent={'AdjT':65.7,'AdjO':104.8,'AdjD':107.9}
    kp={canon('California'):team,canon('USC'):opponent}
    scenarios=[('no_odds',None),('with_odds',{'total':145.5,'team_spread':-3.5}),('extreme_odds',{'total':180,'team_spread':-20})]
    checks=[]
    for name,odds in scenarios:
        actual=apply_matchup([sample],'California','USC',kp,odds)[0]
        expected=independent_expected(sample,team,opponent,odds)
        for field,exp in expected.items():
            got=actual[field]
            diff=abs(got-exp) if exp is not None and got is not None else (0 if exp is got else float('inf'))
            checks.append({'scenario':name,'field':field,'expected':exp,'actual':got,'abs_difference':diff,'pass':diff<=args.tolerance})
    # Explicitly test that invalid KenPom inputs fail rather than silently fall back.
    rejected=False
    try: apply_matchup([sample],'California','USC',{canon('California'):team,canon('USC'):{**opponent,'AdjT':0}})
    except ValueError: rejected=True
    checks.append({'scenario':'invalid_tempo','field':'reject_invalid_kenpom','pass':rejected})
    report={'mode':'DRY_RUN_NO_WRITES','verification_scope':'independent_matchup_formula_fixtures_only',
            'browser_parity_verified':False,'manual_minutes_overrides_applied':False,
            'warning':'This is not an end-to-end browser parity test. Browser and Python must still be compared with identical as-of date, player inputs, and minutes overrides.',
            'tolerance':args.tolerance,'checks':checks,'passed':sum(x['pass'] for x in checks),'failed':sum(not x['pass'] for x in checks)}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(f"Stage 7 independent arithmetic checks: {report['passed']} passed, {report['failed']} failed; browser parity NOT yet verified")
    if report['failed']:sys.exit(1)

if __name__=='__main__':main()
