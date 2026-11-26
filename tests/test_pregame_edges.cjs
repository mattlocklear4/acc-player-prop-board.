const assert=require('node:assert/strict');
const {evaluate,probabilities}=require('../pregame-edges.js');
const p=probabilities('player_points',14.5,14.5);
assert.ok(Math.abs(p.over-.5)<.001);
const threes=probabilities('player_threes',1,1.5);
assert.ok(Math.abs(threes.over-(1-2/Math.E))<.00001);
const board={date_eastern:'2026-11-23',generated_at_utc:'2026-11-23T18:58:09Z',games:[{game_id:'espn_event_1',tipoff_utc:'2026-11-23T19:30:00Z',home_team:'Clemson',away_team:'Ole Miss',teams:[{team:'Clemson',players:[{Player:'Ace Buckner',KenPomPoints:17}]}]}]};
const snapshot={snapshot_date_eastern:'2026-11-23',generated_at_utc:'2026-11-23T16:55:29Z',events:[{schedule_game_id:'espn_event_1',home_team:'Clemson',away_team:'Ole Miss',props:[
  {bookmaker:'fanduel',market:'player_points',player:'Ace Buckner',side:'Over',line:14.5,odds:-110,last_update:'2026-11-23T16:55:22Z'},
  {bookmaker:'fanduel',market:'player_points',player:'Ace Buckner',side:'Under',line:14.5,odds:-110,last_update:'2026-11-23T16:55:22Z'},
  {bookmaker:'fanduel',market:'player_points',player:'Unknown',side:'Over',line:14.5,odds:-110,last_update:'2026-11-23T16:55:22Z'}]}]};
const result=evaluate(board,snapshot);
assert.equal(result.rows.length,1);
assert.equal(result.rows[0].player,'Ace Buckner');
assert.equal(result.rows[0].bestSide,'over');
assert.ok(result.rows[0].roiOver>0);
assert.equal(result.diagnostics.length,1);
assert.equal(result.diagnostics[0].reason,'No archived player projection');
snapshot.events[0].props[0].last_update='2026-11-23T20:00:00Z';
assert.equal(evaluate(board,snapshot).rows.length,0);
snapshot.events[0].props[0].last_update='2026-11-23T16:55:22Z';
snapshot.generated_at_utc='2026-11-23T20:00:00Z';
assert.equal(evaluate(board,snapshot).rows.length,0);
snapshot.generated_at_utc='2026-11-23T16:55:29Z';
board.generated_at_utc='2026-11-23T20:00:00Z';
assert.equal(evaluate(board,snapshot).rows.length,0);
console.log('Pregame edge matching and distribution tests passed');

// V10 uses the identical mean and a proper nonnegative count distribution.
const {negativeBinomialCdf,experimentalBoard}=require('../pregame-edges.js');
assert.ok(Math.abs(negativeBinomialCdf(2,1,1)-.875)<1e-10); // geometric mean 1
assert.equal(negativeBinomialCdf(0,0,1),1);
let last=0;
for(let k=0;k<60;k++){
 const u=negativeBinomialCdf(k,14,.1);
 assert.ok(u>=last&&u<=1);last=u;
}
assert.ok(last>.999);
const v10={family:'negative_binomial',mean:17,dispersion:.1};
const custom=probabilities('player_points',17,14.5,v10);
assert.ok(custom&&Math.abs(custom.over+custom.under-1)<1e-12);
assert.notEqual(custom.over,probabilities('player_points',17,14.5).over);
assert.equal(probabilities('player_points',17,14.5,{...v10,mean:18}),null);
assert.equal(probabilities('player_points',17,14.5,null),null);
board.generated_at_utc='2026-11-23T18:58:09Z';
board.games[0].teams[0].players[0].ExperimentalModels={'v10-player-distributions':{ModelVersion:'v10-player-distributions',ProbabilityModel:'player-count-dispersion-v1',KenPomPoints:17,Distributions:{Points:v10}}};
const v10Rows=evaluate(experimentalBoard(board,'v10-player-distributions'),snapshot).rows;
assert.equal(v10Rows.length,1);
assert.equal(v10Rows[0].projection,17);
assert.equal(v10Rows[0].probOver,custom.over);
assert.equal(v10Rows[0].pricingModel,'player-count-dispersion-v1');
assert.equal(evaluate(board,snapshot).rows[0].probOver,probabilities('player_points',17,14.5).over);
console.log('V10 count distribution and control pricing tests passed');
