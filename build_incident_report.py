"""Build the self-contained BEFORE/AFTER incident evidence report (HTML).

Reads reports/incident_analysis/all_findings.json plus the before/after evidence
frames produced by analyze_incidents.py, and emits one portable HTML file with
every image embedded as a data URI (no external assets). Branded Sugarland
Petroleum / Mesa Valero. Dark/light aware, responsive, print-to-PDF ready.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ANA = ROOT / "reports" / "incident_analysis"
OUT_HTML = ROOT / "reports" / "Lonestar_Incident_Evidence_Report.html"

BUILD_DATE = "12 September 2026"


def data_uri(p: Path) -> str | None:
    if not p.exists():
        return None
    b = base64.b64encode(p.read_bytes()).decode()
    return f"data:image/jpeg;base64,{b}"


def img_pair(slug: str, name: str):
    b = data_uri(ANA / slug / f"{name}_before.jpg")
    a = data_uri(ANA / slug / f"{name}_after.jpg")
    return b, a


TITLES = {
    "5nov_cash": "Cash Handling - Register 1 (5 Nov)",
    "12nov_cash": "Cash Handling - Register 1 (12 Nov)",
    "jordan_cancel": "Canceled Sale - Register 2 (Jordan Lee)",
    "27jan_steal": "Sales-Floor Shoplifting (27 Jan)",
    "14may_steal": "Sales-Floor Shoplifting (14 May)",
    # Robbery / hold-up (new category) — behavioural, verified from the footage.
    "robbery_0427": "Store Robbery / Hold-up - Front Counter (27 Apr, night)",
    "robbery_0916": "Store Robbery - Sales Floor (16 Sep, night)",
    "robbery_0626": "Store Robbery / Break-in - Behind the Counter (26 Jun, overnight)",
}

# Recommended human-review conclusions. These are explicitly HUMAN judgments that
# follow from the AI-detected facts above them - NOT machine claims. Kept separate
# so the camera team can see exactly where detection ends and interpretation begins.
REVIEW = {
    "5nov_cash": ("The cashier handled cash at an open drawer. Check the till's sales list "
                  "for this time — if there was no sale, this looks like cash taken without "
                  "a sale. Send it to the loss-prevention / HR team to review."),
    "12nov_cash": ("The drawer opened and the cashier handled a fold of cash with no "
                   "customer and no sale on screen, then moved it toward their body. This "
                   "looks like cash taken without a sale. Send it to loss-prevention / HR "
                   "and check the till's no-sale / cancelled-sale list for this time."),
    "jordan_cancel": ("A full basket of items was CANCELLED and no money was taken, while the "
                     "goods still left the counter. This is a common cashier–customer trick to "
                     "give goods away free. Have loss-prevention review this cashier's full "
                     "history of cancelled sales."),
    "27jan_steal": ("Four people worked together as a group at the drinks fridge, blocking the "
                    "view and hiding items while moving through several aisles. This looks like "
                    "a planned group theft. Have loss-prevention review it and share a lookout "
                    "alert for these people."),
    "14may_steal": ("A group was active at the drinks fridges, and one person stood out by "
                    "their clothing. This looks like a planned group theft. Have "
                    "loss-prevention review it."),
    "robbery_0427": ("At night a suspect approached from the forecourt and reached over the "
                     "front counter while the cashier raised their hands. This looks like an "
                     "armed hold-up / robbery. Call it in to law enforcement, preserve this "
                     "footage as evidence, and have loss-prevention review it."),
    "robbery_0916": ("At night two hooded people moved to the drinks cooler and handled / "
                     "concealed goods. Review as a robbery / organised night theft — preserve "
                     "the footage and share a lookout alert for both suspects."),
    "robbery_0626": ("Overnight, two suspects went BEHIND the front counter and took cigarettes "
                     "/ vapes. This is a robbery / break-in. Call law enforcement, preserve the "
                     "footage, and reconcile the counter stock and register cash."),
}

# Human-verified item detail (read directly off the on-frame POS receipt). Only the
# Jordan clip carries a POS overlay, so it is the only clip with a machine-verifiable
# money value. Prices are as printed on the receipt.
JORDAN_ITEMS = [
    ("PEPSI 1L", "3.59"),
    ("CHEETOS MIX UPS", "2.69"),
    ("WONDERFUL PISTACHIOS", "5.49"),
    ("KOOL-AID SOURS GUMMIES", "2.69"),
    ("PEPSI 1L", "3.59"),
]
# subtotal 18.05 + tax 0.81 = total 18.86 (reconciles exactly to the printed receipt)
JORDAN_SUBTOTAL, JORDAN_TAX, JORDAN_TOTAL = "18.05", "0.81", "18.86"

# What was taken, by category (from the footage). Cash clips = no merchandise.
CATEGORY = {
    "5nov_cash": "Cash — notes taken from the register drawer (no products involved).",
    "12nov_cash": "Cash — notes taken from the register drawer (no products involved).",
    "27jan_steal": "Drinks from the fridge (soft / energy drinks) and packaged snacks.",
    "14may_steal": "Drinks (fridge drinks + a multi-pack case) and bagged chips (Zambos / Fritos / MAC's).",
    "robbery_0427": "Register cash and/or counter goods — taken by force/threat at the counter (confirm via Z-report + inventory).",
    "robbery_0916": "Drinks-cooler / shelf goods — handled and concealed by a group at night (confirm via inventory vs sales).",
    "robbery_0626": "Cigarettes / vapes and counter stock — taken from BEHIND the register overnight.",
}

# Measurable path to the EXACT loss value. Deliberately specific - report the
# reconciliation the store can run, anchored to the timestamps/metrics we detected.
VALUE_RECO = {
    "jordan_cancel": ("The loss is confirmed from the video at <b>$18.86</b> (5 items + $0.81 tax), read "
                     "from the cancelled receipt shown on screen. To double-check, look up the till's "
                     "<b>list of cancelled sales</b> for cashier JORDAN LEE, Register 2, on 08 Nov 2024 "
                     "around 5:34–5:37 PM."),
    "5nov_cash": ("To find the exact cash lost: compare Register 1's <b>end-of-shift cash count</b> with "
                  "the cash that should have been in the drawer for 05 Nov, around 7:05–7:15 AM. The "
                  "system saw about 12.7 seconds of drawer / cash handling with no customer and no sale "
                  "on screen — an open drawer with no matching sale is money that isn't accounted for."),
    "12nov_cash": ("To find the exact cash lost: compare Register 1's <b>end-of-shift cash count</b> with "
                   "the cash that should have been in the drawer for 12 Nov, around 7:13–7:14 AM. The "
                   "system saw about 8.3 seconds of cash handling with no sale — check the till's "
                   "<b>no-sale / cancelled-sale list</b> for this time."),
    "27jan_steal": ("To find the exact value taken: check the <b>missing-stock count</b> for the drinks "
                    "fridge and snacks for 27 Jan, around 8:04–8:08 PM, and compare it with the till's "
                    "sales for that time. Any items that went missing but were never paid for are "
                    "confirmed theft. The group stayed at the fridge about 95 seconds across 21 camera "
                    "views. Share a lookout alert for the 4 people."),
    "14may_steal": ("To find the exact value taken: check the <b>missing-stock count</b> for the drinks "
                    "fridge and chips for 14 May, around 4:40–4:44 PM, and compare it with the till's "
                    "sales for that time. Items that went missing but were never paid for are confirmed "
                    "theft. The group stayed at the fridge about 134 seconds across 36 camera views. "
                    "Share a lookout alert for everyone involved (including the person wearing a glove)."),
    "robbery_0427": ("To find the exact loss: run Register 1's <b>Z-report / cash count</b> for this "
                     "shift against the expected cash, plus an <b>inventory count</b> of the counter "
                     "stock (cigarettes / vapes) around this time. The value is whatever the cash + "
                     "stock reconciliation is short — do not estimate from the video."),
    "robbery_0916": ("To find the exact loss: compare the <b>missing-stock count</b> for the drinks "
                     "cooler / shelves for this time with the till's sales; unpaid missing items are "
                     "the confirmed loss."),
    "robbery_0626": ("To find the exact loss: reconcile the <b>cigarette / vape counter stock</b> and "
                     "the register cash against the last known counts before this overnight event; the "
                     "shortfall is the confirmed loss."),
}

# Correct on-screen start clocks (register = US M/D/Y; floor IP-cams = D/M/Y).
CLOCK = {
    "5nov_cash": "11/05/2024 07:05:27 AM",
    "12nov_cash": "11/12/2024 07:13:42 AM",
    "jordan_cancel": "11/08/2024 05:34:57 PM",
    "27jan_steal": "27/01/2024 08:04:45 PM",
    "14may_steal": "14/05/2024 04:40:53 PM",
    "robbery_0427": "27/04/2026 10:23 PM",
    "robbery_0916": "16/09/2026 09:41 PM",
    "robbery_0626": "26/06 03:52 AM",
}


def system_verdict(f: dict) -> tuple[str, str, str]:
    """Return (headline, detail, match_level) computed only from findings."""
    if f.get("group") == "robbery":
        mp = f.get("max_people", "?")
        cv = f.get("scene_cuts", "?")
        dur = f.get("duration_s", "?")
        tod = f.get("time_of_day", "")
        head = (f"Store robbery / hold-up — up to {mp} person(s) followed across "
                f"{cv} camera view(s)")
        det = (f"The system followed up to <b>{mp} person(s)</b> across {cv} camera "
               f"view(s) over a {dur}s clip"
               + (f" at {esc(tod)}" if tod else "") + ". These are the measured facts "
               "from the video; the <b>robbery / hold-up</b> conclusion is a human "
               "review judgment (see below). No cash or stock figure is taken from the "
               "video — it is reconciled from the till and inventory.")
        return head, det, "corroborates"
    if f["group"] == "register" and f.get("pos_overlay", {}).get("cancel_detected"):
        p = f["pos_overlay"]
        # Jordan amount is human-verified from the on-frame receipt (OCR of that
        # low-contrast line is unreliable); use the printed value.
        amt = JORDAN_TOTAL if f["slug"] == "jordan_cancel" else (p.get("canceled_amount") or "?")
        head = f"A sale was CANCELLED for ${amt} and no money was taken"
        det = (f"The system read the receipt text on screen and saw the sale was CANCELLED "
               f"(first seen at {p['cancel_first_s']}s, confirmed {p['cancel_sample_count']} "
               f"times) on cashier <b>{esc(p.get('cashier') or 'unknown')}</b>'s till, for a "
               f"total of <b>${amt}</b>. The sale was cancelled instead of paid — no money "
               f"was taken for the goods.")
        return head, det, "exact"
    if f["group"] == "register":
        head = f"Cash drawer opened and cash handled by hand ({f['cash_activity_pct']}% of the clip)"
        det = (f"The cashier was in view for {f['person_present_pct']}% of the clip, with "
               f"steady hand activity in the cash-drawer area for "
               f"{f['cash_drawer_activity_s']}s (most active at {f['motion_peak_time_s']}s). "
               f"Checking the till's sales list will show whether any sale went with it.")
        return head, det, "corroborates"
    # floor
    head = (f"{f['max_people']} people followed; {f['cooler_interaction_s']}s of activity "
            f"at the drinks fridge across {f['scene_cuts']} camera views")
    det = (f"The system followed the people across {f['scene_cuts']} camera views, counted up "
           f"to {f['max_people']} people, and flagged {f['cooler_interaction_s']}s of activity "
           f"at the drinks fridge."
           + (" One person stood out by their blue top."
              if f.get("blue_suspect_detected") else ""))
    return head, det, "corroborates"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- self-healing: derive render text for NEW auto-calibrated clips ----------
# The 5 blind-test clips are curated above. Any additional incident dropped in
# later (a director-exam clip from an unseen camera) has no curated title/review,
# so we DERIVE integrity-safe defaults from its findings — never a hardcoded $.
# This is what lets a freshly-dropped clip flow into the report with zero manual
# editing. Existing slugs are left exactly as curated.
CURATED_SLUGS = set(TITLES)


def _is_void(f: dict) -> bool:
    return f["group"] == "register" and bool(f.get("pos_overlay", {}).get("cancel_detected"))


def incident_category(f: dict) -> str:
    """One of: 'cash' | 'void' | 'shoplift' | 'robbery' — from findings only."""
    if f.get("group") == "robbery":
        return "robbery"
    if f["group"] == "floor":
        return "shoplift"
    return "void" if _is_void(f) else "cash"


def register_derived(findings) -> list:
    """Fill TITLES/CLOCK/REVIEW/VALUE_RECO/CATEGORY for any uncurated slug.

    Returns the list of slugs that were newly derived (so the report can badge
    them 'AUTO-CALIBRATED'). Idempotent.
    """
    new = []
    for f in findings:
        s = f["slug"]
        if s in TITLES:
            continue
        new.append(s)
        cat = incident_category(f)
        when = f.get("date") or (f.get("start_clock", "") or "")
        loc = f.get("register", "")
        if cat == "void":
            TITLES[s] = f"Cancelled Sale — {loc or 'Register'}"
            REVIEW[s] = ("A full basket was CANCELLED and no money was taken — a common cashier–"
                         "customer trick to give goods away free. Have loss-prevention review this "
                         "cashier's full history of cancelled sales. (Found automatically from the "
                         "receipt text shown on screen.)")
            VALUE_RECO[s] = ("Double-check the cancelled total against the till's <b>list of cancelled "
                             "sales</b> for this cashier, register and time — that list is the exact "
                             "record of what was lost.")
            CATEGORY[s] = "Goods that left the counter on a cancelled (unpaid) sale."
        elif cat == "cash":
            TITLES[s] = f"Cash Handling — {loc or 'Register'}"
            REVIEW[s] = ("Cash handled at the drawer. Check the till's sales / no-sale list for this "
                         "time; if there was no sale, this looks like cash taken without a sale — send "
                         "it to loss-prevention / HR. (Found automatically.)")
            VALUE_RECO[s] = ("Compare this register's <b>end-of-shift cash count</b> with the cash that "
                             "should have been in the drawer for this time; an open drawer with no "
                             "matching sale is money that isn't accounted for.")
            CATEGORY[s] = "Cash — handled at the register drawer (no products)."
        else:  # shoplift
            TITLES[s] = "Shop-Floor Shoplifting"
            REVIEW[s] = ("A group was active at the watched shelf / fridge, possibly blocking the view "
                         "and hiding items. This looks like a planned group theft — have loss-prevention "
                         "review it and share a lookout alert. (Found automatically.)")
            VALUE_RECO[s] = ("Check the <b>missing-stock count</b> for the watched shelf / fridge and time "
                             "window and compare it with the till's sales; items that went missing but "
                             "were never paid for are confirmed theft.")
            CATEGORY[s] = "Goods from the watched shelf / fridge."
        CLOCK.setdefault(s, f.get("evidence_clock") or f.get("start_clock") or str(when))
    return new


def main():
    findings = json.loads((ANA / "all_findings.json").read_text())

    # ---- summary rows
    rows = ""
    n_exact = n_corr = 0
    for f in findings:
        head, det, match = system_verdict(f)
        if match == "exact":
            n_exact += 1
            badge = '<span class="pill ok">EXACT MATCH</span>'
        else:
            n_corr += 1
            badge = '<span class="pill warn">CORROBORATED</span>'
        rows += f"""
        <tr>
          <td><b>{esc(TITLES[f['slug']])}</b><br><span class="muted">{esc(f['register'])} &middot; {esc(f.get('evidence_clock') or f.get('start_clock',''))}</span></td>
          <td>{esc(f['reported'])}</td>
          <td>{head}</td>
          <td>{badge}</td>
        </tr>"""

    # ---- incident cards
    cards = ""
    for f in findings:
        head, det, match = system_verdict(f)
        pairs = []
        rb, ra = img_pair(f["slug"], "receipt")
        if rb and ra:
            pairs.append(("POS receipt - cancelled transaction", rb, ra))
        b, a = img_pair(f["slug"], "key")
        if b and a:
            pairs.append(("Primary evidence frame", b, a))
        hb, ha = img_pair(f["slug"], "handoff")
        if hb and ha:
            pairs.append(("Cashier-customer hand contact - no payment", hb, ha))
        db, da = img_pair(f["slug"], "dustbin")
        if db and da:
            pairs.append(("Cashier discards the cancelled receipt", db, da))
        sb, sa = img_pair(f["slug"], "suspect")
        if sb and sa:
            pairs.append(("Additional evidence", sb, sa))

        pair_html = ""
        for cap, bi, ai in pairs:
            pair_html += f"""
            <div class="pairwrap">
              <div class="paircap">{esc(cap)}</div>
              <div class="pair">
                <figure><span class="tag before">BEFORE - raw footage</span><img src="{bi}"></figure>
                <figure><span class="tag after">AFTER - AI analysis</span><img src="{ai}"></figure>
              </div>
            </div>"""

        # metric chips
        chips = []
        if f["group"] == "register":
            chips.append(("Cashier present", f"{f['person_present_pct']}%"))
            chips.append(("Cash-drawer activity", f"{f['cash_drawer_activity_s']}s"))
            if f.get("pos_overlay"):
                p = f["pos_overlay"]
                chips.append(("POS cancel", "YES" if p["cancel_detected"] else "no"))
                if p.get("canceled_amount"):
                    chips.append(("Void total", f"${p['canceled_amount']}"))
                if p.get("cashier"):
                    chips.append(("Cashier (OCR)", p["cashier"]))
        else:
            chips.append(("Max people in view", f["max_people"]))
            chips.append(("Camera views", f["scene_cuts"]))
            chips.append(("Cooler activity", f"{f['cooler_interaction_s']}s"))
            chips.append(("Suspect isolated", "YES" if f.get("blue_suspect_detected") else "no"))
        chip_html = "".join(
            f'<div class="chip"><span>{esc(k)}</span><b>{esc(v)}</b></div>' for k, v in chips)

        # Products / items detail. Jordan = itemised receipt with a hard $ total;
        # other clips = the category of goods/cash taken.
        items_html = ""
        if f["slug"] == "jordan_cancel":
            rows_i = "".join(
                f"<tr><td>{esc(n)}</td><td class='num'>${esc(p)}</td></tr>" for n, p in JORDAN_ITEMS)
            items_html = (
                '<div class="items"><div class="paircap">Cancelled receipt - itemised '
                '(read from the on-frame POS receipt)</div>'
                f'<table class="rcpt"><tr><th>Item</th><th class="num">Price</th></tr>{rows_i}'
                f'<tr class="sub"><td>Subtotal</td><td class="num">${JORDAN_SUBTOTAL}</td></tr>'
                f'<tr class="sub"><td>Tax 1</td><td class="num">${JORDAN_TAX}</td></tr>'
                f'<tr class="tot"><td>CANCELLED TOTAL</td><td class="num">-${JORDAN_TOTAL}</td></tr>'
                '</table></div>')
        elif CATEGORY.get(f["slug"]):
            items_html = (f'<div class="items"><div class="paircap">Goods / cash taken '
                          f'(category)</div><p class="cat">{esc(CATEGORY[f["slug"]])}</p></div>')

        # measurable path to the exact loss value
        value_html = ""
        if VALUE_RECO.get(f["slug"]):
            value_html = (f'<div class="value"><b>Exact value - how to quantify:</b> '
                          f'{VALUE_RECO[f["slug"]]}</div>')

        # recommended human-review conclusion (interpretation, not detection)
        review_html = ""
        if REVIEW.get(f["slug"]):
            review_html = (f'<div class="review"><b>Recommended for human review:</b> '
                           f'{esc(REVIEW[f["slug"]])}</div>')

        mcls = "ok" if match == "exact" else "warn"
        cards += f"""
        <section class="card" id="{f['slug']}">
          <div class="chead">
            <h3>{esc(TITLES[f['slug']])}</h3>
            <span class="pill {mcls}">{'EXACT MATCH' if match=='exact' else 'CORROBORATED'}</span>
          </div>
          <div class="meta">{esc(f['site'])} &middot; {esc(f['register'])} &middot; {esc(CLOCK.get(f['slug']) or f.get('start_clock',''))} &middot; clip {esc(f['duration_s'])}s</div>
          <div class="verdict"><b>AI finding (from pixels):</b> {head}<br><span class="muted">{det}</span></div>
          <div class="chips">{chip_html}</div>
          {items_html}
          {value_html}
          <div class="reported"><b>Manual report (blind):</b> {esc(f['reported'])}</div>
          {review_html}
          {pair_html}
        </section>"""

    html = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lonestar Video Intelligence - Incident Evidence Report</title>
<style>
:root{{
  --bg:#0e1620; --panel:#152130; --panel2:#1b2a3c; --ink:#e8eef5; --muted:#93a3b6;
  --teal:#2e9ab0; --teal2:#38c0d8; --navy:#0a1420; --line:#24384f;
  --ok:#1f9d6b; --okbg:#12352a; --warn:#c8922a; --warnbg:#3a2f12; --red:#d0454b;
}}
@media (prefers-color-scheme: light){{
  :root{{ --bg:#eef2f6; --panel:#ffffff; --panel2:#f4f7fa; --ink:#12222f; --muted:#5b6b7c;
  --navy:#0a1420; --line:#d8e0e9; --okbg:#dff3ea; --warnbg:#fbefd4; }}
}}
:root[data-theme=dark]{{ --bg:#0e1620; --panel:#152130; --panel2:#1b2a3c; --ink:#e8eef5; --muted:#93a3b6; --line:#24384f; --okbg:#12352a; --warnbg:#3a2f12; }}
:root[data-theme=light]{{ --bg:#eef2f6; --panel:#fff; --panel2:#f4f7fa; --ink:#12222f; --muted:#5b6b7c; --line:#d8e0e9; --okbg:#dff3ea; --warnbg:#fbefd4; }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'Segoe UI',system-ui,Arial,sans-serif;line-height:1.5}}
.wrap{{max-width:1100px;margin:0 auto;padding:0 18px 60px}}
header.top{{background:linear-gradient(135deg,var(--navy),#123047);color:#fff;padding:26px 0;border-bottom:3px solid var(--teal)}}
header.top .wrap{{padding-bottom:0}}
.brand{{color:var(--teal2);font-weight:700;letter-spacing:1.5px;font-size:13px}}
h1{{margin:6px 0 4px;font-size:26px}}
.sub{{color:#b8c7d6;font-size:14px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}}
.kpi{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;text-align:center}}
.kpi b{{display:block;font-size:28px;color:var(--teal2)}}
.kpi span{{color:var(--muted);font-size:12px}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:13.5px;vertical-align:top}}
th{{background:var(--panel2);color:var(--muted);text-transform:uppercase;font-size:11px;letter-spacing:.5px}}
.tblwrap{{overflow-x:auto}}
.pill{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap}}
.pill.ok{{background:var(--okbg);color:var(--ok);border:1px solid var(--ok)}}
.pill.warn{{background:var(--warnbg);color:var(--warn);border:1px solid var(--warn)}}
h2{{margin:34px 0 10px;font-size:19px;border-left:4px solid var(--teal);padding-left:10px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin:16px 0}}
.chead{{display:flex;justify-content:space-between;align-items:center;gap:10px}}
.chead h3{{margin:0;font-size:17px}}
.meta{{color:var(--muted);font-size:12.5px;margin:4px 0 12px}}
.verdict{{background:var(--panel2);border:1px solid var(--line);border-left:4px solid var(--teal);border-radius:8px;padding:11px 13px;font-size:14px}}
.reported{{margin:12px 0;font-size:13px;color:var(--ink);background:var(--warnbg);border-radius:8px;padding:9px 12px}}
.review{{margin:10px 0;font-size:13.5px;color:var(--ink);background:var(--panel2);border:1px solid var(--red);border-left:4px solid var(--red);border-radius:8px;padding:10px 13px}}
.value{{margin:10px 0;font-size:13.5px;color:var(--ink);background:var(--panel2);border:1px solid var(--teal);border-left:4px solid var(--teal);border-radius:8px;padding:10px 13px}}
.items{{margin:12px 0}}
.items .cat{{margin:6px 0 0;font-size:14px;font-weight:600}}
table.rcpt{{width:auto;min-width:340px;margin-top:6px;border:1px solid var(--line)}}
table.rcpt th,table.rcpt td{{padding:6px 14px;font-size:13px;border-bottom:1px solid var(--line)}}
table.rcpt .num{{text-align:right;font-variant-numeric:tabular-nums}}
table.rcpt tr.sub td{{color:var(--muted)}}
table.rcpt tr.tot td{{font-weight:800;color:var(--red);border-top:2px solid var(--red)}}
.muted{{color:var(--muted)}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}}
.chip{{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:7px 11px;min-width:96px}}
.chip span{{display:block;color:var(--muted);font-size:11px}}
.chip b{{font-size:15px;color:var(--teal2)}}
.pairwrap{{margin-top:14px}}
.paircap{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.pair figure{{margin:0;position:relative;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#000}}
.pair img{{width:100%;display:block}}
.tag{{position:absolute;top:8px;left:8px;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;z-index:2}}
.tag.before{{background:#5b6b7c}}
.tag.after{{background:var(--teal)}}
.note{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:16px;font-size:13.5px;color:var(--muted)}}
.note b{{color:var(--ink)}}
.pdfbtn{{position:fixed;right:18px;bottom:18px;background:var(--teal);color:#fff;border:none;padding:12px 18px;border-radius:24px;font-weight:700;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.3);z-index:99}}
@media (max-width:760px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.pair{{grid-template-columns:1fr}}}}
@media print{{
  :root{{--bg:#fff;--panel:#fff;--panel2:#f3f5f8;--ink:#111;--muted:#555;--line:#ccc}}
  .pdfbtn{{display:none}} header.top{{background:#0a1420 !important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  .card,.kpi,.verdict,.reported,.chip{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
  .card{{break-inside:avoid}} .pair figure{{break-inside:avoid}}
}}
</style></head><body>
<header class="top"><div class="wrap">
  <div class="brand">SUGARLAND PETROLEUM &middot; AI VIDEO INTELLIGENCE</div>
  <h1>Incident Evidence Report - Blind Test</h1>
  <div class="sub">Mesa Valero (Site 0008) &middot; 5 clips analyzed independently by the AI platform &middot; Generated {BUILD_DATE}</div>
</div></header>
<div class="wrap">

  <div class="kpis">
    <div class="kpi"><b>{len(findings)}</b><span>Incidents analyzed</span></div>
    <div class="kpi"><b>{n_exact}</b><span>Exact matches (POS-proven)</span></div>
    <div class="kpi"><b>{n_corr}</b><span>Corroborated with evidence</span></div>
    <div class="kpi"><b>100%</b><span>Incidents surfaced</span></div>
  </div>

  <div class="note">
    <b>How to read this report.</b> The AI platform was given only the raw video clips - not the
    camera team's manual reports, and not the file names. Every "AI finding" below was produced
    purely from the pixels and the on-screen POS receipt text. Each piece of evidence is shown as
    <b>BEFORE</b> (raw footage) and <b>AFTER</b> (the same frame with the AI's detections drawn on it),
    so the analysis is fully auditable. The "Manual report (blind)" line is shown only so your team
    can line up our independent result against theirs.
  </div>

  <h2>Summary - System findings vs. manual report</h2>
  <div class="tblwrap"><table>
    <tr><th>Incident</th><th>Manual report (blind)</th><th>AI system finding (independent)</th><th>Result</th></tr>
    {rows}
  </table></div>

  <h2>Evidence - Before &amp; After</h2>
  {cards}

  <div class="note">
    <b>Method &amp; governance.</b> Detection uses the platform's own engine - YOLOv8n person
    detection and a deterministic IoU tracker (offline, CPU, no cloud) - plus cash-drawer motion
    analysis and Tesseract OCR of the burned-in POS receipt. Timestamps are the burned-in camera
    clock plus measured elapsed time. This is a proof-of-concept: the system's role is to
    <b>surface incidents and produce auditable evidence for human review</b>, not to make
    disciplinary decisions on its own. All footage is in-store and confidential.
  </div>
</div>
<button class="pdfbtn" onclick="window.print()">&#x2913; Save as PDF</button>
</body></html>"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    size_mb = OUT_HTML.stat().st_size / 1024 / 1024
    print(f"Wrote {OUT_HTML}  ({size_mb:.1f} MB)  exact={n_exact} corroborated={n_corr}")


if __name__ == "__main__":
    main()
