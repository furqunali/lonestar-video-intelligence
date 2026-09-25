"""Interactive 'type START' console for the director exam.

Furqan's colleague keeps this window open on Furqan's PC. When the director drops
a clip into the shared-drive incoming folder, they type  START  (or GO) and press
Enter — the full pipeline runs and publishes the report. (A python prompt is used,
not the cmd prompt, because `start` is a Windows built-in that would otherwise be
intercepted.)
"""
from __future__ import annotations
import run_incoming as ri


def main():
    print("=" * 62)
    print("  SUGARLAND PETROLEUM — Video Intelligence  ·  RUN CONSOLE")
    print("=" * 62)
    print(f"  Watching folder : {ri.INCOMING}")
    print(f"  Publishes to    : {ri.DIRREPORT}")
    print("  Drop the video(s) into the incoming folder, then type START.")
    print("-" * 62)
    ri.idle_status()                            # clean 'READY' status for the director
    while True:
        try:
            cmd = input("\nType START (or GO) + Enter to process — or Q to quit: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nBye."); return 0
        if cmd in ("q", "quit", "exit"):
            print("Bye."); return 0
        if cmd in ("start", "go", "run", "s", "g", ""):
            try:
                ri.main()
            except Exception as e:
                import traceback
                print("Run error:", e); traceback.print_exc()
            ri.idle_status()                    # reset to READY after each run
            print("\n(Ready for the next run.)")
        else:
            print("  Unrecognized — type START to process, or Q to quit.")


if __name__ == "__main__":
    raise SystemExit(main())
