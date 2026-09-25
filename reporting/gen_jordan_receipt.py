"""Build the Jordan receipt evidence pair (BEFORE raw / AFTER annotated) directly
from the receipt frame. The receipt text is human-verifiable; we brand it and box
the cancelled transaction. Saved into the incident_analysis/jordan_cancel folder."""
import cv2
SRC = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\New Videos for test\Jordan Lee Canceled Sale By -18.86.wmv"
OUTDIR = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\reports\incident_analysis\jordan_cancel"
TEAL=(176,122,46); NAVY=(74,44,10); RED=(60,60,220); YELLOW=(0,215,255); GREEN=(90,200,90); WHITE=(255,255,255)

cap=cv2.VideoCapture(SRC); fps=cap.get(cv2.CAP_PROP_FPS) or 24.0
cap.set(cv2.CAP_PROP_POS_FRAMES,int(108*fps)); ok,fr=cap.read(); cap.release()
h,w=fr.shape[:2]
crop=fr[int(0.42*h):h,int(0.50*w):w].copy()
crop=cv2.resize(crop,(crop.shape[1]*2,crop.shape[0]*2),interpolation=cv2.INTER_CUBIC)
before=crop.copy()
after=crop.copy()
H,W=after.shape[:2]

def banner(img,title,sub):
    bar=int(max(34,H*0.06))
    cv2.rectangle(img,(0,0),(W,bar),NAVY,-1)
    cv2.putText(img,"SUGARLAND PETROLEUM",(10,int(bar*0.42)),cv2.FONT_HERSHEY_SIMPLEX,0.7,TEAL,2,cv2.LINE_AA)
    cv2.putText(img,title,(10,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,0.6,WHITE,1,cv2.LINE_AA)
    (tw,_),_=cv2.getTextSize(sub,cv2.FONT_HERSHEY_SIMPLEX,0.6,1)
    cv2.putText(img,sub,(W-tw-10,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,0.6,YELLOW,1,cv2.LINE_AA)

# box around the cancelled JORDAN LEE transaction (left receipt column, items->TOTAL)
cv2.rectangle(after,(6,312),(792,772),RED,3)
cv2.putText(after,"CANCELLED TXN 3636162 - JORDAN LEE",(10,305),cv2.FONT_HERSHEY_SIMPLEX,0.62,RED,2,cv2.LINE_AA)
# tight highlight on the CANCELLED -18.86 line and TOTAL line
cv2.rectangle(after,(10,632),(420,676),YELLOW,2)
cv2.rectangle(after,(10,720),(300,762),YELLOW,2)
banner(after,"Register #2 - CANCELLED sale, no cash collected","11/08/2024 05:36:38 PM")
cv2.rectangle(after,(0,H-38),(W,H),(20,20,20),-1)
cv2.putText(after,"AI FINDING: SALE CANCELLED  -$18.86  (TAX 0.81)  cashier JORDAN LEE  -  goods left, no cash",
            (10,H-12),cv2.FONT_HERSHEY_SIMPLEX,0.6,GREEN,2,cv2.LINE_AA)
banner(before,"Register #2 - RAW receipt (no analysis)","11/08/2024 05:36:38 PM")

cv2.imwrite(OUTDIR+r"\receipt_before.jpg",before,[cv2.IMWRITE_JPEG_QUALITY,92])
cv2.imwrite(OUTDIR+r"\receipt_after.jpg",after,[cv2.IMWRITE_JPEG_QUALITY,92])
print("saved receipt_before/after to",OUTDIR)
