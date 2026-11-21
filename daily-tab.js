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
for(const p of t.players){
html+='<tr><td>'+esc(p.Player??p.player??p.name)+'</td><td>'+val(pick(p,'Minutes','minutes','MIN'))+'</td><td>'+val(pick(p,'KenPomPoints','BaselinePoints','points','PTS'))+'</td><td>'+val(pick(p,'KenPomRebounds','BaselineRebounds','rebounds','REB'))+'</td><td>'+val(pick(p,'KenPomAssists','BaselineAssists','assists','AST'))+'</td><td>'+val(pick(p,'KenPomThrees','BaselineThrees','threes','3PM'))+'</td></tr>';
}
html+='</tbody></table></div>';
}}
el.innerHTML=html;
}catch(e){status.textContent='Daily board unavailable: '+e.message;el.innerHTML='<p class="note">The daily automation must successfully publish a board before projections appear here.</p>';}
}
document.querySelector('[data-tab="daily"]')?.addEventListener('click',load);
load();
})();