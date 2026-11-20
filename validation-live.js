(()=>{'use strict';const root=document.getElementById('validationLive');if(!root)return;
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
fetch('data/validation_summary.json?cache='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Validation scorecard not published yet');return r.json()}).then(d=>{
 const stats=['Minutes','Points','Rebounds','Assists','Threes'];
 root.innerHTML='<h3>Live baseline · chronological walk-forward validation</h3><p class="note">'+esc(d.status)+' · '+esc(d.player_game_observations)+' player-game observations · Generated '+esc(d.generated_at_utc)+'</p>'+
 '<div class="tablewrap"><table><thead><tr><th>Stat</th><th>Samples</th><th>MAE</th><th>RMSE</th><th>Bias (predicted − actual)</th></tr></thead><tbody>'+
 stats.map(k=>{const m=(d.metrics||{})[k]||{};return '<tr><td>'+esc(k)+'</td><td>'+esc(m.n)+'</td><td>'+esc(m.mae)+'</td><td>'+esc(m.rmse)+'</td><td>'+esc(m.bias)+'</td></tr>'}).join('')+
 '</tbody></table></div><p class="note">'+esc(d.method)+'</p><p class="note"><strong>Not yet betting-validated:</strong> historical pregame odds and matched outcomes are needed for probability calibration, ROI, and closing-line value. No recommendations are qualified from this scorecard alone.</p>';
}).catch(e=>{root.textContent=e.message+'. The next successful scheduled workflow should publish it.'})})();