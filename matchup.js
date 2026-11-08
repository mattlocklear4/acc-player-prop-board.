(()=>{'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalize=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
const aliases={floridastate:'Florida St.',miami:'Miami FL',miamiflorida:'Miami FL',ncstate:'N.C. State',northcarolinastate:'N.C. State',cal:'California',pitt:'Pittsburgh'};
const num=x=>x==null||x===''?NaN:Number(x);
const cap=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const fix=x=>Number.isFinite(x)?x.toFixed(1):'—';
let last=[];
function find(rows,name){const k=normalize(name),alias=aliases[k];return rows.find(r=>r.Team===alias)||rows.find(r=>normalize(r.Team)===k)}
function selectOptions(sel,names){const prior=sel.value;sel.innerHTML='<option value="">Choose '+(sel.id==='matchupTeam'?'ACC team':'opponent')+'</option>'+names.map(n=>'<option value="'+esc(n)+'">'+esc(n)+'</option>').join('');if(names.includes(prior))sel.value=prior}
function render(){if(!$('matchupTeam'))return;const snapshot=window.ACCKenPom?.getSnapshot(),players=window.ACCProjections?.getPlayers()||[];
if(!snapshot){$('matchupStatus').textContent='KenPom snapshot not yet available.';return}
const rows=snapshot.rows,acc=rows.filter(r=>r.Conference==='ACC').map(r=>r.Team).sort(),all=rows.map(r=>r.Team).sort();
selectOptions($('matchupTeam'),acc);selectOptions($('matchupOpponent'),all);
const team=$('matchupTeam').value,opponent=$('matchupOpponent').value;
if(!team||!opponent){$('matchupStatus').textContent='Select an ACC team and its opponent. Snapshot: '+snapshot.date+' ('+snapshot.label+').';$('matchupSummary').textContent='';$('matchupTable').textContent='';last=[];return}
if(team===opponent){$('matchupStatus').textContent='Choose two different teams.';$('matchupTable').textContent='';last=[];return}
const t=find(rows,team),o=find(rows,opponent),ta=num(t?.AdjT),oa=num(o?.AdjT),def=num(o?.AdjD);
if(![ta,oa,def].every(Number.isFinite)||ta<=0){$('matchupStatus').textContent='Missing or invalid adjusted ratings.';return}
const possessions=(ta+oa)/2,pace=cap(1+0.5*(possessions/ta-1),0.90,1.10),defPts=cap(1+0.35*(def/105-1),0.88,1.12),defAst=cap(1+0.20*(def/105-1),0.92,1.08);
const query=$('matchupSearch').value.trim().toLowerCase();last=players.filter(p=>find(rows,p.team)?.Team===team&&p.name.toLowerCase().includes(query)).sort((a,b)=>a.name.localeCompare(b.name)).map(p=>{
 const values={Points:pace*defPts,Rebounds:pace,Assists:pace*defAst,Threes:pace};const result={Player:p.name,Team:p.team,Opponent:opponent,Minutes:p.min,Snapshot:snapshot.date,ProjectedPossessions:possessions,PaceFactor:pace,OpponentDefenseFactor:defPts};
 for(const [k,factor] of Object.entries(values)){result['Baseline'+k]=p[k];result['Adjusted'+k]=Number.isFinite(p[k])?Math.max(0,p[k]*factor):null;result['Delta'+k]=Number.isFinite(p[k])?p[k]*(factor-1):null}return result});
$('matchupStatus').textContent=team+' vs '+opponent+' · '+last.length+' players · KenPom '+snapshot.date+' ('+snapshot.label+')';
$('matchupSummary').textContent='Expected possessions: '+fix(possessions)+' · '+team+' AdjT '+fix(ta)+' · '+opponent+' AdjT '+fix(oa)+' · opponent AdjD '+fix(def)+' · pace multiplier '+pace.toFixed(3)+' · points defense multiplier '+defPts.toFixed(3);
const fields=[['Points','PTS'],['Rebounds','REB'],['Assists','AST'],['Threes','3PM']];$('matchupTable').innerHTML=last.length?'<table><thead><tr><th>Player</th><th>MIN</th>'+fields.map(([k,label])=>'<th>'+label+' base</th><th>'+label+' adj</th><th>Δ</th>').join('')+'</tr></thead><tbody>'+last.map(r=>'<tr><td>'+esc(r.Player)+'</td><td>'+fix(r.Minutes)+'</td>'+fields.map(([k])=>'<td>'+fix(r['Baseline'+k])+'</td><td><strong>'+fix(r['Adjusted'+k])+'</strong></td><td>'+fix(r['Delta'+k])+'</td>').join('')+'</tr>').join('')+'</tbody></table>':'<p class="note">No matching player projections loaded for this team.</p>';
}
function exportCSV(){if(!last.length)return alert('Select a matchup with player projections first.');const keys=Object.keys(last[0]);const cell=x=>'"'+String(x??'').replace(/"/g,'""')+'"';const csv=[keys.join(','),...last.map(r=>keys.map(k=>cell(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='acc_kenpom_matchup_comparison.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function init(){if(!$('matchupTeam'))return;for(const id of ['matchupTeam','matchupOpponent'])$(id).addEventListener('change',render);$('matchupSearch').addEventListener('input',render);$('matchupExport').addEventListener('click',exportCSV);document.addEventListener('acc:kenpom-updated',render);document.addEventListener('acc:projections-updated',render);render()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
