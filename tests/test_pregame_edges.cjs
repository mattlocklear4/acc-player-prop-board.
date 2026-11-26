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

// V11 uses its combined mean, its own dispersion and never prices an out player.
const p11=board.games[0].teams[0].players[0];
const v11dist={family:'negative_binomial',mean:13.2,dispersion:.08};
p11.ExperimentalModels['v11-combined']={ModelVersion:'v11-combined',Minutes:29,ProbabilityModel:'player-count-dispersion-v1',KenPomPoints:13.2,Distributions:{Points:v11dist},CombinedModelInputs:{pricing_status:'available'}};
let v11rows=evaluate(experimentalBoard(board,'v11-combined'),snapshot).rows;
assert.equal(v11rows.length,1);assert.equal(v11rows[0].projection,13.2);
assert.equal(v11rows[0].probOver,probabilities('player_points',13.2,14.5,v11dist).over);
assert.equal(v11rows[0].pricingModel,'player-count-dispersion-v1');
p11.ExperimentalModels['v11-combined'].Minutes=0;
assert.equal(evaluate(experimentalBoard(board,'v11-combined'),snapshot).rows.length,0);
assert.equal(evaluate(board,snapshot).rows[0].projection,17);
console.log('V11 combined mean and pricing safeguards passed');


// Live freshness checks are UI-only; archival pricing remains unchanged.
const {quoteFresh,quotePregame,quoteEligible,groupRows}=require('../pregame-edges.js');
const row={...result.rows[0],snapshotUtc:'2026-11-23T18:50:00Z',quoteUpdatedOver:'2026-11-23T18:49:00Z',quoteUpdatedUnder:'2026-11-23T16:50:00Z',tipoffUtc:'2026-11-23T19:30:00Z'};
const now=Date.parse('2026-11-23T19:00:00Z');
assert.equal(quoteFresh(row,'over',now),true);
assert.equal(quoteFresh(row,'under',now),false);
assert.equal(quoteFresh({...row,snapshotUtc:'2026-11-23T19:01:00Z'},'over',now),false);
assert.equal(quoteFresh(row,'over',Date.parse(row.tipoffUtc)),false);
assert.equal(groupRows([row],()=>false)[0].best,null);
assert.equal(groupRows([row],(r,side)=>quoteFresh(r,side,now))[0].best.side,'over');
assert.ok(groupRows([row])[0].best); // historical pricing still available
assert.equal(quotePregame(row,'under',now),true);
assert.equal(quoteEligible(row,'under',now),true); // older saved quote is ranked by default
assert.equal(quoteEligible(row,'under',now,true),false);
assert.equal(quoteEligible(row,'over',now,true),true);
assert.equal(quoteEligible(row,'over',Date.parse(row.tipoffUtc)),false);
assert.equal(groupRows([row],(r,side)=>quoteEligible(r,side,Date.parse(row.tipoffUtc)))[0].best,null);
assert.ok(groupRows([row],(r,side)=>quoteEligible(r,side,now))[0].best);
console.log('Stale quote and active-edge ranking safeguards passed');
