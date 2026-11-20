#!/usr/bin/env python3
"""Convert capped DraftKings preview to a CSV for the existing ROI comparison. Offline."""
import csv,json
from collections import defaultdict
from pathlib import Path
src=Path('research/acc_stage8b_multibook_preview.json')
out=Path('data/multibook_player_props.csv')
data=json.loads(src.read_text())
mapping={'player_points':'points','player_rebounds':'rebounds','player_assists':'assists','player_threes':'threes'}
paired={}
for event in data.get('events',[]):
    for p in event.get('props',[]):
        stat=mapping.get(p.get('market'))
        side=str(p.get('side') or '').lower()
        if not stat or side not in ('over','under') or p.get('line') is None or not p.get('player'):continue
        book=p.get('bookmaker') or 'unknown'
        key=(event['event_id'],book,p['player'],stat,str(p['line']))
        item=paired.setdefault(key,{'player':p['player'],'stat':stat,'line':p['line'],
            'over_odds':'','under_odds':'','game_id':event.get('schedule_game_id') or '',
            'book':book})
        item[side+'_odds']=p.get('odds')
rows=[r for r in paired.values() if r['over_odds']!='' and r['under_odds']!='']
out.parent.mkdir(parents=True,exist_ok=True)
with out.open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['player','stat','line','over_odds','under_odds','game_id','book'])
    writer.writeheader();writer.writerows(rows)
print('Paired multi-book props:',len(rows),'No additional API requests')
