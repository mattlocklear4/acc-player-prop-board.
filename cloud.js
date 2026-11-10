(()=>{'use strict';
const $=id=>document.getElementById(id);
const URL='https://srwpfmzoqorhrswoupws.supabase.co';
const KEY='sb_publishable_tCPpzrB9-idPSy0wxswoYw_xe4Ri6n0';
const status=s=>{if($('accCloudStatus'))$('accCloudStatus').textContent=s};
const lockStatus=s=>{if($('accCloudLockStatus'))$('accCloudLockStatus').textContent=s};
let client=null,user=null,busy=false;
function numeric(v){if(v==null||String(v).trim()===''||String(v).trim()==='-99.00')return null;const n=Number(v);return Number.isFinite(n)?n:null}
async function sync(){
 if(!user||busy)return;
 busy=true;
 try{
  const list=window.ACCKenPom?.getSnapshots()||[];
  const pending=list.filter(s=>!s.cloudSnapshotId&&s.importedAt&&Number.isFinite(Date.parse(s.importedAt)));
  if(!pending.length){status('Signed in · all timestamped local KenPom imports are archived.');return}
  let saved=0;
  for(const s of pending){
   const importedAt=new Date(s.importedAt).toISOString();
   const {data:head,error:he}=await client.from('acc_kenpom_snapshots').insert({
    season:Number(s.season)||2027,source:'manual_kenpom_tsv',source_as_of:null,
    team_count:s.rows.length,notes:'User date label: '+s.date+' · '+s.label+'; imported at '+importedAt
   }).select('id').single();
   if(he)throw he;
   const ratings=s.rows.map(r=>({
    snapshot_id:head.id,team:r.Team,conference:r.Conference,
    wins:numeric(r.Wins),losses:numeric(r.Losses),
    adj_em:numeric(r.AdjEM),adj_o:numeric(r.AdjO),adj_d:numeric(r.AdjD),
    adj_t:numeric(r.AdjT),sos_adj_em:numeric(r.SOS_AdjEM),
    sos_adj_o:numeric(r.SOS_AdjO),sos_adj_d:numeric(r.SOS_AdjD)
   }));
   const {error:re}=await client.from('acc_kenpom_team_ratings').insert(ratings);
   if(re)throw new Error('Snapshot header saved, but team ratings failed: '+re.message+'; contact us before retrying this import');
   window.ACCKenPom.markCloudSaved(s.id,head.id);saved++;
  }
  status('Signed in · '+saved+' new KenPom snapshot(s) archived.');
 }catch(e){status('Cloud sync failed: '+e.message+' · Local snapshots remain saved.');}
 finally{busy=false}
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
  const {error}=await client.auth.signInWithOtp({email,options:{emailRedirectTo:location.origin+location.pathname,shouldCreateUser:true}});
  status(error?'Sign-in failed: '+error.message:'Check your email for the Supabase sign-in link.');
 };
 $('accCloudSignOut').onclick=async()=>{await client.auth.signOut();user=null;status('Signed out. Local snapshots are preserved.')};
 $('accCloudSync').onclick=sync;
 $('accCloudLock').onclick=lock;
 document.addEventListener('acc:kenpom-imported',()=>{if(user)sync();else status('Import saved locally. Sign in to archive it in Supabase.')});
 client.auth.onAuthStateChange(()=>{setTimeout(update,0)});
 await update();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();