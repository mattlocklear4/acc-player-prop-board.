#!/usr/bin/env python3
"""Convert The Odds API Google Sheets player props export to DraftKings CSV.
Offline only. Input is the 11-column PlayerProps.gs format; no API calls.
"""
import argparse,csv
from pathlib import Path
MARKETS={'player_points':'points','player_rebounds':'rebounds','player_assists':'assists',
         'player_threes':'threes'}
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',default='data/draftkings_player_props.csv')
    a=p.parse_args()
    with open(a.input,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not {'id','bookmaker','market','label','description','price','point'}.issubset(reader.fieldnames or []):
            p.error('Expected Google Sheets PlayerProps.gs columns: id,bookmaker,market,label,description,price,point')
        pairs={}
        for r in reader:
            if (r.get('bookmaker') or '').strip().lower()!='draftkings':continue
            market=MARKETS.get((r.get('market') or '').strip())
            side=(r.get('label') or '').strip().lower()
            if not market or side not in ('over','under'):continue
            player=(r.get('description') or '').strip()
            point=(r.get('point') or '').strip()
            if not player or not point:continue
            key=(r.get('id'),player,market,point)
            item=pairs.setdefault(key,{'player':player,'stat':market,'line':point,'over_odds':'','under_odds':'','game_id':'','book':'DraftKings'})
            item[side+'_odds']=(r.get('price') or '').strip()
    rows=[r for r in pairs.values() if r['over_odds'] and r['under_odds']]
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['player','stat','line','over_odds','under_odds','game_id','book'])
        w.writeheader();w.writerows(rows)
    print(f'DraftKings paired player props: {len(rows)}; no API calls')
if __name__=='__main__':main()
