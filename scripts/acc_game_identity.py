"""Stable ESPN identifiers for pricing, availability and settlement.

Verified one-to-one provider aliases are scoped to exact teams and tipoff;
never mutate stored historical captures or guess by a partial team name.
"""
import json,datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
def norm(s):return ''.join(c for c in str(s or '').lower() if c.isalnum())
def timestamp(s):
    try:
        x=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return x.astimezone(dt.timezone.utc) if x.tzinfo else None
    except (ValueError,TypeError):return None
def load_aliases(root=ROOT):
    p=root/'data/game_identity_aliases.json'
    if not p.exists():return []
    data=json.loads(p.read_text())
    return data if isinstance(data,list) else []
def verified_id(game,aliases,date=None):
    gid=str(game.get('game_id') or '')
    tip=timestamp(game.get('tipoff_utc'))
    if not tip:return gid
    day=tip.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if date and date!=day:return gid
    # Only trust dated numeric -> ESPN mappings with exact CBBD participants.
    pair={norm(game.get('home_team')),norm(game.get('away_team'))}
    matches=[a for a in aliases if a.get('cbbd_game_id')==gid and a.get('date')==day and timestamp(a.get('tipoff_utc'))==tip and {norm(a.get('home_team')),norm(a.get('away_team'))}==pair and str(a.get('espn_game_id','')).startswith('espn_event_')]
    return matches[0]['espn_game_id'] if len(matches)==1 else gid
def canonical_game(game,aliases):
    gid=verified_id(game,aliases)
    if gid==game.get('game_id'):return game
    return {**game,'game_id':gid,'provider_game_id':game.get('game_id'),'identity_source':'verified_dated_crosswalk'}
def canonical_record(r,aliases):
    g=r.get('game') or {};old=g.get('game_id')
    new=verified_id(g,aliases,r.get('date_eastern'))
    if not old or new==old:return r
    def fix(q):
        return {**q,'game_id':new,'original_game_id':old} if q.get('game_id')==old else q
    return {**r,'game':{**g,'game_id':new,'provider_game_id':old},'quotes':[fix(q) for q in r.get('quotes') or []],'experimental_quotes':{v:[fix(q) for q in qs] for v,qs in (r.get('experimental_quotes') or {}).items()}}
