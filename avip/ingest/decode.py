"""Decode + sample dumps with PyAV (spec §9.1).

PyAV bundles ffmpeg, so no system ffmpeg is required. Corrupt/partial dumps
are detected (too few decodable frames) and quarantined — never half-processed.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from avip.common.logging import get_logger

log = get_logger("ingest.decode")


class DecodeError(Exception):
    """Raised when a dump cannot be decoded at all."""


@dataclass(frozen=True)
class SampledFrame:
    index: int          # frame index within the source stream
    ts_seconds: float   # presentation time, seconds from clip start
    image: np.ndarray   # BGR uint8 (H, W, 3)


def _open_video(path: Path):
    import av

    try:
        container = av.open(str(path))
    except Exception as exc:  # av.AVError and friends
        raise DecodeError(f"cannot open {path}: {exc}") from exc
    if not container.streams.video:
        container.close()
        raise DecodeError(f"no video stream in {path}")
    return container


def source_fps(path: Path) -> float:
    """Average frames-per-second of the first video stream."""
    container = _open_video(path)
    try:
        stream = container.streams.video[0]
        rate = stream.average_rate or stream.base_rate
        return float(rate) if rate else 0.0
    finally:
        container.close()


def iter_sampled_frames(path: Path | str, sample_fps: float) -> Iterator[SampledFrame]:
    """Yield frames sampled down to ``sample_fps`` from the dump.

    Decoding errors mid-stream stop iteration cleanly (partial dump); the
    caller decides whether the number of frames obtained is sufficient.
    """
    from avip.ingest.sampler import sample_stride

    path = Path(path)
    container = _open_video(path)
    try:
        stream = container.streams.video[0]
        rate = stream.average_rate or stream.base_rate
        fps = float(rate) if rate else sample_fps
        stride = sample_stride(fps, sample_fps)
        tb = stream.time_base
        try:
            for i, frame in enumerate(container.decode(stream)):
                if i % stride:
                    continue
                if frame.pts is not None and tb is not None:
                    ts = float(frame.pts * tb)
                else:
                    ts = i / fps if fps else float(i)
                yield SampledFrame(i, ts, frame.to_ndarray(format="bgr24"))
        except Exception as exc:  # truncated/partial stream
            log.warning("decode_truncated", file=str(path), error=str(exc))
    finally:
        container.close()


def probe_valid(path: Path | str, min_frames: int, sample_fps: float) -> tuple[bool, int]:
    """Return (is_valid, frames_seen). Valid iff we decode >= min_frames sampled frames."""
    seen = 0
    try:
        for _ in iter_sampled_frames(path, sample_fps):
            seen += 1
            if seen >= min_frames:
                return True, seen
    except DecodeError as exc:
        log.warning("probe_undecodable", file=str(path), error=str(exc))
        return False, seen
    return seen >= min_frames, seen


def quarantine(path: Path | str, quarantine_dir: Path | str) -> Path:
    """Move a corrupt/partial dump aside so it is never half-processed."""
    path = Path(path)
    qdir = Path(quarantine_dir)
    qdir.mkdir(parents=True, exist_ok=True)
    dest = qdir / path.name
    if dest.exists():
        dest = qdir / f"{path.stem}_{abs(hash(str(path))) % 10000}{path.suffix}"
    shutil.move(str(path), str(dest))
    log.warning("quarantined", src=str(path), dest=str(dest))
    return dest
