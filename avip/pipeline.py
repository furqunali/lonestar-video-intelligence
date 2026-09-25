"""End-to-end data-plane processing for a single dump (M1 -> M5).

Chains the deterministic data plane: decode + sample -> camera health ->
detect/track/zones -> ArUco vote -> build canonical events -> persist
(idempotent, dead-letter on invalid). The M10 nightly Prefect flow calls this
per dump; it is plain, testable Python with no agent/LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from avip.common.config import CameraCfg, Config
from avip.common.logging import get_logger
from avip.common.timeutil import now_store
from avip.cv.detect import Detector, YoloDetector
from avip.cv.health import assess_health
from avip.cv.markers import ArucoReader, decode_markers_for_frames, vote_marker
from avip.cv.process import nominal_dt, process_clip
from avip.events.builder import build_camera_health_event, build_tracklet_events
from avip.events.store import persist_events
from avip.ingest.decode import iter_sampled_frames

log = get_logger("pipeline")

RESTRICTED_ZONE_NAMES = {"restricted"}


@dataclass
class DumpResult:
    events_written: int
    tracklets: int
    health_clarity: str


def process_dump(
    engine: Engine,
    config: Config,
    dump_path: Path | str,
    camera: CameraCfg,
    *,
    clip_start: datetime | None = None,
    detector: Detector | None = None,
) -> DumpResult:
    """Process one dump into persisted events. Returns a small summary."""
    tz = config.settings.timezone
    sample_fps = config.settings.batch.sampling_fps
    clip_start = clip_start or now_store(tz)
    detector = detector or YoloDetector(
        model=config.settings.detection.model,
        device=config.settings.detection.device,
        person_class_id=config.settings.detection.person_class_id,
        conf=config.settings.detection.person_conf,
        imgsz=config.settings.detection.imgsz,
    )

    frames = list(iter_sampled_frames(dump_path, sample_fps))
    images = [f.image for f in frames]

    # --- camera health (foundation) ---
    health = assess_health(images, config.settings.health,
                           baseline=images[0] if images else None)
    ndt = nominal_dt(frames) if frames else 1.0

    events = []
    if frames:
        events.append(build_camera_health_event(
            camera.location_id, camera.camera_id,
            clip_start, clip_start, health, tz_name=tz,
        ))

    # --- detect / track / zones ---
    tracklets = process_clip(frames, detector, camera.zones)

    # --- markers (ArUco vote) — kept in the pipeline but OFF by default (item 6) ---
    aruco_on = config.settings.identity.aruco_enabled
    if aruco_on:
        reader = ArucoReader(config.settings.markers.aruco_dict)
        per_frame_markers = decode_markers_for_frames(reader, frames)
    else:
        # Disabled: run normally, no errors, no marker identity used.
        per_frame_markers = {}
        log.info("aruco_disabled", camera=camera.camera_id)
    restricted = RESTRICTED_ZONE_NAMES & set(camera.zones)

    for tl in tracklets:
        code = (vote_marker(tl, per_frame_markers,
                            config.settings.markers.vote_min_frames)
                if aruco_on else None)
        events.extend(build_tracklet_events(
            camera.location_id, camera.camera_id, tl, health, clip_start,
            nominal_dt=ndt,
            dwell_min_seconds=config.settings.zones.dwell_min_seconds,
            restricted_zones=restricted, marker_code=code,
            evidence_bucket=config.settings.object_storage.bucket, tz_name=tz,
        ))

    written = persist_events(engine, events)
    log.info("dump_processed", camera=camera.camera_id, dump=str(dump_path),
             tracklets=len(tracklets), events_written=written,
             health=health.clarity)
    return DumpResult(events_written=written, tracklets=len(tracklets),
                      health_clarity=health.clarity)
