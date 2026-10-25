/* ================= Accounts (server) ================= */
let GUEST=false,guestWhy='',guestT=null,ACC=null,acctView='loading',authMode='signup',authMsg='',syncTimer=null,syncBusy=false,syncAgain=false,syncState='saved',newGameFlag=false,lbData=null,signupGender='',pendingLife=null,livesData=null,livesCache=null,seasonCache=null,lbTab='season-country',signupRegion='',signupCur='USD',resetToken='',emailSkip=false,forgotDone='',BILL=null,billSkew=0,payMsg='',payBusy=false,payRef='',payCancelled=false,payTries=0,payDone=null,refCode='',refInfo=null,inviteData=null,inviteMsg='';
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
let SESS='';try{SESS=sessionStorage.getItem('hs-s')||'';}catch(e){}   /* login session, sent as a header too: some in-app browsers (TikTok, Facebook) leave the cookie off. Kept for this tab only */
function setSess(t){SESS=t||'';try{if(SESS)sessionStorage.setItem('hs-s',SESS);else sessionStorage.removeItem('hs-s');}catch(e){}}
async function api(method,path,body){let r;
 if(GUEST&&!/^\/api\/(visit|signup|login|google|config|tuning|invite\/check|username\/check|company\/check|forgot|reset|me|wall|live|map)\b/.test(path))throw{status:401,guest:true,message:'Create your free account to use this.'};
 try{const hd=body?{'Content-Type':'application/json'}:{};if(SESS)hd['X-Hustle-Session']=SESS;const url=SESS?path+(path.indexOf('?')<0?'?':'&')+'_hs='+encodeURIComponent(SESS):path;r=await fetch(url,{method,credentials:'same-origin',headers:hd,body:body?JSON.stringify(body):undefined});}
 catch(e){throw{status:0,message:navigator.onLine===false?'You\'re offline. Connect to the internet to keep playing. Your empire is saved safely on the server.':'Could not reach the game server. Check your connection and try again.'};}
 let d={};try{d=await r.json();}catch(e){}
 if(d&&typeof d.sess==='string')setSess(d.sess);
 if(r.status===401&&SESS&&/^\/api\/(me|save)\b/.test(path))setSess('');
 if(!r.ok)throw{status:r.status,message:d.error||'Something went wrong on the server. Try again in a moment.',data:d};postWorth(d);return d;}
/* posts that carry an amount (a property's worth) show it in this player's own currency */
function postWorth(d){try{['items','posts','posted'].forEach(k=>{(d&&Array.isArray(d[k])?d[k]:[]).forEach(x=>{if(x&&x.tpl)x.text=x.tpl.split('{worth}').join(fmt(+x.worth||0));});});}catch(e){}}
function pastLives(){return livesCache;}
function recordLife(l){pendingLife=l||null;if(l&&livesCache){l.n=livesCache.reduce((m,x)=>Math.max(m,x.n||0),0)+1;livesCache=[l].concat(livesCache);}}
async function loadLives(){try{livesCache=(await api('GET','/api/lives')).lives;}catch(e){livesCache=null;}}
async function showLives(){if(!ACC)return;loadSeason();stopAuto();closeModal();acctView='lives';livesData=null;renderAccts();window.scrollTo(0,0);try{livesData=(await api('GET','/api/lives')).lives;livesCache=livesData;}catch(e){livesData=[];}if(acctView==='lives')renderAccts();}
function startWith(user,save,bill,ver){ttIdentify(user);if(GUEST){GUEST=false;guestDrop();}setTimeout(fyFix,1500);{const lb=document.getElementById('lbbtn');if(lb)lb.hidden=false;if(!window.lbPaintT)window.lbPaintT=setInterval(paintLbBtn,4000);}try{localStorage.setItem('hs-player','1');}catch(e){}setTimeout(()=>pushRegister(false).catch(()=>{}),3000);SAVEVER=(typeof ver==='number')?ver:null;setBill(bill);if(refCode&&authMode==='signup'){refCode='';refInfo=null;try{localStorage.removeItem('hs-ref');}catch(e){}}livesCache=null;loadLives();setTimeout(loadSeason,1200);ACC=user;S=save&&save.hist?Object.assign(fresh(),save):freshFor(user);const away0=S.seen||0;migrate();if(S.gnum>1&&S.who&&!/\s/.test(S.who.trim()))S.who=S.who.trim()+' '+familyName();current=null;closeModal();acctView=null;authMsg='';renderAccts();render();
 if(!save)queueSync(true);
 signupGender='';signupRegion='';signupCur='USD';if(!user.email&&!emailSkip){acctView='addemail';authMsg='';renderAccts();}bankLots=null;mkData={local:null,world:null,mine:null};mkMsg='';setTimeout(bankFlush,2000);mkSettleTries=0;setTimeout(mkSettle,6000);xcData=null;setTimeout(()=>{xcSettle();xcLoad(true);},7000);if(!awayWelcome(away0))startEvents();giftTries=0;setTimeout(giftCheck,4000);setTimeout(()=>{if(typeof bidLoad==='function')bidLoad(true);},5000);rivalStart();
 paintPass();if(payRef)confirmPay();else if(passLocked())openPay();}
function summary(){const nw=netWorth();return{nw,month:S.month,cash:S.cash,rank:TITLES[titleIdx(nw)][1],won:!!S.won,over:!!S.over,newGame:newGameFlag,prev:newGameFlag?pendingLife:null,
 industries:S.inds.length,units:totalUnits(),properties:(S.props||[]).length,teams:Object.keys(S.teams||{}).length,happiness:Math.round(S.happy),reputation:Math.round(S.rep),
 influence:Math.round(S.influence),debt:Math.round(S.debt),married:!!S.spouse,health:Math.round(S.health||0),died:!!S.died,streak:(S.daily&&S.daily.last)?S.daily.streak:0,gender:S.g||'',gen:S.headstart?2:(S.gnum||1),season:S.sea?{id:S.sea.id,pts:S.sea.pts}:null,region:S.region||'',currency:S.cur||'USD',spouse:S.spouse?spW():'',kids:S.kids.length,age:age(),race:S.race?S.race.series:'',foundation:!!S.fdn,cities:(S.pcOpen||[]).length,tab:curTab,ms:msAges(),who:S.who||'',co:Math.round(coValue()),g10:S.newbie?(S.g10||0):-1,card:(typeof current!=='undefined'&&current)?String(current._id||current.cat||'event').slice(0,40):''};}
/* save as soon as a card opens, so the admin can see which card a player was looking at when they left */
{const _oe=window.openEvent;if(typeof _oe==='function')window.openEvent=function(){const r=_oe.apply(this,arguments);try{if(ACC)queueSync();}catch(e){}return r;};}
function queueSync(now){if(!ACC)return;syncState='saving';paintChip();clearTimeout(syncTimer);syncTimer=setTimeout(doSync,now?0:900);}
let SAVEVER=null,syncChecking=false;
async function doSync(){if(!ACC)return;if(syncBusy){syncAgain=true;return;}syncBusy=true;
 const evs=S.log.filter(l=>l.n&&l.n>(S.logSent||0)).slice(0,60).reverse(),maxN=evs.reduce((m,l)=>Math.max(m,l.n),S.logSent||0);
 const evq=(S.evq||[]).slice(0,200);
 try{const r=await api('PUT','/api/save',{state:S,summary:summary(),events:evs,evlog:evq,base:SAVEVER==null?undefined:SAVEVER});if(r&&typeof r.ver==='number')SAVEVER=r.ver;S.logSent=maxN;S.evq=(S.evq||[]).slice(evq.length);if(newGameFlag)pendingLife=null;newGameFlag=false;syncState='saved';}
 catch(e){if(e.status===409){syncBusy=false;syncAgain=false;loadLatest();return;}
  if(e.status===402){setBill(e.data&&e.data.bill);syncState='locked';stopAuto();openPay();}
  else if(e.status===401){ACC=null;stopAuto();acctView='auth';authMode='login';authMsg='Your session ended. Log in again to keep playing. Your last moves are safe on this screen until you do.';renderAccts();}
  else{syncState='offline';clearTimeout(syncTimer);syncTimer=setTimeout(doSync,8000);}}
 syncBusy=false;paintChip();if(syncAgain){syncAgain=false;queueSync();}}
/* the same account on several devices: always show the newest saved game */
async function loadLatest(){if(!ACC)return;stopAuto();try{const d=await api('GET','/api/me');current=null;closeModal();startWith(d.user,d.save,d.bill,d.ver);syncState='saved';paintChip();
 showCard('Updated from your other device','You played on another phone or computer, so this screen now shows your latest empire. Nothing was lost.','<button class="btn primary" data-a="close">Continue</button>');}catch(e){}}
async function syncCheck(){if(!ACC||syncBusy||syncChecking||SAVEVER==null||document.visibilityState!=='visible')return;syncChecking=true;
 try{const d=await api('GET','/api/save/ver');if(d&&typeof d.ver==='number'&&d.ver>SAVEVER&&!syncBusy)await loadLatest();}catch(e){}syncChecking=false;}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')syncCheck();});
window.addEventListener('focus',()=>syncCheck());window.addEventListener('online',()=>syncCheck());window.addEventListener('pageshow',e=>{if(e.persisted){syncCheck();checkVersion(true);}});setInterval(syncCheck,15000);
/* the person being played: the founder, or the heir who took over the family empire */
function playerName(){return(S&&S.who)||(ACC&&ACC.name)||'';}
const playerAcc=()=>Object.assign({},ACC,{name:playerName()});
function paintChip(){const c=$('acctchip');if(!c)return;c.classList.toggle('guest',GUEST);if(GUEST){c.innerHTML=avatar({name:'?',color:1})+'<span><b>Guest</b><small>Not saved · tap to save</small></span>';return;}c.innerHTML=ACC?avatar(playerAcc())+'<span><b>'+esc(playerName())+'</b><small>'+esc(ACC.company)+' · '+({saved:'saved',saving:'saving…',offline:'offline, retrying',locked:'needs the Hustle Pass'})[syncState]+'</small></span>':'<span><b>Not logged in</b><small>Log in to play</small></span>';}
/* first screen: invited friends go straight to sign-up, people who have played on this device to log in, everyone else to About */
function firstMode(){if(refCode)return'signup';try{if(localStorage.getItem('hs-player'))return'login';}catch(e){}return'about';}
function authTabs(){const t=(v,l)=>'<button role="tab" aria-selected="'+(authMode===v)+'" data-a="authmode" data-v="'+v+'">'+l+'</button>';
 return'<div class="authtabs" role="tablist" style="grid-template-columns:1fr 1fr 1fr">'+t('signup','Create account')+t('login','Log in')+t('about','About')+'</div>';}
function authForm(gs){const su=authMode==='signup',gu=gs&&GUEST&&su;const inv=su&&refInfo?'<p class="invbanner"><span aria-hidden="true">🎁</span><span><b>'+esc(refInfo.name)+'</b> invited you to Hustlempires'+(refInfo.trialDays?'. You get <b>'+refInfo.trialDays+' days free</b> to build your empire.':'.')+'</span></p>':'';
 let h=inv+(gs?'':authTabs());
 if(authMsg)h+='<p class="amsg">'+esc(authMsg)+'</p>';
 h+=gsiHTML(su);
 h+='<form id="acctform" class="aform" novalidate>'+
  '<label for="acc-user">Username</label><input id="acc-user" maxlength="20" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="'+(su?'e.g. wanjiku_k':'')+'" required>'+
  (su?'<p class="cotaken" id="acc-user-chk" hidden></p><p class="hint">3 to 20 characters: letters, numbers, dots and underscores. You log in with this. Every username is unique, and if you leave the company name blank, your company is named after it.</p>':'')+
  '<label for="acc-pass">Password</label><input id="acc-pass" type="password" maxlength="128" autocomplete="'+(su?'new-password':'current-password')+'" required>'+(su?'<p class="hint">At least 8 characters.</p>':'')+
  (su?'<label for="acc-email">Email</label><input id="acc-email" type="email" maxlength="120" autocomplete="email" inputmode="email" autocapitalize="none" spellcheck="false" required><p class="hint">Only used to reset your password if you forget it.</p>':'');
 if(su)h+='<label for="acc-name">Your name</label><input id="acc-name" maxlength="24" autocomplete="nickname" placeholder="e.g. Wanjiku Kamau" required>'+(gu&&S.g?'':GENDER_FS)+
  '<details class="moreopts"><summary><b>More options</b><span>'+(gu?'Company brand, home town and colour. All optional: you can skip this.':'Company brand, home town, country, money, starting background and colour. All optional: you can skip this.')+'</span></summary>'+
  '<label for="acc-company">Your company brand</label><input id="acc-company" maxlength="16" placeholder="Leave blank to use your username"><p class="cotaken" id="acc-company-chk" hidden></p><p class="hint">Every company name is unique. Used across your empire: <i>Brand</i> Racing, <i>Brand</i> Tower Dubai, the <i>Brand</i> Foundation.</p>'+
  '<label for="acc-town">Home town</label><select id="acc-town">'+(countryRow(detectCountry())||{towns:TOWNS}).towns.map(t=>'<option>'+esc(t)+'</option>').join('')+'</select>'+(gu?'':regionFormHTML(detectCountry(),'USD'))+
  (gu?'':'<fieldset><legend>Starting background</legend>'+BGS.map((b,i)=>'<label class="bgopt"><input type="radio" name="acc-bg" id="acc-bg-'+b.id+'" value="'+b.id+'"'+(i===0?' checked':'')+'><span><b>'+b.name+'</b><span>'+dollars(b.desc)+'</span></span></label>').join('')+'</fieldset>')+
  '<fieldset><legend>Avatar colour</legend><div class="swatches">'+AVCOL.map((c,i)=>'<label class="sw"><input type="radio" name="acc-col" id="acc-col-'+i+'" value="'+i+'"'+(i===0?' checked':'')+' aria-label="Colour '+(i+1)+'"><span style="background:'+c+'"></span></label>').join('')+'</div></fieldset></details>';
 return h+'<p class="aerr" id="acc-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="acc-submit">'+(su?(gu?'Save my empire':'Create account and start'):'Log in')+'</button>'+(su?'':'<button type="button" class="btn ghost" data-a="forgotview">Forgot your password?</button>')+'</div></form>';}
function authHook(){const su=authMode!=='login';
 return'<div class="hook">'+(su?'<p class="hook-mind"><span aria-hidden="true">🎮</span> <b>A free business life game.</b> Build an empire with game cash, just for fun.</p>':'')+'<p class="hook-big">'+(su?'Start with <em>'+fmt(1000)+'</em>.<br>Die a <em>legend</em>.':'Your empire <em>missed you</em>.')+'</p><p class="hook-sub">'+(su?'Free to play. No downloads. Your first hustle is one tap away.':'Your businesses kept running. Your rivals kept climbing. Time to take back your throne.')+'</p></div>';}
const ABOUT=[['🏪','From kiosk to conglomerate','Open shops, farms, factories and more across industries and cities. Every deal is your call.'],
 ['📈','Real business choices','Bank loans, hot tips, rival bids, hostile takeovers and taking your company public. Grow fast or grow safe.'],
 ['⚖️','Every shortcut has a price','Bribe the inspector or play it straight? Blame the contractor or own it? What you hide comes back for you.'],
 ['🚀','Life at the top','The rich list, a space programme aiming for Mars, your own football club and F1 team, even a city with your family name on it.'],
 ['🏛️','Power and giving','Run for office, start a foundation and take on a world problem. Or watch one scandal undo it all.'],
 ['👨‍👩‍👧','Your name lives on','Marry, raise your children, then decide which one inherits everything you built. Read your own obituary when your story ends.'],
 ['🏆','Prove you are the best','A new leaderboard season every month, in your country and the world, plus records that never reset: youngest to $1 million, $1 billion and $1 trillion. Nobody has reached $1 quadrillion yet.']];
function aboutGame(gs){
 return'<section class="about" aria-labelledby="about-h"><h3 id="about-h">Build an empire. Live a whole life.</h3>'+
  '<p class="about-lead">Hustlempires is a free business life game for your phone or computer. You start young with '+fmt(1000)+' of game cash and a street kiosk. Every month brings a decision: grow, borrow, take a risk or play it safe. Climb from Street Hustler to Billionaire, and beyond. <b>One life. One empire.</b> Your name on a stadium, or in the bankruptcy papers.</p>'+
  '<p class="about-lead"><b>How to play:</b> tap <b>PLAY</b> and the months run until something happens, then you choose. Your first hustle takes one minute.</p>'+
  '<ul class="about-list">'+ABOUT.map(x=>'<li><span class="about-ic" aria-hidden="true">'+x[0]+'</span><span><b>'+x[1]+'</b>'+x[2]+'</span></li>').join('')+'</ul>'+
  '<p class="hook-mind"><span aria-hidden="true">🎮</span> <b>It is a game.</b> All the money in Hustlempires is game money, just for fun. You cannot win, earn or withdraw real money.</p>'+
  '<div class="about-cta"><p class="hook-big">Every empire here started with <em>one kiosk</em>.<br>Yours starts in <em>one minute</em>.</p>'+
  '<p class="about-fine">Free to play. No download. Play as a guest first, then create a free account when you want to save your empire and play on any device.</p>'+
  (gs?'<div class="chips"><button class="btn primary" data-a="guestlater">Keep playing</button><button class="btn ghost" data-a="authmode" data-v="signup">Save my empire</button></div>'
   :'<div class="chips"><button class="btn primary" data-a="authjump" data-v="signup">Start my empire, free</button><button class="btn ghost" data-a="authjump" data-v="login">I already have an empire</button></div>')+'</div></section>';}
/* ---------- Notifications: a friendly nudge when the player has been away ---------- */
let pushKey=null,pushAskT=null;
function pushSupported(){return'serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window;}
function pushPerm(){return pushSupported()?Notification.permission:'unsupported';}
function iosNoPush(){return/iphone|ipad|ipod/i.test(navigator.userAgent)&&!pushSupported();}
function u8(b){const p='='.repeat((4-b.length%4)%4),r=atob((b+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(r,c=>c.charCodeAt(0));}
async function pushGetKey(){if(pushKey!==null)return pushKey;try{const d=await api('GET','/api/push/key');pushKey=d.on?d.key:'';}catch(e){pushKey='';}return pushKey;}
async function pushRegister(ask){if(!pushSupported()||!ACC)return false;const key=await pushGetKey();if(!key)return false;
 if(ask){const p=await Notification.requestPermission();if(p!=='granted')return false;}else if(Notification.permission!=='granted')return false;
 const reg=await navigator.serviceWorker.ready;let sub=await reg.pushManager.getSubscription();
 if(sub){const cur=sub.options&&sub.options.applicationServerKey;if(cur){const a=new Uint8Array(cur),b=u8(key);if(a.length!==b.length||a.some((x,i)=>x!==b[i])){await sub.unsubscribe();sub=null;}}}
 if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:u8(key)});
 let tz='';try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone||'';}catch(e){}
 const j=sub.toJSON();await api('POST','/api/push/subscribe',{endpoint:j.endpoint,keys:j.keys,tz,off:-new Date().getTimezoneOffset()});return true;}
async function pushForget(){try{if(!pushSupported())return;const reg=await navigator.serviceWorker.getRegistration();const sub=reg&&await reg.pushManager.getSubscription();if(sub)await api('POST','/api/push/unsubscribe',{endpoint:sub.endpoint});}catch(e){}}
function pushAskedRecently(){try{return Date.now()-(+localStorage.getItem('hs-push-ask')||0)<14*864e5;}catch(e){return true;}}
function pushMaybeAsk(){if(pushAskT||!ACC||!S||S.over||S.month<6||pushPerm()!=='default'||pushAskedRecently())return;
 pushAskT=setTimeout(async()=>{pushAskT=null;if(current||!$('modal').hidden||acctView||pushPerm()!=='default'||pushAskedRecently())return;if(!(await pushGetKey()))return;
  try{localStorage.setItem('hs-push-ask',String(Date.now()));}catch(e){}
  showCard('Never miss a big moment','Want a heads-up when your daily streak is about to break, a rival passes you on the leaderboard, or your empire needs you? We send a few at most, and never at night.',
   '<button class="choice" data-a="pushyes"><b>Yes, notify me</b><span>Your phone will ask you to allow notifications. Tap Allow.</span></button><button class="choice" data-a="pushno"><b>Not now</b><span>You can switch them on later from your account.</span></button>');},2500);}
async function pushYes(){closeModal();try{const ok=await pushRegister(true);showCard(ok?'Notifications on':'Notifications are off',ok?'We will give you a nudge when something needs you. You can switch them off any time from your account.':(pushPerm()==='denied'?'Your browser blocked them. You can allow notifications for this site in your browser settings, then switch them on from your account.':'They could not be switched on on this device.'),'<button class="choice" data-a="closecard"><b>Back to my empire</b></button>');}catch(e){showCard('Notifications are off','They could not be switched on on this device.','<button class="choice" data-a="closecard"><b>Back to my empire</b></button>');}}
function pushMenuHTML(){const p=pushPerm();let line,btn='';
 if(iosNoPush())line='On iPhone, notifications work once the game is on your Home Screen. Tap <b>Install app</b> above, then open the game from its icon.';
 else if(p==='unsupported')line='This browser cannot show notifications.';
 else if(p==='granted')line='<b>On.</b> We nudge you when your streak is about to break, a rival passes you, or your empire needs you. Never at night.',btn='<button class="btn ghost" data-a="pushoff">Switch off on this device</button>';
 else if(p==='denied')line='<b>Blocked</b> by your browser. To switch them on, allow notifications for this site in your browser settings.';
 else line='<b>Off.</b> Get a nudge when your streak is about to break or a rival passes you. A few at most, never at night.',btn='<button class="btn" data-a="pushon">Switch on notifications</button>';
 return'<h3>Notifications</h3><p class="sub">'+line+'</p>'+(btn?'<div class="chips">'+btn+'</div>':'');}
async function pushOff(){await pushForget();try{const reg=await navigator.serviceWorker.getRegistration();const sub=reg&&await reg.pushManager.getSubscription();if(sub)await sub.unsubscribe();}catch(e){}renderAccts();}
/* ---------- While you were away: a welcome back after 8+ hours ---------- */
let awayBusy=false,awayAmt=0;
function seaRemember(d){if(d&&d.me&&S)S.seaRank={id:d.season,r:d.me.rankRegion};}
function awayMonths(h){return h>=72?3:h>=48?2:h>=8?1:0;}
function awayWelcome(seen){if(!S||S.over||!S.inds.length||S.month<1||!seen)return false;
 const t=Date.now(),from=Math.max(seen,S.awayClaim||0),h=(t-from)/36e5;if(h<8||h>24*365)return false;
 awayBusy=true;const net=Math.max(0,Math.round(flows(false).net)),mo=awayMonths(h);awayAmt=net*mo;S.awayClaim=t;
 const paint=d=>{awayBusy=false;const rows=[],nm=(playerName()||'').split(' ')[0],days=h>=48?Math.floor(h/24)+' days':h>=24?'a day':Math.round(h)+' hours';
  if(awayAmt>0)rows.push('<li><span>💰</span><span><b>Your businesses earned '+fmt(awayAmt)+'</b>Your managers kept the doors open: '+mo+' month'+(mo>1?'s':'')+' of profit is waiting for you.</span></li>');
  const old=S.seaRank,me=d&&d.me;
  if(me){const fell=old&&old.id===d.season&&me.rankRegion>old.r?me.rankRegion-old.r:0;
   rows.push('<li><span>🏆</span><span><b>You are #'+me.rankRegion+' in your country this season</b>'+(fell?fell+' player'+(fell>1?'s':'')+' passed you while you were away. ':'')+(me.ahead?esc(me.ahead.name)+' is just '+me.ahead.gap.toLocaleString('en-US')+' points ahead.':'Nobody is ahead of you. Stay there.')+'</span></li>');}
  seaRemember(d);
  const dl=(S.daily||{});if(dl.streak>=2&&dl.last===yesterdayKey())rows.push('<li><span>🔥</span><span><b>Your '+dl.streak+'-day streak is still alive</b>Press PLAY to claim today\'s bonus and keep it going.</span></li>');
  if(!rows.length){startEvents();return;}
  showCard('Welcome back'+(nm?', '+esc(nm):''),'You were away for '+days+'. Here is what happened.<ul class="awaylist">'+rows.join('')+'</ul>',
   '<button class="choice" data-a="awaygo"><b>'+(awayAmt>0?'Collect '+fmt(awayAmt):'Back to my empire')+'</b><span>'+(awayAmt>0?'Then carry on building.':'Pick up where you left off.')+'</span></button>');};
 Promise.race([api('GET','/api/season?scope=country&region='+encodeURIComponent(S.region||'')),new Promise(r=>setTimeout(()=>r(null),2500))]).then(d=>{if(d)seasonCache=d;paint(d);}).catch(()=>paint(null));
 return true;}
function awayCollect(){closeModal();if(awayAmt>0){S.cash+=awayAmt;log('While you were away, your businesses earned '+fmt(awayAmt)+'.','good');try{coinBurst(14);}catch(e){}awayAmt=0;render();save();}startEvents();}
/* ---------- Friends: see how they are doing, send a daily gift ---------- */
let friendsData=null,friendMsg='',frTab='friends',feedScope='country',feedData=null;
async function openFriends(tab){if(tab==='feed'){openLive('country');return;}stopAuto();closeModal();{const t=$('hstoast');if(t)t.hidden=true;}acctView='friends';friendMsg='';if(tab)frTab=tab;renderAccts();
 try{friendsData=await api('GET','/api/friends?open=1');}catch(e){friendMsg=esc(e.message);}if(frTab==='feed')await feedLoad();if(acctView==='friends')renderAccts();}
async function feedLoad(){try{feedData=await api('GET','/api/feed?scope='+feedScope+'&region='+encodeURIComponent(S.region||''));}catch(e){feedData={items:[],reacts:[],err:e.message};}}
async function frTabGo(t){if(t==='feed'){openLive('country');return;}frTab=t;friendMsg='';if(t==='feed'&&!feedData)await feedLoad();renderAccts();if(t==='feed'){await feedLoad();if(acctView==='friends'&&frTab==='feed')renderAccts();}}
async function feedScopeGo(v){feedScope=v;feedData=null;renderAccts();await feedLoad();renderAccts();}
async function feedReact(id,e){const it=feedData&&feedData.items.find(x=>x.id===id);if(!it)return;try{const r=await api('POST','/api/feed/react',{id,e});it.reacts=r.reacts||{};it.mine=r.mine||'';}catch(er){friendMsg=esc(er.message);}renderAccts();}
async function feedAddFriend(id){try{const r=await api('POST','/api/friends/add',{id});friendMsg=esc(r.name)+' is now your friend.';const it=feedData&&feedData.items.filter(x=>x.uid===id);(it||[]).forEach(x=>x.friend=true);friendsData=await api('GET','/api/friends');}catch(e){friendMsg=esc(e.message);}renderAccts();}
function feedLine(it){const who=it.who&&it.who!==it.name?it.who:it.name,nm0=esc(it.guest?(who||'A player'):(who||'A player').split(' ')[0]),nm=it.handle?'<button class="linkbtn wname" data-a="wallopen" data-v="'+esc(it.handle)+'">'+nm0+'</button>':'<b>'+nm0+'</b>';
 if(it.text)return nm+' '+esc(it.text)+(/[A-Za-z0-9]$/.test(it.text)?'.':'');
 if(it.kind==='heir')return nm+' took over the family empire as generation '+it.gen+'.';
 const r=it.rank||'',an=/^[AEIOU]/.test(r)?'an ':'a ';return nm+' became '+an+'<b>'+esc(r)+'</b>.';}
function feedHTML(){const d=feedData,cn=(countryRow(S.region)||{}).name||'your country';
 let h='<div class="chips mktabs"><button class="btn small'+(feedScope==='country'?' primary':'')+'" data-a="feedscope" data-v="country">'+esc(cn)+'</button><button class="btn small'+(feedScope==='friends'?' primary':'')+'" data-a="feedscope" data-v="friends">Friends</button></div>';
 if(!d)return h+'<p class="sub">Loading…</p>';
 if(d.err)return h+'<p class="amsg">'+esc(d.err)+'</p>';
 if(!d.items.length)return h+'<p class="sub">'+(feedScope==='friends'?'No news from your friends in the last two weeks. Add friends from the '+esc(cn)+' feed, or invite them.':'Nothing yet. When players in '+esc(cn)+' make their first million or billion, or a major purchase, it shows up here.')+'</p>';
 return h+'<ul class="invlist feedlist">'+d.items.map(it=>'<li>'+(it.handle?'<button class="wavbtn" data-a="wallopen" data-v="'+esc(it.handle)+'" aria-label="Open '+esc(it.name||'')+'\'s profile">'+avatar(it)+'</button>':avatar(it))+'<span class="ameta"><span class="feedtxt">'+feedLine(it)+'</span><span>'+(it.guest?'Guest player':esc(it.company||''))+' · '+esc(it.ago||'')+'</span>'+
  '<span class="reacts">'+(it.kind==='obit'?WALL_RX_SAD:(d.reacts||[])).map(e=>{const n=(it.reacts||{})[e]||0;return it.me?(n?'<span class="react on">'+e+' '+n+'</span>':''):'<button class="react'+(it.mine===e?' on':'')+'" data-a="feedreact" data-v="'+it.id+'" data-e="'+e+'" aria-label="React '+e+'">'+e+(n?' '+n:'')+'</button>';}).join('')+
  (!it.me&&!it.friend&&it.uid?'<button class="btn ghost small feedadd" data-a="feedadd" data-v="'+it.uid+'">+ Friend</button>':'')+'</span></span></li>').join('')+'</ul>';}
let frPick=0;
function msgPick(id){frPick=id;frTab='friends';friendMsg='';renderAccts();try{window.scrollTo(0,0);const el=$('acct');if(el)el.scrollTop=0;}catch(e){}}
function msgPickHTML(){const d=friendsData,f=d&&d.friends.find(x=>x.id===frPick);if(!f||!d.codes)return'';
 return'<div class="msgpick"><h3>Message '+esc((f.name||'').split(' ')[0])+'</h3><p class="sub">Pick one. It lands on their phone.'+(d.msgsLeft<5?' '+d.msgsLeft+' left today.':'')+'</p><div class="choices">'+d.codes.map(([k,t])=>'<button class="choice" data-a="msgsend" data-v="'+f.id+'" data-c="'+k+'"><b>'+esc(t)+'</b></button>').join('')+'</div><button class="btn ghost" data-a="msgcancel">Cancel</button></div>';}
async function msgSend(id,code){frPick=0;try{await api('POST','/api/friends/msg',{id,code});friendMsg='Message sent.';friendsData=await api('GET','/api/friends?open=1');if(friendsData)friendsData.msgsLeft=friendsData.msgsLeft;}catch(e){friendMsg=esc(e.message);}acctView='friends';frTab='friends';renderAccts();}
function friendsHTML(){const d=friendsData,un=d&&d.msgs?d.msgs.filter(m=>!m.seen).length:0;let h='<h2>Friends</h2><div class="authtabs frtabs" role="tablist"><button role="tab" aria-selected="'+(frTab==='feed')+'" data-a="frtab" data-v="feed">Business feed</button><button role="tab" aria-selected="'+(frTab!=='feed')+'" data-a="frtab" data-v="friends">Friends'+(un&&frTab==='feed'?' <i class="frbadge">'+un+'</i>':'')+'</button></div>';
 if(frTab==='feed'){if(friendMsg)h+='<p class="amsg">'+friendMsg+'</p>';return h+'<p class="sub">Big moments from real players. Cheer them on, or add them as friends.</p>'+feedHTML()+'<div class="chips"><button class="btn" data-a="acctclose">Back to my game</button><button class="btn ghost" data-a="leaderboard">Leaderboard</button></div>';}
 if(frPick&&d){const pk=msgPickHTML();if(pk)return h+pk;}
 h+='<p class="sub">See how your friends are doing, send each one a gift every day and send quick messages. A gift is worth a month of their profit, and their phone gets a nudge.</p>';
 h+='<form id="friendform" class="aform frform" novalidate><label for="fr-user">Add a friend by username</label><div class="frrow"><input id="fr-user" maxlength="21" autocapitalize="none" spellcheck="false" placeholder="e.g. wanjiku_k"><button type="submit" class="btn primary">Add</button></div></form>';
 if(friendMsg)h+='<p class="amsg">'+friendMsg+'</p>';
 if(!d)return h+'<p class="sub">Loading…</p><div class="chips"><button class="btn" data-a="acctclose">Back to my game</button></div>';
 if(d.msgs&&d.msgs.length)h+='<h3>Messages</h3><ul class="invlist msglist">'+d.msgs.slice(0,8).map(m=>'<li class="'+(m.seen?'':'unseen')+'">'+avatar(m)+'<span class="ameta"><b>'+esc((m.name||'').split(' ')[0])+'</b><span class="msgtxt">'+esc(m.text)+'</span><span>'+esc(m.ago)+'</span></span>'+(d.friends.some(f=>f.id===m.from)?'<button class="btn small" data-a="msgpick" data-v="'+m.from+'">Reply</button>':'')+'</li>').join('')+'</ul>';
 if(d.added&&d.added.length)h+='<h3>Added you</h3><ul class="invlist">'+d.added.map(f=>'<li>'+avatar(f)+'<span class="ameta"><b>'+esc(f.name)+'</b><span>@'+esc(f.username)+' · '+esc(f.company)+'</span></span><button class="btn small" data-a="friendaddid" data-v="'+f.id+'">Add back</button></li>').join('')+'</ul>';
 h+='<h3>Your friends'+(d.friends.length?' ('+d.friends.length+')':'')+'</h3>';
 if(!d.friends.length)h+='<p class="sub">No friends yet. Add someone by their username above, or invite friends: anyone who joins with your link becomes your friend.</p><div class="chips"><button class="btn" data-a="invite">Invite friends</button></div>';
 else{h+='<p class="sub">'+(d.giftsLeft?d.giftsLeft+' gift'+(d.giftsLeft>1?'s':'')+' left to send today.':'All gifts sent for today. More tomorrow.')+'</p><ul class="invlist frlist">'+d.friends.map(f=>{const diff=f.nw-(d.me.nw||0);
  return'<li>'+avatar(f)+'<span class="ameta"><b><button class="linkbtn wname" data-a="wallopen" data-v="'+esc(f.username)+'">'+esc(f.name)+'</button>'+(f.online?' <i class="frdot" title="Playing now"></i>':'')+'</b><span>'+esc(f.company)+' · '+esc(f.seen)+'</span><span>'+fmt(f.nw)+' · '+esc(f.rank||'')+(f.nw>0?' · <em class="'+(diff>0?'frup':'frdn')+'">'+(diff>0?fmt(diff)+' ahead of you':fmt(-diff)+' behind you')+'</em>':'')+'</span></span>'+
   '<span class="frbtns"><button class="btn small" data-a="msgpick" data-v="'+f.id+'" aria-label="Message '+esc(f.name)+'">💬</button><button class="btn small'+(f.canGift?' primary':'')+'" data-a="friendgift" data-v="'+f.id+'"'+(f.canGift?'':' disabled')+'>'+(f.canGift?'🎁 Gift':'Sent')+'</button><button class="btn ghost small" data-a="friendrm" data-v="'+f.id+'" aria-label="Remove '+esc(f.name)+'">✕</button></span></li>';}).join('')+'</ul>';}
 return h+'<div class="chips"><button class="btn" data-a="acctclose">Back to my game</button><button class="btn ghost" data-a="leaderboard">Leaderboard</button></div>';}
async function friendAct(kind,v){try{if(kind==='add'){const u=v||($('fr-user')||{}).value||'';if(!u.trim()){friendMsg='Type their username first.';renderAccts();return;}const r=await api('POST','/api/friends/add',typeof v==='number'?{id:v}:{username:u});friendMsg=esc(r.name)+' is now your friend.';}
 else if(kind==='gift'){await api('POST','/api/friends/gift',{id:v});friendMsg='Gift sent. They will get a nudge on their phone.';try{coinBurst(10);}catch(e){}}
 else if(kind==='rm'){await api('POST','/api/friends/remove',{id:v});friendMsg='Removed.';}
 friendsData=await api('GET','/api/friends');}catch(e){friendMsg=esc(e.message);}renderAccts();}
document.addEventListener('submit',e=>{if(e.target&&e.target.id==='friendform'){e.preventDefault();friendAct('add');}});
let giftTries=0,giftPending=null;
async function giftCheck(){if(!ACC||!S||S.over)return;if(current||!$('modal').hidden||acctView){if(++giftTries<20)setTimeout(giftCheck,3000);return;}
 let d;try{d=await api('GET','/api/friends');}catch(e){return;}friendsData=d;if(!d.gifts||!d.gifts.length){const m=(d.msgs||[]).find(x=>!x.seen);if(m&&!current&&!acctView)toast('<b>💬 '+esc((m.name||'A friend').split(' ')[0])+'</b><span>'+esc(m.text)+(d.unseen>1?' (+'+(d.unseen-1)+' more)':'')+'</span>','friendsmsg');return;}
 if(current||!$('modal').hidden||acctView){if(++giftTries<20)setTimeout(giftCheck,3000);return;}
 const g=d.gifts.slice(0,5),names=[...new Set(g.map(x=>(x.name||'A friend').split(' ')[0]))],each=Math.max(100,Math.round(flows(false).net)),amt=each*g.length;giftPending=amt;
 showCard('🎁 '+(g.length>1?g.length+' gifts':'A gift')+' from your friends',esc(names.length>1?names.slice(0,-1).join(', ')+' and '+names[names.length-1]:names[0])+' sent you '+(g.length>1?'gifts':'a gift')+'. Each one is worth a month of your profit.',
  '<button class="choice" data-a="giftclaim"><b>Collect '+fmt(amt)+'</b><span>Then send one back from Friends.</span></button>');}
async function giftClaim(){closeModal();try{const r=await api('POST','/api/friends/claim',{});if(r.n){const each=Math.max(100,Math.round(flows(false).net)),amt=each*r.n;S.cash+=amt;log('Gifts from '+r.from.join(', ')+': '+fmt(amt)+'.','good');try{coinBurst(14);}catch(e){}render();save();
  showCard('Say thanks','Send a gift back. It only takes a tap, and it lands on their phone.','<button class="choice" data-a="friends"><b>Open Friends</b><span>Send gifts back.</span></button><button class="choice" data-a="closecard"><b>Later</b><span>Back to my empire.</span></button>');}}catch(e){}}
/* ---------- Public profile ("empire wall"): big moments post themselves, and the profile has a link to share ---------- */
/* The game only sends which milestone happened; the server writes the words. Guests get a profile too (Hustler 1234),
   kept with a secret key in this browser, and it moves to their account when they save their empire. */
/* what posts: the first million, billion and trillion; luxury buys, top cars and homes, teams, planes and a city;
   weddings, babies and divorces; the foundation and every cause it advances; league titles and championships */
const WALL_VER=4;   /* raise when new kinds of post are added, so existing lives do not post their old moments */
const WALL_RANKS=[3,6,8];   /* Millionaire, Billionaire, Trillionaire */
const WALL_BUYS=['shoes','bags','wardrobe','birkin','jewels','watch','horses','villa','art','yacht','vineyard','golfclub','island','superyacht','trophyhotel','masterpiece','car4','car5','car6','jet','h4','h5','h6'];
const WALL_TOP=['rank','title','cause','fdn','buy','married','baby','divorce'];
const WALL_RX=['\u{1F44F}','\u{1F525}','\u{1F4B0}','\u{1F62E}'],WALL_RX_SAD=['\u{1F64F}','\u2764\uFE0F','\u{1F54A}\uFE0F','\u{1F622}'];   /* an obituary gets condolences */
let wallMine=null,wallView=null,wallMsg='',wallBusy=false,wallT=null,wallBack=null,wallToastQ=null;
const capFirst=t=>String(t||'').charAt(0).toUpperCase()+String(t||'').slice(1);
/* never Math.random here: the game's luck runs on it, and a milestone must not change what happens next */
function wallId(){let r='';try{r=crypto.getRandomValues(new Uint32Array(1))[0].toString(36);}catch(e){r=String(performance.now()|0);}return Date.now().toString(36)+r.slice(0,5);}
function wallKey(){try{return localStorage.getItem('hs-gp')||'';}catch(e){return'';}}
function wallOwner(){return ACC&&!GUEST?'u'+ACC.id:GUEST?'g':'';}
function wallQ(){try{const a=JSON.parse(localStorage.getItem('hs-wallq')||'[]');return Array.isArray(a)?a:[];}catch(e){return[];}}
function wallQSet(a){try{localStorage.setItem('hs-wallq',JSON.stringify(a.slice(-60)));}catch(e){}}
/* everything this life has achieved that could be a post: [key, kind, details, big] */
function wallFacts(){const L=S.lifeId,f=[],ag=age(),w=d=>S.who?Object.assign({who:S.who},d):d;
 WALL_RANKS.forEach(i=>{if((S.title||0)<i)return;const d=w({r:TITLES[i][1],age:ag}),R=i===6?S.race1:i===8?S.race2:null;
  if(R&&!R.inherited&&R.m!=null&&GRADE_NAME[R.grade])Object.assign(d,{m:R.m,g:R.grade});   /* the billion and the trillion carry the race time and title */
  f.push([L+':rank:'+i,'rank',d,true]);});
 const buy=id=>f.push([L+':buy:'+id,'buy',w({i:id,age:ag}),true]);
 WALL_BUYS.forEach(id=>{if(has(id)>0)buy(id);});
 Object.keys(S.teams||{}).forEach(id=>{const T=S.teams[id];if(!T)return;buy('team-'+id);for(let n=1;n<=Math.min(T.titles||0,99);n++)f.push([L+':title:'+id+':'+n,'title',w({t:id,n}),true]);});
 if(S.race&&S.race.series==='F1')buy('f1');
 if(S.race&&S.race.titles){const sr=String(S.race.series||'F1').toLowerCase();for(let n=1;n<=Math.min(S.race.titles,99);n++)f.push([L+':title:'+sr+':'+n,'title',w({t:sr,n}),true]);}
 if(S.city&&S.city.done>=1)buy('city');
 if(S.spouse)f.push([L+':wed:'+(S.spouse.since||0),'married',w({n:String(S.spouse.name||'').split(' ')[0],age:ag}),true]);
 for(let n=1;n<=Math.min(S.exes||0,20);n++)f.push([L+':div:'+n,'divorce',w(n===(S.exes||0)&&S.lastEx?{n:String(S.lastEx).split(' ')[0]}:{}),true]);
 (S.kids||[]).forEach(k=>{if(!k.rel&&k.born!=null&&k.born>=0)f.push([L+':kid:'+k.born+':'+k.name,'baby',w({n:k.name}),true]);});
 if(S.died){const sp=S.spouse&&!S.widowed?String(S.spouse.name||'').split(' ')[0]:'';f.push([L+':obit','obit',w({age:ag,r:TITLES[Math.max(0,S.title||0)][1],k:(S.kids||[]).filter(k=>!k.rel&&!k.dead).length,n:sp}),true]);}   /* the obituary */
 /* property: every building in every town, with what it is worth and how many the player now owns there */
 const P=S.props||[],cities=new Set(P.map(p=>p.city));
 P.forEach(p=>{let t,c;try{t=ptype(p.type);c=pcity(p.city);}catch(e){return;}if(!t||!c)return;const dev=p.left>0,v=t.base*c.m*p.af/(dev?.7:1);
  f.push([(L+':prop:'+p.city+':'+p.type+':'+String(p.name||'').replace(/[^A-Za-z0-9]+/g,'-')).slice(0,80),'prop',w({t:p.type,c:c.name,v:Math.round(v),dev:dev?1:0,n:1,q:P.filter(x=>x.city===p.city).length,tq:P.length,tc:cities.size}),true]);});
 /* rental units, apartment blocks and malls are bought by the dozen: post at 1, 5, 10, 25, 50, 100 and so on */
 ['a1','a2','a3'].forEach(id=>{const n=has(id);if(!n)return;const a=ASSETS.find(x=>x.id===id);if(!a)return;const v=Math.round(n*a.price*(typeof afx==='function'?afx(id):1));
  [1,5,10,25,50,100,250,500,1000,2500,5000,10000].forEach(m=>{if(n>=m)f.push([L+':units:'+id+':'+m,'units',w({i:id,n,v}),true]);});});
 if(S.fdn){f.push([L+':fdn','fdn',w({}),true]);const st=S.fdn.stage||{};Object.keys(st).forEach(c=>{for(let l=1;l<=Math.min(st[c]||0,3);l++)f.push([L+':cause:'+c+':'+l,'cause',w({c,l}),true]);});}
 return f;}
/* after every save: anything new becomes a post. The first look at a life only takes note of what is already there,
   so nobody's old milestones arrive all at once as if they had just happened. */
/* ---- the law on the Live feed: arrest, the case, prison or hiding, and the day they are back ----
   The game's own law functions are wrapped once, after the whole game has loaded, so each step posts as it happens. */
let lawHooked=false,lawCtx='';
function lawPost(e,d){try{if(!S||!wallOwner())return;if(!S.lifeId||!S.wallDone)wallTick();if(!S.lifeId)return;
 const k=(S.lifeId+':law:'+e+':'+(S.month||0)).slice(0,80);if(S.wallDone[k])return;S.wallDone[k]=1;
 wallPush([[k,'law',Object.assign(S.who?{who:S.who}:{},{e,g:S.g==='f'?'f':S.g==='m'?'m':''},d||{}),true]]);}catch(x){}}
function lawWhy(w){w=String(w||'');return/negligence/.test(w)?'neg':/corruption and fraud/.test(w)?'fraud':/tax/.test(w)?'tax':/crime from/.test(w)?'past':/ran from/.test(w)?'ran':'';}
function lawHook(){if(lawHooked)return;try{if(typeof startJail!=='function'||typeof LAW_EVENTS==='undefined')return;}catch(x){return;}lawHooked=true;
 const sj=startJail;startJail=function(n,why){const r=sj.apply(this,arguments);const w=lawWhy(why);lawPost(lawCtx==='guilty'?'guilty':w==='tax'?'plea':'jail',{n:Math.round(n)||0,w});lawCtx='';return r;};
 const tr=trial;trial=function(){lawCtx='guilty';const r=tr.apply(this,arguments);if(r&&r[1]==='good')lawPost('innocent',{});lawCtx='';return r;};
 const sh=startHide;startHide=function(){const r=sh.apply(this,arguments);lawPost('fled',{});return r;};
 const hb=hideBack;hideBack=function(k){const was=hiding();if(k==='plead'&&was)lawPost('surrender',{});const r=hb.apply(this,arguments);
  if(was&&!hiding()){if(k==='influence')lawPost('dropped',{});else if(k==='deal')lawPost('deal',{});}return r;};
 const lt=lawTick;lawTick=function(){const L=S&&S.law,was=!!(L&&L.jail),tot=was?L.jail.total:0;const r=lt.apply(this,arguments);if(was&&!(S.law&&S.law.jail))lawPost('free',{n:tot});return r;};
 if(typeof vanish==='function'){const va=vanish;vanish=function(){lawPost('vanished',{});try{wallFlush();}catch(x){}return va.apply(this,arguments);};}
 LAW_EVENTS.forEach(ev=>{if(ev.id!=='law_arrest'&&ev.id!=='law_raid')return;const b=ev.build;ev.build=function(){const r=b.apply(this,arguments);lawPost(ev.id==='law_arrest'?'arrest':'raid',{});return r;};});}
function wallTick(){try{lawHook();if(!S||!wallOwner())return;const gen=S.gnum||1;
 if(!S.wallDone||!S.lifeId||S.wallGen!==gen){if(!S.lifeId||S.wallGen!==gen)S.lifeId=wallId();S.wallGen=gen;S.wallDone={};
  wallFacts().forEach(x=>{S.wallDone[x[0]]=1;});S.wallVer=WALL_VER;
  if(S.wallNew&&ACC&&!GUEST){const k=S.lifeId+':start';S.wallDone[k]=1;wallPush([(S.gnum||1)>1?[k,'heir',{who:S.who||'',gen:S.gnum},true]:[k,'start',S.who?{who:S.who,b:ACC.bg||'hustler'}:{b:ACC.bg||'hustler'},true]]);}   /* a new game is news too */
  delete S.wallNew;return;}
 if((S.wallVer||1)<WALL_VER){wallFacts().forEach(x=>{S.wallDone[x[0]]=1;});S.wallVer=WALL_VER;return;}   /* new kinds of post: what a life already has is not news */
 const nu=wallFacts().filter(x=>!S.wallDone[x[0]]);nu.forEach(x=>{S.wallDone[x[0]]=1;});
 const rk=nu.filter(x=>x[1]==='rank'),out=nu.filter(x=>x[1]!=='rank'&&x[1]!=='prop'&&x[1]!=='units');if(rk.length)out.unshift(rk[rk.length-1]);   /* two ranks in one month: only the higher one */
 const pg={};nu.filter(x=>x[1]==='prop').forEach(x=>{const d=x[2],g=d.c+'|'+d.t+'|'+(d.dev||0);if(pg[g]){pg[g][2].n++;pg[g][2].v+=d.v;}else pg[g]=[x[0],'prop',Object.assign({},d)];});   /* several of the same building in one town at once: one post */
 Object.values(pg).forEach(x=>{const P=S.props||[];x[2].q=P.filter(p=>(pcity(p.city)||{}).name===x[2].c).length;x[2].tq=P.length;x[2].tc=new Set(P.map(p=>p.city)).size;out.push([x[0],x[1],x[2],true]);});
 const un={};nu.filter(x=>x[1]==='units').forEach(x=>{un[x[2].i]=x;});Object.values(un).forEach(x=>out.push(x));   /* only the highest new count of each kind of unit */
 if(out.length)wallPush(out);else if(!wallT&&!wallBusy&&wallQ().some(x=>x.o===wallOwner()))wallFlushSoon(4000);}catch(e){}}
function wallPush(list){const o=wallOwner(),t=Date.now(),Q=wallQ();
 list.forEach(x=>{const d=x[2];
  if(x[1]==='prop'){const m=Q.find(y=>y.o===o&&y.kind==='prop'&&y.d.c===d.c&&y.d.t===d.t&&(y.d.dev||0)===(d.dev||0));   /* bought another one while the first is still waiting to post: one post for both */
   if(m){m.d.n+=d.n;m.d.v+=d.v;m.d.q=d.q;m.d.tq=d.tq;m.d.tc=d.tc;m.t=t;return;}}
  if(x[1]==='units'){const m=Q.find(y=>y.o===o&&y.kind==='units'&&y.d.i===d.i);if(m){m.d=d;m.k=x[0];m.t=t;return;}}
  Q.push({o,k:x[0],kind:x[1],d,big:!!x[3],t});});
 wallQSet(Q);wallFlushSoon(1800);}
function wallFlushSoon(ms){clearTimeout(wallT);wallT=setTimeout(wallFlush,ms||2000);}
async function wallFlush(){wallT=null;if(wallBusy)return;const o=wallOwner();if(!o)return;const mine=wallQ().filter(x=>x.o===o);if(!mine.length)return;wallBusy=true;
 try{let key='';if(o==='g'){key=wallKey();if(!key){const r=await api('POST','/api/wall/guest',{region:(S&&S.region)||''});key=r.key;try{localStorage.setItem('hs-gp',key);}catch(e){}}}
  const send=mine.slice(0,20),r=await api('POST','/api/wall/post',{key:key||undefined,region:(S&&S.region)||'',items:send.map(x=>({k:x.k,kind:x.kind,d:x.d}))});
  wallQSet(wallQ().filter(x=>!(x.o===o&&send.some(s=>s.k===x.k))));wallMine=null;
  const hot=(r.posted||[]).filter(p=>{const s=send.find(x=>x.k===p.k);return s&&s.big&&Date.now()-s.t<15*60000;});
  let first=false;try{first=!localStorage.getItem('hs-wallseen')&&(r.posted||[]).length>0;if(first)localStorage.setItem('hs-wallseen','1');}catch(e){}
  const top=L=>L.slice().sort((x,y)=>WALL_TOP.indexOf(x.kind)-WALL_TOP.indexOf(y.kind))[0];   /* the note shows the biggest of them */
  if(hot.length)wallToast(top(hot),hot.length,0,first);else if(first)wallToast(top(r.posted),r.posted.length,0,true);
  if(wallQ().some(x=>x.o===o))wallFlushSoon(1500);}
 catch(e){if(e&&e.status===401&&o==='g'){try{localStorage.removeItem('hs-gp');}catch(x){}}}   /* an unknown guest key: start a new profile next time */
 finally{wallBusy=false;}}
/* a big moment: a small note that it is on the profile, ready to share */
function wallToast(p,n,tries,first){tries=tries||0;if((document.querySelector('.rankup')||(typeof current!=='undefined'&&current&&current.cat==='Finish line'))&&tries<12){setTimeout(()=>wallToast(p,n,tries+1,first),1500);return;}
 toast('<b>\u{1F4E3} '+(first?'Your public profile is live':'Posted to your profile')+'</b><span>'+p.ico+' '+esc(capFirst(p.text))+(n>1?' (+'+(n-1)+' more)':'')+'</span><span class="tshare">Tap to see it and share it</span>','myprofile');}
/* a new account made from a guest game keeps the guest's profile: the server moves it, and anything still waiting to be posted follows */
function wallAdopt(uid){wallQSet(wallQ().map(x=>x.o==='g'?Object.assign(x,{o:'u'+uid}):x));try{localStorage.removeItem('hs-gp');}catch(e){}}
/* ---- screens ---- */
async function openProfile(){stopAuto();closeModal();try{closeMore();}catch(e){}{const t=$('hstoast');if(t)t.hidden=true;}acctView='profile';wallMsg='';wallMine=null;renderAccts();try{window.scrollTo(0,0);const A=$('acct');if(A)A.scrollTop=0;}catch(e){}
 try{await wallFlush();}catch(e){}const o=wallOwner(),key=o==='g'?wallKey():'';
 try{wallMine=o==='g'&&!key?{none:true}:await api('POST','/api/wall/mine',{key:key||undefined});}catch(e){wallMine={err:e.message};}
 if(acctView==='profile')renderAccts();}
async function openWall(handle,back){stopAuto();closeModal();{const t=$('hstoast');if(t)t.hidden=true;}wallBack=back!=null?back:(acctView&&acctView!=='wall'?acctView:wallBack);acctView='wall';wallMsg='';wallView=null;renderAccts();try{const A=$('acct');if(A)A.scrollTop=0;}catch(e){}
 try{wallView=await api('GET','/api/wall?h='+encodeURIComponent(handle));}catch(e){wallView={err:e.message};}if(acctView==='wall')renderAccts();}
function wallGoBack(){const b=wallBack;wallBack=null;if(b==='friends'){acctView='friends';renderAccts();}else if(b==='profile')openProfile();else if(b==='board'){acctView='board';renderAccts();}else{acctView=null;renderAccts();render();}}
function wallHead(d){return'<div class="me whead">'+avatar({name:d.name,color:d.color},true)+'<div><h2>'+esc(d.name)+'</h2><p class="sub">'+['@'+d.handle,d.company].filter(Boolean).map(esc).join(' · ')+'</p></div></div>'+
 '<div class="wstats"><div><small>Top rank</small><b>'+esc(d.top||'—')+'</b></div><div><small>Highlights</small><b>'+(d.count||0)+'</b></div></div>';}
function wallPostsHTML(d,own){const P=d.posts||[];if(!P.length)return'<p class="sub wempty">'+(own?'Nothing yet. Your highlights land here by themselves: your first million, billion and trillion, luxury buys, weddings and babies, your foundation\'s work and the titles your teams win.':'No highlights yet.')+'</p>';
 const canRx=!own&&ACC&&!GUEST&&!d.me;
 return'<ul class="wposts">'+P.map(p=>{const line=p.who&&p.who!==d.name?'<b>'+esc(p.who)+'</b> '+esc(p.text):esc(capFirst(p.text));
  const rx=canRx?(p.kind==='obit'?WALL_RX_SAD:WALL_RX).map(e=>{const n=(p.reacts||{})[e]||0;return'<button class="react'+(p.mine===e?' on':'')+'" data-a="wallreact" data-v="'+p.id+'" data-e="'+e+'" aria-label="React '+e+'">'+e+(n?' '+n:'')+'</button>';}).join(''):
   Object.keys(p.reacts||{}).map(e=>'<span class="react on">'+e+' '+p.reacts[e]+'</span>').join('');
  return'<li><span class="wico" aria-hidden="true">'+p.ico+'</span><div class="wbody"><p>'+line+'</p><span class="wmeta">'+esc(p.ago)+'</span>'+(rx?'<span class="reacts">'+rx+'</span>':'')+'</div>'+
   (own?'<button class="wdel" data-a="wallhide" data-v="'+p.id+'" aria-label="Remove this post">✕</button>':'')+'</li>';}).join('')+'</ul>';}
function profileHTML(){const d=wallMine;let h='<h2>My profile</h2>';
 if(!d)return h+'<p class="sub">Loading…</p>';
 if(d.err)return h+'<p class="amsg">'+esc(d.err)+'</p><div class="chips"><button class="btn" data-a="acctclose">Back to my game</button></div>';
 if(d.none)return h+'<p class="sub">Your public profile starts with your first highlight: your first million, a luxury buy, a wedding, your foundation or a title for your team. It appears here with a link you can share.</p><div class="chips"><button class="btn primary" data-a="acctclose">Back to my game</button></div>';
 h=wallHead(d)+'<div class="wlink"><span class="wurl">'+esc(d.link.replace(/^https?:\/\//,''))+'</span><div class="chips"><button class="btn primary small" data-a="wallshare">📤 Share my profile</button><button class="btn small" data-a="wallcopy">Copy link</button><a class="btn ghost small" href="'+esc(d.link)+'" target="_blank" rel="noopener">Open page</a></div></div>';
 if(wallMsg)h+='<p class="amsg">'+wallMsg+'</p>';
 if(d.guest)h+='<div class="wguest"><p><b>You are playing as a guest</b>, so your profile has a guest name. Save your empire to put your own name on it. Your posts and your link come with you.</p><button class="btn small" data-a="accts">Save my empire</button></div>';
 h+='<h3>Who can see it</h3><div class="seg wseg" role="group" aria-label="Who can see my profile"><button data-a="wallpriv" data-v="0" aria-pressed="'+!d.private+'">🌍 Everyone</button><button data-a="wallpriv" data-v="1" aria-pressed="'+!!d.private+'">🔒 Only friends</button></div>'+
  '<p class="hint">'+(d.private?'Only friends you added can see your profile, and your news stays out of the Live feed. The link shows that the profile is private.':'Anyone with your link can see it, and your highlights show in the Live feed. It is not listed on Google.')+'</p>';
 h+='<h3>Highlights</h3><p class="hint">Posted automatically: your first million, billion and trillion, luxury buys, weddings, babies and divorces, your foundation\'s work and the titles your teams win. Tap ✕ to take one down.</p>'+wallPostsHTML(d,true);
 return h+'<div class="chips stickynav"><button class="btn" data-a="acctclose">← My game</button>'+(ACC&&!GUEST?'<button class="btn ghost" data-a="liveopen">Live feed</button>':'')+'</div>';}
function wallViewHTML(){const d=wallView;let h='';
 if(!d)return'<h2>Profile</h2><p class="sub">Loading…</p>';
 if(d.err)return'<h2>Profile</h2><p class="amsg">'+esc(d.err)+'</p><div class="chips"><button class="btn" data-a="wallback">Back</button></div>';
 h=wallHead(d);if(wallMsg)h+='<p class="amsg">'+wallMsg+'</p>';
 const acts=[];if(ACC&&!GUEST&&!d.me&&d.uid&&!d.friend)acts.push('<button class="btn primary small" data-a="walladd" data-v="'+d.uid+'">+ Add friend</button>');
 if(ACC&&!GUEST&&d.friend)acts.push('<button class="btn small" data-a="wallmsg" data-v="'+d.uid+'">💬 Message</button>');
 if(!d.hidden)acts.push('<a class="btn ghost small" href="'+esc(d.link)+'" target="_blank" rel="noopener">Open page</a>');
 if(acts.length)h+='<div class="chips">'+acts.join('')+'</div>';
 if(d.guest)h+='<p class="hint">A guest player. They have not created an account yet.</p>';
 h+=d.hidden?'<p class="sub wempty">🔒 This profile is private.</p>':'<h3>Highlights</h3>'+wallPostsHTML(d,!!d.me);
 return h+'<div class="chips stickynav"><button class="btn" data-a="wallback">← Back</button></div>';}
async function wallHide(id){const key=wallOwner()==='g'?wallKey():'';try{await api('POST','/api/wall/hide',{id,key:key||undefined});if(wallMine&&wallMine.posts){wallMine.posts=wallMine.posts.filter(p=>p.id!==id);wallMine.count=Math.max(0,(wallMine.count||1)-1);}wallMsg='Taken down. It is off your profile and the feed.';}catch(e){wallMsg=esc(e.message);}renderAccts();}
async function wallPrivacy(on){const key=wallOwner()==='g'?wallKey():'';try{await api('POST','/api/wall/privacy',{private:on,key:key||undefined});if(wallMine)wallMine.private=on;wallMsg=on?'Your profile is now for friends only.':'Your profile is public again.';}catch(e){wallMsg=esc(e.message);}renderAccts();}
function wallShareText(d){return'My empire on Hustlempires, the free business game: '+(d.top?d.top+', ':'')+(d.count||0)+' highlight'+(d.count===1?'':'s')+' so far. Can you build a bigger one? 👑';}
async function wallShare(){const d=wallMine;if(!d||!d.link)return;const text=wallShareText(d);
 try{if(navigator.share){await navigator.share({title:'Hustlempires',text,url:d.link});return;}}catch(e){if(e&&e.name==='AbortError')return;}
 const u='https://wa.me/?text='+encodeURIComponent(text+' '+d.link);try{window.open(u,'_blank','noopener');}catch(e){location.href=u;}}
async function wallCopy(){const d=wallMine;if(!d||!d.link)return;try{await navigator.clipboard.writeText(d.link);wallMsg='Link copied. Paste it in WhatsApp, TikTok or Instagram.';}catch(e){wallMsg='Copy this link: '+esc(d.link);}renderAccts();}
async function wallReact(id,e){const d=wallView,p=d&&(d.posts||[]).find(x=>x.id===id);if(!p)return;try{const r=await api('POST','/api/feed/react',{id,e});p.reacts=r.reacts||{};p.mine=r.mine||'';}catch(er){wallMsg=esc(er.message);}renderAccts();}
async function wallAddFriend(id){try{const r=await api('POST','/api/friends/add',{id});wallMsg=esc(r.name)+' is now your friend.';if(wallView)wallView.friend=true;}catch(e){wallMsg=esc(e.message);}renderAccts();}
async function wallMessage(id){await openFriends('friends');msgPick(id);}
/* ---------- Live feed: everyone's highlights as they happen. Guests can watch; an account is needed to cheer or reply ---------- */
let liveData=null,liveScope='world',liveT=null,liveMsg='',livePick=0,stripI=null;
const ctryOf=c=>{const r=c&&countryRow(String(c).toUpperCase());return r?r.name:'';};
const flagOf=c=>{c=String(c||'').toUpperCase();return/^[A-Z]{2}$/.test(c)?String.fromCodePoint(...[...c].map(x=>0x1F1E6+x.charCodeAt(0)-65)):'';};
const liveSigned=()=>!!(ACC&&!GUEST);
function liveURL(scope){return'/api/live?scope='+scope+'&region='+encodeURIComponent((S&&S.region)||'')+(liveSigned()?'':'&vid='+encodeURIComponent(visitorId()));}
async function openLive(scope){stopAuto();closeModal();try{closeMore();}catch(e){}{const t=$('hstoast');if(t)t.hidden=true;}
 if(scope)liveScope=scope;if(liveScope!=='friends'||!liveSigned())liveScope=scope==='friends'&&liveSigned()?'friends':'world';acctView='live';liveMsg='';livePick=0;liveData=null;renderAccts();try{const A=$('acct');if(A)A.scrollTop=0;window.scrollTo(0,0);}catch(e){}
 clearInterval(liveT);liveT=setInterval(()=>{if(acctView!=='live'){clearInterval(liveT);liveT=null;return;}if(!document.hidden&&!livePick)liveLoad(false);},20000);
 await liveLoad(true);}
async function liveLoad(first){const sc=liveScope;let d;try{d=await api('GET',liveURL(sc));}catch(e){if(!liveData)liveData={err:e.message,items:[]};if(acctView==='live')first?renderAccts():livePatch();return;}
 if(sc!==liveScope)return;const old=liveData&&liveData.scope===d.scope&&liveData.items?new Set(liveData.items.map(i=>i.id)):null;
 d.items.forEach(i=>{i.fresh=!!(old&&!old.has(i.id));});liveData=d;if(acctView!=='live')return;first?renderAccts():livePatch();}
function livePlaying(d){const p=d&&d.playing;if(!p)return'';const n=p.world;return n>=1?'🟢 '+n+' playing now':'';}
function livePatch(){const L=$('livelist');if(!L){renderAccts();return;}L.innerHTML=liveListHTML();const P=$('liveplaying');if(P)P.textContent=livePlaying(liveData);const M=$('livemsg');if(M){M.innerHTML=liveMsg;M.hidden=!liveMsg;}}
function liveHTML(){const sg=liveSigned();
 let h='<div class="livehead"><h2><span class="livedot" aria-hidden="true"></span>Live</h2><span class="liveon" id="liveplaying">'+livePlaying(liveData)+'</span></div>'+
  '<p class="sub">Real players\' highlights the moment they happen: millions and billions, properties around the world, luxury buys, weddings, foundations, titles and records.</p>'+
  (sg?'<div class="seg livetabs" role="group" aria-label="Whose highlights" style="grid-template-columns:1fr 1fr"><button data-a="livescope" data-v="world" aria-pressed="'+(liveScope!=='friends')+'">🌍 Everyone</button><button data-a="livescope" data-v="friends" aria-pressed="'+(liveScope==='friends')+'">👥 Friends</button></div>':'');
 if(!sg)h+='<div class="liveguest"><span>👀 You are watching as a guest. Save your empire to cheer and reply.</span><button class="btn small primary" data-a="accts">Save my empire</button></div>';
 h+='<p class="amsg" id="livemsg"'+(liveMsg?'':' hidden')+'>'+liveMsg+'</p><div id="livelist">'+liveListHTML()+'</div>';
 return h+'<div class="chips stickynav"><button class="btn" data-a="acctclose">← My game</button><button class="btn ghost" data-a="myprofile">My profile</button>'+(sg?'<button class="btn ghost" data-a="friendsmsg">Friends</button>':'')+'</div>';}
function liveListHTML(){const d=liveData;
 if(!d)return'<p class="sub">Loading…</p>';if(d.err)return'<p class="amsg">'+esc(d.err)+'</p>';
 if(!d.items.length)return'<div class="liveempty"><p>'+(liveScope==='friends'?'No highlights from your friends yet. Add friends from their profiles, or invite them.':'No highlights yet. They appear here the moment a player anywhere makes their first million, their first billion, sets a record or makes a major purchase.')+'</p>'+(liveScope==='friends'?'<button class="btn small" data-a="livescope" data-v="world">See everyone</button>':'')+'</div>';
 const sg=liveSigned(),R=d.reacts||WALL_RX;
 return d.items.map(i=>{i.name=String(i.name||'A player').trim();const who=i.who&&i.who!==i.name?'<b>'+esc(i.who)+'</b> '+esc(i.text):esc(capFirst(i.text)),rp=i.replies||{n:0,last:[]};
  const rx=i.me?Object.keys(i.reacts||{}).map(e=>'<span class="react on">'+e+' '+i.reacts[e]+'</span>').join(''):
   (i.kind==='obit'?(d.reactsSad||WALL_RX_SAD):R).map(e=>{const n=(i.reacts||{})[e]||0;return'<button class="react'+(i.mine===e?' on':'')+'" data-a="livereact" data-v="'+i.id+'" data-e="'+e+'" aria-label="React '+e+'">'+e+(n?' '+n:'')+'</button>';}).join('');
  let f='<div class="lfoot"><span class="reacts">'+rx+'</span>'+(i.me?(rp.n?'<span class="lrn">💬 '+rp.n+'</span>':''):'<button class="btn ghost small lrbtn" data-a="livereply" data-v="'+i.id+'">💬 '+(i.myReply?'Replied':'Reply')+(rp.n?' · '+rp.n:'')+'</button>')+'</div>';
  if(rp.last.length)f+='<ul class="lreplies">'+rp.last.map(r=>'<li><b>'+esc(r.name)+'</b> '+esc(r.text)+'</li>').join('')+(rp.n>rp.last.length?'<li class="lmore">+'+(rp.n-rp.last.length)+' more</li>':'')+'</ul>';
  if(livePick===i.id&&d.replies)f+='<div class="lpick">'+((i.kind==='obit'&&d.repliesSad)||d.replies).map(([k,t])=>'<button class="btn small'+(i.myReply===k?' primary':'')+'" data-a="livesay" data-v="'+i.id+'" data-c="'+k+'">'+esc(t)+'</button>').join('')+'<button class="btn ghost small" data-a="livereply" data-v="0">Cancel</button></div>';
  return'<article class="lcard k-'+esc(i.kind)+(i.fresh?' fresh':'')+'"><header>'+(i.handle?'<button class="wavbtn" data-a="wallopen" data-v="'+esc(i.handle)+'" aria-label="Open '+esc(i.name)+'\'s profile">'+avatar(i)+'</button>':avatar(i))+
   '<div class="lwho">'+(i.handle?'<button class="linkbtn wname" data-a="wallopen" data-v="'+esc(i.handle)+'">'+esc(i.name)+'</button>':'<b>'+esc(i.name)+'</b>')+'<small>'+(ctryOf(i.region)?esc(ctryOf(i.region))+' · ':'')+(i.guest?'Guest player':esc(i.company||''))+' · '+esc(i.ago)+'</small></div></header>'+
   '<div class="lhl"><span class="lico" aria-hidden="true">'+i.ico+'</span><p>'+who+'</p></div>'+f+'</article>';}).join('');}
function liveNeedAcct(){if(liveSigned())return false;guestWhy='feature';guestAsk('feature');return true;}
async function liveReact(id,e){if(liveNeedAcct())return;const it=liveData&&liveData.items.find(x=>x.id===id);if(!it)return;
 try{const r=await api('POST','/api/feed/react',{id,e});it.reacts=r.reacts||{};it.mine=r.mine||'';liveMsg='';}catch(er){liveMsg=esc(er.message);}livePatch();}
function liveReplyPick(id){if(id&&liveNeedAcct())return;livePick=id;livePatch();}
async function liveSay(id,code){const it=liveData&&liveData.items.find(x=>x.id===id);if(!it)return;
 try{const r=await api('POST','/api/live/reply',{id,code});const me=(playerName()||(ACC&&ACC.name)||'You').split(' ')[0],txt=((liveData.replies||[]).find(x=>x[0]===code)||[])[1]||'';
  const rp=it.replies=it.replies||{n:0,last:[]};rp.last=[{name:me,text:txt}].concat(rp.last.filter(x=>!(x.name===me&&it.myReply))).slice(0,3);rp.n=r.n;it.myReply=code;liveMsg='';}catch(er){liveMsg=esc(er.message);}
 livePick=0;livePatch();}
/* the live strip on the game screen: the newest highlight from anyone, or how many people are playing right now */
function stripSeen(){try{return+(localStorage.getItem('hs-lseen')||0);}catch(e){return 0;}}
/* the floating ticker: the latest highlights from the last 6 hours take turns, a new one jumps to the front */
let stripList=[],stripIdx=0,stripR=null;
/* your own place on the leaderboard takes its turn in the ticker: where you stand, who is next, and every climb or fall as it happens */
function stripMeItem(){const d=typeof seasonCache!=='undefined'?seasonCache:null;if(!ACC||GUEST||!S||!d||!S.sea||d.season!==S.sea.id)return null;const me=d.me,c=countryRow(S.region)||{name:'your country'};
 if(!me||!me.rankRegion)return{id:'me',me:1,h:'🏆 <b>Play a month</b> to get on the '+esc(c.name)+' leaderboard this season',ago:'Board'};
 return{id:'me',me:1,h:'You are <b>#'+me.rankRegion+'</b> of '+me.playersRegion+' in '+esc(c.name)+(me.ahead?' · <b>'+me.ahead.gap.toLocaleString('en-US')+'</b> points behind '+esc(me.ahead.name):' · <b>top of the board</b>')+(me.rank?' · #'+me.rank+' worldwide':''),ago:'Board'};}
function stripMix(L){const m=stripMeItem();if(!m)return L;const out=[m];L.forEach((x,i)=>{out.push(x);if(i%3===2&&i<L.length-1)out.push(m);});return out;}
function stripMeRefresh(){const m=stripMeItem();if(!m)return;if(!stripList.some(x=>x.id==='me')){stripList=stripMix(stripList.filter(x=>x.id!=='flash'));}else stripList=stripList.map(x=>x.id==='me'?m:x);const cur=stripList[stripIdx];if(cur&&cur.id==='me')stripShow(false);}
function stripOn(){const el=$('livestrip');return!!(el&&!el.hidden&&!stripMin());}   /* the ticker carries the news; the pop-up only when the ticker is tucked away */
function stripFlash(h,up){stripList=[{id:'flash',me:1,flash:up?'up':'down',h,ago:'Board'}].concat(stripList.filter(x=>x.id!=='flash'));stripIdx=0;stripShow(true,true);
 clearTimeout(stripFlash.t);stripFlash.t=setTimeout(()=>{const was=stripList[stripIdx]&&stripList[stripIdx].id;stripList=stripList.filter(x=>x.id!=='flash');const k=stripList.findIndex(x=>x.id===was);stripIdx=k<0?0:k;},30000);}
function stripMin(){try{return localStorage.getItem('hs-lsmin')==='1';}catch(e){return false;}}
function stripMinToggle(){const m=!stripMin();try{localStorage.setItem('hs-lsmin',m?'1':'0');}catch(e){}stripShow(false);}
function stripPlace(){const t=document.querySelector('nav.tabs');document.documentElement.style.setProperty('--tabh',((t&&phoneUI()?t.getBoundingClientRect().height:0)||0)+'px');}
function stripVis(){const el=$('livestrip');if(!el)return;const off=!stripList.length||!!acctView||!S||!S.inds||!S.inds.length||(!ACC&&!GUEST);el.hidden=off;document.documentElement.classList.toggle('lson',!off&&!stripMin());if(!off)stripPlace();}
function stripShow(anim,pop){const el=$('livestrip');if(!el)return;const it=stripList[stripIdx%Math.max(1,stripList.length)];if(el.parentNode!==document.body)document.body.appendChild(el);el.classList.add('lsfloat');
 if(!it){stripVis();return;}const mn=stripMin();el.classList.toggle('lsmin',mn);el.classList.toggle('lsme',!!it.me);el.classList.toggle('lsup',it.flash==='up');el.classList.toggle('lsdown',it.flash==='down');el.dataset.a=mn?'lsmin':it.me?'leaderboard':'liveopen';el.setAttribute('aria-label',mn?'Show the live news':it.me?'Open the leaderboard':'Open the live feed');
 el.innerHTML='<span class="lsbadge">'+(it.me&&!mn?(it.flash==='up'?'⬆️ YOU':it.flash==='down'?'⬇️ YOU':'🏆 YOU'):'<span class="lsdot"></span>LIVE')+'</span><span class="lstext'+(anim?' lsin':'')+'">'+it.h+'</span><span class="lsago">'+esc(it.ago)+' ›</span><span class="lsx" data-a="lsmin" role="button" aria-label="Tuck the live news away">✕</span>';
 if(pop){el.classList.remove('lspop');void el.offsetWidth;el.classList.add('lspop');}stripVis();}
async function stripTick(){const el=$('livestrip');if(!el)return;if(document.hidden||!S||!S.inds||!S.inds.length||(!ACC&&!GUEST)){stripVis();return;}
 let d;try{d=await api('GET',liveURL('world'));}catch(e){return;}
 const now=d.now||Math.floor(Date.now()/1000),recent=(d.items||[]).filter(i=>!i.me&&now-i.ts<6*3600).slice(0,8),seen=stripSeen(),n=(d.playing||{}).world||0;
 const cur=stripList[stripIdx]&&stripList[stripIdx].id;
 stripList=recent.map(top=>{const nm=esc(((top.who&&top.who!==top.name?top.who:top.name)||'A player').split(' ').slice(0,top.guest?2:1).join(' '));return{id:top.id,h:'<b>'+nm+'</b> '+esc(top.text),ago:top.ago};});
 if(!stripList.length&&n>=2)stripList=[{id:0,h:'🟢 <b>'+n+' players</b> are building empires right now',ago:'See'}];
 stripList=stripMix(stripList);
 const isNew=recent.length&&recent[0].id>seen;
 if(isNew){try{localStorage.setItem('hs-lseen',String(recent[0].id));}catch(e){}stripIdx=Math.max(0,stripList.findIndex(x=>x.id===recent[0].id));stripShow(true,true);return;}
 const k=stripList.findIndex(x=>x.id===cur);stripIdx=k<0?0:k;stripShow(false);}
function stripRotate(){if(document.hidden||stripList.length<2||stripMin()||acctView)return;stripIdx=(stripIdx+1)%stripList.length;stripShow(true);}
function stripStart(){if(stripI)return;setTimeout(stripTick,6000);stripI=setInterval(stripTick,45000);stripR=setInterval(stripRotate,6000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(stripTick,800);});window.addEventListener('resize',stripPlace);}
stripStart();
{const _ra=renderAccts;renderAccts=function(){const r=_ra.apply(this,arguments);try{stripVis();}catch(e){}return r;};}   /* hide behind full-screen pages, back when they close */
/* ---------- Live rivals: you passed someone, or someone passed you ---------- */
let rivalPrev=null,rivalT=null;
function toast(html,act){let t=$('hstoast');if(!t){t=document.createElement('button');t.id='hstoast';t.className='hstoast';document.body.appendChild(t);}
 t.innerHTML=html;t.dataset.a=act||'';t.hidden=false;t.classList.remove('out');clearTimeout(toast.h);toast.h=setTimeout(()=>{t.classList.add('out');setTimeout(()=>t.hidden=true,400);},6000);}
async function rivalCheck(){if(!ACC||!S||S.over||acctView||document.hidden)return;let d;try{d=await api('GET','/api/season?scope=country&region='+encodeURIComponent(S.region||''));}catch(e){return;}
 seasonCache=d;try{stripMeRefresh();}catch(e){}const me=d&&d.me;if(!me)return;const now={id:d.season,r:me.rankRegion,ahead:me.ahead&&me.ahead.name};
 if(rivalPrev&&rivalPrev.id===now.id&&!current&&$('modal').hidden){
  if(now.r!==rivalPrev.r)try{stripFlash(now.r<rivalPrev.r?'You climbed to <b>#'+now.r+'</b>'+(rivalPrev.ahead?', passing '+esc(rivalPrev.ahead):'')+(me.ahead?' · next: '+esc(me.ahead.name)+', '+me.ahead.gap.toLocaleString('en-US')+' points ahead':' · nobody is ahead of you'):esc(now.ahead||'A rival')+' passed you · you are <b>#'+now.r+'</b> now'+(me.ahead?', '+me.ahead.gap.toLocaleString('en-US')+' points behind':''),now.r<rivalPrev.r);}catch(e){}
  if(stripOn()){}else if(now.r<rivalPrev.r)toast('<b>🏆 You passed '+esc(rivalPrev.ahead||'a rival')+'!</b><span>You are now #'+now.r+' in your country this season.'+(me.ahead?' Next up: '+esc(me.ahead.name)+', '+me.ahead.gap.toLocaleString('en-US')+' points ahead.':' Nobody is ahead of you.')+'</span>','leaderboard');
  else if(now.r>rivalPrev.r)toast('<b>⚠️ '+esc(now.ahead||'A rival')+' just passed you</b><span>You dropped to #'+now.r+' in your country. They are '+(me.ahead?me.ahead.gap.toLocaleString('en-US'):'a few')+' points ahead. Take it back.</span>','leaderboard');}
 rivalPrev=now;}
function rivalStart(){clearInterval(rivalT);rivalPrev=null;setTimeout(rivalCheck,6000);rivalT=setInterval(rivalCheck,90000);}
/* ---------- Bank auctions: seized buildings other players can buy ---------- */
let bankLots=null,bankT=0,bankMsg='',bankBusy=false;
function bankPost(lots){if(!S)return;S.bankOut=(S.bankOut||[]).concat(lots).slice(-60);bankFlush();}
let bankFlushing=false;
async function bankFlush(){if(bankFlushing||!ACC||!S||!S.bankOut||!S.bankOut.length)return;bankFlushing=true;const L=S.bankOut.splice(0,30);
 try{await api('POST','/api/bank/list',{region:S.region||'',lots:L});}catch(e){S.bankOut=L.concat(S.bankOut||[]);}
 bankFlushing=false;save();if(S.bankOut&&S.bankOut.length)setTimeout(bankFlush,1500);}
async function bankLoad(force){if(!ACC||bankBusy)return;if(!force&&Date.now()-bankT<60000)return;bankT=Date.now();bankBusy=true;
 try{const d=await api('GET','/api/bank/lots?region='+encodeURIComponent(S.region||''));bankLots=d.lots||[];}catch(e){if(bankLots===null)bankLots=[];}
 bankBusy=false;if(typeof curTab!=='undefined'&&curTab==='property')render();}
function bankRowsHTML(){if(bankLots===null){bankLoad(true);return'<p class="seghint">Checking with the bank…</p>';}bankLoad();
 let h=bankMsg?'<p class="amsg" style="margin-bottom:10px">'+bankMsg+'</p>':'';
 if(!bankLots.length)return h;
 return h+bankLots.map(l=>{const t=ptype(l.type),c=pcity(l.city);if(!t||!c)return'';const open=cityOpen(c),afford=S.cash>=l.price;
  return'<div class="ptype banklot"><div class="top">'+picon(l.type)+'<div class="ptx"><b>'+esc(l.name)+'</b><span>'+t.name+' · '+esc(c.name)+' · worth '+fmt(l.value)+'</span><span class="bankmeta"><em>30% off</em> · seized from '+esc(l.from||'a player')+' · '+l.daysLeft+' day'+(l.daysLeft>1?'s':'')+' left</span></div></div>'+
   '<div class="chips"><button class="btn small '+(open&&afford?'primary':'')+'" data-a="bankbuy" data-v="'+l.id+'"'+(open&&afford?'':' disabled')+'>'+(open?'Buy · '+fmt(l.price):'Unlock '+esc(c.name)+' first')+'</button></div></div>';}).join('');}
async function bankBuy(id){const l=(bankLots||[]).find(x=>x.id===id);if(!l)return;const t=ptype(l.type),c=pcity(l.city);
 if(!t||!c||!cityOpen(c)||S.cash<l.price||S.over)return;bankMsg='';
 try{const r=await api('POST','/api/bank/buy',{id});const L=r.lot;S.cash-=L.price;S.props=S.props||[];
  S.props.push({type:L.type,city:L.city,name:propName(t,c),af:L.af,left:0,total:L.total||t.build,occ:L.occ||.9,anchor:0,was:L.name});
  propUnlockCheck();log('You bought '+L.name+' at a bank auction for '+fmt(L.price)+'. It is worth '+fmt(L.value)+'.','gold');
  bankMsg='Yours. You picked up a '+fmt(L.value)+' building for '+fmt(L.price)+'.';try{coinBurst(14);}catch(e){}
  bankLots=bankLots.filter(x=>x.id!==id);afterChange();}
 catch(e){bankMsg=esc(e.message);bankT=0;bankLoad(true);}render();}
/* ---------- Marketplace: players sell buildings and luxury items to each other ---------- */
let mkTab='local',mkData={local:null,world:null,mine:null},mkT={},mkBusy={},mkMsg='',mkPending=null,mkFee=.05;
const MK_ICON={car1:'🚗',car2:'🚙',car3:'🚙',car4:'🚘',car5:'🚘',car6:'🚁',jet:'✈️',a1:'🏢',a2:'🏢',a3:'🏢',shoes:'👠',bags:'👜',wardrobe:'👗',birkin:'👜',jewels:'💎',watch:'⌚',horses:'🐎',villa:'🏖️',art:'🖼️',yacht:'🛥️',vineyard:'🍇',golfclub:'⛳',island:'🏝️',superyacht:'🛳️',trophyhotel:'🏨',masterpiece:'🖼️'};
function mkIcon(d){return d.k==='p'||d.type?picon(d.type):'<span class="mkicon" aria-hidden="true">'+(MK_ICON[d.id]||(/^h\d/.test(d.id)?'🏠':'💎'))+'</span>';}
async function mkLoad(tab,force){if(!ACC||mkBusy[tab])return;if(!force&&mkData[tab]&&Date.now()-(mkT[tab]||0)<45000)return;mkT[tab]=Date.now();mkBusy[tab]=true;
 try{const d=await api('GET',tab==='mine'?'/api/market/mine':'/api/market?scope='+tab+'&region='+encodeURIComponent(S.region||''));mkData[tab]=d.items||[];if(d.fee!=null)mkFee=d.fee;}catch(e){if(!mkData[tab])mkData[tab]=[];}
 mkBusy[tab]=false;if(typeof curTab!=='undefined'&&curTab==='property')render();}
function mkWho(d){const a=d.k==='a'?ASSETS.find(x=>x.id===d.id):null;return a;}
function mkRow(d){const pr=d.price,v=d.value,off=Math.round(100*(1-pr/v));let title=d.name,sub='',btn='';
 if(d.k==='p'){const t=ptype(d.type),c=pcity(d.city);if(!t||!c)return'';sub=t.name+' · '+esc(c.name);
  btn=!cityOpen(c)?'<button class="btn small" disabled>Unlock '+esc(c.name)+' first</button>':'<button class="btn small '+(S.cash>=pr?'primary':'')+'" data-a="mkbuy" data-v="'+d.lid+'"'+(S.cash>=pr?'':' disabled')+'>Buy · '+fmt(pr)+'</button>';}
 else{const a=mkWho(d);if(!a)return'';if(a.g&&S.g&&a.g!==S.g)return'';title=a.name;sub=a.kind;
  btn=(!a.stack&&has(a.id))?'<button class="btn small" disabled>You already own one</button>':'<button class="btn small '+(S.cash>=pr?'primary':'')+'" data-a="mkbuy" data-v="'+d.lid+'"'+(S.cash>=pr?'':' disabled')+'>Buy · '+fmt(pr)+'</button>';}
 return'<div class="ptype banklot mklot"><div class="top">'+mkIcon(d)+'<div class="ptx"><b>'+esc(title)+'</b><span>'+sub+' · worth '+fmt(v)+'</span><span class="bankmeta">'+(off>0?'<em>'+off+'% below value</em>':off<0?'<em class="mkup">'+(-off)+'% above value</em>':'<em class="mkeq">at value</em>')+' · sold by '+esc(d.from||'a player')+(mkTab==='world'&&d.region?' in '+esc((countryRow(d.region)||{name:d.region}).name):'')+' · '+Math.max(1,d.daysLeft)+' day'+(d.daysLeft>1?'s':'')+' left</span></div></div><div class="chips">'+btn+'</div></div>';}
function mkMineRow(d){const net=d.price*(1-mkFee);
 return'<div class="ptype mklot"><div class="top">'+mkIcon(d)+'<div class="ptx"><b>'+esc(d.k==='a'&&mkWho(d)?mkWho(d).name:d.name)+'</b><span>Asking '+fmt(d.price)+' · worth '+fmt(d.value)+'</span><span class="bankmeta">'+(d.status==='sold'?'<em>Sold</em> · you get '+fmt(net)+' after the '+Math.round(mkFee*100)+'% fee':'For sale · '+Math.max(1,d.daysLeft)+' day'+(d.daysLeft>1?'s':'')+' left · you would get '+fmt(net))+'</span></div></div>'+
  (d.status==='open'?'<div class="chips"><button class="btn ghost small" data-a="mkcancel" data-v="'+d.lid+'">Take it back</button></div>':'')+'</div>';}
function bankLotsHTML(){if(!ACC||!S||!S.inds.length)return null;
 const tabs='<div class="authtabs mktabs" role="tablist" style="grid-template-columns:1fr 1fr 1fr">'+[['local','Local'],['world','Worldwide'],['mine','My listings']].map(x=>'<button role="tab" aria-selected="'+(mkTab===x[0])+'" data-a="mktab" data-v="'+x[0]+'">'+x[1]+'</button>').join('')+'</div>';
 let h=tabs+(mkMsg?'<p class="amsg" style="margin:10px 0 0">'+mkMsg+'</p>':'')+(bankMsg?'<p class="amsg" style="margin:10px 0 0">'+bankMsg+'</p>':'');
 const L=mkData[mkTab];if(L===null){mkLoad(mkTab,true);return h+'<p class="seghint">Loading…</p>';}mkLoad(mkTab);
 if(mkTab==='mine'){const open=L.filter(x=>x.status==='open').length;
  return h+'<p class="seghint">'+(open?'You have '+open+' item'+(open>1?'s':'')+' for sale. ':'Nothing for sale yet. ')+'To sell, press <b>List for players</b> on a building (Property tab) or a luxury item, car or home (Life tab). You get the price minus a '+Math.round(mkFee*100)+'% fee. Unsold items come back after 7 days.</p>'+L.map(mkMineRow).join('');}
 let rows=L.map(mkRow).join('');
 if(mkTab==='local'){const b=bankRowsHTML();rows=(bankLots&&bankLots.length?'<h4 class="mkh">Bank auctions · 30% off</h4>'+b:'')+(rows?'<h4 class="mkh">From players in your country</h4>'+rows:'');}
 return h+(rows||'<p class="seghint">'+(mkTab==='local'?'Nothing for sale in your country right now. Be the first: press <b>List for players</b> on anything you own.':'Nothing for sale around the world right now.')+'</p>');}
function mkList(v){if(!S||S.over)return;const k=v[0],ref=v.slice(1);let name,value,obj=null;
 if(k==='p'){obj=S.props[+ref];if(!obj||obj.left>0)return;name=obj.name;value=propValue1(obj);}
 else{const a=ASSETS.find(x=>x.id===ref);if(!a||!has(ref))return;name=a.name;value=a.price*afx(ref);}
 mkPending={k,ref,obj,name,value};const P=[[.7,'Quick sale'],[.9,'Priced to sell'],[1,'At value'],[1.15,'A little above value'],[1.3,'Premium'],[1.5,'Top price']];
 showCard('Sell to other players',esc(name)+' is worth <b>'+fmt(value)+'</b>. Pick your asking price. Players in your country'+(k==='p'&&['nairobi','mombasa'].includes(obj.city)?'':' and around the world')+' can buy it. When it sells you get the price minus a '+Math.round(mkFee*100)+'% market fee. It leaves your empire while it is for sale; you can take it back any time, and if nobody buys it in 7 days it comes back to you.',
  P.map(x=>'<button class="choice" data-a="mkpost" data-v="'+x[0]+'"><b>Ask '+fmt(value*x[0])+'</b><span>'+x[1]+(x[0]!==1?' · '+Math.round(Math.abs(x[0]-1)*100)+'% '+(x[0]<1?'below':'above')+' value':'')+' · you get '+fmt(value*x[0]*(1-mkFee))+'</span></button>').join('')+'<button class="choice" data-a="closecard"><b>Keep it</b><span>Not now.</span></button>');}
function mkTakeAsset(id){const a=ASSETS.find(x=>x.id===id);S.assets[id]--;S.cust=S.cust||{};S.cust[id]=[];
 if(a.kind==='Homes'&&homeTier()<0){S.rent=a.tier;log('You now rent a '+a.name.lc()+' instead.','');}if(a.jet&&S.travel===4)S.travel=3;}
function mkGive(k,d,restore){if(k==='p'){const t=ptype(d.type),c=pcity(d.city);if(!t||!c)return;S.props=S.props||[];S.props.push({type:d.type,city:d.city,name:restore?d.name:propName(t,c),af:d.af,left:0,total:d.total||t.build,occ:d.occ||.9,anchor:0});propUnlockCheck();return;}
 const a=ASSETS.find(x=>x.id===d.id);if(!a)return;if(!a.stack&&has(a.id)){S.cash+=d.value*.9;log(a.name+' came back, but you already own one, so it was sold for '+fmt(d.value*.9)+'.','');return;}
 S.assets[a.id]=has(a.id)+1;S.af=S.af||{};if(restore||!S.af[a.id])S.af[a.id]=d.af||1;if(MODELS[a.id]){S.gen=S.gen||{};S.gen[a.id]=d.gen||0;}
 if(!restore&&a.lux&&a.rep)addRep(a.rep);if(a.kind==='Homes'&&S.rent>=0&&a.tier>=S.rent)S.rent=-1;}
async function mkPost(pct){const P=mkPending;closeModal();if(!P||!S)return;pct=+pct;let k=P.k,data;
 if(k==='p'){const i=S.props.indexOf(P.obj);if(i<0)return;data=bankLot(P.obj);S.props.splice(i,1);}
 else{if(!has(P.ref))return;data={id:P.ref,name:P.name,af:(S.af&&S.af[P.ref])||1,gen:(S.gen||{})[P.ref]||0,value:Math.round(P.value)};mkTakeAsset(P.ref);}
 const price=Math.round(P.value*pct);mkPending=null;afterChange();
 try{await api('POST','/api/market/list',{k,item:data,price,region:S.region||'',g:S.g||''});log('You put '+P.name+' up for sale at '+fmt(price)+'.','');mkMsg='Listed. '+esc(P.name)+' is for sale at '+fmt(price)+'.';mkTab='mine';mkData.mine=null;save();}
 catch(e){mkGive(k,data,true);showCard('Could not list it',esc(e.message),'<button class="choice" data-a="closecard"><b>OK</b></button>');}
 afterChange();render();}
function mkFind(lid){for(const t of['local','world','mine']){const x=(mkData[t]||[]).find(d=>d.lid===lid);if(x)return x;}return null;}
async function mkBuy(lid){const d=mkFind(lid);if(!d||!S||S.over||S.cash<d.price)return;mkMsg='';bankMsg='';
 try{const r=await api('POST','/api/market/buy',{id:lid});const it=r.item;S.cash-=it.price;mkGive(it.k,it,false);
  const nm=it.k==='a'&&mkWho(it)?mkWho(it).name:it.name;log('You bought '+nm+' from '+(it.from||'a player')+' for '+fmt(it.price)+'.','gold');
  mkMsg='Yours: '+esc(nm)+' for '+fmt(it.price)+'.';try{coinBurst(14);}catch(e){}save();}
 catch(e){mkMsg=esc(e.message);}mkData.local=mkData.world=null;afterChange();render();}
async function mkCancel(lid){try{const r=await api('POST','/api/market/cancel',{id:lid});const it=r.item;mkGive(it.k,it,true);log('You took '+(it.k==='a'&&mkWho(it)?mkWho(it).name:it.name)+' off the market.','');mkMsg='Taken off the market and back in your empire.';save();}
 catch(e){mkMsg=esc(e.message);}mkData.mine=null;afterChange();render();}
let mkSettleTries=0;
async function mkSettle(){if(!ACC||!S||S.over)return;if(current||!$('modal').hidden||acctView){if(++mkSettleTries<20)setTimeout(mkSettle,3000);return;}
 let r;try{r=await api('POST','/api/market/settle',{});}catch(e){return;}const lines=[];
 (r.sold||[]).forEach(it=>{const nm=it.k==='a'&&mkWho(it)?mkWho(it).name:it.name;S.cash+=it.net;log('Sold on the marketplace: '+nm+'. You received '+fmt(it.net)+' after the fee.','good');lines.push('<li><span>💰</span><span><b>'+esc(nm)+' sold</b>You received '+fmt(it.net)+' after the '+Math.round(mkFee*100)+'% fee.</span></li>');});
 (r.back||[]).forEach(it=>{const nm=it.k==='a'&&mkWho(it)?mkWho(it).name:it.name;mkGive(it.k,it,true);log(nm+' did not sell in 7 days and is back in your empire.','');lines.push('<li><span>↩️</span><span><b>'+esc(nm)+' did not sell</b>It is back in your empire. Try a lower price.</span></li>');});
 if(!lines.length)return;afterChange();render();save();
 const show=()=>{if(current||!$('modal').hidden){setTimeout(show,3000);return;}showCard('Marketplace news','While you were away:<ul class="awaylist">'+lines.join('')+'</ul>','<button class="choice" data-a="closecard"><b>Great</b></button>');};show();}
/* ---------- Players' exchange: buy shares in other players' companies ---------- */
let xcData=null,xcT=0,xcBusy=false,xcMsg='';
async function xcLoad(force){if(!ACC||xcBusy)return;if(!force&&xcData&&Date.now()-xcT<60000)return;xcT=Date.now();xcBusy=true;
 try{xcData=await api('GET','/api/xchg');S.xcv=newGameFlag?0:(xcData.holdings||[]).reduce((t,h)=>t+h.value,0);}catch(e){if(!xcData)xcData={companies:[],holdings:[],me:null};}
 xcBusy=false;if(typeof curTab!=='undefined'&&curTab==='money')render();}
const xcPx=p=>p>=100?fmt(p):curSym()+(curLocal()?p*R.rate:p).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
function xcHTML(){if(!ACC||!S||!S.inds.length)return null;if(!xcData){xcLoad(true);return'<p class="seghint">Loading the exchange…</p>';}xcLoad();
 const d=xcData,me=d.me,fee=Math.round((d.fee||.02)*100);let h=xcMsg?'<p class="amsg" style="margin:0 0 10px">'+xcMsg+'</p>':'';
 h+='<h4>Your company</h4>';
 if(me){const sold=Math.round(100*(me.float*1e6-me.avail)/1e6*10)/10;
  h+='<div class="pcbox on"><b>'+esc(ACC.company)+' is listed</b><span>Share price '+xcPx(me.px)+' · company value '+fmt(me.cap)+' · '+(me.chg>=0?'+':'')+(me.chg*100).toFixed(1)+'% this week</span><span>'+sold+'% of the company sold to '+d.holders+' investor'+(d.holders===1?'':'s')+' · '+Math.round(me.float*100)+'% for sale in total · you have raised '+fmt(d.raised||0)+'</span>'+
   (me.float<.3?'<div class="chips" style="margin-top:6px">'+[.2,.3].filter(f=>f>me.float).map(f=>'<button class="btn ghost small" data-a="xclist" data-v="'+f+'">Offer '+Math.round(f*100)+'% in total</button>').join('')+'</div>':'')+'</div>';}
 else if(d.canList)h+='<p class="seghint" style="margin:0 0 8px">List '+esc(ACC.company)+' and let other players buy a piece of it. Their money comes straight to you (less a '+fee+'% fee) and your share price follows your net worth.</p><div class="chips">'+[.1,.2,.3].map(f=>'<button class="btn small'+(f===.1?' primary':'')+'" data-a="xclist" data-v="'+f+'">Sell '+Math.round(f*100)+'% to the public</button>').join('')+'</div>';
 else h+='<p class="seghint" style="margin:0">You can list your company once your empire is worth '+fmt(d.minNw||1e7)+'.</p>';
 if(d.holdings&&d.holdings.length){h+='<h4>Your shares</h4>'+d.holdings.map(x=>{const g=x.value-x.cost;return'<div class="sec"><div class="nm"><b>'+esc(x.company)+'</b><span class="hold">Worth '+fmt(x.value)+' <span class="'+(g>=0?'pos':'neg')+'">'+(g>=0?'+':'−')+fmt(Math.abs(g))+' ('+(x.cost?(g>=0?'+':'')+Math.round(g/x.cost*100)+'%':'—')+')</span></span></div><div class="acts"><button class="btn ghost small" data-a="xcsell" data-v="'+x.id+'" data-f=".5">Sell ½</button><button class="btn ghost small" data-a="xcsell" data-v="'+x.id+'" data-f="1">Sell all</button></div></div>';}).join('');}
 const C=d.companies||[];h+='<h4>Listed companies'+(C.length?' ('+C.length+')':'')+'</h4>';
 if(!C.length)h+='<p class="seghint" style="margin:0">No player companies are listed yet. Be the first.</p>';
 else h+=C.slice(0,40).map(c=>{const ctry=(countryRow(c.region)||{name:''}).name,av=Math.round(c.avail/1e6*1000)/10;
  return'<div class="sec"><div class="nm"><b>'+esc(c.company)+'</b><span>'+esc(c.founder)+(ctry?' · '+esc(ctry):'')+' · worth '+fmt(c.cap)+'</span><span>'+(av>0?av+'% of the company for sale':'Sold out')+'</span></div><div class="px">'+xcPx(c.px)+'<small class="'+(c.chg>=0?'pos':'neg')+'">'+(c.chg>=0?'+':'')+(c.chg*100).toFixed(1)+'% wk</small></div><div class="acts"><button class="btn small" data-a="xcbuy" data-v="'+c.id+'"'+(av>0&&c.px>0&&S.cash>10?'':' disabled')+'>Buy</button></div></div>';}).join('');
 return h;}
function xcBuyCard(id){const c=(xcData&&xcData.companies||[]).find(x=>x.id===id);if(!c)return;const max=c.avail*c.px;
 const opts=[.05,.1,.25].map(f=>Math.min(Math.max(0,S.cash)*f,max)).filter((v,i,a)=>v>=1&&a.indexOf(v)===i);
 showCard('Buy shares in '+esc(c.company),'Founded by '+esc(c.founder)+'. Company worth '+fmt(c.cap)+', share price '+xcPx(c.px)+', '+(c.chg>=0?'up ':'down ')+Math.abs(c.chg*100).toFixed(1)+'% this week. Up to '+fmt(max)+' of shares are for sale. Your money goes to the founder. If their empire grows, your shares grow with it; if they go bankrupt, your shares are worth nothing.',
  opts.map(v=>'<button class="choice" data-a="xcgo" data-v="'+id+':'+Math.floor(v)+'"><b>Invest '+fmt(v)+'</b><span>'+(v>=max-1?'Every share that is left.':Math.round(v/Math.max(1,S.cash)*100)+'% of your cash.')+'</span></button>').join('')+'<button class="choice" data-a="closecard"><b>Not now</b><span>Keep your money.</span></button>');}
async function xcBuy(v){closeModal();const [id,amt]=String(v).split(':').map(Number);if(!(amt>0)||S.cash<amt)return;xcMsg='';
 try{const r=await api('POST','/api/xchg/buy',{id,amount:amt});S.cash-=r.cost;const c=(xcData.companies||[]).find(x=>x.id===id);log('You invested '+fmt(r.cost)+' in '+(c?c.company:'a player company')+'.','gold');xcMsg='Done. You invested '+fmt(r.cost)+'.';save();}
 catch(e){xcMsg=esc(e.message);}await xcLoad(true);afterChange();render();}
async function xcSell(id,frac){xcMsg='';try{const r=await api('POST','/api/xchg/sell',{id,frac});S.cash+=r.amount;log('You sold shares for '+fmt(r.amount)+'.',r.amount>0?'good':'bad');xcMsg='Sold for '+fmt(r.amount)+' after the fee.';save();}
 catch(e){xcMsg=esc(e.message);}await xcLoad(true);afterChange();render();}
async function xcList(f){xcMsg='';try{await api('POST','/api/xchg/list',{float:+f});log(ACC.company+' is now listed on the players\' exchange.','gold');xcMsg=esc(ACC.company)+' is listed. Other players can now buy up to '+Math.round(f*100)+'% of it.';}
 catch(e){xcMsg=esc(e.message);}await xcLoad(true);render();}
async function xcSettle(){if(!ACC||!S||S.over)return;try{const r=await api('POST','/api/xchg/settle',{});if(r.amount>0){S.cash+=r.amount;log('Investors bought shares in '+ACC.company+'. You raised '+fmt(r.amount)+'.','gold');try{toast('<b>💹 Investors backed '+esc(ACC.company)+'</b><span>You raised '+fmt(r.amount)+' on the players\' exchange.</span>','');}catch(e){}afterChange();render();save();}}catch(e){}}
function hideSplash(){const sp=document.getElementById('splash');if(!sp||sp.classList.contains('gone'))return;sp.classList.add('gone');setTimeout(()=>sp.remove(),400);}
function renderAccts(){if(acctView!=='loading')hideSplash();const el=$('acct');if(!acctView){el.hidden=true;return;}el.hidden=false;let h='<div class="acctbox"><div class="acctbrand">Hustlempires</div>';
 if(acctView==='loading')h+='<h2>Loading…</h2><p class="sub">Connecting to the game server.</p>';
 else if(acctView==='guestsave')h+=guestSaveHTML();
 else if(acctView==='down')h+='<h2>Can\'t connect</h2><p class="sub">'+esc(authMsg)+'</p><div class="chips"><button class="btn primary" data-a="retryboot">Try again</button></div>';
 else if(acctView==='auth')h+=authHook()+(authMode==='about'?'<div class="chips hook-cta"><button class="btn primary" data-a="authjump" data-v="signup">Start my empire, free</button><button class="btn ghost" data-a="authjump" data-v="login">Log in</button></div>'+authTabs()+aboutGame():'<h2>'+(authMode==='signup'?'Create your account':'Welcome back')+'</h2><p class="sub">'+(authMode==='signup'?'Your account keeps your empire safe, so you can pick it up on any device.':'Log in to carry on building your empire.')+'</p>'+authForm()+'<p class="about-link"><button class="linkbtn" data-a="authmode" data-v="about">New to Hustlempires? Read what the game is about →</button></p>')+(authMode!=='login'?'<p class="hook-end"><span class="hook-kick"><span aria-hidden="true">🏪</span> Your empire starts here!</span></p>':'');
 else if(acctView==='menu')h+='<div class="me">'+avatar(playerAcc(),true)+'<div><h2>'+esc(playerName())+'</h2><p class="sub">'+((S&&S.gnum>1)?'Generation '+S.gnum+' of the '+esc(familyName())+' family · ':'')+'@'+esc(ACC.username)+' · '+esc(ACC.company)+' · '+esc(ACC.town)+'</p></div></div>'+
  '<div class="chips"><button class="btn primary" data-a="acctclose">Back to my game</button><button class="btn" data-a="leaderboard">Leaderboard</button>'+'<button class="btn" data-a="myprofile">My profile</button><button class="btn" data-a="lives">Past lives</button><button class="btn" data-a="friends">Friends</button>'+(canInstall()?'<button class="btn" data-a="installapp">Install app</button>':'')+'<button class="btn ghost" data-a="logout">Log out</button></div>'+
  passMenuHTML()+pushMenuHTML()+'<h3>Invite friends</h3><p class="sub">'+inviteRuleLine()+'</p><div class="chips"><button class="btn" data-a="invite">Invite friends</button></div>'+(ACC.google&&!ACC.pw?'<h3>Signing in</h3><p class="sub"><span class="gsi-g" aria-hidden="true">G</span> You sign in with <b>Google</b> ('+esc(ACC.email)+'). Your username is <b>@'+esc(ACC.username)+'</b>. Want a password too? <button class="linkbtn" data-a="forgotview">Set one by email</button></p>':(ACC.google?'<p class="sub"><span class="gsi-g" aria-hidden="true">G</span> Google is connected: you can also log in with <b>Continue with Google</b>.</p>':'')+'<h3>Email for password resets</h3><p class="sub">'+(ACC.email?'Resets go to <b>'+esc(ACC.email)+'</b>.':'<b>No email yet.</b> Add one so you can reset your password if you forget it.')+'</p>'+emailForm(ACC.email?'Change email':'Save email'))+companyHTML()+'<div class="regionbox">'+regionMenuHTML()+'</div>';
 else if(acctView==='installios')h+='<h2>Install the app</h2><p class="sub">Put the game on your home screen. It opens full-screen, like any other app.</p><ol class="iossteps"><li>At the bottom of Safari, tap the <b>Share</b> button (the square with an arrow pointing up).</li><li>Scroll down and tap <b>Add to Home Screen</b>.</li><li>Tap <b>Add</b>. The game\'s icon appears on your home screen.</li></ol><div class="chips"><button class="btn primary" data-a="acctclose">Got it</button></div>';
 else if(acctView==='addemail')h+='<h2>Add your email</h2><p class="sub">If you ever forget your password, we\'ll send a reset link here. We don\'t use it for anything else.</p>'+emailForm('Save email',true);
 else if(acctView==='forgot')h+='<h2>Forgot your password?</h2>'+(forgotDone?'<p class="amsg">'+esc(forgotDone)+'</p><div class="chips"><button class="btn primary" data-a="backlogin">Back to log in</button></div>':
  '<p class="sub">Enter your username or the email on your account. We\'ll email you a link to choose a new password.</p><form id="forgotform" class="aform" novalidate><label for="fg-who">Username or email</label><input id="fg-who" maxlength="120" autocomplete="username" autocapitalize="none" spellcheck="false" required>'+
  '<p class="aerr" id="acc-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="fg-submit">Email me a reset link</button><button type="button" class="btn ghost" data-a="backlogin">Back to log in</button></div></form>');
 else if(acctView==='reset')h+='<h2>Choose a new password</h2><p class="sub">Pick something you haven\'t used here before. You\'ll be logged in straight away.</p><form id="resetform" class="aform" novalidate>'+
  '<label for="rs-pass">New password</label><input id="rs-pass" type="password" maxlength="128" autocomplete="new-password" required><p class="hint">At least 8 characters.</p>'+
  '<label for="rs-pass2">Type it again</label><input id="rs-pass2" type="password" maxlength="128" autocomplete="new-password" required>'+
  '<p class="aerr" id="acc-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="rs-submit">Save new password</button><button type="button" class="btn ghost" data-a="forgotview">Get a new link</button></div></form>';
 else if(acctView==='tip')h+=tipViewHTML();
 else if(acctView==='pay'||acctView==='gift'||acctView==='payleft'||acctView==='paid')h+=payViewHTML();
 else if(acctView==='invite')h+=inviteHTML();
 else if(acctView==='friends')h+=friendsHTML();
 else if(acctView==='profile')h+=profileHTML();
 else if(acctView==='live')h+=liveHTML();
 else if(acctView==='wall')h+=wallViewHTML();
 else if(acctView==='lives'){h+='<h2>Your legacy</h2><p class="sub">Your family, your achievements and every empire you have built.</p>'+(livesData===null?'<p class="sub">Loading…</p>':legacyHTML()+trophiesHTML()+livesHTML(livesData,livesData.length))+'<div class="chips">'+(S&&S.over&&S.died&&S.kids.length?'<button class="btn primary" data-a="heirpick">Choose your heir</button>':'')+(S&&S.over?'<button class="btn primary" data-a="reset">Start a new life</button><button class="btn ghost" data-a="acctclose">Back to my game</button>':'<button class="btn primary" data-a="acctclose">Back to my game</button>')+'</div>';}
 else if(acctView==='board'){const cn=(countryRow(S.region||'')||{name:'your country'}).name;
  h+='<h2>Leaderboard</h2><div class="authtabs" role="tablist" style="grid-template-columns:1fr 1fr 1fr"><button role="tab" aria-selected="'+(lbTab==='season-country')+'" data-a="boardtab" data-v="season-country">'+esc(cn)+'</button><button role="tab" aria-selected="'+(lbTab==='season-world')+'" data-a="boardtab" data-v="season-world">World</button><button role="tab" aria-selected="'+(lbTab==='alltime')+'" data-a="boardtab" data-v="alltime">Hall of fame</button></div>'+
   '<p class="sub">'+(lbTab==='alltime'?'The best of all time, one record holder for each. Records never reset.':seasonName(seasonId())+'. Points come from daily bonuses, weekly challenges, new ranks, achievements and big milestones. The board resets on the 1st of every month.')+'</p>';
  const subOn=lbTab!=='alltime',place=lbTab==='season-world'?'the world':cn;
  if(subOn&&lbSub!=='season'){h=h.replace(/<p class="sub">[^<]*<\/p>$/,()=>'')+lbSubHTML()+lbLocalHTML(place);}
  else if(subOn)h=h.replace(/(<p class="sub">[^<]*<\/p>)$/,m=>lbSubHTML()+m);
  if(subOn&&lbSub!=='season'){}else if(!lbData)h+='<p class="sub">Loading…</p>';else if(lbTab==='alltime')h+=hofHTML(lbData);else if(!lbData.length)h+='<p class="sub">No one is on the board yet.</p>';
  else h+='<ol class="hof">'+lbData.map((a,i)=>'<li><span class="hpos">'+(i+1)+'</span>'+avatar(a)+'<span class="ameta"><b>'+(a.username?'<button class="linkbtn wname" data-a="wallopen" data-v="'+esc(a.username)+'">'+esc(a.name)+'</button>':esc(a.name))+'</b><span>'+esc(a.company)+(lbTab!=='alltime'&&a.region?' · '+esc((countryRow(a.region)||{name:a.region}).name):'')+'</span></span><span class="hnum">'+(lbTab!=='alltime'?Number(a.pts).toLocaleString('en-US')+' pts':a.billion_month!=null?fmt(1e9)+' in '+Math.floor(a.billion_month/12)+'y '+(a.billion_month%12)+'m':'Best '+fmt(a.best))+'</span></li>').join('')+'</ol>';
  h+='<div class="chips"><button class="btn ghost" data-a="acctclose">Back to my game</button></div>';}
 el.innerHTML=h+'</div>';
 const f=$('acctform');if(f){f.addEventListener('submit',e=>{e.preventDefault();submitAuth();});const u=$('acc-user');if(u&&!GOOGLE_ID)u.focus();wireRegionForm();}
 gsiMount();
 wireRegionMenu();
 const ff=$('forgotform');if(ff){ff.addEventListener('submit',e=>{e.preventDefault();submitForgot();});$('fg-who').focus();}
 const rf=$('resetform');if(rf){rf.addEventListener('submit',e=>{e.preventDefault();submitReset();});$('rs-pass').focus();}
 const cf=$('coform');if(cf)cf.addEventListener('submit',e=>{e.preventDefault();submitCompany();});
 const ef=$('emailform');if(ef){ef.addEventListener('submit',e=>{e.preventDefault();submitEmail();});if(acctView==='addemail')$('em-email').focus();}}
function companyHTML(){if(ACC.renamed)return'<h3>Company name</h3><p class="sub">Your company is <b>'+esc(ACC.company)+'</b>. You have already used your one rename.</p>';
 return'<h3>Company name</h3><p class="sub">Your company is <b>'+esc(ACC.company)+'</b>. It names your racing team, towers, foundation and more. You can rename it <b>once</b>.</p><form id="coform" class="aform" novalidate><label for="co-name">New company name</label><input id="co-name" maxlength="16" autocomplete="off" placeholder="e.g. Zuri" required><p class="cotaken" id="co-name-chk" hidden></p><p class="hint">Up to 16 characters. You cannot change it again after this.</p><p class="aerr" id="co-err" hidden></p><div class="chips"><button type="submit" class="btn primary" id="co-submit">Rename company</button></div></form>';}
/* live check that a company name is free, as the player types it */
let coChkT=null;
document.addEventListener('input',e=>{const t=e.target;if(!t||t.id!=='acc-user'||authMode!=='signup')return;clearTimeout(unChkT);const out=document.getElementById('acc-user-chk');if(!out)return;const v=t.value.trim().toLowerCase();
 if(!v){out.hidden=true;return;}unChkT=setTimeout(async()=>{try{const r=await api('GET','/api/username/check?name='+encodeURIComponent(v));if(t.value.trim().toLowerCase()!==v)return;out.hidden=false;
  out.className='cotaken '+(r.valid&&!r.taken?'ok':'bad');out.textContent=!r.valid?'✗ Use 3 to 20 letters, numbers, dots or underscores.':r.taken?'✗ '+v+' is already taken. Try another.':'✓ '+v+' is available.';}catch(x){out.hidden=true;}},400);});
let unChkT=null;
document.addEventListener('input',e=>{const t=e.target;if(!t||(t.id!=='acc-company'&&t.id!=='co-name'))return;clearTimeout(coChkT);const out=document.getElementById(t.id+'-chk');if(!out)return;const v=t.value.trim();
 if(!v){out.hidden=true;return;}coChkT=setTimeout(async()=>{try{const r=await api('GET','/api/company/check?name='+encodeURIComponent(v));if(t.value.trim()!==v)return;out.hidden=false;out.className='cotaken '+(r.taken?'bad':'ok');out.textContent=r.taken?'✗ '+v+' is already taken. Try another.':'✓ '+v+' is available.';}catch(x){out.hidden=true;}},400);});
async function submitCompany(){const v=$('co-name').value.trim().replace(/\s+/g,' '),btn=$('co-submit'),err=$('co-err'),bad=m=>{err.textContent=m;err.hidden=false;};
 if(!v)return bad('Enter a company name.');if(v===ACC.company)return bad('That is already your company name.');
 if(!confirm('Rename '+ACC.company+' to '+v+'? You can only do this once.'))return;
 btn.disabled=true;const old=ACC.company;try{const d=await api('POST','/api/company',{company:v});ACC=d.user;
  (S.props||[]).forEach(p=>{if(p.name)p.name=p.name.split(old).join(ACC.company);});
  log('You renamed your company from '+old+' to '+ACC.company+'.','gold');if(typeof save==='function')save();render();renderAccts();}
 catch(e){btn.disabled=false;bad(e.message);}}
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
 btn.disabled=true;btn.textContent='Saving…';try{const d=await api('POST','/api/reset',{token:resetToken,password:a});resetToken='';startWith(d.user,d.save,d.bill,d.ver);}
 catch(e){btn.disabled=false;btn.textContent='Save new password';showErr(e.message);}}
function showErr(msg){if(/company name/i.test(msg||'')){const c=$('acc-company');if(c){const d=c.closest('details');if(d)d.open=true;setTimeout(()=>c.focus(),50);}}const e=$('acc-err');if(e){e.textContent=msg;e.hidden=false;try{e.scrollIntoView({block:'center',behavior:'smooth'});}catch(x){}}}
/* ---------- Guest play: new visitors play first; an account is needed to keep (save) their empire ---------- */
/* soft offers at milestones, a firm "save to keep playing" after the first two game years */
const GUEST_RULES={nw:10000,year:12,two:24,lock:0,gapMonths:4};  /* lock:0 = never force an account; guests play as long as they like */
function guestLoad(){try{const g=JSON.parse(localStorage.getItem('hs-guest')||'null');return g&&g.hist?g:null;}catch(e){return null;}}
function guestStore(){if(!GUEST||!S)return;clearTimeout(guestT);guestT=setTimeout(()=>{try{localStorage.setItem('hs-guest',JSON.stringify(S));}catch(e){}},300);}
function guestDrop(){try{localStorage.removeItem('hs-guest');}catch(e){}}
const guestLocked=()=>!!GUEST_RULES.lock&&GUEST&&S&&!S.over&&(S.month||0)>=GUEST_RULES.lock;
function startGuest(){GUEST=true;ACC=null;BILL=null;SAVEVER=null;const g=guestLoad();
 if(g)S=Object.assign(fresh(),g);else{S=fresh();S.m0=new Date().getMonth();S.region=detectCountry();S.cur=S.region==='KE'?'LOCAL':'USD';S.gAsk={};}   /* Kenyan visitors start in KSh, like the Kenya ads */
 useRegion(S.region);migrate();livesCache=[];current=null;closeModal();acctView=null;authMsg='';renderAccts();render();paintChip();
 visitMark(g&&((g.plays||0)>0||g.month>1)?'played':'landed');stepMark('open');stepDay2();
 if(guestLocked()){guestAsk('lock');return;}
 if(!g||!S.inds.length)openEvent(industryEvent(true));else startEvents();}  /* a new visitor's first screen is the street kiosk card */
/* the first card a new visitor sees: the hook, and who they are, in one tap */
function guestWelcome(){
 return{cat:'Welcome',title:'Do you have a <mark class="hook-hl">billionaire mindset</mark>? Time to use it.',noOut:true,
  text:'You start at 24 with '+fmt(S.cash)+' and a street hustle. Build businesses, buy property, own a football club, raise a family and choose who inherits it all. Free to play, no sign-up needed to start.',
  choices:[{l:'Start my empire',d:'Free. Your first business is waiting.',f(){return['Your story begins. You are 24, with '+fmt(S.cash)+' and a big idea.','good',!S.inds.length?industryEvent(true):null];}},
   {l:'I already have an account',d:'Log in to carry on your empire.',f(){setTimeout(()=>{stopAuto();authMode='login';guestWhy='login';acctView='guestsave';renderAccts();},0);return['','',null];}}]};}
/* after each move: is this a good moment to offer saving? */
function guestCheck(){if(!GUEST||!S||S.over)return;S.gAsk=S.gAsk||{};const A=S.gAsk,m=S.month||0;
 if((S.plays||0)>=1&&!A.played){A.played=1;visitMark('played');}
 if(totalUnits()>=2)stepMark('buy2');if(m>=12)stepMark('m12');
 if(guestLocked()){if(acctView!=='guestsave')setTimeout(()=>guestAsk('lock'),0);return;}
 if(current||!$('modal').hidden||acctView)return;
 if(A.last!=null&&m-A.last<GUEST_RULES.gapMonths)return;
 let why='';if(!A.nw&&netWorth()>=GUEST_RULES.nw){A.nw=1;why='nw';}else if(!A.year&&m>=GUEST_RULES.year){A.year=1;why='year';}else if(!A.two&&m>=GUEST_RULES.two){A.two=1;why='two';}else if((S.ach||[]).length>(A.ach||0)){A.ach=(S.ach||[]).length;why='ach';}
 if(why){A.last=m;setTimeout(()=>{if(!current&&$('modal').hidden&&!acctView)guestAsk(why);},700);}}
function guestAsk(why){if(!GUEST)return;if(acctView==='guestsave'&&(why==='lock'||guestWhy===why))return;stopAuto();guestWhy=why||'chip';authMode='signup';authMsg='';acctView='guestsave';renderAccts();const A=$('acct');if(A)A.scrollTop=0;visitMark('asked');stepMark('ask');}
function guestSaveHTML(){const nw=netWorth(),lock=guestWhy==='lock',achN=(S.ach||[]).length,lastAch=achN?(ACH.find(a=>a[0]===S.ach[achN-1])||[])[1]:'';
 if(authMode==='about')return aboutGame(true);
 if(authMode==='login')return'<h2>Log in</h2><p class="sub">Log in to carry on the empire on your account. The guest game on this screen will be replaced by your account\'s empire.</p>'+authForm(true)+'<div class="chips"><button class="btn ghost" data-a="authmode" data-v="signup">'+(S.month>0?'Save this guest game instead':'Back')+'</button></div>';
 const head={nw:['First milestone','You just passed '+fmt(GUEST_RULES.nw)+'. Don\'t lose it.'],year:['One year in','Your first year in business is done. Keep it safe.'],
  ach:['Achievement unlocked',(lastAch?lastAch+'. ':'')+'Save your achievements so they count.'],two:['Two years in','Look how far you have come. Save it whenever you are ready.'],lock:['Your first two years are done','Create your free account to keep playing. Your empire carries straight on from here.'],
  chip:['Playing as a guest','Your empire is only on this screen. Save it to keep it.'],feature:['Free account needed','That needs a free account, so you can play with real people.'],login:['Playing as a guest','Your empire is only on this screen. Save it to keep it.']}[guestWhy]||['Save your empire','Your empire is only on this screen. Save it to keep it.'];
 return'<div class="gsave-hero"><p class="gs-kick">'+head[0]+'</p><h2>Save your empire</h2><p>'+head[1]+'</p>'+
  '<ul class="gs-stats"><li><span>Net worth</span><b>'+fmt(nw)+'</b></li><li><span>Rank</span><b>'+esc(TITLES[titleIdx(nw)][1])+'</b></li><li><span>Businesses</span><b>'+(S.inds||[]).length+'</b></li><li><span>Age</span><b>'+age()+'</b></li>'+(achN?'<li><span>Achievements</span><b>'+achN+'</b></li>':'')+'</ul></div>'+
  (lock?'':'<div class="chips gs-top"><button class="btn primary" data-a="guestlater">Keep playing</button><span class="gs-note">Save any time from the <b>Guest</b> badge at the top.</span></div>')+'<ul class="gs-perks"><li><b>Keep everything</b>: your money, businesses and achievements.</li><li><b>Play on any phone or computer</b>, and never start over.</li><li><b>Climb the leaderboard</b> against real players in your country.</li><li><b>Put your name on your profile</b>: your milestones and your link come with you.</li></ul>'+
  '<p class="about-link" style="margin:4px 0 12px"><button class="linkbtn" data-a="authmode" data-v="about">What is Hustlempires? Read about the game →</button></p>'+
  authForm(true)+(lock?'':'<button class="btn ghost gs-later" data-a="guestlater">Not now, keep playing</button>')+
  '<p class="about-link"><button class="linkbtn" data-a="authmode" data-v="login">Already have an account? Log in</button></p>';}
/* the guest game becomes the new account's first saved game */
function guestAdopt(d){const g=S,co=d.user.company||'';GUEST=false;guestDrop();wallAdopt(d.user.id);g._uid=d.user.id;if(!g.g&&signupGender)g.g=signupGender;
 if(co&&co!=='Savanna')(g.props||[]).forEach(p=>{if(p.name)p.name=p.name.split('Savanna').join(co);});
 delete g.gAsk;S=g;log('You created your account. Your empire is saved, and it now follows you to any device.','gold');
 startWith(d.user,S,d.bill,d.ver);queueSync(true);if(!current&&$('modal').hidden&&!acctView){const m=typeof bestMove==='function'?bestMove():null;   /* saving is not the end: point straight at the next move */
  showCard('Your empire is saved','Welcome, '+esc(d.user.name)+'. Everything you built is kept on any device, and you are on the leaderboard now.<br><br><b>Next move:</b> '+(m?'open another '+esc(m.b.name.lc())+'. It adds about '+fmt(m.gain)+' a month.':'press PLAY. Your businesses keep earning every month.'),
   (m?'<button class="btn primary" data-a="savedbuy" data-v="'+m.b.id+'">Open it · '+fmtFull(m.c)+' game cash</button>':'<button class="btn primary" data-a="fmplay">Press PLAY</button>')+'<button class="btn ghost" data-a="close">Look around first</button>');}}
/* anonymous visit counting: a random id per browser, so the admin can see how many people open the game but never sign up */
function visitorId(){try{let v=localStorage.getItem('hs-vid');if(!v){v=Array.from(crypto.getRandomValues(new Uint8Array(12)),b=>b.toString(36).padStart(2,'0')).join('').replace(/[^a-z0-9]/gi,'').slice(0,20);if(v.length<12)v=(v+Math.random().toString(36).slice(2)).slice(0,20);localStorage.setItem('hs-vid',v);}return v;}catch(e){return'';}}
let visitFormSent=false,campCode='';
function visitMark(stage){try{if(localStorage.getItem('hs-player'))return;}catch(e){}const vid=visitorId();if(!vid)return;api('POST','/api/visit',{vid,stage,camp:campCode||undefined,ref:stage==='landed'?document.referrer||'':''}).catch(()=>{});}
/* first-session steps: each step is sent once per browser, so the admin can see exactly where new players stop */
function stepsDone(){try{return JSON.parse(localStorage.getItem('hs-steps')||'{}')||{};}catch(e){return{};}}
/* TikTok Pixel: events named after game moments; a player's email and number are hashed (SHA-256) in the browser before they are sent */
async function ttSha(s){const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(String(s)));return Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');}
async function ttIdentify(u){try{if(!window.ttq||!u||!window.crypto||!crypto.subtle)return;const o={external_id:await ttSha('hustlempires-'+u.id)};const e=String(u.email||'').trim().toLowerCase();if(e)o.email=await ttSha(e);ttq.identify(o);}catch(e){}}
function ttTrack(ev,name,extra){try{if(window.ttq)ttq.track(ev,Object.assign({contents:[{content_id:'hustlempires',content_type:'product',content_name:name}]},extra||{}));}catch(e){}}
const TT_STEP={buy:['ClickButton','Buy my first business'],play1:['ViewContent','First PLAY'],form:['Lead','Sign-up form']};
function stepMark(k){try{if(localStorage.getItem('hs-player'))return;const d=stepsDone();if(d[k])return;d[k]=1;if(TT_STEP[k])ttTrack(TT_STEP[k][0],TT_STEP[k][1]);if(!d._day)d._day=new Date().toDateString();localStorage.setItem('hs-steps',JSON.stringify(d));}catch(e){return;}
 const vid=visitorId();if(!vid)return;api('POST','/api/visit',{vid,step:k,camp:campCode||undefined,ref:k==='open'?document.referrer||'':''}).catch(()=>{});}
function stepDay2(){const d=stepsDone();if(d._day&&d._day!==new Date().toDateString())stepMark('day2');}
document.addEventListener('input',e=>{if(!visitFormSent&&!ACC&&e.target&&e.target.closest&&e.target.closest('#acctform')){visitFormSent=true;visitMark('form');stepMark('form');}});
async function submitAuth(){const btn=$('acc-submit'),username=$('acc-user').value.trim().toLowerCase(),password=$('acc-pass').value;
 if(!username||!password)return showErr('Enter your username and password.');
 let body={username,password,vid:visitorId()};
 if(authMode==='signup'){const name=$('acc-name').value.trim();if(!name)return showErr('Enter your name.');if(password.length<8)return showErr('Passwords need at least 8 characters.');
  const email=$('acc-email').value.trim();if(!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email))return showErr('Enter a valid email address. It\'s how you reset your password.');
  signupGender=(document.querySelector('input[name="acc-g"]:checked')||{}).value||(GUEST&&S.g)||'';if(!signupGender){const g=document.querySelector('.gopts');if(g){g.classList.add('need');g.scrollIntoView({block:'center',behavior:'smooth'});}return showErr('One more thing: choose whether you are a man or a woman (just above).');}
  signupRegion=($('acc-region')||{}).value||(GUEST&&S.region)||detectCountry();signupCur=(document.querySelector('input[name="acc-cur"]:checked')||{}).value||(GUEST&&S.cur)||'USD';
  body=Object.assign(body,{ref:refCode||undefined,camp:campCode||undefined,gkey:GUEST?wallKey()||undefined:undefined,email,name,company:$('acc-company').value.trim(),town:$('acc-town').value,bg:(document.querySelector('input[name="acc-bg"]:checked')||{}).value||'hustler',color:+((document.querySelector('input[name="acc-col"]:checked')||{}).value||0)});}
 btn.disabled=true;btn.textContent=authMode==='signup'?'Creating your account…':'Logging in…';
 try{const d=await api('POST',authMode==='signup'?'/api/signup':'/api/login',body);
  if(authMode==='signup')try{if(window.fbq)fbq('track','CompleteRegistration',{content_name:'Hustlempires account'});}catch(x){}
  if(authMode==='signup'){const u=d.user;(async()=>{await ttIdentify(u);ttTrack('CompleteRegistration','Hustlempires account');})();}
  if(GUEST&&authMode==='signup'){guestAdopt(d);return;}
  if(ACC===null&&S&&S.month>0&&authMode==='login'&&d.save&&d.save.month<S.month&&S.logN&&S._uid===d.user.id){startWith(d.user,S,d.bill,d.ver);}else startWith(d.user,d.save,d.bill,d.ver);}
 catch(e){btn.disabled=false;btn.textContent=authMode==='signup'?(GUEST?'Save my empire':'Create account and start'):'Log in';showErr(e.message);}}
/* ---------- Sign in with Google: one tap makes (or opens) the account, no password to remember ---------- */
let GOOGLE_ID='',gsiReady=false,gsiInit=false,gsiBusy=false;
function gsiHTML(su){if(!GOOGLE_ID)return'';return'<div class="gsi"><div id="gsi-btn" class="gsi-btn" aria-label="Continue with Google"></div><p class="gsi-st" id="gsi-st" hidden></p>'+(su?'<p class="hint gsi-hint">Fastest way in: no password to remember.</p>':'')+'<p class="gsi-or"><span>'+(su?'or create a username':'or use your username')+'</span></p></div>';}
function gsiLoad(){if(window.google&&google.accounts&&google.accounts.id){gsiReady=true;return;}if(document.getElementById('gsi-js'))return;const s=document.createElement('script');s.id='gsi-js';s.src='https://accounts.google.com/gsi/client';s.async=true;s.defer=true;
 s.onload=()=>{gsiReady=true;gsiMount();};s.onerror=()=>{const b=document.querySelector('.gsi');if(b)b.hidden=true;};document.head.appendChild(s);}
function gsiMount(){const el=document.getElementById('gsi-btn');if(!el||!GOOGLE_ID)return;if(!gsiReady){gsiLoad();return;}
 try{if(!gsiInit){google.accounts.id.initialize({client_id:GOOGLE_ID,callback:googleDone,ux_mode:'popup',auto_select:false,cancel_on_tap_outside:true,context:'signin',itp_support:true,use_fedcm_for_button:true});gsiInit=true;}
  const w=Math.round(Math.min(400,Math.max(220,el.getBoundingClientRect().width||300)));
  google.accounts.id.renderButton(el,{type:'standard',theme:'filled_black',size:'large',shape:'pill',logo_alignment:'center',width:w,text:authMode==='login'?'signin_with':'continue_with'});}
 catch(e){const b=el.closest('.gsi');if(b)b.hidden=true;}}
async function googleDone(resp){if(gsiBusy||!resp||!resp.credential)return;gsiBusy=true;const st=$('gsi-st'),er=$('acc-err');if(er)er.hidden=true;if(st){st.textContent='Signing you in with Google…';st.hidden=false;}
 const gu=GUEST,v=id=>{const x=$(id);return x&&x.value?x.value.trim():'';},ck=n=>(document.querySelector('input[name="'+n+'"]:checked')||{}).value;
 const body={credential:resp.credential,vid:visitorId(),ref:refCode||undefined,camp:campCode||undefined,gkey:gu?wallKey()||undefined:undefined};
 if(v('acc-name'))body.name=v('acc-name');if(v('acc-company'))body.company=v('acc-company');if(v('acc-town'))body.town=v('acc-town');if(ck('acc-bg'))body.bg=ck('acc-bg');if(ck('acc-col')!=null)body.color=+ck('acc-col');
 signupGender=ck('acc-g')||(gu&&S&&S.g)||'';signupRegion=v('acc-region')||(gu&&S&&S.region)||detectCountry();signupCur=ck('acc-cur')||(gu&&S&&S.cur)||'USD';
 try{const d=await api('POST','/api/google',body);gsiBusy=false;
  if(d.isNew){try{if(window.fbq)fbq('track','CompleteRegistration',{content_name:'Hustlempires account',method:'google'});}catch(x){}{const u=d.user;(async()=>{await ttIdentify(u);ttTrack('CompleteRegistration','Hustlempires account');})();}
   authMode='signup';if(gu){guestAdopt(d);return;}startWith(d.user,d.save,d.bill,d.ver);return;}
  const hadGuest=gu&&S&&S.month>0;authMode='login';
  if(ACC===null&&!gu&&S&&S.month>0&&d.save&&d.save.month<S.month&&S.logN&&S._uid===d.user.id)startWith(d.user,S,d.bill,d.ver);else startWith(d.user,d.save,d.bill,d.ver);
  if(hadGuest)setTimeout(()=>{if(!current&&$('modal').hidden&&!acctView)showCard('Welcome back, '+esc(d.user.name.split(' ')[0]),'This Google account already has an empire, <b>'+esc(d.user.company)+'</b>, so we opened it for you.','<button class="btn primary" data-a="close">Back to my empire</button>');},400);}
 catch(e){gsiBusy=false;if(st)st.hidden=true;if($('acc-err'))showErr(e.message);else alert(e.message);}}
function bootAuth(){try{const u=new URL(location.href),t=u.searchParams.get('reset'),pr=u.searchParams.get('paid');if(t){resetToken=t;u.searchParams.delete('reset');}
 if(pr){payRef=pr.slice(0,60);payCancelled=u.searchParams.get('cancelled')==='1';payTries=0;['paid','cancelled','OrderTrackingId','OrderMerchantReference','OrderNotificationType'].forEach(k=>u.searchParams.delete(k));}
 const rf=(u.searchParams.get('ref')||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,12);if(rf){refCode=rf;u.searchParams.delete('ref');try{localStorage.setItem('hs-ref',rf);}catch(e){}}
 if(!refCode)try{refCode=localStorage.getItem('hs-ref')||'';}catch(e){}
 const cm=(u.searchParams.get('c')||'').toLowerCase().replace(/[^a-z0-9-]/g,'').slice(0,30);if(cm){campCode=cm;u.searchParams.delete('c');try{localStorage.setItem('hs-camp',cm);}catch(e){}}
 if(!campCode)try{campCode=localStorage.getItem('hs-camp')||'';}catch(e){}
 if(t||pr||rf||cm)history.replaceState(null,'',u.pathname+u.search+u.hash);}catch(e){}
 if(refCode)api('GET','/api/invite/check?code='+encodeURIComponent(refCode)).then(d=>{refInfo=d&&d.ok?d:null;if(acctView==='auth')renderAccts();}).catch(()=>{});
 api('GET','/api/config').then(c=>{GOOGLE_ID=(c&&typeof c.google==='string')?c.google:'';if(GOOGLE_ID){gsiLoad();if(acctView&&acctView!=='loading')renderAccts();}}).catch(()=>{});
 api('GET','/api/tuning').then(t=>{if(t&&typeof t==='object')TUNE=Object.assign({freq:1,gap:2,w:{},cat:{}},t);}).catch(()=>{});
 if(resetToken){acctView='reset';authMsg='';renderAccts();return;}
 acctView='loading';renderAccts();api('GET','/api/me').then(d=>startWith(d.user,d.save,d.bill,d.ver)).catch(e=>{if(e.status===401){if(firstMode()==='login'&&!guestLoad()){acctView='auth';authMode='login';}else{startGuest();return;}}else{acctView='down';authMsg=e.message;}renderAccts();});}
async function logout(){stopAuto();BILL=null;paintPass();if(ACC)try{await doSync();}catch(e){}await pushForget();try{await api('POST','/api/logout',{});}catch(e){}setSess('');ACC=null;S=fresh();current=null;closeModal();acctView='auth';authMode='login';authMsg='';render();renderAccts();}
/* ---- hall of fame: founder milestones, richest founders, then every heir generation ---- */
const HOF_MS=[['m','Youngest to $1 million','💵'],['b','Youngest to $1 billion','💰'],['t','Youngest to $1 trillion','🏦'],['q','Youngest to $1 quadrillion','👑']];
const ordN=n=>n+(['th','st','nd','rd'][(n%100>10&&n%100<14)?0:n%10]||'th');
function hofList(rows,val,sub,line2){if(!rows||!rows.length)return'<p class="hofnone">Nobody has made it yet. It could be you.</p>';
 const li=(a,i)=>'<li><span class="hpos">'+(i+1)+'</span>'+avatar(a)+'<span class="ameta"><b>'+esc(sub?sub(a):a.name)+'</b><span>'+esc(line2?line2(a):sub?a.name+' · '+a.company:a.company)+(a.region?' · '+esc((countryRow(a.region)||{name:a.region}).name):'')+'</span></span><span class="hnum">'+val(a)+'</span></li>';
 return'<ol class="hof">'+rows.slice(0,5).map(li).join('')+'</ol>'+(rows.length>5?'<details class="hofmore"><summary>Show '+(rows.length-5)+' more</summary><ol class="hof" start="6">'+rows.slice(5).map((a,i)=>li(a,i+5)).join('')+'</ol></details>':'');}
function hofHTML(d0){const one=r=>(r||[]).slice(0,1),d={ms:{},founders:one(d0.founders),companies:one(d0.companies),gens:{}};Object.keys(d0.ms||{}).forEach(k=>d.ms[k]=one(d0.ms[k]));Object.keys(d0.gens||{}).forEach(k=>d.gens[k]=one(d0.gens[k]));const coH='<h3 class="hofh">Most valued company</h3><p class="sub">The most valuable company running today, valued by its businesses, subsidiaries, property developments and sports teams.</p><section class="hofsec">'+hofList(d.companies,a=>fmt(a.co),a=>a.company,a=>'Run by '+(a.gen>1&&a.who?a.who+' ('+ordN(a.gen)+' generation)':a.name))+'</section>';const ageS=m=>'age '+Math.floor(m/12)+(m%12?'y '+(m%12)+'m':'');let h='<h3 class="hofh">First generation</h3><p class="sub">Self-made founders who started from scratch.</p>';
 HOF_MS.forEach(([k,t,ic])=>{h+='<section class="hofsec"><h4>'+ic+' '+t+'</h4>'+hofList((d.ms||{})[k],a=>ageS(a.age_m))+'</section>';});
 h+='<section class="hofsec"><h4>🏆 Richest founder</h4>'+hofList(d.founders,a=>fmt(a.top))+'</section>';
 const gs=Object.keys(d.gens||{}).map(Number).sort((a,b)=>a-b);
 h+='<h3 class="hofh">Dynasties</h3><p class="sub">The richest heir of each generation, by the peak worth of their life.</p>';
 if(!gs.length)h+='<p class="hofnone">No heir has taken over an empire yet.</p>';
 gs.forEach(g=>{h+='<section class="hofsec"><h4>'+ordN(g)+' generation</h4>'+hofList(d.gens[g],a=>fmt(a.top),a=>a.who||a.name)+'</section>';});
 return h+coH;}
/* ---- country tab sub-tabs: season points or a founder record board for this country ---- */
let lbSub='season',lbLocal=null;
const LB_SUBS=[['season','📅 Season'],['m','💵 $1M'],['b','💰 $1B'],['t','🏦 $1T'],['q','👑 $1Q'],['rich','🏆 Richest'],['co','🏢 Companies']];
function lbSubHTML(){return'<div class="lbsubs" role="tablist">'+LB_SUBS.map(([k,l])=>'<button role="tab" class="lbsub" aria-selected="'+(lbSub===k)+'" data-a="lbsub" data-v="'+k+'">'+l+'</button>').join('')+'</div>';}
function lbLocalHTML(cn){const d=lbLocal;if(!d)return'<p class="sub">Loading…</p>';const ageS=m=>'age '+Math.floor(m/12)+(m%12?'y '+(m%12)+'m':'');
 if(lbSub==='co')return'<p class="sub">The most valuable companies running today in '+esc(cn)+', valued by their businesses, subsidiaries, property developments and sports teams. Cash, shares and personal luxuries do not count.</p>'+hofList(d.companies,a=>fmt(a.co),a=>a.company,a=>'Run by '+(a.gen>1&&a.who?a.who+' ('+ordN(a.gen)+' generation)':a.name));
 if(lbSub==='rich')return'<p class="sub">Self-made founders in '+esc(cn)+', ranked by the peak worth of their life.</p>'+hofList(d.founders,a=>fmt(a.top));
 const t=HOF_MS.find(x=>x[0]===lbSub);return'<p class="sub">'+t[1]+' in '+esc(cn)+'. Self-made founders only, youngest first. Records never reset.</p>'+hofList((d.ms||{})[lbSub],a=>ageS(a.age_m));}
async function lbSubGo(k){lbSub=k;if(k!=='season'&&!lbLocal){renderAccts();try{lbLocal=await api('GET','/api/leaderboard'+(lbTab==='season-country'?'?region='+encodeURIComponent(S.region||''):''));}catch(e){lbLocal={ms:{},founders:[],companies:[]};}}renderAccts();}
async function openBoard(tab){lbLocal=null;if(tab)lbTab=tab;stopAuto();closeModal();acctView='board';lbData=null;renderAccts();
 try{if(lbTab==='alltime')lbData=await api('GET','/api/leaderboard');else{const d=await api('GET','/api/season?scope='+(lbTab==='season-world'?'world':'country')+'&region='+encodeURIComponent(S.region||''));seasonCache=d;lbData=d.top;}}catch(e){lbData=[];}renderAccts();}
/* heirs saved before family years existed: work out when the founder started from the past lives */
async function fyFix(){if(!S||S.fy0||(S.gnum||1)<2)return;try{const d=await api('GET','/api/lives');let y=S.y0||new Date().getFullYear(),g=S.gnum-1;
 for(const l of d.lives||[]){if((l.gen||1)!==g)break;y-=Math.floor((l.months||0)/12);g--;if(g<1)break;}S.fy0=y;render();}catch(e){}}
/* the dashboard leaderboard button shows the player's rank in their country, and bounces when it improves */
let lbShown=0;
function paintLbBtn(){const b=document.getElementById('lbbtn'),r=document.getElementById('lbrank');if(!b||!r)return;const d=seasonCache,me=d&&d.me&&S.sea&&d.season===S.sea.id?d.me:null;
 if(!me||!me.rankRegion){r.hidden=true;b.setAttribute('aria-label','Open the leaderboard');return;}
 r.hidden=false;r.textContent='#'+me.rankRegion;b.setAttribute('aria-label','Leaderboard: you are number '+me.rankRegion+' in your country');
 if(lbShown&&me.rankRegion<lbShown){b.classList.remove('lbup');void b.offsetWidth;b.classList.add('lbup');}lbShown=me.rankRegion;}
async function loadSeason(){try{seasonCache=await api('GET','/api/season?scope=country&region='+encodeURIComponent(S.region||''));if(!awayBusy)seaRemember(seasonCache);render();}catch(e){}}
function seasonRankLine(){const d=seasonCache,s=S.sea;if(!d||!s||d.season!==s.id||!d.me)return' <span class="rk">Play this month to get on the board</span> <button class="btn small ghost" data-a="leaderboard">Leaderboard</button> <button class="btn small ghost" data-a="invite">Invite friends</button>';
 const c=countryRow(d.me.region)||{name:d.me.region};return' <span class="rk">#'+d.me.rankRegion+' of '+d.me.playersRegion+' in '+esc(c.name)+' · #'+d.me.rank+' of '+d.me.players+' worldwide</span> <button class="btn small ghost" data-a="leaderboard">Leaderboard</button> <button class="btn small ghost" data-a="invite">Invite friends</button>';}
function trophiesHTML(){const d=seasonCache;if(!d||!d.history||!d.history.length)return'';
 return'<h3 class="achh">Season trophies</h3><ul class="achs">'+d.history.map(h=>{const c=countryRow(h.region)||{name:h.region||'World'},top=h.rankRegion<=3?['🥇','🥈','🥉'][h.rankRegion-1]+' ':'';
  return'<li class="ach got"><b>'+top+seasonName(h.season)+'</b><span>'+h.pts.toLocaleString('en-US')+' points · #'+h.rankRegion+' of '+h.playersRegion+' in '+esc(c.name)+' · #'+h.rank+' of '+h.players+' worldwide</span></li>';}).join('')+'</ul>';}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&ACC&&syncState!=='saved')doSync();});

/* ================= New version available: prompt to update ================= */
const APP_VER='__APP_VER__';let updShown=false;
/* back on a screen after a while with an old version: update straight away, so an old screen never plays on stale code */
function checkVersion(back){fetch('/api/version',{cache:'no-store',credentials:'same-origin'}).then(r=>r.ok?r.json():null).then(d=>{if(d&&d.v&&d.v!==APP_VER){if(back&&!current&&!autoOn())appUpdate();else showUpdate();}}).catch(()=>{});}
const autoOn=()=>typeof timer!=='undefined'&&!!timer;let hiddenAt=0;
function showUpdate(){if(updShown)return;updShown=true;const b=document.createElement('div');b.className='updbar';b.setAttribute('role','status');
 b.innerHTML='<span><b>A new update is ready</b><small>Get the latest features and fixes. Your empire is saved.</small></span><button class="btn primary small" data-a="appupdate">Update now</button>';document.body.appendChild(b);}
async function appUpdate(){const b=document.querySelector('.updbar button');if(b){b.disabled=true;b.textContent='Updating…';}stopAuto();
 try{if(ACC)await doSync();}catch(e){}
 try{if(navigator.serviceWorker){const r=await navigator.serviceWorker.getRegistration();if(r)await r.update();}}catch(e){}
 location.reload();}
setTimeout(checkVersion,15000);setInterval(checkVersion,5*60*1000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'){hiddenAt=Date.now();return;}checkVersion(hiddenAt&&Date.now()-hiddenAt>60000);});

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
function setBill(b){TIPS=b&&!b.on&&b.tips?b:null;BILL=b&&b.on?b:null;if(BILL&&BILL.now)billSkew=BILL.now-Date.now()/1000;paintPass();}
const nowS=()=>Date.now()/1000+billSkew;
const passLocked=()=>!!(BILL&&BILL.state==='locked');
function leftText(sec){sec=Math.max(0,sec);const d=Math.floor(sec/86400),h=Math.floor(sec%86400/3600),m=Math.max(1,Math.ceil(sec%3600/60));
 return d?d+' day'+(d>1?'s':'')+(h?' '+h+' h':''):h?h+' h'+(h<6&&m<60?' '+(m%60)+' min':''):m+' min';}
const dateText=ts=>new Date(ts*1000).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
function kesText(k){return'KSh '+Number(k).toLocaleString('en-US');}
function kesLocal(k){const ke=countryRow('KE');if(!ke||typeof R==='undefined'||!R||R.cur==='KES')return'';const usd=k/ke.rate;
 if(R.cur==='USD'||!R.rate)return'about $'+(usd<10?usd.toFixed(2):Math.round(usd));const v=usd*R.rate;return'about '+R.sym+(/[A-Za-z.]$/.test(R.sym)?' ':'')+(v<100?v.toFixed(v<10?2:0):Math.round(v).toLocaleString('en-US'));}
function paintPass(){let b=$('passbar');const st=BILL&&BILL.state,left=BILL&&BILL.until?BILL.until-nowS():0;
 if(!BILL){const tip=tipAskNow();if(!b&&tip){const c=$('acctchip');if(!c)return;b=document.createElement('button');b.id='passbar';b.className='passbar';c.parentNode.insertBefore(b,c.nextSibling);}
  if(!b)return;b.hidden=!tip;b.dataset.a='tipopen';b.classList.remove('warn');if(tip)b.innerHTML='<span>Enjoying '+esc(GAME_NAME)+'?</span><i>Tip the developers</i>';return;}
 const show=ACC&&BILL&&(st==='trial'||st==='bonus'||st==='locked'||(st==='paid'&&left<3*86400));
 if(b)b.dataset.a='passopen';
 if(!b&&show){const c=$('acctchip');if(!c)return;b=document.createElement('button');b.id='passbar';b.className='passbar';b.dataset.a='passopen';c.parentNode.insertBefore(b,c.nextSibling);}
 if(!b)return;b.hidden=!show;if(!show)return;b.classList.toggle('warn',st==='locked'||left<6*3600);
 b.innerHTML=st==='trial'?'<span>Free trial · <b>'+leftText(left)+' left</b></span><i>Get the Pass</i>':st==='bonus'?'<span>Bonus days · <b>'+leftText(left)+' left</b></span><i>Get the Pass</i>':
  st==='paid'?'<span>Hustle Pass ends in <b>'+leftText(left)+'</b></span><i>Renew</i>':'<span><b>Your free time is up</b></span><i>Get the Pass</i>';}
function passMenuHTML(){if(!BILL)return TIPS?'<h3>Tip the developers</h3><p class="sub">'+esc(GAME_NAME)+' is free to play. If you enjoy it, a tip helps us keep adding new events, countries and features.</p><div class="chips"><button class="btn" data-a="tipopen">Leave a tip</button></div>':'';const st=BILL.state,left=BILL.until?BILL.until-nowS():0;
 const line=st==='paid'?'Your <b>'+esc(planName(BILL.plan))+'</b> is active until <b>'+dateText(BILL.until)+'</b>.':st==='trial'?'You\'re on your free trial: <b>'+leftText(left)+'</b> left.':st==='bonus'?'You\'re on bonus days: <b>'+leftText(left)+'</b> left.':'You need the pass to keep playing.';
 return'<h3>Hustle Pass</h3><p class="sub">'+line+'</p><div class="chips"><button class="btn" data-a="passopen">'+(st==='paid'?'Add more time':'Get the Hustle Pass')+'</button></div>';}
function planName(id){const p=BILL&&BILL.plans&&BILL.plans.find(x=>x.id===id);return id==='gift'?'gifted pass':p?p.name.toLowerCase():'Hustle Pass';}
function openPay(msg){stopAuto();closeModal();payMsg=msg||'';payBusy=false;acctView='pay';renderAccts();window.scrollTo(0,0);}
const PERKS=['Keep building past your first day, all the way to a billion','Dynasties: hand your empire to your heirs, generation after generation','Monthly seasons, trophies and the country leaderboard','Every new event, crisis and feature we add'];
function payViewHTML(){const b=BILL||{plans:[]},st=b.state,co=esc(BR());let h='';
 if(acctView==='paid'&&payDone&&payDone.plan==='tip')return'<div class="paidbox"><span class="paidicon" aria-hidden="true">♥</span><h2>Thank you!</h2><p class="sub">Your '+kesText(payDone.amount)+' tip came through. It means a lot, and it goes straight into making the game better. '+co+' is waiting for you.</p></div><div class="chips"><button class="btn primary" data-a="acctclose">Back to my game</button></div>';
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
async function confirmPay(){if(!payRef)return;stopAuto();closeModal();acctView=TIPS?'tip':'pay';payBusy=true;payMsg=payCancelled?'You left the payment page. Checking…':'Checking your payment…';renderAccts();
 let d=null;try{d=await api('POST','/api/billing/confirm',{ref:payRef});}catch(e){}
 if(d){setBill(d.bill);const ps=d.payment&&d.payment.status;
  if(ps==='paid'){payDone=d.payment;{const p=d.payment||{};ttTrack('CompletePayment',p.plan==='tip'?'Tip':'Hustle Pass',{value:+p.amount||0,currency:p.currency||'KES'});}payRef='';payMsg='';payBusy=false;acctView='paid';renderAccts();if(syncState==='locked'||syncState==='offline'){syncState='saving';}queueSync(true);if(typeof confettiFx==='function')try{confettiFx();}catch(e){}return;}
  if(ps==='pending'&&!payCancelled&&++payTries<13){payMsg='Waiting for the payment to come through. If you paid by M-Pesa, approve the prompt on your phone.';renderAccts();setTimeout(confirmPay,5000);return;}
  payMsg=ps==='pending'&&!payCancelled?(TIPS?'We haven\'t had confirmation yet. If you paid, it will come through within a few minutes. Thank you!':'We haven\'t had confirmation yet. If you paid, your pass switches on within a few minutes; we keep checking. You can also pick a pass again below.'):'The payment didn\'t go through, so you weren\'t charged. You can try again below.';}
 else payMsg='We couldn\'t check your payment just now. If you paid, your pass switches on within a few minutes.';
 payRef='';payBusy=false;if(acctView==='tip'){renderAccts();return;}if(passLocked()||acctView==='pay'){acctView='pay';renderAccts();}}
setInterval(()=>{if(ACC&&!BILL&&TIPS){paintPass();return;}if(!ACC||!BILL)return;paintPass();if(BILL.state!=='locked'&&BILL.until&&nowS()>=BILL.until){
 api('GET','/api/billing').then(d=>{setBill(d.bill);if(passLocked()&&acctView!=='pay'&&acctView!=='gift'&&acctView!=='payleft')openPay();}).catch(()=>{});}},30000);

/* ================= Tips: the game is free; players can tip the developers ================= */
let TIPS=null,tipAmt=100;
const GAME_NAME='Hustlempires';
function tipAskNow(){if(!ACC||!TIPS||!S||S.month<24||S.over)return false;let last=0;try{last=+localStorage.getItem('hs-tipask')||0;}catch(e){}return Date.now()-last>14*86400000;}
function tipSnooze(){try{localStorage.setItem('hs-tipask',String(Date.now()));}catch(e){}paintPass();}
function openTip(msg){stopAuto();closeModal();tipSnooze();payMsg=msg||'';payBusy=false;acctView='tip';renderAccts();window.scrollTo(0,0);}
function tipViewHTML(){const am=(TIPS&&TIPS.tipAmounts)||[50,100,250,500,1000],co=esc(BR());let h='<h2>Enjoying '+GAME_NAME+'?</h2>'+
 '<p class="sub">The game is free, and it stays free. If '+co+' has given you some fun, you can leave a tip for the developers. It goes straight into new events, countries and features.</p>';
 if(payMsg)h+='<p class="amsg" role="status">'+payMsg+'</p>';
 h+='<div class="plans tips">'+am.map(k=>{const loc=kesLocal(k);return'<button class="plan'+(k===tipAmt?' pick':'')+'" data-a="tipamt" data-v="'+k+'" aria-pressed="'+(k===tipAmt)+'"'+(payBusy?' disabled':'')+'><span class="pr">'+kesText(k)+'</span>'+(loc?'<small>'+loc+'</small>':'')+'</button>';}).join('')+'</div>';
 h+='<form id="tipform" class="aform" novalidate><label for="tip-amt">Or choose your own amount (KSh)</label><input id="tip-amt" type="number" inputmode="numeric" min="20" max="100000" step="10" value="'+(am.includes(tipAmt)?'':tipAmt)+'" placeholder="For example 300"></form>';
 h+='<p class="hint">Pay with M-Pesa, Airtel Money, card or bank through Pesapal. It is a one-off tip, nothing renews, and the game is exactly the same whether you tip or not.</p>';
 h+='<div class="chips"><button class="btn primary" data-a="tipgo"'+(payBusy?' disabled':'')+'>Tip '+kesText(tipAmt)+'</button><button class="btn ghost" data-a="acctclose">Not now</button></div>';
 return h;}
function tipPick(v){tipAmt=+v||100;const i=$('tip-amt');if(i)i.value='';renderAccts();}
async function sendTip(){if(payBusy)return;const i=$('tip-amt'),own=i&&i.value?Math.round(+i.value):0;const k=own||tipAmt;
 if(!(k>=20&&k<=100000)){payMsg='Choose an amount from KSh 20 to KSh 100,000.';renderAccts();return;}
 tipAmt=k;payBusy=true;payMsg='Opening the payment page…';renderAccts();try{await doSync();}catch(e){}
 try{const d=await api('POST','/api/billing/checkout',{tip:k});location.href=d.url;}
 catch(e){payBusy=false;payMsg=esc(e.message);renderAccts();}}
document.addEventListener('input',e=>{if(e.target&&e.target.id==='tip-amt'){const v=Math.round(+e.target.value);const b=document.querySelector('[data-a=tipgo]');if(b)b.textContent='Tip '+kesText(v>=20?v:tipAmt);if(v>=20)document.querySelectorAll('.tips .plan').forEach(x=>{x.classList.remove('pick');x.setAttribute('aria-pressed','false');});}});
document.addEventListener('submit',e=>{if(e.target&&e.target.id==='tipform'){e.preventDefault();sendTip();}});

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

/* ---------- Offers: bid for another player's buildings or business outlets (from the Empire map) ---------- */
let bidData=null,bidT=0,bidBusy=false,bidDraft=null,bidSeen={},bidMsg='';
function bidFmtPct(p){return Math.round(p*100)+'%';}
function bidHeldSet(){if(!S)return;S.bidOut=S.bidOut||{};S.bidHeld=Object.values(S.bidOut).reduce((a,v)=>a+(+v||0),0);}
function bidWhat(b,me){const n=b.qty;if(b.kind==='biz'){const x=BIZ.find(z=>z.id===b.item);return n+' '+(x?x.name:'outlet')+(n===1?'':' outlets');}
 const t=ptype(b.item),c=pcity(b.city);return n+' '+(t?t.name.lc():'building')+(n===1?'':'s')+(c?' in '+c.name:'');}
async function bidLoad(force){if(!ACC||GUEST||bidBusy||!S)return;if(!force&&Date.now()-bidT<60000)return;bidT=Date.now();bidBusy=true;
 try{bidData=await api('GET','/api/bids');}catch(e){bidBusy=false;return;}bidBusy=false;await bidSettle();bidPrompt();try{if(typeof emLegend==='function'&&curTab==='map')emLegend();}catch(e){}}
/* the buyer's game applies finished offers once: what was bought arrives, or the held cash comes back */
async function bidSettle(){if(!bidData||!S)return;S.bidOut=S.bidOut||{};S.bidDone=S.bidDone||{};const done=[];let changed=false;
 (bidData.out||[]).forEach(b=>{if(b.status==='open'||b.done)return;if(S.bidDone[b.id]){done.push(b.id);return;}const held=S.bidOut[b.id];
  if(held==null){S.bidDone[b.id]=1;done.push(b.id);return;}
  let got=false;if(b.status==='accepted'){if(b.kind==='biz'){const x=BIZ.find(z=>z.id===b.item);if(x){S.owned[x.id]=owned(x.id)+b.qty;got=true;}}
   else{const t=ptype(b.item),c=pcity(b.city);if(t&&c){S.props=S.props||[];const G=(b.give||[]).slice(0,b.qty);while(G.length<b.qty)G.push({});
    G.forEach(g=>S.props.push({type:t.id,city:c.id,name:propName(t,c),af:+g.af||(S.reIdx||1),left:0,total:+g.total||t.build,occ:g.occ!=null?+g.occ:.9,anchor:0,was:g.name||''}));
    S.pcOpen=S.pcOpen||[];if(!S.pcOpen.includes(c.id))S.pcOpen.push(c.id);got=true;}}}
  if(got)log(esc(b.name)+' accepted your offer. You bought '+bidWhat(b)+' for '+fmt(b.price)+'.','gold');
  else{S.cash+=held;log(b.status==='accepted'?'The deal with '+esc(b.name)+' could not be completed. Your '+fmt(held)+' is back.':b.status==='declined'?esc(b.name)+' turned down your offer for '+bidWhat(b)+'. Your '+fmt(held)+' is back.':b.status==='cancelled'?'You took back your offer for '+bidWhat(b)+'. Your '+fmt(held)+' is back.':'Your offer for '+bidWhat(b)+' expired. Your '+fmt(held)+' is back.',b.status==='accepted'?'bad':'');}
  delete S.bidOut[b.id];S.bidDone[b.id]=1;done.push(b.id);changed=true;});
 {const k=Object.keys(S.bidDone);if(k.length>300)k.slice(0,k.length-300).forEach(x=>delete S.bidDone[x]);}
 if(changed){bidHeldSet();afterChange();try{await doSync();}catch(e){}}
 if(done.length)api('POST','/api/bids/collect',{ids:done}).catch(()=>{});}
/* the seller sees each new offer once per session as a card */
function bidPrompt(){if(!bidData||current||!$('modal').hidden||acctView||(typeof tourOn!=='undefined'&&tourOn))return;const b=(bidData.in||[]).find(x=>!bidSeen[x.id]);if(!b)return;bidSeen[b.id]=1;bidAsk(b);}
function bidAsk(b){const left=Math.max(1,Math.round((b.expires-(bidData.now||Date.now()/1000))/3600)),pct=b.value>0?b.price/b.value:1;
 showCard('An offer for your '+(b.kind==='biz'?'business':'buildings'),'<p><b>'+esc(b.name)+'</b>'+(b.company?' of '+esc(b.company):'')+' offers <b>'+fmt(b.price)+'</b> for '+bidWhat(b)+'.</p><p>That is '+bidFmtPct(pct)+' of what they are worth at today\'s prices ('+fmt(b.value)+'). The offer ends in about '+left+' hour'+(left===1?'':'s')+'.</p>'+
  (b.kind==='biz'?'<p class="sub">Selling outlets lowers your monthly profit.</p>':'<p class="sub">Your cheapest matching buildings go first.</p>'),
  '<button class="btn primary" data-a="bidyes" data-v="'+b.id+'">Accept · '+fmt(b.price)+'</button><button class="btn" data-a="bidno" data-v="'+b.id+'">Turn it down</button><button class="btn ghost" data-a="close">Decide later</button>');}
async function bidAnswer(id,yes){const b=bidData&&(bidData.in||[]).find(x=>x.id===id);if(!b)return closeModal();let give=[],pick=[];
 if(yes){if(b.kind==='biz'){if(owned(b.item)<b.qty){showCard('Not enough to sell','You no longer own '+bidWhat(b)+'.','<button class="btn primary" data-a="close">OK</button>');return;}}
  else{pick=(S.props||[]).filter(p=>p.type===b.item&&p.city===b.city&&!(p.left>0)).sort((x,y)=>propValue1(x)-propValue1(y)).slice(0,b.qty);
   if(pick.length<b.qty){showCard('Not enough to sell','You no longer own '+bidWhat(b)+'.','<button class="btn primary" data-a="close">OK</button>');return;}
   give=pick.map(p=>({af:p.af,occ:p.occ,total:p.total,name:p.name}));}}
 try{await doSync();await api('POST','/api/bids/answer',{id,accept:yes,give});}catch(e){showCard('Could not answer',esc(e.message||'Try again in a moment.'),'<button class="btn primary" data-a="close">OK</button>');bidLoad(true);return;}
 if(yes){if(b.kind==='biz')S.owned[b.item]=owned(b.item)-b.qty;else S.props=S.props.filter(p=>!pick.includes(p));S.cash+=b.price;
  log('You sold '+bidWhat(b)+' to '+esc(b.name)+' for '+fmt(b.price)+'.','gold');afterChange();try{await doSync();}catch(e){}}
 else log('You turned down '+esc(b.name)+'\'s offer for '+bidWhat(b)+'.','');
 bidData.in=(bidData.in||[]).filter(x=>x.id!==id);closeModal();setTimeout(bidPrompt,600);}
async function bidCancel(id){try{await api('POST','/api/bids/cancel',{id});}catch(e){}await bidLoad(true);bidsList();}
/* the offer card: pick their buildings or outlets, how many, and a price between 50% and 300% of what it is worth */
function bidOpts(pl,city){const o=[];
 Object.keys(pl.pt||{}).forEach(cid=>{Object.keys(pl.pt[cid]).forEach(tid=>{const n=pl.pt[cid][tid],t=ptype(tid),c=pcity(cid);if(!t||!n)return;
  const why=!c?'Not on your property route':'';o.push({kind:'prop',item:tid,city:cid,n,label:t.name+' in '+(c?c.name:cid),unit:c?propPrice(t,c):0,why,here:cid===city});});});
 Object.keys(pl.b||{}).forEach(id=>{const b=BIZ.find(x=>x.id===id),n=pl.b[id];if(!b||!n)return;
  const why=!S.inds.includes(b.ind)?'You do not run '+IND[b.ind].name.lc():bizLocked(b)?'Still locked for you':'';o.push({kind:'biz',item:id,city:'',n,label:b.name,unit:unitCost(b,owned(b.id)),why});});
 return o.sort((a,b)=>(b.here?1:0)-(a.here?1:0)||(a.why?1:0)-(b.why?1:0));}
function bidOpen(h,city){if(GUEST||!ACC){guestAsk('chip');return;}const pl=(EM.othRaw||[]).find(x=>x.h===h);if(!pl)return;const opts=bidOpts(pl,city||'');
 bidDraft={pl,opts,i:opts.findIndex(x=>!x.why),qty:1,pct:1};if(bidDraft.i<0)bidDraft.i=0;bidMsg='';bidPaint();}
function bidPaint(){const d=bidDraft;if(!d)return;const o=d.opts[d.i];
 const list=d.opts.length?d.opts.map((x,i)=>'<button class="bidopt'+(i===d.i?' on':'')+'" data-a="bidpick" data-v="'+i+'"'+(x.why?' disabled':'')+'><b>'+esc(x.label)+'</b><span>'+(x.kind==='biz'?'Business · ':'Building · ')+x.n+' owned'+(x.why?' · '+esc(x.why):' · worth '+fmt(x.unit)+' each')+'</span></button>').join(''):'<p class="sub">They have nothing you can make an offer for yet.</p>';
 let body='<p>Make <b>'+esc(d.pl.n)+'</b>'+(d.pl.co?' of '+esc(d.pl.co):'')+' an offer. Your cash is held until they answer, and comes back if they say no or do not answer within 48 hours.</p><div class="bidopts">'+list+'</div>';
 let btn='<button class="btn ghost" data-a="close">Cancel</button>';
 if(o&&!o.why){const mx=Math.min(o.n,100);d.qty=Math.max(1,Math.min(d.qty,mx));const val=o.unit*d.qty,tot=val*d.pct;
  body+='<div class="bidset"><label>How many<input type="range" id="bid-qty" min="1" max="'+mx+'" step="1" value="'+d.qty+'"><b>'+d.qty+'</b></label>'+
   '<label>Your price<input type="range" id="bid-pct" min="50" max="300" step="5" value="'+Math.round(d.pct*100)+'"><b>'+bidFmtPct(d.pct)+' of value</b></label>'+
   '<p class="bidtot">Worth '+fmt(val)+' · your offer <b>'+fmt(tot)+'</b></p>'+(S.cash<tot?'<p class="amsg">You need '+fmt(tot)+' in cash.</p>':'')+(bidMsg?'<p class="amsg">'+esc(bidMsg)+'</p>':'')+'</div>';
  btn='<button class="btn primary" data-a="bidsend"'+(S.cash<tot?' disabled':'')+'>Send offer · '+fmt(tot)+'</button>'+btn;}
 showCard('Make an offer',body,btn);}
document.addEventListener('input',e=>{if(!bidDraft||!e.target)return;if(e.target.id==='bid-qty'){bidDraft.qty=+e.target.value;bidRepaintNums();}else if(e.target.id==='bid-pct'){bidDraft.pct=+e.target.value/100;bidRepaintNums();}});
function bidRepaintNums(){const d=bidDraft,o=d&&d.opts[d.i];if(!o)return;const val=o.unit*d.qty,tot=val*d.pct,q=$('bid-qty'),p=$('bid-pct');
 if(q&&q.nextElementSibling)q.nextElementSibling.textContent=d.qty;if(p&&p.nextElementSibling)p.nextElementSibling.textContent=bidFmtPct(d.pct)+' of value';
 const t=document.querySelector('.bidtot');if(t)t.innerHTML='Worth '+fmt(val)+' · your offer <b>'+fmt(tot)+'</b>';const s=document.querySelector('[data-a="bidsend"]');if(s){s.disabled=S.cash<tot;s.textContent='Send offer · '+fmt(tot);}}
function bidPick(i){if(!bidDraft)return;bidDraft.i=+i;bidDraft.qty=1;bidMsg='';bidPaint();}
async function bidSend(){const d=bidDraft,o=d&&d.opts[d.i];if(!o||o.why)return;const val=o.unit*d.qty,tot=Math.round(val*d.pct*100)/100;if(S.cash<tot)return;
 const s=document.querySelector('[data-a="bidsend"]');if(s){s.disabled=true;s.textContent='Sending…';}
 try{await doSync();const r=await api('POST','/api/bids/make',{seller:d.pl.h,kind:o.kind,item:o.item,city:o.city,qty:d.qty,value:val,price:tot});
  S.cash-=tot;S.bidOut=S.bidOut||{};S.bidOut[r.bid.id]=tot;bidHeldSet();log('You offered '+fmt(tot)+' to '+esc(d.pl.n)+' for '+bidWhat(r.bid)+'. The money is held until they answer.','');afterChange();try{await doSync();}catch(e){}
  bidDraft=null;showCard('Offer sent','<p>'+esc(d.pl.n)+' has 48 hours to answer. If they say no, or do not answer, your '+fmt(tot)+' comes straight back.</p>','<button class="btn primary" data-a="close">OK</button><button class="btn ghost" data-a="bids">My offers</button>');bidLoad(true);}
 catch(e){bidMsg=e.message||'Could not send the offer.';bidPaint();}}
function bidsList(){if(!bidData){bidLoad(true).then(()=>{if(bidData)bidsList();});return;}const now=bidData.now||Date.now()/1000;
 const inc=(bidData.in||[]),out=(bidData.out||[]).filter(b=>b.status==='open'||now-b.created<7*86400);
 const row=(b,acts)=>'<li><span><b>'+(b.mine?'To ':'From ')+esc(b.name)+'</b>'+bidWhat(b)+' · '+fmt(b.price)+'<small>'+(b.status==='open'?'Ends in about '+Math.max(1,Math.round((b.expires-now)/3600))+'h':b.status==='accepted'?'Accepted':b.status==='declined'?'Turned down':b.status==='cancelled'?'Taken back':'Expired')+'</small></span>'+acts+'</li>';
 const body=(inc.length?'<p><b>Offers for you</b></p><ul class="emolist">'+inc.map(b=>row(b,'<span class="bidacts"><button class="btn small primary" data-a="bidyes" data-v="'+b.id+'">Accept</button><button class="btn small ghost" data-a="bidno" data-v="'+b.id+'">No</button></span>')).join('')+'</ul>':'')+
  '<p><b>Offers you made</b></p>'+(out.length?'<ul class="emolist">'+out.map(b=>row(b,b.status==='open'?'<button class="btn small ghost" data-a="bidcancel" data-v="'+b.id+'">Take back</button>':'')).join('')+'</ul>':'<p class="sub">None yet. Tap a blue 👥 place on the Map to make an offer.</p>')+
  (S.bidHeld?'<p class="sub">Held for your open offers: '+fmt(S.bidHeld)+' (still counts in your net worth).</p>':'');
 showCard('Offers',body,'<button class="btn ghost" data-a="close">Close</button>');}
setInterval(()=>bidLoad(),120000);
