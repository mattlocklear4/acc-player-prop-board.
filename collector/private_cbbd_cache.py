#!/usr/bin/env python3
"""Keep new CBBD bulk datasets in a service-role-only Supabase cache.

Only counts, timestamps and status are published. Never log response bodies,
upload raw artifacts or commit the downloaded datasets.
"""
import argparse, datetime as dt, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
CACHE='acc_cbbd_private_cache'
FILES={'players_2027':('acc_player_games_2027.csv','acc_collection_summary_2027.json'),
       'teams_2027':('acc_team_stats_2027.csv','acc_team_stats_2027.json','d1_team_stats_2027.json','acc_team_collection_summary_2027.json')}
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def request(url,key,method='GET',payload=None,headers=None):
    h={'apikey':key,'Authorization':'Bearer '+key,'Accept':'application/json'}
    if headers:h.update(headers)
    data=json.dumps(payload).encode() if payload is not None else None
    if data is not None:h['Content-Type']='application/json'
    try:
        with urlopen(Request(url,data=data,headers=h,method=method),timeout=90) as r:
            raw=r.read()
            return json.loads(raw) if raw else None
    except HTTPError as e:raise RuntimeError(f'HTTP {e.code} from service') from None
    except URLError:raise RuntimeError('Service connection failed') from None

def db():
    url=os.environ['SUPABASE_URL'].rstrip('/')
    key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
    if not url.startswith('https://') or not key:raise ValueError('Missing cloud configuration')
    return url+'/rest/v1/'+CACHE,key

def read_cache(dataset,dest,required=False):
    url,key=db()
    data=request(url+'?select=refreshed_at,files&dataset=eq.'+dataset,key)
    if not data:
        if required:raise RuntimeError('No private CBBD cache for '+dataset)
        print('No private CBBD cache yet for '+dataset)
        return False
    if len(data)!=1:raise ValueError('Unexpected cache contents')
    allowed=set(FILES[dataset]); actual=set(data[0]['files'])
    if actual!=allowed and not (dataset=='teams_2027' and actual==allowed-{'d1_team_stats_2027.json'}):raise ValueError('Unexpected cache contents')
    dest.mkdir(parents=True,exist_ok=True)
    for name,content in data[0]['files'].items():
        if not isinstance(content,str) or not content:raise ValueError('Invalid cached file')
        (dest/name).write_text(content,encoding='utf-8')
    print('Restored '+dataset+' from '+data[0]['refreshed_at'])
    return True

def store_cache(dataset,folder):
    url,key=db()
    files={n:(folder/n).read_text(encoding='utf-8') for n in FILES[dataset]}
    if any(not v for v in files.values()):raise ValueError('Empty dataset')
    payload={'dataset':dataset,'refreshed_at':now(),'files':files}
    request(url+'?on_conflict=dataset',key,'POST',payload,{'Prefer':'resolution=merge-duplicates,return=minimal'})
    # Verify private storage and exact bytes before declaring success.
    with tempfile.TemporaryDirectory() as tmp:
        dest=Path(tmp);read_cache(dataset,dest,required=True)
        if any((dest/n).read_text(encoding='utf-8')!=files[n] for n in files):raise ValueError('Cache verification failed')

def info():
    k=os.environ['CBBD_API_KEY']
    # CBBD uses bearer auth; do not send the Supabase key or raw response to logs.
    try:
        with urlopen(Request('https://api.collegebasketballdata.com/info',headers={'Authorization':'Bearer '+k,'Accept':'application/json'}),timeout=30) as r:
            v=json.load(r)
    except HTTPError as e:raise RuntimeError('CBBD info HTTP '+str(e.code)) from None
    if not isinstance(v,dict) or 'tierName' not in v or 'remainingCalls' not in v:raise ValueError('Invalid CBBD info response')
    return {k:v.get(k) for k in ('patronLevel','tierName','monthlyLimit','remainingCalls','usedCalls','resetAt','sharedPool')}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['refresh','restore'])
    p.add_argument('--dest',default='data/cbbd')
    p.add_argument('--scope',choices=['both','players','teams'],default='both')
    p.add_argument('--reuse-today-players-if-push',action='store_true')
    a=p.parse_args();dest=Path(a.dest)
    datasets=[d for d in FILES if a.scope=='both' or d.startswith(a.scope+'_')]
    if a.mode=='restore':
        for d in datasets:read_cache(d,dest)
        return
    status={'checked_at_utc':now(),'status':'FAILED','data_updated':False,'datasets':{}}
    report=dest/'acc_private_refresh_status.json'
    try:
        status['quota_before']=info()
        print('CBBD entitlement: '+json.dumps(status['quota_before']))
        reuse=False
        if a.reuse_today_players_if_push and os.environ.get('EVENT_NAME')=='push' and 'players_2027' in datasets:
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                if read_cache('players_2027',folder):
                    saved=json.loads((folder/FILES['players_2027'][-1]).read_text())
                    ts=dt.datetime.fromisoformat(saved['last_successful_run_utc'])
                    if ts.date()==dt.datetime.now(dt.timezone.utc).date() and len(saved.get('team_counts',{}))==18:
                        status['datasets']['players_2027']={k:saved[k] for k in ('last_successful_run_utc','api_requests','total_player_games','team_counts') if k in saved}
                        status['datasets']['players_2027']['reused_verified_today']=True
                        reuse=True
                        datasets.remove('players_2027')
                        print('Reusing verified current-day private player data; no duplicate calls')
        required=sum(18 if d=='players_2027' else 1 for d in datasets)
        balance=status['quota_before'].get('remainingCalls')
        if balance is not None and balance<required:raise RuntimeError('Insufficient CBBD quota for full refresh')
        for dataset in datasets:
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                if not read_cache(dataset,folder) and dataset=='players_2027':
                    seed=ROOT/'data/cbbd'/FILES[dataset][0]
                    if seed.exists():shutil.copy2(seed,folder/seed.name)
                script='collect_cbbd.py' if dataset=='players_2027' else 'collect_team_stats.py'
                # Suppress provider error bodies; success reports below are aggregate only.
                proc=subprocess.run([sys.executable,str(ROOT/'collector'/script),'--season','2027','--output-dir',str(folder)],capture_output=True,text=True)
                if proc.returncode or (folder/'acc_collector_status.json').exists():raise RuntimeError('CBBD '+dataset+' collection incomplete; private cache retained')
                summary=json.loads((folder/FILES[dataset][-1]).read_text())
                if dataset=='players_2027' and (len(summary.get('team_counts',{}))!=18 or not all(v.get('games',0)>0 for v in summary['team_counts'].values())):raise ValueError('Player collection does not cover all 18 teams')
                store_cache(dataset,folder)
                safe={k:summary[k] for k in ('last_successful_run_utc','api_requests','team_count','national_team_count','total_player_games','team_counts') if k in summary}
                status['datasets'][dataset]=safe
                print(dataset+': '+json.dumps(safe))
        status['quota_after']=info()
        status.update(status='OK',data_updated=True)
        print('CBBD remaining balance: '+str(status['quota_after']['remainingCalls']))
    except Exception as e:
        status['message']=str(e)
        print('Private refresh failed: '+str(e),file=sys.stderr)
        raise SystemExit(1)
    finally:
        status['checked_at_utc']=now()
        dest.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(status,indent=2)+'\n')

if __name__=='__main__':main()
