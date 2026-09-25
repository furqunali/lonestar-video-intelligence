# Heat-Mapping — implementation plan (offline, CPU, no new model)

Everything needed already exists in the pipeline. Standard "spatial density accumulator"
method maps 1:1 onto our per-frame track outputs. OpenCV + numpy only.

## Inputs we already have
- `avip/cv/detect.py` → `Detection.bottom_center` = ((x1+x2)/2, y2) = **feet point** (the correct floor anchor for retail heatmaps).
- `avip/cv/process.py` → `Tracklet.observations` (frame_index, ts_seconds, xyxy, confidence, zones); `nominal_dt(frames)` = seconds per sample (for dwell weighting).
- `avip/cv/zones.py` → normalized zone polygons per camera (for per-zone ranking).
- `build_incident_report.py` → base64 embed pattern for the self-contained HTML.

## Two flavours (same post-processing)
- **Traffic/frequency:** +1 per present feet sample → where people go / how often.
- **Dwell-time:** +`nominal_dt` seconds per sample, ×2 boost when feet nearly stationary (small displacement between consecutive obs) → where people linger (queues, displays). More valuable retail signal.

## Post-processing (canonical)
1. Accumulate feet points into float32 array `A` (H×W native res).
2. `cv2.GaussianBlur(A, (0,0), sigma)` — sigma ≈ half a person's on-screen footprint.
3. `cv2.normalize(..., 0,255, NORM_MINMAX)` → uint8.
4. `cv2.applyColorMap(..., COLORMAP_TURBO)`.
5. Blend over a clean reference frame; **mask cold pixels** (let background show through in dead zones — looks professional).

## Accuracy notes
- Use FEET point, not centroid (angled/overhead cams).
- Dwell = weight by `nominal_dt` (correct regardless of sampling rate).
- **Time-of-day comparison MUST share the normalization max** across both images, else quiet hour looks as hot as rush (the #1 DIY bug).
- Ignore flickery 1-frame tracks (mannequins/reflections become fake hotspots) — heatmap only tracks with ≥N observations.
- Hotspots: threshold at ~95th percentile + `cv2.connectedComponentsWithStats`.
- Homography to a top-down floor plan = optional phase 2 (4 clicked floor points); raw-view overlay needs no calibration — ship that first.

## Director-facing outputs (new "Heat Maps" tab)
1. Per-camera traffic + dwell overlays (TURBO on clean frame) + colorbar legend.
2. Busiest zones ranked (sum accumulator inside `cameras.yaml` polygons).
3. Dwell-by-zone table (person-seconds, avg dwell) — reuse `Tracklet.zone_dwell`.
4. Rush vs normal shared-scale pair.
+ Privacy line: heatmaps are anonymous aggregate foot positions (no faces/identity) — compliance selling point.

## Minimal function (OpenCV + numpy)
```python
import cv2, numpy as np
def build_heatmap(points, background, sigma=25, alpha=0.5, colormap=cv2.COLORMAP_TURBO, mask_cold=True):
    h, w = background.shape[:2]
    acc = np.zeros((h, w), np.float32)
    for p in points:                       # p = (frame_idx, foot_x, foot_y[, weight])
        x, y = int(round(p[1])), int(round(p[2]))
        wgt = p[3] if len(p) > 3 else 1.0  # 1.0=traffic ; nominal_dt=dwell
        if 0 <= x < w and 0 <= y < h: acc[y, x] += wgt
    if acc.max() <= 0: return background.copy()
    acc = cv2.GaussianBlur(acc, (0, 0), sigmaX=sigma, sigmaY=sigma)
    norm = cv2.normalize(acc, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    colored = cv2.applyColorMap(norm, colormap)
    if mask_cold:
        m = (norm.astype(np.float32) / 255.0)[..., None]
        return (background * (1 - alpha * m) + colored * (alpha * m)).astype(np.uint8)
    return cv2.addWeighted(background, 1 - alpha, colored, alpha, 0)
# feed: pts=[(o.frame_index,*Detection(o.xyxy,o.confidence).bottom_center, nominal_dt(frames)) for t in tracklets for o in t.observations]
```

## Build order
1. Raw-view traffic + dwell overlays → base64 → new "Heat Maps" tab. (all inputs exist)
2. Zone-ranked + dwell-by-zone tables.
3. Shared-scale time-of-day pair.
4. Optional homography floor-density (only if a director asks).
