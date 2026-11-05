'use strict';
const $=id=>document.getElementById(id);const KEY='accprop_v1';const FIELDS=['player','min','points','or','dr','assists','usage','ortg','orpct','drpct','astpct','fga','threepa'];
const legacyRows=GAMES.flatMap(g=>g.players.map(p=>Object.fromEntries([['game',g.id],['date',g.date],['team',g.id==='miami-florida'?'Miami':g.home],['opponent',g.id==='miami-florida'?'Florida':g.away],['possessions',g.possessions],...FIELDS.map((f,i)=>[f,p[i]])])));
let rows=[...legacyRows], liveGames=[], liveRecords=[], dataMode='historical';
function load(){try{return JSON.parse(localStorage.getItem(KEY))||{}}catch{return {}}}let state=load();state.odds=Array.isArray(state.odds)?state.odds:structuredClone(INITIAL_ODDS);state.projections=state.projections||{};function save(){try{localStorage.setItem(KEY,JSON.stringify(state));$('saveStatus').textContent='Saved on this device'}catch(e){alert('Browser storage unavailable: '+e.message)}}
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function table(data,cols){if(!data.length)return '<p class="empty">No matching rows.</p>';return '<table><thead><tr>'+cols.map(([key,title])=>`<th data-sort="${esc(key)}">${esc(title)} ↕</th>`).join('')+'</tr></thead><tbody>'+data.map(r=>'<tr>'+cols.map(([key])=>`<td>${r[key]===null||r[key]===undefined?'—':esc(r[key])}</td>`).join('')+'</tr>').join('')+'</tbody></table>'}
function sortRows(a,key,reverse){return [...a].sort((x,y)=>{let v=x[key],w=y[key];return (typeof v==='number'&&typeof w==='number'?v-w:String(v??'').localeCompare(String(w??'')))*(reverse?-1:1)})}function attachSort(container,fn){container.querySelectorAll('th[data-sort]').forEach(th=>th.onclick=()=>fn(th.dataset.sort))}
function renderGames(){if(dataMode==='cbbd')return renderLiveGames(); $('gameCards').innerHTML=GAMES.map(g=>`<div class="card"><small>${esc(g.date)} · ${g.possessions} possessions</small><div class="score">${esc(g.home)} ${g.homeScore}<br>${esc(g.away)} ${g.awayScore}</div><p>${g.players.length} tracked ${g.id==='miami-florida'?'Miami':g.home} players</p></div>`).join('');$('gameSelect').innerHTML=GAMES.map(g=>`<option value="${g.id}">${esc(g.home)} vs ${esc(g.away)}</option>`).join('');$('gameSelect').onchange=renderGameTable;renderGameTable()}
let gameSort='min',gameReverse=true;function renderGameTable(){if(dataMode==='cbbd')return renderLiveGameTable();let data=sortRows(rows.filter(r=>r.game===$('gameSelect').value),gameSort,gameReverse);const cols=[['player','Player'],['min','MIN'],['points','PTS'],['or','OREB'],['dr','DREB'],['assists','AST'],['fga','FGA'],['threepa','3PA'],['usage','USG%'],['ortg','ORtg'],['orpct','OR%'],['drpct','DR%'],['astpct','AST%']];$('gameTable').innerHTML=table(data,cols);attachSort($('gameTable'),k=>{gameReverse=gameSort===k?!gameReverse:false;gameSort=k;renderGameTable()})}
let playerSort='min',playerReverse=true;function renderPlayers(){const q=$('playerSearch').value.toLowerCase(),t=$('teamFilter').value;let data=sortRows((dataMode==='cbbd'?seasonPlayerRows():rows).filter(r=>(!t||r.team===t)&&r.player.toLowerCase().includes(q)),playerSort,playerReverse);$('playerTable').innerHTML=table(data,[['team','Team'],['player','Player'],['min','MIN'],['points','PTS'],['or','OREB'],['dr','DREB'],['assists','AST'],['usage','USG%'],['ortg','ORtg'],['orpct','OR%'],['drpct','DR%'],['astpct','AST%'],['fga','FGA'],['threepa','3PA']]);attachSort($('playerTable'),k=>{playerReverse=playerSort===k?!playerReverse:false;playerSort=k;renderPlayers()})}
const projectionNames=[...new Set([...legacyRows.map(r=>r.player),...INITIAL_ODDS.map(o=>o.player)])].sort();function renderProjections(){const q=$('projectionSearch').value.toLowerCase();const names=[...new Set([...projectionNames,...rows.map(r=>r.player),...Object.keys(state.projections)])].filter(n=>n.toLowerCase().includes(q)).sort();$('projectionTable').innerHTML='<table><thead><tr><th>Player</th><th>MIN</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th></tr></thead><tbody>'+names.map(n=>`<tr><td>${esc(n)}</td>${['min','Points','Rebounds','Assists','Threes'].map(k=>`<td><input style="width:82px" type="number" min="0" max="80" step="0.1" data-player="${esc(n)}" data-field="${k}" value="${esc(state.projections[n]?.[k]??'')}" placeholder="—"></td>`).join('')}</tr>`).join('')+'</tbody></table>'; $('projectionTable').querySelectorAll('input').forEach(el=>el.onchange=()=>{let n=el.dataset.player,k=el.dataset.field;state.projections[n]??={};if(el.value.trim()==='')delete state.projections[n][k];else state.projections[n][k]=Number(el.value);save();renderOdds()})}
function normCdf(x){const t=1/(1+.2316419*Math.abs(x));const d=.3989423*Math.exp(-x*x/2);const p=1-d*t*(.3193815+t*(-.3565638+t*(1.781478+t*(-1.821256+t*1.330274))));return x>=0?p:1-p}
function poissonOver(mean,line){if(mean<=0)return 0;const k=Math.floor(line),p0=Math.exp(-mean);let p=p0,sum=p;for(let i=1;i<=k;i++){p*=mean/i;sum+=p}return Math.max(0,Math.min(1,1-sum))}function prob(o){const m=state.projections[o.player]?.[o.market];if(!Number.isFinite(m))return null;return o.market==='Points'?1-normCdf((o.line+.0-m)/5.5):poissonOver(m,o.line)}function american(p){if(p===null||!Number.isFinite(p)||p<=0||p>=1)return '—';return p>=.5?String(Math.round(-100*p/(1-p))):'+'+Math.round(100*(1-p)/p)}function decimal(o){return o>0?1+o/100:1+100/Math.abs(o)}function roi(p,o){return (p*(decimal(o)-1)-(1-p))*100}function actual(o){let r=legacyRows.find(r=>r.player===o.player&&((o.game==='Duke vs Army'&&r.game==='duke-army')||(o.game==='Miami vs Florida'&&r.game==='miami-florida')));if(!r)return null;return o.market==='Points'?r.points:o.market==='Rebounds'?r.or+r.dr:o.market==='Assists'?r.assists:null}
function renderOdds(){const q=$('oddsSearch').value.toLowerCase(),m=$('marketFilter').value,only=$('positiveOnly').checked;let list=state.odds.filter(o=>(!m||o.market===m)&&o.player.toLowerCase().includes(q)).map(o=>{let p=prob(o),a=actual(o),overR=p===null?null:roi(p,o.over),underR=p===null?null:roi(1-p,o.under);return {...o,projection:state.projections[o.player]?.[o.market]??'—',fairOver:american(p),fairUnder:american(p===null?null:1-p),roiOver:overR===null?'—':overR.toFixed(1)+'%',roiUnder:underR===null?'—':underR.toFixed(1)+'%',bestRoi:Math.max(overR??-Infinity,underR??-Infinity),actual:a??'—',result:a===null?'—':a>o.line?'Over':a<o.line?'Under':'Push'}}).filter(o=>!only||o.bestRoi>0).sort((a,b)=>b.bestRoi-a.bestRoi);$('oddsTable').innerHTML=table(list,[['player','Player'],['game','Game'],['market','Market'],['line','Line'],['projection','Projection'],['over','Over odds'],['fairOver','Fair O'],['roiOver','ROI O'],['under','Under odds'],['fairUnder','Fair U'],['roiUnder','ROI U'],['actual','Actual'],['result','Result']])}
function csv(rows){if(!rows.length)return '';const keys=[...new Set(rows.flatMap(Object.keys))];return [keys.join(','),...rows.map(r=>keys.map(k=>'"'+String(r[k]??'').replace(/"/g,'""')+'"').join(','))].join('\r\n')}function download(name,content,type='text/csv'){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500)}
function importTSV(){let lines=$('tsvInput').value.trim().split(/\r?\n/).filter(Boolean),ok=0,bad=[];for(let i=0;i<lines.length;i++){let parts=lines[i].split('\t');if(parts.length<4)parts=lines[i].trim().split(/\s{2,}/);let [player,line,over,under]=parts;if(!player||!Number.isFinite(Number(line))||!Number.isFinite(Number(over))||!Number.isFinite(Number(under))){bad.push(i+1);continue}let item={game:$('importGame').value.trim()||'Unspecified',market:$('importMarket').value,player:player.trim(),line:Number(line),over:Number(over),under:Number(under),source:'BetOnline',date:new Date().toISOString().slice(0,10)};let index=state.odds.findIndex(o=>o.game===item.game&&o.market===item.market&&o.player.toLowerCase()===item.player.toLowerCase()&&o.line===item.line);if(index>=0)state.odds[index]=item;else state.odds.push(item);ok++}save();renderOdds();$('importMessage').textContent=`Imported ${ok} lines${bad.length?'; skipped rows '+bad.join(', '):''}. Saved locally on this device.`}
function wire(){document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.tab).classList.add('active')});updateTeamFilter();$('playerSearch').oninput=renderPlayers;$('teamFilter').onchange=renderPlayers;$('projectionSearch').oninput=renderProjections;$('oddsSearch').oninput=renderOdds;$('marketFilter').onchange=renderOdds;$('positiveOnly').onchange=renderOdds;$('addProjection').onclick=()=>{let name=prompt('Enter player name');if(name?.trim()){state.projections[name.trim()]??={};save();renderProjections()}};$('importTSV').onclick=importTSV;$('clearTSV').onclick=()=>$('tsvInput').value='';$('exportGames').onclick=()=>download('acc_game_logs_2027.csv',csv(dataMode==='cbbd'?liveRecords:rows));$('exportAdvanced').onclick=()=>download('acc_advanced_stats_2027.csv',csv(dataMode==='cbbd'?seasonPlayerRows():rows));$('exportOdds').onclick=()=>download('acc_betonline_lines.csv',csv(state.odds));$('exportProjections').onclick=()=>download('acc_projections.csv',csv(Object.entries(state.projections).map(([player,v])=>({player,...v}))));$('exportAll').onclick=()=>download('acc_prop_board_backup.json',JSON.stringify({version:1,exportedAt:new Date().toISOString(),...state},null,2),'application/json');$('restoreBackup').onchange=async e=>{let f=e.target.files?.[0];if(!f)return;try{let d=JSON.parse(await f.text());if(!Array.isArray(d.odds)||typeof d.projections!=='object'||d.projections===null)throw Error('Invalid backup format');if(!confirm('Replace this device’s saved odds and projections with the backup?'))return;state={odds:d.odds,projections:d.projections};save();renderProjections();renderOdds();alert('Backup restored')}catch(err){alert('Could not restore backup: '+err.message)}e.target.value=''};renderGames();renderPlayers();renderProjections();renderOdds()}
wire();
loadCBBD();


// CBBD player-game database is published by the nightly GitHub Actions collector.
// It is read-only: browser-local projections and sportsbook imports remain untouched.
function parseCSV(input){
 const result=[];let row=[],cell='',quoted=false;
 for(let i=0;i<input.length;i++){
  const c=input[i];
  if(quoted){if(c==='"'&&input[i+1]==='"'){cell+='"';i++}else if(c==='"')quoted=false;else cell+=c}
  else if(c==='"')quoted=true;
  else if(c===','){row.push(cell);cell=''}
  else if(c==='\n'){row.push(cell.replace(/\r$/,''));result.push(row);row=[];cell=''}
  else cell+=c;
 }
 if(cell!==''||row.length){row.push(cell.replace(/\r$/,''));result.push(row)}
 const headers=result.shift()||[];
 return result.filter(r=>r.some(v=>v!=='')).map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]??''])));
}
function numberOrNull(v){return v===''||v==null?null:(Number.isFinite(Number(v))?Number(v):null)}
function formatNumber(v,digits=1){return v==null||!Number.isFinite(v)?'—':Number(v.toFixed(digits))}
function updateTeamFilter(){const current=$('teamFilter').value;const teams=[...new Set(rows.map(r=>r.team))].sort();$('teamFilter').innerHTML='<option value="">All teams</option>'+teams.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join('');if(teams.includes(current))$('teamFilter').value=current}
function seasonPlayerRows(){
 const groups=new Map();
 for(const r of rows){const id=r.team+'|'+(r.athlete_id||r.player);if(!groups.has(id))groups.set(id,[]);groups.get(id).push(r)}
 const totals=['min','points','or','dr','assists','fga','threepa','reb','steals','blocks','turnovers'];
 return [...groups.values()].map(g=>{
  const r=g[0],games=g.length,out={team:r.team,player:r.player,games};
  for(const k of totals)out[k]=formatNumber(g.reduce((s,x)=>s+(Number(x[k])||0),0)/games);
  // Weight game-level rates by minutes played; ignore missing rates, not zero-fill.
  for(const k of ['usage','ortg','orpct','drpct','astpct']){
   const eligible=g.filter(x=>Number.isFinite(x[k])&&Number.isFinite(x.min)&&x.min>0);
   const weight=eligible.reduce((s,x)=>s+x.min,0);
   out[k]=weight?formatNumber(eligible.reduce((s,x)=>s+x[k]*x.min,0)/weight):'—';
  }
  return out;
 });
}
function renderLiveGames(){
 $('gameCards').innerHTML='<div class="card"><small>Automated CBBD feed</small><div class="score">'+liveGames.length+' team-games</div><p>'+liveRecords.length+' player-game rows across '+new Set(liveRecords.map(r=>r.team)).size+' ACC teams. Game scores are not included in this CSV.</p></div>';
 const selected=$('gameSelect').value;
 $('gameSelect').innerHTML=liveGames.map(g=>`<option value="${esc(g.key)}">${esc(g.date)} · ${esc(g.team)} vs ${esc(g.opponent)}</option>`).join('');
 if(liveGames.some(g=>g.key===selected))$('gameSelect').value=selected;
 $('gameSelect').onchange=renderGameTable;renderLiveGameTable();
}
function renderLiveGameTable(){
 const g=liveGames.find(x=>x.key===$('gameSelect').value);
 let data=sortRows(g?rows.filter(r=>r.game===g.key):[],gameSort,gameReverse);
 const cols=[['player','Player'],['min','MIN'],['points','PTS'],['or','OREB'],['dr','DREB'],['assists','AST'],['fga','FGA'],['threepa','3PA'],['usage','USG%'],['ortg','ORtg'],['orpct','OR%'],['drpct','DR%'],['astpct','AST%']];
 $('gameTable').innerHTML=table(data,cols);attachSort($('gameTable'),k=>{gameReverse=gameSort===k?!gameReverse:false;gameSort=k;renderLiveGameTable()});
}
async function loadCBBD(){
 const status=$('collectorState'),note=$('collectorNote'),details=$('collectorDetails');
 status.textContent='Loading CBBD database…';
 try{
  const response=await fetch('data/cbbd/acc_player_games_2027.csv?ts='+Date.now(),{cache:'no-store'});
  if(!response.ok)throw Error('HTTP '+response.status);
  const raw=parseCSV(await response.text());
  if(!raw.length||!raw[0].game_id||!raw[0].athlete_id||!raw[0].player)throw Error('Invalid or empty CBBD player CSV');
  liveRecords=raw;const keys=new Map();
  rows=raw.map(r=>{
   const game=r.game_id+'|'+r.team;
   if(!keys.has(game))keys.set(game,{key:game,date:r.game_date,team:r.team,opponent:r.opponent});
   return {game,date:r.game_date,team:r.team,opponent:r.opponent,athlete_id:r.athlete_id,player:r.player,
    min:numberOrNull(r.minutes),points:numberOrNull(r.points),or:numberOrNull(r.oreb),dr:numberOrNull(r.dreb),
    reb:numberOrNull(r.reb),assists:numberOrNull(r.assists),fga:numberOrNull(r.fga),threepa:numberOrNull(r.three_pa),
    steals:numberOrNull(r.steals),blocks:numberOrNull(r.blocks),turnovers:numberOrNull(r.turnovers),
    usage:numberOrNull(r.usage_pct),ortg:numberOrNull(r.offensive_rating),orpct:numberOrNull(r.offensive_rebound_pct),
    drpct:null,astpct:null};
  });
  liveGames=[...keys.values()].sort((a,b)=>b.date.localeCompare(a.date)||a.team.localeCompare(b.team));
  dataMode='cbbd';updateTeamFilter();renderGames();renderPlayers();renderProjections();
  const count=new Set(rows.map(r=>r.team)).size;
  status.textContent='CBBD connected · '+rows.length+' player-game records';
  note.textContent=count+' ACC teams · '+liveGames.length+' team-games · 2026–27 season · refresh page for latest data';
  details.textContent='Season player table shows per-game averages. Usage and ORtg are minutes-weighted descriptive averages; unavailable DR% and AST% display —. Local projections and odds remain unchanged.';
  $('saveStatus').textContent='CBBD live · edits saved locally';
  const p=$('players').querySelector('.heading p');if(p)p.textContent='Automated 2026–27 season-to-date per-game averages. Filter by team or sort columns.';
  const gamesP=$('games').querySelector('.heading p');if(gamesP)gamesP.textContent='ACC player box scores collected automatically by GitHub Actions.';
  const gamesBadge=$('games').querySelector('.heading .pill');if(gamesBadge)gamesBadge.textContent=liveGames.length+' team-games';
 }catch(e){
  status.textContent='CBBD feed unavailable · historical sample shown';
  note.textContent='Could not load published CSV: '+e.message;
  details.textContent='The original three sample games remain available. Check that data/cbbd/acc_player_games_2027.csv exists on the published branch.';
 }
}
$('refreshCollector').onclick=loadCBBD;
