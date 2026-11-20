(()=>{'use strict';
const el=document.getElementById('fridayLiveBoard');if(!el)return;
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(n,d=1)=>n!==null&&n!==undefined&&n!==''&&Number.isFinite(Number(n))?Number(n).toFixed(d):'—';
const odds=n=>n!==null&&n!==undefined&&n!==''&&Number.isFinite(Number(n))?(Number(n)>0?'+':'')+n:'—';
const pct=n=>n!==null&&n!==undefined&&n!==''&&Number.isFinite(Number(n))?(100*Number(n)).toFixed(1)+'%':'—';
const state={model:'KenPom',positive:false,team:'',rotation:true};
let data=null;
function render(){
 if(!data){el.textContent='Loading Friday research board…';return}
 const games=data.games||[],rows=data.value_rows||[];
 const projections=[];
 for(const g of games)for(const t of g.teams||[])for(const p of t.players||[])projections.push({game:g,team:t,player:p});
 const reviews=new Map((data.minute_reviews||[]).map(r=>[r.game_id+'|'+r.team+'|'+r.player,r]));
 const matches=rows.filter(r=>(!state.team||r.team===state.team)&&(!state.positive||((r.models||{})[state.model]||{}).over_roi>0||((r.models||{})[state.model]||{}).under_roi>0));
 const shown=projections.filter(r=>!state.team||r.team.team===state.team);
 const teams=[...new Set(projections.map(r=>r.team.team))].sort();
 el.innerHTML='<div class="toolbar"><label>ACC team <select id="fridayTeam"><option value="">All teams</option>'+teams.map(t=>'<option value="'+escape(t)+'" '+(state.team===t?'selected':'')+'>'+escape(t)+'</option>').join('')+'</select></label><label>Model <select id="fridayModel">'+['Baseline','KenPom','Vegas','Combined'].map(m=>'<option '+(state.model===m?'selected':'')+'>'+m+'</option>').join('')+'</select></label><label class="check"><input type="checkbox" id="fridayPositive" '+(state.positive?'checked':'')+'>Positive ROI only</label><label class="check"><input type="checkbox" id="fridayRotation" '+(state.rotation?'checked':'')+'>Rotation-adjusted stats</label></div>'+
 '<p class="note">Friday '+escape(data.date_eastern)+' · '+games.length+' scheduled games · '+projections.length+' projection rows · '+rows.length+' matched DraftKings lines · Schedule: '+escape(data.schedule_status)+' · Odds checked: '+escape(data.odds_generated_at_utc||'Not yet')+'. Research only; rotation-adjusted stats scale production by minutes and do not yet model usage redistribution.</p>'+
 '<h3>Player projections and minutes review</h3><div class="tablewrap"><table><thead><tr><th>Team</th><th>Player</th><th>MIN</th><th>Rotation scenario MIN</th><th>Last 3 MIN</th><th>Usage (last 5)</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th><th>Review</th></tr></thead><tbody>'+
 shown.map(({game,team,player:p})=>{const r=reviews.get(game.game_id+'|'+team.team+'|'+p.Player)||{};const scenario=state.rotation&&p.RotationMinutesScenario!=null;return '<tr><td>'+escape(team.team)+'</td><td>'+escape(p.Player)+'</td><td>'+num(p.Minutes)+'</td><td>'+num(p.RotationMinutesScenario??r.rotation_minutes_scenario)+'</td><td>'+num(r.last3_minutes)+'</td><td>'+num(p.RecentUsagePct??r.usage_pct_last5)+'</td>'+['Points','Rebounds','Assists','Threes'].map(k=>'<td>'+num(scenario?p['Rotation'+state.model+k]:p[state.model+k])+'</td>').join('')+'<td>'+escape(p.AvailabilityStatus||r.availability_status||r.risk||'—')+'</td></tr>'}).join('')+'</tbody></table></div>'+
 '<h3>DraftKings line value comparison</h3>'+(rows.length?'':'<p class="note">No paired DraftKings player props have been returned yet. This section will populate after a successful odds retrieval and board publish.</p>')+
 '<div class="tablewrap"><table><thead><tr><th>Player</th><th>Market</th><th>Line</th><th>O odds</th><th>U odds</th><th>Proj</th><th>O fair %</th><th>U fair %</th><th>O ROI</th><th>U ROI</th></tr></thead><tbody>'+
 matches.map(r=>{const m=(r.models||{})[state.model]||{};return '<tr><td>'+escape(r.player)+'</td><td>'+escape(r.stat)+'</td><td>'+num(r.line)+'</td><td>'+odds(r.over_odds)+'</td><td>'+odds(r.under_odds)+'</td><td>'+num(m.projection)+'</td><td>'+pct(m.over_probability)+'</td><td>'+pct(m.under_probability)+'</td><td>'+pct(m.over_roi)+'</td><td>'+pct(m.under_roi)+'</td></tr>'}).join('')+'</tbody></table></div>'+
 '<p class="note">Fair probabilities use historical player variance when available; threes use an exploratory Poisson model. Blank probabilities mean insufficient data. A positive estimated ROI is not a verified betting edge.</p>';
 el.querySelector('#fridayTeam').onchange=e=>{state.team=e.target.value;render()};
 el.querySelector('#fridayModel').onchange=e=>{state.model=e.target.value;render()};
 el.querySelector('#fridayPositive').onchange=e=>{state.positive=e.target.checked;render()};
 el.querySelector('#fridayRotation').onchange=e=>{state.rotation=e.target.checked;render()};
}
fetch('data/friday_board.json?cache='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Friday board not yet published');return r.json()}).then(x=>{data=x;render()}).catch(e=>{el.textContent=e.message+'. Current Projections and DraftKings Odds tabs remain available.'});
})();
