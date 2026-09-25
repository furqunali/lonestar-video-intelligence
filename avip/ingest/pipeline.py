"""Ingest orchestration for M1: discover -> validate -> quarantine, with a
recorded pipeline_run. This is the deterministic entry the nightly Prefect flow
(M10) will call per site.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import Engine

from avip.common.config import Config
from avip.common.logging import get_logger
from avip.db.runs import RunHandle, finish_run, start_run
from avip.ingest.decode import probe_valid, quarantine
from avip.ingest.discover import Dump, discover_dumps

log = get_logger("ingest.pipeline")


@dataclass
class IngestResult:
    run_id: int
    valid: list[Dump] = field(default_factory=list)
    quarantined: list[Path] = field(default_factory=list)

    @property
    def dumps_processed(self) -> int:
        return len(self.valid) + len(self.quarantined)


def ingest_site(engine: Engine, config: Config, location_id: str,
                input_dir: Path | str | None = None) -> IngestResult:
    """Discover + validate dumps for one site; quarantine corrupt ones.

    Returns the valid dumps (ready for CV) plus what was quarantined, and
    records the run in pipeline_runs.
    """
    tz = config.settings.timezone
    root = Path(input_dir) if input_dir else Path(config.settings.paths.input_dir)
    qdir = Path(config.settings.paths.quarantine_dir)
    min_frames = config.settings.ingest.min_valid_frames
    sample_fps = config.settings.batch.sampling_fps

    run = start_run(engine, tz)
    result = IngestResult(run_id=run.run_id)
    status = "ok"
    try:
        all_dumps = discover_dumps(root, config)
        dumps = [d for d in all_dumps if d.location_id == location_id]
        for dump in dumps:
            ok, seen = probe_valid(dump.path, min_frames, sample_fps)
            if ok:
                result.valid.append(dump)
                log.info("dump_ok", site=location_id, file=str(dump.path), frames=seen)
            else:
                dest = quarantine(dump.path, qdir)
                result.quarantined.append(dest)
                run.errors += 1
                log.warning("dump_quarantined", site=location_id,
                            file=str(dump.path), frames=seen)
        run.dumps_processed = result.dumps_processed
    except Exception as exc:  # never crash the batch; record + re-raise-free
        status = "error"
        run.errors += 1
        log.error("ingest_failed", site=location_id, error=str(exc))
    finally:
        finish_run(engine, run, status=status)
    return result
