"""Merge current-season CBBD and final ESPN box scores without double-counting.
ESPN identity is a provider ID, not a CBBD athlete ID. No fuzzy player matching.
"""
from collections import defaultdict, Counter
from datetime import date
import math
import re

ACC_DISPLAY = {
    'Boston College Eagles':'Boston College','California Golden Bears':'California',
    'Clemson Tigers':'Clemson','Duke Blue Devils':'Duke','Florida State Seminoles':'Florida State',
    'Georgia Tech Yellow Jackets':'Georgia Tech','Louisville Cardinals':'Louisville',
    'Miami Hurricanes':'Miami','NC State Wolfpack':'NC State','North Carolina Tar Heels':'North Carolina',
    'Notre Dame Fighting Irish':'Notre Dame','Pittsburgh Panthers':'Pittsburgh','SMU Mustangs':'SMU',
    'Stanford Cardinal':'Stanford','Syracuse Orange':'Syracuse','Virginia Cavaliers':'Virginia',
    'Virginia Tech Hokies':'Virginia Tech','Wake Forest Demon Deacons':'Wake Forest',
}
SCHOOLS = set(ACC_DISPLAY.values())
FIELDS = ('minutes','points','reb','assists','three_pm')
def n(s): return ''.join(c for c in str(s or '').lower() if c.isalnum())
def school(s):
    x=str(s or '').strip()
    return ACC_DISPLAY.get(x,x if x in SCHOOLS else None)
def valid(r):
    try:
        vals=[float(r[k]) for k in FIELDS]
        return all(math.isfinite(x) and x>=0 for x in vals) and vals[0]>0 and all(x.is_integer() for x in vals[1:])
    except (KeyError,ValueError,TypeError):return False
def opponent_matches(a,b):
    def key(v):
        v=re.sub(r'\bstate\b','st',str(v or '').lower())
        return n(v)
    a,b=key(a),key(b)
    if not a or not b:return False
    aliases={'uconn':'connecticut','uconnhuskies':'connecticuthuskies','ualbany':'albany','ualbanygreatdanes':'albanygreatdanes','olemiss':'mississippi','olemissrebels':'mississippirebels'}
    a,b=aliases.get(a,a),aliases.get(b,b)
    return a==b or (min(len(a),len(b))>=4 and (a.startswith(b) or b.startswith(a)))

def merge_current_games(cbbd,espn,as_of,identity_rows=()):
    """Use one completed ACC team-game per date; reject ambiguous event or player identities."""
    cbbd=[r for r in cbbd if str(r.get('season'))=='2027' and '2026-11-01'<=str(r.get('game_date',''))<as_of]
    espn=[r for r in espn if r.get('source')=='ESPN_UNOFFICIAL' and str(r.get('season'))=='2027' and '2026-11-01'<=str(r.get('game_date',''))<as_of and school(r.get('team'))]
    links=defaultdict(set);reverse=defaultdict(set)
    for r in [*identity_rows,*cbbd]:
        e,a=str(r.get('athlete_source_id') or '').strip(),str(r.get('athlete_id') or '').strip()
        if e.isdigit() and a.isdigit():links[e].add(a);reverse[a].add(e)
    def espn_id(e):
        a=links.get(e,set())
        if len(a)>1:return None
        if len(a)==1:
            aid=next(iter(a))
            if len(reverse[aid])!=1:return None
            return aid
        return 'espn:'+e
    def group(rows,provider):
        out=defaultdict(lambda:defaultdict(list))
        for r in rows:
            t=school(r.get('team'))
            gid=str(r.get('game_id') or '')
            if t and gid:out[(t,r['game_date'])][gid].append(r)
        return out
    cg,eg=group(cbbd,'CBBD'),group(espn,'ESPN')
    merged=[];issues=defaultdict(list);coverage=defaultdict(Counter)
    def warn(t,day,reason):issues[t].append(day+': '+reason)
    for t,day in sorted(set(cg)|set(eg)):
        c,e=cg.get((t,day),{}),eg.get((t,day),{})
        if len(c)>1 or len(e)>1:
            warn(t,day,'ambiguous same-day team game; omitted');continue
        cr=next(iter(c.values()),[]);er=next(iter(e.values()),[])
        if cr and er and not opponent_matches(cr[0].get('opponent'),er[0].get('opponent')):
            warn(t,day,'provider opponent mismatch; ESPN supplement excluded');er=[]
        # Check adjacent-day provider dates before including an ESPN-only game.
        if er and not cr:
            from datetime import timedelta
            nearby=[]
            for delta in (-1,1):
                d=(date.fromisoformat(day)+timedelta(days=delta)).isoformat()
                for rr in cg.get((t,d),{}).values():
                    if opponent_matches(rr[0].get('opponent'),er[0].get('opponent')):nearby.append(rr)
            if nearby:
                warn(t,day,'possible cross-date duplicate; ESPN game omitted');continue
        seen=set();primary={}
        counts=Counter(str(r.get('athlete_id') or '') for r in cr if valid(r))
        for r in cr:
            aid=str(r.get('athlete_id') or '')
            if not valid(r) or not aid or not r.get('player'):continue
            if counts[aid]!=1:
                warn(t,day,'duplicate CBBD athlete '+aid);continue
            x={**r,'team':t,'athlete_id':aid,'_source':'CBBD'}
            merged.append(x);seen.add(aid);primary[aid]=x;coverage[t]['CBBD_rows']+=1
        counts=Counter(str(r.get('athlete_id') or '') for r in er if valid(r))
        for r in er:
            eid=str(r.get('athlete_id') or '').strip()
            if not valid(r) or not eid.isdigit() or not r.get('player'):continue
            aid=espn_id(eid)
            if not aid or counts[eid]!=1:
                warn(t,day,'ambiguous ESPN athlete '+eid);continue
            if aid in seen:
                if any(float(r[k])!=float(primary[aid][k]) for k in FIELDS):
                    warn(t,day,'provider stat discrepancy for '+r['player']+'; retained CBBD')
                continue
            # If CBBD contains a same-name player without a verified crosswalk, don't duplicate.
            if any(n(x.get('player'))==n(r['player']) for x in cr if str(x.get('athlete_id'))!=aid):
                warn(t,day,'unverified cross-provider identity for '+r['player']);continue
            merged.append({**r,'team':t,'athlete_id':aid,'athlete_source_id':eid,'_source':'ESPN'})
            seen.add(aid);coverage[t]['ESPN_rows']+=1
        if cr:coverage[t]['CBBD_games']+=1
        if er:coverage[t]['ESPN_games']+=1
        if seen:coverage[t]['merged_games']+=1
    return merged,dict(issues),{k:dict(v) for k,v in coverage.items()}
