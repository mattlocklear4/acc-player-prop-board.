'use strict';
(function(){
const el=document.getElementById('dailyResults'),status=document.getElementById('dailyStatus');
if(!el||!status)return;
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const val=x=>{const n=Number(x);return x==null||x===''||!Number.isFinite(n)?'—':n.toFixed(1)};
const pick=(p,...names)=>{for(const n of names)if(p[n]!=null&&p[n]!=='')return p[n];return null};
async function load(){
try{
const res=await fetch('data/daily_board.json?ts='+Date.now(),{cache:'no-store'});
if(!res.ok)throw Error('Daily projection data has not been published yet.');
const d=await res.json();
status.textContent='Slate '+(d.date_eastern||'unknown')+' · '+(d.game_count||0)+' upcoming games · '+(d.projection_player_rows||0)+' player projections · Updated '+new Date(d.generated_at_utc).toLocaleString();
let html='<p class="note">'+esc(d.caution||'Pregame research projections. Verify injuries and minutes before betting.')+'</p>';
if(!d.games?.length)html+='<p class="note">No upcoming ACC games in this published snapshot. Check the daily projection workflow for updates.</p>';
for(const g of d.games||[]){
html+='<h3>'+esc(g.away_team)+' at '+esc(g.home_team)+'</h3><p class="note">Tipoff: '+new Date(g.tipoff_utc).toLocaleString()+'</p>';
for(const t of g.teams||[]){
html+='<h4>'+esc(t.team)+'</h4>';
if(!t.players?.length){html+='<p class="note">'+esc(t.reason||'No player projections available')+'</p>';continue;}
const sample=t.players[0];
if(sample.CurrentTeamGames!=null){html+='<p class="note">Team game coverage: '+esc(sample.CurrentTeamGames)+' merged games · KenPom record: '+esc(sample.KenPomTeamGames??'unknown')+' games'+(sample.DataCoverageWarning?' · WARNING: '+esc(sample.DataCoverageWarning):'')+'</p>';if(sample.DataIssues?.length)html+='<details><summary>Source reconciliation warnings ('+sample.DataIssues.length+')</summary><ul>'+sample.DataIssues.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></details>';}
html+='<div class="tablewrap"><table><thead><tr><th>Player</th><th>GP</th><th>MIN</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th></tr></thead><tbody>';
for(const p of [...t.players].sort((a,b)=>{const am=Number(pick(a,'Minutes','minutes','MIN'));const bm=Number(pick(b,'Minutes','minutes','MIN'));return (Number.isFinite(bm)?bm:-1)-(Number.isFinite(am)?am:-1)})){
html+='<tr><td>'+esc(p.Player??p.player??p.name)+'</td><td title="'+esc('CBBD '+(p.CBBDGP??'—')+' / ESPN '+(p.ESPNGP??'—')+' · Last game '+(p.LatestGameDate??'—'))+'">'+esc(p.CurrentGP??'—')+'</td><td>'+val(pick(p,'Minutes','minutes','MIN'))+'</td><td>'+val(pick(p,'KenPomPoints','BaselinePoints','points','PTS'))+'</td><td>'+val(pick(p,'KenPomRebounds','BaselineRebounds','rebounds','REB'))+'</td><td>'+val(pick(p,'KenPomAssists','BaselineAssists','assists','AST'))+'</td><td>'+val(pick(p,'KenPomThrees','BaselineThrees','threes','3PM'))+'</td></tr>';
}
html+='</tbody></table></div>';
}}
try{
const healthRes=await fetch('data/pipeline_health.json?ts='+Date.now(),{cache:'no-store'});
if(healthRes.ok){
const health=await healthRes.json();
const counts=(health.failures||0)+' failures · '+(health.warnings||0)+' warnings';
html+='<h3>Daily pipeline health: '+esc(String(health.status||'unknown').toUpperCase())+'</h3>';
html+='<p class="note">Last audited '+esc(health.generated_at_utc?new Date(health.generated_at_utc).toLocaleString():'unknown')+' · '+esc(counts)+'. An automated health alert indicates missing data or a failed workflow, not a fabricated result.</p>';
html+='<div class="tablewrap"><table><thead><tr><th>Check</th><th>Status</th><th>Evidence / gap</th></tr></thead><tbody>';
for(const check of health.checks||[])html+='<tr><td>'+esc(check.code)+'</td><td>'+esc(String(check.level||'').toUpperCase())+'</td><td>'+esc(check.detail)+'</td></tr>';
html+='</tbody></table></div>';
}
}catch(_e){/* health report is optional until first scheduled publication */}
try{
const gradeRes=await fetch('data/daily_grading.json?ts='+Date.now(),{cache:'no-store'});
if(gradeRes.ok){
const grade=await gradeRes.json();
html+='<h3>Historical projection accuracy</h3><p class="note">'+esc(grade.players_graded||0)+' player-game projections graded against final ESPN box scores. Missing results are excluded.</p>';
html+='<div class="tablewrap"><table><thead><tr><th>Stat</th><th>Sample</th><th>MAE</th><th>Bias</th></tr></thead><tbody>';
for(const stat of ['Minutes','Points','Rebounds','Assists','Threes']){
const m=grade.metrics?.[stat]||{};
html+='<tr><td>'+esc(stat)+'</td><td>'+esc(m.n??0)+'</td><td>'+val(m.mae)+'</td><td>'+val(m.bias)+'</td></tr>';
}
html+='</tbody></table></div>';
const recent=(grade.days||[]).slice(-7).reverse();
if(recent.length){
html+='<h4>Recent grading coverage</h4><div class="tablewrap"><table><thead><tr><th>Date</th><th>Games with results</th><th>Players graded</th><th>Issues</th></tr></thead><tbody>';
for(const day of recent)html+='<tr><td>'+esc(day.date)+'</td><td>'+esc(day.games_with_final_logs)+' / '+esc(day.games)+'</td><td>'+esc(day.players_graded)+'</td><td>'+esc(day.issues)+'</td></tr>';
html+='</tbody></table></div>';
}
html+='<p class="note">Grading uses archived pregame projections. This does not represent betting ROI.</p>';
}
}catch(_e){/* grading is optional until first publish */}
try{
const roiRes=await fetch('data/daily_odds_evaluation.json?ts='+Date.now(),{cache:'no-store'});
if(roiRes.ok){
const roi=await roiRes.json();
html+='<h3>Legacy sportsbook evaluation (projection vs line)</h3>';
html+='<p class="note">'+esc(roi.snapshots??0)+' saved odds snapshots · '+esc(roi.quotes_offered??0)+' quoted props · '+esc(roi.settled??0)+' settled hypothetical selections.</p>';
if(roi.roi_percent==null){html+='<p class="note">ROI unavailable: no qualifying pregame odds quotes matched to graded final results yet. No odds or results have been estimated.</p>';}
else{html+='<p class="note">Flat $1 research simulation: '+esc(roi.wins)+' wins, '+esc(roi.losses)+' losses, '+esc(roi.pushes)+' pushes · net '+esc(roi.profit_units)+' units · ROI '+esc(roi.roi_percent)+'% (settled stakes only).</p>';}
const days=(roi.days||[]).slice(-7).reverse();
if(days.length){
html+='<h4>Recent odds coverage</h4><div class="tablewrap"><table><thead><tr><th>Date</th><th>Games checked</th><th>Real lines found</th><th>Unmatched player/market</th><th>Hypothetical selections</th></tr></thead><tbody>';
for(const day of days)html+='<tr><td>'+esc(day.date)+'</td><td>'+esc(day.events)+'</td><td>'+esc(day.quotes_offered)+'</td><td>'+esc(day.issues?.unmatched_player_or_market??0)+'</td><td>'+esc(day.hypothetical_selections)+'</td></tr>';
html+='</tbody></table></div>';
}
html+='<p class="note">'+esc(roi.caution||'Research only; no real bets placed.')+'</p>';
}
}catch(_e){/* odds evaluation is optional until first publish */}
try{
const exactRes=await fetch('data/pregame_edge_grading.json?ts='+Date.now(),{cache:'no-store'});
if(exactRes.ok){
const exact=await exactRes.json(),m=exact.positive_roi||{};
html+='<h3>Archived Sportsbook Edges · positive expected ROI</h3><p class="note">Latest genuinely captured pregame snapshot per game. Separate from the legacy direction-only evaluation. '+esc(exact.players_graded??0)+' latest player projections graded · '+esc(exact.quotes_priced??0)+' priced sides · '+esc(m.selections??0)+' positive-ROI selections · '+esc(m.settled??0)+' settled.</p>';
html+='<p class="note">Hypothetical flat 1-unit results: '+esc(m.wins??0)+' wins / '+esc(m.losses??0)+' losses / '+esc(m.pushes??0)+' pushes · '+val(m.profit_units)+' units · realized ROI '+(m.roi_percent==null?'—':val(m.roi_percent)+'%')+'.</p>';
for(const [label,group] of [['Expected ROI tier',exact.by_tier],['Sportsbook',exact.by_bookmaker],['Stat',exact.by_market],['Model version',exact.by_model_version],['Date',exact.by_date]]){
if(!Object.keys(group||{}).length)continue;
html+='<h4>'+esc(label)+'</h4><div class="tablewrap"><table><thead><tr><th>Group</th><th>Settled</th><th>W–L–P</th><th>Mean expected ROI</th><th>Realized ROI</th><th>Units</th></tr></thead><tbody>';
for(const [key,s] of Object.entries(group))html+='<tr><td>'+esc(key)+'</td><td>'+esc(s.settled)+'</td><td>'+esc(s.wins+'–'+s.losses+'–'+s.pushes)+'</td><td>'+val(s.mean_expected_roi_percent)+'</td><td>'+val(s.roi_percent)+'</td><td>'+val(s.profit_units)+'</td></tr>';
html+='</tbody></table></div>';
}
html+='<p class="note">'+esc(exact.method)+'</p>';
}
}catch(_e){/* exact edge grading optional until published */}
el.innerHTML=html;
}catch(e){status.textContent='Daily board unavailable: '+e.message;el.innerHTML='<p class="note">The daily automation must successfully publish a board before projections appear here.</p>';}
}
document.querySelector('[data-tab="daily"]')?.addEventListener('click',load);
load();
})();
