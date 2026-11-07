(()=>{'use strict';
const $=id=>document.getElementById(id);
const fields=[
 ['team','Team'],['games','GP'],['pace','Pace'],['teamStats_rating','Off Rtg'],['opponentStats_rating','Def Rtg'],
 ['teamStats_fourFactors_effectiveFieldGoalPct','eFG%'],['opponentStats_fourFactors_effectiveFieldGoalPct','Opp eFG%'],
 ['teamStats_fourFactors_offensiveReboundPct','ORB%'],['opponentStats_fourFactors_offensiveReboundPct','Opp ORB%'],
 ['teamStats_fourFactors_turnoverRatio','TOV%'],['teamStats_threePointFieldGoals_attempted','3PA'],['teamStats_threePointFieldGoals_pct','3P%']
];
let rows=[],sortKey='team',sortAsc=true,loadedSeason='';
const n=x=>{const v=Number(x);return x==null||String(x).trim()===''||!Number.isFinite(v)?null:v};
const fmt=(k,v)=>{if(k==='team')return String(v??'');let x=n(v);if(x===null)return '—';if(k==='games'||k==='teamStats_threePointFieldGoals_attempted')return x.toFixed(0);return x.toFixed(1)};
const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function parseCSV(csv){
 const result=[],line=[];let field='',quoted=false;
 for(let i=0;i<csv.length;i++){let c=csv[i];
  if(c==='"'){if(quoted&&csv[i+1]==='"'){field+='"';i++}else quoted=!quoted}
  else if(c===','&&!quoted){line.push(field);field=''}
  else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&csv[i+1]==='\n')i++;line.push(field);if(line.some(v=>v!==''))result.push([...line]);line.length=0;field=''}
  else field+=c;
 }
 if(field||line.length){line.push(field);result.push(line)}
 const head=result.shift()||[];
 return result.map(r=>Object.fromEntries(head.map((h,i)=>[h,r[i]??''])));
}
function renderTable(){
 const q=$('teamStatsSearch').value.toLowerCase().trim();
 const filtered=rows.filter(r=>r.team.toLowerCase().includes(q));
 filtered.sort((a,b)=>{const x=a[sortKey],y=b[sortKey],nx=n(x),ny=n(y);
 let c=(sortKey==='team'||nx===null||ny===null)?String(x).localeCompare(String(y)):(nx-ny);
 return sortAsc?c:-c});
 $('teamStatsTable').innerHTML='<table class="team-stats-table"><thead><tr>'+fields.map(([k,label])=>'<th><button type="button" data-sort="'+k+'">'+label+(sortKey===k?(sortAsc?' ▲':' ▼'):'')+'</button></th>').join('')+'</tr></thead><tbody>'+
 filtered.map(r=>'<tr>'+fields.map(([k])=>'<td>'+escapeHtml(fmt(k,r[k]))+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
 $('teamStatsTable').querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>{const key=b.dataset.sort;if(key===sortKey)sortAsc=!sortAsc;else{sortKey=key;sortAsc=key==='team'}renderTable()});
}
function renderMatchup(){
 const a=rows.find(r=>r.team===$('matchupA').value),b=rows.find(r=>r.team===$('matchupB').value);
 if(!a||!b){$('matchupCards').textContent='Select two teams.';return}
 const paceA=n(a.pace),paceB=n(b.pace),pace=paceA!==null&&paceB!==null?(paceA+paceB)/2:null;
 const metric=(label,x,y)=>'<div class="team-compare-row"><span>'+escapeHtml(label)+'</span><strong>'+escapeHtml(x)+'</strong><strong>'+escapeHtml(y)+'</strong></div>';
 $('matchupCards').innerHTML='<div class="team-matchup-pace"><span>Neutral estimated game pace</span><strong>'+(pace===null?'—':pace.toFixed(1)+' possessions')+'</strong></div>'+
 '<div class="team-compare-row team-compare-head"><span>Metric</span><strong>'+escapeHtml(a.team)+'</strong><strong>'+escapeHtml(b.team)+'</strong></div>'+
 metric('Games',fmt('games',a.games),fmt('games',b.games))+
 metric('Season pace',fmt('pace',a.pace),fmt('pace',b.pace))+
 metric('Offensive rating',fmt('teamStats_rating',a.teamStats_rating),fmt('teamStats_rating',b.teamStats_rating))+
 metric('Defensive rating',fmt('opponentStats_rating',a.opponentStats_rating),fmt('opponentStats_rating',b.opponentStats_rating))+
 metric('Effective FG%',fmt('teamStats_fourFactors_effectiveFieldGoalPct',a.teamStats_fourFactors_effectiveFieldGoalPct),fmt('teamStats_fourFactors_effectiveFieldGoalPct',b.teamStats_fourFactors_effectiveFieldGoalPct))+
 metric('Offensive rebound %',fmt('teamStats_fourFactors_offensiveReboundPct',a.teamStats_fourFactors_offensiveReboundPct),fmt('teamStats_fourFactors_offensiveReboundPct',b.teamStats_fourFactors_offensiveReboundPct));
}
async function load(){
 const season=$('teamStatsSeason').value;
 $('teamStatsStatus').textContent='Loading '+season+' team data…';
 try{
  const response=await fetch('data/cbbd/acc_team_stats_'+season+'.csv?ts='+Date.now(),{cache:'no-store'});
  if(!response.ok)throw Error('CSV unavailable (HTTP '+response.status+')');
  const result=parseCSV(await response.text());
  if(result.length!==18||result.some(r=>!r.team))throw Error('Expected 18 ACC teams; got '+result.length);
  rows=result;loadedSeason=season;
  const oldA=$('matchupA').value,oldB=$('matchupB').value;
  const opts=rows.map(r=>'<option value="'+escapeHtml(r.team)+'">'+escapeHtml(r.team)+'</option>').join('');
  $('matchupA').innerHTML=opts;$('matchupB').innerHTML=opts;
  $('matchupA').value=rows.some(r=>r.team===oldA)?oldA:(rows.find(r=>r.team==='Duke')?.team||rows[0].team);
  $('matchupB').value=rows.some(r=>r.team===oldB)?oldB:(rows.find(r=>r.team==='North Carolina')?.team||rows[1].team);
  const games=rows.map(r=>n(r.games)).filter(x=>x!==null);
  $('teamStatsStatus').textContent='Loaded '+rows.length+' ACC teams · '+(games.length?'Games played per team: '+Math.min(...games)+'–'+Math.max(...games):'Games unavailable')+' · Season '+season+'. Data refreshes from GitHub CSV.';
  renderTable();renderMatchup();
 }catch(e){rows=[];$('teamStatsStatus').textContent='Team statistics unavailable: '+e.message+'. Verify the CSV exists in data/cbbd/ on GitHub.';$('teamStatsTable').textContent='';$('matchupCards').textContent=''}
}
function init(){
 if(!$('teamStatsSeason'))return;
 $('teamStatsSeason').onchange=load;$('teamStatsRefresh').onclick=load;
 $('teamStatsSearch').oninput=renderTable;
 $('matchupA').onchange=renderMatchup;$('matchupB').onchange=renderMatchup;
 load();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();