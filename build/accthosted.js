/* ================= Accounts (server) ================= */
let ACC=null,acctView='loading',authMode='signup',authMsg='',syncTimer=null,syncBusy=false,syncAgain=false,syncState='saved',newGameFlag=false,lbData=null,signupGender='';
const BR=()=>(ACC&&ACC.company)||'Savanna';
const BGS=[{id:'hustler',name:'Street hustler',desc:'$1,000 and a big idea. The classic start.',cash:1000,debt:0,rep:50,happy:60},
 {id:'grad',name:'University graduate',desc:'$4,000 saved and a good name, but a $2,500 student loan to repay.',cash:4000,debt:2500,rep:58,happy:62},
 {id:'heir',name:'Family business heir',desc:'$12,000 from the family, and relatives who expect a lot in return.',cash:12000,debt:0,rep:55,happy:52}];
const TOWNS=['Nairobi','Mombasa','Kisumu','Nakuru','Eldoret','Nyeri','Machakos','Kakamega','Thika','Malindi'];
const AVCOL=['var(--green)','var(--brass)','var(--plum)','var(--red)','var(--ink)','var(--muted)'];
const initials=n=>String(n||'').trim().split(/\s+/).slice(0,2).map(w=>w.charAt(0).toUpperCase()).join('')||'?';
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function freshFor(a){const b=BGS.find(x=>x.id===a.bg)||BGS[0],s=fresh();s.g=a.gender||signupGender||'';s.cash=b.cash;s.debt=b.debt;s.rep=b.rep;s.happy=b.happy;s.hist=[Math.max(1,b.cash-b.debt)];
 s.log=[{m:0,n:1,t:'Welcome, '+a.name+'. You are 24, from '+a.town+', with '+fmt(b.cash)+(b.debt?' and a '+fmt(b.debt)+' student loan':'')+'. Time to build '+a.company+' into an empire.',k:'gold'}];s.logN=1;s.logSent=0;return s;}
const GENDER_FS='<fieldset><legend>You are</legend><div class="gopts"><label class="gopt"><input type="radio" name="acc-g" id="acc-g-m" value="m"><span>A man</span></label><label class="gopt"><input type="radio" name="acc-g" id="acc-g-f" value="f"><span>A woman</span></label></div><p class="hint">Used for your story, like who you marry.</p></fieldset>';
function avatar(a,big){return'<span class="av'+(big?' big':'')+'" style="background:'+AVCOL[(a&&a.color)||0]+'">'+esc(initials(a&&a.name))+'</span>';}
async function api(method,path,body){let r;
 try{r=await fetch(path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});}
 catch(e){throw{status:0,message:'Could not reach the game server. Check your connection and try again.'};}
 let d={};try{d=await r.json();}catch(e){}
 if(!r.ok)throw{status:r.status,message:d.error||'Something went wrong on the server. Try again in a moment.'};return d;}
function startWith(user,save){ACC=user;S=save&&save.hist?Object.assign(fresh(),save):freshFor(user);migrate();current=null;closeModal();acctView=null;authMsg='';renderAccts();render();
 if(!save)queueSync(true);
 signupGender='';startEvents();}
function summary(){const nw=netWorth();return{nw,month:S.month,cash:S.cash,rank:TITLES[titleIdx(nw)][1],won:!!S.won,over:!!S.over,newGame:newGameFlag,
 industries:S.inds.length,units:totalUnits(),properties:(S.props||[]).length,teams:Object.keys(S.teams||{}).length,happiness:Math.round(S.happy),reputation:Math.round(S.rep),
 influence:Math.round(S.influence),debt:Math.round(S.debt),married:!!S.spouse,gender:S.g||'',spouse:S.spouse?spW():'',kids:S.kids.length,age:age(),race:S.race?S.race.series:'',foundation:!!S.fdn,cities:(S.pcOpen||[]).length,tab:curTab};}
function queueSync(now){if(!ACC)return;syncState='saving';paintChip();clearTimeout(syncTimer);syncTimer=setTimeout(doSync,now?0:900);}
async function doSync(){if(!ACC)return;if(syncBusy){syncAgain=true;return;}syncBusy=true;
 const evs=S.log.filter(l=>l.n&&l.n>(S.logSent||0)).slice(0,60).reverse(),maxN=evs.reduce((m,l)=>Math.max(m,l.n),S.logSent||0);
 try{await api('PUT','/api/save',{state:S,summary:summary(),events:evs});S.logSent=maxN;newGameFlag=false;syncState='saved';}
 catch(e){if(e.status===401){ACC=null;stopAuto();acctView='auth';authMode='login';authMsg='Your session ended. Log in again to keep playing. Your last moves are safe on this screen until you do.';renderAccts();}
  else{syncState='offline';clearTimeout(syncTimer);syncTimer=setTimeout(doSync,8000);}}
 syncBusy=false;paintChip();if(syncAgain){syncAgain=false;queueSync();}}
function paintChip(){const c=$('acctchip');if(!c)return;c.innerHTML=ACC?avatar(ACC)+'<span><b>'+esc(ACC.name)+'</b><small>'+esc(ACC.company)+' · '+({saved:'saved',saving:'saving…',offline:'offline, retrying'})[syncState]+'</small></span>':'<span><b>Not logged in</b><small>Log in to play</small></span>';}
function authForm(){const su=authMode==='signup';
 let h='<div class="authtabs" role="tablist"><button role="tab" aria-selected="'+su+'" data-a="authmode" data-v="signup">Create account</button><button role="tab" aria-selected="'+(!su)+'" data-a="authmode" data-v="login">Log in</button></div>';
 if(authMsg)h+='<p class="amsg">'+esc(authMsg)+'</p>';
 h+='<form id="acctform" class="aform" novalidate>'+
  '<label for="acc-user">Username</label><input id="acc-user" maxlength="20" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="'+(su?'e.g. wanjiku_k':'')+'" required>'+
  (su?'<p class="hint">3 to 20 characters: letters, numbers, dots and underscores. You log in with this.</p>':'')+
  '<label for="acc-pass">Password</label><input id="acc-pass" type="password" maxlength="128" autocomplete="'+(su?'new-password':'current-password')+'" required>'+(su?'<p class="hint">At least 8 characters.</p>':'');
 if(su)h+='<label for="acc-name">Your name</label><input id="acc-name" maxlength="24" autocomplete="nickname" placeholder="e.g. Wanjiku Kamau" required>'+
  '<label for="acc-company">Your company brand</label><input id="acc-company" maxlength="16" placeholder="e.g. Savanna"><p class="hint">Used across your empire: <i>Brand</i> Racing, <i>Brand</i> Tower Dubai, the <i>Brand</i> Foundation.</p>'+
  '<label for="acc-town">Home town</label><select id="acc-town">'+TOWNS.map(t=>'<option>'+t+'</option>').join('')+'</select>'+GENDER_FS+
  '<fieldset><legend>Starting background</legend>'+BGS.map((b,i)=>'<label class="bgopt"><input type="radio" name="acc-bg" id="acc-bg-'+b.id+'" value="'+b.id+'"'+(i===0?' checked':'')+'><span><b>'+b.name+'</b><span>'+b.desc+'</span></span></label>').join('')+'</fieldset>'+
  '<fieldset><legend>Avatar colour</legend><div class="swatches">'+AVCOL.map((c,i)=>'<label class="sw"><input type="radio" name="acc-col" id="acc-col-'+i+'" value="'+i+'"'+(i===0?' checked':'')+' aria-label="Colour '+(i+1)+'"><span style="background:'+c+'"></span></label>').join('')+'</div></fieldset>';
 return h+'<p class="aerr" id="acc-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="acc-submit">'+(su?'Create account and start':'Log in')+'</button></div></form>';}
function renderAccts(){const el=$('acct');if(!acctView){el.hidden=true;return;}el.hidden=false;let h='<div class="acctbox"><div class="acctbrand">Hustle to a Billion</div>';
 if(acctView==='loading')h+='<h2>Loading…</h2><p class="sub">Connecting to the game server.</p>';
 else if(acctView==='down')h+='<h2>Can\'t connect</h2><p class="sub">'+esc(authMsg)+'</p><div class="chips"><button class="btn primary" data-a="retryboot">Try again</button></div>';
 else if(acctView==='auth')h+='<h2>'+(authMode==='signup'?'Create your account':'Welcome back')+'</h2><p class="sub">'+(authMode==='signup'?'Your account keeps your empire safe, so you can pick it up on any device.':'Log in to carry on building your empire.')+'</p>'+authForm();
 else if(acctView==='menu')h+='<div class="me">'+avatar(ACC,true)+'<div><h2>'+esc(ACC.name)+'</h2><p class="sub">@'+esc(ACC.username)+' · '+esc(ACC.company)+' · '+esc(ACC.town)+'</p></div></div>'+
  '<div class="chips"><button class="btn primary" data-a="acctclose">Back to my game</button><button class="btn" data-a="leaderboard">Leaderboard</button><button class="btn ghost" data-a="logout">Log out</button></div>';
 else if(acctView==='board'){h+='<h2>Leaderboard</h2><p class="sub">Every player on this server, fastest to a billion first.</p>';
  if(!lbData)h+='<p class="sub">Loading…</p>';else if(!lbData.length)h+='<p class="sub">No one is on the board yet.</p>';
  else h+='<ol class="hof">'+lbData.map((a,i)=>'<li><span class="hpos">'+(i+1)+'</span>'+avatar(a)+'<span class="ameta"><b>'+esc(a.name)+'</b><span>'+esc(a.company)+'</span></span><span class="hnum">'+(a.billion_month!=null?'$1B in '+Math.floor(a.billion_month/12)+'y '+(a.billion_month%12)+'m':'Best '+fmt(a.best))+'</span></li>').join('')+'</ol>';
  h+='<div class="chips"><button class="btn ghost" data-a="acctclose">Back to my game</button></div>';}
 el.innerHTML=h+'</div>';
 const f=$('acctform');if(f){f.addEventListener('submit',e=>{e.preventDefault();submitAuth();});const u=$('acc-user');if(u)u.focus();}}
function showErr(msg){const e=$('acc-err');if(e){e.textContent=msg;e.hidden=false;}}
async function submitAuth(){const btn=$('acc-submit'),username=$('acc-user').value.trim().toLowerCase(),password=$('acc-pass').value;
 if(!username||!password)return showErr('Enter your username and password.');
 let body={username,password};
 if(authMode==='signup'){const name=$('acc-name').value.trim();if(!name)return showErr('Enter your name.');if(password.length<8)return showErr('Passwords need at least 8 characters.');
  signupGender=(document.querySelector('input[name="acc-g"]:checked')||{}).value||'';if(!signupGender)return showErr('Choose whether you are a man or a woman.');
  body=Object.assign(body,{name,company:$('acc-company').value.trim()||'Savanna',town:$('acc-town').value,bg:(document.querySelector('input[name="acc-bg"]:checked')||{}).value||'hustler',color:+((document.querySelector('input[name="acc-col"]:checked')||{}).value||0)});}
 btn.disabled=true;btn.textContent=authMode==='signup'?'Creating your account…':'Logging in…';
 try{const d=await api('POST',authMode==='signup'?'/api/signup':'/api/login',body);
  if(ACC===null&&S&&S.month>0&&authMode==='login'&&d.save&&d.save.month<S.month&&S.logN&&S._uid===d.user.id){startWith(d.user,S);}else startWith(d.user,d.save);}
 catch(e){btn.disabled=false;btn.textContent=authMode==='signup'?'Create account and start':'Log in';showErr(e.message);}}
function bootAuth(){acctView='loading';renderAccts();api('GET','/api/me').then(d=>startWith(d.user,d.save)).catch(e=>{if(e.status===401){acctView='auth';authMode='signup';}else{acctView='down';authMsg=e.message;}renderAccts();});}
async function logout(){stopAuto();if(ACC)try{await doSync();}catch(e){}try{await api('POST','/api/logout',{});}catch(e){}ACC=null;S=fresh();current=null;closeModal();acctView='auth';authMode='login';authMsg='';render();renderAccts();}
async function openBoard(){acctView='board';lbData=null;renderAccts();try{lbData=(await api('GET','/api/leaderboard')).players;}catch(e){lbData=[];}renderAccts();}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&ACC&&syncState!=='saved')doSync();});
