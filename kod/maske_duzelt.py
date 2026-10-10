"""Manken fotografinda boyama maskesini firca ile elle duzelt -> kod/duzeltme/<manken>.png
Sol tus (basili surukle): BOYANSIN (gomlek ama boyanmamis yer)    Sag tus: BOYANMASIN (manken/arka plan ama boyanmis yer)
Tekerlek: yakinlastir/uzaklastir    Orta tus surukle veya ok tuslari: kaydir    [ ve ]: firca kucult/buyut
Z: son darbeyi geri al    Enter: kaydet    Esc: vazgec.   Kirmizi = su an boyanacak yer (duzeltme dahil).
Duzeltme dosyasi sonraki 4_renk_degistir.bat calismasinda otomatik uygulanir (dosyayi silerseniz duzeltme gider)."""
import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from dugme_isaretle import JSON, yukle
import json

DIR = Path(__file__).resolve().parent / "duzeltme"


def yukle_duzelt(stem):
    f = DIR / f"{stem}.png"
    return cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_GRAYSCALE) if f.exists() else None


def duzelt(foto):
    import tkinter as tk                                           # sadece GUI'de gerekli (sunucuda tkinter olmayabilir)
    from boya import R, hazirla
    from seg.pipeline import Segmenter, analyze_model
    foto = Path(foto)
    img = yukle(foto); h, w = img.shape[:2]
    print("Maske hesaplaniyor...")
    seg = Segmenter(R / "modeller" / "segformer_b2_clothes.onnx")
    dugme = json.loads(JSON.read_text()) if JSON.exists() else {}
    alpha = hazirla(img, analyze_model(img, seg), seg, dugme.get(foto.stem, ()))["alpha"]
    corr = yukle_duzelt(foto.stem)
    corr = np.zeros((h, w), np.uint8) if corr is None or corr.shape != (h, w) else corr.copy()
    undo, st = [], dict(r=6, z=1.0, ox=0.0, oy=0.0, mod=None, last=None, pan=None, kayit=False, bekle=False)

    root = tk.Tk(); root.title(f"Maske duzelt: {foto.name}   sol=boyansin  sag=boyanmasin  tekerlek=zoom  [ ]=firca  Z=geri al  Enter=kaydet  Esc=vazgec")
    s0 = min((root.winfo_screenheight() - 120) / h, (root.winfo_screenwidth() - 40) / w)
    cw, ch = round(w * s0), round(h * s0)
    cv = tk.Canvas(root, width=cw, height=ch, highlightthickness=0, cursor="none"); cv.pack()
    item = cv.create_image(0, 0, anchor="nw")
    brush = cv.create_oval(0, 0, 0, 0, outline="yellow")

    def olcek(): return s0 * st["z"]

    def kisit():
        s = olcek()
        st["ox"] = float(np.clip(st["ox"], 0, max(0, w - cw / s))); st["oy"] = float(np.clip(st["oy"], 0, max(0, h - ch / s)))

    def ciz():
        st["bekle"] = False; kisit(); s = olcek(); ox, oy = st["ox"], st["oy"]
        M = np.float32([[s, 0, -ox * s], [0, s, -oy * s]])
        av = np.where(corr == 1, 1.0, np.where(corr == 2, 0.0, alpha)).astype(np.float32)
        v = cv2.warpAffine(img, M, (cw, ch), flags=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA, borderValue=(40, 40, 40)).astype(np.float32)
        a = cv2.warpAffine(av, M, (cw, ch), flags=cv2.INTER_LINEAR)[..., None]
        kd = cv2.warpAffine(corr, M, (cw, ch), flags=cv2.INTER_NEAREST)
        tint = np.where((kd == 1)[..., None], (0, 255, 0), (0, 0, 255)).astype(np.float32)      # yesil = elle eklenen, kirmizi = otomatik
        v = v * (1 - 0.45 * a) + tint * 0.45 * a
        v[(kd == 2)] = v[(kd == 2)] * 0.8 + np.float32((255, 120, 0)) * 0.2                    # mavi isaret = elle cikarilan
        rgb = np.ascontiguousarray(v.clip(0, 255).astype(np.uint8)[..., ::-1])
        st["img"] = tk.PhotoImage(data=b"P6\n%d %d\n255\n" % (cw, ch) + rgb.tobytes(), format="PPM")
        cv.itemconfig(item, image=st["img"])

    def iste():
        if not st["bekle"]: st["bekle"] = True; root.after_idle(ciz)

    def goruntu(e): s = olcek(); return st["ox"] + e.x / s, st["oy"] + e.y / s

    def firca(e):
        x, y = goruntu(e); r = st["r"]; s = olcek()
        cv.coords(brush, e.x - r * s, e.y - r * s, e.x + r * s, e.y + r * s)
        return x, y

    def boya(x, y):
        v = st["mod"]; p0 = st["last"] or (x, y)
        cv2.line(corr, (round(p0[0]), round(p0[1])), (round(x), round(y)), v, 2 * st["r"] + 1)
        cv2.circle(corr, (round(x), round(y)), st["r"], v, -1); st["last"] = (x, y)

    def bas(e, v):
        undo.append(corr.copy()); del undo[:-30]
        st["mod"], st["last"] = v, None; boya(*firca(e)); iste()

    def surukle(e):
        x, y = firca(e)
        if st["mod"]: boya(x, y); iste()

    def birak(_): st["mod"] = None; st["last"] = None

    def zoom(e):
        s1 = olcek(); x, y = goruntu(e)
        st["z"] = float(np.clip(st["z"] * (1.25 if e.delta > 0 else 1 / 1.25), 1.0, 8.0))
        s = olcek(); st["ox"], st["oy"] = x - e.x / s, y - e.y / s; iste(); firca(e)

    def pan_bas(e): st["pan"] = (e.x, e.y, st["ox"], st["oy"])

    def pan(e):
        if st["pan"]: x0, y0, ox, oy = st["pan"]; s = olcek(); st["ox"], st["oy"] = ox - (e.x - x0) / s, oy - (e.y - y0) / s; iste()

    def ok(dx, dy):
        def f(_): st["ox"] += dx * cw / olcek() * 0.1; st["oy"] += dy * ch / olcek() * 0.1; iste()
        return f

    def geri(_=None):
        if undo: corr[:] = undo.pop(); iste()

    def boyut(d):
        def f(_): st["r"] = int(np.clip(st["r"] + d, 1, 60))
        return f

    def kaydet(_=None):
        DIR.mkdir(exist_ok=True)
        if corr.any(): cv2.imencode(".png", corr)[1].tofile(str(DIR / f"{foto.stem}.png"))
        elif (DIR / f"{foto.stem}.png").exists(): (DIR / f"{foto.stem}.png").unlink()
        st["kayit"] = True; root.destroy()

    cv.bind("<ButtonPress-1>", lambda e: bas(e, 1)); cv.bind("<ButtonPress-3>", lambda e: bas(e, 2))
    cv.bind("<B1-Motion>", surukle); cv.bind("<B3-Motion>", surukle); cv.bind("<Motion>", lambda e: firca(e))
    cv.bind("<ButtonRelease-1>", birak); cv.bind("<ButtonRelease-3>", birak)
    cv.bind("<ButtonPress-2>", pan_bas); cv.bind("<B2-Motion>", pan); cv.bind("<MouseWheel>", zoom)
    for k, f in (("<Left>", ok(-1, 0)), ("<Right>", ok(1, 0)), ("<Up>", ok(0, -1)), ("<Down>", ok(0, 1)), ("<bracketleft>", boyut(-1)),
                 ("<bracketright>", boyut(1)), ("z", geri), ("Z", geri), ("<Return>", kaydet)): root.bind(k, f)
    root.bind("<Escape>", lambda _: root.destroy())
    ciz(); root.mainloop()
    return st["kayit"]


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f, "kaydedildi" if duzelt(f) else "vazgecildi")
