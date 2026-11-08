#!/usr/bin/env python3
"""Small historical Torvik archive availability and pregame date validation test."""
import csv, io, json, urllib.request, urllib.error
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

YEAR=2026
URL=f'https://raw.githubusercontent.com/andreweatherman/toRvik-data/main/ratings/archive/by_year/full_{YEAR}.csv'
OUT=Path('torvik_archive_test_results');OUT.mkdir(exist_ok=True)
ACC={'Boston College','California','Clemson','Duke','Florida State','Georgia Tech','Louisville','Miami','NC State','North Carolina','Notre Dame','Pittsburgh','SMU','Stanford','Syracuse','Virginia','Virginia Tech','Wake Forest'}
ALIASES={'Cal':'California','Miami FL':'Miami','Miami (FL)':'Miami','N.C. State':'NC State','North Carolina St.':'NC State','Pitt':'Pittsburgh','Southern Methodist':'SMU'}
report={'archive_url':URL,'season':YEAR,'download_success':False,'valid':False,'warnings':[]}
try:
    req=urllib.request.Request(URL,headers={'User-Agent':'ACC-Prop-Board-Historical-Research/1.0'})
    with urllib.request.urlopen(req,timeout=100) as resp:
        payload=resp.read(120_000_001)
    if len(payload)>120_000_000:raise ValueError('Archive exceeds 120MB test limit')
    report['download_success']=True;report['download_bytes']=len(payload)
    text=payload.decode('utf-8-sig');reader=csv.DictReader(io.StringIO(text));headers=reader.fieldnames or []
    report['columns']=headers
    rows=list(reader);report['rows']=len(rows)
    required={'date','team','adj_o','adj_d'}
    missing=sorted(required-set(headers))
    if missing:raise ValueError('Archive missing required columns: '+', '.join(missing))
    tempo_col=next((x for x in ('adj_tempo','adj_t','adj_tempo') if x in headers),None)
    if not tempo_col:report['warnings'].append('Adjusted tempo column not found; inspect columns')
    def parse_date(v):
        v=str(v or '').strip()
        for fmt in ('%Y-%m-%d','%Y%m%d','%m/%d/%Y','%Y-%m-%d %H:%M:%S'):
            try:return datetime.strptime(v,fmt).date()
            except ValueError:pass
        return None
    parsed=[];bad_dates=0
    for r in rows:
        d=parse_date(r.get('date'))
        if not d:bad_dates+=1;continue
        team=ALIASES.get(r.get('team','').strip(),r.get('team','').strip())
        if team in ACC:parsed.append((d,team,r))
    report['unparsed_date_rows']=bad_dates
    report['acc_archive_rows']=len(parsed)
    report['acc_teams_found']=sorted(set(t for d,t,r in parsed))
    report['acc_teams_missing']=sorted(ACC-set(report['acc_teams_found']))
    report['snapshot_dates']=len(set(d for d,t,r in parsed))
    report['earliest_snapshot']=min((d.isoformat() for d,t,r in parsed),default=None)
    report['latest_snapshot']=max((d.isoformat() for d,t,r in parsed),default=None)
    # Demonstrate strict pregame lookup for sample target dates. No actual CBBD game dates required yet.
    samples=[]
    for target in ('2025-11-15','2026-01-15','2026-03-01'):
        target_date=datetime.strptime(target,'%Y-%m-%d').date()
        for team in ('Duke','North Carolina','Virginia','Clemson','California'):
            eligible=[(d,r) for d,t,r in parsed if t==team and d<target_date]
            if eligible:
                d,r=max(eligible,key=lambda x:x[0]);samples.append({'team':team,'target_game_date':target,'rating_snapshot_date':d.isoformat(),'days_prior':(target_date-d).days,'adj_o':r.get('adj_o'),'adj_d':r.get('adj_d'),'adj_tempo':r.get(tempo_col) if tempo_col else None,'status':'matched'})
            else:samples.append({'team':team,'target_game_date':target,'rating_snapshot_date':'','days_prior':'','adj_o':'','adj_d':'','adj_tempo':'','status':'no earlier snapshot'})
    with (OUT/'sample_pregame_matches.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(samples[0]));w.writeheader();w.writerows(samples)
    report['sample_pregame_matches']=sum(s['status']=='matched' for s in samples)
    report['sample_pregame_attempts']=len(samples)
    report['valid']=len(parsed)>0 and report['snapshot_dates']>1 and not missing
    if report['acc_teams_missing']:report['warnings'].append('Some ACC team names were not matched; inspect aliases before joining player data')
    if bad_dates:report['warnings'].append('Some dates could not be parsed')
except Exception as exc:
    report['error']=str(exc)
finally:
    (OUT/'archive_validation_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if not report['valid']:raise SystemExit('Archive test incomplete or failed. See uploaded validation report.')
