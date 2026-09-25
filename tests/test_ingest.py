"""M1 acceptance: discover dumps, decode/sample, sanitize paths, quarantine
corrupt dumps, record run in pipeline_runs."""
from __future__ import annotations

from sqlalchemy import select

from avip.db.models import pipeline_runs
from avip.ingest.decode import iter_sampled_frames, probe_valid, source_fps
from avip.ingest.discover import discover_dumps
from avip.ingest.pipeline import ingest_site
from avip.ingest.sampler import sample_stride
from tests.synth import write_corrupt_mp4, write_mp4


def test_sample_stride():
    assert sample_stride(30, 3) == 10
    assert sample_stride(10, 3) == 3          # round(3.33)
    assert sample_stride(0, 3) == 1           # guard
    assert sample_stride(30, 0) == 1


def test_discover_only_known_sites(config, tmp_path):
    inc = tmp_path / "incoming"
    write_mp4(inc / "0008" / "reg1.mp4", n_frames=12, fps=10)
    write_mp4(inc / "0099" / "reg1.mp4", n_frames=12, fps=10)   # unknown site
    dumps = discover_dumps(inc, config)
    assert len(dumps) == 1
    assert dumps[0].location_id == "0008"


def test_discover_attaches_known_camera_id(config, tmp_path):
    inc = tmp_path / "incoming"
    write_mp4(inc / "0008" / "CAM-0008-1_clip.mp4", n_frames=12, fps=10)
    dumps = discover_dumps(inc, config)
    assert dumps[0].camera_id == "CAM-0008-1"


def test_decode_samples_at_target_fps(tmp_path):
    path = write_mp4(tmp_path / "clip.mp4", n_frames=30, fps=30)
    assert round(source_fps(path)) == 30
    frames = list(iter_sampled_frames(path, sample_fps=3))
    # 30 frames at stride 10 -> ~3 sampled frames.
    assert 2 <= len(frames) <= 4
    f = frames[0]
    assert f.image.shape[2] == 3 and f.image.dtype.name == "uint8"
    assert f.ts_seconds >= 0.0


def test_corrupt_dump_is_invalid(tmp_path):
    bad = write_corrupt_mp4(tmp_path / "bad.mp4")
    ok, seen = probe_valid(bad, min_frames=5, sample_fps=3)
    assert ok is False


def test_ingest_site_quarantines_and_records_run(config, engine, tmp_path):
    inc = tmp_path / "incoming"
    write_mp4(inc / "0008" / "good.mp4", n_frames=20, fps=10)
    write_corrupt_mp4(inc / "0008" / "bad.mp4")

    # send quarantine into the temp tree
    object.__setattr__(config.settings.paths, "quarantine_dir", str(tmp_path / "quar"))

    result = ingest_site(engine, config, "0008", input_dir=inc)
    assert len(result.valid) == 1
    assert len(result.quarantined) == 1
    assert result.quarantined[0].exists()          # moved aside
    assert not (inc / "0008" / "bad.mp4").exists()  # no longer in incoming

    with engine.begin() as conn:
        row = conn.execute(
            select(pipeline_runs).where(pipeline_runs.c.id == result.run_id)
        ).mappings().one()
    assert row["status"] == "ok"
    assert row["dumps_processed"] == 2
    assert row["errors"] == 1
    assert row["last_processed"] is not None
