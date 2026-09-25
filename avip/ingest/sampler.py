"""Frame-sampling math (spec §9.1: sample frames at the configured FPS)."""
from __future__ import annotations


def sample_stride(source_fps: float, sample_fps: float) -> int:
    """How many source frames to skip between sampled frames.

    e.g. a 30-fps clip sampled at 3 fps => keep every 10th frame.
    Always >= 1 so we never divide by zero or loop forever.
    """
    if source_fps <= 0 or sample_fps <= 0:
        return 1
    return max(1, round(source_fps / sample_fps))
