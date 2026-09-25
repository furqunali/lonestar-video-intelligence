"""Person detection (spec §9.3).

The real detector is YOLOv8n on CPU (small model, no GPU — CLAUDE.md §3).
Detection sits behind a small interface so the tracking/zone logic — and the
tests — do not depend on model weights or a network download. Two offline
detectors (scripted stub, dark-blob) let the pipeline be tested deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class Detection:
    xyxy: tuple[float, float, float, float]   # x1, y1, x2, y2 (pixels)
    confidence: float
    class_id: int = 0                         # 0 = person (COCO)

    @property
    def bottom_center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, y2)


class Detector(Protocol):
    def __call__(self, frame: np.ndarray) -> list[Detection]: ...


class YoloDetector:
    """YOLOv8n person detector (Ultralytics), CPU by default.

    Lazily loads the model on first call so importing this module never pulls
    torch or downloads weights. Weights (yolov8n.pt) download once on first use.
    """

    def __init__(self, model: str = "yolov8n.pt", device: str = "cpu",
                 person_class_id: int = 0, conf: float = 0.35, imgsz: int = 640):
        self.model_name = model
        self.device = device
        self.person_class_id = person_class_id
        self.conf = conf
        self.imgsz = imgsz
        self._model = None

    def _ensure(self):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self.model_name)

    def __call__(self, frame: np.ndarray) -> list[Detection]:
        self._ensure()
        res = self._model.predict(
            frame, device=self.device, conf=self.conf, imgsz=self.imgsz,
            classes=[self.person_class_id], verbose=False,
        )[0]
        out: list[Detection] = []
        for box in res.boxes:
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            out.append(Detection((x1, y1, x2, y2), float(box.conf[0]),
                                 int(box.cls[0])))
        return out


class ScriptedDetector:
    """Returns pre-set detections per frame (deterministic tests)."""

    def __init__(self, per_frame: Sequence[Sequence[Detection]]):
        self._per_frame = list(per_frame)
        self._i = 0

    def __call__(self, frame: np.ndarray) -> list[Detection]:
        dets = list(self._per_frame[self._i]) if self._i < len(self._per_frame) else []
        self._i += 1
        return dets


class DarkBlobDetector:
    """Offline stand-in: finds dark upright blobs ('people') via thresholding.

    Exercises real OpenCV (threshold + contours) so the tracking/zone pipeline
    can be tested end-to-end without model weights.
    """

    def __init__(self, dark_below: int = 60, min_area: int = 300, conf: float = 0.9):
        self.dark_below = dark_below
        self.min_area = min_area
        self.conf = conf

    def __call__(self, frame: np.ndarray) -> list[Detection]:
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mask = (gray < self.dark_below).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out: list[Detection] = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w * h < self.min_area:
                continue
            out.append(Detection((float(x), float(y), float(x + w), float(y + h)),
                                 self.conf))
        return out
