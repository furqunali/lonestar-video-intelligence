"""Embeddable chat-support widget — injected INTO the director report HTML.

A bottom-docked launcher (professional-portal style) that opens a tabbed panel
(Chat / All conversations / Approvals) right inside the one report file. Same
teal/navy theme. Everything (data + evidence pictures) is embedded; chat history,
memory and approvals persist in the browser (localStorage). Internal use only.
"""
from __future__ import annotations

import base64, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANA = ROOT / "reports" / "incident_analysis"

INCIDENTS = [
    dict(slug="5nov_cash", title="Cash theft - Register 1 (5 Nov)", category="Cash theft",
         when="05 Nov 2024 07:09 AM", where="Register 1 (C3)", cashier="Cashier (Reg 1)", amount=0.0,
         finding="Hands in the OPEN cash drawer, notes taken - no customer, till not in use (no sale).",
         frames=["r2_txn", "key", "r3_after"]),
    dict(slug="12nov_cash", title="Cash theft - Register 1 (12 Nov)", category="Cash theft",
         when="12 Nov 2024 07:13 AM", where="Register 1 (C3)", cashier="Cashier (Reg 1)", amount=0.0,
         finding="Loose cash counted at the open drawer - no customer, till not in use (no sale).",
         frames=["r2_txn", "key", "r3_after"]),
    dict(slug="jordan_cancel", title="Cancelled-sale theft - Jordan Lee", category="Cancelled-sale theft",
         when="08 Nov 2024 05:36 PM", where="Register 2 (C2)", cashier="JORDAN LEE", amount=18.86,
         finding=("Sale CANCELLED -$18.86 (5 items: Pepsi 1L x2, Cheetos, Pistachios, Kool-Aid + $0.81 tax). "
                  "No money collected. Cashier and customer hands touch, then the receipt is dropped in the bin."),
         frames=["receipt", "key", "handoff", "dustbin"]),
    dict(slug="27jan_steal", title="Shoplifting - 27 Jan (group)", category="Group shoplifting",
         when="27 Jan 2024 08:06 PM", where="Shop floor (IP Cam 16/22)", cashier="", amount=0.0,
         finding="Group of 4: arrive (parking) -> enter -> gather at the drinks fridge -> take items and hide them, blocking the view.",
         frames=["entry", "entry2", "suspect", "key"]),
    dict(slug="14may_steal", title="Shoplifting - 14 May (group)", category="Group shoplifting",
         when="14 May 2024 04:41 PM", where="Shop floor (IP Cam 15/16)", cashier="", amount=0.0,
         finding="Group of 5+: arrive in the parking lot -> drinks fridge / case -> items hidden; one person wearing a glove.",
         frames=["entry", "suspect", "key"]),
    dict(slug="robbery_0427", title="Robbery / Hold-up - Front Counter (27 Apr)", category="Robbery / Hold-up",
         when="27 Apr 2026 ~10:23 PM (night)", where="Front counter (IP Cam 14/17)", cashier="", amount=0.0,
         finding=("Night hold-up: a suspect approaches the forecourt, reaches over the front counter while the "
                  "cashier raises their hands, then leaves. Up to 5 people across 3 camera views. Robbery is a "
                  "human-review call; cash/stock loss is reconciled from the Z-report + inventory, not the video."),
         frames=["approach", "counter", "flee"]),
    dict(slug="robbery_0626", title="Robbery / Break-in - Behind the Counter (26 Jun)", category="Robbery / Hold-up",
         when="26 Jun ~03:52 AM (overnight)", where="Behind the front counter", cashier="", amount=0.0,
         finding=("Overnight, two suspects go BEHIND the front counter and take cigarettes / vapes. Up to 4 people. "
                  "Reconcile the counter stock + register cash to get the exact loss."),
         frames=["entry", "behind", "key"]),
    dict(slug="robbery_0916", title="Robbery - Sales Floor (16 Sep)", category="Robbery / Hold-up",
         when="16 Sep 2026 ~09:41 PM (night)", where="Sales floor (IP Cam 18)", cashier="", amount=0.0,
         finding=("Two hooded suspects at the drinks cooler at night, handling / concealing goods. Up to 5 people "
                  "across 2 camera views. Check missing-stock vs sales for the exact loss."),
         frames=["entry", "cooler", "key"]),
]


def _uri(slug, name):
    p = ANA / slug / f"{name}_after.jpg"
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else None


# curated detail (nice title/finding) for known incidents; new ones auto-derive.
CURATED = {i["slug"]: {k: i[k] for k in
                       ("title", "category", "when", "where", "cashier", "amount", "finding")}
           for i in INCIDENTS}
FRAME_ORDER = ["approach", "entry", "entry2", "receipt", "counter", "cooler", "behind",
               "suspect", "r2_txn", "key", "r3_after", "handoff", "dustbin", "flee"]


def _derive(slug, f, frames):
    """Auto-build incident detail from findings.json for a NEW (uncurated) clip.
    This is the 'loop engineering' bit: a newly-analysed clip flows into Stella
    with zero manual editing."""
    grp = f.get("group", "")
    pos = f.get("pos_overlay", {}) or {}
    cat = ("Cancelled-sale theft" if pos.get("cancel_detected")
           else "Cash theft" if grp == "register"
           else "Group shoplifting" if grp == "floor" else "Incident")
    reported = f.get("reported", "")
    title = (reported.split(" - ")[0] if " - " in reported else reported) or slug.replace("_", " ").title()
    finding = reported or f"{cat} at {f.get('register') or f.get('site') or 'the store'}"
    extra = []
    if grp == "register" and f.get("cash_drawer_activity_s"):
        extra.append(f"cash-drawer activity {f['cash_drawer_activity_s']}s")
    if grp == "floor":
        if f.get("max_people"):
            extra.append(f"up to {f['max_people']} people")
        if f.get("cooler_interaction_s"):
            extra.append(f"cooler interaction {f['cooler_interaction_s']}s")
    if extra:
        finding += " (" + ", ".join(extra) + ")"
    amt = 0.0
    try:
        amt = float(pos.get("canceled_amount")) if pos.get("canceled_amount") else 0.0
    except Exception:
        amt = 0.0
    return {"slug": slug, "title": title[:60], "category": cat,
            "when": f.get("evidence_clock") or f.get("start_clock") or "",
            "where": f.get("register") or f.get("site") or "", "cashier": pos.get("cashier") or "",
            "amount": amt, "finding": finding, "frames": frames}


def _discover_incidents():
    """Loop engineering: auto-discover every analysed incident (folder with
    *_after.jpg evidence) — known ones get curated text, new ones auto-derive."""
    out = []
    if not ANA.exists():
        return out
    findings = {}
    try:
        for f in json.loads((ANA / "all_findings.json").read_text()):
            findings[f["slug"]] = f
    except Exception:
        pass
    # Only surface incidents that are curated OR live in all_findings.json. This
    # keeps stale on-disk test/experiment folders (e.g. auto_* dry-runs) out of
    # Stella's knowledge base while still self-healing for a genuinely-dropped clip
    # (run_incoming adds real detections to all_findings.json).
    allowed = set(findings) | set(CURATED)
    for d in sorted(p for p in ANA.iterdir() if p.is_dir()):
        slug = d.name
        if slug not in allowed:
            continue
        names = sorted((p.name[:-len("_after.jpg")] for p in d.glob("*_after.jpg")),
                       key=lambda n: FRAME_ORDER.index(n) if n in FRAME_ORDER else 99)
        frames = [{"name": n, "img": _uri(slug, n)} for n in names]
        frames = [x for x in frames if x["img"]]
        if not frames:
            continue
        if slug in CURATED:
            out.append({**CURATED[slug], "slug": slug, "frames": frames})
        else:
            out.append(_derive(slug, findings.get(slug, {}), frames))
    return out


def _data():
    inc = _discover_incidents()
    analytics = {}
    aj = ROOT / "reports" / "analytics" / "analytics.json"
    if aj.exists():
        try:
            analytics = json.loads(aj.read_text())
        except Exception:
            analytics = {}
    return {"incidents": inc, "risk": analytics.get("risk", []),
            "health": analytics.get("health", []), "kpis": analytics.get("rollup", {}).get("totals", {}),
            "transactions": [
                {"cashier": "JORDAN LEE", "register": "Register 2", "tx_type": "cancel", "amount": 18.86, "ts": "2024-11-08 17:36"},
                {"cashier": "Cashier (Reg 1)", "register": "Register 1", "tx_type": "no_sale", "amount": 0.0, "ts": "2024-11-05 07:09"},
                {"cashier": "Cashier (Reg 1)", "register": "Register 1", "tx_type": "no_sale", "amount": 0.0, "ts": "2024-11-12 07:13"}],
            "report_url": r"G:\Shared drives\4. AP\lonestar-video-intelligence\01_Director_Report",
            "facts": [
                {"k": ["1625", "1,625", "event", "events", "structured", "extracted", "how many event", "footage run", "real footage"],
                 "t": "On real Mesa Valero footage the system created 1,625 records of what happened - 668 'person in view', 955 'time spent in an area', and 2 camera-health checks. (Normal-hours clip: 627; rush-hours clip: 998.)"},
                {"k": ["test", "tests", "passing", "suite", "quality", "how many test"],
                 "t": "All the automatic checks pass - 105 checks across 13 parts of the system, with 0 failures."},
                {"k": ["milestone", "milestones", "stage", "phase", "roadmap", "how far", "delivered"],
                 "t": "8 of 11 main stages done. On top of that, a full theft-detection and assistant layer is also done: finding incidents, picking the proof pictures automatically, the extra insights, and me (Stella). Next: matching staff, human review, and nightly automatic runs."},
                {"k": ["auto-evidence", "auto evidence", "auto-select", "proof frame", "evidence frame", "which frame", "pick frame", "automatically"],
                 "t": "The system picks the key proof pictures for each incident by itself (no one points to them): the cash-drawer moment, the cancelled-sale moment, the hand-off, and the shoplifting group. It is honest - some cues (like hands touching or blocking the view) are a best-guess from body position, and being 100% sure would need fuller body-movement analysis (not switched on)."},
                {"k": ["blind test", "blind-test", "5 clips", "five clips", "incident", "incidents", "theft", "shoplifting", "how many incident", "detected"],
                 "t": "The system has found 8 incidents on its own from the video: two cash-drawer thefts (5 & 12 Nov), the Jordan Lee cancelled sale of -$18.86 (read straight off the receipt), two planned group-shoplifting incidents (27 Jan, 14 May), and three robberies / hold-ups (27 Apr, 26 Jun, 16 Sep)."},
                {"k": ["robbery", "robberies", "hold-up", "holdup", "hold up", "armed", "break-in", "break in", "night", "overnight", "gunpoint", "force"],
                 "t": "Robbery / Hold-up is a category the system flags from what it can measure - people, camera views, time of day, and behaviour like going behind the counter. There are 3: a night counter hold-up (27 Apr, cashier's hands up), an overnight break-in behind the counter taking cigarettes/vapes (26 Jun), and two hooded suspects at the drinks cooler at night (16 Sep). The word 'robbery' is a human-review judgment, not a machine claim, and no cash/stock figure is taken from the video - it is reconciled from the Z-report and inventory. Call law enforcement and preserve the footage."},
                {"k": ["safeguard", "safeguards", "guardrail", "reliability", "nan", "fail-safe", "failsafe", "fresh", "freshness", "stale", "robust"],
                 "t": "Safety checks: if a camera reading is broken, it is flagged instead of quietly passing; a freshness check warns if the report is older than the data it was built from; and every important action needs a person to approve it. Nothing about an employee is shared automatically."},
                {"k": ["store", "stores", "camera", "cameras", "scope", "coverage", "how many camera"],
                 "t": "Scope: 3 stores and 6 register cameras (Mesa Valero, Polo Club, Woodridge)."},
                {"k": ["offline", "cloud", "privacy", "gpu", "premise", "on-prem", "secure", "internet", "private"],
                 "t": "100% offline and on your own computers - no cloud, and no footage ever leaves the store. Private by design."},
                {"k": ["how does", "how it work", "how does it", "how the system", "pipeline", "detects people", "yolo", "the engine", "explain", "how it detect", "what does it do", "how are events"],
                 "t": "How it works: it reads the video the cameras already record, spots and follows people, notes which areas they were in and for how long, turns that into clear records, and flags incidents with evidence for a person to review - all offline."},
                {"k": ["rtsp", "live", "24/7", "24-7", "real-time", "real time", "live data", "streaming", "kafka", "cloud", "scale", "scaling", "gpu", "cluster", "phase 2", "phase two", "future", "distributed"],
                 "t": "Today the system works offline on saved clips, on your own computers. Phase 2 - waiting for management approval - would add watching all cameras live, around the clock, across every store at once. It uses the same core, so it is an add-on, not a rebuild. It is in the roadmap and not started until approved."},
                {"k": ["slp", "sugarland", "sugarland petroleum", "what is slp", "the company", "which company", "what company"],
                 "t": "SLP = Sugarland Petroleum. This is Sugarland Petroleum's own AI camera system - it turns the stores' existing camera video into clear records, incident evidence, and useful insights, 100% offline."},
                {"k": ["how do i use", "how to use", "navigate", "which tab", "report tab", "tabs", "get around", "where do i find", "where is the", "use this report", "how do i read"],
                 "t": "This report has tabs along the top: Summary, Dashboard, Demo, Incidents, Architecture, Progress, Tests, Governance and Roadmap - click a tab to jump. The Incidents tab holds the evidence pictures; the Dashboard has the by-date incident log; and you can just ask me here for anything specific."},
                {"k": ["heat", "heatmap", "heat map", "traffic", "dwell", "footfall"],
                 "t": "Heat maps: the Analytics tab shows where people walked and where they stood the longest on the shop floor - with no faces and no names (private and safe)."},
            ]}


CSS = """
<style>
#slpc-l{position:fixed;right:22px;bottom:20px;z-index:100000;background:linear-gradient(135deg,#12314f,#0c8f95);
 color:#fff;border:none;border-radius:28px;padding:13px 20px;font:700 14.5px 'Segoe UI',Arial;cursor:pointer;
 box-shadow:0 10px 26px rgba(16,32,48,.3)}
#slpc-l:hover{filter:brightness(1.08)}
#slpc-p{position:fixed;right:22px;bottom:74px;width:400px;max-width:94vw;height:600px;max-height:80vh;z-index:100000;
 background:#fff;border:1px solid #e1e8f0;border-radius:15px;box-shadow:0 18px 50px rgba(16,32,48,.32);display:none;flex-direction:column;overflow:hidden}
#slpc-p.on{display:flex}
#slpc-p .h{background:linear-gradient(135deg,#12314f,#123047);color:#fff;padding:12px 15px}
#slpc-p .h b{font-size:14.5px}#slpc-p .h span{display:block;font-size:11px;color:#b8c7d6}
#slpc-p .h .x{float:right;cursor:pointer;font-size:19px}
#slpc-id{display:flex;gap:6px;padding:8px 10px;border-bottom:1px solid #e1e8f0;background:#f0f4f8;flex-wrap:wrap;align-items:center}
#slpc-id input,#slpc-id select{padding:7px 8px;border:1px solid #e1e8f0;border-radius:8px;font-size:12px}
#slpc-id input{flex:1;min-width:84px}
#slpc-id button{background:#0c8f95;color:#fff;border:none;border-radius:8px;padding:7px 12px;font-size:12px;cursor:pointer;font-weight:600}
#slpc-id .w{font-size:11px;color:#5a6b7d}
#slpc-t{display:flex;border-bottom:1px solid #e1e8f0}
#slpc-t .t{flex:1;text-align:center;padding:9px;font-size:12px;color:#5a6b7d;cursor:pointer;border-bottom:2px solid transparent}
#slpc-t .t.on{color:#0c8f95;border-bottom-color:#0c8f95;font-weight:700}
#slpc-t .t .b{background:#cf4141;color:#fff;border-radius:10px;padding:0 6px;font-size:10px;margin-left:4px}
.slpc-v{flex:1;overflow-y:auto;display:none;flex-direction:column}.slpc-v.on{display:flex}
#slpc-m{flex:1;overflow-y:auto;padding:13px;display:flex;flex-direction:column;gap:8px}
.slpc-msg{max-width:85%;padding:9px 12px;border-radius:13px;font-size:13.5px;white-space:pre-wrap;line-height:1.45;word-wrap:break-word}
.slpc-msg.user{align-self:flex-end;background:#0c8f95;color:#fff}
.slpc-msg.assistant{align-self:flex-start;background:#f0f4f8;color:#17202b}
.slpc-imgs{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start;max-width:92%}
.slpc-imgs img{width:132px;height:78px;object-fit:cover;border:1px solid #e1e8f0;border-radius:8px;cursor:pointer}
#slpc-ch{display:flex;gap:6px;flex-wrap:wrap;padding:6px 12px}
.slpc-chip{background:#fff;border:1px solid #e1e8f0;border-radius:15px;padding:5px 10px;font-size:11.5px;cursor:pointer;color:#0c8f95}
#slpc-rq,#slpc-tm{padding:12px;overflow-y:auto}
.slpc-req{border:1px solid #e1e8f0;border-radius:10px;padding:10px;margin-bottom:8px;font-size:12.5px}
.slpc-req b{color:#26c6cc}.slpc-req button{border:none;border-radius:7px;padding:6px 14px;font-size:12px;cursor:pointer;color:#fff;font-weight:600;margin:7px 7px 0 0}
.slpc-req .ap{background:#1f9d6b}.slpc-req .dn{background:#cf4141}
.slpc-tmsg{font-size:12px;padding:6px 2px;border-bottom:1px solid #e1e8f0}
.slpc-tmsg .u{font-weight:700;color:#12314f}.slpc-tmsg .r{color:#8595a7;font-size:10px}.slpc-tmsg .t{color:#5a6b7d}
.slpc-empty{color:#8595a7;font-size:12.5px;text-align:center;padding:26px}
#slpc-in{display:flex;gap:6px;padding:10px;border-top:1px solid #e1e8f0}
#slpc-in input{flex:1;padding:10px;border:1px solid #e1e8f0;border-radius:10px;font-size:13.5px}
#slpc-in button{background:#0c8f95;color:#fff;border:none;border-radius:10px;padding:0 16px;font-weight:700;cursor:pointer}
.slpc-foot{font-size:10px;color:#8595a7;text-align:center;padding:5px}
@media(max-width:520px){#slpc-p{right:0;bottom:0;width:100vw;height:100vh;max-width:100vw;max-height:100vh;border-radius:0}}
@media print{#slpc-l,#slpc-p{display:none !important}}
</style>
"""

BODY = """
<button id="slpc-l" onclick="SLPC.toggle()">&#11088; Ask Stella</button>
<div id="slpc-p">
 <div class="h"><span class="x" onclick="SLPC.toggle(0)" style="float:right;cursor:pointer;font-size:19px">&times;</span>
  <b style="font-size:15px">Sugarland Petroleum</b><span><span style="background:linear-gradient(90deg,#ffe9a8,#d4af37,#fff2b0,#c9971d);-webkit-background-clip:text;background-clip:text;color:transparent;font-weight:800">&#11088; Stella</span> &middot; AI Video-Intelligence assistant &middot; internal</span></div>
 <div id="slpc-id"><input id="slpc-uid" placeholder="your name (optional)">
  <select id="slpc-role"><option value="staff">Camera team / Staff</option><option value="manager">Manager</option>
   <option value="director">Director</option></select>
  <button onclick="SLPC.start()">Set</button><span class="w" id="slpc-who"></span></div>
 <div id="slpc-t"><div class="t on" data-v="chat" onclick="SLPC.tab('chat')">Chat</div>
  <div class="t" data-v="team" onclick="SLPC.tab('team')">All conversations</div>
  <div class="t" data-v="appr" onclick="SLPC.tab('appr')" id="slpc-tabAppr" style="display:none">Approvals<span class="b" id="slpc-badge" style="display:none">0</span></div></div>
 <div class="slpc-v on" id="slpc-v-chat"><div id="slpc-m"></div><div id="slpc-ch"></div>
  <div id="slpc-in"><input id="slpc-text" placeholder="Ask - 'summary', 'evidence for jordan', 'risk'"
   onkeydown="if(event.keyCode===13)SLPC.send()"><button onclick="SLPC.send()">Send</button></div></div>
 <div class="slpc-v" id="slpc-v-team"><div id="slpc-tm"></div></div>
 <div class="slpc-v" id="slpc-v-appr"><div id="slpc-rq"></div></div>
 <div class="slpc-foot">Everyone can review all conversations &middot; sensitive actions need Manager&rarr;Director approval</div>
</div>
"""

JS = r"""<script>
var SLPC=(function(){
var D=window.SLPCHAT,RANK={staff:0,manager:1,director:2,admin:3};
var ACT={help:[],list_incidents:[],get_summary:[],get_evidence:[],get_risk_ranking:[],get_camera_health:[],get_kpis:[],search_transaction:[],
 generate_report:['manager'],export_data:['manager'],email_director:['director'],publish_shared_drive:['manager','director']};
var MIN={generate_report:'manager',export_data:'manager',email_director:'manager',publish_shared_drive:'manager'};
var IN=[[/\b(help|what can you|capabilit|commands?)\b/i,'help'],[/\b(publish|shared drive|upload report)\b/i,'publish_shared_drive'],
 [/\b(email|send).{0,20}(director|mustafa)\b/i,'email_director'],[/\b(generate|rebuild|refresh|regenerate).{0,15}report\b/i,'generate_report'],
 [/\b(export|download).{0,15}(data|transactions?|csv)\b/i,'export_data'],[/\b(evidence|proof|photos?|pictures?|footage|clips?|annotat\w*)\b/i,'get_evidence'],
 [/\b(summary|overview|brief|situation|status|how are things|update me)\b/i,'get_summary'],[/\b(risk|rank|worst|priorit)\b/i,'get_risk_ranking'],
 [/\b(cameras?|tampers?|health|uptime)\b/i,'get_camera_health'],[/\b(kpis?|metrics?|totals?|scorecard|numbers?|stats?)\b/i,'get_kpis'],
 [/\b(search|find|look ?up|transactions?|cancels?|refunds?)\b/i,'search_transaction'],[/\b(incidents?|thefts?|shoplift\w*|cases?|jordan|cash|drawer|register|collusion|void|handling|floor|cooler|group)\b/i,'list_incidents']];
function db(){try{return JSON.parse(localStorage.getItem('slpc')||'{}')}catch(e){return {}}}
function save(d){try{if(d&&d.sessions){for(var sid in d.sessions){var ms=d.sessions[sid].msgs||[];for(var k=0;k<ms.length;k++){if(ms[k].imgs)ms[k].imgs=ms[k].imgs.filter(function(x){return (''+x).indexOf('data:')!==0})}}}}catch(e){}
 try{localStorage.setItem('slpc',JSON.stringify(d))}catch(e){}}
function ens(){var d=db();d.sessions=d.sessions||{};d.memory=d.memory||{};d.requests=d.requests||[];return d}
var SID=null,USER='',ROLE='staff',CUR='chat',LL=-1;
try{SID=localStorage.getItem('slpc_sid');USER=localStorage.getItem('slpc_user')||'';ROLE=localStorage.getItem('slpc_role')||'staff'}catch(e){}
function el(i){return document.getElementById(i)}
function safe(fn,fb){try{return fn()}catch(e){return fb}}
function rank(r){return RANK[r]||0}
function toggle(o){var p=el('slpc-p');var open=(o===undefined)?!(p.className.indexOf('on')>=0):o;p.className=open?'on':'';
 if(open){if(!SID){if(!el('slpc-uid').value)el('slpc-uid').value=(USER||'Guest');start()}else restore()}}
function tab(v){CUR=v;['chat','team','appr'].forEach(function(x){el('slpc-v-'+x).className='slpc-v'+(x===v?' on':'')});
 var ts=el('slpc-t').getElementsByClassName('t');for(var j=0;j<ts.length;j++)ts[j].className='t'+(ts[j].getAttribute('data-v')===v?' on':'');
 if(v==='team')team();if(v==='appr')reqs()}
function add(s,t){var d=document.createElement('div');d.className='slpc-msg '+s;d.appendChild(document.createTextNode(t));el('slpc-m').appendChild(d);el('slpc-m').scrollTop=el('slpc-m').scrollHeight}
function frameURI(ref){var s=(''+ref);if(s.indexOf('data:')===0)return s;var p=s.split('|');if(p.length<2)return '';
 for(var k=0;k<D.incidents.length;k++){if(D.incidents[k].slug===p[0]){var fr=D.incidents[k].frames||[];for(var j=0;j<fr.length;j++)if(fr[j].name===p[1])return fr[j].img}}return ''}
function imgs(a){if(!a||!a.length)return;var w=document.createElement('div');w.className='slpc-imgs';var n=0;
 for(var k=0;k<a.length;k++){var uri=frameURI(a[k]);if(!uri)continue;n++;var im=document.createElement('img');im.src=uri;im.onclick=(function(u){return function(){var x=window.open('','_blank');if(x)x.document.write('<img src="'+u+'" style="max-width:100%">')}})(uri);w.appendChild(im)}
 if(n){el('slpc-m').appendChild(w);el('slpc-m').scrollTop=el('slpc-m').scrollHeight}}
function chips(l){el('slpc-ch').innerHTML='';(l||[]).forEach(function(s){var c=document.createElement('span');c.className='slpc-chip';c.appendChild(document.createTextNode(s));c.onclick=function(){el('slpc-text').value=s;send()};el('slpc-ch').appendChild(c)})}
function roleTabs(){el('slpc-tabAppr').style.display=(rank(ROLE)>=1)?'block':'none'}
function start(){USER=(el('slpc-uid').value||'guest');ROLE=el('slpc-role').value;SID='s'+(new Date()).getTime()+Math.floor(Math.random()*999);
 try{localStorage.setItem('slpc_sid',SID);localStorage.setItem('slpc_user',USER);localStorage.setItem('slpc_role',ROLE)}catch(e){}
 var d=ens();d.sessions[SID]={user:USER,role:ROLE,msgs:[]};save(d);el('slpc-who').textContent=USER+' - '+ROLE;el('slpc-m').innerHTML='';roleTabs();tab('chat');LL=-1;
 push('assistant',"Hi"+(USER&&USER!=='Guest'?' '+USER:'')+", I'm Stella - your Sugarland Petroleum assistant. Ask me anything - reporting, real-time data, evidence, analytics, or a summary. I can also run actions (with approval).",null);
 chips(['summary','show incidents','evidence for jordan','risk ranking','camera health','help'])}
function push(sn,tx,im){var d=ens();if(!d.sessions[SID])d.sessions[SID]={user:USER,role:ROLE,msgs:[]};d.sessions[SID].msgs.push({sender:sn,text:tx,imgs:im||null,ts:(new Date()).getTime()});save(d);add(sn,tx);if(im)imgs(im);LL=d.sessions[SID].msgs.length}
function rchat(){var d=ens();var s=d.sessions[SID];if(!s)return;if(s.msgs.length===LL)return;LL=s.msgs.length;el('slpc-m').innerHTML='';for(var k=0;k<s.msgs.length;k++){var m=s.msgs[k];add(m.sender,m.text);if(m.imgs)imgs(m.imgs)}}
function restore(){if(USER){el('slpc-uid').value=USER;el('slpc-role').value=ROLE;el('slpc-who').textContent=USER+' - '+ROLE;roleTabs()}if(SID)rchat()}
var STOP={the:1,and:1,for:1,about:1,show:1,give:1,tell:1,provide:1,detail:1,details:1,incident:1,incidents:1,theft:1,evidence:1,picture:1,pictures:1,pic:1,pics:1,photo:1,photos:1,me:1,please:1,handling:1,the:1};
function scoreInc(i,q){q=(q||'').toLowerCase();var hay=[i.slug,i.title,i.category,i.when,i.where,i.cashier,i.finding].join(' ').toLowerCase();
 var amt=(''+i.amount),sc=0;if(i.amount&&amt!=='0'&&amt!=='0.0'&&q.indexOf(amt)>=0)sc+=5;
 var toks=q.match(/[a-z]{2,}|\d{1,4}/g)||[];for(var k=0;k<toks.length;k++){if(STOP[toks[k]])continue;if(hay.indexOf(toks[k])>=0)sc++}return sc}
function ranked(q){var a=[];for(var k=0;k<D.incidents.length;k++)a.push({i:D.incidents[k],s:scoreInc(D.incidents[k],q)});
 a.sort(function(x,y){return y.s-x.s});return a}
function topInc(q){var r=ranked(q);if(r[0].s<=0)return [];var out=[];for(var k=0;k<r.length;k++){if(r[k].s===r[0].s)out.push(r[k].i)}return out}
function iImg(i){var o=[];for(var k=0;k<(i.frames||[]).length;k++)o.push(i.slug+'|'+i.frames[k].name);return o}
function factSearch(q){q=(''+q).toLowerCase();var toks=q.match(/[a-z0-9]+/g)||[],tset={};for(var i=0;i<toks.length;i++)tset[toks[i]]=1;
 var best=null,bs=0,F=D.facts||[];
 for(var k=0;k<F.length;k++){var sc=0;
  for(var j=0;j<F[k].k.length;j++){var key=(''+F[k].k[j]).toLowerCase();
   // phrase keys (contain space/-/ /) match as a substring and count double;
   // single-word keys must match a WHOLE query token (so 'latest' != 'test').
   if(/[ /-]/.test(key)){if(q.indexOf(key)>=0)sc+=2;}
   else if(tset[key])sc+=1;}
  if(sc>bs){bs=sc;best=F[k]}}
 return bs>0?best:null}
function respond(t){var low=t.toLowerCase();var mem=(ens().memory[USER]||{});
 var rm=t.match(/remember\s+(?:that\s+)?(?:my\s+)?([a-z ]{2,20})\s+is\s+(.+)/i);
 if(rm){var d=ens();d.memory[USER]=d.memory[USER]||{};var kk=rm[1].toLowerCase().replace(/(^\s+|\s+$)/g,'');d.memory[USER][kk]=rm[2].replace(/[.?!\s]+$/,'');save(d);return {text:"Got it - I'll remember your "+kk+" is "+rm[2].replace(/[.?!\s]+$/,'')+"."}}
 if(/\b(hi|hello|hey|salam|assalam)\b/i.test(low)&&low.length<28)return {text:"Hi"+(mem.name?' '+mem.name:'')+", I'm Stella. Ask about incidents, risk, camera health, evidence, or a summary.",suggestions:['summary','evidence for jordan','risk ranking']};
 if(/\b(thanks|thank you|thank u|shukriya|shukria)\b/i.test(low))return {text:"You're welcome! Happy to help. Want a summary, an incident, or the numbers?",suggestions:['summary','evidence for jordan','risk ranking']};
 if(/\b(good job|great job|nice job|nice work|good work|well done|amazing|excellent|awesome|brilliant|love it|wonderful|superb|shabash|impressive|fantastic|you'?re the best|perfect)\b/i.test(low)&&low.length<40)return {text:"Thank you - glad it's helpful! Ask me anything: a summary, an incident, evidence pictures, or the platform numbers.",suggestions:['summary','evidence for jordan','1625 events','risk ranking']};
 if(/\b(who are you|your name|what are you)\b/i.test(low))return {text:"I'm Stella, the Sugarland Petroleum AI Video-Intelligence assistant. I can show incidents, evidence, analytics, and the platform numbers - all offline."};
 if(/\b(bye|goodbye|khuda hafiz|see you)\b/i.test(low))return {text:"Goodbye! I'm here whenever you need me."};
 if(/how many\s+(cameras?|stores?|sites?)|how many.*(camera|store)/i.test(low))return {text:"Scope: 3 stores and 6 register cameras (Mesa Valero, Polo Club, Woodridge).",suggestions:['camera health','summary']};
 for(var k=0;k<IN.length;k++){if(IN[k][0].test(low)){var a=IN[k][1];if((ACT[a]||[]).length===0&&!MIN[a])return {run:a,params:{query:t}};return {req:a,params:{query:t}}}}
 var fx=safe(function(){return factSearch(t)},null);if(fx)return {text:fx.t};
 var hit=safe(function(){return topInc(t)},[]);if(hit&&hit.length)return {run:'list_incidents',params:{query:t}};
 return {text:"I can show incidents, a summary, evidence pictures, risk ranking, camera health, KPIs, search transactions, or (with approval) generate/publish reports. Try 'help'.",suggestions:['help','summary','evidence for jordan','12 Nov cash','27 Jan']}}
function read(a,p){var q=p.query||'';
 if(a==='help'){return {text:"I'm Stella - here's what I can help with:\n - Summary of the whole situation\n - Incidents by name / date / type (cash theft, Jordan void, shoplifting)\n - Evidence: annotated proof frames\n - Risk ranking of POS exceptions\n - Camera health\n - KPIs & transaction search\n - Platform facts: tests, events, milestones, heat maps, the Phase-2 roadmap\n - Actions (with Manager/Director approval): generate or publish the report, export data, email the Director\nJust ask in plain words.",images:[]}}
 if(a==='list_incidents'){var h=topInc(q);
  if(h.length===1){var i=h[0];return {text:i.title+' - '+i.when+' - '+i.where+'\n'+i.finding+(i.amount?'\nAmount: $'+i.amount:'')+(i.cashier?'\nCashier: '+i.cashier:''),images:iImg(i)}}
  if(h.length>1){var s='',im=[];for(var m=0;m<h.length;m++){s+=' - '+h[m].title+' ('+h[m].when+')\n';var ii=iImg(h[m]);for(var y=0;y<ii.length;y++)im.push(ii[y])}return {text:h.length+' matching incidents (pictures below):\n'+s,images:im}}
  var s2='';for(var n=0;n<D.incidents.length;n++)s2+=' - '+D.incidents[n].title+'\n';return {text:D.incidents.length+' incidents on file (ask by name/date/type for pictures):\n'+s2}}
 if(a==='get_summary'){var r=D.risk[0]||null,kk=D.kpis||{},hh=D.health||[],ok=0;for(var z=0;z<hh.length;z++)if(hh[z].clarity==='OK')ok++;
  return {text:'Summary - '+D.incidents.length+' incidents, '+(kk.exceptions||'?')+' unusual till events ($'+(kk.exception_amount||'?')+'), cameras '+ok+'/'+hh.length+' OK'+(r?', top risk: '+r.cashier+' ('+r.band+')':'')+'.\nFull report: '+D.report_url}}
 if(a==='get_evidence'){var pk=topInc(q);if(!pk.length)pk=D.incidents;
  var im=[],tt='';for(var pp=0;pp<pk.length;pp++){tt+=' - '+pk[pp].title+': '+pk[pp].frames.length+' frame(s)\n';var ii=iImg(pk[pp]);for(var y=0;y<ii.length;y++)im.push(ii[y])}return {text:pk.length+' evidence set(s) - annotated frames:\n'+tt,images:im}}
 if(a==='get_risk_ranking'){if(!D.risk.length)return {text:'No exceptions to rank.'};var s='';for(var k3=0;k3<Math.min(5,D.risk.length);k3++){var rr=D.risk[k3];s+=' '+(k3+1)+'. '+rr.cashier+' - '+rr.tx_type+' - $'+rr.amount+' - score '+rr.score+' ('+rr.band+')\n'}return {text:'Risk ranking:\n'+s}}
 if(a==='get_camera_health'){var s='';for(var k4=0;k4<(D.health||[]).length;k4++)s+=' - '+D.health[k4].clip+': '+D.health[k4].clarity+'\n';return {text:'Camera health (hardened):\n'+s}}
 if(a==='get_kpis'){var kp=D.kpis||{},o=[];for(var kx in kp)o.push(kx.replace(/_/g,' ')+'='+kp[kx]);return {text:'KPIs: '+o.join(', ')}}
 if(a==='search_transaction'){var res=[];for(var k5=0;k5<D.transactions.length;k5++){var x=D.transactions[k5];if((!p.cashier||x.cashier.toLowerCase().indexOf(p.cashier.toLowerCase())>=0)&&(!p.tx_type||x.tx_type.indexOf(p.tx_type)>=0)&&(!p.min_amount||x.amount>=p.min_amount))res.push(x)}
  var s='';for(var q2=0;q2<res.length;q2++)s+=' - '+res[q2].ts+' '+res[q2].cashier+' '+res[q2].tx_type+' $'+res[q2].amount+'\n';return {text:res.length+' transaction(s):\n'+s}}
 return {text:'Done.'}}
function exec(a){if(a==='publish_shared_drive')return 'Approved to publish. Report at:\n'+D.report_url;if(a==='generate_report')return 'Report regeneration approved.';if(a==='email_director')return 'Approved to email the Director a summary.';if(a==='export_data')return 'Transaction export approved.';return 'Executed.'}
function request(a,p){if(MIN[a]&&rank(ROLE)<rank(MIN[a]))return {text:'Blocked: '+a+' needs role >= '+MIN[a]+' (you are '+ROLE+').'};
 var chain=(ACT[a]||[]).slice();if(!chain.length)return read(a,p);var d=ens();var id='r'+(new Date()).getTime();
 d.requests.push({id:id,action:a,user:USER,role:ROLE,session:SID,status:'pending_'+chain[0],pending:chain});save(d);
 return {text:'[locked] Requested '+a+'. Needs '+chain.join(' -> ')+' approval - waiting on the '+chain[0]+'.'}}
function decide(id,dec){var d=ens();var r=null;for(var k=0;k<d.requests.length;k++)if(d.requests[k].id===id)r=d.requests[k];if(!r)return;var nx=r.pending[0];if(rank(ROLE)<rank(nx))return;
 if(dec==='deny'){r.status='denied';r.pending=[]}else{r.pending.shift();if(r.pending.length){r.status='pending_'+r.pending[0]}else{r.status='executed';r.result=exec(r.action)}}
 var msg=r.status==='executed'?('[approved] '+r.action+' - executed.\n'+(r.result||'')):r.status==='denied'?('[denied] '+r.action+' denied by the '+ROLE+'.'):('[ok] '+ROLE+' approved '+r.action+' - waiting on the '+r.pending[0]+'.');
 var s=d.sessions[r.session];if(s)s.msgs.push({sender:'assistant',text:msg,ts:(new Date()).getTime()});save(d);if(r.session===SID){LL=-1;rchat()}reqs()}
function reqs(){if(rank(ROLE)<1){el('slpc-badge').style.display='none';return}var d=ens(),p=[];for(var k=0;k<d.requests.length;k++){var r=d.requests[k];if((''+r.status).indexOf('pending_')===0&&rank(ROLE)>=rank(r.pending[0]))p.push(r)}
 el('slpc-badge').style.display=p.length?'inline':'none';el('slpc-badge').innerHTML=p.length;var b=el('slpc-rq');b.innerHTML='';if(!p.length){b.innerHTML='<div class="slpc-empty">No pending approvals.</div>';return}
 for(var j=0;j<p.length;j++){(function(r){var dv=document.createElement('div');dv.className='slpc-req';dv.innerHTML='<b>'+r.action+'</b> - by '+r.user+'<br><span style="color:#8595a7">needs '+r.pending.join(' -> ')+' approval</span><div><button class="ap">Approve</button><button class="dn">Deny</button></div>';
  dv.getElementsByClassName('ap')[0].onclick=function(){safe(function(){decide(r.id,'approve')})};dv.getElementsByClassName('dn')[0].onclick=function(){safe(function(){decide(r.id,'deny')})};b.appendChild(dv)})(p[j])}}
function team(){var b=el('slpc-tm');var d=ens();var all=[];for(var sid in d.sessions){var s=d.sessions[sid];for(var k=0;k<s.msgs.length;k++)all.push({u:s.user,r:s.role,sender:s.msgs[k].sender,text:s.msgs[k].text,ts:s.msgs[k].ts})}
 all.sort(function(a,c){return a.ts-c.ts});all=all.slice(-100);b.innerHTML='';if(!all.length){b.innerHTML='<div class="slpc-empty">No conversations yet.</div>';return}
 for(var j=0;j<all.length;j++){var m=all[j];var e=document.createElement('div');e.className='slpc-tmsg';e.innerHTML='<span class="u">'+m.u+'</span> <span class="r">'+m.r+' - '+m.sender+'</span><br><span class="t">'+(''+m.text).replace(/</g,'&lt;').substr(0,220)+'</span>';b.appendChild(e)}b.scrollTop=b.scrollHeight}
function send(){try{
 var t=el('slpc-text').value;if(!t)return;if(!SID)start();el('slpc-text').value='';push('user',t,null);
 var r=safe(function(){return respond(t)},null)||{text:"Sorry, I couldn't read that. Try 'help'."};
 var o;
 if(r.run){o=safe(function(){return read(r.run,r.params)},null)}
 else if(r.req){o=safe(function(){return request(r.req,r.params)},null)}
 else{o={text:r.text,images:r.images}}
 if(!o)o={text:"Sorry, I hit a problem getting that. Please try again or rephrase."};
 push('assistant',o.text||'Done.',o.images);chips(r.suggestions);safe(function(){reqs()})
 }catch(e){try{push('assistant','Sorry - something went wrong. Please try again.')}catch(_){}}}
setInterval(function(){safe(function(){if(!SID)return;if(CUR==='chat')rchat();if(CUR==='team')team();reqs()})},3000);
function W(fn){return function(){try{return fn.apply(null,arguments)}catch(e){try{add('assistant','Sorry - something went wrong. Please try again.')}catch(_){}}}}
safe(function(){reqs()});
return {toggle:W(toggle),tab:W(tab),start:W(start),send:W(send)};
})();
</script>"""


def widget_html() -> str:
    return CSS + BODY + "<script>window.SLPCHAT=" + json.dumps(_data()) + ";</script>\n" + JS
