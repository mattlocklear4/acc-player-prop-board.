// Independent arithmetic implementation of matchup.js and vegas-matchup.js.
'use strict';
function clamp(x,a,b){return Math.max(a,Math.min(b,x));}
function project(row,team,opp,market){
 const possessions=(team.AdjT+opp.AdjT)/2;
 const pace=clamp(1+.5*(possessions/team.AdjT-1),.90,1.10);
 const dp=clamp(1+.35*(opp.AdjD/105-1),.88,1.12);
 const da=clamp(1+.20*(opp.AdjD/105-1),.92,1.08);
 let factor=null;
 if(market){const implied=(market.total-market.team_spread)/2;
  const expected=possessions*(team.AdjO*opp.AdjD/105)/100;
  factor=clamp(1+.5*(implied/expected-1),.85,1.15);}
 const result={};
 for(const k of ['Points','Rebounds','Assists','Threes']){
  const base=row['Baseline'+k], adj=base*(pace*(k==='Points'?dp:k==='Assists'?da:1));
  const m=factor===null?null:k==='Points'?factor:k==='Assists'||k==='Threes'?1+.5*(factor-1):1;
  result['KenPom'+k]=adj;
  result['Vegas'+k]=m===null?null:base*m;
  result['Combined'+k]=m===null?null:adj*m;
 }
 return result;
}
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>input+=s);
process.stdin.on('end',()=>{const fixtures=JSON.parse(input);console.log(JSON.stringify(fixtures.map(f=>project(f.row,f.team,f.opponent,f.market))))});
