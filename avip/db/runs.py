"""pipeline_runs bookkeeping (spec §9.1, §10.5).

Every batch run is recorded: when it started/finished, how many dumps were
processed, how many events were written, error count, and the "last processed"
time the dashboard shows as batch freshness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import insert, update
from sqlalchemy.engine import Engine

from avip.common.timeutil import now_store
from avip.db.models import pipeline_runs


@dataclass
class RunHandle:
    run_id: int
    started_at: datetime
    dumps_processed: int = 0
    events_written: int = 0
    errors: int = 0
    _tz: str = field(default="America/Chicago")


def start_run(engine: Engine, tz_name: str = "America/Chicago") -> RunHandle:
    started = now_store(tz_name)
    with engine.begin() as conn:
        res = conn.execute(
            insert(pipeline_runs).values(started_at=started, status="running")
        )
        run_id = res.inserted_primary_key[0]
    return RunHandle(run_id=run_id, started_at=started, _tz=tz_name)


def finish_run(engine: Engine, run: RunHandle, status: str = "ok") -> None:
    finished = now_store(run._tz)
    with engine.begin() as conn:
        conn.execute(
            update(pipeline_runs)
            .where(pipeline_runs.c.id == run.run_id)
            .values(
                finished_at=finished,
                status=status,
                dumps_processed=run.dumps_processed,
                events_written=run.events_written,
                errors=run.errors,
                last_processed=finished,
            )
        )
