"""Sugarland Petroleum - AI Video Intelligence - LIVE DEMO runner.

Runs the REAL detector on a short clip and writes a branded, annotated video,
then opens it. Designed to finish in ~30s on a normal laptop CPU. Safe to run
in front of the director: if anything is missing it prints a clear message and
falls back to opening the pre-rendered evidence clip.

Double-click RUN_LIVE_DEMO.cmd instead of running this by hand.
"""
import os, sys, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                     # DEMO/ lives inside the repo
sys.path.insert(0, REPO)

INPUT   = os.path.join(HERE, "demo_input_short.mp4")
OUTPUT  = os.path.join(HERE, "LIVE_RESULT_annotated.mp4")
PRERES  = os.path.join(REPO, "Mesa_Valero_Register1_ANNOTATED_evidence.mp4")
SAMPLE_FPS = 2.0
CONF = 0.35

def openfile(p):
    try: os.startfile(p)                          # Windows
    except Exception:
        subprocess.run(["cmd", "/c", "start", "", p], shell=False)

def fallback(msg):
    print("\n[!]", msg)
    print("[i] Opening the pre-rendered evidence clip instead (always works).")
    openfile(PRERES if os.path.exists(PRERES) else HERE)
    input("\nPress Enter to close...")
    sys.exit(0)

print("="*64)
print("  SUGARLAND PETROLEUM - AI Video Intelligence - LIVE DEMO")
print("  Mesa Valero (Site 0008) - Register 1")
print("="*64)

try:
    import cv2, numpy as np, av
    from avip.cv.detect import YoloDetector
except Exception as e:
    fallback(f"Python libraries not ready on this PC ({e}).")

if not os.path.exists(INPUT):
    fallback("Demo input clip not found next to this script.")

ZONES = {"register":[[0.30,0.35],[0.70,0.35],[0.70,0.95],[0.30,0.95]],
         "entrance":[[0.72,0.05],[0.98,0.05],[0.98,0.55],[0.72,0.55]]}
ZCOL  = {"register":(196,181,20),"entrance":(224,148,139)}

def poly_px(p,w,h): return np.array([[int(x*w),int(y*h)] for x,y in p],np.int32)
def zone_of(cx,cy,w,h):
    for nm,p in ZONES.items():
        if cv2.pointPolygonTest(poly_px(p,w,h),(float(cx),float(cy)),False)>=0: return nm
    return "sales_floor"

print("\n[1/3] Loading detector (YOLOv8n, CPU)...")
weights = os.path.join(REPO,"yolov8n.pt")
det = YoloDetector(model=weights if os.path.exists(weights) else "yolov8n.pt",
                   device="cpu", person_class_id=0, conf=CONF, imgsz=640)

print("[2/3] Watching the clip and detecting people...\n")
c=av.open(INPUT); st=c.streams.video[0]
rate=st.average_rate or st.base_rate; fps=float(rate) if rate else SAMPLE_FPS
stride=max(1,round(fps/SAMPLE_FPS)); W=st.codec_context.width; H=st.codec_context.height
ow=980; oh=int(H*ow/W)
vw=cv2.VideoWriter(OUTPUT, cv2.VideoWriter_fourcc(*"mp4v"), 6.0, (ow,oh))
t0=time.time(); processed=0; withppl=0; total=0
for i,fr in enumerate(c.decode(st)):
    if i%stride: continue
    img=fr.to_ndarray(format="bgr24"); ts=float(fr.pts*st.time_base) if fr.pts is not None else i/fps
    dets=det(img); processed+=1
    vis=img.copy()
    for nm,p in ZONES.items():
        cv2.polylines(vis,[poly_px(p,W,H)],True,ZCOL[nm],2)
        q=poly_px(p,W,H)[0]; cv2.putText(vis,nm,(q[0]+4,q[1]+22),cv2.FONT_HERSHEY_SIMPLEX,0.7,ZCOL[nm],2,cv2.LINE_AA)
    for d in dets:
        x1,y1,x2,y2=[int(v) for v in d.xyxy]; cx,cy=d.bottom_center; z=zone_of(cx,cy,W,H)
        cv2.rectangle(vis,(x1,y1),(x2,y2),(70,220,130),2)
        lb=f"person {d.confidence:.2f} [{z}]"
        (tw,th),_=cv2.getTextSize(lb,cv2.FONT_HERSHEY_SIMPLEX,0.6,2)
        cv2.rectangle(vis,(x1,y1-th-8),(x1+tw+6,y1),(70,220,130),-1)
        cv2.putText(vis,lb,(x1+3,y1-5),cv2.FONT_HERSHEY_SIMPLEX,0.6,(20,30,20),2,cv2.LINE_AA)
    n=len(dets); total+=n; withppl+=(n>0)
    cv2.rectangle(vis,(0,0),(W,58),(22,26,36),-1); cv2.rectangle(vis,(0,56),(W,58),(196,181,20),-1)
    cv2.putText(vis,"SUGARLAND PETROLEUM",(12,26),cv2.FONT_HERSHEY_SIMPLEX,0.82,(240,244,250),2,cv2.LINE_AA)
    cv2.putText(vis,"AI Video Intelligence  -  Mesa Valero (Site 0008) - Register 1 - CAM-0008-1",
                (12,48),cv2.FONT_HERSHEY_SIMPLEX,0.55,(178,190,206),1,cv2.LINE_AA)
    s=f"t={ts:5.1f}s   persons: {n}"; (sw,_),_=cv2.getTextSize(s,cv2.FONT_HERSHEY_SIMPLEX,0.66,2)
    cv2.putText(vis,s,(W-sw-14,34),cv2.FONT_HERSHEY_SIMPLEX,0.66,(120,210,235),2,cv2.LINE_AA)
    cv2.rectangle(vis,(0,H-24),(W,H),(22,26,36),-1)
    cv2.putText(vis,"Sugarland Petroleum - AI Video Intelligence  |  Confidential - for internal review",
                (12,H-8),cv2.FONT_HERSHEY_SIMPLEX,0.5,(150,162,178),1,cv2.LINE_AA)
    vw.write(cv2.resize(vis,(ow,oh)))
    if processed%10==0: print(f"    ...{processed} frames, {withppl} with people, {total} detections")
vw.release(); c.close()
dt=time.time()-t0
print("\n[3/3] Done.")
print("-"*64)
print(f"  Frames analysed : {processed}")
print(f"  Frames w/ people: {withppl}")
print(f"  Person detections: {total}")
print(f"  Compute time    : {dt:.0f}s on CPU (no GPU, no internet)")
print("-"*64)
print("\nOpening the annotated result...")
openfile(OUTPUT)
input("\nDemo complete. Press Enter to close...")
