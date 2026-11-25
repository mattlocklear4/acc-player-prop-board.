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
function probabilities(market,mean,line){
  if(mean===null||line===null||mean<0||line<0)return null;
  let under;
  if(market==='player_points')under=normalCdf((Math.floor(line)-mean+.5)/5.5); // fixed, uncalibrated SD
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
      const sides={};let invalid=false;
      for(const x of quotes){const updated=time(x.last_update),side=String(x.side||'').toLowerCase();
        if(!updated||updated>collected||updated>=tipoff||!['over','under'].includes(side)||profit(number(x.odds))===null||sides[side]){invalid=true;break;}
        sides[side]=number(x.odds);
      }
      if(invalid){diagnostics.push({game:label,player:q.player,reason:'Invalid/duplicate or unverifiable quote'});continue;}
      const ps=probabilities(q.market,mean,line);
      if(!ps){diagnostics.push({game:label,player:q.player,reason:'Probability unavailable'});continue;}
      const roi={};for(const side of ['over','under'])roi[side]=sides[side]===undefined?null:100*(ps[side]*profit(sides[side])-(1-ps[side]));
      const best=roi.over===null?'under':roi.under===null?'over':roi.over>=roi.under?'over':'under';
      rows.push({game:label,team:matches[0].team,player:q.player,book:q.bookmaker,market:fields[0],projection:mean,line,over:sides.over??null,under:sides.under??null,
        fairOver:american(ps.over),fairUnder:american(ps.under),roiOver:roi.over,roiUnder:roi.under,bestSide:best,bestRoi:roi[best],snapshotUtc:snapshot.generated_at_utc,tipoffUtc:game.tipoff_utc,gameId:game.game_id});
    }
  }
  rows.sort((a,b)=>b.bestRoi-a.bestRoi);
  return {rows,diagnostics};
}
const names={draftkings:'DraftKings',fanduel:'FanDuel',williamhill_us:'Caesars',fanatics:'Fanatics',betonlineag:'BetOnline'};
const marketOrder=['Points','Rebounds','Assists','Threes'];
function groupRows(rows){
  const groups=new Map();
  for(const r of rows){
    const key=JSON.stringify([r.gameId||r.game,r.team,norm(r.player),r.market]);
    if(!groups.has(key))groups.set(key,{game:r.game,gameId:r.gameId,team:r.team,player:r.player,market:r.market,projection:r.projection,tipoffUtc:r.tipoffUtc,books:{},best:null});
    const g=groups.get(key);
    if(!g.books[r.book])g.books[r.book]=[];
    g.books[r.book].push(r);
    for(const side of ['over','under']){
      const roi=side==='over'?r.roiOver:r.roiUnder;
      if(roi!==null&&roi!==undefined&&Number.isFinite(roi)&&(!g.best||roi>g.best.roi))g.best={book:r.book,side,roi,line:r.line,odds:r[side]};
    }
  }
  return [...groups.values()];
}
const api={evaluate,probabilities,groupRows};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ACCPregameEdges=api;
if(!root.document)return;
const doc=root.document;
const host=doc.getElementById('sportsbookResults')||doc.getElementById('dailyResults');if(!host)return;
const section=doc.createElement('section');section.id='pregameEdges';section.innerHTML='<div class="edge-toolbar"><label>Market<select id="edgeMarket"><option value="">All markets</option><option>Points</option><option>Rebounds</option><option>Assists</option><option value="Threes">Made threes</option></select></label><label>Game<select id="edgeGame"><option value="">All games</option></select></label><label>Book<select id="edgeBook"><option value="">All books</option></select></label><label>Sort<select id="edgeSort"><option value="roi">Highest ROI</option><option value="time">Tipoff time</option><option value="player">Player A–Z</option><option value="projection">Projection</option></select></label><label class="edge-search">Search<input id="edgeSearch" type="search" placeholder="Player or team"></label><label class="check edge-check"><input type="checkbox" id="edgePositive">Positive ROI only</label><button id="edgeReload" class="secondary" type="button">Refresh board</button></div><p id="edgeStatus" class="note" role="status">Loading saved odds…</p><div id="edgeCoverage" class="note"></div><div id="edgeTable" class="edge-scroll" tabindex="0" aria-label="Scrollable sportsbook odds comparison"></div><div id="edgeMissing"></div><details class="edge-method"><summary>Pricing methodology</summary><p class="note">Experimental research estimates, not validated win probabilities. Points use normal SD 5.5; rebounds, assists and threes use Poisson. ROI is expected profit per $1 staked. Only timestamp-verified pregame quotes and matched projections are priced; saved odds are not live. Refresh board reloads existing files, not the paid odds API.</p></details>';
if(host.id==='sportsbookResults')host.appendChild(section);else host.parentNode.insertBefore(section,host.nextSibling);
const $=id=>doc.getElementById(id);
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>n===null||n===undefined?'—':Number(n).toFixed(1);
const odds=n=>n===null||n===undefined?'—':(n>0?'+':'')+n;
const roi=n=>n===null||n===undefined?'—':(n>0?'+':'')+fmt(n)+'%';
let current={rows:[],diagnostics:[]},requested=[],meta={};
function optionList(id,items,first){
  const select=$(id),prev=select.value;
  select.innerHTML='<option value="">'+esc(first)+'</option>'+items.map(([v,l])=>'<option value="'+esc(v)+'">'+esc(l)+'</option>').join('');
  if(items.some(([v])=>v===prev))select.value=prev;
}
function render(){
  const book=$('edgeBook').value,market=$('edgeMarket').value,game=$('edgeGame').value,positive=$('edgePositive').checked,search=$('edgeSearch').value.trim().toLowerCase(),sort=$('edgeSort').value;
  const books=book?[book]:requested;
  const rows=current.rows.filter(r=>(!book||r.book===book)&&(!market||r.market===market)&&(!game||(r.gameId||r.game)===game)&&(!search||[r.player,r.team,r.game].some(x=>String(x||'').toLowerCase().includes(search))));
  const grouped=groupRows(rows).filter(g=>!positive||g.best?.roi>0);
  const cmp=(a,b)=>sort==='time'?(time(a.tipoffUtc)||0)-(time(b.tipoffUtc)||0)||a.player.localeCompare(b.player):sort==='player'?a.player.localeCompare(b.player):sort==='projection'?b.projection-a.projection:(b.best?.roi??-Infinity)-(a.best?.roi??-Infinity);
  $('edgeStatus').textContent=(meta.date||'')+' · Odds saved '+(meta.oddsAt?new Date(meta.oddsAt).toLocaleString():'—')+' · Projections '+(meta.projectionAt?new Date(meta.projectionAt).toLocaleString():'—')+' · '+grouped.length+' player/market rows · '+current.rows.length+' matched book lines';
  function quote(r,side){
    const value=r[side],edge=side==='over'?r.roiOver:r.roiUnder,fair=side==='over'?r.fairOver:r.fairUnder;
    if(value==null)return '';
    return '<div class="edge-quote" title="'+esc('Fair odds '+odds(fair)+' · Estimated ROI '+roi(edge)+' · Saved '+new Date(r.snapshotUtc).toLocaleString())+'"><span>'+ (side==='over'?'O':'U')+esc(r.line)+' <b>'+esc(odds(value))+'</b></span><span class="edge-roi'+(edge>0?' edge-win':'')+'">'+esc(roi(edge))+'</span></div>';
  }
  let html='<table class="edge-matrix"><thead><tr><th class="edge-player">Player / game</th><th class="edge-proj">Proj</th><th class="edge-best">Best ROI</th>'+books.map(k=>'<th class="edge-bookhead">'+esc(names[k]||k)+'</th>').join('')+'</tr></thead><tbody>';
  for(const m of marketOrder){
    const items=grouped.filter(g=>g.market===m).sort(cmp);
    if(!items.length)continue;
    html+='<tr class="edge-marketband"><th class="edge-player" scope="row">'+esc(m==='Threes'?'Made threes':m)+' <small>'+items.length+'</small></th><td colspan="'+(books.length+2)+'"></td></tr>';
    for(const g of items){
      const best=g.best,when=g.tipoffUtc?new Date(g.tipoffUtc).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}):'';
      html+='<tr><td class="edge-player"><strong>'+esc(g.player)+'</strong><small>'+esc(g.team)+' · '+esc(when)+'</small><small class="edge-game-label" title="'+esc(g.game)+'">'+esc(g.game)+'</small></td><td class="edge-proj">'+esc(fmt(g.projection))+'</td><td class="edge-best">'+(best?'<strong class="'+(best.roi>0?'edge-win':'')+'">'+esc(roi(best.roi))+'</strong><small>'+esc(names[best.book]||best.book)+' · '+(best.side==='over'?'O':'U')+esc(best.line)+'</small>':'—')+'</td>';
      for(const k of books){
        const lines=(g.books[k]||[]).slice().sort((a,b)=>a.line-b.line);
        html+='<td class="edge-bookcell">'+(lines.length?lines.map(r=>quote(r,'over')+quote(r,'under')).join(''):'<span class="edge-empty">—</span>')+'</td>';
      }
      html+='</tr>';
    }
  }
  html+='</tbody></table>';
  $('edgeTable').innerHTML=grouped.length?html:'<p class="edge-empty-note">No matched lines for these filters. Missing quotes are never treated as zero ROI.</p>';
  $('edgeMissing').innerHTML='<details><summary>Coverage and matching diagnostics ('+current.diagnostics.length+')</summary><ul>'+current.diagnostics.slice(0,100).map(d=>'<li>'+esc(d.game||'')+' '+esc(d.player||'')+': '+esc(d.reason)+'</li>').join('')+'</ul></details>';
}
async function load(){try{const b=await fetch('data/daily_board.json?edge='+Date.now(),{cache:'no-store'});
  if(!b.ok)throw Error('Published projection board unavailable');
  const board=await b.json();
  if(!/^\d{4}-\d{2}-\d{2}$/.test(board.date_eastern||''))throw Error('Invalid projection date');
  const s=await fetch('data/odds_snapshots/'+board.date_eastern+'.json?edge='+Date.now(),{cache:'no-store'});
  if(!s.ok)throw Error('No saved odds snapshot for the published projection slate');
  const base=await s.json();
  current=evaluate(board,base);
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
  meta={date:board.date_eastern,oddsAt:base.generated_at_utc,projectionAt:board.generated_at_utc};
  const counts={};
  for(const event of base.events||[])for(const q of event.props||[])counts[q.bookmaker]=(counts[q.bookmaker]||0)+1;
  const coverage=root.document.getElementById('edgeCoverage');
  coverage.innerHTML='<strong>Saved sportsbook coverage</strong> · individual over/under quotes returned in the daily snapshot; matched lines require a valid pregame ACC player projection.<br>'+requested.map(k=>{const n=counts[k]||0,m=current.rows.filter(r=>r.book===k).length;return esc(names[k]||k)+': '+n+' quotes / '+m+' matched lines'+(n===0?' (none returned in daily snapshot)':'')}).join(' · ');
  optionList('edgeBook',requested.map(k=>[k,names[k]||k]),'All books');
  optionList('edgeGame',[...new Map(current.rows.map(r=>[r.gameId||r.game,r.game])).entries()],'All games');render();
}catch(e){current={rows:[],diagnostics:[]};$('edgeTable').innerHTML='';$('edgeCoverage').textContent='';$('edgeMissing').innerHTML='';$('edgeStatus').textContent=e.message+'; no edges shown.';}}
for(const id of ['edgeBook','edgeMarket','edgeGame','edgeSort','edgePositive'])$(id).addEventListener('change',render);
$('edgeSearch').addEventListener('input',render);
$('edgeReload').addEventListener('click',load);
doc.querySelector('[data-tab="sportsbook"]')?.addEventListener('click',load);
load();
})(typeof window!=='undefined'?window:globalThis);
