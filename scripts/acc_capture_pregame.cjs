'use strict';
// Immutable game-level pregame snapshots; use exactly the browser's pricing implementation.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {evaluate}=require('../pregame-edges.js');
const root=path.resolve(__dirname,'..');
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
const stamp=s=>Date.parse(s||'');
const safe=s=>String(s).replace(/[^a-zA-Z0-9_-]/g,'_');
const pricingVersion='board-normal55-poisson-v1';
function capture(board,odds,now,output,pricingHash='test'){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(board.date_eastern||''))throw Error('Invalid board date');
  const projected=stamp(board.generated_at_utc),captured=stamp(now);
  if(!Number.isFinite(projected)||!Number.isFinite(captured)||projected>captured)throw Error('Invalid projection/capture timestamp');
  const collected=stamp(odds?.generated_at_utc);
  const usable=odds?.snapshot_date_eastern===board.date_eastern&&Number.isFinite(collected)&&collected<=captured;
  let written=0,skipped=0,priced=0,positive=0;
  for(const game of board.games||[]){
    const tip=stamp(game.tipoff_utc);
    if(!Number.isFinite(tip)||captured>=tip||projected>=tip||!game.game_id||!(game.teams||[]).some(t=>(t.players||[]).length)){skipped++;continue;}
    const withOdds=usable&&collected<tip;
    const result=withOdds?evaluate({...board,games:[game]},{...odds,events:(odds.events||[]).filter(e=>e.schedule_game_id===game.game_id)}):{rows:[],diagnostics:[]};
    const flatten=result=>result.rows.flatMap(r=>['over','under'].filter(side=>r[side]!=null).map(side=>{
      const suffix=side==='over'?'Over':'Under';
      return {game_id:r.gameId,team:r.team,player:r.player,athlete_id:r.athleteId,market:r.market,bookmaker:r.book,side,line:r.line,american_odds:r[side],projection:r.projection,model_version:r.modelVersion,win_probability:r['prob'+suffix],fair_odds:r['fair'+suffix],expected_roi_percent:r['roi'+suffix],projection_utc:r.projectionUtc,odds_snapshot_utc:r.snapshotUtc,quote_updated_utc:r['quoteUpdated'+suffix],tipoff_utc:r.tipoffUtc};
    }));
    const rows=flatten(result);
    const experimental_quotes={};
    if(withOdds){
      const versions=[...new Set((game.teams||[]).flatMap(t=>(t.players||[]).flatMap(p=>Object.keys(p.ExperimentalModels||{}))))];
      for(const v of versions){
        const shadow={...game,teams:(game.teams||[]).map(t=>({...t,players:(t.players||[]).filter(p=>p.ExperimentalModels?.[v]).map(p=>({...p,...p.ExperimentalModels[v]}))}))};
        experimental_quotes[v]=flatten(evaluate({...board,games:[shadow]},{...odds,events:(odds.events||[]).filter(e=>e.schedule_game_id===game.game_id)}));
      }
    }
    const dir=path.join(output,board.date_eastern);fs.mkdirSync(dir,{recursive:true});
    const file=path.join(dir,[game.game_id,board.generated_at_utc,withOdds?odds.generated_at_utc:'no-odds',pricingHash.slice(0,16)].map(safe).join('__')+'.json');
    const record={date_eastern:board.date_eastern,captured_at_utc:now,projection_utc:board.generated_at_utc,odds_snapshot_utc:withOdds?odds.generated_at_utc:null,pricing_version:pricingVersion,pricing_source_sha256:pricingHash,kenpom_source:board.kenpom_source??null,game,quotes:rows,experimental_quotes,diagnostics:result.diagnostics};
    try{fs.writeFileSync(file,JSON.stringify(record,null,2)+'\n',{flag:'wx'});written++;priced+=rows.length;positive+=rows.filter(r=>r.expected_roi_percent>0).length;}
    catch(e){if(e.code!=='EEXIST')throw e;}
  }
  return {written,skipped,priced,positive};
}
module.exports={capture};
if(require.main===module){
  const board=read('data/daily_board.json');
  let odds=null;try{odds=read('data/odds_snapshots/'+board.date_eastern+'.json');}catch(e){if(e.code!=='ENOENT')throw e;}
  const hash=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'pregame-edges.js'))).update(fs.readFileSync(__filename)).digest('hex');
  console.log(JSON.stringify(capture(board,odds,new Date().toISOString(),path.join(root,'data/archives/pregame'),hash)));
}
