'use strict';
/* Research-only pregame quote comparisons. No network calls except published JSON. */
(function(root){
const MARKETS={player_points:['Points','KenPomPoints','BaselinePoints'],player_rebounds:['Rebounds','KenPomRebounds','BaselineRebounds'],player_assists:['Assists','KenPomAssists','BaselineAssists'],player_threes:['Threes','KenPomThrees','BaselineThrees']};
const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
const number=x=>x===null||x===undefined||x===''?null:Number.isFinite(Number(x))?Number(x):null;
const time=s=>{const n=Date.parse(s||'');return Number.isFinite(n)?n:null};
function erf(x){const sign=x<0?-1:1; x=Math.abs(x);const t=1/(1+.3275911*x);return sign*(1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*Math.exp(-x*x));}
function normalCdf(x){return .5*(1+erf(x/Math.sqrt(2)))}
function poissonCdf(k,mu){if(mu<0||!Number.isFinite(mu))return null;if(k<0)return 0;let term=Math.exp(-mu),sum=term;for(let n=1;n<=k;n++){term*=mu/n;sum+=term;}return Math.min(1,sum)}
const DISTRIBUTION_VERSION='v10-player-distributions',COMBINED_VERSION='v11-combined',DISTRIBUTION_PRICING='player-count-dispersion-v1';
function negativeBinomialCdf(k,mu,alpha){
  if(!Number.isFinite(alpha)||alpha<=0||!Number.isFinite(mu)||mu<0)return null;
  if(k<0)return 0;if(mu===0)return 1;
  if(alpha<=1e-6)return poissonCdf(k,mu);
  const r=1/alpha,q=mu/(mu+r);
  let term=Math.exp(-r*Math.log1p(mu/r)),sum=term;
  if(!Number.isFinite(term)||term===0||k>1000)return null;
  for(let n=1;n<=k;n++){term*=((n-1+r)/n)*q;sum+=term;}
  return Math.max(0,Math.min(1,sum));
}
function probabilities(market,mean,line,distribution){
  if(mean===null||line===null||mean<0||line<0)return null;
  let under;
  if(distribution!==undefined){
    if(!distribution||!Number.isFinite(distribution.mean)||Math.abs(distribution.mean-mean)>1e-7)return null;
    if(distribution.family==='poisson')under=poissonCdf(Math.floor(line),mean);
    else if(distribution.family==='negative_binomial')under=negativeBinomialCdf(Math.floor(line),mean,distribution.dispersion);
    else return null;
  }
  else if(market==='player_points')under=normalCdf((Math.floor(line)-mean+.5)/5.5); // fixed, uncalibrated SD
  else under=poissonCdf(Math.floor(line),mean); // integer counts
  if(under===null)return null;
  return {over:1-under,under};
}
function profit(odds){return odds>=100?odds/100:odds<=-100?100/(-odds):null}
function american(p){if(p<=0||p>=1)return null;return p>=.5?Math.round(-100*p/(1-p)):Math.round(100*(1-p)/p)}
function evaluate(board,snapshot){
  const rows=[],diagnostics=[];
  if(board.date_eastern!==snapshot.snapshot_date_eastern){return {rows,diagnostics:[{reason:'Board and odds snapshot dates differ'}]};}
  const collected=time(snapshot.generated_at_utc),projected=time(board.generated_at_utc);
  for(const event of snapshot.events||[]){
    const game=(board.games||[]).find(g=>g.game_id===event.schedule_game_id);
    if(!game){diagnostics.push({game:event.home_team+' / '+event.away_team,reason:'No matching game ID'});continue;}
    const tipoff=time(game.tipoff_utc);
    if(!collected||!projected||!tipoff||collected>=tipoff||projected>=tipoff){diagnostics.push({game:game.home_team+' / '+game.away_team,reason:'Projection board or odds snapshot not demonstrably pregame'});continue;}
    const players=[];
    for(const team of game.teams||[])for(const p of team.players||[])players.push({team:team.team,p});
    const groups=new Map();
    for(const q of event.props||[]){
      if(!MARKETS[q.market])continue;
      const key=[q.bookmaker,q.market,norm(q.player),q.line].join('|');
      if(!groups.has(key))groups.set(key,[]);
      groups.get(key).push(q);
    }
    if(!groups.size)diagnostics.push({game:game.home_team+' / '+game.away_team,reason:'No captured player lines'});
    for(const quotes of groups.values()){
      const q=quotes[0],matches=players.filter(({p})=>norm(p.Player||p.player||p.name)===norm(q.player));
      const label=game.away_team+' at '+game.home_team;
      if(matches.length!==1){diagnostics.push({game:label,player:q.player,reason:matches.length?'Ambiguous player':'No archived player projection'});continue;}
      const p=matches[0].p,fields=MARKETS[q.market],mean=number(p[fields[1]]??p[fields[2]]),line=number(q.line);
      if(mean===null||line===null){diagnostics.push({game:label,player:q.player,reason:'Missing projection or line'});continue;}
      if(Number.isInteger(line)){diagnostics.push({game:label,player:q.player,reason:'Whole-number line requires push-aware pricing; excluded'});continue;}
      const sides={},updates={};let invalid=false;
      for(const x of quotes){const updated=time(x.last_update),side=String(x.side||'').toLowerCase();
        if(!updated||updated>collected||updated>=tipoff||!['over','under'].includes(side)||profit(number(x.odds))===null||sides[side]){invalid=true;break;}
        sides[side]=number(x.odds);updates[side]=x.last_update;
      }
      if(invalid){diagnostics.push({game:label,player:q.player,reason:'Invalid/duplicate or unverifiable quote'});continue;}
      const custom=[DISTRIBUTION_VERSION,COMBINED_VERSION].includes(p.ModelVersion);
      if(p.ModelVersion===COMBINED_VERSION&&(number(p.Minutes)===null||number(p.Minutes)<=0||p.CombinedModelInputs?.pricing_status==='excluded_zero_minutes')){
        diagnostics.push({game:label,player:q.player,reason:'V11 unavailable: zero or unverified playing time; no conditional-on-playing price'});continue;
      }
      const distribution=custom?(p.ProbabilityModel===DISTRIBUTION_PRICING?p.Distributions?.[fields[0]]??null:null):undefined;
      const ps=probabilities(q.market,mean,line,distribution);
      if(!ps){diagnostics.push({game:label,player:q.player,reason:'Probability unavailable'});continue;}
      const roi={};for(const side of ['over','under'])roi[side]=sides[side]===undefined?null:100*(ps[side]*profit(sides[side])-(1-ps[side]));
      const best=roi.over===null?'under':roi.under===null?'over':roi.over>=roi.under?'over':'under';
      rows.push({game:label,team:matches[0].team,player:q.player,book:q.bookmaker,market:fields[0],projection:mean,line,over:sides.over??null,under:sides.under??null,
        fairOver:american(ps.over),fairUnder:american(ps.under),probOver:ps.over,probUnder:ps.under,quoteUpdatedOver:updates.over??null,quoteUpdatedUnder:updates.under??null,modelVersion:p.ModelVersion??'unknown',pricingModel:custom?DISTRIBUTION_PRICING:'board-normal55-poisson-v1',distribution:custom?distribution:null,minutesRisk:p.MinutesRiskFlags||[],scenarioType:p.ScenarioType||null,adjustmentLabel:root.ACCAvailability?.adjustmentLabel(p)||'',projectionUtc:board.generated_at_utc,roiOver:roi.over,roiUnder:roi.under,bestSide:best,bestRoi:roi[best],snapshotUtc:snapshot.generated_at_utc,tipoffUtc:game.tipoff_utc,gameId:game.game_id,athleteId:String(p.AthleteId??'')});
    }
  }
  rows.sort((a,b)=>b.bestRoi-a.bestRoi);
  return {rows,diagnostics};
}
const names={draftkings:'DraftKings',fanduel:'FanDuel',williamhill_us:'Caesars',fanatics:'Fanatics',betonlineag:'BetOnline'};
const marketOrder=['Points','Rebounds','Assists','Threes'];
const FRESH_QUOTE_MINUTES=60;
function quotePregame(r,side,now=Date.now()){
  const saved=time(r.snapshotUtc),updated=time(side==='over'?r.quoteUpdatedOver:r.quoteUpdatedUnder),tip=time(r.tipoffUtc);
  return saved!==null&&updated!==null&&tip!==null&&updated<=saved&&saved<=now&&now<tip&&r[side]!=null;
}
function quoteFresh(r,side,now=Date.now()){
  const saved=time(r.snapshotUtc),updated=time(side==='over'?r.quoteUpdatedOver:r.quoteUpdatedUnder),tip=time(r.tipoffUtc);
  return quotePregame(r,side,now)&&now-updated<=FRESH_QUOTE_MINUTES*60000&&now-saved<=FRESH_QUOTE_MINUTES*60000;
}
function quoteEligible(r,side,now=Date.now(),freshOnly=false){return freshOnly?quoteFresh(r,side,now):quotePregame(r,side,now);}
function groupRows(rows,eligible=()=>true){
  const groups=new Map();
  for(const r of rows){
    const key=JSON.stringify([r.gameId||r.game,r.team,norm(r.player),r.market]);
    if(!groups.has(key))groups.set(key,{game:r.game,gameId:r.gameId,team:r.team,player:r.player,market:r.market,projection:r.projection,tipoffUtc:r.tipoffUtc,athleteId:r.athleteId,minutesRisk:r.minutesRisk||[],scenarioType:r.scenarioType,adjustmentLabel:r.adjustmentLabel,books:{},best:null});
    const g=groups.get(key);
    if(!g.books[r.book])g.books[r.book]=[];
    g.books[r.book].push(r);
    for(const side of ['over','under']){
      const roi=side==='over'?r.roiOver:r.roiUnder;
      if(eligible(r,side)&&roi!==null&&roi!==undefined&&Number.isFinite(roi)&&(!g.best||roi>g.best.roi))g.best={book:r.book,side,roi,line:r.line,odds:r[side]};
    }
  }
  return [...groups.values()];
}
const projectionFields=[['minutes','MIN','Minutes','minutes','MIN'],['points','PTS','KenPomPoints','BaselinePoints','points','PTS'],['reb','REB','KenPomRebounds','BaselineRebounds','rebounds','REB'],['assists','AST','KenPomAssists','BaselineAssists','assists','AST'],['three_pm','3PM','KenPomThrees','BaselineThrees','threes','3PM']];
function projectionValue(p,field){
  const spec=projectionFields.find(x=>x[0]===field);
  if(!spec)return null;
  for(const key of spec.slice(2)){const v=number(p?.[key]);if(v!==null)return v;}
  return null;
}
function projectionProfileContext(game,team,p){
  if(!game||!team||!p)return null;
  return {gameId:game.game_id,team:team.team,player:p.Player??p.player??p.name??'Unknown player',game:game.away_team+' at '+game.home_team,tipoffUtc:game.tipoff_utc,athleteId:String(p.AthleteId??''),market:null,books:{},projectionOnly:true};
}
function experimentalBoard(board,version){
  return {...board,games:(board.games||[]).map(g=>({...g,teams:(g.teams||[]).map(t=>({...t,players:(t.players||[]).filter(p=>p.ExperimentalModels?.[version]).map(p=>({...p,...p.ExperimentalModels[version],ControlProjection:p}))}))}))};
}
// Keep per-event observation timestamps; never relabel old lines as newly collected.
function latestSnapshots(board,base,manifest){
  const chosen=new Map(),games=new Map((board.games||[]).map(g=>[String(g.game_id),g]));
  if(base?.snapshot_date_eastern===board.date_eastern&&time(base.generated_at_utc)){
    for(const e of base.events||[])chosen.set(String(e.schedule_game_id),{...base,events:[e]});
  }
  if(manifest?.date_eastern===board.date_eastern)for(const o of manifest.observations||[]){
    if(!['ODDS_RETRIEVED','NO_REQUESTED_BOOK_PROPS_RETURNED'].includes(o.status))continue;
    const id=String(o.schedule_game_id),g=games.get(id),old=chosen.get(id),e=old?.events?.[0];
    const collected=time(o.generated_at_utc),tip=time(g?.tipoff_utc);
    if(!g||!e||e.event_id!==o.event_id||e.home_team!==o.home_team||e.away_team!==o.away_team||!collected||!tip||time(o.tipoff_utc)!==tip||collected>=tip||collected<=time(old.generated_at_utc))continue;
    chosen.set(id,{...base,generated_at_utc:o.generated_at_utc,events:[{...e,props:o.props||[]}]});
  }
  return [...chosen.values()];
}
const api={latestSnapshots,quoteFresh,quotePregame,quoteEligible,evaluate,probabilities,negativeBinomialCdf,experimentalBoard,groupRows,projectionValue,projectionProfileContext};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ACCPregameEdges=api;
if(!root.document)return;
const doc=root.document;
const host=doc.getElementById('sportsbookResults')||doc.getElementById('dailyResults');if(!host)return;
const section=doc.createElement('section');section.id='pregameEdges';section.innerHTML='<div class="edge-toolbar"><label>Market<select id="edgeMarket"><option value="">All markets</option><option>Points</option><option>Rebounds</option><option>Assists</option><option value="Threes">Made threes</option></select></label><label>Game<select id="edgeGame"><option value="">All games</option></select></label><div class="edge-book-filter"><span class="edge-book-label" id="edgeBookLabel">Book</span><details id="edgeBook"><summary aria-labelledby="edgeBookLabel edgeBookText"><span id="edgeBookText">All books</span></summary><div class="edge-book-menu"><div class="edge-book-actions"><button type="button" id="edgeBookAll">Select all</button><button type="button" id="edgeBookNone">Clear</button></div><div id="edgeBookChoices" role="group" aria-labelledby="edgeBookLabel"></div><button type="button" id="edgeBookDone">Done</button></div></details></div><label>Projection view<select id="edgeAvailability"><option value="adjusted">Availability-adjusted (where available)</option><option value="control">V4 control</option><option value="v10">V10 · Player distributions (research)</option><option value="v11">V11 · Combined model (research)</option></select></label><label>Sort<select id="edgeSort"><option value="roi">Highest ROI</option><option value="time">Tipoff time</option><option value="player">Player A–Z</option><option value="projection">Projection</option></select></label><label class="edge-search">Search<input id="edgeSearch" type="search" placeholder="Player or team"></label><label class="check edge-check"><input type="checkbox" id="edgePositive">Positive ROI only</label><label class="check edge-check" title="Limit to pregame quotes captured and updated within 60 minutes"><input type="checkbox" id="edgeFreshOnly">Updated within 60 min</label><button id="edgeReload" class="secondary" type="button">Refresh board</button></div><p id="edgeStatus" class="note" role="status">Loading saved odds…</p><div id="edgeCoverage" class="note"></div><div id="edgeTable" class="edge-scroll" tabindex="0" aria-label="Scrollable sportsbook odds comparison"></div><div id="edgeMissing"></div><details class="edge-method"><summary>Pricing methodology</summary><p class="note">Experimental research estimates, not validated win probabilities. Default pricing: points normal SD 5.5, rebounds, assists and threes Poisson. V10 uses the same V6 averages with shrunk player-specific count variance (negative binomial or Poisson), conditional on playing; small samples use priors. V11 combines V9 rotations, V6 production, V8 matchup adjustments and V10 count pricing; unavailable inputs are excluded, zero-minute players are not priced. ROI is expected profit per $1 staked. Only timestamp-verified pregame quotes and matched projections are priced; saved odds are not live. Saved ROI is calculated from the displayed price, not a live sportsbook quote. Each quote shows its last collection time; older quotes may still be available but should be verified. The optional 60-minute filter requires both the provider update and capture to be recent. Started games retain historical ROI but are excluded from best-edge and positive-ROI rankings. Historical CLV requirements are unchanged. Refresh board reloads existing files, not the paid odds API.</p></details>';
if(host.id==='sportsbookResults')host.appendChild(section);else host.parentNode.insertBefore(section,host.nextSibling);
const bookStyle=doc.createElement('style');
bookStyle.textContent=`
#pregameEdges .edge-quote-time{display:block;color:#91a2b9;font-size:10px;font-weight:400;line-height:1.2;margin-top:2px}
#pregameEdges .edge-quote-historical{color:#91a2b9}
#pregameEdges .edge-book-filter{position:relative;flex:0 0 auto}
#pregameEdges .edge-book-label{display:block;font-size:11px;font-weight:600;color:#a9bed8;margin-bottom:4px}
#pregameEdges #edgeBook{margin:0;color:#edf4ff;position:relative}
#pregameEdges #edgeBook summary{display:flex;justify-content:space-between;align-items:center;gap:10px;list-style:none;min-width:108px;border:1px solid #3b516d;background:#0d192c;border-radius:8px;padding:7px 9px;line-height:normal;font-size:12px;font-weight:600}
#pregameEdges #edgeBook summary::-webkit-details-marker{display:none}
#pregameEdges #edgeBook summary::after{content:'▾';color:#a9bed8}
#pregameEdges .edge-book-menu{position:absolute;z-index:30;top:calc(100% + 5px);left:0;width:210px;max-width:85vw;padding:9px;background:#152338;border:1px solid #405977;border-radius:8px;box-shadow:0 10px 28px #0008}
#pregameEdges .edge-book-actions{display:flex;justify-content:space-between;gap:5px;margin-bottom:7px}
#pregameEdges .edge-book-menu button{padding:5px 8px;font-size:11px}
#pregameEdges .edge-book-menu .edge-book-choice{display:flex;align-items:center;gap:9px;padding:7px 5px;cursor:pointer;color:#edf4ff;font-size:12px;margin:0}
#pregameEdges .edge-book-choice:hover{background:#21354f;border-radius:4px}
#pregameEdges .edge-book-choice input{width:auto;display:inline;margin:0;accent-color:#438cf8}
#pregameEdges #edgeBookDone{width:100%;margin-top:6px}
`;
section.appendChild(bookStyle);
const $=id=>doc.getElementById(id);
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>n===null||n===undefined?'—':Number(n).toFixed(1);
const odds=n=>n===null||n===undefined?'—':(n>0?'+':'')+n;
const roi=n=>n===null||n===undefined?'—':(n>0?'+':'')+fmt(n)+'%';
let current={rows:[],diagnostics:[]},requested=[],meta={},activeBoard=null,rawBoard=null,profileRows=[],profileFocus=null;
let showAvailability=true,showV10=false,showV11=false;
const BOOK_PREF='acc-edge-selected-books-v1';
let selectedBooks=null; // null means all books, [] means none
try{const pref=JSON.parse(root.localStorage.getItem(BOOK_PREF)||'null');if(Array.isArray(pref)&&pref.every(k=>typeof k==='string'))selectedBooks=new Set(pref);}catch(_e){}
function visibleBooks(){return requested.filter(k=>selectedBooks===null||selectedBooks.has(k));}
function updateBookChoices(){
  const books=visibleBooks();
  $('edgeBookText').textContent=selectedBooks===null?'All books':books.length===0?'No books':books.length===1?(names[books[0]]||books[0]):books.length+' of '+requested.length+' books';
  $('edgeBookChoices').innerHTML=requested.map(k=>'<label class="edge-book-choice"><input type="checkbox" value="'+esc(k)+'" '+(books.includes(k)?'checked':'')+'><span>'+esc(names[k]||k)+'</span></label>').join('');
}
function saveBookChoices(){
  try{root.localStorage.setItem(BOOK_PREF,JSON.stringify(selectedBooks===null?null:[...selectedBooks]));}catch(_e){}
  updateBookChoices();render();
}

function optionList(id,items,first){
  const select=$(id),prev=select.value;
  select.innerHTML='<option value="">'+esc(first)+'</option>'+items.map(([v,l])=>'<option value="'+esc(v)+'">'+esc(l)+'</option>').join('');
  if(items.some(([v])=>v===prev))select.value=prev;
}
function render(){
  const market=$('edgeMarket').value,game=$('edgeGame').value,positive=$('edgePositive').checked,search=$('edgeSearch').value.trim().toLowerCase(),sort=$('edgeSort').value;
  const books=visibleBooks();
  const rows=current.rows.filter(r=>books.includes(r.book)&&(!market||r.market===market)&&(!game||(r.gameId||r.game)===game)&&(!search||[r.player,r.team,r.game].some(x=>String(x||'').toLowerCase().includes(search))));
  const now=Date.now(),freshOnly=$('edgeFreshOnly').checked,fresh=(r,side)=>quoteFresh(r,side,now),eligible=(r,side)=>quoteEligible(r,side,now,freshOnly);
  const displayed=freshOnly?rows.filter(r=>['over','under'].some(side=>fresh(r,side))):rows;
  const grouped=groupRows(displayed,eligible).filter(g=>!positive||g.best?.roi>0);
  const older=rows.reduce((n,r)=>n+['over','under'].filter(side=>quotePregame(r,side,now)&&!fresh(r,side)).length,0);
  profileRows=grouped;
  const cmp=(a,b)=>sort==='time'?(time(a.tipoffUtc)||0)-(time(b.tipoffUtc)||0)||a.player.localeCompare(b.player):sort==='player'?a.player.localeCompare(b.player):sort==='projection'?b.projection-a.projection:(b.best?.roi??-Infinity)-(a.best?.roi??-Infinity);
  $('edgeStatus').textContent=(showV11?'V11 combined research pricing · ':showV10?'V10 research pricing · ':'')+(meta.date||'')+' · Latest odds saved '+(meta.oddsAt?new Date(meta.oddsAt).toLocaleString():'—')+' · Projections '+(meta.projectionAt?new Date(meta.projectionAt).toLocaleString():'—')+' · '+grouped.length+' player/market rows · '+current.rows.length+' matched book lines · '+books.length+' of '+requested.length+' books shown'+(older?' · '+older+' pregame quote sides older than 60 min'+(freshOnly?' (filtered)':' (verify prices)'):'')+' · Started games excluded from best ROI';
  function quote(r,side){
    const value=r[side],edge=side==='over'?r.roiOver:r.roiUnder,fair=side==='over'?r.fairOver:r.fairUnder;
    if(value==null||(freshOnly&&!fresh(r,side)))return '';
    const pregame=quotePregame(r,side,now),updated=side==='over'?r.quoteUpdatedOver:r.quoteUpdatedUnder;
    const checked=time(r.snapshotUtc)!==null?new Date(r.snapshotUtc).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}):'unknown';
    const detail=(pregame?'Checked '+checked:'Started · '+checked);
    return '<div class="edge-quote" title="'+esc('Fair odds '+odds(fair)+' · Estimated ROI at saved price '+roi(edge)+' · Provider update '+(updated?new Date(updated).toLocaleString():'unknown')+' · Saved '+new Date(r.snapshotUtc).toLocaleString()+(pregame?' · Verify current sportsbook price':' · Historical only'))+'"><span>'+ (side==='over'?'O':'U')+esc(r.line)+' <b>'+esc(odds(value))+'</b><small class="edge-quote-time">'+esc(detail)+'</small></span><span class="edge-roi'+(pregame&&edge>0?' edge-win':!pregame?' edge-quote-historical':'')+'">'+esc(roi(edge))+'</span></div>';
  }
  let html='<table class="edge-matrix"><thead><tr><th class="edge-player">Player / game</th><th class="edge-proj">Proj</th><th class="edge-best">Best ROI</th>'+books.map(k=>'<th class="edge-bookhead">'+esc(names[k]||k)+'</th>').join('')+'</tr></thead><tbody>';
  for(const m of marketOrder){
    const items=grouped.filter(g=>g.market===m).sort(cmp);
    if(!items.length)continue;
    html+='<tr class="edge-marketband"><th class="edge-player" scope="row">'+esc(m==='Threes'?'Made threes':m)+' <small>'+items.length+'</small></th><td colspan="'+(books.length+2)+'"></td></tr>';
    for(const g of items){
      const best=g.best,when=g.tipoffUtc?new Date(g.tipoffUtc).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}):'';
      html+='<tr><td class="edge-player"><button class="edge-player-link" type="button" data-profile="'+profileRows.indexOf(g)+'" title="View season game log">'+esc(g.player)+'</button>'+(g.adjustmentLabel?'<small title="'+esc(g.scenarioType==='local'?'Local preview — not archived':g.adjustmentLabel==='Manual Override'?'Direct manual playing-time adjustment':'Team minutes redistributed; not an injury designation')+'">'+esc(g.adjustmentLabel)+(g.scenarioType==='local'?' · Local':'')+'</small>':'')+((g.minutesRisk?.length&&(best?.roi>=20||g.scenarioType))?'<small class="edge-profile-warn" title="'+esc(g.minutesRisk.join(' · '))+'">⚠ Verify minutes</small>':'')+'<small>'+esc(g.team)+' · '+esc(when)+'</small><small class="edge-game-label" title="'+esc(g.game)+'">'+esc(g.game)+'</small></td><td class="edge-proj">'+esc(fmt(g.projection))+'</td><td class="edge-best">'+(best?'<strong class="'+(best.roi>0?'edge-win':'')+'">'+esc(roi(best.roi))+'</strong><small>'+esc(names[best.book]||best.book)+' · '+(best.side==='over'?'O':'U')+esc(best.line)+'</small>':'—')+'</td>';
      for(const k of books){
        const lines=(g.books[k]||[]).slice().sort((a,b)=>a.line-b.line);
        html+='<td class="edge-bookcell">'+(lines.length?lines.map(r=>quote(r,'over')+quote(r,'under')).join(''):'<span class="edge-empty">—</span>')+'</td>';
      }
      html+='</tr>';
    }
  }
  html+='</tbody></table>';
  $('edgeTable').innerHTML=grouped.length?html:'<p class="edge-empty-note">'+(books.length?'No matched lines for these filters. Missing quotes are never treated as zero ROI.':'Select at least one sportsbook to display the board.')+'</p>';
  $('edgeMissing').innerHTML='<details><summary>Coverage and matching diagnostics ('+current.diagnostics.length+')</summary><ul>'+current.diagnostics.slice(0,100).map(d=>'<li>'+esc(d.game||'')+' '+esc(d.player||'')+': '+esc(d.reason)+'</li>').join('')+'</ul></details>';
}
// Read-only player drilldown using exactly the games embedded in the projection.
const profile=doc.createElement('dialog');
profile.id='edgePlayerProfile';
profile.setAttribute('aria-labelledby','edgeProfileTitle');
profile.innerHTML='<div class="edge-profile-head"><div><h2 id="edgeProfileTitle">Player game log</h2><p id="edgeProfileSubtitle" class="note"></p></div><button type="button" id="edgeProfileClose" class="secondary">Close ×</button></div><div id="edgeProfileBody"></div>';
doc.body.appendChild(profile);
const profileStyle=doc.createElement('style');
profileStyle.textContent=`
#pregameEdges .edge-player-link,#daily .daily-player-link{padding:0;border:0;background:none;color:#9cc9ff;font-size:inherit;font-weight:750;text-align:left;white-space:normal;cursor:pointer;text-decoration:underline;text-underline-offset:3px}
#pregameEdges .edge-player-link:hover,#daily .daily-player-link:hover{color:#d1e5ff;background:none}
#edgePlayerProfile{color:#e8effb;background:#132239;border:1px solid #45658d;border-radius:13px;padding:20px;width:min(1150px,calc(100vw - 24px));max-height:90vh;overflow:auto;box-shadow:0 24px 80px #0009;font:inherit}
#edgePlayerProfile::backdrop{background:#000a}
#edgePlayerProfile .edge-profile-head{position:sticky;top:-20px;display:flex;justify-content:space-between;align-items:flex-start;gap:14px;background:#132239;z-index:5;padding:12px 0;border-bottom:1px solid #304057;margin-bottom:14px}
#edgePlayerProfile h2{font-size:21px;margin:0}
#edgePlayerProfile h3{font-size:15px;margin:18px 0 8px}
#edgePlayerProfile .note{margin:5px 0}
#edgePlayerProfile .edge-profile-head button{flex:none}
#edgePlayerProfile .edge-profile-summary{overflow:auto;border:1px solid #304057;border-radius:8px}
#edgePlayerProfile table{font-size:12px;font-variant-numeric:tabular-nums}
#edgePlayerProfile th,#edgePlayerProfile td{padding:8px 10px;text-align:right}
#edgePlayerProfile th:first-child,#edgePlayerProfile td:first-child{text-align:left}
#edgePlayerProfile .edge-profile-highlight{background:#213c52;color:#e7f3ff;font-weight:750}
#edgePlayerProfile .edge-profile-line{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin:12px 0}
#edgePlayerProfile .edge-profile-line label{margin:0;font-size:12px}
#edgePlayerProfile .edge-profile-line select{margin:4px 0 0;max-width:100%;font-size:12px;padding:7px}
#edgePlayerProfile .edge-profile-hit{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
#edgePlayerProfile .edge-profile-hit>div{flex:1;min-width:125px;border:1px solid #36516f;background:#0d192c;border-radius:8px;padding:10px}
#edgePlayerProfile .edge-profile-hit b{font-size:19px;display:block;margin-top:4px}
#edgePlayerProfile .edge-profile-chart{display:flex;gap:8px;align-items:flex-end;overflow-x:auto;padding:10px 6px 0;background:#101d32;border:1px solid #304057;border-radius:8px}
#edgePlayerProfile .edge-profile-bar{min-width:34px;max-width:72px;flex:1;text-align:center;font-size:11px;color:#a9bed8}
#edgePlayerProfile .edge-profile-bar>div{height:100px;display:flex;align-items:flex-end;position:relative}
#edgePlayerProfile .edge-profile-bar i{width:100%;display:block;background:#4c85be;border-radius:3px 3px 0 0}
#edgePlayerProfile .edge-profile-bar .edge-profile-over{background:#62ad9b}
#edgePlayerProfile .edge-profile-bar .edge-profile-threshold{position:absolute;left:0;right:0;border-top:1px dashed #e4e9f2;z-index:1}
#edgePlayerProfile .edge-profile-bar strong{display:block;color:#e8effb;margin-bottom:3px}
#edgePlayerProfile .edge-profile-bar small{display:block;padding:5px 0}
#edgePlayerProfile .edge-profile-warn{color:#efc27b}
@media(max-width:650px){#edgePlayerProfile{padding:12px}#edgePlayerProfile .edge-profile-head{top:-12px}#edgePlayerProfile th,#edgePlayerProfile td{padding:7px}#edgePlayerProfile .edge-profile-line select{max-width:270px}}
`;
doc.head.appendChild(profileStyle);
const profileFields=projectionFields;
const marketField={Points:'points',Rebounds:'reb',Assists:'assists',Threes:'three_pm'};
const fieldTitle={points:'Points',reb:'Rebounds',assists:'Assists',three_pm:'Made threes'};
const meanLog=(logs,k)=>{const a=logs.map(x=>number(x[k])).filter(x=>x!==null);return a.length?a.reduce((a,b)=>a+b,0)/a.length:null};
const plain=x=>number(x)===null?'—':String(number(x));
const shooting=(x,m,a)=>number(x[m])===null||number(x[a])===null?'—':plain(x[m])+'–'+plain(x[a]);
function renderProfile(g,p,choice=0){
  const body=$('edgeProfileBody');
  if(!p){body.innerHTML='<p class="note">The exact player projection could not be matched. No game log shown.</p>';return;}
  const logs=Array.isArray(p.CurrentSeasonLog)?p.CurrentSeasonLog.slice().sort((a,b)=>String(b.date).localeCompare(String(a.date))):null;
  if(!logs){body.innerHTML='<p class="note">Game logs are not included in this saved projection yet. Reload the board after the next projection publication.</p>';return;}
  if(logs.length!==Number(p.CurrentGP)){body.innerHTML='<p class="note edge-profile-warn">The stored log count does not match the projection inputs. No game-log statistics shown until the source is reconciled.</p>';return;}
  const k=marketField[g.market];
  const alternatives=Object.values(g.books||{}).flat().sort((a,b)=>a.book.localeCompare(b.book)||a.line-b.line);
  const r=alternatives[choice]||alternatives[0];
  let html='<p class="note">'+esc(p.ModelVersion||'')+' · '+esc(p.CurrentGP)+' games used · CBBD '+esc(p.CBBDGP??'—')+' / ESPN '+esc(p.ESPNGP??'—')+' · Last game '+esc(p.LatestGameDate??'—')+'</p>';
  if(p.MinutesNormalizationStatus==='normalized')html+='<p class="note">Rotation normalization: '+esc(fmt(number(p.RawMinutes)))+' → '+esc(fmt(number(p.Minutes)))+' MIN · Team before adjustment '+esc(fmt(number(p.RawTeamMinutes)))+' → 200.0 MIN</p>';
  if(p.DataCoverageWarning)html+='<p class="note edge-profile-warn">'+esc(p.DataCoverageWarning)+'</p>';
  if(p.DataIssues?.length)html+='<details><summary>Team-level source reconciliation notes ('+p.DataIssues.length+')</summary><ul>'+p.DataIssues.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></details>';
  html+='<h3>Projection vs. recent form</h3><div class="edge-profile-summary"><table><thead><tr><th>Sample</th>'+profileFields.map(([f,l])=>'<th'+(f===k?' class="edge-profile-highlight"':'')+'>'+l+'</th>').join('')+'</tr></thead><tbody>';
  const sets=[['Today’s projection',null],['Season ('+logs.length+')',logs],['Last '+Math.min(5,logs.length)+' games',logs.slice(0,5)],['Last '+Math.min(3,logs.length)+' games',logs.slice(0,3)]];
  for(const [label,sample] of sets)html+='<tr><td>'+esc(label)+'</td>'+profileFields.map(([f,l,proj])=>'<td'+(f===k?' class="edge-profile-highlight"':'')+'>'+esc(fmt(sample?meanLog(sample,f):projectionValue(p,f)))+'</td>').join('')+'</tr>';
  html+='</tbody></table></div>';
  if(g.projectionOnly){
    const baselines=[['minutes','Minutes'],['points','BaselinePoints'],['reb','BaselineRebounds'],['assists','BaselineAssists'],['three_pm','BaselineThrees']];
    const factors=[['Projected possessions',p.ProjectedPossessions,1],['Pace factor',p.PaceFactor,3],['Opponent defense factor',p.OpponentDefenseFactor,3]];
    html+='<h3>Model inputs for this matchup</h3><div class="edge-profile-summary"><table><thead><tr><th>Model</th>'+profileFields.map(([f,l])=>'<th>'+l+'</th>').join('')+'</tr></thead><tbody><tr><td>Baseline</td>'+baselines.map(([f,key])=>'<td>'+esc(fmt(number(p[key])))+'</td>').join('')+'</tr><tr><td>Published projection</td>'+profileFields.map(([f])=>'<td>'+esc(fmt(projectionValue(p,f)))+'</td>').join('')+'</tr></tbody></table></div>';
    html+='<p class="note">'+esc(factors.map(([label,v,d])=>label+': '+(number(v)===null?'—':number(v).toFixed(d))).join(' · '))+' · Confidence: '+esc(p.Confidence??'—')+'</p>';
  }
  const control=p.ControlProjection||p;
  const experiments=Object.entries(control.ExperimentalModels||{});
  if(control.CombinedModelStatus&&control.CombinedModelStatus!=='available')html+='<p class="note">V11 unavailable: '+esc(control.CombinedModelStatus.replaceAll('_',' '))+'</p>';
  if(control.RotationModelStatus&&control.RotationModelStatus!=='available')html+='<p class="note">V9 unavailable: '+esc(control.RotationModelStatus.replaceAll('_',' '))+'</p>';
  if(control.OpponentModelStatus&&control.OpponentModelStatus!=='available')html+='<p class="note">V8 unavailable: '+esc(control.OpponentModelStatus.replaceAll('_',' '))+'</p>';
  if(experiments.length){
    html+='<h3>Experimental projections · research only</h3><div class="edge-profile-summary"><table><thead><tr><th>Model</th>'+profileFields.map(([f,l])=>'<th>'+l+'</th>').join('')+'</tr></thead><tbody><tr><td>v4 control</td>'+profileFields.map(([f])=>'<td>'+esc(fmt(projectionValue(control,f)))+'</td>').join('')+'</tr>'+experiments.map(([v,x])=>'<tr><td>'+esc(v)+'</td>'+profileFields.map(([f])=>'<td>'+esc(fmt(projectionValue(x,f)))+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
    for(const [v,x] of experiments){
      if(x.RotationInputs&&v.includes('v5'))html+='<p class="note">Participation: '+esc(x.RotationInputs.appearances)+' of '+esc(x.RotationInputs.team_games)+' observed team games · '+esc(x.RotationInputs.starts)+' starts · Season minutes including nonappearances '+esc(fmt(x.RotationInputs.season_minutes_including_nonappearances))+'</p>';
      if(x.CombinedModelInputs){const a=x.CombinedModelInputs;html+='<p class="note"><strong>V11 combined</strong> · V9 minutes → V6 production → V8 opponent → V10 pricing · '+esc(a.distribution_games)+' production games'+(a.excluded_games?.length?' · Excluded '+esc(a.excluded_games.join(', ')):'')+(a.fallback_stats?.length?' · Generic matchup fallback: '+esc(a.fallback_stats.join(', ')):'')+(a.pricing_status==='excluded_zero_minutes'?' · No conditional playing-time price':'')+'</p>';}
      if(x.Distributions){html+='<h4>'+esc(v===COMBINED_VERSION?'V11 combined probability distributions':'V10 player-specific probability distributions · V6 means unchanged')+'</h4><div class="edge-profile-summary"><table><thead><tr><th>Stat</th><th>Mean</th><th>SD</th><th>Games</th><th>Distribution</th></tr></thead><tbody>'+Object.entries(x.Distributions).map(([stat,d])=>'<tr><td>'+esc(stat)+'</td><td>'+esc(fmt(d.mean))+'</td><td>'+esc(fmt(d.sd))+'</td><td>'+esc(d.sample)+'</td><td>'+esc(d.family.replace('_',' ')+' · '+d.status.replaceAll('_',' '))+'</td></tr>').join('')+'</tbody></table></div><p class="note">Conditional on appearing; priors protect small samples. Includes minutes variance and scoring residuals; shot volume and conversion inform the points variance prior.</p>';}
      if(x.IntelligentRotation&&!x.CombinedModelInputs){const a=x.IntelligentRotation;html+='<p class="note">V9 rotation · '+esc(a.role||'Unknown role')+' · '+esc(a.reconciled_games)+'/'+esc(a.candidate_games)+' reconciled games · V6 '+esc(fmt(a.v6_minutes))+' → '+esc(fmt(x.Minutes))+' MIN · '+esc(a.direct_swap_pairs)+' substitution partners · 4+ fouls '+esc(a.high_foul_games)+'/'+esc(a.foul_sample)+(a.manual_minutes!=null?' · Manual minutes locked':'')+(a.spread_available?' · Spread adjustment '+esc(fmt(a.spread_adjustment_minutes))+' MIN':' · No verified spread adjustment')+'</p>';}
      if(x.OpponentAdjustment&&!x.CombinedModelInputs){const a=x.OpponentAdjustment;html+='<p class="note">V8 opponent adjustments · '+esc(a.opponent_games)+' games · '+esc(a.national_teams)+' national teams · '+esc(Object.entries(a.factors).map(([k,v])=>k+' ×'+Number(v).toFixed(3)).join(' · '))+(a.fallback_stats?.length?' · V6 fallback: '+esc(a.fallback_stats.join(', ')):'')+'</p>';}
      if(x.ShotInputs&&!x.OpponentAdjustment&&!x.Distributions)html+='<p class="note">Shot-volume inputs (before matchup adjustment): '+esc(Object.entries(x.ShotInputs.components).map(([k,c])=>k+' '+fmt(x.ShotInputs.projected_attempts[k])+' attempts × '+fmt(100*c.expected_pct)+'%').join(' · '))+'</p>';
      else if(x.ShotStatus)html+='<p class="note edge-profile-warn">Insufficient complete shooting data: rotation-only fallback.</p>';
    }
    html+='<p class="note">Experimental estimates are archived for evaluation. V4 is retained as the archived control. Availability scenarios are separately labeled; local previews are not archived.</p>';
  }
  if(p.MinutesRiskFlags?.length)html+='<p class="note edge-profile-warn">Minutes review: '+esc(p.MinutesRiskFlags.join(' · '))+'</p>';
  const adjustmentLabel=root.ACCAvailability?.adjustmentLabel(p);
  if(adjustmentLabel)html+='<p class="note"><strong>'+esc(adjustmentLabel)+'</strong> · '+esc(p.AvailabilityAdjustment.reason)+' · Minutes '+esc(fmt(p.OriginalMinutes))+' → '+esc(fmt(p.Minutes))+' · Production games '+esc(p.ProductionGamesUsed)+(p.ScenarioType==='local'?' · Local preview, not archived':'')+'</p>';
  const canEdit=Date.now()<Date.parse(g.tipoffUtc)&&root.ACCAvailability;
  if(canEdit){
    const own=p.AvailabilityAdjustment?.status!=='redistributed'?p.AvailabilityAdjustment:null;
    html+='<h3>Manual availability preview</h3><p class="note">Saved on this browser only. Applies to this game before tipoff; redistributes the rest of the team to 200 minutes. Does not change official archives.</p><div class="toolbar"><label>Minutes<input id="manualAvailMinutes" type="number" min="0" max="40" step="0.1" value="'+esc(own?.minutes??p.Minutes)+'"></label><label>Status<select id="manualAvailStatus">'+['manual','returning','limited','out'].map(s=>'<option '+(s===own?.status?'selected':'')+'>'+s+'</option>').join('')+'</select></label><label>Reason<input id="manualAvailReason" value="'+esc(own?.reason||'')+'" placeholder="Reason for adjustment"></label></div><details><summary>Exclude injury-shortened games from production rates</summary>'+logs.map(x=>'<label class="check"><input type="checkbox" class="manualAvailExclude" value="'+esc(x.date)+'" '+(own?.exclude_dates?.includes(x.date)?'checked':'')+'>'+esc(x.date+' · '+x.opponent+' · '+x.minutes+' MIN')+'</label>').join('')+'</details><div class="toolbar"><button type="button" id="manualAvailSave">Apply preview</button><button type="button" id="manualAvailClear" class="secondary">Clear local preview</button></div><p id="manualAvailMessage" class="note" role="status"></p>';
  }
  if(r&&k){
    const usable=logs.filter(x=>number(x[k])!==null);
    const counts=a=>({n:a.length,over:a.filter(x=>number(x[k])>r.line).length,under:a.filter(x=>number(x[k])<r.line).length,push:a.filter(x=>number(x[k])===r.line).length});
    const summary=a=>{const c=counts(a);return c.n?c.over+'/'+c.n+' over · '+c.under+'/'+c.n+' under'+(c.push?' · '+c.push+' push':''):'No results'};
    html+='<div class="edge-profile-line"><label>Compare with saved '+esc(fieldTitle[k])+' line<select id="edgeProfileLine">'+alternatives.map((q,i)=>'<option value="'+i+'" '+(q===r?'selected':'')+'>'+esc((names[q.book]||q.book)+' '+q.line+' · O '+odds(q.over)+' / U '+odds(q.under))+'</option>').join('')+'</select></label><p class="note">Historical comparison only — not the modeled probability.</p></div>';
    const all=counts(usable),last=counts(logs.slice(0,5).filter(x=>number(x[k])!==null));
    html+='<div class="edge-profile-hit"><div><small>Season</small><b>'+esc(all.n?(100*all.over/all.n).toFixed(0)+'% over':'—')+'</b><small>'+esc(summary(usable))+'</small></div><div><small>Last 5 games</small><b>'+esc(last.n?(100*last.over/last.n).toFixed(0)+'% over':'—')+'</b><small>'+esc(summary(logs.slice(0,5).filter(x=>number(x[k])!==null)))+'</small></div><div><small>Current model</small><b>'+esc(fmt(g.projection))+'</b><small>Fair O '+esc(odds(r.fairOver))+' · Fair U '+esc(odds(r.fairUnder))+'</small></div></div>';
    const max=Math.max(1,r.line,...usable.map(x=>number(x[k])))*1.12;
    html+='<h3>'+esc(fieldTitle[k])+' by game · line '+esc(r.line)+'</h3><div class="edge-profile-chart" role="img" aria-label="'+esc('Game-by-game '+fieldTitle[k]+', dashed line '+r.line)+'">'+usable.slice().reverse().map(x=>{const v=number(x[k]);return '<div class="edge-profile-bar" title="'+esc(x.date+' '+x.opponent+': '+v)+'"><strong>'+esc(v)+'</strong><div><i class="'+(v>r.line?'edge-profile-over':'')+'" style="height:'+(100*v/max)+'%"></i><span class="edge-profile-threshold" style="bottom:'+(100*r.line/max)+'%"></span></div><small>'+esc(String(x.date).slice(5))+'</small></div>'}).join('')+'</div><p class="note">Dashed line: selected sportsbook threshold. Bars are chronological; teal indicates a result above that line.</p>';
  }
  html+='<h3>Current-season game log</h3><div class="edge-profile-summary"><table><thead><tr><th>Date</th><th>Opponent</th><th>H/A</th><th>Start</th>'+profileFields.map(([f,l])=>'<th'+(f===k?' class="edge-profile-highlight"':'')+'>'+l+'</th>').join('')+'<th>FG</th><th>3PT</th><th>FT</th><th>OREB</th><th>DREB</th><th>STL</th><th>BLK</th><th>TO</th><th>PF</th><th>Source</th></tr></thead><tbody>';
  const yn=x=>/^(true|1|yes)$/i.test(String(x))?'Yes':/^(false|0|no)$/i.test(String(x))?'No':'—';
  for(const x of logs)html+='<tr><td>'+esc(x.date)+'</td><td>'+esc(x.opponent)+'</td><td>'+esc(yn(x.home)==='Yes'?'H':yn(x.home)==='No'?'A':'—')+'</td><td>'+esc(yn(x.starter))+'</td>'+profileFields.map(([f])=>'<td'+(f===k?' class="edge-profile-highlight"':'')+'>'+esc(plain(x[f]))+'</td>').join('')+'<td>'+esc(shooting(x,'fgm','fga'))+'</td><td>'+esc(shooting(x,'three_pm','three_pa'))+'</td><td>'+esc(shooting(x,'ftm','fta'))+'</td>'+['oreb','dreb','steals','blocks','turnovers','fouls'].map(f=>'<td>'+esc(plain(x[f]))+'</td>').join('')+'<td>'+esc(x.source)+'</td></tr>';
  html+='</tbody></table></div><p class="note">Exact completed games used by this pregame projection; provider game dates can differ by a day. H/A reflects provider designation. Missing stats are shown as —, not zero.</p>';
  body.innerHTML=html;
  function changeAvailability(clear){
    try{
      const board=rawBoard||{date_eastern:new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()),games:[]};
      const game=board.games.find(x=>x.game_id===g.gameId);
      if(!game||Date.now()>=Date.parse(game.tipoff_utc))throw Error('Published pregame game unavailable; refresh Sportsbook Edges');
      const team=game.teams.find(t=>t.team===g.team),player=team?.players.find(x=>String(x.AthleteId)===g.athleteId);
      if(!player)throw Error('Player ID not found');
      const status=$('manualAvailStatus').value,minutes=status==='out'?0:Number($('manualAvailMinutes').value),reason=$('manualAvailReason').value.trim(),exclude_dates=[...body.querySelectorAll('.manualAvailExclude:checked')].map(x=>x.value);
      if(!clear&&(!$('manualAvailMinutes').value||!reason||!Number.isFinite(minutes)||minutes<0||minutes>40||Math.abs(minutes*10-Math.round(minutes*10))>1e-6||exclude_dates.length>=logs.length))throw Error('Enter valid minutes, reason, and retain at least one game');
      const settings=root.ACCAvailability.read(),key=root.ACCAvailability.id(board,game,team,player),value=clear?null:{minutes,status,reason,exclude_dates};
      if(clear)delete settings[key];else settings[key]=value;
      root.ACCAvailability.scenario(board,settings,true);
      root.ACCAvailability.save(board,game,team,player,value);
      showAvailability=true;showV10=false;showV11=false;$('edgeAvailability').value='adjusted';
      root.dispatchEvent(new Event('acc-availability-changed'));load();profile.close();
    }catch(e){$('manualAvailMessage').textContent=e.message;}
  }
  $('manualAvailSave')?.addEventListener('click',()=>changeAvailability(false));
  $('manualAvailClear')?.addEventListener('click',()=>changeAvailability(true));
  $('edgeProfileLine')?.addEventListener('change',e=>{const pos=profile.scrollTop;renderProfile(g,p,Number(e.target.value));profile.scrollTop=pos;$('edgeProfileLine')?.focus({preventScroll:true})});
}
function openProfile(g,button){
  if(!g)return;
  const game=activeBoard?.games?.find(x=>x.game_id===g.gameId);
  const candidates=(game?.teams||[]).filter(t=>t.team===g.team).flatMap(t=>t.players||[]).filter(p=>g.athleteId?String(p.AthleteId)===g.athleteId:norm(p.Player)===norm(g.player));
  const p=candidates.length===1?candidates[0]:null;
  showProfile(g,p,button);
}
function showProfile(g,p,button){
  $('edgeProfileTitle').textContent=g.player;
  $('edgeProfileSubtitle').textContent=g.team+' · '+g.game+' · '+(g.projectionOnly?'Daily projection':g.market==='Threes'?'Made threes':g.market);
  const alternatives=Object.values(g.books||{}).flat().sort((a,b)=>a.book.localeCompare(b.book)||a.line-b.line);
  const choice=Math.max(0,alternatives.findIndex(q=>q.book===g.best?.book&&q.line===g.best?.line));
  renderProfile(g,p,choice);
  profileFocus=button;
  if(!profile.open)profile.showModal();
  profile.scrollTop=0;
}
// Daily Projections passes the exact already-rendered player object, not a name lookup
// or a sportsbook quote. Works even if odds loading failed or player has no line.
root.ACCPlayerProfile={openProjection(game,team,p,button){
  const g=projectionProfileContext(game,team,p);if(!g)return;
  showProfile(g,p,button);
}};
$('edgeTable').addEventListener('click',e=>{const b=e.target.closest('button[data-profile]');if(b)openProfile(profileRows[Number(b.dataset.profile)],b)});
$('edgeProfileClose').addEventListener('click',()=>profile.close());
profile.addEventListener('click',e=>{if(e.target===profile){const r=profile.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)profile.close()}});
profile.addEventListener('close',()=>profileFocus?.focus());
async function load(){try{const b=await fetch('data/daily_board.json?edge='+Date.now(),{cache:'no-store'});
  if(!b.ok)throw Error('Published projection board unavailable');
  rawBoard=await b.json();
  let board;
  try{board=showV11?experimentalBoard(rawBoard,COMBINED_VERSION):showV10?experimentalBoard(rawBoard,DISTRIBUTION_VERSION):root.ACCAvailability?.scenario(rawBoard,undefined,showAvailability)||rawBoard;}catch(e){throw Error('Invalid local availability scenario: '+e.message+'; switch to V4 control or edit override');}
  activeBoard=board;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(board.date_eastern||''))throw Error('Invalid projection date');
  const s=await fetch('data/odds_snapshots/'+board.date_eastern+'.json?edge='+Date.now(),{cache:'no-store'});
  if(!s.ok)throw Error('No saved odds snapshot for the published projection slate');
  const base=await s.json();
  let manifest=null;
  try{const rr=await fetch('data/odds_snapshots/intraday/'+board.date_eastern+'.json?edge='+Date.now(),{cache:'no-store'});if(rr.ok)manifest=await rr.json();}catch(_e){}
  const snapshots=latestSnapshots(board,base,manifest);
  current={rows:[],diagnostics:[]};
  for(const snap of snapshots){const result=evaluate(board,snap);current.rows.push(...result.rows);current.diagnostics.push(...result.diagnostics);}
  current.rows.sort((a,b)=>b.bestRoi-a.bestRoi);
  // Optional separately archived pregame refreshes; never rewrite the immutable morning snapshot.
  if(board.date_eastern==='2026-11-23'){
    try{
      const rr=await fetch('data/odds_refreshes/2026-11-23_unc_monmouth.json?edge='+Date.now(),{cache:'no-store'});
      if(rr.ok){
        const fresh=await rr.json();
        const match=(base.events||[]).find(e=>e.event_id===fresh.event_id);
        if(match&&fresh.home_team===match.home_team&&fresh.away_team===match.away_team&&fresh.commence_time===board.games.find(g=>g.game_id===match.schedule_game_id)?.tipoff_utc?.replace('+00:00','Z')){
          const supplemental={date_eastern:board.date_eastern,generated_at_utc:fresh.generated_at_utc,snapshot_date_eastern:board.date_eastern,events:[{...match,props:fresh.props||[]}]};
          const extra=evaluate(board,supplemental);
          current.rows.push(...extra.rows);
          current.diagnostics.push(...extra.diagnostics);
          current.rows.sort((a,b)=>b.bestRoi-a.bestRoi);
        }else current.diagnostics.push({game:'North Carolina / Monmouth',reason:'Refresh event identity or tipoff mismatch; ignored'});
      }
    }catch(_e){current.diagnostics.push({game:'North Carolina / Monmouth',reason:'Supplemental odds refresh unavailable'});}
  }
  requested=[...new Set([...(base.bookmakers||Object.keys(names)),...current.rows.map(r=>r.book)])];
  meta={date:board.date_eastern,oddsAt:snapshots.reduce((t,x)=>time(x.generated_at_utc)>time(t)?x.generated_at_utc:t,base.generated_at_utc),projectionAt:board.generated_at_utc};
  const counts={};
  for(const snapshot of snapshots)for(const event of snapshot.events||[])for(const q of event.props||[])counts[q.bookmaker]=(counts[q.bookmaker]||0)+1;
  const coverage=root.document.getElementById('edgeCoverage');
  coverage.innerHTML='<strong>Saved sportsbook coverage</strong> · latest saved per-game quotes; collection times vary by game; matched lines require a valid pregame ACC player projection.<br>'+requested.map(k=>{const n=counts[k]||0,m=current.rows.filter(r=>r.book===k).length;return esc(names[k]||k)+': '+n+' quotes / '+m+' matched lines'+(n===0?' (none returned in latest snapshots)':'')}).join(' · ');
  updateBookChoices();
  optionList('edgeGame',[...new Map(current.rows.map(r=>[r.gameId||r.game,r.game])).entries()],'All games');render();
}catch(e){current={rows:[],diagnostics:[]};$('edgeTable').innerHTML='';$('edgeCoverage').textContent='';$('edgeMissing').innerHTML='';$('edgeStatus').textContent=e.message+'; no edges shown.';}}
for(const id of ['edgeMarket','edgeGame','edgeSort','edgePositive','edgeFreshOnly'])$(id).addEventListener('change',render);
$('edgeBookChoices').addEventListener('change',e=>{
  if(e.target.type!=='checkbox')return;
  if(selectedBooks===null)selectedBooks=new Set(requested);
  if(e.target.checked)selectedBooks.add(e.target.value);else selectedBooks.delete(e.target.value);
  if(requested.every(k=>selectedBooks.has(k)))selectedBooks=null;
  // Do not rebuild the focused checkbox on each click; preserve keyboard focus.
  try{root.localStorage.setItem(BOOK_PREF,JSON.stringify(selectedBooks===null?null:[...selectedBooks]));}catch(_e){}
  const books=visibleBooks();
  $('edgeBookText').textContent=selectedBooks===null?'All books':books.length===0?'No books':books.length===1?(names[books[0]]||books[0]):books.length+' of '+requested.length+' books';
  render();
});
$('edgeBookAll').addEventListener('click',()=>{selectedBooks=null;saveBookChoices()});
$('edgeBookNone').addEventListener('click',()=>{selectedBooks=new Set();saveBookChoices()});
$('edgeBookDone').addEventListener('click',()=>{$('edgeBook').open=false;$('edgeBook').querySelector('summary').focus()});
doc.addEventListener('click',e=>{if(!$('edgeBook').contains(e.target))$('edgeBook').open=false});
$('edgeBook').addEventListener('keydown',e=>{if(e.key==='Escape'){$('edgeBook').open=false;$('edgeBook').querySelector('summary').focus()}});

$('edgeSearch').addEventListener('input',render);
$('edgeReload').addEventListener('click',load);
$('edgeAvailability').addEventListener('change',e=>{showAvailability=e.target.value==='adjusted';showV10=e.target.value==='v10';showV11=e.target.value==='v11';load();});
doc.querySelector('[data-tab="sportsbook"]')?.addEventListener('click',load);
// Update the age display even if no new snapshot is published.
root.setInterval(()=>{if(activeBoard)render();},60000);
load();
})(typeof window!=='undefined'?window:globalThis);
