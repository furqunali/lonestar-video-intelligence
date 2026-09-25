"""Regenerate BEFORE/AFTER evidence at the actual theft-in-progress moment for all
5 incidents. Single-frame YOLO (fast). Boxes+ROI+brand banner+finding strip."""
import cv2, sys
sys.path.insert(0, r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence")
from avip.cv.detect import YoloDetector

SRC = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\New Videos for test"
OUT = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\reports\incident_analysis"
TEAL=(176,122,46); NAVY=(74,44,10); RED=(60,60,220); YELLOW=(0,215,255); GREEN=(90,200,90); WHITE=(255,255,255)

SPECS = [
  dict(slug="5nov_cash", file="Cash theft By cashier 5 Nov.wmv", grp="reg", t=42, conf=0.35,
       roi=(0.40,0.28,0.72,0.82), clock="11/05/2024 07:09:44 AM",
       banner="Register 1 - cash removed from OPEN drawer",
       finding="AI FINDING: hands in cash drawer, bills removed - no customer, POS idle (no sale)"),
  dict(slug="12nov_cash", file="Cash theft By Cashier 12 Nov.wmv", grp="reg", t=20, conf=0.35,
       roi=(0.36,0.26,0.78,0.84), clock="11/12/2024 07:13:41 AM",
       banner="Register 1 - cash handled at OPEN drawer",
       finding="AI FINDING: loose cash counted at open drawer - no customer, POS idle (no sale)"),
  dict(slug="jordan_cancel", file="Jordan Lee Canceled Sale By -18.86.wmv", grp="regscene", t=100, conf=0.35,
       roi=(0.30,0.20,0.55,0.75), clock="11/08/2024 05:36:34 PM",
       banner="Register 2 - sale CANCELLED -$18.86, goods handed over",
       finding="AI FINDING: JORDAN LEE cancelled -$18.86 - customer left with goods, no cash collected",
       key="scene"),
  dict(slug="27jan_steal", file="27 Jan 2024 Stealing 1.mp4", grp="floor", t=110, conf=0.30,
       clock="27/01/2024 08:06:17 PM",
       banner="Sales floor - grab & conceal (group shielding)",
       finding="AI FINDING: subject concealing item while others shield - coordinated group",
       t2=45, banner2="Sales floor - 4 subjects grouped at beverage cooler",
       finding2="AI FINDING: 4 people converged at the cooler, one reaching into the fridge"),
  dict(slug="14may_steal", file="Stealing 14-may.mp4", grp="floor", t=120, conf=0.30,
       clock="14/05/2024 04:41:59 PM",
       banner="Sales floor - merchandise concealed into clothing",
       finding="AI FINDING: item stuffed into waistband; gloved accomplice; group of 5+",
       t2=80, banner2="Sales floor - beverages taken from cooler + drinks case",
       finding2="AI FINDING: cooler drinks + multi-pack drinks case carried by the group"),
]

def banner(img, title, sub):
    h,w = img.shape[:2]; bar=int(max(40,h*0.075))
    cv2.rectangle(img,(0,0),(w,bar),NAVY,-1)
    cv2.putText(img,"SUGARLAND PETROLEUM",(10,int(bar*0.42)),cv2.FONT_HERSHEY_SIMPLEX,max(0.6,h/1400),TEAL,2,cv2.LINE_AA)
    cv2.putText(img,title,(10,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,max(0.5,h/1700),WHITE,1,cv2.LINE_AA)
    (tw,_),_=cv2.getTextSize(sub,cv2.FONT_HERSHEY_SIMPLEX,max(0.5,h/1700),1)
    cv2.putText(img,sub,(w-tw-10,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,max(0.5,h/1700),YELLOW,1,cv2.LINE_AA)

def annotate(frame, det, spec, title, finding):
    h,w = frame.shape[:2]
    before = frame.copy(); after = frame.copy()
    small = cv2.resize(after,(960,int(960*h/w))); sc = w/960.0
    for dd in det(small):
        x1,y1,x2,y2 = [int(v*sc) for v in dd.xyxy]
        cv2.rectangle(after,(x1,y1),(x2,y2),TEAL,2)
        cv2.putText(after,f"person {dd.confidence:.2f}",(x1,max(18,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,0.55,TEAL,2,cv2.LINE_AA)
    if spec.get("roi"):
        x1,y1,x2,y2=[int(spec["roi"][i]*(w if i%2==0 else h)) for i in range(4)]
        cv2.rectangle(after,(x1,y1),(x2,y2),YELLOW,2)
        cv2.putText(after,"CASH DRAWER",(x1,max(18,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,0.6,YELLOW,2,cv2.LINE_AA)
    banner(after,title,spec["clock"])
    cv2.rectangle(after,(0,h-36),(w,h),(20,20,20),-1)
    cv2.putText(after,finding,(10,h-12),cv2.FONT_HERSHEY_SIMPLEX,max(0.5,h/1800),GREEN,2,cv2.LINE_AA)
    banner(before,title.split(" - ")[0]+" - RAW (no analysis)",spec["clock"])
    return before, after

def grab(cap, t):
    cap.set(cv2.CAP_PROP_POS_FRAMES,int(t*(cap.get(cv2.CAP_PROP_FPS) or 24.0)))
    ok,fr = cap.read(); return fr if ok else None

for spec in SPECS:
    det = YoloDetector(conf=spec["conf"])
    cap = cv2.VideoCapture(f"{SRC}\\{spec['file']}")
    outdir = f"{OUT}\\{spec['slug']}"
    fr = grab(cap, spec["t"])
    if fr is not None:
        b,a = annotate(fr, det, spec, spec["banner"], spec["finding"])
        cv2.imwrite(f"{outdir}\\key_before.jpg",b,[cv2.IMWRITE_JPEG_QUALITY,88])
        cv2.imwrite(f"{outdir}\\key_after.jpg",a,[cv2.IMWRITE_JPEG_QUALITY,88])
        print(spec["slug"],"key @",spec["t"],"s ok")
    if spec.get("t2"):
        fr2 = grab(cap, spec["t2"])
        if fr2 is not None:
            b,a = annotate(fr2, det, {**spec,"roi":None}, spec["banner2"], spec["finding2"])
            cv2.imwrite(f"{outdir}\\suspect_before.jpg",b,[cv2.IMWRITE_JPEG_QUALITY,88])
            cv2.imwrite(f"{outdir}\\suspect_after.jpg",a,[cv2.IMWRITE_JPEG_QUALITY,88])
            print(spec["slug"],"2nd @",spec["t2"],"s ok")
    cap.release()
print("done")
