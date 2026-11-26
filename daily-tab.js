'use strict';
(function(){
const el=document.getElementById('dailyResults'),status=document.getElementById('dailyStatus');
if(!el||!status)return;
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const val=x=>{const n=Number(x);return x==null||x===''||!Number.isFinite(n)?'—':n.toFixed(1)};
const pick=(p,...names)=>{for(const n of names)if(p[n]!=null&&p[n]!=='')return p[n];return null};
let profileRows=[],loadSequence=0;
async function load(){
const token=++loadSequence;
try{
const res=await fetch('data/daily_board.json?ts='+Date.now(),{cache:'no-store'});
if(!res.ok)throw Error('Daily projection data has not been published yet.');
const raw=await res.json();
const d=window.ACCAvailability?.scenario(raw)||raw;
if(token!==loadSequence)return;
const nextRows=[];
status.textContent='Slate '+(d.date_eastern||'unknown')+' · '+(d.game_count||0)+' upcoming games · '+(d.projection_player_rows||0)+' player projections · Updated '+new Date(d.generated_at_utc).toLocaleString();
let html='<p class="note">'+esc(d.caution||'Pregame research projections. Verify injuries and minutes before betting.')+'</p><p class="note">Select any player name to compare today’s projection with their current-season game log.</p>';
if(!d.games?.length)html+='<p class="note">No upcoming ACC games in this published snapshot. Check the daily projection workflow for updates.</p>';
for(const g of d.games||[]){
html+='<h3>'+esc(g.away_team)+' at '+esc(g.home_team)+'</h3><p class="note">Tipoff: '+new Date(g.tipoff_utc).toLocaleString()+'</p>';
for(const t of g.teams||[]){
html+='<h4>'+esc(t.team)+'</h4>';
if(!t.players?.length){html+='<p class="note">'+esc(t.reason||'No player projections available')+'</p>';continue;}
const sample=t.players[0];
const teamMinutes=t.players.reduce((sum,p)=>sum+Number(pick(p,'Minutes','minutes','MIN')||0),0);
const normalized=t.players.every(p=>p.MinutesNormalizationStatus==='normalized')&&Math.abs(teamMinutes-200)<1e-6;
html+='<p class="note">Projected team minutes: <strong class="'+(normalized?'positive':'negative')+'">'+val(teamMinutes)+' / 200.0</strong>'+(normalized?' · Regulation rotation normalized':' · Rotation not yet normalized')+(sample.RawTeamMinutes!=null?' · Before normalization: '+val(sample.RawTeamMinutes):'')+'</p>';
if(sample.CurrentTeamGames!=null){html+='<p class="note">Team game coverage: '+esc(sample.CurrentTeamGames)+' merged games · KenPom record: '+esc(sample.KenPomTeamGames??'unknown')+' games'+(sample.DataCoverageWarning?' · WARNING: '+esc(sample.DataCoverageWarning):'')+'</p>';if(sample.DataIssues?.length)html+='<details><summary>Source reconciliation warnings ('+sample.DataIssues.length+')</summary><ul>'+sample.DataIssues.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></details>';}
html+='<div class="tablewrap"><table><thead><tr><th>Player</th><th>GP</th><th>MIN</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th></tr></thead><tbody>';
for(const p of [...t.players].sort((a,b)=>{const am=Number(pick(a,'Minutes','minutes','MIN'));const bm=Number(pick(b,'Minutes','minutes','MIN'));return (Number.isFinite(bm)?bm:-1)-(Number.isFinite(am)?am:-1)})){
const profileIndex=nextRows.push({game:g,team:t,player:p})-1;
html+='<tr><td><button type="button" class="daily-player-link" data-daily-profile="'+profileIndex+'" title="View projection and season game log">'+esc(p.Player??p.player??p.name)+'</button>'+(window.ACCAvailability?.adjustmentLabel(p)?'<small> '+esc(window.ACCAvailability.adjustmentLabel(p))+(p.ScenarioType==='local'?' · Local':'')+'</small>':'')+(p.MinutesRiskFlags?.length?'<small title="'+esc(p.MinutesRiskFlags.join(' · '))+'"> ⚠ Verify minutes</small>':'')+'</td><td title="'+esc('CBBD '+(p.CBBDGP??'—')+' / ESPN '+(p.ESPNGP??'—')+' · Last game '+(p.LatestGameDate??'—'))+'">'+esc(p.CurrentGP??'—')+'</td><td title="'+esc(p.RawMinutes!=null?'Before normalization: '+val(p.RawMinutes)+' min':'Projected minutes')+'">'+val(pick(p,'Minutes','minutes','MIN'))+'</td><td>'+val(pick(p,'KenPomPoints','BaselinePoints','points','PTS'))+'</td><td>'+val(pick(p,'KenPomRebounds','BaselineRebounds','rebounds','REB'))+'</td><td>'+val(pick(p,'KenPomAssists','BaselineAssists','assists','AST'))+'</td><td>'+val(pick(p,'KenPomThrees','BaselineThrees','threes','3PM'))+'</td></tr>';
}
html+='</tbody><tfoot><tr><td><strong>Team total</strong></td><td>—</td><td><strong class="'+(normalized?'positive':'negative')+'">'+val(teamMinutes)+'</strong></td><td colspan="4">Regulation target: 200.0 MIN</td></tr></tfoot></table></div>';
}}
profileRows=nextRows;
el.innerHTML=html;
}catch(e){if(token!==loadSequence)return;profileRows=[];status.textContent='Daily board unavailable: '+e.message;el.innerHTML='<p class="note">The daily automation must successfully publish a board before projections appear here.</p>';}
}
el.addEventListener('click',e=>{
  const button=e.target.closest('button[data-daily-profile]');if(!button)return;
  const row=profileRows[Number(button.dataset.dailyProfile)];if(!row)return;
  if(window.ACCPlayerProfile?.openProjection)window.ACCPlayerProfile.openProjection(row.game,row.team,row.player,button);
  else status.textContent='Player profile unavailable. Refresh the page to reload the board scripts.';
});
document.querySelector('[data-tab="daily"]')?.addEventListener('click',load);
window.addEventListener('acc-availability-changed',load);
load();
})();
