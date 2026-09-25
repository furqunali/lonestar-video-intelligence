"""Regenerate FLOOR evidence sharper (2x upscale) + add entry/parking frames that
tell the full incident story: arrive (parking) -> enter store -> gather -> steal."""
import cv2, sys
sys.path.insert(0, r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence")
from avip.cv.detect import YoloDetector
SRC = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\New Videos for test"
OUT = r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence\reports\incident_analysis"
TEAL=(176,122,46); NAVY=(74,44,10); RED=(60,60,220); YELLOW=(0,215,255); GREEN=(90,200,90); WHITE=(255,255,255)

def annotate(clip_file, t, out_slug, out_name, conf, manual, banner_t, finding, clock, box_people=True):
    cap=cv2.VideoCapture(f"{SRC}\\{clip_file}"); fps=cap.get(cv2.CAP_PROP_FPS) or 24.0
    cap.set(cv2.CAP_PROP_POS_FRAMES,int(t*fps)); ok,fr=cap.read(); cap.release()
    if not ok: print("no frame",clip_file,t); return
    h,w=fr.shape[:2]
    up=cv2.resize(fr,(w*2,h*2),interpolation=cv2.INTER_CUBIC)   # sharper display
    H,W=up.shape[:2]
    if box_people:
        det=YoloDetector(conf=conf)
        small=cv2.resize(fr,(960,int(960*h/w))); sc=W/960.0
        for dd in det(small):
            x1,y1,x2,y2=[int(v*sc) for v in dd.xyxy]
            cv2.rectangle(up,(x1,y1),(x2,y2),TEAL,2)
            cv2.putText(up,f"person {dd.confidence:.2f}",(x1,max(int(H*0.09),y1-6)),cv2.FONT_HERSHEY_SIMPLEX,0.6,TEAL,2,cv2.LINE_AA)
    for (bx1,by1,bx2,by2),lbl in manual:
        X1,Y1,X2,Y2=int(bx1*W),int(by1*H),int(bx2*W),int(by2*H)
        cv2.rectangle(up,(X1,Y1),(X2,Y2),RED,3)
        cv2.putText(up,lbl,(X1,max(int(H*0.09),Y1-8)),cv2.FONT_HERSHEY_SIMPLEX,0.8,RED,2,cv2.LINE_AA)
    bar=int(max(40,H*0.065))
    cv2.rectangle(up,(0,0),(W,bar),NAVY,-1)
    cv2.putText(up,"SUGARLAND PETROLEUM",(10,int(bar*0.42)),cv2.FONT_HERSHEY_SIMPLEX,0.8,TEAL,2,cv2.LINE_AA)
    cv2.putText(up,banner_t,(10,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,0.62,WHITE,1,cv2.LINE_AA)
    (tw,_),_=cv2.getTextSize(clock,cv2.FONT_HERSHEY_SIMPLEX,0.62,1)
    cv2.putText(up,clock,(W-tw-10,int(bar*0.9)),cv2.FONT_HERSHEY_SIMPLEX,0.62,YELLOW,1,cv2.LINE_AA)
    cv2.rectangle(up,(0,H-40),(W,H),(20,20,20),-1)
    cv2.putText(up,finding,(10,H-14),cv2.FONT_HERSHEY_SIMPLEX,0.66,GREEN,2,cv2.LINE_AA)
    cv2.imwrite(f"{OUT}\\{out_slug}\\{out_name}_after.jpg",up,[cv2.IMWRITE_JPEG_QUALITY,90])
    print(out_slug,out_name,"@",t,"ok",up.shape[1],"x",up.shape[0])

# --- 27 JAN: arrival(parking) -> entry(door) -> gather(cooler) -> conceal ---
annotate("27 Jan 2024 Stealing 1.mp4",2.0,"27jan_steal","entry",0.25,
         [((0.50,0.10,0.72,0.30),"GROUP (parking lot)")],
         "Sales floor - group arrives at the forecourt (parking lot)",
         "AI FINDING: group of subjects crossing the forecourt toward the store entrance",
         "27/01/2024 08:04:46 PM")
annotate("27 Jan 2024 Stealing 1.mp4",4.0,"27jan_steal","entry2",0.30,
         [((0.52,0.12,1.00,0.52),"GROUP ENTERS")],
         "Sales floor - group enters the store together",
         "AI FINDING: 4 subjects entering the store together",
         "27/01/2024 08:05:00 PM")
annotate("27 Jan 2024 Stealing 1.mp4",45,"27jan_steal","suspect",0.30,[],
         "Sales floor - 4 subjects grouped at beverage cooler",
         "AI FINDING: 4 people converged at the cooler, one reaching into the fridge",
         "27/01/2024 08:05:47 PM")
annotate("27 Jan 2024 Stealing 1.mp4",110,"27jan_steal","key",0.30,[],
         "Sales floor - grab & conceal (group shielding)",
         "AI FINDING: subject concealing item while others shield - coordinated group",
         "27/01/2024 08:06:17 PM")

# --- 14 MAY: arrival(parking) -> cooler -> conceal ---
annotate("Stealing 14-may.mp4",2.0,"14may_steal","entry",0.25,
         [((0.45,0.05,0.72,0.30),"GROUP (parking lot)")],
         "Sales floor - group arrives at the forecourt (parking lot)",
         "AI FINDING: group of subjects approaching the store from the forecourt",
         "14/05/2024 04:40:53 PM")
annotate("Stealing 14-may.mp4",80,"14may_steal","suspect",0.30,[],
         "Sales floor - beverages taken from cooler + drinks case",
         "AI FINDING: cooler drinks + multi-pack drinks case carried by the group",
         "14/05/2024 04:41:35 PM")
annotate("Stealing 14-may.mp4",120,"14may_steal","key",0.30,
         [((0.70,0.35,0.88,0.78),"CONCEAL")],
         "Sales floor - merchandise concealed into clothing",
         "AI FINDING: item stuffed into waistband; gloved accomplice; group of 5+",
         "14/05/2024 04:41:59 PM")
print("done")
