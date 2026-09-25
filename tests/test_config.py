"""M0 acceptance: config loads & validates; DB schema builds (offline SQLite)."""
from __future__ import annotations

import pytest
from sqlalchemy import inspect

from avip.common.config import Config, load_config
from avip.db.models import init_db, make_engine


def test_config_loads_and_validates(config: Config):
    # Sites in scope (CLAUDE.md §3).
    assert set(config.store_ids()) == {"0008", "0025", "0028"}
    # Six register cameras, two per site.
    assert len(config.cameras.cameras) == 6
    for sid in config.store_ids():
        assert len(config.cameras_for(sid)) == 2
    # Store-local timezone, never Pakistan.
    assert config.settings.timezone == "America/Chicago"
    # CPU-only detection (no GPU / CUDA).
    assert config.settings.detection.device == "cpu"
    assert config.settings.detection.model == "yolov8n.pt"
    # Rubric bands + roles present with colours.
    assert config.rubric.grade_bands["A"] > config.rubric.grade_bands["B"]
    for role in config.rubric.roles:
        assert role in config.roles.colours


def test_camera_register_matches_data_request(config: Config):
    # Filled Data Request Form (29 Aug 2026): 2 register cameras per site,
    # named Register 1 / Register 2, on i3 SRX-Pro servers.
    for sid in config.store_ids():
        cams = config.cameras_for(sid)
        names = sorted(c.name for c in cams)
        assert names == ["Register 1", "Register 2"]
        assert all("SRX-Pro" in (c.model or "") for c in cams)


def test_zone_polygons_normalized(config: Config):
    for cam in config.cameras.cameras:
        assert "register" in cam.zones            # every register camera has a register zone
        for poly in cam.zones.values():
            for x, y in poly:
                assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def test_invalid_camera_store_rejected(tmp_path, monkeypatch):
    # A camera pointing at a non-existent store must fail validation.
    import yaml

    from avip.common import config as cfgmod

    cdir = tmp_path / "config"
    cdir.mkdir()
    # copy the good files, then break cameras.yaml
    src = cfgmod.CONFIG_DIR
    for name in ("settings.yaml", "rubric.yaml", "roles.yaml"):
        (cdir / name).write_text((src / name).read_text(encoding="utf-8"), encoding="utf-8")
    (cdir / "cameras.yaml").write_text(
        yaml.safe_dump({"cameras": [{
            "camera_id": "CAM-9999-1", "location_id": "9999",
            "zones": {"register": [[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]]},
        }]}),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_config(cdir)


def test_db_schema_builds(engine):
    tables = set(inspect(engine).get_table_names())
    for expected in ("events", "grades", "pipeline_runs", "dead_letter",
                     "hitl_queue", "audit_log", "employees", "markers"):
        assert expected in tables
