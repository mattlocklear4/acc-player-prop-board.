(()=>{'use strict';
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
const alias={floridastate:'floridastate',floridast:'floridastate',miamifl:'miami',miamiflorida:'miami',ncstate:'ncstate',northcarolinastate:'ncstate',pitt:'pittsburgh',cal:'california'};
const canon=s=>alias[norm(s)]||norm(s), cap=(v,a,b)=>Math.max(a,Math.min(b,v)), fmt=v=>Number.isFinite(v)?v.toFixed(1):'—';
const acc={bostoncollege:'Boston College',california:'California',clemson:'Clemson',duke:'Duke',floridastate:'Florida State',georgiatech:'Georgia Tech',louisville:'Louisville',miami:'Miami',ncstate:'NC State',northcarolina:'North Carolina',notredame:'Notre Dame',pittsburgh:'Pittsburgh',smu:'SMU',stanford:'Stanford',syracuse:'Syracuse',virginia:'Virginia',virginiatech:'Virginia Tech',wakeforest:'Wake Forest'};
const mascots={bostoncollege:'eagles',california:'goldenbears',clemson:'tigers',duke:'bluedevils',floridastate:'seminoles',georgiatech:'yellowjackets',louisville:'cardinals',miami:'hurricanes',ncstate:'wolfpack',northcarolina:'tarheels',notredame:'fightingirish',pittsburgh:'panthers',smu:'mustangs',stanford:'cardinal',syracuse:'orange',virginia:'cavaliers',virginiatech:'hokies',wakeforest:'demondeacons'};
function identify(s){const n=norm(s);for(const k of Object.keys(acc)){if(n===k||n===k+mascots[k])return k}return null}
function median(a){a.sort((x,y)=>x-y);return a.length?(a[Math.floor((a.length-1)/2)]+a[Math.floor(a.length/2)])/2:NaN}
let feed=null,last=[];
function render(){const status=$('vegasMatchupStatus');if(!status)return;
const selection=window.ACCMatchup?.getSelection(), rows=window.ACCMatchup?.getRows()||[], snapshot=window.ACCKenPom?.getSnapshot();
const team=selection?.team,opp=selection?.opponent;last=[];$('vegasMatchupTable').innerHTML='';$('vegasMatchupSummary').textContent='';
if(!team||!opp){status.textContent='Choose an ACC team and opponent in the KenPom matchup panel below.';return}
if(!feed){status.textContent='Waiting for the published odds snapshot.';return}
const teamId=canon(team), oppId=canon(opp);
const games=(feed.games||[]).filter(g=>{
 const home=identify(g.home_team),away=identify(g.away_team);
 const oppMatch=name=>{const id=identify(name);if(id)return id===oppId;const n=norm(name);return n===oppId||n.startsWith(oppId)};
 return (home===teamId&&oppMatch(g.away_team))||(away===teamId&&oppMatch(g.home_team))
});
if(!games.length){status.textContent='No exact matchup found in the latest odds feed. No Vegas adjustment applied.';return}
const game=games.sort((a,b)=>a.commence_time.localeCompare(b.commence_time))[0], tip=Date.parse(game.commence_time), collected=Date.parse(feed.collected_at);
if(!Number.isFinite(tip)||!Number.isFinite(collected)||collected>=tip){status.textContent='Odds snapshot was not collected before this game’s tipoff. Excluded from pregame research.';return}
const spreads=[],totals=[],books=[];
for(const b of game.bookmakers||[]){const t=b.markets?.totals?.outcomes?.find(o=>o.name==='Over')?.point;
 const s=b.markets?.spreads?.outcomes?.find(o=>o.name===game.home_team)?.point;
 const tu=b.markets?.totals?.last_update, su=b.markets?.spreads?.last_update;
 if(!Number.isFinite(Number(t))||!Number.isFinite(Number(s))||t==null||s==null)continue;
 if((tu&&Date.parse(tu)>=tip)||(su&&Date.parse(su)>=tip))continue;
 const teamSpread=identify(game.home_team)===teamId?Number(s):-Number(s);
 totals.push(Number(t));spreads.push(teamSpread);books.push(b.title||b.key)
}
if(!totals.length){status.textContent='No complete pregame spread + total pair available for this matchup.';return}
const total=median(totals),spread=median(spreads),implied=(total-spread)/2;
const kp=snapshot?.rows||[],tr=kp.find(r=>canon(r.Team)===teamId),or=kp.find(r=>canon(r.Team)===oppId);
const tempo=(Number(tr?.AdjT)+Number(or?.AdjT))/2;
const expected=tempo*(Number(tr?.AdjO)*Number(or?.AdjD)/105)/100;
if(!Number.isFinite(expected)||expected<=0){status.textContent='KenPom offensive/defensive ratings unavailable; cannot compute market-vs-model scoring gap.';return}
// Research-only: 50% shrinkage toward Vegas team implied scoring, cap at +/-15%.
const factor=cap(1+0.5*(implied/expected-1),0.85,1.15);
last=rows.map(r=>{const o={Player:r.Player,Team:team,Opponent:opp,Tipoff:game.commence_time,OddsCollectedAt:feed.collected_at,Books:books.join('; '),GameTotal:total,TeamSpread:spread,TeamImplied:implied,KenPomTeamExpected:expected,MarketFactor:factor};
 for(const k of ['Points','Rebounds','Assists','Threes']){const base=Number(r['Baseline'+k]),adj=Number(r['Adjusted'+k]);o['Baseline'+k]=base;o['KenPom'+k]=adj;
 const m=k==='Points'?factor:k==='Assists'?1+0.5*(factor-1):k==='Threes'?1+0.5*(factor-1):1;
 o['Vegas'+k]=base*m;o['Combined'+k]=adj*m}return o});
status.textContent=`${game.away_team} at ${game.home_team} · ${last.length} players · ${books.length} books · collected ${new Date(collected).toLocaleString()}`;
$('vegasMatchupSummary').textContent=`Consensus total ${fmt(total)} · ${team} spread ${spread>0?'+':''}${fmt(spread)} · implied ${team} points ${fmt(implied)} · KenPom expected ${fmt(expected)} · experimental scoring multiplier ${factor.toFixed(3)} (50% shrinkage; ±15% cap). Rebounds unchanged; AST/3PM half-strength. This is not a calibrated model.`;
const keys=[['Points','PTS'],['Rebounds','REB'],['Assists','AST'],['Threes','3PM']];
$('vegasMatchupTable').innerHTML=last.length?'<table><thead><tr><th>Player</th>'+keys.map(([k,n])=>`<th>${n} base</th><th>KP</th><th>Vegas</th><th>Combined</th>`).join('')+'</tr></thead><tbody>'+last.map(r=>'<tr><td>'+esc(r.Player)+'</td>'+keys.map(([k])=>['Baseline','KenPom','Vegas','Combined'].map(p=>'<td>'+fmt(r[p+k])+'</td>').join('')).join('')+'</tr>').join('')+'</tbody></table>':'<p class="note">No player projections available.</p>';
}
function exportCSV(){if(!last.length){alert('Select a matchup with valid pregame odds first.');return}const keys=Object.keys(last[0]);const csv=[keys.join(','),...last.map(r=>keys.map(k=>'"'+String(r[k]??'').replace(/"/g,'""')+'"').join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='acc_four_model_vegas_research.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function init(){if(!$('vegasMatchupPanel'))return;for(const id of ['matchupTeam','matchupOpponent','matchupSearch'])$(id)?.addEventListener(id==='matchupSearch'?'input':'change',()=>setTimeout(render,0));document.addEventListener('acc:kenpom-updated',()=>setTimeout(render,0));document.addEventListener('acc:projections-updated',()=>setTimeout(render,0));$('vegasMatchupExport')?.addEventListener('click',exportCSV);fetch('data/acc_odds.json?cache='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Odds file unavailable');return r.json()}).then(d=>{feed=d;render()}).catch(()=>{$('vegasMatchupStatus').textContent='No published odds snapshot found yet.'});render()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
