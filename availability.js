'use strict';
(function(root){
const VERSION='v7-manual-availability',KEY='acc-availability-preview-v1';
const num=x=>x==null||x===''?null:Number.isFinite(Number(x))?Number(x):null;
const cols={Points:'points',Rebounds:'reb',Assists:'assists',Threes:'three_pm'};
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const id=(board,g,t,p)=>[board.date_eastern,g.game_id,t.team,String(p.AthleteId)].join('|');
function read(){try{return JSON.parse(root.localStorage.getItem(KEY)||'{}')||{};}catch{return {};}}
function save(board,g,t,p,value){const s=read(),k=id(board,g,t,p);if(value==null)delete s[k];else s[k]=value;root.localStorage.setItem(KEY,JSON.stringify(s));}
function allocation(raw,locked){
 const units=raw.map(()=>0),free=raw.map((v,i)=>i).filter(i=>!locked.has(i)&&raw[i]>0);
 for(const [i,m] of locked){if(!Number.isFinite(m)||m<0||m>40||Math.abs(m*10-Math.round(m*10))>1e-6)throw Error('Minutes must be 0–40 in tenths');units[i]=Math.round(m*10);}
 let remaining=2000-units.reduce((a,b)=>a+b,0),active=free.slice();
 if(remaining<0||active.length*400<remaining)throw Error('Cannot allocate exactly 200 minutes with those overrides');
 const fraction=raw.map(()=>0);
 while(active.length&&remaining>0){const total=active.reduce((s,i)=>s+raw[i],0),capped=active.filter(i=>remaining*raw[i]/total>=400);
 if(!capped.length){for(const i of active){const v=remaining*raw[i]/total;units[i]=Math.floor(v+1e-9);fraction[i]=v-units[i];}break;}
 for(const i of capped){units[i]=400;remaining-=400;}active=active.filter(i=>!capped.includes(i));}
 let residual=2000-units.reduce((a,b)=>a+b,0);const ranked=free.filter(i=>units[i]<400).sort((a,b)=>fraction[b]-fraction[a]||a-b);
 if(residual<0||residual>ranked.length)throw Error('Invalid rotation rounding');for(const i of ranked.slice(0,residual))units[i]++;
 return units.map(v=>v/10);
}
function rate(logs,k){const a=logs.map(g=>[num(g[k]),num(g.minutes)]).filter(([v,m])=>v!==null&&m!==null&&m>0);return a.length?a.reduce((s,x)=>s+x[0],0)/a.reduce((s,x)=>s+x[1],0):null;}
function scenario(board,settings=read(),enabled=true,now=Date.now()){
 if(!enabled)return board;
 return {...board,games:(board.games||[]).map(g=>({...g,teams:(g.teams||[]).map(t=>{
 const ps=t.players||[];if(!ps.length)return t;
 const local=new Map(),published=new Map();
 for(let i=0;i<ps.length;i++){const p=ps[i],v=p.ExperimentalModels?.[VERSION]?.AvailabilityAdjustment;if(v&&v.status!=='redistributed')published.set(i,v);
 const own=settings[id(board,g,t,p)];if(own&&now<Date.parse(g.tipoff_utc))local.set(i,own);}
 if(!local.size){return {...t,players:ps.map(p=>p.ExperimentalModels?.[VERSION]?{...p,...p.ExperimentalModels[VERSION],ControlProjection:p,ScenarioType:'published'}:p)};}
 const locked=new Map([...published,...local]);const mins=allocation(ps.map(p=>Number(p.Minutes)),new Map([...locked].map(([i,e])=>[i,Number(e.minutes)])));
 return {...t,players:ps.map((p,i)=>{const e=locked.get(i),m=mins[i],old=Number(p.Minutes),excluded=new Set(e?.exclude_dates||[]),logs=(p.CurrentSeasonLog||[]).filter(g=>!excluded.has(g.date)).sort((a,b)=>String(b.date).localeCompare(String(a.date)));
 if(e&&excluded.size&&!logs.length)throw Error('At least one production game must remain');
 const x={...p,Minutes:m,OriginalMinutes:old,ModelVersion:'local-availability-preview',ControlProjection:p,ScenarioType:'local',AvailabilityAdjustment:e||{status:'redistributed',reason:'Team rotation reallocated'},ProductionGamesUsed:logs.length};
 for(const [stat,col] of Object.entries(cols)){const key='Baseline'+stat,v=num(p[key]);let base=v!==null&&old>0?v*m/old:v!==null&&m===0?0:null;
 if(e&&excluded.size||old===0&&m>0){const a=rate(logs,col),b=rate(logs.slice(0,5),col);base=a===null?null:m*(.75*a+.25*(b??a));}
 const pace=num(p.PaceFactor),def=num(p.OpponentDefenseFactor);let adj=stat==='Points'?def:stat==='Assists'&&def!==null?clamp(1+(def-1)*.20/.35,.92,1.08):1;
 if(stat==='Assists'&&num(p.BaselineAssists)>0&&num(p.KenPomAssists)!==null&&pace)adj=p.KenPomAssists/p.BaselineAssists/pace;
 x[key]=base;x['KenPom'+stat]=base===null||pace===null||adj===null?null:base*pace*adj;
 }return x;})};
 })}))};
}
// Classify the reason for a changed projection independently from where it was saved.
function adjustmentLabel(p){
 const a=p?.AvailabilityAdjustment;
 if(!p?.ScenarioType||!a)return '';
 if(a.status!=='redistributed')return 'Manual Override';
 if(num(p.Minutes)!==num(p.OriginalMinutes))return 'Rotation Adjusted';
 return '';
}
const api={VERSION,id,read,save,allocation,scenario,adjustmentLabel};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ACCAvailability=api;
})(typeof window!=='undefined'?window:globalThis);
