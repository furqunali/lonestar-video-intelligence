# Sugarland Petroleum — AI Video Intelligence
## How to give the demo in the Director's room (Mustafa sir)

**Golden rule:** apna laptop le kar jao. Sab kuch is laptop par offline chalta hai —
internet ki zaroorat NAHI. Room ka PC use karna ho to sirf Layer 1 (neeche) ke 2 files
USB/shared drive se copy kar lo.

---

### What is in this DEMO folder
| File | Kya hai |
|------|---------|
| `1_START_HERE_Report.html` | Poori report — summary, evidence, architecture, tests. Double-click → browser me khulti hai. |
| `2_Annotated_Evidence.mp4` | System ka apna output — real footage par detections. Double-click → play. |
| `RUN_LIVE_DEMO.cmd` | Ek click me LIVE detection chalata hai (~25 sec). Sirf is laptop par. |
| `demo_input_short.mp4` | 60-sec input clip jo live demo use karti hai. |

---

## LAYER 1 — Zero-risk demo (yehi primary, ye kabhi fail nahi hoti)

1. **`1_START_HERE_Report.html`** double-click karo → upar **Summary** dikhado (2 line padho).
2. Thoda scroll → **"See it work in three steps"** → phir **LIVE EVIDENCE** wali moving clip.
3. Ya seedha **`2_Annotated_Evidence.mp4`** play kar do — green boxes = system khud logon ko detect kar raha hai.
4. Report me neeche: **Architecture map**, **Milestone board**, **Test report (55 passed)**.
5. Report ke upar right corner me **"⤓ Save as PDF"** button hai → PDF nikal ke email/print kar sakte ho.

> Sirf yeh Layer 1 hi ek complete, professional demo hai. Agar nervous ho to bas yehi karo.

---

## LAYER 2 — "Abhi chala ke dikhao" (optional wow) — SIRF apne laptop par

1. **`RUN_LIVE_DEMO.cmd`** double-click karo.
2. Black window khulega: "Loading detector… detecting people…" ~25 second.
3. Khud hi ek annotated video khul jayegi (green boxes + Sugarland Petroleum branding).
4. Agar kisi wajah se Python na chale → ye script **khud** pre-rendered clip khol deti hai. **Fail nahi hogi.**

---

## Bologe kya (30-second script)

> "Ye system hamari maujooda camera recordings leta hai — koi naya hardware nahi, internet nahi,
> footage kahin bahar nahi jati. Sab kuch store ke andar, isi laptop jaise CPU par chalta hai.
>
> Ye khud logon ko detect karta hai, unhe register / sales-floor / entrance zone me daalta hai,
> aur har cheez ek timestamped record ban jati hai. Ye dekhiye — real Mesa Valero rush-hour footage
> par 130 frames me 125 detections.
>
> Full automation me ye har raat khud sabhi stores ki clips process karega. Lekin faisla hamesha
> insaan ka — system sirf measure aur flag karta hai, koi bhi grade insaan ki approval ke baghair
> publish nahi hota.
>
> Abhi ye ek working proof-of-concept hai jo hamari apni footage par proven hai. Agla step:
> camera team se ek reference frame + roster, phir graded pilot."

---

## Do / Don't
- ✅ Laptop charge karke le jao; DEMO folder desktop par rakho.
- ✅ Demo se pehle ek baar `RUN_LIVE_DEMO.cmd` ghar par chala kar test kar lo.
- ✅ PDF pehle se bana kar rakho (report → Save as PDF) — backup ke taur par.
- ❌ 2 GB wali wmv clips demo me mat chalao — slow hain. Sirf `demo_input_short.mp4`.
- ❌ Shared drive se live detection mat chalao — wo sirf backup copy ke liye hai.

**Sab data private + offline hai. In-store footage kahin commit ya upload nahi hoti.**
