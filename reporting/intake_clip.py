"""Auto-intake for a NEW incident clip (blind, no markings). Probes any clip and
classifies it so the right analysis template can be applied — genuine detection
only, nothing hardcoded from the filename.

Usage:  python reporting/intake_clip.py "New Videos for test/<clip>"
Prints: resolution/fps/duration, header text (camera/register/date via OCR),
whether a POS receipt overlay exists, person-density, and a suggested clip TYPE.
"""
import sys, re, cv2, numpy as np, pytesseract
sys.path.insert(0, r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence")
from avip.cv.detect import YoloDetector
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

POS = re.compile(r"TOTAL|CANCEL|CASH|CHANGE|TAX|SALES|\d{1,3}\.\d{2}", re.I)

def ocr(gray):
    g = cv2.resize(gray, (gray.shape[1]*2, gray.shape[0]*2), interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    return pytesseract.image_to_string(th, config="--psm 6")

def main(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); w = int(cap.get(3)); h = int(cap.get(4))
    dur = n / fps
    print(f"file        : {path}")
    print(f"resolution  : {w}x{h}   fps {fps:.1f}   frames {n}   duration {dur:.1f}s")

    # header (top strip) — camera / register / date
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(min(n-1, fps*3)))
    ok, fr = cap.read()
    header = ""
    if ok:
        top = cv2.cvtColor(fr[0:int(0.12*h), 0:w], cv2.COLOR_BGR2GRAY)
        header = " ".join(l.strip() for l in ocr(top).splitlines() if l.strip())[:160]
    print(f"header OCR   : {header or '(none read)'}")

    # POS overlay? scan right band on a few frames for receipt-like text
    pos_hits = 0; samples = 0
    for t in np.linspace(0.2, 0.9, 6):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n*t)); ok, fr = cap.read()
        if not ok: continue
        samples += 1
        band = cv2.cvtColor(fr[:, int(0.50*w):w], cv2.COLOR_BGR2GRAY)
        if len(POS.findall(ocr(band).upper())) >= 4:
            pos_hits += 1
    has_overlay = pos_hits >= 2
    print(f"POS overlay  : {'YES' if has_overlay else 'no'}  ({pos_hits}/{samples} sampled frames receipt-like)")

    # person density
    det = YoloDetector(conf=0.30)
    counts = []
    for t in np.linspace(0.1, 0.95, 10):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n*t)); ok, fr = cap.read()
        if not ok: continue
        small = cv2.resize(fr, (960, int(960*h/w)))
        counts.append(len(det(small)))
    cap.release()
    mx = max(counts) if counts else 0
    avg = round(float(np.mean(counts)), 1) if counts else 0
    print(f"person count : max {mx}   avg {avg}   (per sampled frame)")

    # classify
    hi = header.upper()
    if has_overlay:
        typ = "POS / VOID (register with receipt overlay) -> OCR cancel/void + cashier + amount"
    elif "REGISTER" in hi or mx <= 2:
        typ = "REGISTER CASH (no overlay) -> cash-drawer ROI + no-customer + POS-idle"
    else:
        typ = "SALES FLOOR (shoplifting) -> group/cooler/shielding/concealment; UPSCALE 2x if low-res"
    lowres = w <= 800
    print(f"\nSUGGESTED    : {typ}")
    print(f"low-res      : {'YES -> upscale 2x for evidence frames' if lowres else 'no'}")
    print("next         : read the header clock by eye (burned-in clock does not OCR reliably),"
          " set start_clock + ROIs, then run the matching template in reporting/.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "New Videos for test")
