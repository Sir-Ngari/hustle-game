"""Build public/index.html (the hosted game) from the artifact version of the game."""
import sys,re
src=sys.argv[1]; out=sys.argv[2]
s=open(src).read()
def rep(a,b,cnt=1):
    global s
    assert s.count(a)==cnt,(s.count(a),a[:90]); s=s.replace(a,b)
# swap the device-account block for the server-account block
i=s.index("/* ================= Accounts ================= */"); j=s.index("function save(){if(!ACC)return;",i)
k=s.index("saveAccs();}",j)+len("saveAccs();}")
s=s[:i]+open('accthosted.js').read()+"\nfunction save(){if(!ACC)return;S._uid=ACC.id;queueSync();}"+s[k:]
# number every news entry so the server can store each one once
rep("function log(t,k){if(!t)return;S.log.unshift({m:S.month,t,k:k||''});","function log(t,k){if(!t)return;S.logN=(S.logN||0)+1;S.log.unshift({m:S.month,t,k:k||'',n:S.logN});")
# click handlers for the account screens
i=s.index("accts:()=>showAccts('pick'),"); j=s.index("acctdelyes:()=>deleteAccount(v),",i)+len("acctdelyes:()=>deleteAccount(v),")
s=s[:i]+"accts:()=>{if(!ACC)return;stopAuto();acctView='menu';renderAccts();},acctclose:()=>{acctView=passLocked()?'payleft':null;renderAccts();},passopen:()=>openPay(),buyplan:()=>buyPlan(v),tipopen:()=>openTip(),tipamt:()=>tipPick(v),tipgo:()=>sendTip(),paylater:payLater,paygift:payGift,invite:openInvite,invcopy:inviteCopy,invshare:inviteShare,authmode:()=>{authMode=v;authMsg='';renderAccts();},authjump:()=>{authMode=v;authMsg='';renderAccts();const u=$('acc-user');if(u){u.scrollIntoView({behavior:'smooth',block:'center'});setTimeout(()=>u.focus({preventScroll:true}),400);}},forgotview:()=>{acctView='forgot';forgotDone='';authMsg='';renderAccts();},backlogin:()=>{acctView='auth';authMode='login';forgotDone='';authMsg='';renderAccts();},skipemail:()=>{emailSkip=true;acctView=null;renderAccts();},logout,installapp:installApp,leaderboard:()=>openBoard(),boardtab:()=>openBoard(v),retryboot:bootAuth,appupdate:appUpdate,"+s[j:]
# new game keeps the account and tells the server
rep("S=ACC?freshFor(ACC):fresh();","S=ACC?freshFor(ACC):fresh();newGameFlag=true;")
# start-up: ask the server who is playing
i=s.index("{const a=ACCS.list.find(x=>x.id===ACCS.active);if(a)loadAccount(a);}"); j=s.index("else startEvents();",i)+len("else startEvents();")
s=s[:i]+"window.addEventListener('error',()=>{if(typeof hideSplash==='function')setTimeout(()=>{if(acctView==='loading')return;hideSplash();},50);});\ntry{render();showTab(curTab);}catch(e){console.error('start-up render failed',e);}\nbootAuth();\npaintInstall();\nif('serviceWorker' in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));"+s[j:]
# header chip shows sync status
s=re.sub(r" \$\('acctchip'\)\.innerHTML=ACC\?avatar\(ACC\).*?;\n"," paintChip();\n",s,count=1)
assert "paintChip();\n $('fdn-title')" in s
# extra styles for the auth screens
rep(".acctbrand{",""".authtabs{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--ink);border-radius:3px;overflow:hidden}
.authtabs button{border:0;background:transparent;padding:10px;font-weight:700;font-size:14px}
.authtabs button[aria-selected="true"]{background:var(--ink);color:var(--paper)}
.amsg{margin:0;padding:10px 12px;border-radius:3px;background:var(--brass-soft);color:var(--ink);font-size:13.5px}
.aform input[type=password],.aform input[type=email]{width:100%;padding:10px 12px;border:1px solid var(--line);background:var(--paper);border-radius:3px;font-size:15px;color:var(--ink)}
.me{display:flex;align-items:center;gap:14px}
.hook{margin:2px 0 4px}
.hook-big{margin:0;font-family:var(--display);font-weight:900;font-size:30px;line-height:1.08;text-transform:uppercase;letter-spacing:.01em;color:var(--ink)}
.hook-big em{font-style:normal;color:var(--brass)}
.hook-sub{margin:8px 0 0;font-size:15px;color:var(--muted)}
.about{margin-top:18px;padding-top:18px;border-top:1px solid var(--line);display:flex;flex-direction:column;gap:12px}
.about h3{margin:0;font-family:var(--display);font-size:20px;text-transform:uppercase;letter-spacing:.04em;color:var(--brass)}
.about-lead{margin:0;font-size:15px;line-height:1.55}
.about-list{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}
.about-list li{display:flex;gap:12px;align-items:flex-start;padding:12px;border:1px solid var(--line);border-radius:10px;background:var(--paper);font-size:13.5px;line-height:1.45;color:var(--muted)}
.about-list b{display:block;color:var(--ink);font-size:15px;margin-bottom:2px}
.about-ic{font-size:24px;line-height:1}
.about-cta{margin-top:6px;padding:16px;border:2px solid var(--brass);border-radius:12px;background:var(--brass-soft);display:flex;flex-direction:column;gap:12px}
.about-cta .hook-big{font-size:24px}
.updbar{position:fixed;z-index:44;left:50%;transform:translateX(-50%);top:calc(10px + env(safe-area-inset-top,0px));width:min(480px,calc(100vw - 24px));display:flex;align-items:center;gap:12px;padding:12px 12px 12px 16px;border-radius:14px;background:#14261f;color:#fff;border:2px solid #ffd36b;box-shadow:0 14px 36px rgba(0,0,0,.4)}
.updbar span{flex:1;min-width:0;display:flex;flex-direction:column}.updbar b{font-size:15px}.updbar small{font-size:12.5px;opacity:.85}
.iossteps{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:8px;font-size:15px;line-height:1.5}
.passbar{display:flex;align-items:center;gap:10px;margin-top:8px;border:1px solid var(--brass);background:var(--brass-soft);color:var(--ink);border-radius:22px;padding:5px 6px 5px 14px;font-size:13px;text-align:left;max-width:100%}
.passbar span{flex:1;min-width:0}.passbar i{font-style:normal;font-weight:700;background:var(--brass);color:#fff;border-radius:16px;padding:4px 12px;white-space:nowrap}
.passbar.warn{border-color:var(--red)}.passbar.warn i{background:var(--red)}
.plans{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.plan{position:relative;display:flex;flex-direction:column;align-items:center;gap:2px;padding:18px 8px 14px;border:1px solid var(--line);border-radius:10px;background:var(--paper);color:var(--ink);text-align:center}
.plan:hover:not(:disabled){border-color:var(--ink)}.plan:disabled{opacity:.55;cursor:not-allowed}
.plan.pick{border:2px solid var(--brass)}
.plan em{position:absolute;top:-10px;left:50%;transform:translateX(-50%);font-style:normal;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;background:var(--brass);color:#fff;border-radius:10px;padding:1px 8px;white-space:nowrap}
.plan b{font-size:13.5px}.plan .pr{font-family:var(--display);font-size:24px;line-height:1.15;font-weight:700}.plan small{font-size:11.5px;color:var(--muted)}
.perks{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:4px;font-size:13.5px}
.invbanner{display:flex;gap:10px;align-items:center;margin:0;padding:10px 12px;border-radius:10px;background:var(--brass-soft);color:var(--ink);font-size:14px;border:1px solid var(--brass)}
.invbanner span:first-child{font-size:22px}
.invcta{display:flex;flex-direction:column;gap:6px;padding:12px;border:1px dashed var(--brass);border-radius:10px;font-size:13.5px}.invcta .btn{align-self:flex-start}
.invlink{width:100%;padding:10px 12px;border:1px solid var(--line);background:var(--paper);border-radius:6px;font-size:14px;color:var(--ink)}
.invstats{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.invstats b{color:var(--ink);font-size:18px;margin-right:3px}
.invlist{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}.invlist li{display:flex;align-items:center;gap:10px}
.invlist .ameta{flex:1;min-width:0;display:flex;flex-direction:column}.invlist .ameta span{font-size:12.5px;color:var(--muted)}
a.btn{text-decoration:none;display:inline-flex;align-items:center}
.plans.tips{grid-template-columns:repeat(5,minmax(0,1fr))}.plans.tips .plan{padding:14px 6px 12px}.plans.tips .pr{font-size:19px}
@media (max-width:520px){.plans.tips{grid-template-columns:repeat(3,minmax(0,1fr))}}
.paidbox{display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px;padding:10px 0}
.paidicon{width:56px;height:56px;border-radius:50%;display:grid;place-items:center;background:var(--green);color:#fff;font-size:30px;font-weight:700}
@media (max-width:420px){.plans:not(.tips){grid-template-columns:1fr}.plan{flex-direction:row;flex-wrap:wrap;justify-content:space-between;text-align:left;padding:14px}.plan small{width:100%}.plan em{left:auto;right:10px;transform:none}.plans.tips .plan{flex-direction:column;justify-content:center;text-align:center;padding:12px 4px}.plans.tips .plan small{width:auto}}
.acctbrand{""")
assert 'localStorage.getItem(SAVE)' not in s and 'ACCS' not in s, 'device-account code left behind'
head='''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="Build an empire from a street hustle to a billion.">
<meta name="theme-color" content="#0b1a2c">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Hustlempires">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="48x48" href="/icons/favicon-48.png">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"%3E%3Cdefs%3E%3ClinearGradient id="bg" x1="0" y1="0" x2="1" y2="1"%3E%3Cstop offset="0" stop-color="#264476"/%3E%3Cstop offset="1" stop-color="#0b1a2c"/%3E%3C/linearGradient%3E%3ClinearGradient id="gold" x1="0" y1="0" x2="0" y2="1"%3E%3Cstop offset="0" stop-color="#ffe08a"/%3E%3Cstop offset="1" stop-color="#ff8a2b"/%3E%3C/linearGradient%3E%3CclipPath id="r"%3E%3Crect width="512" height="512" rx="112"/%3E%3C/clipPath%3E%3C/defs%3E%3Cg clip-path="url(#r)"%3E%3Crect width="512" height="512" fill="url(#bg)"/%3E%3Cg fill="url(#gold)"%3E%3Cpath d="M120 420V150l40-40 40 40v270z"/%3E%3Cpath d="M312 420V110l40-44 40 44v310z"/%3E%3Crect x="190" y="250" width="132" height="54" rx="6"/%3E%3Crect x="96" y="420" width="320" height="22" rx="8"/%3E%3C/g%3E%3Cg fill="#0b1a2c" opacity=".55"%3E%3Crect x="144" y="170" width="12" height="18"/%3E%3Crect x="164" y="170" width="12" height="18"/%3E%3Crect x="144" y="206" width="12" height="18"/%3E%3Crect x="164" y="330" width="12" height="18"/%3E%3Crect x="144" y="366" width="12" height="18"/%3E%3Crect x="336" y="140" width="12" height="18"/%3E%3Crect x="356" y="176" width="12" height="18"/%3E%3Crect x="336" y="212" width="12" height="18"/%3E%3Crect x="356" y="330" width="12" height="18"/%3E%3Crect x="336" y="366" width="12" height="18"/%3E%3C/g%3E%3Cpath d="M232 196l12-30 12 14 12-14 12 30z" fill="#ffd36b"/%3E%3C/g%3E%3C/svg%3E">
<script>try{if((localStorage.getItem('hustle-skin')||'game')==='game')document.documentElement.classList.add('gm');}catch(e){document.documentElement.classList.add('gm');}</script>
<style>#splash{position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;background:radial-gradient(circle at 50% 35%,#264476,#0b1a2c 70%);color:#fff;font:600 15px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;transition:opacity .35s ease}
#splash b{font:800 26px/1 "Oswald","Arial Narrow",Impact,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#ffd36b}
#splash small{opacity:.75}#splash i{width:140px;height:4px;border-radius:2px;background:rgba(255,255,255,.15);overflow:hidden;position:relative}
#splash i::after{content:"";position:absolute;inset:0;width:40%;border-radius:2px;background:linear-gradient(90deg,#ffe08a,#ff8a2b);animation:spl 1.1s ease-in-out infinite}
@keyframes spl{from{transform:translateX(-100%)}to{transform:translateX(250%)}}
#splash.gone{opacity:0;pointer-events:none}
@media (prefers-reduced-motion:reduce){#splash i::after{animation:none;width:100%}}</style>
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:#eef0e6}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
<div id="splash" role="status" aria-live="polite"><svg width="96" height="96" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="splbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#264476"/><stop offset="1" stop-color="#0b1a2c"/></linearGradient><linearGradient id="splgold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe08a"/><stop offset="1" stop-color="#ff8a2b"/></linearGradient><clipPath id="splr"><rect width="512" height="512" rx="112"/></clipPath></defs><g clip-path="url(#splr)"><rect width="512" height="512" fill="url(#splbg)"/><g fill="url(#splgold)"><path d="M120 420V150l40-40 40 40v270z"/><path d="M312 420V110l40-44 40 44v310z"/><rect x="190" y="250" width="132" height="54" rx="6"/><rect x="96" y="420" width="320" height="22" rx="8"/></g><g fill="#0b1a2c" opacity=".55"><rect x="144" y="170" width="12" height="18"/><rect x="164" y="170" width="12" height="18"/><rect x="144" y="206" width="12" height="18"/><rect x="164" y="330" width="12" height="18"/><rect x="144" y="366" width="12" height="18"/><rect x="336" y="140" width="12" height="18"/><rect x="356" y="176" width="12" height="18"/><rect x="336" y="212" width="12" height="18"/><rect x="356" y="330" width="12" height="18"/><rect x="336" y="366" width="12" height="18"/></g><path d="M232 196l12-30 12 14 12-14 12 30z" fill="#ffd36b"/></g></svg><b>Hustlempires</b><small>Loading your empire…</small><i></i></div>
'''
import hashlib
assert s.count("'__APP_VER__'")==1
s=s.replace("'__APP_VER__'","'"+hashlib.sha256(s.encode()).hexdigest()[:12]+"'")
open(out,'w').write(head+s+'\n</body>\n</html>\n')
print('built',out,len(head+s),'bytes')
