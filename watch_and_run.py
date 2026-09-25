"""Fully-automatic watcher for the director exam.

Runs on Furqan's always-on PC (start it once with START_WATCHER.cmd). It polls the
shared-drive incoming folder; when the director drops a clip (and it finishes
copying) OR drops a `GO` file, it runs the full pipeline and publishes the report
to the shared drive — no one has to type anything. The director just drops a video
on the 2nd floor and the report appears in 01_Director_Report.
"""
from __future__ import annotations
import time
import run_incoming as ri

POLL_SECONDS = 5
TRIGGER_NAMES = ("GO", "GO.txt", "go", "go.txt", "START", "START.txt",
                 "RUN", "RUN.txt", "run.txt")


def _trigger():
    for n in TRIGGER_NAMES:
        p = ri.INCOMING / n
        if p.exists():
            return p
    return None


def main():
    print("=" * 62)
    print("  SUGARLAND PETROLEUM — Video Intelligence  ·  AUTO WATCHER")
    print("=" * 62)
    print(f"  Watching : {ri.INCOMING}")
    print(f"  Publishes: {ri.DIRREPORT}")
    print("  Drop a video (or a 'GO' file) to auto-run. Ctrl+C to stop.")
    print("-" * 62, flush=True)
    ri.INCOMING.mkdir(parents=True, exist_ok=True)
    ri.idle_status()                            # clean 'READY' so no stale % is shown
    beat = 0
    while True:
        try:
            trig = _trigger()
            vids = ri.new_videos()
            ready = [v for v in vids if ri.stable(v)]
            if trig or ready:
                print(f"\n[{time.strftime('%H:%M:%S')}] Trigger — processing "
                      f"{len(ready) or len(vids)} clip(s)…", flush=True)
                ri.main()
                if trig:
                    try:
                        trig.unlink()
                    except OSError:
                        pass
                ri.idle_status()                # reset to READY between drops
                print("[done — waiting for the next drop]", flush=True)
            else:
                beat += 1
                if beat % 12 == 0:                      # ~1 min heartbeat
                    print(f"[{time.strftime('%H:%M:%S')}] waiting…", flush=True)
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            print("\nWatcher stopped."); return 0
        except Exception as e:
            print("watch error:", e); time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
