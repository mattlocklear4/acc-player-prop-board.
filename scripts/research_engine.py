"""Offline ACC research projection engine. No database writes or network calls.

Mirrors app.js buildProjectionModel and matchup.js / vegas-matchup.js formulas.
Historical cutoff is exclusive: a game on the target date is never a model input.
Current-season projections enforce a 200-minute regulation rotation per team.
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from acc_merge_game_logs import merge_current_games

ROOT = Path(__file__).resolve().parents[1]
STATS = {'Points': 'points', 'Rebounds': 'reb', 'Assists': 'assists', 'Threes': 'three_pm'}
ALIASES = {'floridastate':'floridast','miamiflorida':'miamifl','miami':'miamifl','ncstate':'ncstate','northcarolinastate':'ncstate','cal':'california','pitt':'pittsburgh'}

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

TEAM_MINUTES = 200
PLAYER_MAX_MINUTES = 40
MINUTE_PRECISION = 10
CURRENT_MODEL_VERSION = 'current-season-hybrid-v4-200min'

def allocate_team_minutes(raw):
    """Proportional capped allocation, rounded to tenths with exact integer total.

    Zero-minute players remain zero. If fewer than five positive candidates
    exist, a regulation rotation is impossible; fail closed rather than invent
    minutes or publish a partial team. No injury assumptions are introduced.
    """
    if any(v is None or not math.isfinite(v) or v < 0 for v in raw):
        raise ValueError('invalid raw rotation minutes')
    active = [i for i, v in enumerate(raw) if v > 0]
    if len(active) * PLAYER_MAX_MINUTES < TEAM_MINUTES:
        raise ValueError('insufficient positive-minute players for 200-minute rotation')
    allocation = [0.0] * len(raw)
    remaining = float(TEAM_MINUTES)
    # Reallocate any overflow only among players who are not already capped.
    while active:
        total = sum(raw[i] for i in active)
        capped = [i for i in active if remaining * raw[i] / total >= PLAYER_MAX_MINUTES]
        if not capped:
            for i in active:
                allocation[i] = remaining * raw[i] / total
            break
        for i in capped:
            allocation[i] = float(PLAYER_MAX_MINUTES)
            remaining -= PLAYER_MAX_MINUTES
        active = [i for i in active if i not in capped]
        if not active and abs(remaining) > 1e-8:
            raise ValueError('rotation capacity exhausted')
    # Largest-remainder rounding: the visible tenths must also total 200.0.
    units = [math.floor(v * MINUTE_PRECISION + 1e-9) for v in allocation]
    remainder = TEAM_MINUTES * MINUTE_PRECISION - sum(units)
    eligible = [i for i, v in enumerate(raw) if v > 0 and units[i] < PLAYER_MAX_MINUTES * MINUTE_PRECISION]
    ranked = sorted(eligible, key=lambda i: (-(allocation[i] * MINUTE_PRECISION - units[i]), i))
    if remainder < 0 or remainder > len(ranked):
        raise ValueError('rotation rounding failed')
    for i in ranked[:remainder]:
        units[i] += 1
    if sum(units) != TEAM_MINUTES * MINUTE_PRECISION or any(v < 0 or v > PLAYER_MAX_MINUTES * MINUTE_PRECISION for v in units):
        raise ValueError('invalid normalized regulation rotation')
    return [v / MINUTE_PRECISION for v in units]

def normalize_team_baselines(rows):
    """Keep original per-minute production, changing only allocated minutes."""
    raw = [numeric(p.get('Minutes')) for p in rows]
    allocated = allocate_team_minutes(raw)
    total = sum(raw)
    result = []
    for p, old, new in zip(rows, raw, allocated):
        item = dict(p)
        item.update(Minutes=new, RawMinutes=old, MinutesNormalizationFactor=new/old if old>0 else None,
                    RawTeamMinutes=total, TeamMinutesTarget=TEAM_MINUTES,
                    MinutesNormalizationStatus='normalized', ModelVersion=CURRENT_MODEL_VERSION)
        for field in STATS:
            key = 'Baseline'+field
            value = numeric(p.get(key))
            item[key] = value * new / old if value is not None and old>0 else (0.0 if value is not None and new==0 else None)
        result.append(item)
    return result

def current_game_inputs(as_of, root=ROOT):
    data = root / 'data' / 'cbbd'
    current = read_csv(data/'acc_player_games_2027.csv')
    history = (read_csv(data/'acc_player_games_2026.csv') + read_csv(data/'acc_player_games_2025.csv') + read_csv(data/'acc_transfer_player_games_2025_2026.csv'))
    espn_path = root/'data'/'espn'/'acc_player_games_2027.csv'
    espn = read_csv(espn_path) if espn_path.exists() else []
    rows,issues,coverage=merge_current_games(current,espn,as_of,history)
    return rows,issues,coverage,history

def build_baselines(as_of, root=ROOT, legacy=False):
    """Only use current season games STRICTLY before as_of (YYYY-MM-DD)."""
    current,issues,coverage,history_raw = current_game_inputs(as_of,root)
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
        n = len(games)
        w = n/(n+8)
        mw = w if legacy else 1.0
        rw = w if legacy else 1.0
        if not legacy: rm = avg(games[:3], 'minutes')
        if cm is None: minutes = hm if legacy else None
        elif not legacy: minutes = .60*cm+.40*(rm if rm is not None else cm)
        elif hm is None: minutes = cm
        else: minutes = (1-mw)*hm + mw*((.65 if legacy else .60)*cm + (.35 if legacy else .40)*rm)
        if minutes is None: continue
        minutes = clamp(minutes, 0, 40)
        obj = {'Player':r['player'], 'AthleteId':aid, 'Team':r['team'], 'Minutes':minutes,
               'CurrentGP':len(games), 'HistoryGP':len(h),
               'ModelVersion':'legacy-hybrid' if legacy else 'current-season-hybrid-v3',
               'CBBDGP':sum(x.get('_source')=='CBBD' for x in games),
               'ESPNGP':sum(x.get('_source')=='ESPN' for x in games),
               'LatestGameDate':r['game_date'],
               'CurrentTeamGames':coverage.get(r['team'],{}).get('merged_games',0),
               'DataIssues':issues.get(r['team'],[]),
               'CurrentMinutesWeight':mw, 'CurrentProductionWeight':rw,
               'Confidence':'Higher' if len(games)>=10 else 'Moderate' if len(games)>=5 else 'Limited'}
        # Publish the exact pregame inputs with the projection, not a separately fetched log.
        # Missing optional box-score fields remain null; never substitute zero.
        log_fields=('minutes','points','reb','assists','three_pm','fgm','fga','three_pa','ftm','fta','oreb','dreb','steals','blocks','turnovers','fouls')
        obj['CurrentSeasonLog']=[
            {'date':x['game_date'],'opponent':x.get('opponent'),'team':x.get('team'),
             'home':x.get('home'),'starter':x.get('starter'),'source':x.get('_source'),
             **{k:(v if v is not None and math.isfinite(v) else None) for k in log_fields for v in [numeric(x.get(k))]}}
            for x in games
        ]
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
            if cr is None: blended = hr if legacy else None
            elif not legacy: blended = .75*cr+.25*(rr if rr is not None else cr)
            elif hr is None: blended = cr
            else: blended = (1-rw)*hr + rw*((.65 if legacy else .75)*cr + (.35 if legacy else .25)*(rr if rr is not None else cr))
            obj['Baseline'+field] = max(0, minutes*blended) if blended is not None else None
        result.append(obj)
    if not legacy:
        by_team = defaultdict(list)
        for row in sorted(result, key=lambda x: (x['Team'], x['Player'])):
            by_team[canon(row['Team'])].append(row)
        result = []
        for rows in by_team.values():
            try:
                result.extend(normalize_team_baselines(rows))
            except ValueError as exc:
                # Keep explicit diagnostic metadata for apply_matchup; never
                # publish these unallocated rows as valid player projections.
                result.extend({**row, 'MinutesNormalizationStatus':'unavailable',
                               'MinutesNormalizationReason':str(exc),
                               'ModelVersion':CURRENT_MODEL_VERSION} for row in rows)
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
        if row.get('MinutesNormalizationStatus') == 'unavailable':
            raise ValueError(row.get('MinutesNormalizationReason','200-minute rotation unavailable'))
        p=dict(row)
        expected_games=(numeric(t.get('Wins')) or 0)+(numeric(t.get('Losses')) or 0)
        p['KenPomTeamGames']=int(expected_games)
        p['DataCoverageWarning']=('Merged team-game count below KenPom W+L; verify missing games' if expected_games>p.get('CurrentTeamGames',0) else None)
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
