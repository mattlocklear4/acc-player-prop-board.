(()=>{'use strict';
const $=id=>document.getElementById(id);
const URL='https://srwpfmzoqorhrswoupws.supabase.co';
const KEY='sb_publishable_tCPpzrB9-idPSy0wxswoYw_xe4Ri6n0';
const status=s=>{if($('accCloudStatus'))$('accCloudStatus').textContent=s};
const lockStatus=s=>{if($('accCloudLockStatus'))$('accCloudLockStatus').textContent=s};
let client=null,user=null,busy=false;
function numeric(v){if(v==null||String(v).trim()===''||String(v).trim()==='-99.00')return null;const n=Number(v);return Number.isFinite(n)?n:null}
let rerun=false;
async function latestCloud(){
 const {data,error}=await client.from('acc_kenpom_snapshots').select('id,imported_at,notes,team_count').eq('season',2027).order('imported_at',{ascending:false}).limit(1).maybeSingle();
 if(error)throw error;
 if(!data)return null;
 const {count,error:ce}=await client.from('acc_kenpom_team_ratings').select('id',{count:'exact',head:true}).eq('snapshot_id',data.id);
 if(ce)throw ce;
 if(count!==data.team_count)throw Error('Latest cloud snapshot is incomplete');
 return data;
}
function notes(s){return 'User date label: '+s.date+' · '+s.label+'; imported at '+new Date(s.importedAt).toISOString()}
async function showFreshness(head){
 const el=$('accCloudFreshness');if(!el)return;
 const label=head?.notes?.match(/User date label: (\d{4}-\d{2}-\d{2})/)?.[1]||'date not labeled';
 el.textContent=head?'Cloud ratings: '+label+' · '+head.team_count+' teams verified · saved '+new Date(head.imported_at).toLocaleString():'No cloud ratings found for this account.';
 try{
  const response=await fetch('data/daily_board.json',{cache:'no-store'});if(!response.ok)throw Error('Board unavailable');
  const board=await response.json();const used=board.kenpom_source;
  if(used?.snapshot_id===head?.id&&head)el.textContent+=' · current projections use this snapshot.';
  else if(head)el.textContent+=' · projection refresh pending; checks run every 15 minutes (GitHub scheduling can delay).';
 }catch(e){el.textContent+=' · could not verify projection status.'}
}
async function sync(){
 if(!user)return;
 if(busy){rerun=true;return}
 busy=true;
 try{
  let head=await latestCloud();
  const list=window.ACCKenPom?.getSnapshots()||[];
  const pending=list.filter(s=>!s.cloudSnapshotId&&s.importedAt&&Number.isFinite(Date.parse(s.importedAt))).sort((a,b)=>Date.parse(a.importedAt)-Date.parse(b.importedAt));
  let saved=0,skipped=0;
  for(const s of pending){
   if(!user)break;
   if(s.rows.length!==365){skipped++;continue}
   // Avoid making old restored backups the active snapshot. Keep them locally.
   if(head&&Date.parse(s.importedAt)<Date.parse(head.imported_at)&&notes(s)!==head.notes){skipped++;continue}
   const ratings=s.rows.map(r=>({team:r.Team,conference:r.Conference,wins:numeric(r.Wins),losses:numeric(r.Losses),adj_em:numeric(r.AdjEM),adj_o:numeric(r.AdjO),adj_d:numeric(r.AdjD),adj_t:numeric(r.AdjT),sos_adj_em:numeric(r.SOS_AdjEM),sos_adj_o:numeric(r.SOS_AdjO),sos_adj_d:numeric(r.SOS_AdjD)}));
   const {data:id,error}=await client.rpc('acc_upload_kenpom_v1',{p_notes:notes(s),p_rows:ratings});
   if(error)throw error;
   const {count,error:ce}=await client.from('acc_kenpom_team_ratings').select('id',{count:'exact',head:true}).eq('snapshot_id',id);
   if(ce||count!==ratings.length)throw Error(ce?.message||'Cloud count verification failed');
   window.ACCKenPom.markCloudSaved(s.id,id);saved++;
   head=await latestCloud();
  }
  if(user){status('Connected · '+(saved?saved+' new snapshot(s) verified.':'Cloud checked; no new eligible imports.')+(skipped?' '+skipped+' older/incomplete local snapshot(s) retained.':'') );await showFreshness(head)}
 }catch(e){status('Cloud sync failed: '+e.message+' · Local snapshots remain saved.');}
 finally{busy=false;if(rerun){rerun=false;setTimeout(sync,0)}}
}
async function lock(){
 try{
  if(!user)throw Error('Sign in before locking projections');
  const gameId=$('accCloudGameId').value.trim(),time=$('accCloudTipoff').value;
  if(!gameId||!time)throw Error('Enter a unique game ID and scheduled tipoff');
  const tipoff=new Date(time);
  if(!Number.isFinite(tipoff.getTime())||tipoff.getTime()<=Date.now())throw Error('Tipoff must be in the future');
  const snap=window.ACCKenPom?.getSnapshot();
  if(!snap||!snap.cloudSnapshotId)throw Error('Select a KenPom snapshot already archived to cloud');
  if(!snap.importedAt||Date.parse(snap.importedAt)>Date.now()||Date.parse(snap.importedAt)>=tipoff.getTime())throw Error('KenPom snapshot must have a valid import timestamp before tipoff');
  const selection=window.ACCMatchup?.getSelection(),rows=window.ACCMatchup?.getRows()||[];
  if(!selection?.team||!selection?.opponent||!rows.length)throw Error('Select a matchup with loaded players first');
  if($('matchupSearch')?.value.trim())throw Error('Clear the matchup player search to lock the full roster');
  if(!confirm('Lock '+rows.length+' player projections for '+selection.team+' vs '+selection.opponent+'? Confirm game ID and scheduled tipoff are correct.'))return;
  lockStatus('Saving '+rows.length+' projections…');
  const payload=rows.map(r=>({
   game_id:gameId,game_start_at:tipoff.toISOString(),season:2027,team:r.Team,opponent:r.Opponent,
   player_id:r.Player,player_name:r.Player,model_version:'v1.9.1-kenpom-experimental',
   kenpom_snapshot_id:snap.cloudSnapshotId,
   baseline:{MIN:r.Minutes,PTS:r.BaselinePoints,REB:r.BaselineRebounds,AST:r.BaselineAssists,'3PM':r.BaselineThrees},
   adjusted:{MIN:r.Minutes,PTS:r.AdjustedPoints,REB:r.AdjustedRebounds,AST:r.AdjustedAssists,'3PM':r.AdjustedThrees},
   assumptions:{snapshot_imported_at:snap.importedAt,snapshot_label_date:snap.date,
    projected_possessions:r.ProjectedPossessions,pace_factor:r.PaceFactor,
    opponent_defense_factor:r.OpponentDefenseFactor,model:'experimental; not used in odds'}
  }));
  const {error}=await client.from('acc_pregame_projections').insert(payload);
  if(error)throw error;
  lockStatus('Saved '+rows.length+' immutable pregame projections for '+gameId+'.');
 }catch(e){lockStatus('Not saved: '+e.message)}
}
async function init(){
 if(!window.supabase?.createClient){status('Supabase library unavailable. Check internet access and reload.');return}
 client=window.supabase.createClient(URL,KEY,{auth:{detectSessionInUrl:true,persistSession:true,autoRefreshToken:true}});
 const update=async()=>{const {data:{user:u},error}=await client.auth.getUser();user=error?null:u;
  status(user?'Signed in as '+user.email+' · checking pending snapshots…':'Not signed in · imports remain saved locally.');
  if(user)await sync();
 };
 $('accCloudSignIn').onclick=async()=>{
  const email=$('accCloudEmail').value.trim();
  if(!email.includes('@')){status('Enter a valid email address');return}
  status('Sending sign-in link…');
  const {error}=await client.auth.signInWithOtp({email,options:{emailRedirectTo:location.origin+location.pathname,shouldCreateUser:false}});
  status(error?'Sign-in failed: '+error.message:'Check your email for the Supabase sign-in link.');
 };
 $('accCloudSignOut').onclick=async()=>{await client.auth.signOut();user=null;status('Signed out. Local snapshots are preserved.');if($('accCloudFreshness'))$('accCloudFreshness').textContent='Sign in to check cloud ratings.'};
 $('accCloudSync').onclick=sync;
 if($('accCloudLock'))$('accCloudLock').onclick=lock;
 document.addEventListener('acc:kenpom-imported',()=>{if(user)sync();else status('Import saved locally. Sign in to archive it in Supabase.')});
 client.auth.onAuthStateChange(()=>{setTimeout(update,0)});
 document.addEventListener('acc:kenpom-ready',()=>{if(user)sync()});
 window.addEventListener('online',()=>{if(user)sync();else update()});
 window.addEventListener('focus',()=>{if(user)sync()});
 await update();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();