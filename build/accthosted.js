/* ================= Accounts (server) ================= */
let ACC=null,acctView='loading',authMode='signup',authMsg='',syncTimer=null,syncBusy=false,syncAgain=false,syncState='saved',newGameFlag=false,lbData=null,signupGender='',pendingLife=null,livesData=null,livesCache=null,seasonCache=null,lbTab='season-country',signupRegion='',signupCur='USD',resetToken='',emailSkip=false,forgotDone='',BILL=null,billSkew=0,payMsg='',payBusy=false,payRef='',payCancelled=false,payTries=0,payDone=null,refCode='',refInfo=null,inviteData=null,inviteMsg='';
const BR=()=>(ACC&&ACC.company)||'Savanna';
const BGS=[{id:'hustler',name:'Street hustler',desc:'$1,000 and a big idea. The classic start.',cash:1000,debt:0,rep:50,happy:60},
 {id:'grad',name:'University graduate',desc:'$4,000 saved and a good name, but a $2,500 student loan to repay.',cash:4000,debt:2500,rep:58,happy:62},
 {id:'heir',name:'Family business heir',desc:'$12,000 from the family, and relatives who expect a lot in return.',cash:12000,debt:0,rep:55,happy:52}];
const TOWNS=['Nairobi','Mombasa','Kisumu','Nakuru','Eldoret','Nyeri','Machakos','Kakamega','Thika','Malindi'];
const AVCOL=['var(--green)','var(--brass)','var(--plum)','var(--red)','var(--ink)','var(--muted)'];
const initials=n=>String(n||'').trim().split(/\s+/).slice(0,2).map(w=>w.charAt(0).toUpperCase()).join('')||'?';
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function freshFor(a){const b=BGS.find(x=>x.id===a.bg)||BGS[0],s=fresh();s.g=a.gender||signupGender||'';s.region=signupRegion||a.region||detectCountry();s.cur=signupCur||'USD';useRegion(s.region);const S0=S;S=s;s.cash=b.cash;s.debt=b.debt;s.rep=b.rep;s.happy=b.happy;s.hist=[Math.max(1,b.cash-b.debt)];
 s.log=[{m:0,n:1,t:'Welcome, '+a.name+'. You are 24, from '+a.town+', with '+fmt(b.cash)+(b.debt?' and a '+fmt(b.debt)+' student loan':'')+'. Time to build '+a.company+' into an empire.',k:'gold'}];s.logN=1;s.logSent=0;S=S0;return s;}
const GENDER_FS='<fieldset><legend>You are</legend><div class="gopts"><label class="gopt"><input type="radio" name="acc-g" id="acc-g-m" value="m"><span>A man</span></label><label class="gopt"><input type="radio" name="acc-g" id="acc-g-f" value="f"><span>A woman</span></label></div><p class="hint">Used for your story, like who you marry.</p></fieldset>';
function avatar(a,big){return'<span class="av'+(big?' big':'')+'" style="background:'+AVCOL[(a&&a.color)||0]+'">'+esc(initials(a&&a.name))+'</span>';}
async function api(method,path,body){let r;
 try{r=await fetch(path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});}
 catch(e){throw{status:0,message:navigator.onLine===false?'You\'re offline. Connect to the internet to keep playing. Your empire is saved safely on the server.':'Could not reach the game server. Check your connection and try again.'};}
 let d={};try{d=await r.json();}catch(e){}
 if(!r.ok)throw{status:r.status,message:d.error||'Something went wrong on the server. Try again in a moment.',data:d};return d;}
function pastLives(){return livesCache;}
function recordLife(l){pendingLife=l||null;if(l&&livesCache){l.n=livesCache.reduce((m,x)=>Math.max(m,x.n||0),0)+1;livesCache=[l].concat(livesCache);}}
async function loadLives(){try{livesCache=(await api('GET','/api/lives')).lives;}catch(e){livesCache=null;}}
async function showLives(){if(!ACC)return;loadSeason();stopAuto();closeModal();acctView='lives';livesData=null;renderAccts();window.scrollTo(0,0);try{livesData=(await api('GET','/api/lives')).lives;livesCache=livesData;}catch(e){livesData=[];}if(acctView==='lives')renderAccts();}
function startWith(user,save,bill){setBill(bill);if(refCode&&authMode==='signup'){refCode='';refInfo=null;try{localStorage.removeItem('hs-ref');}catch(e){}}livesCache=null;loadLives();setTimeout(loadSeason,1200);ACC=user;S=save&&save.hist?Object.assign(fresh(),save):freshFor(user);migrate();current=null;closeModal();acctView=null;authMsg='';renderAccts();render();
 if(!save)queueSync(true);
 signupGender='';signupRegion='';signupCur='USD';if(!user.email&&!emailSkip){acctView='addemail';authMsg='';renderAccts();}startEvents();
 paintPass();if(payRef)confirmPay();else if(passLocked())openPay();}
function summary(){const nw=netWorth();return{nw,month:S.month,cash:S.cash,rank:TITLES[titleIdx(nw)][1],won:!!S.won,over:!!S.over,newGame:newGameFlag,prev:newGameFlag?pendingLife:null,
 industries:S.inds.length,units:totalUnits(),properties:(S.props||[]).length,teams:Object.keys(S.teams||{}).length,happiness:Math.round(S.happy),reputation:Math.round(S.rep),
 influence:Math.round(S.influence),debt:Math.round(S.debt),married:!!S.spouse,health:Math.round(S.health||0),died:!!S.died,streak:(S.daily&&S.daily.last)?S.daily.streak:0,gender:S.g||'',gen:S.headstart?2:(S.gnum||1),season:S.sea?{id:S.sea.id,pts:S.sea.pts}:null,region:S.region||'',currency:S.cur||'USD',spouse:S.spouse?spW():'',kids:S.kids.length,age:age(),race:S.race?S.race.series:'',foundation:!!S.fdn,cities:(S.pcOpen||[]).length,tab:curTab};}
function queueSync(now){if(!ACC)return;syncState='saving';paintChip();clearTimeout(syncTimer);syncTimer=setTimeout(doSync,now?0:900);}
async function doSync(){if(!ACC)return;if(syncBusy){syncAgain=true;return;}syncBusy=true;
 const evs=S.log.filter(l=>l.n&&l.n>(S.logSent||0)).slice(0,60).reverse(),maxN=evs.reduce((m,l)=>Math.max(m,l.n),S.logSent||0);
 const evq=(S.evq||[]).slice(0,200);
 try{await api('PUT','/api/save',{state:S,summary:summary(),events:evs,evlog:evq});S.logSent=maxN;S.evq=(S.evq||[]).slice(evq.length);if(newGameFlag)pendingLife=null;newGameFlag=false;syncState='saved';}
 catch(e){if(e.status===402){setBill(e.data&&e.data.bill);syncState='locked';stopAuto();openPay();}
  else if(e.status===401){ACC=null;stopAuto();acctView='auth';authMode='login';authMsg='Your session ended. Log in again to keep playing. Your last moves are safe on this screen until you do.';renderAccts();}
  else{syncState='offline';clearTimeout(syncTimer);syncTimer=setTimeout(doSync,8000);}}
 syncBusy=false;paintChip();if(syncAgain){syncAgain=false;queueSync();}}
function paintChip(){const c=$('acctchip');if(!c)return;c.innerHTML=ACC?avatar(ACC)+'<span><b>'+esc(ACC.name)+'</b><small>'+esc(ACC.company)+' · '+({saved:'saved',saving:'saving…',offline:'offline, retrying',locked:'needs the Hustle Pass'})[syncState]+'</small></span>':'<span><b>Not logged in</b><small>Log in to play</small></span>';}
function authForm(){const su=authMode==='signup';const inv=su&&refInfo?'<p class="invbanner"><span aria-hidden="true">🎁</span><span><b>'+esc(refInfo.name)+'</b> invited you to Hustlempires'+(refInfo.trialDays?'. You get <b>'+refInfo.trialDays+' days free</b> to build your empire.':'.')+'</span></p>':'';
 let h=inv+'<div class="authtabs" role="tablist"><button role="tab" aria-selected="'+su+'" data-a="authmode" data-v="signup">Create account</button><button role="tab" aria-selected="'+(!su)+'" data-a="authmode" data-v="login">Log in</button></div>';
 if(authMsg)h+='<p class="amsg">'+esc(authMsg)+'</p>';
 h+='<form id="acctform" class="aform" novalidate>'+
  '<label for="acc-user">Username</label><input id="acc-user" maxlength="20" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="'+(su?'e.g. wanjiku_k':'')+'" required>'+
  (su?'<p class="hint">3 to 20 characters: letters, numbers, dots and underscores. You log in with this.</p>':'')+
  '<label for="acc-pass">Password</label><input id="acc-pass" type="password" maxlength="128" autocomplete="'+(su?'new-password':'current-password')+'" required>'+(su?'<p class="hint">At least 8 characters.</p>':'')+
  (su?'<label for="acc-email">Email</label><input id="acc-email" type="email" maxlength="120" autocomplete="email" inputmode="email" autocapitalize="none" spellcheck="false" required><p class="hint">Only used to reset your password if you forget it.</p>':'');
 if(su)h+='<label for="acc-name">Your name</label><input id="acc-name" maxlength="24" autocomplete="nickname" placeholder="e.g. Wanjiku Kamau" required>'+
  '<label for="acc-company">Your company brand</label><input id="acc-company" maxlength="16" placeholder="e.g. Savanna"><p class="hint">Used across your empire: <i>Brand</i> Racing, <i>Brand</i> Tower Dubai, the <i>Brand</i> Foundation.</p>'+
  '<label for="acc-town">Home town</label><select id="acc-town">'+(countryRow(detectCountry())||{towns:TOWNS}).towns.map(t=>'<option>'+esc(t)+'</option>').join('')+'</select>'+GENDER_FS+regionFormHTML(detectCountry(),'USD')+
  '<fieldset><legend>Starting background</legend>'+BGS.map((b,i)=>'<label class="bgopt"><input type="radio" name="acc-bg" id="acc-bg-'+b.id+'" value="'+b.id+'"'+(i===0?' checked':'')+'><span><b>'+b.name+'</b><span>'+dollars(b.desc)+'</span></span></label>').join('')+'</fieldset>'+
  '<fieldset><legend>Avatar colour</legend><div class="swatches">'+AVCOL.map((c,i)=>'<label class="sw"><input type="radio" name="acc-col" id="acc-col-'+i+'" value="'+i+'"'+(i===0?' checked':'')+' aria-label="Colour '+(i+1)+'"><span style="background:'+c+'"></span></label>').join('')+'</div></fieldset>';
 return h+'<p class="aerr" id="acc-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="acc-submit">'+(su?'Create account and start':'Log in')+'</button>'+(su?'':'<button type="button" class="btn ghost" data-a="forgotview">Forgot your password?</button>')+'</div></form>';}
function renderAccts(){const el=$('acct');if(!acctView){el.hidden=true;return;}el.hidden=false;let h='<div class="acctbox"><div class="acctbrand">Hustlempires</div>';
 if(acctView==='loading')h+='<h2>Loading…</h2><p class="sub">Connecting to the game server.</p>';
 else if(acctView==='down')h+='<h2>Can\'t connect</h2><p class="sub">'+esc(authMsg)+'</p><div class="chips"><button class="btn primary" data-a="retryboot">Try again</button></div>';
 else if(acctView==='auth')h+='<h2>'+(authMode==='signup'?'Create your account':'Welcome back')+'</h2><p class="sub">'+(authMode==='signup'?'Your account keeps your empire safe, so you can pick it up on any device.':'Log in to carry on building your empire.')+'</p>'+authForm();
 else if(acctView==='menu')h+='<div class="me">'+avatar(ACC,true)+'<div><h2>'+esc(ACC.name)+'</h2><p class="sub">@'+esc(ACC.username)+' · '+esc(ACC.company)+' · '+esc(ACC.town)+'</p></div></div>'+
  '<div class="chips"><button class="btn primary" data-a="acctclose">Back to my game</button><button class="btn" data-a="leaderboard">Leaderboard</button>'+'<button class="btn" data-a="lives">Past lives</button>'+(canInstall()?'<button class="btn" data-a="installapp">Install app</button>':'')+'<button class="btn ghost" data-a="logout">Log out</button></div>'+
  passMenuHTML()+'<h3>Invite friends</h3><p class="sub">'+inviteRuleLine()+'</p><div class="chips"><button class="btn" data-a="invite">Invite friends</button></div><h3>Email for password resets</h3><p class="sub">'+(ACC.email?'Resets go to <b>'+esc(ACC.email)+'</b>.':'<b>No email yet.</b> Add one so you can reset your password if you forget it.')+'</p>'+emailForm(ACC.email?'Change email':'Save email')+'<div class="regionbox">'+regionMenuHTML()+'</div>';
 else if(acctView==='installios')h+='<h2>Install the app</h2><p class="sub">Put the game on your home screen. It opens full-screen, like any other app.</p><ol class="iossteps"><li>At the bottom of Safari, tap the <b>Share</b> button (the square with an arrow pointing up).</li><li>Scroll down and tap <b>Add to Home Screen</b>.</li><li>Tap <b>Add</b>. The game\'s icon appears on your home screen.</li></ol><div class="chips"><button class="btn primary" data-a="acctclose">Got it</button></div>';
 else if(acctView==='addemail')h+='<h2>Add your email</h2><p class="sub">If you ever forget your password, we\'ll send a reset link here. We don\'t use it for anything else.</p>'+emailForm('Save email',true);
 else if(acctView==='forgot')h+='<h2>Forgot your password?</h2>'+(forgotDone?'<p class="amsg">'+esc(forgotDone)+'</p><div class="chips"><button class="btn primary" data-a="backlogin">Back to log in</button></div>':
  '<p class="sub">Enter your username or the email on your account. We\'ll email you a link to choose a new password.</p><form id="forgotform" class="aform" novalidate><label for="fg-who">Username or email</label><input id="fg-who" maxlength="120" autocomplete="username" autocapitalize="none" spellcheck="false" required>'+
  '<p class="aerr" id="acc-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="fg-submit">Email me a reset link</button><button type="button" class="btn ghost" data-a="backlogin">Back to log in</button></div></form>');
 else if(acctView==='reset')h+='<h2>Choose a new password</h2><p class="sub">Pick something you haven\'t used here before. You\'ll be logged in straight away.</p><form id="resetform" class="aform" novalidate>'+
  '<label for="rs-pass">New password</label><input id="rs-pass" type="password" maxlength="128" autocomplete="new-password" required><p class="hint">At least 8 characters.</p>'+
  '<label for="rs-pass2">Type it again</label><input id="rs-pass2" type="password" maxlength="128" autocomplete="new-password" required>'+
  '<p class="aerr" id="acc-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="rs-submit">Save new password</button><button type="button" class="btn ghost" data-a="forgotview">Get a new link</button></div></form>';
 else if(acctView==='pay'||acctView==='gift'||acctView==='payleft'||acctView==='paid')h+=payViewHTML();
 else if(acctView==='invite')h+=inviteHTML();
 else if(acctView==='lives'){h+='<h2>Your legacy</h2><p class="sub">Your family, your achievements and every empire you have built.</p>'+(livesData===null?'<p class="sub">Loading…</p>':legacyHTML()+trophiesHTML()+livesHTML(livesData,livesData.length))+'<div class="chips">'+(S&&S.over&&S.died&&S.kids.length?'<button class="btn primary" data-a="heirpick">Choose your heir</button>':'')+(S&&S.over?'<button class="btn primary" data-a="reset">Start a new life</button><button class="btn ghost" data-a="acctclose">Back to my game</button>':'<button class="btn primary" data-a="acctclose">Back to my game</button>')+'</div>';}
 else if(acctView==='board'){const cn=(countryRow(S.region||'')||{name:'your country'}).name;
  h+='<h2>Leaderboard</h2><div class="authtabs" role="tablist" style="grid-template-columns:1fr 1fr 1fr"><button role="tab" aria-selected="'+(lbTab==='season-country')+'" data-a="boardtab" data-v="season-country">'+esc(cn)+'</button><button role="tab" aria-selected="'+(lbTab==='season-world')+'" data-a="boardtab" data-v="season-world">World</button><button role="tab" aria-selected="'+(lbTab==='alltime')+'" data-a="boardtab" data-v="alltime">All time</button></div>'+
   '<p class="sub">'+(lbTab==='alltime'?'Founders only, fastest to a billion first.':seasonName(seasonId())+'. Points come from daily bonuses, weekly challenges, new ranks, achievements and big milestones. The board resets on the 1st of every month.')+'</p>';
  if(!lbData)h+='<p class="sub">Loading…</p>';else if(!lbData.length)h+='<p class="sub">No one is on the board yet.</p>';
  else h+='<ol class="hof">'+lbData.map((a,i)=>'<li><span class="hpos">'+(i+1)+'</span>'+avatar(a)+'<span class="ameta"><b>'+esc(a.name)+'</b><span>'+esc(a.company)+(lbTab!=='alltime'&&a.region?' · '+esc((countryRow(a.region)||{name:a.region}).name):'')+'</span></span><span class="hnum">'+(lbTab!=='alltime'?Number(a.pts).toLocaleString('en-US')+' pts':a.billion_month!=null?fmt(1e9)+' in '+Math.floor(a.billion_month/12)+'y '+(a.billion_month%12)+'m':'Best '+fmt(a.best))+'</span></li>').join('')+'</ol>';
  h+='<div class="chips"><button class="btn ghost" data-a="acctclose">Back to my game</button></div>';}
 el.innerHTML=h+'</div>';
 const f=$('acctform');if(f){f.addEventListener('submit',e=>{e.preventDefault();submitAuth();});const u=$('acc-user');if(u)u.focus();wireRegionForm();}
 wireRegionMenu();
 const ff=$('forgotform');if(ff){ff.addEventListener('submit',e=>{e.preventDefault();submitForgot();});$('fg-who').focus();}
 const rf=$('resetform');if(rf){rf.addEventListener('submit',e=>{e.preventDefault();submitReset();});$('rs-pass').focus();}
 const ef=$('emailform');if(ef){ef.addEventListener('submit',e=>{e.preventDefault();submitEmail();});if(acctView==='addemail')$('em-email').focus();}}
function emailForm(label,later){return'<form id="emailform" class="aform" novalidate><label for="em-email">Email</label><input id="em-email" type="email" maxlength="120" autocomplete="email" inputmode="email" autocapitalize="none" spellcheck="false" value="'+esc((ACC&&ACC.email)||'')+'" required>'+
 '<label for="em-pass">Your current password</label><input id="em-pass" type="password" maxlength="128" autocomplete="current-password" required><p class="hint">So nobody else can change it.</p>'+
 '<p class="aerr" id="acc-err" hidden></p><p class="amsg" id="em-ok" hidden></p><div class="chips"><button type="submit" class="btn primary" id="em-submit">'+label+'</button>'+(later?'<button type="button" class="btn ghost" data-a="skipemail">Not now</button>':'')+'</div></form>';}
async function submitEmail(){const email=$('em-email').value.trim(),password=$('em-pass').value,btn=$('em-submit');
 if(!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email))return showErr('Enter a valid email address.');if(!password)return showErr('Enter your current password.');
 btn.disabled=true;try{const d=await api('POST','/api/email',{email,password});ACC=d.user;if(acctView==='addemail'){acctView=null;renderAccts();return;}renderAccts();const ok=$('em-ok');if(ok){ok.textContent='Saved. Password resets will go to '+ACC.email+'.';ok.hidden=false;}}
 catch(e){btn.disabled=false;showErr(e.message);}}
async function submitForgot(){const who=$('fg-who').value.trim(),btn=$('fg-submit');if(!who)return showErr('Enter your username or email.');
 btn.disabled=true;btn.textContent='Sending…';try{const d=await api('POST','/api/forgot',{who});forgotDone=d.message;renderAccts();}
 catch(e){btn.disabled=false;btn.textContent='Email me a reset link';showErr(e.message);}}
async function submitReset(){const a=$('rs-pass').value,b=$('rs-pass2').value,btn=$('rs-submit');
 if(a.length<8)return showErr('Passwords need at least 8 characters.');if(a!==b)return showErr('The two passwords don\'t match.');
 btn.disabled=true;btn.textContent='Saving…';try{const d=await api('POST','/api/reset',{token:resetToken,password:a});resetToken='';startWith(d.user,d.save,d.bill);}
 catch(e){btn.disabled=false;btn.textContent='Save new password';showErr(e.message);}}
function showErr(msg){const e=$('acc-err');if(e){e.textContent=msg;e.hidden=false;}}
async function submitAuth(){const btn=$('acc-submit'),username=$('acc-user').value.trim().toLowerCase(),password=$('acc-pass').value;
 if(!username||!password)return showErr('Enter your username and password.');
 let body={username,password};
 if(authMode==='signup'){const name=$('acc-name').value.trim();if(!name)return showErr('Enter your name.');if(password.length<8)return showErr('Passwords need at least 8 characters.');
  const email=$('acc-email').value.trim();if(!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email))return showErr('Enter a valid email address. It\'s how you reset your password.');
  signupGender=(document.querySelector('input[name="acc-g"]:checked')||{}).value||'';if(!signupGender)return showErr('Choose whether you are a man or a woman.');
  signupRegion=($('acc-region')||{}).value||detectCountry();signupCur=(document.querySelector('input[name="acc-cur"]:checked')||{}).value||'USD';
  body=Object.assign(body,{ref:refCode||undefined,email,name,company:$('acc-company').value.trim()||'Savanna',town:$('acc-town').value,bg:(document.querySelector('input[name="acc-bg"]:checked')||{}).value||'hustler',color:+((document.querySelector('input[name="acc-col"]:checked')||{}).value||0)});}
 btn.disabled=true;btn.textContent=authMode==='signup'?'Creating your account…':'Logging in…';
 try{const d=await api('POST',authMode==='signup'?'/api/signup':'/api/login',body);
  if(ACC===null&&S&&S.month>0&&authMode==='login'&&d.save&&d.save.month<S.month&&S.logN&&S._uid===d.user.id){startWith(d.user,S,d.bill);}else startWith(d.user,d.save,d.bill);}
 catch(e){btn.disabled=false;btn.textContent=authMode==='signup'?'Create account and start':'Log in';showErr(e.message);}}
function bootAuth(){try{const u=new URL(location.href),t=u.searchParams.get('reset'),pr=u.searchParams.get('paid');if(t){resetToken=t;u.searchParams.delete('reset');}
 if(pr){payRef=pr.slice(0,60);payCancelled=u.searchParams.get('cancelled')==='1';payTries=0;['paid','cancelled','OrderTrackingId','OrderMerchantReference','OrderNotificationType'].forEach(k=>u.searchParams.delete(k));}
 const rf=(u.searchParams.get('ref')||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,12);if(rf){refCode=rf;u.searchParams.delete('ref');try{localStorage.setItem('hs-ref',rf);}catch(e){}}
 if(!refCode)try{refCode=localStorage.getItem('hs-ref')||'';}catch(e){}
 if(t||pr||rf)history.replaceState(null,'',u.pathname+u.search+u.hash);}catch(e){}
 if(refCode)api('GET','/api/invite/check?code='+encodeURIComponent(refCode)).then(d=>{refInfo=d&&d.ok?d:null;if(acctView==='auth')renderAccts();}).catch(()=>{});
 api('GET','/api/tuning').then(t=>{if(t&&typeof t==='object')TUNE=Object.assign({freq:1,gap:2,w:{},cat:{}},t);}).catch(()=>{});
 if(resetToken){acctView='reset';authMsg='';renderAccts();return;}
 acctView='loading';renderAccts();api('GET','/api/me').then(d=>startWith(d.user,d.save,d.bill)).catch(e=>{if(e.status===401){acctView='auth';authMode='signup';}else{acctView='down';authMsg=e.message;}renderAccts();});}
async function logout(){stopAuto();BILL=null;paintPass();if(ACC)try{await doSync();}catch(e){}try{await api('POST','/api/logout',{});}catch(e){}ACC=null;S=fresh();current=null;closeModal();acctView='auth';authMode='login';authMsg='';render();renderAccts();}
async function openBoard(tab){if(tab)lbTab=tab;stopAuto();closeModal();acctView='board';lbData=null;renderAccts();
 try{if(lbTab==='alltime')lbData=(await api('GET','/api/leaderboard')).players;else{const d=await api('GET','/api/season?scope='+(lbTab==='season-world'?'world':'country')+'&region='+encodeURIComponent(S.region||''));seasonCache=d;lbData=d.top;}}catch(e){lbData=[];}renderAccts();}
async function loadSeason(){try{seasonCache=await api('GET','/api/season?scope=country&region='+encodeURIComponent(S.region||''));render();}catch(e){}}
function seasonRankLine(){const d=seasonCache,s=S.sea;if(!d||!s||d.season!==s.id||!d.me)return' <span class="rk">Play this month to get on the board</span> <button class="btn small ghost" data-a="leaderboard">Leaderboard</button> <button class="btn small ghost" data-a="invite">Invite friends</button>';
 const c=countryRow(d.me.region)||{name:d.me.region};return' <span class="rk">#'+d.me.rankRegion+' of '+d.me.playersRegion+' in '+esc(c.name)+' · #'+d.me.rank+' of '+d.me.players+' worldwide</span> <button class="btn small ghost" data-a="leaderboard">Leaderboard</button> <button class="btn small ghost" data-a="invite">Invite friends</button>';}
function trophiesHTML(){const d=seasonCache;if(!d||!d.history||!d.history.length)return'';
 return'<h3 class="achh">Season trophies</h3><ul class="achs">'+d.history.map(h=>{const c=countryRow(h.region)||{name:h.region||'World'},top=h.rankRegion<=3?['🥇','🥈','🥉'][h.rankRegion-1]+' ':'';
  return'<li class="ach got"><b>'+top+seasonName(h.season)+'</b><span>'+h.pts.toLocaleString('en-US')+' points · #'+h.rankRegion+' of '+h.playersRegion+' in '+esc(c.name)+' · #'+h.rank+' of '+h.players+' worldwide</span></li>';}).join('')+'</ul>';}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&ACC&&syncState!=='saved')doSync();});

/* ================= New version available: prompt to update ================= */
const APP_VER='__APP_VER__';let updShown=false;
function checkVersion(){fetch('/api/version',{cache:'no-store',credentials:'same-origin'}).then(r=>r.ok?r.json():null).then(d=>{if(d&&d.v&&d.v!==APP_VER)showUpdate();}).catch(()=>{});}
function showUpdate(){if(updShown)return;updShown=true;const b=document.createElement('div');b.className='updbar';b.setAttribute('role','status');
 b.innerHTML='<span><b>A new update is ready</b><small>Get the latest features and fixes. Your empire is saved.</small></span><button class="btn primary small" data-a="appupdate">Update now</button>';document.body.appendChild(b);}
async function appUpdate(){const b=document.querySelector('.updbar button');if(b){b.disabled=true;b.textContent='Updating…';}stopAuto();
 try{if(ACC)await doSync();}catch(e){}
 try{if(navigator.serviceWorker){const r=await navigator.serviceWorker.getRegistration();if(r)await r.update();}}catch(e){}
 location.reload();}
setTimeout(checkVersion,15000);setInterval(checkVersion,5*60*1000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')checkVersion();});

/* ================= Install as an app ================= */
let installEvt=null;
const isStandalone=()=>(window.matchMedia&&matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true;
const isIOS=/iphone|ipad|ipod/i.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const canInstall=()=>!isStandalone()&&(!!installEvt||isIOS);
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installEvt=e;paintInstall();});
window.addEventListener('appinstalled',()=>{installEvt=null;paintInstall();});
function paintInstall(){let b=$('installbtn');const show=canInstall();
 if(!b&&show){const t=$('tourbtn');if(!t)return;b=document.createElement('button');b.className='btn ghost';b.id='installbtn';b.dataset.a='installapp';b.textContent='Install app';t.parentNode.insertBefore(b,t.nextSibling);}
 if(b)b.hidden=!show;}
async function installApp(){if(installEvt){const e=installEvt;e.prompt();try{await e.userChoice;}catch(x){}installEvt=null;paintInstall();}
 else if(isIOS){stopAuto();acctView='installios';renderAccts();}}

/* ================= Hustle Pass (free trial, then pay through Pesapal) ================= */
function setBill(b){BILL=b&&b.on?b:null;if(BILL&&BILL.now)billSkew=BILL.now-Date.now()/1000;paintPass();}
const nowS=()=>Date.now()/1000+billSkew;
const passLocked=()=>!!(BILL&&BILL.state==='locked');
function leftText(sec){sec=Math.max(0,sec);const d=Math.floor(sec/86400),h=Math.floor(sec%86400/3600),m=Math.max(1,Math.ceil(sec%3600/60));
 return d?d+' day'+(d>1?'s':'')+(h?' '+h+' h':''):h?h+' h'+(h<6&&m<60?' '+(m%60)+' min':''):m+' min';}
const dateText=ts=>new Date(ts*1000).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
function kesText(k){return'KSh '+Number(k).toLocaleString('en-US');}
function kesLocal(k){const ke=countryRow('KE');if(!ke||typeof R==='undefined'||!R||R.cur==='KES')return'';const usd=k/ke.rate;
 if(R.cur==='USD'||!R.rate)return'about $'+(usd<10?usd.toFixed(2):Math.round(usd));const v=usd*R.rate;return'about '+R.sym+(/[A-Za-z.]$/.test(R.sym)?' ':'')+(v<100?v.toFixed(v<10?2:0):Math.round(v).toLocaleString('en-US'));}
function paintPass(){let b=$('passbar');const st=BILL&&BILL.state,left=BILL&&BILL.until?BILL.until-nowS():0;
 const show=ACC&&BILL&&(st==='trial'||st==='bonus'||st==='locked'||(st==='paid'&&left<3*86400));
 if(!b&&show){const c=$('acctchip');if(!c)return;b=document.createElement('button');b.id='passbar';b.className='passbar';b.dataset.a='passopen';c.parentNode.insertBefore(b,c.nextSibling);}
 if(!b)return;b.hidden=!show;if(!show)return;b.classList.toggle('warn',st==='locked'||left<6*3600);
 b.innerHTML=st==='trial'?'<span>Free trial · <b>'+leftText(left)+' left</b></span><i>Get the Pass</i>':st==='bonus'?'<span>Bonus days · <b>'+leftText(left)+' left</b></span><i>Get the Pass</i>':
  st==='paid'?'<span>Hustle Pass ends in <b>'+leftText(left)+'</b></span><i>Renew</i>':'<span><b>Your free time is up</b></span><i>Get the Pass</i>';}
function passMenuHTML(){if(!BILL)return'';const st=BILL.state,left=BILL.until?BILL.until-nowS():0;
 const line=st==='paid'?'Your <b>'+esc(planName(BILL.plan))+'</b> is active until <b>'+dateText(BILL.until)+'</b>.':st==='trial'?'You\'re on your free trial: <b>'+leftText(left)+'</b> left.':st==='bonus'?'You\'re on bonus days: <b>'+leftText(left)+'</b> left.':'You need the pass to keep playing.';
 return'<h3>Hustle Pass</h3><p class="sub">'+line+'</p><div class="chips"><button class="btn" data-a="passopen">'+(st==='paid'?'Add more time':'Get the Hustle Pass')+'</button></div>';}
function planName(id){const p=BILL&&BILL.plans&&BILL.plans.find(x=>x.id===id);return id==='gift'?'gifted pass':p?p.name.toLowerCase():'Hustle Pass';}
function openPay(msg){stopAuto();closeModal();payMsg=msg||'';payBusy=false;acctView='pay';renderAccts();window.scrollTo(0,0);}
const PERKS=['Keep building past your first day, all the way to a billion','Dynasties: hand your empire to your heirs, generation after generation','Monthly seasons, trophies and the country leaderboard','Every new event, crisis and feature we add'];
function payViewHTML(){const b=BILL||{plans:[]},st=b.state,co=esc(BR());let h='';
 if(acctView==='paid'){const p=payDone||{};return'<div class="paidbox"><span class="paidicon" aria-hidden="true">✓</span><h2>Payment received</h2><p class="sub">Thank you! Your <b>'+esc(planName(p.plan))+'</b> is active'+(b.until?' until <b>'+dateText(b.until)+'</b>':'')+'. '+co+' is waiting for you.</p></div><div class="chips"><button class="btn primary" data-a="acctclose">Back to my game</button></div>';}
 if(acctView==='gift'){const d=b.giftDays||2;return'<h2>Before you go: '+d+' more days on us</h2><p class="sub">'+co+' is just getting going. Keep building free for '+d+' more days. After that, the Hustle Pass starts at just '+kesText(Math.min.apply(null,b.plans.map(p=>p.kes)))+' a week.</p>'+
  '<div class="chips"><button class="btn primary" data-a="paygift">Claim '+d+' free days</button><button class="btn" data-a="passopen">See the passes</button></div>';}
 if(acctView==='payleft')return'<h2>Your empire is safe</h2><p class="sub">'+co+' is saved exactly as you left it. Get the Hustle Pass whenever you\'re ready and pick up where you left off.</p><p class="sub">Or keep playing free: '+inviteRuleLine()+'</p><div class="chips"><button class="btn primary" data-a="passopen">See the passes</button><button class="btn" data-a="invite">Invite friends</button><button class="btn" data-a="leaderboard">Leaderboard</button><button class="btn ghost" data-a="logout">Log out</button></div>';
 const locked=st==='locked',left=b.until?b.until-nowS():0;
 h+=locked?(b.everPaid?'<h2>Your Hustle Pass has ended</h2><p class="sub">Renew to carry on. '+co+' is saved exactly as you left it.</p>':
   '<h2>'+(b.giftsUsed?'Your bonus days are up':'Your free day is up')+'</h2><p class="sub">'+co+' is just getting started. Get the Hustle Pass to keep building your empire.</p>'):
  '<h2>Hustle Pass</h2><p class="sub">'+(st==='paid'?'Active until <b>'+dateText(b.until)+'</b>. Buying again adds the days on top.':(st==='trial'?'Free trial: ':'Bonus days: ')+'<b>'+leftText(left)+' left</b>. Get the pass now and keep going without a break.')+'</p>';
 if(payMsg)h+='<p class="amsg" role="status">'+payMsg+'</p>';
 const best=b.plans.length>1?b.plans.reduce((m,p)=>p.kes/p.days<m.kes/m.days?p:m,b.plans[0]).id:'';
 h+='<div class="plans">'+b.plans.map(p=>{const loc=kesLocal(p.kes);return'<button class="plan'+(p.id==='month'?' pick':'')+'" data-a="buyplan" data-v="'+p.id+'"'+(payBusy||!b.payReady?' disabled':'')+'>'+
   (p.id==='month'?'<em>Most popular</em>':p.id===best?'<em>Best value</em>':'')+'<b>'+esc(p.name)+'</b><span class="pr">'+kesText(p.kes)+'</span><small>'+p.days+' days'+(loc?' · '+loc:'')+'</small></button>';}).join('')+'</div>';
 h+=b.payReady?'<p class="hint">Pay with M-Pesa, Airtel Money, card or bank through Pesapal. You come straight back here after paying. The pass doesn\'t renew by itself; we remind you before it ends.</p>':'<p class="aerr">Payments are being set up. Please check back soon.</p>';
 h+='<ul class="perks">'+PERKS.map(x=>'<li>'+x+'</li>').join('')+'</ul>';
 if(st!=='paid')h+='<div class="invcta"><b>Can\'t pay right now?</b><span>'+inviteRuleLine()+'</span><button class="btn" data-a="invite">Invite friends</button></div>';
 h+='<div class="chips">'+(locked?'<button class="btn ghost" data-a="paylater"'+(payBusy?' disabled':'')+'>Not now</button><button class="btn ghost" data-a="logout">Log out</button>':'<button class="btn ghost" data-a="acctclose">Back to my game</button>')+'</div>';
 return h;}
async function buyPlan(id){if(payBusy)return;payBusy=true;payMsg='Opening the payment page…';renderAccts();
 if(!passLocked())try{await doSync();}catch(e){}
 try{const d=await api('POST','/api/billing/checkout',{plan:id});location.href=d.url;}
 catch(e){payBusy=false;payMsg=esc(e.message);renderAccts();}}
async function payLater(){payBusy=true;renderAccts();let b=BILL;try{b=(await api('POST','/api/billing/later',{})).bill;}catch(e){}setBill(b);payBusy=false;acctView=BILL&&BILL.gift?'gift':'payleft';renderAccts();}
async function payGift(){try{setBill((await api('POST','/api/billing/gift',{})).bill);acctView=null;renderAccts();if(syncState==='locked'){syncState='saving';queueSync(true);}
  log('You have '+((BILL&&BILL.giftDays)||2)+' more free days. Make them count.','gold');render();}
 catch(e){if(e.data&&e.data.bill)setBill(e.data.bill);acctView='payleft';renderAccts();}}
async function confirmPay(){if(!payRef)return;stopAuto();closeModal();acctView='pay';payBusy=true;payMsg=payCancelled?'You left the payment page. Checking…':'Checking your payment…';renderAccts();
 let d=null;try{d=await api('POST','/api/billing/confirm',{ref:payRef});}catch(e){}
 if(d){setBill(d.bill);const ps=d.payment&&d.payment.status;
  if(ps==='paid'){payDone=d.payment;payRef='';payMsg='';payBusy=false;acctView='paid';renderAccts();if(syncState==='locked'||syncState==='offline'){syncState='saving';}queueSync(true);if(typeof confettiFx==='function')try{confettiFx();}catch(e){}return;}
  if(ps==='pending'&&!payCancelled&&++payTries<13){payMsg='Waiting for the payment to come through. If you paid by M-Pesa, approve the prompt on your phone.';renderAccts();setTimeout(confirmPay,5000);return;}
  payMsg=ps==='pending'&&!payCancelled?'We haven\'t had confirmation yet. If you paid, your pass switches on within a few minutes; we keep checking. You can also pick a pass again below.':'The payment didn\'t go through, so you weren\'t charged. You can try again below.';}
 else payMsg='We couldn\'t check your payment just now. If you paid, your pass switches on within a few minutes.';
 payRef='';payBusy=false;if(passLocked()||acctView==='pay'){acctView='pay';renderAccts();}}
setInterval(()=>{if(!ACC||!BILL)return;paintPass();if(BILL.state!=='locked'&&BILL.until&&nowS()>=BILL.until){
 api('GET','/api/billing').then(d=>{setBill(d.bill);if(passLocked()&&acctView!=='pay'&&acctView!=='gift'&&acctView!=='payleft')openPay();}).catch(()=>{});}},30000);

/* ================= Invite a friend ================= */
function inviteRuleLine(){const b=BILL;if(!b)return'Share your link. Build an empire together and race each other on the leaderboard.';
 return'Every friend who joins with your link gets <b>'+(inviteData?inviteData.trialDays:3)+' days free</b>. When they come back to play on a second day, you get <b>'+(b.refActiveDays||3)+' free pass days</b>, and <b>'+(b.refPaidDays||7)+' more</b> if they buy a pass.';}
function inviteText(){const d=inviteData||{};return'Nimeanza empire yangu on Hustlempires 🏙️ From a street kiosk to a billion. Can you build a bigger one?'+(BILL&&d.trialDays?' Join with my link and get '+d.trialDays+' days free 👉 ':' 👉 ')+(d.link||'https://hustlempires.com');}
async function openInvite(){stopAuto();closeModal();acctView='invite';inviteMsg='';renderAccts();window.scrollTo(0,0);
 try{inviteData=await api('GET','/api/invite');}catch(e){inviteMsg=esc(e.message);}if(acctView==='invite')renderAccts();}
function inviteHTML(){const d=inviteData;let h='<h2>Invite friends</h2><p class="sub">'+inviteRuleLine()+'</p>';
 if(inviteMsg)h+='<p class="amsg" role="status">'+inviteMsg+'</p>';
 if(!d)return h+'<p class="sub">Loading your link…</p><div class="chips"><button class="btn ghost" data-a="acctclose">Back</button></div>';
 h+='<label for="inv-link">Your invite link</label><input id="inv-link" class="invlink" readonly value="'+esc(d.link)+'">';
 h+='<div class="chips"><a class="btn primary" target="_blank" rel="noopener" href="https://wa.me/?text='+encodeURIComponent(inviteText())+'">Share on WhatsApp</a>'+(navigator.share?'<button class="btn" data-a="invshare">Share…</button>':'')+'<button class="btn" data-a="invcopy">Copy link</button></div>';
 h+='<div class="invstats"><span><b>'+d.friends.length+'</b> friend'+(d.friends.length===1?'':'s')+' joined</span><span><b>'+d.friends.filter(f=>f.active).length+'</b> came back</span><span><b>'+d.daysEarned+'</b> free days earned</span></div>';
 if(d.friends.length)h+='<ul class="invlist">'+d.friends.map(f=>'<li>'+avatar(f)+'<span class="ameta"><b>'+esc(f.name)+'</b><span>'+esc(f.company)+' · '+(f.paid?'bought a pass':f.active?'came back to play':'joined, not back yet')+'</span></span><span class="hnum">'+(f.days?'+'+f.days+' days':'')+'</span></li>').join('')+'</ul>';
 else h+='<p class="sub">No one has joined with your link yet. WhatsApp groups and status updates work best.</p>';
 return h+'<p class="hint">Your invite code is <b>'+esc(d.code)+'</b>. Free days from friends who come back are capped at '+d.cap+' friends a month.</p><div class="chips"><button class="btn ghost" data-a="acctclose">Back</button></div>';}
async function inviteCopy(){const d=inviteData;if(!d)return;try{await navigator.clipboard.writeText(inviteText());inviteMsg='Copied. Paste it into any chat.';}catch(e){const i=$('inv-link');if(i){i.select();try{document.execCommand('copy');inviteMsg='Link copied.';}catch(x){inviteMsg='Press and hold the link to copy it.';}}}renderAccts();}
async function inviteShare(){const d=inviteData;if(!d||!navigator.share)return;try{await navigator.share({title:'Hustlempires',text:inviteText().replace(d.link,'').trim(),url:d.link});}catch(e){}}
