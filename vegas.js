(function(){
 const target=document.getElementById('vegas-odds-panel');if(!target)return;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 fetch('data/acc_odds.json?cache='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('No odds snapshot published yet');return r.json()}).then(data=>{
  const games=(data.games||[]).slice().sort((a,b)=>a.commence_time.localeCompare(b.commence_time));
  const rows=games.map(g=>{
   const books=(g.bookmakers||[]).filter(b=>['draftkings','fanduel','caesars','betmgm'].includes(b.key));
   const use=books.length?books:g.bookmakers||[];
   const parts=use.map(b=>{
    const t=b.markets?.totals?.outcomes?.find(o=>o.name==='Over')?.point;
    const home=b.markets?.spreads?.outcomes?.find(o=>o.name===g.home_team)?.point;
    return `<div class="vegas-book"><b>${esc(b.title)}</b>: Total ${t==null?'—':esc(t)} · ${esc(g.home_team)} ${home==null?'—':home>0?'+':''}${home==null?'':esc(home)}</div>`;
   }).join('');
   return `<article style="padding:12px;border:1px solid #46536a;border-radius:8px;margin:8px 0"><strong>${esc(g.away_team)} at ${esc(g.home_team)}</strong><div style="opacity:.8;font-size:.85em">${esc(new Date(g.commence_time).toLocaleString())}</div>${parts||'<p>No selected sportsbook lines available yet.</p>'}</article>`;
  }).join('');
  target.innerHTML=`<h3>Vegas pregame odds <small style="font-weight:normal">(research only)</small></h3><p>Latest collection: ${esc(new Date(data.collected_at).toLocaleString())}. Odds are snapshots, not live quotes.</p>${rows||'<p>No upcoming ACC games in the current odds feed.</p>'}`;
 }).catch(e=>{target.innerHTML='<h3>Vegas pregame odds</h3><p>Waiting for the first successful GitHub Actions collection.</p>';console.warn(e)});
})();
