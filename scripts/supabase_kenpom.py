"""Read-only KenPom snapshot fetch for ACC diagnostic GitHub Actions.

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY as GitHub Actions secrets.
Never logs credentials or persists the raw team ratings in artifacts.
"""
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from research_engine import canon

EXPECTED_COLUMNS = ('Team','Conference','Wins','Losses','AdjEM','AdjO','AdjD','AdjT','SOS_AdjEM','SOS_AdjO','SOS_AdjD')
FIELD_MAP = {'team':'Team','conference':'Conference','wins':'Wins','losses':'Losses',
             'adj_em':'AdjEM','adj_o':'AdjO','adj_d':'AdjD','adj_t':'AdjT',
             'sos_adj_em':'SOS_AdjEM','sos_adj_o':'SOS_AdjO','sos_adj_d':'SOS_AdjD'}
# Explicit school-name aliases; never use fuzzy matching that could confuse schools.
OPPONENT_ALIASES = {
    'southcarolinastate':'southcarolinast',
    'southcarolinast':'southcarolinast',
    'floridastate':'floridast',
    'northcarolinastate':'ncstate',
    'miamiflorida':'miamifl',
    'saintmarys':'saintmarys',
}

def resolve_opponent(name, kp):
    key = canon(name)
    key = OPPONENT_ALIASES.get(key,key)
    matches=[r['Team'] for k,r in kp.items() if OPPONENT_ALIASES.get(k,k)==key]
    return matches[0] if len(matches)==1 else None

def _iso(ts):
    if not ts: return None
    dt=datetime.fromisoformat(ts.replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('Snapshot timestamp missing timezone')
    return dt.astimezone(timezone.utc)

def fetch_latest_kenpom(now,season=2027,fetch=None):
    """Return (canonical team map, metadata); refuse incomplete or future snapshots."""
    url=os.getenv('SUPABASE_URL','').rstrip('/')
    key=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
    if fetch is None:
        if not (url.startswith('https://') and key):
            raise RuntimeError('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY GitHub Actions secret')
        def fetch(table,params):
            uri=url+'/rest/v1/'+table+'?'+urlencode(params)
            req=Request(uri,headers={'apikey':key,'Authorization':'Bearer '+key,'Accept':'application/json'})
            with urlopen(req,timeout=30) as resp:
                return json.load(resp)
    snapshots=fetch('acc_kenpom_snapshots',{'select':'id,season,imported_at,source_as_of,team_count',
                                           'season':f'eq.{season}', 'imported_at':f'lte.{now.astimezone(timezone.utc).isoformat()}',
                                           'order':'imported_at.desc','limit':'10'})
    if not snapshots: raise ValueError('No KenPom snapshot imported before projection run')
    # Select latest *complete* snapshot, not silently fall back to a stale one.
    snap=snapshots[0]
    imported=_iso(snap['imported_at'])
    if imported is None or imported>now:raise ValueError('Snapshot timestamp is invalid/future')
    if snap.get('source_as_of') and _iso(snap['source_as_of'])>now:
        raise ValueError('Snapshot source date is later than projection run')
    expected=int(snap['team_count'])
    if expected<300 or expected>400:raise ValueError('Unexpected KenPom team count: '+str(expected))
    rows=[]
    for offset in range(0,expected,500):
        page=fetch('acc_kenpom_team_ratings',{'select':','.join(FIELD_MAP),
                    'snapshot_id':f"eq.{snap['id']}",'order':'id.asc','limit':'500','offset':str(offset)})
        rows.extend(page)
    if len(rows)!=expected:raise ValueError(f'Incomplete KenPom snapshot: expected {expected}, got {len(rows)}')
    kp={}
    for row in rows:
        r={out:row.get(field) for field,out in FIELD_MAP.items()}
        if any(r[c] is None for c in EXPECTED_COLUMNS):raise ValueError('KenPom snapshot contains missing fields')
        c=canon(r['Team'])
        if c in kp:raise ValueError('Duplicate KenPom team: '+str(r['Team']))
        kp[c]=r
    meta={'source':'supabase_snapshot','snapshot_id':snap['id'],
          'imported_at':snap['imported_at'],'source_as_of':snap.get('source_as_of'),
          'team_count':len(kp)}
    return kp,meta
