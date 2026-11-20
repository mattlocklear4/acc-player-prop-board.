#!/usr/bin/env python3
"""Build public, read-only Friday board JSON from diagnostic artifacts. No secrets."""
import json
from pathlib import Path
def load(path):
    p=Path(path)
    return json.loads(p.read_text()) if p.exists() else {}
slate=load('research/acc_friday_slate.json')
value=load('research/acc_betonline_value_preview.json')
minutes=load('research/acc_friday_minutes_review.json')
odds=load('research/acc_stage8b_betonline_preview.json')
output={'date_eastern':slate.get('date_eastern'),'generated_at_utc':slate.get('generated_at_utc'),
        'schedule_status':slate.get('schedule_status'),'games':slate.get('games',[]),
        'minute_reviews':minutes.get('rows',[]),'value_rows':value.get('rows',[]),
        'value_warnings':value.get('warnings',[]),
        'odds_quota':odds.get('quota',{}),'odds_warnings':odds.get('warnings',[]),
        'odds_generated_at_utc':odds.get('generated_at_utc'),
        'caution':'Unverified research projections. Injury/rotation uncertainty. Estimated ROI is not a calibrated edge.'}
dest=Path('data/friday_board.json')
dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps(output,separators=(',',':'))+'\n')
print('Public Friday board:',len(output['games']),'games;',len(output['value_rows']),'prop lines')
