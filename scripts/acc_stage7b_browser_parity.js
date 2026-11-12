/* Executes the actual buildProjectionModel function extracted from app.js in a
   minimal Node VM harness. Read-only; no browser state or Supabase access. */
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.resolve(__dirname,'..');
const asOf=process.argv[2];
if(!/^\d{4}-\d\d-\d\d$/.test(asOf||''))throw Error('Usage: node scripts/acc_stage7b_browser_parity.js YYYY-MM-DD');
function parseCSV(text){const lines=[];let row=[],field='',quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++}else quoted=!quoted;}else if(c===','&&!quoted){row.push(field);field='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);field='';if(row.some(x=>x!==''))lines.push(row);row=[];}else field+=c;}if(field||row.length){row.push(field);lines.push(row)}const head=lines.shift()||[];return lines.map(a=>Object.fromEntries(head.map((k,i)=>[k.replace(/^\ufeff/,''),a[i]??''])))}
function extract(source,name){const start=source.indexOf('async function '+name+'(');if(start<0)throw Error('Cannot find browser function '+name);let brace=source.indexOf('{',start),depth=0,quote=null,escaped=false;for(let i=brace;i<source.length;i++){let c=source[i];if(quote){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c===quote)quote=null;continue;}if(c==='"'||c==="'"||c==='`'){quote=c;continue;}if(c==='{')depth++;else if(c==='}'&&!--depth)return source.slice(start,i+1);}throw Error('Unclosed function')}
const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
const ctx={Map,Set,Number,Math,String,Date,Promise,parseCSV,seasonCache:new Map(),modelLoading:false,modelStatus:'',modelProjections:new Map(),
 $:id=>({value:'',innerHTML:'',textContent:''}),renderProjections:()=>{},renderOdds:()=>{},
 fetch:async url=>{const rel=url.split('?')[0];const file=path.join(root,rel);if(!file.startsWith(root+path.sep))throw Error('Invalid path');const all=parseCSV(fs.readFileSync(file,'utf8'));const filtered=rel.includes('acc_player_games_2027.csv')?all.filter(r=>r.game_date<asOf):all;return {ok:true,text:async()=>JSON.stringify(filtered),json:async()=>filtered};}};
// The actual browser function expects parseCSV(await response.text()).
ctx.parseCSV=value=>value.startsWith('[')?JSON.parse(value):parseCSV(value);
ctx.esc=v=>String(v);
ctx.numberOrNull=v=>{if(v===null||v===undefined||String(v).trim()==='')return null;const n=Number(v);return Number.isFinite(n)?n:null};
vm.createContext(ctx);vm.runInContext(extract(source,'buildProjectionModel'),ctx);ctx.buildProjectionModel().then(()=>{
 if(!ctx.modelStatus.startsWith('Model loaded:'))throw Error(ctx.modelStatus);
 const result=[...ctx.modelProjections.entries()].map(([name,m])=>({Player:name,Team:m.team,Minutes:m.min,CurrentGP:m.currentGP,HistoryGP:m.historyGP,...Object.fromEntries(['Points','Rebounds','Assists','Threes'].map(k=>['Baseline'+k,m[k]]))}));
 process.stdout.write(JSON.stringify({as_of:asOf,players:result}));
}).catch(e=>{console.error(e.stack);process.exitCode=1});
