"""Offline ACC research projection engine. No database writes or network calls.

Mirrors app.js buildProjectionModel and matchup.js / vegas-matchup.js formulas.
Historical cutoff is exclusive: a game on the target date is never a model input.
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATS = {'Points': 'points', 'Rebounds': 'reb', 'Assists': 'assists', 'Threes': 'three_pm'}
ALIASES = {'floridastate':'floridast','miamiflorida':'miamifl','ncstate':'ncstate','northcarolinastate':'ncstate','cal':'california','pitt':'pittsburgh'}

def norm(s):
    return ''.join(c for c in str(s or '').lower() if c.isalnum())

def canon(s):
    n = norm(s)
    return ALIASES.get(n, n)

def numeric(value):
    try:
        return float(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None

def mean(values):
    a = [v for v in values if v is not None and math.isfinite(v)]
    return sum(a) / len(a) if a else None

def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def build_baselines(as_of, root=ROOT):
    """Only use current season games STRICTLY before as_of (YYYY-MM-DD)."""
    data = root / 'data' / 'cbbd'
    current = [r for r in read_csv(data/'acc_player_games_2027.csv') if r['game_date'] < as_of]
    history_raw = (read_csv(data/'acc_player_games_2026.csv') +
                   read_csv(data/'acc_player_games_2025.csv') +
                   read_csv(data/'acc_transfer_player_games_2025_2026.csv'))
    seen, history = set(), defaultdict(list)
    for r in history_raw:
        aid = r.get('athlete_id', '')
        if not aid: continue
        key = (r.get('season'), r.get('game_id'), r.get('team_id') or r.get('team'), aid)
        if key in seen: continue
        seen.add(key)
        history[aid].append(r)
    players = defaultdict(list)
    for r in current:
        if r.get('athlete_id') and r.get('player'):
            players[r['athlete_id']].append(r)
    result = []
    for aid, games in players.items():
        games.sort(key=lambda r: r['game_date'], reverse=True)
        r = games[0]
        h = sorted(history.get(aid, []), key=lambda x: (int(x['season']), x['game_date']), reverse=True)
        recent = games[:5]
        prior = [x for x in h if x['season'] == '2026']
        older = [x for x in h if x['season'] == '2025']
        avg = lambda records, key: mean([numeric(x.get(key)) for x in records])
        hm = avg(prior, 'minutes')
        if hm is None: hm = avg(older, 'minutes')
        cm, rm = avg(games, 'minutes'), avg(recent, 'minutes')
        w = len(games)/(len(games)+8)
        if cm is None: minutes = hm
        elif hm is None: minutes = cm
        else: minutes = (1-w)*hm + w*(.65*cm + .35*rm)
        if minutes is None: continue
        minutes = clamp(minutes, 0, 40)
        obj = {'Player':r['player'], 'AthleteId':aid, 'Team':r['team'], 'Minutes':minutes,
               'CurrentGP':len(games), 'HistoryGP':len(h),
               'Confidence':'Higher' if len(games)>=10 else 'Moderate' if len(h)>=12 else 'Limited'}
        for field, key in STATS.items():
            def rate(group):
                total = mins = 0
                for x in group:
                    val = numeric(x.get(key))
                    if val is None and key == 'reb':
                        a, b = numeric(x.get('oreb')), numeric(x.get('dreb'))
                        if a is not None and b is not None: val = a+b
                    minute = numeric(x.get('minutes'))
                    if val is not None and minute is not None and minute > 0:
                        total += val
                        mins += minute
                return total/mins if mins else None
            cr, hr, rr = rate(games), rate(prior), rate(recent)
            if hr is None: hr = rate(older)
            if cr is None: blended = hr
            elif hr is None: blended = cr
            else: blended = (1-w)*hr + w*(.65*cr + .35*(rr if rr is not None else cr))
            obj['Baseline'+field] = max(0, minutes*blended) if blended is not None else None
        result.append(obj)
    return sorted(result, key=lambda x: (x['Team'], x['Player']))

def load_kenpom(path):
    return {canon(r['Team']):r for r in read_csv(path)}

def apply_matchup(baselines, team, opponent, kp, odds=None):
    t, o = kp.get(canon(team)), kp.get(canon(opponent))
    if not t or not o: raise ValueError('Missing KenPom team/opponent: '+team+' / '+opponent)
    ta, oa, defense = (numeric(t['AdjT']), numeric(o['AdjT']), numeric(o['AdjD']))
    if any(v is None or v <= 0 for v in (ta, oa, defense)): raise ValueError('Invalid KenPom ratings')
    possessions = (ta+oa)/2
    pace = clamp(1+.5*(possessions/ta-1), .90, 1.10)
    defpts = clamp(1+.35*(defense/105-1), .88, 1.12)
    defast = clamp(1+.20*(defense/105-1), .92, 1.08)
    factor = None
    if odds is not None:
        total, spread = numeric(odds.get('total')), numeric(odds.get('team_spread'))
        if total is None or spread is None: raise ValueError('Both game total and team spread required')
        implied = (total-spread)/2
        expected = possessions*(numeric(t['AdjO'])*numeric(o['AdjD'])/105)/100
        if expected <= 0: raise ValueError('Invalid KenPom team expected points')
        factor = clamp(1+.5*(implied/expected-1), .85, 1.15)
    output=[]
    for row in baselines:
        if canon(row['Team']) != canon(team): continue
        p=dict(row)
        p.update({'Opponent':opponent, 'ProjectedPossessions':possessions, 'PaceFactor':pace,
                  'OpponentDefenseFactor':defpts, 'MarketFactor':factor})
        for k in STATS:
            base = row['Baseline'+k]
            adjustment = pace * (defpts if k=='Points' else defast if k=='Assists' else 1)
            kpval = max(0, base*adjustment) if base is not None else None
            mult = factor if k=='Points' else 1+.5*(factor-1) if k in ('Assists','Threes') and factor is not None else 1
            p['KenPom'+k] = kpval
            p['Vegas'+k] = base*mult if base is not None and factor is not None else None
            p['Combined'+k] = kpval*mult if kpval is not None and factor is not None else None
        output.append(p)
    return output

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--as-of',required=True,help='Projection date YYYY-MM-DD, exclusive input cutoff')
    ap.add_argument('--team',required=True)
    ap.add_argument('--opponent',required=True)
    ap.add_argument('--kenpom',required=True, type=Path)
    ap.add_argument('--total',type=float)
    ap.add_argument('--team-spread',type=float,help='Negative for favored team')
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    date.fromisoformat(args.as_of)
    if (args.total is None) != (args.team_spread is None): ap.error('Provide both --total and --team-spread')
    odds={'total':args.total,'team_spread':args.team_spread} if args.total is not None else None
    rows=apply_matchup(build_baselines(args.as_of),args.team,args.opponent,load_kenpom(args.kenpom),odds)
    payload={'as_of':args.as_of,'team':args.team,'opponent':args.opponent,'odds':odds,
             'research_only':True,'not_a_pregame_lock':True,'players':rows}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'players':len(rows),'as_of':args.as_of,'team':args.team,'opponent':args.opponent,'output':str(args.output) if args.output else None}))

if __name__=='__main__': main()
