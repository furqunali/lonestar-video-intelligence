"""Focused probe: does 18.86 appear in the POS band during the cancel window?
Scans only ~80-114s, saves the best band crops so we can eyeball them too.
"""
import re, cv2, numpy as np, pytesseract, collections, os
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

SRC = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\New Videos for test\Jordan Lee Canceled Sale By -18.86.wmv"
OUTDIR = r"C:\Users\Rauf\AppData\Local\Temp\claude\C--Windows-system32\0d8d7db7-dd16-448b-95b3-83ff4af33ba3\jordan_bands"
os.makedirs(OUTDIR, exist_ok=True)
BAND = (0.50, 0.00, 1.00, 0.82)
AMT = re.compile(r"\b\d{1,3}[.,]\d{2}\b")
KEYS = re.compile(r"CANCEL|VOID|REFUND|NO ?SALE|RETURN", re.I)
WIN0, WIN1 = 80.0, 114.6   # cancel window

cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"fps={fps:.1f} frames={n} dur={n/fps:.1f}s  window={WIN0}-{WIN1}s", flush=True)

amt_times = collections.defaultdict(list)
cancel_times, found = [], []
cap.set(cv2.CAP_PROP_POS_FRAMES, int(WIN0*fps))
idx = int(WIN0*fps)
step = max(1, int(fps/4))   # 4 Hz
saved = 0
while True:
    ok, frame = cap.read()
    if not ok: break
    t = idx/fps
    if t > WIN1: break
    if idx % step == 0:
        h, w = frame.shape[:2]
        x1,y1,x2,y2 = int(BAND[0]*w),int(BAND[1]*h),int(BAND[2]*w),int(BAND[3]*h)
        crop = frame[y1:y2, x1:x2]
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        g2 = cv2.resize(g,(g.shape[1]*2,g.shape[0]*2),interpolation=cv2.INTER_CUBIC)
        tr = round(t,1)
        line_hit_1886 = False
        for thr in (150,165,180):
            _,th = cv2.threshold(g2,thr,255,cv2.THRESH_BINARY)
            up = pytesseract.image_to_string(th, config="--psm 6").upper()
            if KEYS.search(up): cancel_times.append(tr)
            for line in up.splitlines():
                for m in AMT.findall(line.replace(",",".")):
                    amt_times[m].append(tr)
                    if m=="18.86":
                        found.append((tr,line.strip())); line_hit_1886=True
        if line_hit_1886 and saved < 8:
            cv2.imwrite(os.path.join(OUTDIR,f"band_{tr}.png"), crop); saved += 1
    idx += 1
cap.release()

ct = sorted(set(cancel_times))
print(f"\nCANCEL/VOID sample-times: {len(ct)} -> {ct[:40]}", flush=True)
print("\n=== 18.86 ===", flush=True)
if found:
    ts = sorted(set(t for t,_ in found))
    print(f"YES: {len(found)} hits, {len(ts)} distinct times: {ts}", flush=True)
    for t,line in found[:15]: print(f"  t={t}  '{line}'", flush=True)
    print(f"saved {saved} band crops -> {OUTDIR}", flush=True)
else:
    print("NO 18.86 in window.", flush=True)
print("\n=== top amounts in window ===", flush=True)
for a,tl in sorted(amt_times.items(), key=lambda kv:-len(kv[1]))[:20]:
    ts=sorted(set(tl)); print(f"  {a:>8} hits={len(tl):>3} first={ts[0]} last={ts[-1]}", flush=True)
