"""run_incoming.py — process clips dropped in the shared-drive incoming folder.

This is the single command the director-exam trigger calls (a `GO` file picked up
by the watcher, or someone typing `start`). For every NEW video in the incoming
folder it:

  1. AUTO-CALIBRATES the clip from pixels — incident type + ROI, no manual pointing
     (avip.analytics.auto_calibrate),
  2. ANALYSES it with the real CV + OCR engine (analyze_incidents),
  3. MERGES the finding into the cumulative all_findings.json,
  4. REBUILDS the ONE director report (build_consolidated) — Incidents tab,
     Dashboard by-date log and Stella all auto-update,
  5. REGENERATES the PDF (Edge headless),
  6. PUBLISHES HTML + PDF to the shared drive 01_Director_Report,
  7. ARCHIVES the processed clip into 02_Evidence.

A live STATUS.txt is written to the incoming folder the whole time so the director
can watch progress from their own PC. Integrity rule (skill §1) is preserved end
to end: nothing is derived from the filename; unknown values are never invented.

Paths can be overridden with env vars (used by the dry-run harness):
  AVIP_INCOMING, AVIP_DIRREPORT, AVIP_EVIDENCE, AVIP_ARCHIVE
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Everything runs on THIS PC (offline, CPU) for the presentation + initial launch
# (Upgrade item 4). No path is hardcoded into logic: the shared-tree base is the
# AVIP_SHARED env var (falls back to the current AP drive), and each subfolder has
# its own AVIP_* override — so the whole thing moves to the Mesa server by setting
# env vars only, no code change.
SHARED = Path(os.environ.get("AVIP_SHARED", r"G:\Shared drives\4. AP\lonestar-video-intelligence"))
INCOMING = Path(os.environ.get("AVIP_INCOMING", SHARED / "00_Incoming_Clips"))
DIRREPORT = Path(os.environ.get("AVIP_DIRREPORT", SHARED / "01_Director_Report"))
# Processed videos are kept ONLY on the local PC (Furqan's decision, 17 Sep) — the
# shared drive gets the report but NOT the raw in-store footage (privacy + size).
EVIDENCE = Path(os.environ.get("AVIP_EVIDENCE", ROOT / "02_Evidence" / "Incident_Clips"))
ARCHIVE = Path(os.environ.get("AVIP_ARCHIVE", SHARED / "99_Archive"))
# Corrupt/partial/failed clips go here (item 7): never half-processed, never left in
# incoming to loop forever. Kept locally.
QUARANTINE = Path(os.environ.get("AVIP_QUARANTINE", ROOT / "data" / "quarantine"))

ANA = ROOT / "reports" / "incident_analysis"
ALL_FINDINGS = ANA / "all_findings.json"
REPORT_HTML = ROOT / "reports" / "Sugarland_Petroleum_Video_Intelligence_Director_Report.html"
REPORT_PDF = ROOT / "reports" / "Sugarland_Petroleum_Video_Intelligence_Director_Report.pdf"
MANIFEST = ROOT / "reports" / "incoming_processed.json"
REVIEWED_LOG = ROOT / "reports" / "reviewed_log.json"
LOCK = ROOT / "reports" / ".run.lock"          # single-run guard (exam safety)
VIDEO_EXT = {".wmv", ".mp4", ".avi", ".mov", ".mkv", ".m4v"}


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _console(s: str):
    """Console echo that never crashes on a Windows cp1252 cmd window (emoji/unicode
    are replaced instead of raising UnicodeEncodeError and killing the run)."""
    try:
        print(s, flush=True)
    except Exception:
        try:
            enc = sys.stdout.encoding or "utf-8"
            sys.stdout.write(s.encode(enc, "replace").decode(enc, "replace") + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def status(msg: str, pct: int | None = None):
    """Write a live status line the director can watch, and echo to the console."""
    bar = f"[{pct:3d}%] " if pct is not None else ""
    line = f"{bar}{msg}"
    _console(f"{_now()}  {line}")
    try:
        INCOMING.mkdir(parents=True, exist_ok=True)
        (INCOMING / "STATUS.txt").write_text(
            "SUGARLAND PETROLEUM — Video Intelligence\n"
            "Automated run status (updates live)\n"
            "----------------------------------------\n"
            f"{_now()}\n\n{line}\n", encoding="utf-8")
    except Exception as e:
        print("  (status write skipped:", e, ")")


def idle_status(msg: str = "READY — waiting for a clip. Drop a CCTV video into this "
                           "folder to start the analysis."):
    """Write a clean 'ready / idle' STATUS the director can see between runs, so
    they never see a stale mid-run percentage (e.g. a frozen '92% Publishing')."""
    try:
        INCOMING.mkdir(parents=True, exist_ok=True)
        (INCOMING / "STATUS.txt").write_text(
            "SUGARLAND PETROLEUM — Video Intelligence\n"
            "Automated run status (updates live)\n"
            "----------------------------------------\n"
            f"{_now()}\n\n{msg}\n", encoding="utf-8")
    except Exception as e:
        print("  (idle status write skipped:", e, ")")


def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text())
    except Exception:
        return {}


def save_manifest(m: dict):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))


def slugify(name: str) -> str:
    stem = Path(name).stem.lower()
    base = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")[:24] or "clip"
    h = hashlib.md5(name.encode("utf-8")).hexdigest()[:4]
    return f"auto_{base}_{h}"


def stable(path: Path, tries: int = 3, gap: float = 1.0) -> bool:
    """True if the file size holds steady — i.e. the copy into the folder finished."""
    import time
    last = -1
    for _ in range(tries):
        try:
            sz = path.stat().st_size
        except OSError:
            return False
        if sz == last and sz > 0:
            return True
        last = sz
        time.sleep(gap)
    return path.stat().st_size > 0


def new_videos() -> list[Path]:
    # Any video sitting in the incoming folder is work to do. Successfully-analysed
    # clips are MOVED out to 02_Evidence, so whatever remains here is a fresh drop
    # (or a re-drop for a re-test) and must be processed — we do NOT skip on the
    # manifest, otherwise re-dropping the same clip to re-test would be ignored.
    if not INCOMING.exists():
        return []
    return [p for p in sorted(INCOMING.iterdir()) if p.suffix.lower() in VIDEO_EXT]


def merge_finding(f: dict):
    """Upsert a finding into the cumulative all_findings.json (by slug)."""
    try:
        data = json.loads(ALL_FINDINGS.read_text())
    except Exception:
        data = []
    by_slug = {x["slug"]: i for i, x in enumerate(data)}
    if f["slug"] in by_slug:
        data[by_slug[f["slug"]]] = f
    else:
        data.append(f)
    ALL_FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    ALL_FINDINGS.write_text(json.dumps(data, indent=2))


# --- INCIDENT GATE --------------------------------------------------------
# The pipeline must NOT assume every dropped clip is a theft. A normal clip (a
# person walking, a product/demo video) must return "no incident", never a
# fabricated cash-theft with an accusatory review. We decide from the MEASURED
# signals — not from the fact that a clip was dropped. Thresholds are calibrated
# against the 5 real incidents vs. observed false clips:
#   real cash: drawer activity 8-13s, presence 53-94%   |  false: 1.7s/0%, 2.7s/100%
#   real void: POS CANCEL OCR'd                          |  normal: no cancel
#   real shoplift: 6-8 people, 95-134s at zone           |  normal: <3 people / low dwell
MIN_CASH_ACTIVITY_S = 5.0
MIN_CASH_PRESENCE = 30.0
MIN_FLOOR_PEOPLE = 3
MIN_FLOOR_DWELL_S = 10.0


def assess_incident(f: dict) -> tuple[bool, str, str]:
    """Return (is_incident, verdict, reason) from measured findings only."""
    if f.get("group") == "robbery":
        mp = f.get("max_people") or 0
        return True, "robbery", (f"robbery / hold-up — {mp} person(s) tracked; the robbery "
                                 f"call is a human-review judgment, not a machine claim")
    if f["group"] == "register":
        if f.get("pos_overlay", {}).get("cancel_detected"):
            return True, "void", "POS CANCEL/VOID independently OCR'd from the on-frame receipt"
        cs = f.get("cash_drawer_activity_s") or 0
        pp = f.get("person_present_pct") or 0
        if cs >= MIN_CASH_ACTIVITY_S and pp >= MIN_CASH_PRESENCE:
            return True, "cash", f"sustained cash-drawer handling {cs}s with cashier present {pp}%"
        return (False, "none",
                f"no sustained cash-drawer handling (activity {cs}s, cashier presence {pp}%) "
                f"— looks like normal / non-register activity, not a cash incident")
    mp = f.get("max_people") or 0
    cs = f.get("cooler_interaction_s") or 0
    if mp >= MIN_FLOOR_PEOPLE and cs >= MIN_FLOOR_DWELL_S:
        return True, "shoplift", f"group of {mp} with {cs}s of activity at the target zone"
    return (False, "none",
            f"no organised-group activity ({mp} people, {cs}s dwell) — normal floor traffic, "
            f"not an organised-shoplifting incident")


def record_reviewed(pairs):
    """Append no-incident clips to a visible transparency log (last 25 kept).

    So a NORMAL clip is not silently swallowed: the report shows the system DID
    review it and correctly found no incident — proof it works, no false blame.
    """
    try:
        log = json.loads(REVIEWED_LOG.read_text())
    except Exception:
        log = []
    for v, f in pairs:
        name = Path(v.name).stem
        log = [e for e in log if e.get("name") != name]   # dedupe: keep only latest per clip
        log.append({"name": name, "when": _now(),
                    "verdict": "no incident — normal activity",
                    "reason": f.get("incident_reason", ""),
                    "confidence": f.get("calib_confidence")})
    log = log[-25:]
    REVIEWED_LOG.parent.mkdir(parents=True, exist_ok=True)
    REVIEWED_LOG.write_text(json.dumps(log, indent=2))


def analyze_one(video: Path) -> dict | None:
    """Calibrate + analyse a single unseen clip; return its augmented finding."""
    import analyze_incidents as ai
    from avip.analytics.auto_calibrate import calibrate
    from avip.cv.detect import YoloDetector

    ai.SRC = video.parent                      # analyzers read SRC / clip["file"]
    slug = slugify(video.name)

    status(f"Calibrating '{video.name}' (type + ROI from pixels)…")
    cal = calibrate(video, detector=YoloDetector(conf=0.30))
    status(f"  → {cal.group}/{cal.subtype}  confidence {cal.confidence:.2f}"
           + ("  (flagged: verify ROI)" if cal.needs_review else ""))

    clip = cal.as_clip(slug, video.name)
    status(f"Analysing '{video.name}' — detection + OCR + auto-evidence…")
    f = ai.analyze_register(clip) if cal.group == "register" else ai.analyze_floor(clip)

    # carry the calibration provenance into the finding (for the AUTO badge)
    f["auto_calibrated"] = True
    f["calib_confidence"] = round(cal.confidence, 2)
    f["calib_needs_review"] = cal.needs_review
    f["camera"] = "auto"
    f.setdefault("site", clip["site"])
    inc, verdict, reason = assess_incident(f)
    f["incident_detected"] = inc
    f["incident_verdict"] = verdict
    f["incident_reason"] = reason
    (ANA / slug / "calibration.json").write_text(json.dumps(cal.to_dict(), indent=2))
    return f


def rebuild_report() -> bool:
    status("Rebuilding the director report (Incidents · Dashboard · Stella)…", 70)
    r = subprocess.run([sys.executable, "build_consolidated.py"],
                       cwd=str(ROOT), capture_output=True, text=True)
    print(r.stdout[-600:])
    if r.returncode != 0:
        status("ERROR building report:\n" + r.stderr[-800:])
        return False
    return REPORT_HTML.exists()


def _find_edge() -> str | None:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(c).exists():
            return c
    return shutil.which("msedge")


def regenerate_pdf() -> bool:
    if os.environ.get("AVIP_SKIP_PDF"):
        status("PDF step skipped (HTML is the deliverable; Stella + report auto-update).", 88)
        return False
    edge = _find_edge()
    if not edge:
        status("PDF skipped — Microsoft Edge not found (HTML still published).")
        return False
    status("Generating the PDF (Edge headless)…", 82)
    url = "file:///" + str(REPORT_HTML).replace("\\", "/")
    # Delete any stale PDF first so we can prove a fresh one was written. Use a
    # throwaway --user-data-dir: without it Edge hands the job to an already-running
    # Edge instance and exits in ~2s WITHOUT rendering (that produced a stale PDF).
    try:
        if REPORT_PDF.exists():
            REPORT_PDF.unlink()
    except OSError:
        pass
    udd = ROOT / "reports" / "_edge_pdf_profile"
    try:
        subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run",
                        "--no-default-browser-check", "--run-all-compositor-stages-before-draw",
                        "--virtual-time-budget=45000", f"--user-data-dir={udd}",
                        "--no-pdf-header-footer", f"--print-to-pdf={REPORT_PDF}", url],
                       timeout=180, capture_output=True)
    except Exception as e:
        status(f"PDF generation error: {e} (HTML still published).")
        return False
    if not REPORT_PDF.exists():
        status("PDF did not render (HTML still published; use the report's Save-as-PDF button).")
        return False
    # Gate on real image content: a report PDF with no embedded JPEG evidence means
    # headless printed before the base64 frames decoded — don't publish that.
    try:
        blob = REPORT_PDF.read_bytes()
        has_imgs = blob.count(b"DCTDecode") > 0
    except Exception:
        has_imgs = False
    if not has_imgs:
        status("PDF rendered without evidence images — skipping PDF (HTML is complete; "
               "use the report's Save-as-PDF button for a full PDF).")
        try:
            REPORT_PDF.unlink()
        except OSError:
            pass
        return False
    return True


def publish(pdf_ok: bool):
    status("Publishing to the shared drive…", 92)
    DIRREPORT.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    # archive any previous HTML/PDF, then publish exactly one of each
    for old in list(DIRREPORT.glob("*.html")) + list(DIRREPORT.glob("*.pdf")):
        shutil.move(str(old), str(ARCHIVE / f"{old.stem}_{stamp}{old.suffix}"))
    # Self-healing (item 7): a network shared-drive can blip — retry the copy with
    # backoff before giving up so a momentary hiccup doesn't lose the publish.
    try:
        from avip.common.retry import retry_call
        retry_call(lambda: shutil.copy2(REPORT_HTML, DIRREPORT / REPORT_HTML.name),
                   attempts=3, base_delay=0.8, label="publish HTML to shared drive")
        if pdf_ok and REPORT_PDF.exists():
            retry_call(lambda: shutil.copy2(REPORT_PDF, DIRREPORT / REPORT_PDF.name),
                       attempts=3, base_delay=0.8, label="publish PDF to shared drive")
    except Exception as e:
        status(f"  ERROR publishing to shared drive after retries: {e}")
        raise


def archive_clip(video: Path) -> Path | None:
    """Move the analysed clip to the local evidence store. Returns the final path
    (used by the incident alarm to show the clip) or None if the move failed."""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    dest = EVIDENCE / video.name
    try:
        if dest.exists():                       # same clip already stored (a re-test)
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = EVIDENCE / f"{video.stem}_{stamp}{video.suffix}"
        shutil.move(str(video), str(dest))
        return dest
    except Exception as e:
        # never leave it in incoming (would reprocess forever) — remove it
        status(f"  (evidence move issue for {video.name}: {e})")
        try:
            video.unlink()
        except OSError:
            pass
        return None


def quarantine_clip(video: Path, reason: str) -> Path | None:
    """Move a corrupt/partial/failed clip out of incoming into the quarantine folder
    (item 7) with a reason sidecar. Never half-process; never leave it to re-loop."""
    try:
        QUARANTINE.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = QUARANTINE / f"{video.stem}_{stamp}{video.suffix}"
        shutil.move(str(video), str(dest))
        try:
            dest.with_suffix(dest.suffix + ".reason.txt").write_text(
                f"{_now()}\nquarantined: {reason}\n", encoding="utf-8")
        except OSError:
            pass
        status(f"  quarantined '{video.name}' -> {dest.name}  ({reason})")
        return dest
    except Exception as e:
        status(f"  (quarantine move failed for {video.name}: {e})")
        try:
            video.unlink()                     # last resort: don't let it re-loop
        except OSError:
            pass
        return None


def fire_alarms(incidents: list) -> None:
    """Upgrade item 1 — raise the incident alarm (beep + clip) for each detected
    incident, split by run mode (test = this PC / live = Mesa LCD). Config-driven and
    self-healing: never stops the run. 'No incident' clips never reach here."""
    if not incidents:
        return
    try:
        from avip.alarm import raise_incident_alarm
        from avip.common.config import get_config
        rt = get_config().settings.runtime
    except Exception as e:
        status(f"  (alarm step skipped — config/module unavailable: {e})")
        return
    for _v, f in incidents:
        try:
            r = raise_incident_alarm(f, f.get("_evidence_path"),
                                     mode=rt.mode, alarm_cfg=rt.alarm,
                                     lcd_player_cmd=rt.lcd_player_cmd)
            if r.fired:
                status(f"  ALARM ({r.mode}) - {r.message}")
            elif r.suppressed and r.reason:
                status(f"  (alarm not raised: {r.reason})")
        except Exception as e:
            status(f"  (alarm error for {f.get('slug','?')}: {e})")


def _run():
    status("Checking the incoming folder…", 2)
    vids = new_videos()
    if not vids:
        status("No new videos to process. Drop clip(s) into 00_Incoming_Clips and run again.")
        return 0

    status(f"Found {len(vids)} new clip(s): " + ", ".join(v.name for v in vids), 5)
    manifest = load_manifest()
    incidents, normals, failed = [], [], []
    for i, v in enumerate(vids):
        status(f"Waiting for '{v.name}' to finish copying…")
        if not stable(v):
            status(f"  skipped '{v.name}' — still copying / unreadable.")
            continue
        try:
            f = analyze_one(v)
            if not f:
                continue
            manifest[v.name] = {"slug": f["slug"], "when": _now(),
                                "incident": bool(f.get("incident_detected"))}
            pct = int(10 + 55 * (i + 1) / len(vids))
            if f.get("incident_detected"):
                merge_finding(f)
                incidents.append((v, f))
                status(f"  ✓ INCIDENT in '{v.name}' → {f.get('incident_verdict')} "
                       f"({f['slug']}).", pct)
            else:
                normals.append((v, f))
                status(f"  • NO INCIDENT in '{v.name}' — {f.get('incident_reason')}", pct)
        except Exception as e:
            # Self-healing (item 7): one bad file NEVER stops the batch — record the
            # failure with context and quarantine the clip so it can't re-loop.
            import traceback
            status(f"  ERROR on '{v.name}': {e} — quarantining (batch continues).")
            traceback.print_exc()
            manifest[v.name] = {"when": _now(), "failed": True, "reason": str(e)[:300]}
            failed.append(v)

    save_manifest(manifest)
    for v in failed:                            # corrupt/failed clips → quarantine
        quarantine_clip(v, "analysis error / corrupt or partial clip")
    for v, f in incidents + normals:           # every analysed clip → evidence store
        dest = archive_clip(v)
        if dest:
            f["_evidence_path"] = str(dest)     # in-memory only (not persisted)
    if normals:
        record_reviewed(normals)

    # Upgrade item 1: sound the alarm + show the clip for real incidents only.
    fire_alarms(incidents)

    if not incidents:
        n = len(normals)
        status(f"Analysed {n} clip(s) — NO loss-prevention incident detected (normal "
               f"activity). No false report filed. Updating the 'Reviewed — no incident' log…", 70)
        rebuild_report()                       # refresh so the reviewed note is visible
        publish(False)
        status(f"DONE ✅  {n} clip(s) reviewed — NO incident (normal activity). No accusation "
               f"made. See 'Reviewed — no incident' in the report Dashboard.", 100)
        return 0

    if not rebuild_report():
        return 1
    pdf_ok = regenerate_pdf()
    publish(pdf_ok)

    names = ", ".join(f["slug"] for _v, f in incidents)
    extra = (f"  ({len(normals)} other clip(s) reviewed: no incident.)" if normals else "")
    status(f"DONE ✅  {len(incidents)} incident(s) [{names}] added.{extra}\n"
           f"Open the report in 01_Director_Report:\n  {REPORT_HTML.name}"
           + ("  (+ PDF)" if pdf_ok else ""), 100)
    return 0


def integrity_gate() -> bool:
    """Upgrade item 8: refuse to run if the code/config was tampered. No-op unless
    security.integrity_check is ON in config (production). Returns True = safe to run."""
    try:
        from avip.security import IntegrityError, check_or_raise
    except Exception as e:
        status(f"  (integrity check unavailable, continuing: {e})")
        return True
    try:
        check_or_raise(alert=lambda m: status(f"SECURITY ALERT: {m}"))
        return True
    except IntegrityError as e:
        status(f"REFUSING TO RUN — integrity/tamper check failed: {e}")
        return False
    except Exception as e:
        status(f"  (integrity check error, continuing: {e})")
        return True


def main():
    """Single-run guard around _run() so two triggers (console + watcher) can never
    process/publish at the same time and corrupt the report."""
    if not integrity_gate():                   # tamper check (off by default in PoC)
        return 1
    if LOCK.exists():
        try:
            age = time.time() - LOCK.stat().st_mtime
        except OSError:
            age = 9999
        if age < 900:                          # a run started < 15 min ago is live
            status("A run is already in progress — please wait for it to finish.")
            return 0
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        LOCK.write_text(_now())
        return _run()
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
