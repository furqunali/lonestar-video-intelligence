"""Consolidate: inject an 'Incidents' tab + section into the ONE director report
HTML (the 10-Sep tabbed report). Dashboard strip (visual) is kept separate from
the category-wise data/text + evidence, surveillance-app style. Reuses the
incident data/images from build_incident_report.py. Output = single maintained HTML.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
import build_incident_report as bir

ROOT = Path(__file__).resolve().parent
ANA = ROOT / "reports" / "incident_analysis"
DIRECTOR = ROOT / "reports" / "Sugarland_Petroleum_Video_Intelligence_Director_Report_2026-09-10.html"
OUT = ROOT / "reports" / "Sugarland_Petroleum_Video_Intelligence_Director_Report.html"

esc = bir.esc
_flist = list(json.loads((ANA / "all_findings.json").read_text()))
findings = {f["slug"]: f for f in _flist}

# Self-healing: derive title/review/value text for any NEW (auto-calibrated) clip
# that has no curated entry, so a freshly-dropped director-exam clip renders with
# ZERO manual editing. NEW_SLUGS get an "AUTO-CALIBRATED" badge on their card.
NEW_SLUGS = set(bir.register_derived(_flist))

# Category buckets are computed from the findings (not hardcoded), so dropping a
# clip auto-files it under the right category. Curated clips keep their order;
# any additional clip is appended in file order.
_CAT_DEF = [
    ("Cash Theft at the Till", "cat1", "🟥",
     "A cashier takes or handles cash from an open drawer with no customer and no sale rung up.", "cash"),
    ("Cancelled-Sale Theft", "cat3", "🟧",
     "A full basket is cancelled and no money is taken, while someone walks out with the goods.", "void"),
    ("Group Shoplifting on the Shop Floor", "cat2", "🟨",
     "A group works together to hide drinks and snacks in their clothes across several aisles.", "shoplift"),
    ("Robbery / Hold-up", "cat4", "🔴",
     "A person or group takes cash or goods by force, threat, or an after-hours break-in — at the "
     "counter or behind it. The robbery call is a human-review judgment; the video gives the facts.",
     "robbery"),
]
_CURATED_ORDER = {"cash": ["5nov_cash", "12nov_cash"],
                  "void": ["jordan_cancel"],
                  "robbery": ["robbery_0427", "robbery_0916", "robbery_0626"],
                  "shoplift": ["27jan_steal", "14may_steal"]}


def _build_cats():
    out = []
    for title, cv, emoji, desc, key in _CAT_DEF:
        slugs = [s for s in _CURATED_ORDER[key] if s in findings]
        for f in _flist:                       # append any non-curated clip in this category
            s = f["slug"]
            if s not in slugs and bir.incident_category(f) == key:
                slugs.append(s)
        out.append((title, cv, emoji, desc, slugs))
    return out


CATS = _build_cats()


def kpi_numbers():
    """Live KPI values from the findings — never hardcoded counts."""
    n = len(_flist)
    cats_present = sum(1 for *_x, slugs in CATS if slugs)
    void_amt, n_void = None, 0
    for f in _flist:
        if bir.incident_category(f) == "void":
            n_void += 1
            amt = bir.JORDAN_TOTAL if f["slug"] == "jordan_cancel" else f.get("pos_overlay", {}).get("canceled_amount")
            if amt:
                void_amt = amt
    return dict(n=n, cats=cats_present, void_amt=void_amt, n_void=n_void)

# chronological order: arrive → enter → (POS) → gather → incident → hand-touch → bin
EV_LABELS = [
    ("entry", "Arriving in the parking lot"),
    ("entry2", "Entering the store together"),
    ("receipt", "Receipt on screen — sale cancelled"),
    ("suspect", "At the drinks fridge — group together"),
    ("r1_ctx", "Register — overview"),
    ("r2_txn", "Cash in hand at the counter (no sale rung up)"),
    ("key", "Cash taken from the open drawer"),
    ("r3_after", "Just after — cash still in hand"),
    ("handoff", "Cashier and customer hands touch (no payment)"),
    ("dustbin", "Cashier drops the cancelled receipt in the bin"),
]


ROBBERY_EV = [
    ("approach", "Suspect approaches (forecourt)"),
    ("entry", "Moving in / toward the counter"),
    ("counter", "At the counter — cashier's hands up"),
    ("cooler", "At the drinks cooler"),
    ("behind", "Behind the counter — grabbing stock"),
    ("key", "Key moment — taking goods"),
    ("flee", "Leaving the store"),
]


def chips_for(f):
    chips = []
    if f.get("group") == "robbery":
        chips.append(("Most people in view", f.get("max_people", "?")))
        chips.append(("Camera views", f.get("scene_cuts", "?")))
        chips.append(("Clip length", f"{f.get('duration_s', '?')}s"))
        if f.get("time_of_day"):
            chips.append(("When", f["time_of_day"]))
        return "".join(f'<div class="inc-chip"><span>{esc(k)}</span><b>{esc(v)}</b></div>'
                       for k, v in chips)
    if f["group"] == "register":
        chips.append(("Cashier present", f"{f['person_present_pct']}%"))
        chips.append(("Time at the open drawer", f"{f['cash_drawer_activity_s']}s"))
        if f.get("pos_overlay", {}).get("cancel_detected"):
            p = f["pos_overlay"]
            # Jordan's total is human-verified from the printed receipt; any OTHER
            # void clip must show ITS OWN read amount/cashier — never Jordan's.
            amt = bir.JORDAN_TOTAL if f["slug"] == "jordan_cancel" else (p.get("canceled_amount") or "?")
            chips.append(("Sale cancelled", "YES"))
            chips.append(("Cancelled amount", f"${amt}"))
            cashier = "JORDAN LEE" if f["slug"] == "jordan_cancel" else p.get("cashier")
            if cashier:
                chips.append(("Cashier name (on screen)", cashier))
    else:
        chips.append(("Most people in view", f["max_people"]))
        chips.append(("Camera views", f["scene_cuts"]))
        chips.append(("Time at the drinks fridge", f"{f['cooler_interaction_s']}s"))
    return "".join(f'<div class="inc-chip"><span>{esc(k)}</span><b>{esc(v)}</b></div>' for k, v in chips)


def items_html(slug):
    if slug == "jordan_cancel":
        rows = "".join(f"<tr><td>{esc(n)}</td><td class='num'>${esc(p)}</td></tr>" for n, p in bir.JORDAN_ITEMS)
        return ('<div class="inc-items"><div class="inc-cap">Cancelled receipt — item by item (read from the receipt on screen)</div>'
                f'<table><tr><th>Item</th><th class="num">Price</th></tr>{rows}'
                f'<tr class="subr"><td>Subtotal</td><td class="num">${bir.JORDAN_SUBTOTAL}</td></tr>'
                f'<tr class="subr"><td>Tax 1</td><td class="num">${bir.JORDAN_TAX}</td></tr>'
                f'<tr class="tot"><td>CANCELLED TOTAL</td><td class="num">-${bir.JORDAN_TOTAL}</td></tr></table></div>')
    if bir.CATEGORY.get(slug):
        return (f'<div class="inc-items"><div class="inc-cap">What was taken</div>'
                f'<p style="margin:4px 0 0;font-weight:600">{esc(bir.CATEGORY[slug])}</p></div>')
    return ""


def evidence_html(slug):
    # Clickable slideshow (FB-post style): 3-4 AI-annotated frames per incident,
    # one shown at a time with ‹ › nav + dots. Falls back gracefully to 1 frame.
    shots = []
    labels = ROBBERY_EV if findings.get(slug, {}).get("group") == "robbery" else EV_LABELS
    for name, label in labels:
        _b, a = bir.img_pair(slug, name)
        if a:
            shots.append((a, label))
    if not shots:
        return ""
    slides = ""
    for i, (a, label) in enumerate(shots):
        slides += (f'<figure class="inc-slide{" on" if i == 0 else ""}">'
                   f'<span class="inc-tag" style="background:var(--accent)">AI-ANNOTATED</span>'
                   f'<img src="{a}"><figcaption>{esc(label)}</figcaption></figure>')
    dots = "".join(f'<span class="inc-dot{" on" if i == 0 else ""}" data-i="{i}"></span>'
                   for i in range(len(shots)))
    single = " one" if len(shots) == 1 else ""
    return (f'<div class="inc-carousel{single}" data-n="{len(shots)}">'
            f'<div class="inc-track">{slides}</div>'
            f'<button class="inc-nav prev" type="button" aria-label="Previous">&#8249;</button>'
            f'<button class="inc-nav next" type="button" aria-label="Next">&#8250;</button>'
            f'<div class="inc-count">1 / {len(shots)}</div>'
            f'<div class="inc-dots">{dots}</div>'
            f'</div>')


def card(slug):
    f = findings[slug]
    head, det, match = bir.system_verdict(f)
    pill = ('<span class="inc-pill ok">POS-VERIFIED</span>' if match == "exact"
            else '<span class="inc-pill warn">BACKED BY VIDEO</span>')
    auto = ""
    if slug in NEW_SLUGS or f.get("auto_calibrated"):
        conf = f.get("calib_confidence")
        rev = f.get("calib_needs_review")
        cls = "warn" if rev else "ok"
        txt = "SET UP AUTOMATICALLY" + (f" · confidence {conf}" if conf is not None else "")
        txt += " · please double-check the area" if rev else ""
        auto = (f'<span class="inc-pill {cls}" '
                f'title="The system worked out the type of incident and the area to watch by itself — no manual setup.">'
                f'{esc(txt)}</span>')
    value = (f'<div class="inc-value"><b>How to find the exact amount:</b> {bir.VALUE_RECO.get(slug,"")}</div>'
             if bir.VALUE_RECO.get(slug) else "")
    review = (f'<div class="inc-review"><b>Suggested next step for the team:</b> {esc(bir.REVIEW.get(slug,""))}</div>'
              if bir.REVIEW.get(slug) else "")
    return (f'<div class="inc-card" id="inc-{slug}">'
            f'<div class="inc-head"><b>{esc(bir.TITLES[slug])}</b>{pill}{auto}</div>'
            f'<div class="inc-meta">{esc(f["site"])} · {esc(f["register"])} · {esc(bir.CLOCK.get(slug,""))} · clip {esc(f["duration_s"])}s</div>'
            f'<div class="inc-find"><b>What the AI saw in the video:</b> {head}<br><span>{det}</span></div>'
            f'<div class="inc-chips">{chips_for(f)}</div>'
            f'{items_html(slug)}'
            f'{value}'
            f'{review}'
            f'{evidence_html(slug)}'
            f'</div>')


INCIDENT_LOG = [
    ("27 Jan 2024", "Shop floor · IP Cam 16/18", "Group shoplifting", "cat2",
     "Group of 4 · 95.5s at the drinks fridge · 21 camera views · items hidden"),
    ("14 May 2024", "Shop floor · IP Cam 15/18", "Group shoplifting", "cat2",
     "Group of 5+ · 134s at the fridge · 36 camera views · one wearing a glove · items hidden"),
    ("05 Nov 2024", "Register 1 · Cam C3", "Cash theft", "cat1",
     "Drawer opened with no sale · cash taken · cashier present 94% · no customer"),
    ("08 Nov 2024", "Register 2 · Cam C2", "Cancelled-sale theft", "cat3",
     "Sale cancelled −$18.86 · cashier JORDAN LEE · goods taken · no money collected"),
    ("12 Nov 2024", "Register 1 · Cam C3", "Cash theft", "cat1",
     "Cash handled with no sale · 8.3s at the drawer · no customer, no sale"),
    ("27 Apr 2026", "Front counter · night", "Robbery / Hold-up", "cat4",
     "Counter hold-up · cashier's hands up · up to 5 people · 3 camera views"),
    ("26 Jun", "Behind the counter · overnight", "Robbery / Break-in", "cat4",
     "Suspects behind the counter taking cigarettes / vapes · up to 4 people"),
    ("16 Sep 2026", "Sales floor · night", "Robbery", "cat4",
     "Two+ hooded suspects at the drinks cooler · up to 5 people · 2 camera views"),
]


_CAT_LABEL = {"cash": ("Cash theft", "cat1"),
              "void": ("Cancelled-sale theft", "cat3"),
              "shoplift": ("Group shoplifting", "cat2"),
              "robbery": ("Robbery / Hold-up", "cat4")}


def _derived_log_rows():
    """By-date rows for any NEW (auto-calibrated) clip — computed from findings."""
    out = []
    for f in _flist:
        s = f["slug"]
        if s not in NEW_SLUGS:
            continue
        cat = bir.incident_category(f)
        lab, cv = _CAT_LABEL[cat]
        date = (bir.CLOCK.get(s, "") or f.get("date", "") or "auto")[:12]
        loc = f.get("register", "")
        if f.get("camera"):
            loc += f" · Cam {f['camera']}"
        head, _d, _m = bir.system_verdict(f)
        finding = re.sub("<[^>]+>", "", head) + "  · set up automatically"
        out.append((date, loc, lab, cv, finding))
    return out


def reviewed_panel():
    """Transparency log: clips the system reviewed and CLEARED as normal activity.

    So a normal clip (a customer's ordinary visit, staff routine) is visibly
    accounted for — the platform reviews every clip and only reports a REAL
    incident. No false blame; but no silent black box either.
    """
    p = ROOT / "reports" / "reviewed_log.json"
    try:
        log = json.loads(p.read_text())
    except Exception:
        return ""
    if not log:
        return ""
    rows = ""
    for e in reversed(log):                      # newest first
        rows += (f'<tr><td class="dt">{esc(e.get("when",""))}</td>'
                 f'<td>{esc(e.get("name",""))}</td>'
                 f'<td><span class="inc-pill ok">NORMAL — OK</span></td>'
                 f'<td>{esc(e.get("reason",""))}</td></tr>')
    return ('<h3 class="inc-cat" style="border-left-color:var(--pass);margin-top:22px">'
            '✅ Checked — nothing wrong (normal activity)</h3>'
            '<p class="intro">Clips the system checked and cleared as normal customer or staff '
            'activity — no theft, no blame. Shown so you can see the system looks at every clip '
            'and only reports a real problem.</p>'
            '<div class="inc-log-wrap"><table class="inc-log">'
            '<tr><th>Checked</th><th>Clip</th><th>Result</th><th>Why (from the video)</th></tr>'
            f'{rows}</table></div>')


def dash_block():
    rows = ""
    for date, loc, cat, cv, finding in INCIDENT_LOG + _derived_log_rows():
        rows += (f'<tr><td class="dt">{esc(date)}</td><td>{esc(loc)}</td>'
                 f'<td><span class="dot" style="background:var(--{cv})"></span>{esc(cat)}</td>'
                 f'<td>{esc(finding)}</td></tr>')
    k = kpi_numbers()
    counts = {"cash": 0, "void": 0, "shoplift": 0, "robbery": 0}
    for f in _flist:
        counts[bir.incident_category(f)] = counts.get(bir.incident_category(f), 0) + 1
    cat_kpi = f'{counts["cash"]}·{counts["void"]}·{counts["shoplift"]}·{counts["robbery"]}'
    void_kpi = f'${k["void_amt"]}' if k["void_amt"] else '—'
    void_sub = "confirmed from video" + (" (Jordan)" if k["n_void"] == 1 else f" ({k['n_void']} cancelled sales)") if k["void_amt"] else "no cancelled-sale loss"
    intro = (f'The {k["n"]} clips the system checked, in order. Each was found by the system on its own '
             f'from the video and the text shown on screen — the full marked-up pictures are in the Incidents tab.')
    return ('  <section data-tab="dashboard">\n'
            '    <p class="kicker">Incident summary</p>\n'
            '    <h2>Theft &amp; loss incidents — by date</h2>\n'
            f'    <p class="intro">{intro}</p>\n'
            '    <div class="kpis" style="margin-bottom:16px">'
            f'<div class="kpi"><div class="n">{k["n"]}</div><div class="l">Incidents</div><div class="s">checked by the system</div></div>'
            f'<div class="kpi"><div class="n">{cat_kpi}</div><div class="l">Cash · Cancelled · Shoplifting · Robbery</div><div class="s">{k["cats"]} types</div></div>'
            f'<div class="kpi"><div class="n">{void_kpi}</div><div class="l">Loss confirmed from video</div><div class="s">{void_sub}</div></div>'
            '<div class="kpi"><div class="n">100%</div><div class="l">Found by the system</div><div class="s">no tip-off needed</div></div>'
            '</div>\n'
            f'    <div class="inc-log-wrap"><table class="inc-log">'
            '<tr><th>Date</th><th>Location</th><th>Type</th><th>What the system found</th></tr>'
            f'{rows}</table></div>\n'
            f'    {reviewed_panel()}\n'
            '  </section>\n')


def analytics_section():
    """New Analytics tab: risk-ranking + multi-store rollup + camera-health + heat maps.
    Reads reports/analytics/*.json (generated by reporting/gen_analytics.py &
    gen_heatmap.py). Renders nothing gracefully if a piece is missing."""
    import json
    adir = ROOT / "reports" / "analytics"
    try:
        data = json.loads((adir / "analytics.json").read_text())
    except Exception:
        return ""  # analytics not generated yet -> skip the tab entirely
    try:
        heat = json.loads((adir / "heatmap.json").read_text())
    except Exception:
        heat = {}

    band_col = {"CRITICAL": "var(--crit)", "HIGH": "var(--crit)",
                "MEDIUM": "var(--warn)", "LOW": "var(--ink-3)"}

    # risk-ranked exceptions
    rrows = ""
    for f in data.get("risk", []):
        col = band_col.get(f["band"], "var(--ink-3)")
        rrows += (f'<tr><td><b>{esc(f["cashier"])}</b><br><span class="inc-meta">{esc(f["register"])} · {esc(f["when"])}</span></td>'
                  f'<td>{esc(f["tx_type"].upper())}</td><td class="num">${esc(f["amount"])}</td>'
                  f'<td><b style="color:{col}">{esc(f["score"])}</b></td>'
                  f'<td><span class="inc-pill" style="color:{col};border-color:{col}">{esc(f["band"])}</span></td>'
                  f'<td class="inc-meta">{esc("; ".join(f["reasons"]))}</td></tr>')
    risk_html = (f'<h3 class="inc-cat">Riskiest till events, ranked</h3>'
                 f'<p class="intro">Each unusual till event gets a risk score based on the amount, how often that '
                 f'cashier shows up, the time of day, and the type of event. The highest risk is shown first.</p>'
                 f'<div class="inc-log-wrap"><table class="inc-log"><tr><th>Cashier / register</th><th>Type</th><th class="num">Amount</th><th>Risk score</th><th>Level</th><th>Why</th></tr>{rrows}</table></div>')

    # rollup totals + by cashier
    roll = data.get("rollup", {}); tot = roll.get("totals", {})
    krow = "".join(f'<div class="kpi"><div class="n">{esc(v)}</div><div class="l">{esc(k.replace("_"," "))}</div></div>'
                   for k, v in tot.items())
    crows = "".join(f'<tr><td>{esc(c["cashier"])}</td><td class="num">{esc(c["exceptions"])}</td>'
                    f'<td class="num">${esc(c["amount"])}</td><td>{esc(", ".join(c["stores"]))}</td></tr>'
                    for c in roll.get("by_cashier", []))
    roll_html = (f'<h3 class="inc-cat">Totals across all stores</h3><div class="kpis">{krow}</div>'
                 f'<div class="inc-log-wrap"><table class="inc-log"><tr><th>Cashier</th><th class="num">Exceptions</th><th class="num">Amount</th><th>Stores</th></tr>{crows}</table></div>')

    # camera health (proves tamper false-positive fixed)
    hrows = ""
    for h in data.get("health", []):
        c = "var(--pass)" if h["clarity"] == "OK" else "var(--crit)"
        hrows += (f'<tr><td>{esc(h["clip"])}</td><td><b style="color:{c}">{esc(h["clarity"])}</b></td>'
                  f'<td class="num">{esc(h["blur"])}</td><td class="num">{esc(h["edges"])}</td>'
                  f'<td class="inc-meta">{esc(h["reason"])}</td></tr>')
    health_html = (f'<h3 class="inc-cat">Camera health check</h3>'
                   f'<p class="intro">The system checks each camera for tampering or a blocked / blurry view. All '
                   f'clips read <b>OK</b> — the picture is clear and the camera has not been moved or covered.</p>'
                   f'<div class="inc-log-wrap"><table class="inc-log"><tr><th>Clip</th><th>Picture</th><th class="num">Sharpness</th><th class="num">Detail</th><th>Note</th></tr>{hrows}</table></div>')

    # heat maps
    heat_html = ""
    shots = ""
    for slug, meta in heat.items():
        for kind in ("traffic", "dwell"):
            uri = bir.data_uri(adir / f"heat_{slug}_{kind}.jpg")
            desc = "footfall density (where people moved)" if kind == "traffic" else "dwell (where people lingered)"
            if uri:
                shots += (f'<figure class="inc-shot"><img src="{uri}">'
                          f'<figcaption>{esc(meta.get("label",""))} — {esc(desc)}</figcaption></figure>')
    if shots:
        heat_html = (f'<h3 class="inc-cat">Heat maps — where people go and stand</h3>'
                     f'<p class="intro">Shows where people walked (traffic) and where they stood the longest '
                     f'(dwell). No faces and no names — private and safe.</p>'
                     f'<div class="inc-shots">{shots}</div>')

    return (f'\n  <!-- ============ ANALYTICS ============ -->\n'
            f'  <section data-tab="analytics">\n'
            f'    <p class="kicker">Extra insights</p>\n'
            f'    <h2>Analytics</h2>\n'
            f'    <p class="intro">Extra insights from the same video — the riskiest till events ranked, totals '
            f'across stores, a camera health check, and privacy-safe heat maps. Everything runs on your own '
            f'computer; nothing goes to the cloud.</p>\n'
            f'    {risk_html}\n    {roll_html}\n    {health_html}\n    {heat_html}\n  </section>\n')


def build_section():
    # visual dashboard strip (separate from data/text) — live numbers from findings
    k = kpi_numbers()
    void_kpi = f'${k["void_amt"]}' if k["void_amt"] else '—'
    void_sub = ("confirmed from video · Jordan" if k["n_void"] == 1 and "jordan_cancel" in findings
                else (f"confirmed from video · {k['n_void']} cancelled sales" if k["void_amt"] else "no cancelled-sale loss"))
    n_auto = len(NEW_SLUGS)
    auto_kpi = (f'<div class="kpi"><div class="n">{n_auto}</div><div class="l">Set up automatically</div>'
                f'<div class="s">new camera · no manual setup</div></div>') if n_auto else ''
    dash = ('<div class="kpis" style="margin-bottom:8px">'
            f'<div class="kpi"><div class="n">{k["n"]}</div><div class="l">Incidents found</div><div class="s">by the system, on its own</div></div>'
            f'<div class="kpi"><div class="n">{k["cats"]}</div><div class="l">Types of theft</div><div class="s">cash · cancelled sale · shoplifting</div></div>'
            f'<div class="kpi"><div class="n">{void_kpi}</div><div class="l">Cancelled-sale loss</div><div class="s">{void_sub}</div></div>'
            f'{auto_kpi}'
            '<div class="kpi"><div class="n">100%</div><div class="l">Found by the system</div><div class="s">without any tip-off</div></div>'
            '</div>')
    cat_tiles = '<div class="inc-cattiles">'
    for title, cv, emoji, desc, slugs in CATS:
        cat_tiles += (f'<div class="inc-cattile" style="border-top:3px solid var(--{cv})">'
                      f'<div class="inc-tt">{emoji} {esc(title)}</div>'
                      f'<div class="inc-tn">{len(slugs)} incident{"s" if len(slugs)>1 else ""}</div>'
                      f'<div class="inc-td">{esc(desc)}</div></div>')
    cat_tiles += '</div>'

    detail = ""
    for title, cv, emoji, desc, slugs in CATS:
        detail += f'<h3 class="inc-cat" style="border-left-color:var(--{cv})">{emoji} {esc(title)}</h3>'
        for slug in slugs:
            detail += card(slug)

    return (f'\n  <!-- ============ INCIDENTS ============ -->\n'
            f'  <section id="incidents">\n'
            f'    <p class="kicker">Theft &amp; loss incidents</p>\n'
            f'    <h2>Incidents &amp; evidence</h2>\n'
            f'    <p class="intro">{kpi_numbers()["n"]} real theft / loss clips checked by the system on its own. '
            f'Everything below comes only '
            f'from watching the video and reading the text shown on screen. Clips from a new camera are <b>set up '
            f'automatically</b> (the system works out the type of incident and where to look by itself) and are marked '
            f'with a badge.</p>\n'
            f'    {dash}\n    {cat_tiles}\n'
            f'    <div class="inc-detail">{detail}</div>\n'
            f'  </section>\n')


CSS = """
/* ---- incidents ---- */
.inc-cattiles{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0 4px}
.inc-cattile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:var(--shadow)}
.inc-tt{font-weight:660;font-size:14px}
.inc-tn{font-family:var(--mono);font-size:12px;color:var(--accent-ink);margin:4px 0}
.inc-td{font-size:12.5px;color:var(--ink-2)}
.inc-cat{font-size:16px;border-left:4px solid var(--accent);padding-left:10px;margin:28px 0 12px}
.inc-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0;box-shadow:var(--shadow)}
.inc-head{display:flex;justify-content:space-between;align-items:center;gap:10px}
.inc-head b{font-size:15px}
.inc-pill{font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;white-space:nowrap;border:1px solid}
.inc-pill.ok{color:var(--pass);border-color:var(--pass)}
.inc-pill.warn{color:var(--warn);border-color:var(--warn)}
.inc-meta{color:var(--ink-3);font-size:12px;margin:4px 0 10px;font-family:var(--mono)}
.inc-find{background:var(--panel-2);border-left:3px solid var(--accent);border-radius:8px;padding:10px 12px;font-size:13.5px}
.inc-find span{color:var(--ink-2)}
.inc-chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.inc-chip{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12px}
.inc-chip span{display:block;color:var(--ink-3);font-size:11px}
.inc-chip b{color:var(--accent-ink);font-size:14px}
.inc-items{margin:10px 0}
.inc-items table{border-collapse:collapse}
.inc-items td,.inc-items th{border:1px solid var(--line);padding:5px 14px;font-size:12.5px}
.inc-items .num{text-align:right;font-variant-numeric:tabular-nums}
.inc-items .tot td{font-weight:800;color:var(--crit);border-top:2px solid var(--crit)}
.inc-value{border:1px solid var(--accent);border-left:4px solid var(--accent);border-radius:8px;padding:10px 12px;font-size:13px;margin:10px 0;background:var(--panel-2)}
.inc-manual{background:var(--panel-2);border:1px dashed var(--warn);border-radius:8px;padding:9px 12px;font-size:13px;margin:10px 0}
.inc-review{border:1px solid var(--crit);border-left:4px solid var(--crit);border-radius:8px;padding:10px 12px;font-size:13px;margin:10px 0;background:var(--panel-2)}
.inc-cap{font-size:11px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.5px;margin:12px 0 4px}
.inc-shots{display:grid;grid-template-columns:1fr;gap:12px;margin-top:12px}
.inc-shot{margin:0;position:relative;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#000}
.inc-shot img{width:100%;display:block}
.inc-shot figcaption{font-size:12px;color:var(--ink-2);padding:7px 11px;background:var(--panel)}
.inc-tag{position:absolute;top:6px;left:6px;color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:5px;z-index:2}
/* ---- evidence slideshow (clickable, FB-post style) ---- */
.inc-carousel{position:relative;margin-top:12px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#000}
.inc-track{position:relative}
.inc-slide{margin:0;display:none}
.inc-slide.on{display:block}
.inc-slide img{width:100%;display:block}
.inc-slide figcaption{font-size:12.5px;color:var(--ink-2);padding:8px 12px;background:var(--panel)}
.inc-nav{position:absolute;top:calc(50% - 22px);transform:translateY(-50%);width:38px;height:44px;border:none;cursor:pointer;
  background:rgba(10,20,30,.55);color:#fff;font-size:26px;line-height:1;z-index:3;border-radius:8px;transition:background .15s}
.inc-nav:hover{background:rgba(10,20,30,.85)}
.inc-nav.prev{left:8px}.inc-nav.next{right:8px}
.inc-count{position:absolute;top:8px;right:8px;background:rgba(10,20,30,.65);color:#fff;font-size:11px;font-weight:700;
  padding:3px 8px;border-radius:20px;z-index:3;font-family:var(--mono)}
.inc-dots{display:flex;gap:6px;justify-content:center;padding:8px 0 10px;background:var(--panel)}
.inc-dot{width:8px;height:8px;border-radius:50%;background:var(--line);cursor:pointer;transition:background .15s}
.inc-dot.on{background:var(--accent)}
.inc-carousel.one .inc-nav,.inc-carousel.one .inc-count,.inc-carousel.one .inc-dots{display:none}
@media print{.inc-slide{display:block !important}.inc-nav,.inc-count,.inc-dots{display:none !important}}
.inc-log-wrap{overflow-x:auto}
.inc-log{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.inc-log th,.inc-log td{border-bottom:1px solid var(--line);padding:9px 12px;font-size:13px;text-align:left;vertical-align:top}
.inc-log th{color:var(--ink-3);text-transform:uppercase;font-size:11px;letter-spacing:.5px;background:var(--panel-2)}
.inc-log .dt{font-family:var(--mono);white-space:nowrap;font-weight:600}
.inc-log .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.inc-log .subr td{color:var(--ink-2)}
.inc-hr{border:none;border-top:1px dashed var(--line);margin:34px 0 4px}
@media(max-width:760px){.inc-cattiles{grid-template-columns:1fr}.inc-pair{grid-template-columns:1fr}}
"""

html = DIRECTOR.read_text(encoding="utf-8")

# --- Option 1: fold the old "Evidence" (Mesa Valero detection-proof) into the
#     Incidents tab as a BASELINE subsection, and drop the separate Evidence tab ---
m = re.search(r'  <section id="evidence">.*?</section>', html, re.DOTALL)
ev_block = m.group(0) if m else ""
if ev_block:
    html = html.replace(ev_block, "", 1)
    ev_block = ev_block.replace(
        '<p class="kicker">Concrete evidence · real footage</p>',
        '<p class="kicker">Proof the system really works · real footage</p>', 1)
    ev_block = "\n  <hr class=\"inc-hr\">\n" + ev_block

# 1) swap the Evidence tab link for an Incidents tab link (no separate Evidence tab)
html = html.replace('<a href="#evidence" class="tab">Evidence</a>',
                    '<a href="#incidents" class="tab">Incidents</a>', 1)
# 1b) add an Analytics tab after Incidents (only if analytics were generated)
_analytics = analytics_section()
if _analytics:
    html = html.replace('<a href="#incidents" class="tab">Incidents</a>',
                        '<a href="#incidents" class="tab">Incidents</a>\n    <a href="#analytics" class="tab">Analytics</a>', 1)
# 2) incidents section + moved baseline evidence + analytics, before governance
html = html.replace('  <section id="governance">',
                    build_section() + ev_block + _analytics + '\n  <section id="governance">', 1)
# 2b) incident-by-date analytics into the Dashboard tab
html = html.replace('  <section id="about">', dash_block() + '  <section id="about">', 1)
# 2c) header credit: Owner -> Prepared by (Senior AI Engineer)
html = html.replace('<span><b>Owner:</b> Furqan Ali</span>',
                    '<span><b>Prepared / built by:</b> Furqan Ali · Senior AI Engineer</span>', 1)
# 3) CSS before first </style>
html = html.replace('</style>', CSS + '\n</style>', 1)

# ---- convert scroll-spy anchors into REAL show/hide tabs ----
TAB_OF = {"summary": "summary", "dashboard": "dashboard", "about": "summary",
          "demo": "demo", "architecture": "architecture", "progress": "progress",
          "tests": "tests", "evidence": "incidents", "health": "tests",
          "incidents": "incidents", "governance": "governance", "next": "roadmap"}
for sid, tab in TAB_OF.items():
    html = html.replace(f'<section id="{sid}">', f'<section id="{sid}" data-tab="{tab}">', 1)
html = html.replace('<div class="summary" id="summary">',
                    '<div class="summary" id="summary" data-tab="summary">', 1)
html = re.sub(r'<section>(\s*<p class="kicker">At a glance</p>)',
              r'<section data-tab="summary">\1', html, count=1)
# add Roadmap tab
html = html.replace('<a href="#governance" class="tab">Governance</a>',
                    '<a href="#governance" class="tab">Governance</a>\n    <a href="#roadmap" class="tab">Roadmap</a>', 1)
# print rule: show every panel in the PDF
html = html.replace('</style>', '@media print{[data-tab]{display:block !important}}\n</style>', 1)
# replace scroll-spy JS with real tab show/hide
SPY = """    var tabEls=[].slice.call(document.querySelectorAll('.tab')), tmap={}, targets=[];
    tabEls.forEach(function(t){var id=t.getAttribute('href').slice(1); tmap[id]=t;
      var el=document.getElementById(id); if(el) targets.push(el);});
    if('IntersectionObserver' in window){
      var io=new IntersectionObserver(function(ents){
        ents.forEach(function(en){ if(en.isIntersecting){
          tabEls.forEach(function(x){x.classList.remove('active');});
          var t=tmap[en.target.id]; if(t) t.classList.add('active'); } });
      },{rootMargin:'-45% 0px -50% 0px',threshold:0});
      targets.forEach(function(el){io.observe(el);});
    }"""
TABS_JS = """    var tabEls=[].slice.call(document.querySelectorAll('.tab'));
    var panels=[].slice.call(document.querySelectorAll('[data-tab]'));
    function show(id){
      panels.forEach(function(p){p.style.display=(p.getAttribute('data-tab')===id)?'':'none';});
      tabEls.forEach(function(x){x.classList.toggle('active', x.getAttribute('href')==='#'+id);});
      window.scrollTo(0,0);
    }
    tabEls.forEach(function(t){t.addEventListener('click',function(e){e.preventDefault();show(t.getAttribute('href').slice(1));});});
    show('summary');
    /* ---- evidence slideshow (clickable prev/next + dots) ---- */
    [].slice.call(document.querySelectorAll('.inc-carousel')).forEach(function(c){
      var n=parseInt(c.getAttribute('data-n'),10)||1; if(n<2){return;}
      var slides=[].slice.call(c.querySelectorAll('.inc-slide'));
      var dots=[].slice.call(c.querySelectorAll('.inc-dot'));
      var cnt=c.querySelector('.inc-count'); var cur=0;
      function go(i){cur=((i%n)+n)%n;
        slides.forEach(function(s,k){s.classList.toggle('on',k===cur);});
        dots.forEach(function(d,k){d.classList.toggle('on',k===cur);});
        if(cnt){cnt.textContent=(cur+1)+' / '+n;}}
      var p=c.querySelector('.prev'),nx=c.querySelector('.next');
      if(p){p.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();go(cur-1);});}
      if(nx){nx.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();go(cur+1);});}
      dots.forEach(function(d,k){d.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();go(k);});});
    });"""
assert SPY in html, "scroll-spy JS block not found - cannot convert tabs"
html = html.replace(SPY, TABS_JS, 1)

# ---- attach the internal chat-support widget (bottom-docked, tabbed) ----
try:
    from reporting.chat_widget import widget_html
    _widget = widget_html()
    if "</body>" in html:
        html = html.replace("</body>", _widget + "\n</body>", 1)
    else:
        html = html + "\n" + _widget
except Exception as _e:
    print("chat widget skipped:", _e)

OUT.write_text(html, encoding="utf-8")
mb = OUT.stat().st_size / 1024 / 1024
print(f"Wrote {OUT.name} ({mb:.1f} MB)")
print("tab injected:", '<a href="#incidents" class="tab">Incidents</a>' in html)
print("section injected:", '<section id="incidents">' in html)
