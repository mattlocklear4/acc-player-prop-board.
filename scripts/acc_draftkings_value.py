#!/usr/bin/env python3
"""Read-only DraftKings line comparison. Uses a manually supplied CSV; ZERO API calls.

CSV columns: player,stat,line,over_odds,under_odds; optional game_id,book.
No odds are invented. Small samples use conservative, explicitly flagged
stat-level variance priors; threes use Poisson (not calibrated).
"""
import argparse,csv,json,math,statistics,re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from research_engine import read_csv, numeric

STATS={'points':'Points','pts':'Points','rebounds':'Rebounds','reb':'Rebounds',
       'assists':'Assists','ast':'Assists','threes':'Threes','3pm':'Threes','3pt':'Threes'}
MODELS=('Baseline','KenPom','Vegas','Combined')

def norm(x):return re.sub(r'[^a-z0-9]','',str(x or '').lower())
def profit(odds):
    o=float(odds)
    if o==0 or -100<o<100:raise ValueError('Invalid American odds')
    return o/100 if o>0 else 100/(-o)
def poisson_cdf(k,mu):
    if k<0:return 0.0
    if mu==0:return 1.0
    p=math.exp(-mu);total=p
    for n in range(1,k+1):
        p*=mu/n;total+=p
    return min(1.0,total)
def over_probability(mu,stat,line,sigma):
    # Standard half-point markets: over 17.5 means at least 18.
    threshold=math.floor(line)+1
    if stat=='Threes':return max(0.0,min(1.0,1-poisson_cdf(threshold-1,mu)))
    if sigma is None or sigma<=0:return None
    z=(threshold-.5-mu)/(sigma*math.sqrt(2))
    return max(0.0,min(1.0,.5*math.erfc(z)))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--projections',default='research/acc_projection_dry_run.json')
    p.add_argument('--lines',default='data/draftkings_player_props.csv')
    p.add_argument('--output',default='research/acc_draftkings_value_preview.json')
    p.add_argument('--date-eastern',default='',help='Only compare games on YYYY-MM-DD Eastern date')
    a=p.parse_args()
    payload=json.loads(Path(a.projections).read_text())
    players=defaultdict(list)
    for game in payload.get('games',[]):
        for team in game.get('teams',[]):
            if team.get('status')!='research_candidate_unverified':continue
            for player in team.get('players',[]):
                players[norm(player.get('Player'))].append((game,team,player))
    history=defaultdict(list)
    for r in read_csv(Path('data/cbbd/acc_player_games_2027.csv')):
        if r.get('athlete_id'):history[str(r['athlete_id'])].append(r)
    availability={}
    flagfile=Path('data/acc_friday_availability_review.csv')
    if flagfile.exists():
        for flag in read_csv(flagfile):
            availability[(norm(flag.get('team')),norm(flag.get('player')))]=flag
    # Empirical-Bayes shrinkage toward conservative stat-level standard deviations.
    # These are modeling assumptions, NOT measured or validated 2026-27 accuracy.
    prior_sigma={'Points':7.0,'Rebounds':3.5,'Assists':2.5}
    prior_weight=8
    rows=[];warnings=[];unmatched=0
    with open(a.lines,newline='',encoding='utf-8-sig') as file:
        for line in csv.DictReader(file):
            try:
                stat=STATS.get(str(line.get('stat','')).lower().strip())
                if not stat:raise ValueError('unsupported_stat')
                name=str(line.get('player') or '').strip()
                candidates=players.get(norm(name),[])
                gid=str(line.get('game_id') or '').strip()
                if gid:candidates=[x for x in candidates if str(x[0]['game_id'])==gid]
                if len(candidates)!=1:raise ValueError('player_or_game_missing_or_ambiguous')
                game,team,player=candidates[0]
                flag=availability.get((norm(team['team']),norm(player.get('Player'))))
                if flag and str(flag.get('status') or '').strip().casefold() in ('out','reported_out','review_out','questionable','doubtful'):
                    raise ValueError('availability_review_required:'+str(flag['status']).strip().casefold())
                tip=datetime.fromisoformat(game['tipoff_utc'].replace('Z','+00:00'))
                if a.date_eastern and tip.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=a.date_eastern:
                    raise ValueError('game_outside_selected_date')
                if datetime.now(tip.tzinfo)>=tip:raise ValueError('game_already_started')
                raw_line=float(line['line'])
                if raw_line<0 or abs(raw_line*2-round(raw_line*2))>1e-7:raise ValueError('line_must_be_half_point_or_integer')
                # Push markets are intentionally excluded until explicitly supported.
                if raw_line.is_integer():raise ValueError('integer_lines_not_supported_push_risk')
                over=float(line['over_odds']);under=float(line['under_odds'])
                po,pu=profit(over),profit(under)
                # A line with a missing side is not a two-way comparable market.
                # Reject invalid odds instead of fabricating a fair price.
                prior=[numeric(r.get({'Points':'points','Rebounds':'reb','Assists':'assists','Threes':'three_pm'}[stat]))
                       for r in history.get(str(player.get('AthleteId')),[])
                       if r.get('game_date','')<tip.date().isoformat()]
                prior=[v for v in prior if v is not None]
                sample_sigma=statistics.stdev(prior) if len(prior)>=2 and stat!='Threes' else None
                sigma=None
                sigma_method='poisson_assumption' if stat=='Threes' else 'empirical_bayes_prior'
                if stat!='Threes':
                    fallback=prior_sigma[stat]
                    n=max(0,len(prior)-1)
                    sigma=math.sqrt((n*(sample_sigma**2 if sample_sigma is not None else fallback**2)+prior_weight*fallback**2)/(n+prior_weight))
                    sigma_method='sample_shrunk_to_prior' if sample_sigma is not None else 'prior_only'
                model_values={}
                for model in MODELS:
                    mu=numeric(player.get(model+stat))
                    if mu is None:continue
                    probability=over_probability(mu,stat,raw_line,sigma)
                    model_values[model]={'projection':round(mu,3),'over_probability':round(probability,4) if probability is not None else None,
                       'under_probability':round(1-probability,4) if probability is not None else None,
                       'over_roi':round(probability*po-(1-probability),4) if probability is not None else None,
                       'under_roi':round((1-probability)*pu-probability,4) if probability is not None else None}
                rows.append({'game_id':game['game_id'],'tipoff_utc':game['tipoff_utc'],'player':name,'team':team['team'],
                    'stat':stat,'book':line.get('book') or 'DraftKings (manual)','line':raw_line,'over_odds':over,'under_odds':under,
                    'historical_games_for_sigma':len(prior),'historical_sigma':round(sample_sigma,3) if sample_sigma else None,
                    'pricing_sigma':round(sigma,3) if sigma else None,'sigma_method':sigma_method,
                    'models':model_values,'warning':'Exploratory variance-prior pricing, not calibrated; confirm lineup/minutes'})
            except (ValueError,KeyError,TypeError) as exc:
                unmatched+=1;warnings.append({'player':line.get('player'),'stat':line.get('stat'),'reason':str(exc)})
    result={'mode':'READ_ONLY_MANUAL_ODDS_NO_API_CALLS','schedule_status':payload.get('schedule_status'),
            'matched_lines':len(rows),'unmatched_lines':unmatched,'rows':rows,'warnings':warnings,
            'caution':'Exploratory probabilities: PTS/REB/AST use conservative assumed variance priors shrunk toward player samples; threes use Poisson. Not backtested or calibrated; no verified betting edge.'}
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'matched_lines':len(rows),'unmatched_lines':unmatched,'paid_api_calls':0}))
if __name__=='__main__':main()
