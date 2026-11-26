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
function easternDate(now=new Date()){
 const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const get=t=>parts.find(p=>p.type===t)?.value;
 return get('year')+'-'+get('month')+'-'+get('day');
}
function pendingPanel(d,today=easternDate()){
 const title="Today's saved selections · awaiting grading";
 if(!d)return panel(title,note('Pending archive report has not been published yet. No zero count is inferred.'));
 if(d.date_eastern!==today)return panel(title,note('Last published pending report is for '+d.date_eastern+'. Awaiting the '+today+' archive summary.'));
 if(d.status==='NO_ARCHIVES')return panel(title,note('No pregame archive has been saved for '+today+' yet. This can mean no scheduled ACC games or that the next archive run is still pending.'));
 let html=note(d.date_eastern+' · Saved pregame snapshots; no results included. These are hypothetical selections, not actual wagers.');
 html+='<div class="perf-grid">'+kpi('Pending positive ROI',d.positive_selections??'—')+kpi('Average expected ROI',percent(d.mean_expected_roi_percent),cls(d.mean_expected_roi_percent))+kpi('Player projections saved',d.player_projections??'—')+kpi('Priced quote sides',d.quotes_priced??'—')+kpi('Games archived',d.games??'—')+'</div>';
 if(d.positive_selections===0)html+=note('No positive-ROI selections in the saved quotes. This is not a settled loss or a missing-results error.');
 const tiers=Object.entries(d.by_tier||{}).sort(([a],[b])=>parseFloat(a)-parseFloat(b));
 if(tiers.length)html+='<h4>Pending by expected ROI tier</h4>'+table(['Tier','Selections','Average expected ROI'],tiers.map(([k,v])=>[k,v.selections,percent(v.mean_expected_roi_percent)]));
 const versions=Object.entries(d.by_model_version||{});
 if(versions.length)html+='<h4>Pending model versions</h4>'+table(['Model version','Selections','Average expected ROI'],versions.map(([k,v])=>[k,v.selections,percent(v.mean_expected_roi_percent)]));
 html+=note('Latest capture: '+(d.latest_capture_utc?new Date(d.latest_capture_utc).toLocaleString():'—')+' · '+(d.games_with_priced_quotes??0)+' games with priced quotes · '+(d.issues||[]).length+' archive issues. Settled results are published after the next-day grading run.');
 return panel(title,html);
}
function comparisonPanel(d,pending){
 const m=d?.experimental_comparison?.models||{},p=pending?.date_eastern===easternDate()?pending.experimental_models||{}:{};
 let html=note('Research-only shadow models. v4 remains the production projection and Sportsbook Edges model. Same archived inputs and outcomes; no extra API credits.');
 if(Object.keys(p).length)html+='<h4>Today’s shadow projections awaiting grading</h4>'+table(['Model','Players saved','Priced sides','Positive ROI','Avg expected ROI','Shot fallbacks'],Object.entries(p).map(([k,v])=>[k,v.player_projections,v.quotes_priced,v.positive_selections,percent(v.mean_expected_roi_percent),v.shot_fallbacks]));
 if(!Object.values(m).some(v=>v.paired_players||v.paired_settled_quote_sides))html+=note('Awaiting first matched completed games for the experimental models.');
 for(const [version,v] of Object.entries(m)){
 if(!v.paired_players&&!v.paired_settled_quote_sides)continue;
 html+='<h4>'+esc(version)+'</h4>'+table(['Stat','Paired sample',(v.control_model||'v4')+' MAE','Experiment MAE',(v.control_model||'v4')+' RMSE','Experiment RMSE',(v.control_model||'v4')+' bias','Experiment bias'],Object.entries(v.projection_metrics||{}).map(([k,s])=>[k,s.control.n,val(s.control.mae),val(s.experimental.mae),val(s.control.rmse),val(s.experimental.rmse),val(s.control.bias),val(s.experimental.bias)]));
 html+=table(['Model','Paired quote sides','Brier','Log loss','Positive selections settled','ROI','Net units'],[[v.control_model||'v4 control',v.control_calibration.n,val(v.control_calibration.brier,4),val(v.control_calibration.log_loss,4),v.control_positive_roi.settled,percent(v.control_positive_roi.roi_percent),v.control_positive_roi.settled?pnl(v.control_positive_roi.profit_units):'—'],[version,v.experimental_calibration.n,val(v.experimental_calibration.brier,4),val(v.experimental_calibration.log_loss,4),v.experimental_positive_roi.settled,percent(v.experimental_positive_roi.roi_percent),v.experimental_positive_roi.settled?pnl(v.experimental_positive_roi.profit_units):'—']]);
 }
 return panel('Experimental model comparison',html+note(d?.experimental_comparison?.method||'Same-player prospective evaluation only; no backfilled predictions.'));
}
function exactPanel(d){
 if(!d)return panel('Archived Sportsbook Edges',note('Exact-edge grading report is not available. Check the archive and grading workflows.'));
 const m=d.positive_roi||{};
 let html=note('Positive expected ROI only · latest archived pregame odds-backed snapshot per game · hypothetical flat 1-unit results, not actual bets.');
 if(!m.settled)html+=note('Awaiting first settled results; no wins, losses or realized ROI can be calculated yet.');
 html+='<div class="perf-grid">'+kpi('Settled selections',m.settled??0)+kpi('W–L–P',m.settled?(m.wins??0)+'–'+(m.losses??0)+'–'+(m.pushes??0):'—')+kpi('Net P/L',m.settled?pnl(m.profit_units):'—',cls(m.profit_units))+kpi('Expected ROI',percent(m.mean_expected_roi_percent))+kpi('Realized ROI',percent(m.roi_percent),cls(m.roi_percent))+'</div>';
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
if(typeof module!=='undefined'&&module.exports)module.exports={series,chart,pendingPanel,easternDate,exactPanel,latestPanel,morningPanel,healthPanel,legacyPanel};
if(!root.document)return;
const doc=root.document,el=doc.getElementById('performanceResults');if(!el)return;
let sequence=0;
async function load(){
 const token=++sequence;
 async function get(name){try{const r=await fetch('data/'+name+'.json?ts='+Date.now(),{cache:'no-store'});return r.ok?await r.json():null;}catch{return null;}}
 const [pending,exact,morning,health,legacy]=await Promise.all(['pregame_pending','pregame_edge_grading','daily_grading','pipeline_health','daily_odds_evaluation'].map(get));
 if(token!==sequence)return;
 el.innerHTML=pendingPanel(pending)+comparisonPanel(exact,pending)+exactPanel(exact)+latestPanel(exact)+morningPanel(morning)+healthPanel(health)+legacyPanel(legacy);
}
doc.querySelector('[data-tab="accuracy"]')?.addEventListener('click',load);
doc.getElementById('refreshPerformance')?.addEventListener('click',load);
load();
})(typeof window!=='undefined'?window:globalThis);
