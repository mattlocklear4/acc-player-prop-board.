const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {capture}=require('../scripts/acc_capture_pregame.cjs');
const {evaluate}=require('../pregame-edges.js');
const output=fs.mkdtempSync(path.join(os.tmpdir(),'acc-archive-'));
const board={date_eastern:'2026-11-25',generated_at_utc:'2026-11-25T15:00:00Z',games:[{game_id:'espn_event_1',tipoff_utc:'2026-11-25T20:00:00Z',home_team:'Duke',away_team:'Other',teams:[{team:'Duke',players:[{Player:'Test Player',KenPomPoints:17,ModelVersion:'v2'}]}]}]};
const odds={snapshot_date_eastern:board.date_eastern,generated_at_utc:'2026-11-25T16:00:00Z',events:[{schedule_game_id:'espn_event_1',props:['Over','Under'].map(side=>({bookmaker:'fanduel',market:'player_points',player:'Test Player',side,line:14.5,odds:-110,last_update:'2026-11-25T15:59:00Z'}))}]};
try{
 const now='2026-11-25T17:00:00Z';
 assert.equal(capture(board,odds,now,output).written,1);
 const dir=path.join(output,board.date_eastern),file=path.join(dir,fs.readdirSync(dir)[0]),original=fs.readFileSync(file,'utf8'),rec=JSON.parse(original);
 assert.equal(rec.quotes.length,2);
 assert.equal(rec.quotes[0].expected_roi_percent,evaluate(board,odds).rows[0].roiOver);
 assert.equal(rec.quotes[0].model_version,'v2');
 assert.equal(capture(board,odds,'2026-11-25T18:00:00Z',output).written,0);
 assert.equal(fs.readFileSync(file,'utf8'),original);
 assert.equal(capture(board,odds,'2026-11-25T20:00:00Z',output).written,0);
 board.generated_at_utc='2026-11-25T18:00:00Z';
 assert.equal(capture(board,odds,'2026-11-25T19:00:00Z',output).written,1);
 assert.equal(fs.readdirSync(dir).length,2);
 console.log('Immutable archive and browser pricing parity tests passed');
}finally{fs.rmSync(output,{recursive:true,force:true});}
