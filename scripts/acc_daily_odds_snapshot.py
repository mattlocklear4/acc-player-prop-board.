#!/usr/bin/env python3
"""One daily ACC odds snapshot, with no paid retry after a dated snapshot exists.

The Odds API free plan's 500-credit cycle is protected by a 50-credit reserve.
Requests are restricted to 4 markets, <=6 games, and <=24 estimated credits.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TODAY=dt.datetime.now(ZoneInfo('America/New_York')).date().isoformat()
DEST=ROOT/'data/odds_snapshots'/f'{TODAY}.json'
def main():
    if DEST.exists():
        print('Existing daily snapshot; refusing to spend credits again:',DEST)
        return
    if not os.getenv('ODDS_API_KEY'):
        raise RuntimeError('ODDS_API_KEY is missing; no paid requests made')
    # Only future games within 24 hours; the odds script filters to today ET.
    subprocess.run([sys.executable,'scripts/acc_schedule.py','--season','2027',
                    '--horizon-hours','24'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'scripts/acc_stage8b_multibook.py',
                    '--schedule','research/acc_schedule_dry_run.json',
                    '--daily','--fetch-odds','--max-events','6',
                    '--max-credits','24','--min-credits-remaining','50'],
                   cwd=ROOT,check=True)
    result=json.loads((ROOT/'research/acc_stage8b_multibook_preview.json').read_text())
    # A provider/network failure must not silently consume the day's only attempt.
    quota=result.get('quota') or {}
    result['snapshot_date_eastern']=TODAY
    result['daily_credit_cap']=24
    result['monthly_reserve_credits']=50
    result['note']='Single pregame snapshot; games with no available player props may be missing.'
    DEST.parent.mkdir(parents=True,exist_ok=True)
    DEST.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved',DEST,'paid requests:',quota.get('requests_sent',0),
          'reported credits:',quota.get('credits_spent_reported',0))
if __name__=='__main__':main()
