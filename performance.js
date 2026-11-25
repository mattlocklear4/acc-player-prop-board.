'use strict';
(function(root){
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const numeric=x=>typeof x==='number'&&Number.isFinite(x);
const val=(x,d=2)=>numeric(x)?x.toFixed(d):'—';
const percent=x=>numeric(x)?val(x,1)+'%':'—';
const pnl=x=>numeric(x)?(x>0?'+':'')+val(x)+'u':'—';
const cls=x=>numeric(x)&&x!==0?(x>0?'positive':'negative'):'';
const table=(head,rows)=>'<div class="tablewrap"><table><thead><tr>'+head.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+esc(x)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
const panel=(title,body)=>'<div class="panel"><h3>'+esc(title)+'</h3>'+body+'</div>';
const kpi=(label,value,style='')=>'<div class="perf-kpi"><small>'+esc(label)+'</small><strong class="'+style+'">'+esc(value)+'</strong></div>';
const note=s=>'<p class="note">'+esc(s)+'</p>';
const stats=['Minutes','Points','Rebounds','Assists','Threes'];
function series(byDate){
 let cumulative=0;
 return Object.entries(byDate||{}).filter(([date,m])=>/^\d{4}-\d{2}-\d{2}$/.test(date)&&m.settled>0&&numeric(m.profit_units)).sort(([a],[b])=>a.localeCompare(b)).map(([date,m])=>({date,daily:m.profit_units,cumulative:cumulative+=m.profit_units,settled:m.settled}));
}
function chart(byDate){
 const data=series(byDate);
 if(!data.length)return note('P/L chart will appear once the first exact-edge results are settled. Earlier direction-only results are not mixed in.');
 const W=720,H=245,L=58,R=18,T=16,B=38,lo=Math.min(0,...data.flatMap(d=>[d.daily,d.cumulative])),hi=Math.max(0,...data.flatMap(d=>[d.daily,d.cumulative]));
 const pad=Math.max((hi-lo)*.12,.25),min=lo-pad,max=hi+pad;
 const y=v=>T+(max-v)/(max-min)*(H-T-B),step=(W-L-R)/data.length,x=i=>L+step*(i+.5),bar=Math.min(38,step*.65);
 let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Daily and cumulative hypothetical profit and loss in units">';
 for(let i=0;i<=4;i++){let v=min+(max-min)*i/4;svg+='<line class="axis" opacity=".35" x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'"/><text x="'+(L-6)+'" y="'+(y(v)+4)+'" text-anchor="end">'+val(v,1)+'</text>';}
 svg+='<line class="axis" x1="'+L+'" x2="'+(W-R)+'" y1="'+y(0)+'" y2="'+y(0)+'"/>';
 for(let i=0;i<data.length;i++){const d=data[i];svg+='<rect class="'+(d.daily>=0?'pos':'neg')+'" x="'+(x(i)-bar/2)+'" y="'+Math.min(y(d.daily),y(0))+'" width="'+bar+'" height="'+Math.max(1,Math.abs(y(d.daily)-y(0)))+'"><title>'+esc(d.date+' daily '+pnl(d.daily))+'</title></rect>';if(i===0||i===data.length-1||i%Math.max(1,Math.ceil(data.length/7))===0)svg+='<text x="'+x(i)+'" y="'+(H-12)+'" text-anchor="middle">'+esc(d.date.slice(5))+'</text>';}
 svg+='<polyline class="cumulative" points="'+data.map((d,i)=>x(i)+','+y(d.cumulative)).join(' ')+'"/>';
 data.forEach((d,i)=>{svg+='<circle class="dot" cx="'+x(i)+'" cy="'+y(d.cumulative)+'" r="3"><title>'+esc(d.date+' cumulative '+pnl(d.cumulative))+'</title></circle>';});
 return '<div class="perf-chart"><div class="perf-chart-key"><span>■ Daily P/L (green/red)</span><span style="color:#7aa8ff">● Cumulative P/L</span></div>'+svg+'</svg></div>';
}
function metrics(m){return table(['Stat','Sample','MAE','Bias'],stats.map(s=>[s,m?.[s]?.n??0,val(m?.[s]?.mae),val(m?.[s]?.bias)]));}
function groups(label,obj){
 let entries=Object.entries(obj||{});
 if(label==='Expected ROI tier')entries.sort(([a],[b])=>parseFloat(a)-parseFloat(b));
 if(!entries.length)return '';
 const names={draftkings:'DraftKings',fanduel:'FanDuel',williamhill_us:'Caesars',fanatics:'Fanatics',betonlineag:'BetOnline'};
 return '<h4>'+esc(label)+'</h4>'+table(['Group','Settled','W–L–P','Avg expected ROI','Realized ROI','Net units'],entries.map(([key,s])=>[names[key]||key,s.settled,s.wins+'–'+s.losses+'–'+s.pushes,percent(s.mean_expected_roi_percent),percent(s.roi_percent),pnl(s.profit_units)]));
}
function exactPanel(d){
 if(!d)return panel('Archived Sportsbook Edges',note('Exact-edge grading report is not available. Check the archive and grading workflows.'));
 const m=d.positive_roi||{};
 let html=note('Positive expected ROI only · latest archived pregame odds-backed snapshot per game · hypothetical flat 1-unit results, not actual bets.');
 html+='<div class="perf-grid">'+kpi('Settled selections',m.settled??0)+kpi('W–L–P',(m.wins??0)+'–'+(m.losses??0)+'–'+(m.pushes??0))+kpi('Net P/L',m.settled?pnl(m.profit_units):'—',cls(m.profit_units))+kpi('Expected ROI',percent(m.mean_expected_roi_percent))+kpi('Realized ROI',percent(m.roi_percent),cls(m.roi_percent))+'</div>';
 html+=chart(d.by_date);
 for(const [label,obj] of [['Expected ROI tier',d.by_tier],['Stat category',d.by_market],['Sportsbook',d.by_bookmaker],['Model version',d.by_model_version],['Game date',d.by_date]])html+=groups(label,obj);
 html+=note((d.quotes_priced??0)+' priced sides · '+(m.selections??0)+' positive selections · '+((m.selections??0)-(m.settled??0))+' not settled. Report: '+(d.generated_at_utc||'unknown'));
 html+=note(d.method||'');return panel('Archived Sportsbook Edges · performance',html);
}
function latestPanel(d){
 if(!d)return panel('Latest pregame projection accuracy',note('Exact pregame projection report not yet available.'));
 let html=note((d.players_graded??0)+' player-game projections graded · '+(d.games??0)+' archived games · '+(d.issues||[]).length+' unresolved issues.');
 html+=metrics(d.projection_metrics);
 const versionMap=new Map();
 for(const r of d.projection_rows||[]){const key=r.model_version||'unknown';if(!versionMap.has(key))versionMap.set(key,[]);versionMap.get(key).push(r);}
 if(versionMap.size){
 const rows=[];
 for(const [version,records] of versionMap)for(const stat of stats){const errors=records.map(r=>r.stats?.[stat]?.error).filter(numeric);if(errors.length)rows.push([version,stat,errors.length,val(errors.reduce((a,b)=>a+Math.abs(b),0)/errors.length),val(errors.reduce((a,b)=>a+b,0)/errors.length)]);}
 html+='<h4>Projection accuracy by model version</h4>'+table(['Model version','Stat','Sample','MAE','Bias'],rows)+note('Versions may cover different players and dates; these are not paired comparisons.');
 }
 return panel('Latest pregame projection accuracy',html);
}
function morningPanel(d){
 if(!d)return panel('Original morning projection archive',note('Morning grading report not available.'));
 let html=note((d.players_graded??0)+' of '+(d.projected_players??0)+' player-game projections graded. Original snapshots retained for comparison.')+metrics(d.metrics);
 const recent=(d.days||[]).slice(-14).reverse();
 if(recent.length)html+='<h4>Daily grading coverage</h4>'+table(['Date','Games with finals','Players graded','Projected players','Issues'],recent.map(x=>[x.date,x.games_with_final_logs+' / '+x.games,x.players_graded,x.projected_players,x.issues]));
 return panel('Original morning projection archive',html);
}
function healthPanel(d){
 if(!d)return panel('Pipeline health & automation',note('Health report not available yet. No successful audit is inferred.'));
 return panel('Pipeline health & automation',note(String(d.status||'unknown').toUpperCase()+' · '+(d.failures??0)+' failures · '+(d.warnings??0)+' warnings · audited '+(d.generated_at_utc||'unknown'))+table(['Check','Status','Evidence / gap'],(d.checks||[]).map(c=>[c.code,String(c.level||'').toUpperCase(),c.detail]))+'<p class="note"><a href="https://github.com/mattlocklear4/acc-player-prop-board./actions" target="_blank" rel="noopener">View GitHub Actions</a></p>');
}
function legacyPanel(d){
 if(!d)return '';
 return '<details class="panel performance-history"><summary>Legacy sportsbook evaluation · projection vs line</summary>'+note('Separate historical method; not the positive-ROI edge strategy.')+note((d.settled??0)+' settled · '+(d.wins??0)+' wins / '+(d.losses??0)+' losses / '+(d.pushes??0)+' pushes · '+(d.settled?pnl(d.profit_units):'—')+' · ROI '+percent(d.roi_percent))+table(['Date','Games checked','Quotes','Unmatched player/market','Selections'],(d.days||[]).slice(-14).reverse().map(x=>[x.date,x.events,x.quotes_offered,x.issues?.unmatched_player_or_market??0,x.hypothetical_selections]))+note(d.caution||'')+'</details>';
}
if(typeof module!=='undefined'&&module.exports)module.exports={series,chart,exactPanel,latestPanel,morningPanel,healthPanel,legacyPanel};
if(!root.document)return;
const doc=root.document,el=doc.getElementById('performanceResults');if(!el)return;
let sequence=0;
async function load(){
 const token=++sequence;
 async function get(name){try{const r=await fetch('data/'+name+'.json?ts='+Date.now(),{cache:'no-store'});return r.ok?await r.json():null;}catch{return null;}}
 const [exact,morning,health,legacy]=await Promise.all(['pregame_edge_grading','daily_grading','pipeline_health','daily_odds_evaluation'].map(get));
 if(token!==sequence)return;
 el.innerHTML=exactPanel(exact)+latestPanel(exact)+morningPanel(morning)+healthPanel(health)+legacyPanel(legacy);
}
doc.querySelector('[data-tab="accuracy"]')?.addEventListener('click',load);
doc.getElementById('refreshPerformance')?.addEventListener('click',load);
load();
})(typeof window!=='undefined'?window:globalThis);
