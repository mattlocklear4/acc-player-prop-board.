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
        fairOver:american(ps.over),fairUnder:american(ps.under),roiOver:roi.over,roiUnder:roi.under,bestSide:best,bestRoi:roi[best],snapshotUtc:snapshot.generated_at_utc});
    }
  }
  rows.sort((a,b)=>b.bestRoi-a.bestRoi);
  return {rows,diagnostics};
}
const api={evaluate,probabilities};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ACCPregameEdges=api;
if(!root.document)return;
const host=root.document.getElementById('dailyResults');if(!host)return;
const section=root.document.createElement('section');section.id='pregameEdges';section.innerHTML='<h3>Pregame sportsbook edges · experimental</h3><p class="note">Published pregame projections vs timestamped actual book quotes. Points: normal SD 5.5; rebounds, assists and threes: Poisson. These are uncalibrated distribution assumptions, not validated win probabilities. ROI is hypothetical per $1 stake, not historical performance.</p><div class="toolbar"><label>Book <select id="edgeBook"><option value="">All books</option></select></label><label class="check"><input type="checkbox" id="edgePositive">Positive estimated ROI only</label></div><p id="edgeStatus" class="note">Loading saved odds…</p><div id="edgeCoverage" class="note"></div><div id="edgeTable" class="tablewrap"></div><div id="edgeMissing"></div>';
host.parentNode.insertBefore(section,host.nextSibling);
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&quot;'}[c]));
const fmt=n=>n===null||n===undefined?'—':Number(n).toFixed(1);
let current={rows:[],diagnostics:[]};
function render(){const book=root.document.getElementById('edgeBook').value,positive=root.document.getElementById('edgePositive').checked;
  const rows=current.rows.filter(r=>(!book||r.book===book)&&(!positive||r.bestRoi>0));
  root.document.getElementById('edgeStatus').textContent=current.rows.length+' matched player/book/market lines · '+rows.length+' displayed · '+current.diagnostics.length+' coverage gaps';
  root.document.getElementById('edgeTable').innerHTML=rows.length?'<table><thead><tr><th>Game / player</th><th>Book</th><th>Stat</th><th>Proj</th><th>Line</th><th>Over</th><th>Fair O</th><th>ROI O</th><th>Under</th><th>Fair U</th><th>ROI U</th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+esc(r.player)+'<small> · '+esc(r.team)+'</small></td><td>'+esc(r.book)+'</td><td>'+esc(r.market)+'</td><td>'+fmt(r.projection)+'</td><td>'+fmt(r.line)+'</td><td>'+esc(r.over)+'</td><td>'+esc(r.fairOver)+'</td><td>'+fmt(r.roiOver)+'%</td><td>'+esc(r.under)+'</td><td>'+esc(r.fairUnder)+'</td><td>'+fmt(r.roiUnder)+'%</td></tr>').join('')+'</tbody></table>':'<p class="note">No eligible matched lines for this filter. An unavailable match is never counted as a positive edge.</p>';
  root.document.getElementById('edgeMissing').innerHTML='<details><summary>Coverage and matching diagnostics ('+current.diagnostics.length+')</summary><ul>'+current.diagnostics.slice(0,100).map(d=>'<li>'+esc(d.game||'')+' '+esc(d.player||'')+': '+esc(d.reason)+'</li>').join('')+'</ul></details>';
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
  const names={draftkings:'DraftKings',fanduel:'FanDuel',williamhill_us:'Caesars',fanatics:'Fanatics',betonlineag:'BetOnline'};
  const requested=[...new Set([...(base.bookmakers||[]),...current.rows.map(r=>r.book)])];
  const counts={};
  for(const event of base.events||[])for(const q of event.props||[])counts[q.bookmaker]=(counts[q.bookmaker]||0)+1;
  const coverage=root.document.getElementById('edgeCoverage');
  coverage.innerHTML='<strong>Saved sportsbook coverage</strong> · individual over/under quotes returned in the daily snapshot; matched lines require a valid pregame ACC player projection.<br>'+requested.map(k=>{const n=counts[k]||0,m=current.rows.filter(r=>r.book===k).length;return esc(names[k]||k)+': '+n+' quotes / '+m+' matched lines'+(n===0?' (none returned in daily snapshot)':'')}).join(' · ');
  const select=root.document.getElementById('edgeBook');select.innerHTML='<option value="">All books</option>'+requested.map(k=>'<option value="'+esc(k)+'">'+esc(names[k]||k)+'</option>').join('');render();
}catch(e){root.document.getElementById('edgeStatus').textContent=e.message+'; no edges shown.';}}
root.document.getElementById('edgeBook').addEventListener('change',render);
root.document.getElementById('edgePositive').addEventListener('change',render);
load();
})(typeof window!=='undefined'?window:globalThis);
