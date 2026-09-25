"""Pipeline integration (spec §13): one dump -> events end-to-end (M1..M5),
including idempotent re-run. Uses the offline DarkBlobDetector so the whole
chain runs deterministically without model weights."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from avip.cv.detect import DarkBlobDetector
from avip.db.models import events as events_tbl
from avip.pipeline import process_dump
from tests.synth import write_mp4

CLIP_START = datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc)   # -> 18:00 CDT


def test_one_dump_to_events_and_idempotent(config, engine, tmp_path):
    # A clip with a dark 'person' moving across the register camera's view.
    clip = write_mp4(tmp_path / "0008" / "reg1.mp4", n_frames=30, fps=10,
                     moving_person=True)
    camera = config.cameras_for("0008")[0]        # CAM-0008-1 (has a register zone)

    res = process_dump(engine, config, clip, camera,
                       clip_start=CLIP_START, detector=DarkBlobDetector())

    assert res.tracklets >= 1
    assert res.events_written >= 2                 # camera_health + >=1 person_present

    with engine.begin() as conn:
        types = set(conn.execute(
            select(events_tbl.c.event_type).distinct()
        ).scalars().all())
        count1 = conn.execute(select(func.count()).select_from(events_tbl)).scalar_one()
    assert "camera_health" in types
    assert "person_present" in types

    # Re-processing the SAME dump must not create duplicate events (idempotent).
    res2 = process_dump(engine, config, clip, camera,
                        clip_start=CLIP_START, detector=DarkBlobDetector())
    assert res2.events_written == 0
    with engine.begin() as conn:
        count2 = conn.execute(select(func.count()).select_from(events_tbl)).scalar_one()
    assert count2 == count1


def test_all_events_store_local_time(config, engine, tmp_path):
    clip = write_mp4(tmp_path / "0008" / "reg2.mp4", n_frames=20, fps=10,
                     moving_person=True)
    camera = config.cameras_for("0008")[0]
    process_dump(engine, config, clip, camera,
                 clip_start=CLIP_START, detector=DarkBlobDetector())
    with engine.begin() as conn:
        rows = conn.execute(select(events_tbl.c.ts_start)).scalars().all()
    assert rows
    # Stored timestamps correspond to 18:00 Central (23:00 UTC), never +05:00.
    for ts in rows:
        assert ts.hour == 18
