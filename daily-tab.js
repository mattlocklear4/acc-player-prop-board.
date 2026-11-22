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
html+='<div class="tablewrap"><table><thead><tr><th>Player</th><th>MIN</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th></tr></thead><tbody>';
for(const p of [...t.players].sort((a,b)=>{const am=Number(pick(a,'Minutes','minutes','MIN'));const bm=Number(pick(b,'Minutes','minutes','MIN'));return (Number.isFinite(bm)?bm:-1)-(Number.isFinite(am)?am:-1)})){
html+='<tr><td>'+esc(p.Player??p.player??p.name)+'</td><td>'+val(pick(p,'Minutes','minutes','MIN'))+'</td><td>'+val(pick(p,'KenPomPoints','BaselinePoints','points','PTS'))+'</td><td>'+val(pick(p,'KenPomRebounds','BaselineRebounds','rebounds','REB'))+'</td><td>'+val(pick(p,'KenPomAssists','BaselineAssists','assists','AST'))+'</td><td>'+val(pick(p,'KenPomThrees','BaselineThrees','threes','3PM'))+'</td></tr>';
}
html+='</tbody></table></div>';
}}
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
el.innerHTML=html;
}catch(e){status.textContent='Daily board unavailable: '+e.message;el.innerHTML='<p class="note">The daily automation must successfully publish a board before projections appear here.</p>';}
}
document.querySelector('[data-tab="daily"]')?.addEventListener('click',load);
load();
})();