import cv2, sys
sys.path.insert(0, r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence")
from avip.cv.detect import YoloDetector
SRC = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\New Videos for test\Jordan Lee Canceled Sale By -18.86.wmv"
OUTDIR = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\reports\incident_analysis\jordan_cancel"
TEAL=(176,122,46); NAVY=(74,44,10); RED=(60,60,220); YELLOW=(0,215,255); GREEN=(90,200,90); WHITE=(255,255,255)
det=YoloDetector(conf=0.35)

def build(t, box, label, label_below, banner_t, finding, clock, name):
    cap=cv2.VideoCapture(SRC); fps=cap.get(cv2.CAP_PROP_FPS) or 24.0
    cap.set(cv2.CAP_PROP_POS_FRAMES,int(t*fps)); ok,fr=cap.read(); cap.release()
    h,w=fr.shape[:2]; before=fr.copy(); after=fr.copy()
    small=cv2.resize(after,(960,int(960*h/w))); sc=w/960.0; bar=int(max(40,h*0.06))
    for dd in det(small):
        x1,y1,x2,y2=[int(v*sc) for v in dd.xyxy]
        cv2.rectangle(after,(x1,y1),(x2,y2),TEAL,2)
        cv2.putText(after,f"person {dd.confidence:.2f}",(x1,max(bar+16,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,0.55,TEAL,2,cv2.LINE_AA)
    bx1,by1,bx2,by2=[int(box[i]*(w if i%2==0 else h)) for i in range(4)]
    cv2.rectangle(after,(bx1,by1),(bx2,by2),RED,3)
    ly = by2+26 if label_below else max(bar+18,by1-8)
    cv2.putText(after,label,(bx1,ly),cv2.FONT_HERSHEY_SIMPLEX,0.72,RED,2,cv2.LINE_AA)
    def bn(img,title):
        cv2.rectangle(img,(0,0),(w,bar),NAVY,-1)
        cv2.putText(img,"SUGARLAND PETROLEUM",(10,int(bar*0.42)),cv2.FONT_HERSHEY_SIMPLEX,0.7,TEAL,2,cv2.LINE_AA)
        cv2.putText(img,title,(10,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,0.55,WHITE,1,cv2.LINE_AA)
        cv2.putText(img,clock,(w-320,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,0.55,YELLOW,1,cv2.LINE_AA)
    bn(after,banner_t)
    cv2.rectangle(after,(0,h-36),(w,h),(20,20,20),-1)
    cv2.putText(after,finding,(10,h-12),cv2.FONT_HERSHEY_SIMPLEX,0.6,GREEN,2,cv2.LINE_AA)
    bn(before,"Register #2 - RAW (no analysis)")
    cv2.imwrite(f"{OUTDIR}\\{name}_before.jpg",before,[cv2.IMWRITE_JPEG_QUALITY,88])
    cv2.imwrite(f"{OUTDIR}\\{name}_after.jpg",after,[cv2.IMWRITE_JPEG_QUALITY,88])
    print(name,"@",t,"ok")

# hand-touch COMPLETE (contact) at 84.8s
build(84.8,(0.25,0.37,0.45,0.55),"HANDS TOUCH - no payment (collusion)",False,
      "Register #2 - cashier & customer hands TOUCH (no payment)",
      "AI FINDING: cashier-customer hand contact completed - goods taken, no cash paid",
      "11/08/2024 05:35:33 PM","handoff")
# receipt DROP into bin at 111.2s (arm raised into bin)
build(111.2,(0.50,0.04,0.66,0.34),"RECEIPT DROPPED IN BIN",True,
      "Register #2 - cashier drops CANCELLED receipt into bin",
      "AI FINDING: cashier drops the cancelled receipt into the trash bin (evidence disposal)",
      "11/08/2024 05:35:44 PM","dustbin")
print("done")
