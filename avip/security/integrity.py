"""Startup integrity / tamper check (Upgrade item 8).

Hash the key code + config files and compare to a stored known-good manifest. If a
file was changed (virus / rogue agent / accidental edit), refuse to run and alert.
The running production copy is treated as read-only; the manifest is generated once
from the reviewed commit:

    python -m avip.security.integrity --update      # write known-good manifest
    python -m avip.security.integrity --check       # verify (exit 1 on mismatch)
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from avip.common.config import REPO_ROOT, Config, get_config

log = logging.getLogger("avip.security.integrity")


class IntegrityError(RuntimeError):
    """Raised when the running code/config does not match the known-good manifest."""


@dataclass
class IntegrityResult:
    ok: bool = True
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)   # tracked-but-new (informational)

    def summary(self) -> str:
        if self.ok:
            return "integrity OK"
        return (f"integrity FAILED — changed={self.changed} "
                f"missing={self.missing}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def default_key_files(root: Path) -> list[str]:
    """The files whose integrity we protect: all avip/*.py + config/*.yaml + the
    top-level runner/build scripts. Returned as POSIX relpaths, sorted, stable."""
    root = Path(root)
    files: set[Path] = set()
    files |= set((root / "avip").rglob("*.py"))
    files |= set((root / "config").glob("*.yaml"))
    for name in ("run_incoming.py", "watch_and_run.py", "run_console.py",
                 "build_consolidated.py", "build_incident_report.py",
                 "analyze_incidents.py"):
        p = root / name
        if p.exists():
            files.add(p)
    rels = []
    for p in files:
        if "__pycache__" in p.parts:
            continue
        rels.append(p.relative_to(root).as_posix())
    return sorted(rels)


def compute_manifest(root: Path | None = None, files: list[str] | None = None) -> dict:
    root = Path(root or REPO_ROOT)
    rels = files if files is not None else default_key_files(root)
    out: dict[str, str] = {}
    for rel in rels:
        p = root / rel
        if p.exists() and p.is_file():
            out[rel] = sha256_file(p)
    return out


def write_manifest(manifest: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_manifest(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(root: Path | None = None, manifest_path: Path | None = None) -> IntegrityResult:
    """Compare current files against the stored manifest."""
    root = Path(root or REPO_ROOT)
    manifest_path = Path(manifest_path or (root / "security" / "integrity_manifest.json"))
    known = load_manifest(manifest_path)
    now = compute_manifest(root, list(known.keys()))
    res = IntegrityResult()
    for rel, want in known.items():
        got = now.get(rel)
        if got is None:
            res.missing.append(rel)
        elif got != want:
            res.changed.append(rel)
    res.ok = not (res.changed or res.missing)
    return res


def check_or_raise(config: Config | None = None, *, alert=None) -> IntegrityResult:
    """Startup gate. If security.integrity_check is on: verify against the manifest
    and RAISE IntegrityError (after alerting) on any tamper. No-op if the check is
    off. If the check is on but no manifest exists, refuse to run (no baseline)."""
    cfg = config or get_config()
    sec = cfg.settings.security
    if not sec.integrity_check:
        return IntegrityResult(ok=True)
    mpath = REPO_ROOT / sec.manifest_path
    if not mpath.exists():
        msg = (f"integrity check is ON but no known-good manifest at {mpath} — "
               f"run `python -m avip.security.integrity --update` from the reviewed commit")
        log.error(msg)
        if alert:
            try:
                alert(msg)
            except Exception:
                pass
        raise IntegrityError(msg)
    res = verify(REPO_ROOT, mpath)
    if not res.ok:
        log.error(res.summary())
        if alert:
            try:
                alert(res.summary())
            except Exception:
                pass
        raise IntegrityError(res.summary())
    log.info("integrity OK (%d files verified)", len(load_manifest(mpath)))
    return res


def _main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AVIP code/config integrity manifest")
    ap.add_argument("--update", action="store_true", help="write the known-good manifest")
    ap.add_argument("--check", action="store_true", help="verify against the manifest")
    args = ap.parse_args(argv)
    mpath = REPO_ROOT / "security" / "integrity_manifest.json"
    if args.update:
        m = compute_manifest(REPO_ROOT)
        write_manifest(m, mpath)
        print(f"wrote manifest: {mpath}  ({len(m)} files)")
        return 0
    if args.check:
        if not mpath.exists():
            print(f"no known-good manifest at {mpath} - run --update first")
            return 1
        res = verify(REPO_ROOT, mpath)
        print(res.summary())
        return 0 if res.ok else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
