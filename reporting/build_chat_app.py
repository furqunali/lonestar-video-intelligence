"""Build the SHARED offline chat-support app as a Windows HTA + a RUN button.

- Runs by double-click (the RUN_Chat_Support.cmd 'run button', or the .hta itself)
  via built-in mshta.exe — NO server, NO port, NO install.
- All data + evidence pictures are EMBEDDED in the .hta (works offline).
- Conversations/memory/approvals are stored in ONE shared JSON file next to the
  .hta (`SLP_Chat_Data.json`) via FileSystemObject, so EVERYONE on the shared
  drive sees the SAME conversations. Falls back to localStorage if opened as a
  plain .html (e.g. in a normal browser) so it still works.

    python reporting/build_chat_app.py
      -> reports/SLP_Chat_Support.hta  +  reports/RUN_Chat_Support.cmd
"""
from __future__ import annotations

import base64, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANA = ROOT / "reports" / "incident_analysis"

INCIDENTS = [
    dict(slug="5nov_cash", title="Cash theft — Register 1 (5 Nov)", category="Cash theft",
         when="05 Nov 2024 07:09 AM", where="Register 1 (C3)", cashier="Cashier (Reg 1)", amount=0.0,
         finding="Hands in the OPEN cash drawer, bills removed - no customer, POS idle (no sale).",
         frames=["key"]),
    dict(slug="12nov_cash", title="Cash theft — Register 1 (12 Nov)", category="Cash theft",
         when="12 Nov 2024 07:13 AM", where="Register 1 (C3)", cashier="Cashier (Reg 1)", amount=0.0,
         finding="Loose cash counted at the open drawer - no customer, POS idle (no sale).",
         frames=["key"]),
    dict(slug="jordan_cancel", title="Collusion void — Jordan Lee", category="Collusion void",
         when="08 Nov 2024 05:36 PM", where="Register 2 (C2)", cashier="JORDAN LEE", amount=18.86,
         finding=("Sale CANCELLED -$18.86 (5 items: Pepsi 1L x2, Cheetos, Pistachios, Kool-Aid + $0.81 tax). "
                  "No cash collected. Cashier-customer hand contact, then the receipt dropped in the bin."),
         frames=["receipt", "key", "handoff", "dustbin"]),
    dict(slug="27jan_steal", title="Shoplifting — 27 Jan (group)", category="Organized shoplifting",
         when="27 Jan 2024 08:06 PM", where="Sales floor (IP Cam 16/22)", cashier="", amount=0.0,
         finding="4-person group: arrive (parking) -> enter together -> gather at cooler -> grab & conceal with shielding.",
         frames=["entry", "entry2", "suspect", "key"]),
    dict(slug="14may_steal", title="Shoplifting — 14 May (group)", category="Organized shoplifting",
         when="14 May 2024 04:41 PM", where="Sales floor (IP Cam 15/16)", cashier="", amount=0.0,
         finding=">=5-person group: parking arrival -> cooler drinks/case -> merchandise concealed into clothing; a gloved accomplice.",
         frames=["entry", "suspect", "key"]),
]


def data_uri(slug, name):
    p = ANA / slug / f"{name}_after.jpg"
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else None


def build_data():
    inc = []
    for i in INCIDENTS:
        frames = [{"name": n, "img": data_uri(i["slug"], n)} for n in i["frames"]]
        inc.append({**i, "frames": [f for f in frames if f["img"]]})
    analytics = {}
    aj = ROOT / "reports" / "analytics" / "analytics.json"
    if aj.exists():
        try:
            analytics = json.loads(aj.read_text())
        except Exception:
            analytics = {}
    return {
        "incidents": inc,
        "risk": analytics.get("risk", []),
        "health": analytics.get("health", []),
        "kpis": analytics.get("rollup", {}).get("totals", {}),
        "transactions": [
            {"cashier": "JORDAN LEE", "register": "Register 2", "tx_type": "cancel", "amount": 18.86, "ts": "2024-11-08 17:36"},
            {"cashier": "Cashier (Reg 1)", "register": "Register 1", "tx_type": "no_sale", "amount": 0.0, "ts": "2024-11-05 07:09"},
            {"cashier": "Cashier (Reg 1)", "register": "Register 1", "tx_type": "no_sale", "amount": 0.0, "ts": "2024-11-12 07:13"},
        ],
        "report_url": r"G:\Shared drives\4. AP\lonestar-video-intelligence\01_Director_Report",
        "generated": "14 September 2026",
    }


HEAD = """<html><head><meta http-equiv="x-ua-compatible" content="IE=edge"><meta charset="utf-8">
<title>Sugarland Petroleum - Chat Support</title>
<hta:application id="slp" applicationname="SLP Chat Support" border="thin" scroll="no"
 singleinstance="no" maximizebutton="yes" minimizebutton="yes" caption="yes"/>
<style>
:root{--navy:#12314f;--teal:#0c8f95;--teal2:#26c6cc;--bg:#eef2f7;--panel:#fff;--line:#e1e8f0;
 --ink:#17202b;--ink2:#5a6b7d;--ink3:#8595a7;--user:#0c8f95;--bot:#f0f4f8;--pass:#1f9d6b;--crit:#cf4141;--warn:#c47f1a}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--ink);display:flex;justify-content:center}
#app{width:100%;max-width:860px;background:var(--panel);display:flex;flex-direction:column;height:100vh}
.hd{background:linear-gradient(135deg,#12314f,#123047);color:#fff;padding:14px 18px}
.hd .b{font-weight:800;font-size:16px}.hd .s{font-size:11.5px;color:#b8c7d6}
.id{display:flex;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line);background:var(--bot);flex-wrap:wrap;align-items:center}
.id input,.id select{padding:8px 10px;border:1px solid var(--line);border-radius:9px;font-size:13px}
.id input{flex:1;min-width:110px}
.id button{background:var(--teal);color:#fff;border:none;border-radius:9px;padding:8px 15px;font-size:13px;cursor:pointer;font-weight:600}
.who{font-size:12px;color:var(--ink2)}
.tabs{display:flex;border-bottom:1px solid var(--line)}
.tab{flex:1;text-align:center;padding:11px;font-size:13px;color:var(--ink2);cursor:pointer;border-bottom:2px solid transparent}
.tab.on{color:var(--teal);border-bottom-color:var(--teal);font-weight:700}
.tab .badge{background:var(--crit);color:#fff;border-radius:10px;padding:0 6px;font-size:10px;margin-left:5px}
.view{flex:1;overflow-y:auto;display:none;flex-direction:column}.view.on{display:flex}
#msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:9px}
.msg{max-width:82%;padding:10px 13px;border-radius:14px;font-size:14px;white-space:pre-wrap;line-height:1.5;word-wrap:break-word}
.msg.user{align-self:flex-end;background:var(--user);color:#fff}
.msg.assistant{align-self:flex-start;background:var(--bot);color:var(--ink)}
.imgs{display:flex;flex-wrap:wrap;gap:7px;align-self:flex-start;max-width:92%}
.imgs img{width:150px;height:88px;object-fit:cover;border:1px solid var(--line);border-radius:9px;cursor:pointer}
.chips{display:flex;gap:7px;flex-wrap:wrap;padding:8px 14px}
.chip{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:6px 12px;font-size:12px;cursor:pointer;color:var(--teal)}
.reqs,.team{padding:14px;overflow-y:auto}
.req{border:1px solid var(--line);border-radius:11px;padding:12px;margin-bottom:9px;font-size:13px}
.req b{color:var(--teal2)}.req .btns{margin-top:9px}
.req button{border:none;border-radius:8px;padding:7px 16px;font-size:12.5px;cursor:pointer;color:#fff;font-weight:600;margin-right:7px}
.req .ap{background:var(--pass)}.req .dn{background:var(--crit)}
.tmsg{font-size:12.5px;padding:7px 2px;border-bottom:1px solid var(--line)}
.tmsg .u{font-weight:700;color:var(--navy)}.tmsg .r{color:var(--ink3);font-size:10.5px}.tmsg .t{color:var(--ink2)}
.empty{color:var(--ink3);font-size:13px;text-align:center;padding:30px}
.inp{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)}
.inp input{flex:1;padding:12px;border:1px solid var(--line);border-radius:11px;font-size:14px}
.inp button{background:var(--teal);color:#fff;border:none;border-radius:11px;padding:0 20px;font-weight:700;cursor:pointer;font-size:14px}
.foot{font-size:10.5px;color:var(--ink3);text-align:center;padding:6px}
</style></head><body><div id="app">
<div class="hd"><div class="b">Sugarland Petroleum &middot; Chat Support</div>
 <div class="s">AI Video-Intelligence assistant &middot; runs locally (no server) &middot; shared team conversations</div></div>
<div class="id"><input id="uid" placeholder="your name">
 <select id="role"><option value="staff">Camera team / Staff</option><option value="manager">Manager</option>
 <option value="director">Director</option></select>
 <button onclick="startSession()">Start</button><span class="who" id="who"></span></div>
<div class="tabs"><div class="tab on" data-v="chat" onclick="tab('chat')">Chat</div>
 <div class="tab" data-v="team" onclick="tab('team')">All conversations</div>
 <div class="tab" data-v="appr" onclick="tab('appr')" id="tabAppr" style="display:none">Approvals<span class="badge" id="badge" style="display:none">0</span></div></div>
<div class="view on" id="v-chat"><div id="msgs"></div><div class="chips" id="chips"></div>
 <div class="inp"><input id="text" placeholder="Ask anything - 'summary', 'evidence for jordan', 'risk ranking'"
  onkeydown="if(event.keyCode===13)send()"><button onclick="send()">Send</button></div></div>
<div class="view" id="v-team"><div class="team" id="teamBox"></div></div>
<div class="view" id="v-appr"><div class="reqs" id="reqs"></div></div>
<div class="foot">Everyone sees the same conversations (shared file on the drive) &middot; sensitive actions need Manager&rarr;Director approval</div>
</div>
"""

APP_JS = r"""<script>
var D=window.DATA,RANK={staff:0,manager:1,director:2,admin:3};
var ACT={help:[],list_incidents:[],get_summary:[],get_evidence:[],get_risk_ranking:[],get_camera_health:[],
 get_kpis:[],search_transaction:[],generate_report:['manager'],export_data:['manager'],
 email_director:['director'],publish_shared_drive:['manager','director']};
var MINROLE={generate_report:'manager',export_data:'manager',email_director:'manager',publish_shared_drive:'manager'};
var INTENTS=[[/\b(help|what can you|capabilit|commands?)\b/i,'help'],
 [/\b(publish|shared drive|upload report)\b/i,'publish_shared_drive'],
 [/\b(email|send).{0,20}(director|mustafa)\b/i,'email_director'],
 [/\b(generate|rebuild|refresh|regenerate).{0,15}report\b/i,'generate_report'],
 [/\b(export|download).{0,15}(data|transactions?|csv)\b/i,'export_data'],
 [/\b(evidence|proof|photos?|pictures?|footage|clips?|annotat\w*)\b/i,'get_evidence'],
 [/\b(summary|overview|brief|situation|status|how are things|update me)\b/i,'get_summary'],
 [/\b(risk|rank|worst|priorit)\b/i,'get_risk_ranking'],
 [/\b(camera|tamper|health|uptime)\b/i,'get_camera_health'],
 [/\b(kpi|metric|totals?|scorecard|numbers?|stats?)\b/i,'get_kpis'],
 [/\b(search|find|look ?up|transactions?|voids?|cancels?|refunds?|cashiers?)\b/i,'search_transaction'],
 [/\b(incidents?|thefts?|shoplift\w*|cases?|jordan)\b/i,'list_incidents']];
// ---- shared store (FileSystemObject on the drive; localStorage fallback) ----
var FSO=null;try{FSO=new ActiveXObject('Scripting.FileSystemObject')}catch(e){}
function appFolder(){try{var h=decodeURIComponent(location.href).replace(/^file:\/+/,'').replace(/\//g,'\\');return FSO.GetParentFolderName(h)}catch(e){return ''}}
var DBPATH=FSO?(appFolder()+'\\SLP_Chat_Data.json'):null;
function DB(){try{if(FSO&&FSO.FileExists(DBPATH)){var f=FSO.OpenTextFile(DBPATH,1,false,-1);var s=f.ReadAll();f.Close();return JSON.parse(s||'{}')}}catch(e){}
 try{return JSON.parse(localStorage.getItem('slp_chat')||'{}')}catch(e){}return {}}
function saveDB(d){var s=JSON.stringify(d);
 try{if(FSO){var f=FSO.CreateTextFile(DBPATH,true,true);f.Write(s);f.Close();return}}catch(e){}
 try{localStorage.setItem('slp_chat',s)}catch(e){}}
function ensure(){var d=DB();d.sessions=d.sessions||{};d.memory=d.memory||{};d.requests=d.requests||[];return d}
var SID=null,USER='',ROLE='staff',CUR='chat',lastLen=-1;
try{SID=localStorage.getItem('slp_sid');USER=localStorage.getItem('slp_user')||'';ROLE=localStorage.getItem('slp_role')||'staff'}catch(e){}
function el(i){return document.getElementById(i)}
function tab(v){CUR=v;var xs=['chat','team','appr'];for(var k=0;k<xs.length;k++){el('v-'+xs[k]).className='view'+(xs[k]===v?' on':'')}
 var ts=document.querySelectorAll('.tab');for(var j=0;j<ts.length;j++){ts[j].className='tab'+(ts[j].getAttribute('data-v')===v?' on':'')}
 if(v==='team')renderTeam();if(v==='appr')renderReqs()}
function add(s,t){var d=document.createElement('div');d.className='msg '+s;d.appendChild(document.createTextNode(t));
 el('msgs').appendChild(d);el('msgs').scrollTop=el('msgs').scrollHeight}
function addImgs(imgs){if(!imgs||!imgs.length)return;var w=document.createElement('div');w.className='imgs';
 for(var k=0;k<imgs.length;k++){var im=document.createElement('img');im.src=imgs[k];
  im.onclick=(function(u){return function(){var win=window.open('','_blank');if(win)win.document.write('<img src="'+u+'" style="max-width:100%">')}})(imgs[k]);
  w.appendChild(im)}el('msgs').appendChild(w);el('msgs').scrollTop=el('msgs').scrollHeight}
function chips(l){el('chips').innerHTML='';l=l||[];for(var k=0;k<l.length;k++){(function(s){var c=document.createElement('span');
 c.className='chip';c.appendChild(document.createTextNode(s));c.onclick=function(){el('text').value=s;send()};el('chips').appendChild(c)})(l[k])}}
function roleTabs(){el('tabAppr').style.display=(RANK[ROLE]>=1)?'block':'none'}
function startSession(){USER=(el('uid').value||'guest');ROLE=el('role').value;SID='s'+(new Date()).getTime()+Math.floor(Math.random()*999);
 try{localStorage.setItem('slp_sid',SID);localStorage.setItem('slp_user',USER);localStorage.setItem('slp_role',ROLE)}catch(e){}
 var d=ensure();d.sessions[SID]={user:USER,role:ROLE,msgs:[]};saveDB(d);
 el('who').textContent=USER+' - '+ROLE;el('msgs').innerHTML='';roleTabs();tab('chat');lastLen=-1;
 push('assistant','Hello '+USER+"! Ask me anything - reporting, real-time data, evidence, analytics, or a summary. I can also run actions (with approval).",null);
 chips(['summary','show incidents','evidence for jordan','risk ranking','camera health','help'])}
function push(sender,text,imgs){var d=ensure();if(!d.sessions[SID])d.sessions[SID]={user:USER,role:ROLE,msgs:[]};
 d.sessions[SID].msgs.push({sender:sender,text:text,imgs:imgs||null,ts:(new Date()).getTime()});saveDB(d);
 add(sender,text);if(imgs)addImgs(imgs);lastLen=d.sessions[SID].msgs.length}
function renderChat(){var d=ensure();var s=d.sessions[SID];if(!s)return;if(s.msgs.length===lastLen)return;lastLen=s.msgs.length;
 el('msgs').innerHTML='';for(var k=0;k<s.msgs.length;k++){var m=s.msgs[k];add(m.sender,m.text);if(m.imgs)addImgs(m.imgs)}}
function restore(){if(USER){el('uid').value=USER;el('role').value=ROLE;el('who').textContent=USER+' - '+ROLE;roleTabs()}
 if(SID){renderChat()}}
// ---- engine ----
function rank(r){return RANK[r]||0}
function matchInc(i,q){q=(q||'').toLowerCase();var hay=[i.slug,i.title,i.category,i.when,i.where,i.cashier,i.finding].join(' ').toLowerCase();
 var amt=(''+i.amount);if(i.amount&&amt!=='0'&&amt!=='0.0'&&q.indexOf(amt)>=0)return true;
 var toks=q.match(/[a-z0-9.]{3,}/g)||[];var stop={the:1,and:1,for:1,about:1,show:1,give:1,tell:1,provide:1,detail:1,details:1,incident:1,incidents:1,theft:1,evidence:1};
 for(var k=0;k<toks.length;k++){if(stop[toks[k]])continue;if(hay.indexOf(toks[k])>=0)return true}return false}
function incImgs(i){var o=[];for(var k=0;k<(i.frames||[]).length;k++)o.push(i.frames[k].img);return o}
function respond(text){var t=(text||''),low=t.toLowerCase();var mem=(ensure().memory[USER]||{});
 var rm=t.match(/remember\s+(?:that\s+)?(?:my\s+)?([a-z ]{2,20})\s+is\s+(.+)/i);
 if(rm){var d=ensure();d.memory[USER]=d.memory[USER]||{};d.memory[USER][rm[1].toLowerCase().replace(/(^\s+|\s+$)/g,'')]=rm[2].replace(/[.?!\s]+$/,'');saveDB(d);
  return {text:"Got it - I'll remember your "+rm[1].toLowerCase().replace(/(^\s+|\s+$)/g,'')+" is "+rm[2].replace(/[.?!\s]+$/,'')+"."}}
 if(/\b(hi|hello|hey|salam|assalam)\b/i.test(low)&&low.length<28)return {text:'Hello'+(mem.name?' '+mem.name:'')+"! Ask about incidents, risk, camera health, evidence, or a summary.",suggestions:['summary','show incidents','evidence for jordan','risk ranking']};
 if(/\b(thanks|thank you|shukriya)\b/i.test(low))return {text:"You're welcome. Anything else?"};
 for(var k=0;k<INTENTS.length;k++){if(INTENTS[k][0].test(low)){var a=INTENTS[k][1];
   if((ACT[a]||[]).length===0&&!MINROLE[a])return {run:a,params:{query:t}};return {requestAction:a,params:{query:t}}}}
 return {text:"I can show incidents, a summary, evidence pictures, risk ranking, camera health, KPIs, search transactions, or (with approval) generate/publish reports. Try 'help'.",suggestions:['help','summary','evidence for jordan','risk ranking']}}
function runRead(action,params){var q=params.query||'';
 if(action==='help'){var o=[];for(var a in ACT){o.push(' - '+a+(ACT[a].length?'  (needs '+ACT[a].join('/')+' approval)':''))}return {text:'I can:\n'+o.join('\n')}}
 if(action==='list_incidents'){var hits=[];for(var k=0;k<D.incidents.length;k++)if(matchInc(D.incidents[k],q))hits.push(D.incidents[k]);
  if(hits.length===1){var i=hits[0];return {text:i.title+' - '+i.when+' - '+i.where+'\n'+i.finding+(i.amount?'\nAmount: $'+i.amount:'')+(i.cashier?'\nCashier: '+i.cashier:''),images:incImgs(i)}}
  if(hits.length>1){var t2='';for(var m=0;m<hits.length;m++)t2+=' - '+hits[m].title+' ('+hits[m].when+')\n';return {text:hits.length+' matching incidents:\n'+t2}}
  var t3='';for(var n=0;n<D.incidents.length;n++)t3+=' - '+D.incidents[n].title+'\n';return {text:D.incidents.length+' incidents on file:\n'+t3}}
 if(action==='get_summary'){var r=D.risk[0]||null,kk=D.kpis||{},h=D.health||[],ok=0;for(var z=0;z<h.length;z++)if(h[z].clarity==='OK')ok++;
  return {text:'Summary - '+D.incidents.length+' incidents, '+(kk.exceptions||'?')+' POS exceptions ($'+(kk.exception_amount||'?')+'), cameras '+ok+'/'+h.length+' OK'+(r?', top risk: '+r.cashier+' ('+r.band+')':'')+'.\nFull report: '+D.report_url}}
 if(action==='get_evidence'){var pk=[];for(var k2=0;k2<D.incidents.length;k2++)if(matchInc(D.incidents[k2],q))pk.push(D.incidents[k2]);if(!pk.length)pk=D.incidents;
  var imgs=[],tt='';for(var p=0;p<pk.length;p++){tt+=' - '+pk[p].title+': '+pk[p].frames.length+' frame(s)\n';var ii=incImgs(pk[p]);for(var y=0;y<ii.length;y++)imgs.push(ii[y])}
  return {text:pk.length+' evidence set(s) - annotated frames:\n'+tt,images:imgs}}
 if(action==='get_risk_ranking'){if(!D.risk.length)return {text:'No exceptions to rank.'};var t4='';for(var k3=0;k3<Math.min(5,D.risk.length);k3++){var rr=D.risk[k3];t4+=' '+(k3+1)+'. '+rr.cashier+' - '+rr.tx_type+' - $'+rr.amount+' - score '+rr.score+' ('+rr.band+')\n'}return {text:'Risk ranking:\n'+t4}}
 if(action==='get_camera_health'){var t5='';for(var k4=0;k4<(D.health||[]).length;k4++)t5+=' - '+D.health[k4].clip+': '+D.health[k4].clarity+'\n';return {text:'Camera health (hardened):\n'+t5}}
 if(action==='get_kpis'){var kp=D.kpis||{},o2=[];for(var kx in kp)o2.push(kx.replace(/_/g,' ')+'='+kp[kx]);return {text:'KPIs: '+o2.join(', ')}}
 if(action==='search_transaction'){var res=[];for(var k5=0;k5<D.transactions.length;k5++){var x=D.transactions[k5];
   var okc=!params.cashier||x.cashier.toLowerCase().indexOf(params.cashier.toLowerCase())>=0;var okt=!params.tx_type||x.tx_type.indexOf(params.tx_type)>=0;var oka=!params.min_amount||x.amount>=params.min_amount;
   if(okc&&okt&&oka)res.push(x)}var t6='';for(var q2=0;q2<res.length;q2++)t6+=' - '+res[q2].ts+' '+res[q2].cashier+' '+res[q2].tx_type+' $'+res[q2].amount+'\n';return {text:res.length+' transaction(s):\n'+t6}}
 return {text:'Done.'}}
function execSensitive(action){
 if(action==='export_data'){exportCSV();return 'Exported transactions to SLP_transactions_export.csv (next to this app).'}
 if(action==='publish_shared_drive')return 'Approved to publish. The report is at:\n'+D.report_url;
 if(action==='generate_report')return 'Report regeneration approved (run the report pipeline to rebuild).';
 if(action==='email_director')return 'Approved to email the Director a summary.';return 'Executed.'}
function exportCSV(){try{if(!FSO)return;var rows='cashier,register,tx_type,amount,ts\n';for(var k=0;k<D.transactions.length;k++){var x=D.transactions[k];rows+=x.cashier+','+x.register+','+x.tx_type+','+x.amount+','+x.ts+'\n'}
 var f=FSO.CreateTextFile(appFolder()+'\\SLP_transactions_export.csv',true,false);f.Write(rows);f.Close()}catch(e){}}
function requestAction(action,params){
 if(MINROLE[action]&&rank(ROLE)<rank(MINROLE[action]))return {text:'Blocked: '+action+' needs role >= '+MINROLE[action]+' (you are '+ROLE+').'};
 var chain=(ACT[action]||[]).slice();if(!chain.length)return runRead(action,params);
 var d=ensure();var id='r'+(new Date()).getTime();
 d.requests.push({id:id,action:action,user:USER,role:ROLE,session:SID,status:'pending_'+chain[0],pending:chain,params:params});saveDB(d);
 return {text:'[locked] Requested '+action+'. Needs '+chain.join(' -> ')+' approval - waiting on the '+chain[0]+'.'}}
function decide(id,decision){var d=ensure();var r=null;for(var k=0;k<d.requests.length;k++)if(d.requests[k].id===id)r=d.requests[k];if(!r)return;
 var next=r.pending[0];if(rank(ROLE)<rank(next))return;
 if(decision==='deny'){r.status='denied';r.pending=[]}else{r.pending.shift();if(r.pending.length){r.status='pending_'+r.pending[0]}else{r.status='executed';r.result=execSensitive(r.action)}}
 var msg=r.status==='executed'?('[approved] '+r.action+' - executed.\n'+(r.result||'')):r.status==='denied'?('[denied] '+r.action+' was denied by the '+ROLE+'.'):('[ok] '+ROLE+' approved '+r.action+' - now waiting on the '+r.pending[0]+'.');
 var s=d.sessions[r.session];if(s)s.msgs.push({sender:'assistant',text:msg,ts:(new Date()).getTime()});saveDB(d);
 if(r.session===SID){lastLen=-1;renderChat()}renderReqs()}
function renderReqs(){if(RANK[ROLE]<1){el('badge').style.display='none';return}
 var d=ensure(),p=[];for(var k=0;k<d.requests.length;k++){var r=d.requests[k];if((''+r.status).indexOf('pending_')===0&&rank(ROLE)>=rank(r.pending[0]))p.push(r)}
 el('badge').style.display=p.length?'inline':'none';el('badge').innerHTML=p.length;
 var b=el('reqs');b.innerHTML='';if(!p.length){b.innerHTML='<div class="empty">No pending approvals.</div>';return}
 for(var j=0;j<p.length;j++){(function(r){var dv=document.createElement('div');dv.className='req';
  dv.innerHTML='<b>'+r.action+'</b> - requested by '+r.user+'<br><span style="color:#8595a7">needs '+r.pending.join(' -> ')+' approval</span><div class="btns"><button class="ap">Approve</button><button class="dn">Deny</button></div>';
  dv.getElementsByClassName('ap')[0].onclick=function(){decide(r.id,'approve')};dv.getElementsByClassName('dn')[0].onclick=function(){decide(r.id,'deny')};b.appendChild(dv)})(p[j])}}
function renderTeam(){var b=el('teamBox');var d=ensure();var all=[];
 for(var sid in d.sessions){var s=d.sessions[sid];for(var k=0;k<s.msgs.length;k++)all.push({u:s.user,r:s.role,sender:s.msgs[k].sender,text:s.msgs[k].text,ts:s.msgs[k].ts})}
 all.sort(function(a,c){return a.ts-c.ts});all=all.slice(-100);
 b.innerHTML='';if(!all.length){b.innerHTML='<div class="empty">No conversations yet.</div>';return}
 for(var j=0;j<all.length;j++){var m=all[j];var e=document.createElement('div');e.className='tmsg';
  e.innerHTML='<span class="u">'+m.u+'</span> <span class="r">'+m.r+' - '+m.sender+'</span><br><span class="t">'+(''+m.text).replace(/</g,'&lt;').substr(0,220)+'</span>';b.appendChild(e)}
 b.scrollTop=b.scrollHeight}
function send(){var t=el('text').value;if(!t)return;if(!SID)startSession();el('text').value='';push('user',t,null);
 var r=respond(t);var out;if(r.run){out=runRead(r.run,r.params);push('assistant',out.text,out.images)}
 else if(r.requestAction){out=requestAction(r.requestAction,r.params);push('assistant',out.text,out.images)}
 else push('assistant',r.text,r.images);chips(r.suggestions);renderReqs()}
// live refresh so everyone sees the same conversations/approvals
setInterval(function(){if(!SID)return;if(CUR==='chat')renderChat();if(CUR==='team')renderTeam();renderReqs()},3000);
restore();renderReqs();
</script></body></html>"""


def main():
    data = build_data()
    html = HEAD + "<script>window.DATA=" + json.dumps(data) + ";</script>\n" + APP_JS
    out = ROOT / "reports" / "SLP_Chat_Support.hta"
    out.write_text(html, encoding="utf-8")
    run = ROOT / "reports" / "RUN_Chat_Support.cmd"
    run.write_text('@echo off\r\nstart "" "%~dp0SLP_Chat_Support.hta"\r\n', encoding="utf-8")
    mb = out.stat().st_size / 1024 / 1024
    print(f"Wrote {out.name} ({mb:.1f} MB) + {run.name}  "
          f"images={sum(len(i['frames']) for i in data['incidents'])}")


if __name__ == "__main__":
    main()
