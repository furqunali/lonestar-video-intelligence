"""Config loading + validation (spec §7 rule: load from config, never hardcode).

Reads config/*.yaml into validated Pydantic models and overlays a few
environment overrides (DATABASE_URL, INPUT_DIR, OUTPUT_DIR). Invalid config
raises at load time — a fail-fast so the pipeline never runs on bad settings.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# Repo root = two levels up from this file (avip/common/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


# --------------------------------------------------------------------------- #
#  Models
# --------------------------------------------------------------------------- #
class Paths(BaseModel):
    # ONE dedicated AI folder (Upgrade item 3), separate from the rest of the company
    # drive. The app reads/writes ONLY inside this root: <root>/incoming (per-site),
    # <root>/reports, <root>/evidence. Local path for now; swap to the real shared
    # drive at launch. Override with the AI_SHARED_ROOT env var.
    ai_shared_root: str = "data/ai_shared"
    input_dir: str
    output_dir: str
    quarantine_dir: str = "data/quarantine"


class Database(BaseModel):
    url: str = "sqlite:///data/avip.db"


class ObjectStorage(BaseModel):
    endpoint: str = "localhost:9000"
    bucket: str = "evidence"


class Batch(BaseModel):
    window: str = "overnight"
    sampling_fps: float = Field(default=3, gt=0)


class Ingest(BaseModel):
    video_extensions: list[str] = [".mp4", ".avi", ".mkv"]
    min_valid_frames: int = Field(default=5, ge=1)

    @field_validator("video_extensions")
    @classmethod
    def _lower_dot(cls, exts: list[str]) -> list[str]:
        out = []
        for e in exts:
            e = e.lower().strip()
            if not e.startswith("."):
                e = "." + e
            out.append(e)
        return out


class Health(BaseModel):
    blur_laplacian_min: float = 100.0
    tamper_ssim_min: float = Field(default=0.75, ge=0.0, le=1.0)
    occlusion_solid_frac_max: float = Field(default=0.85, ge=0.0, le=1.0)
    clock_drift_max_s: float = 5.0
    solid_dark_below: int = Field(default=30, ge=0, le=255)
    solid_bright_above: int = Field(default=225, ge=0, le=255)


class Detection(BaseModel):
    model: str = "yolov8n.pt"
    device: str = "cpu"
    person_class_id: int = 0
    person_conf: float = Field(default=0.35, ge=0.0, le=1.0)
    imgsz: int = 640


class Tracking(BaseModel):
    track_activation_threshold: float = 0.35
    lost_track_buffer: int = 30
    minimum_matching_threshold: float = 0.8


class Zones(BaseModel):
    dwell_min_seconds: float = Field(default=1.0, ge=0.0)


class Markers(BaseModel):
    aruco_dict: str = "DICT_4X4_50"
    vote_min_frames: int = Field(default=3, ge=1)


class Identity(BaseModel):
    """Identity attribution (Upgrade item 6). ArUco marker code is kept in the
    pipeline but turned OFF by default — when disabled the pipeline runs normally,
    raises no errors, and does not use markers for identity. Flip to true later,
    once detection is perfect."""
    aruco_enabled: bool = False


class Gates(BaseModel):
    coverage_min_pct: float = Field(default=70, ge=0, le=100)
    confidence_min: float = Field(default=0.6, ge=0.0, le=1.0)


class Alarm(BaseModel):
    """Incident alarm (beep + clip) settings. Fires only ABOVE confidence_min and
    only on real incidents (never on 'no incident' clips)."""
    enabled: bool = True
    confidence_min: float = Field(default=0.6, ge=0.0, le=1.0)
    beep: bool = True
    show_clip: bool = True
    beep_freq_hz: int = Field(default=880, ge=37, le=32767)   # winsound.Beep range
    beep_ms: int = Field(default=600, ge=50, le=5000)
    beep_repeats: int = Field(default=3, ge=1, le=20)


class Runtime(BaseModel):
    """Where/how the pipeline runs. TEST = Furqan's PC (beep + on-screen incident +
    clip). LIVE = Mesa server (beep + clip on the Mesa LCD ONLY — never reports/HTML)."""
    mode: str = "test"                       # test | live
    alarm: Alarm = Alarm()
    # Command used in LIVE mode to show the clip on the Mesa LCD. Left unset for now
    # (LCD not wired yet); use "{clip}" as the placeholder for the clip path.
    lcd_player_cmd: str | None = None

    @field_validator("mode")
    @classmethod
    def _mode_valid(cls, m: str) -> str:
        m = (m or "").strip().lower()
        if m not in ("test", "live"):
            raise ValueError("runtime.mode must be 'test' or 'live'")
        return m


class Recipient(BaseModel):
    """One fixed report/alert recipient. Emails are filled from config (item 5 reads
    them for SMTP) — never hardcoded in code. Blank email = not yet provided."""
    name: str
    role: str = "viewer"          # camera_team_manager | engineer | site | director | viewer
    email: str = ""
    active: bool = True


class Reports(BaseModel):
    """Where reports/HTML go. LOCKED rule (Upgrade item 2): reports/HTML/dashboards go
    to the shared drive for the FIXED recipient list ONLY — and NEVER to the Mesa LCD
    (the LCD shows only the incident alarm beep + clip)."""
    destination: str = "shared_drive"
    on_lcd: bool = False
    recipients: list[Recipient] = []

    @field_validator("on_lcd")
    @classmethod
    def _never_on_lcd(cls, v: bool) -> bool:
        if v:
            raise ValueError("reports/HTML must NEVER go to the Mesa LCD (item 2)")
        return v

    def active_recipients(self) -> list[Recipient]:
        return [r for r in self.recipients if r.active]

    def recipient_emails(self) -> list[str]:
        """The fixed send-to list for item-5 email — active recipients with an email."""
        return [r.email.strip() for r in self.recipients if r.active and r.email.strip()]


class Security(BaseModel):
    """Tamper protection (Upgrade item 8). `integrity_check` is OFF in the PoC and
    turned ON in production together with a fresh known-good manifest generated from
    the reviewed commit (`python -m avip.security.integrity --update`)."""
    integrity_check: bool = False
    manifest_path: str = "security/integrity_manifest.json"
    backup_dir: str = "data/backups"


class Store(BaseModel):
    location_id: str
    name: str
    tz: str = "America/Chicago"


class Settings(BaseModel):
    project: str = "lonestar-video-intelligence"
    timezone: str = "America/Chicago"
    paths: Paths
    database: Database = Database()
    object_storage: ObjectStorage = ObjectStorage()
    batch: Batch = Batch()
    ingest: Ingest = Ingest()
    health: Health = Health()
    detection: Detection = Detection()
    tracking: Tracking = Tracking()
    zones: Zones = Zones()
    markers: Markers = Markers()
    identity: Identity = Identity()
    gates: Gates = Gates()
    runtime: Runtime = Runtime()
    reports: Reports = Reports()
    security: Security = Security()
    stores: list[Store]

    @field_validator("timezone")
    @classmethod
    def _reject_pakistan(cls, tz: str) -> str:
        # Design rule #5: store-local time only, never Pakistan (+05:00).
        if tz.strip() in ("Asia/Karachi", "+05:00", "PKT"):
            raise ValueError("store timezone must be store-local, not Pakistan")
        return tz


class CameraCfg(BaseModel):
    camera_id: str
    location_id: str
    name: str | None = None            # human label, e.g. "Register 1"
    model: str | None = None
    zones: dict[str, list[list[float]]] = {}

    @field_validator("zones")
    @classmethod
    def _valid_polygons(cls, zones):
        for name, poly in zones.items():
            if len(poly) < 3:
                raise ValueError(f"zone {name!r} needs >= 3 points")
            for pt in poly:
                if len(pt) != 2:
                    raise ValueError(f"zone {name!r} point must be [x, y]")
                x, y = pt
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise ValueError(
                        f"zone {name!r} points must be normalized 0..1, got {pt}"
                    )
        return zones


class Cameras(BaseModel):
    cameras: list[CameraCfg]


class RoleRubric(BaseModel):
    metric: str
    target: float
    weight: float = 1.0


class Rubric(BaseModel):
    version: str
    grade_bands: dict[str, float]
    gates: Gates = Gates()
    roles: dict[str, RoleRubric]

    @model_validator(mode="after")
    def _bands_ordered(self):
        b = self.grade_bands
        for k in ("A", "B", "C"):
            if k not in b:
                raise ValueError(f"grade_bands missing {k}")
        if not (b["A"] > b["B"] > b["C"]):
            raise ValueError("grade bands must satisfy A > B > C")
        return self


class Roles(BaseModel):
    colours: dict[str, str]


class Config(BaseModel):
    """The whole validated configuration tree."""
    settings: Settings
    cameras: Cameras
    rubric: Rubric
    roles: Roles

    # --- convenience accessors ---
    def store_ids(self) -> list[str]:
        return [s.location_id for s in self.settings.stores]

    def cameras_for(self, location_id: str) -> list[CameraCfg]:
        return [c for c in self.cameras.cameras if c.location_id == location_id]

    @model_validator(mode="after")
    def _cross_checks(self):
        store_ids = {s.location_id for s in self.settings.stores}
        for cam in self.cameras.cameras:
            if cam.location_id not in store_ids:
                raise ValueError(
                    f"camera {cam.camera_id} references unknown store "
                    f"{cam.location_id!r} (not in settings.stores)"
                )
        # every rubric role must have a colour mapping
        for role in self.rubric.roles:
            if role not in self.roles.colours:
                raise ValueError(f"rubric role {role!r} has no colour in roles.yaml")
        return self


# --------------------------------------------------------------------------- #
#  Loading
# --------------------------------------------------------------------------- #
def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(config_dir: Path | str | None = None) -> Config:
    """Load + validate all config. Env overrides: DATABASE_URL, INPUT_DIR, OUTPUT_DIR."""
    cdir = Path(config_dir) if config_dir else CONFIG_DIR

    settings_raw = _read_yaml(cdir / "settings.yaml")
    # Environment overrides (spec §10.3: secrets/paths from env at runtime).
    if os.getenv("DATABASE_URL"):
        settings_raw.setdefault("database", {})["url"] = os.environ["DATABASE_URL"]
    if os.getenv("INPUT_DIR"):
        settings_raw.setdefault("paths", {})["input_dir"] = os.environ["INPUT_DIR"]
    if os.getenv("OUTPUT_DIR"):
        settings_raw.setdefault("paths", {})["output_dir"] = os.environ["OUTPUT_DIR"]
    if os.getenv("AI_SHARED_ROOT"):
        settings_raw.setdefault("paths", {})["ai_shared_root"] = os.environ["AI_SHARED_ROOT"]

    return Config(
        settings=Settings(**settings_raw),
        cameras=Cameras(**_read_yaml(cdir / "cameras.yaml")),
        rubric=Rubric(**_read_yaml(cdir / "rubric.yaml")),
        roles=Roles(**_read_yaml(cdir / "roles.yaml")),
    )


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Cached default-config accessor (config/ dir)."""
    return load_config()
