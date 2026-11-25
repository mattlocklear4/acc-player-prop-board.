const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {projectionProfileContext,projectionValue}=require('../pregame-edges.js');
const p={Player:'No Odds Player',AthleteId:42,Minutes:31,KenPomPoints:0,BaselinePoints:14,BaselineRebounds:6,CurrentGP:1,CurrentSeasonLog:[{date:'2026-11-20',points:15}]};
const g={game_id:'espn_event_1',away_team:'Duke',home_team:'Other',tipoff_utc:'2026-11-25T23:00:00Z'};
const t={team:'Duke',players:[p]};
const ctx=projectionProfileContext(g,t,p);
assert.equal(ctx.player,'No Odds Player');
assert.equal(ctx.athleteId,'42');
assert.equal(ctx.gameId,g.game_id);
assert.equal(ctx.projectionOnly,true);
assert.deepEqual(ctx.books,{});
assert.equal(ctx.market,null);
assert.equal(projectionValue(p,'points'),0);
assert.equal(projectionValue(p,'reb'),6);
assert.equal(projectionValue(p,'minutes'),31);
assert.equal(projectionValue(p,'assists'),null);
assert.equal(projectionProfileContext(g,t,null),null);
const board=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/daily_board.json'),'utf8'));
for(const game of board.games||[])for(const team of game.teams||[])for(const player of team.players||[]){
 const c=projectionProfileContext(game,team,player);
 assert.equal(c.gameId,game.game_id);
 assert.equal(c.team,team.team);
 assert.equal(c.player,player.Player);
 for(const [field,keys] of Object.entries({minutes:['Minutes','minutes','MIN'],points:['KenPomPoints','BaselinePoints','points','PTS'],reb:['KenPomRebounds','BaselineRebounds','rebounds','REB'],assists:['KenPomAssists','BaselineAssists','assists','AST'],three_pm:['KenPomThrees','BaselineThrees','threes','3PM']})){
  const key=keys.find(k=>player[k]!=null&&player[k]!=='');
  assert.equal(projectionValue(player,field),key===undefined?null:Number(player[key]));
 }
}
const daily=fs.readFileSync(path.join(__dirname,'../daily-tab.js'),'utf8');
assert.ok(daily.includes('data-daily-profile'));
assert.ok(daily.includes('openProjection(row.game,row.team,row.player,button)'));
console.log('Daily player profile context, exact published projections, and no-odds cases passed');
