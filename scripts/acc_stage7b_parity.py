"""Compare actual app.js browser baseline function to Python using identical pregame cutoff.

Does not test manual overrides, KenPom matchup UI, or live Vegas feeds. Read-only.
"""
import argparse
import json
import subprocess
from datetime import date
from pathlib import Path
from research_engine import build_baselines

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['Minutes', 'BaselinePoints', 'BaselineRebounds', 'BaselineAssists', 'BaselineThrees']

def run(as_of, tolerance=0.01):
    result = subprocess.run(['node', str(ROOT/'scripts'/'acc_stage7b_browser_parity.js'), as_of], cwd=ROOT, capture_output=True, text=True, check=True)
    browser = json.loads(result.stdout)['players']
    python = build_baselines(as_of)
    b = {(r['Team'],r['Player']):r for r in browser}
    p = {(r['Team'],r['Player']):r for r in python}
    differences=[]; checked=0; max_delta=0
    for key in sorted(b.keys()|p.keys()):
        if key not in b or key not in p:
            differences.append({'player':key[1], 'team':key[0], 'field':'player_presence','browser':key in b,'python':key in p})
            continue
        for field in FIELDS:
            a,z=b[key].get(field),p[key].get(field)
            checked+=1
            if a is None or z is None:
                if a != z: differences.append({'player':key[1],'team':key[0],'field':field,'browser':a,'python':z})
                continue
            delta=abs(a-z);max_delta=max(max_delta,delta)
            if delta>tolerance:
                differences.append({'player':key[1],'team':key[0],'field':field,'browser':a,'python':z,'delta':delta})
    return {'as_of':as_of,'browser_players':len(b),'python_players':len(p),'fields_checked':checked,'max_absolute_difference':max_delta,'tolerance':tolerance,'passed':not differences,'differences':differences[:100], 'difference_count':len(differences), 'scope':'Actual app.js baseline builder vs research_engine.py with identical date cutoff; does not verify browser matchup, live odds or manual overrides.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--as-of',default=date.today().isoformat());ap.add_argument('--output',default='research/acc_stage7b_parity.json');args=ap.parse_args()
    result=run(args.as_of);out=ROOT/args.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='differences'}));raise SystemExit(0 if result['passed'] else 1)
