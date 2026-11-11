#!/usr/bin/env python3
"""Collect US NCAAB pregame odds. Requires ODDS_API_KEY GitHub Actions secret."""
import datetime as dt, json, os, pathlib, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'acc_odds.json'
ACC = ['Boston College','California','Clemson','Duke','Florida State','Georgia Tech','Louisville','Miami','NC State','North Carolina','Notre Dame','Pittsburgh','SMU','Stanford','Syracuse','Virginia','Virginia Tech','Wake Forest']
ALIASES = {'California':['California Golden Bears','California'],'Miami':['Miami Hurricanes','Miami (FL)'],'NC State':['NC State Wolfpack','North Carolina State'],'SMU':['SMU Mustangs'],'Pittsburgh':['Pittsburgh Panthers','Pitt']}

def is_acc(name):
    n=' '.join(name.lower().replace('.','').split())
    for t in ACC:
        variants=ALIASES.get(t,[])+[t]
        if any(n==v.lower().replace('.','') or n.startswith(v.lower().replace('.','')+' ') for v in variants):return True
    return False

def main():
    key=os.environ.get('ODDS_API_KEY','').strip()
    if not key: raise SystemExit('ODDS_API_KEY missing; set repository Actions secret')
    q=urllib.parse.urlencode({'apiKey':key,'regions':'us','markets':'spreads,totals','oddsFormat':'american','dateFormat':'iso'})
    req=urllib.request.Request('https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/?'+q,headers={'User-Agent':'ACC-Prop-Research/1.0'})
    with urllib.request.urlopen(req,timeout=35) as response:
        games=json.load(response)
        remaining=response.headers.get('x-requests-remaining')
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    selected=[]
    for g in games:
        if not (is_acc(g.get('home_team','')) or is_acc(g.get('away_team',''))):continue
        books=[]
        for b in g.get('bookmakers',[]):
            markets={}
            for m in b.get('markets',[]):
                if m.get('key') in ('spreads','totals'):
                    markets[m['key']]={'last_update':m.get('last_update'),'outcomes':[{'name':o.get('name'),'point':o.get('point'),'price':o.get('price')} for o in m.get('outcomes',[])]}
            if markets:books.append({'key':b.get('key'),'title':b.get('title'),'markets':markets})
        selected.append({'id':g.get('id'),'commence_time':g.get('commence_time'),'home_team':g.get('home_team'),'away_team':g.get('away_team'),'bookmakers':books})
    snapshot={'collected_at':now,'source':'The Odds API','sport':'basketball_ncaab','games':selected}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(snapshot,indent=2)+'\n')
    archive=ROOT/'data'/'odds_history'/dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
    archive.mkdir(parents=True,exist_ok=True)
    (archive/(dt.datetime.now(dt.timezone.utc).strftime('%H%M%S')+'.json')).write_text(json.dumps(snapshot,separators=(',',':'))+'\n')
    print(f'Collected {len(selected)} ACC games; API credits remaining: {remaining or "not reported"}')

if __name__=='__main__':main()
  
