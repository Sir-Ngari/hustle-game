#!/usr/bin/env python3
"""Save a Meta (Facebook/Instagram) token for the game server.
Run as root with the token in the HMT environment variable (the console step does this).
It keeps only the part of the paste that Meta accepts, writes it to /etc/hustle.env and reports
which permissions and which Facebook Page / Instagram account it can use. It never prints the token."""
import os,sys,re,json,urllib.request,urllib.parse
raw=re.sub(r'\s','',os.environ.get('HMT',''));pre='EAAOmQFogn5QB'
parts=[pre+x for x in raw.split(pre) if x] if pre in raw else [raw]
cands=[]
for x in parts:
    m=re.match(r'[A-Za-z0-9]+',x)
    if m and len(m.group(0))>60 and m.group(0) not in cands:cands.append(m.group(0))
def get(path,params):return json.loads(urllib.request.urlopen('https://graph.facebook.com/v25.0/'+path+'?'+urllib.parse.urlencode(params),timeout=30).read())
good=None
for c in cands:
    try:get('act_1055789217482496',{'fields':'name','access_token':c});good=c;break
    except Exception:pass
if not good:print('STOPPED: Meta did not accept that token. Nothing was changed.');sys.exit(1)
p='/etc/hustle.env';s=open(p).read();s=re.sub(r'(?m)^HUSTLE_META_(TOKEN|ACCOUNT)=.*\n?','',s)
if s and not s.endswith('\n'):s+='\n'
open(p,'w').write(s+'HUSTLE_META_TOKEN=%s\nHUSTLE_META_ACCOUNT=1055789217482496\n'%good)
print('TOKEN SAVED')
try:
    sc=get('debug_token',{'input_token':good,'access_token':good}).get('data',{}).get('scopes',[])
    need=['ads_read','pages_show_list','pages_read_engagement','pages_manage_posts','instagram_basic','instagram_content_publish'];miss=[x for x in need if x not in sc]
    print('PERMISSIONS OK' if not miss else 'MISSING PERMISSIONS: '+', '.join(miss))
    ms=[x for x in ['read_insights','instagram_manage_insights'] if x not in sc]
    print('POST STATS PERMISSIONS OK' if not ms else 'POST STATS NEED: '+', '.join(ms))
except Exception as e:print('Could not read the permissions list')
try:
    pg=get('me/accounts',{'fields':'name,instagram_business_account{username}','access_token':good}).get('data',[])
    print('PAGE: '+(pg[0]['name']+(' + Instagram @'+pg[0]['instagram_business_account']['username'] if pg[0].get('instagram_business_account') else ' (no Instagram linked)') if pg else 'NONE FOUND: give hustle-server access to the Facebook Page'))
except Exception as e:print('PAGE: could not check (%s)'%str(e)[:120])
