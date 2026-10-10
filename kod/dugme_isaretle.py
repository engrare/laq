"""Manken fotografindaki dugmeleri isaretleme penceresi -> kod/dugme.json
Sol tik: metal kapak dugme (yesil)   Sag tik: cit-cit disisi (mavi)
Basili tutup surukle: daire boyutu (birakmadan once dugmenin kenarina kadar cek); sadece tik: son kullanilan boyut.
Geri al: Z veya Backspace   Kaydet: Enter   Vazgec: Esc
Tam merkez sart degil: program +-4 px icinde dugmenin kenarini kendisi bulur. Kumasin parcasi gibi gorunen
dikis/kopca gibi seyleri isaretlemeyin; sadece metal parcalar."""
import base64, json, sys
from pathlib import Path
import cv2, numpy as np

JSON = Path(__file__).resolve().parent / "dugme.json"


def yukle(p):
    """Fotograf oku; uzun kenar 1280'den buyukse 1280'e indir (ayarlar WhatsApp boyutuna gore; dugme koordinatlari da bu boyutta)."""
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    k = 1280 / max(img.shape[:2])
    return cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img


def yaz(data):
    """manken basina tek satir (elle duzenlenebilir)"""
    JSON.write_text("{\n" + ",\n".join(f" {json.dumps(k)}: {json.dumps(v)}" for k, v in data.items()) + "\n}\n")


def isaretle(foto):
    import tkinter as tk                                           # sadece GUI'de gerekli (sunucuda tkinter olmayabilir)
    foto = Path(foto)
    img = yukle(foto)
    h, w = img.shape[:2]
    data = json.loads(JSON.read_text()) if JSON.exists() else {}
    pts = [list(p) + (["c" if p[2] < 6 else "k"] if len(p) == 3 else []) for p in data.get(foto.stem, [])]
    son = {"k": max(4, round(7 * w / 853)), "c": max(3, round(5 * w / 853))}

    root = tk.Tk(); root.title(f"Dugme isaretle: {foto.name}   sol=kapak  sag=cit-cit  Z=geri al  Enter=kaydet  Esc=vazgec")
    s = min(1.0, (root.winfo_screenheight() - 120) / h, (root.winfo_screenwidth() - 40) / w)
    png = cv2.imencode(".png", cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA))[1]
    tkimg = tk.PhotoImage(data=base64.b64encode(png.tobytes()))
    cv = tk.Canvas(root, width=tkimg.width(), height=tkimg.height(), highlightthickness=0); cv.pack()
    cv.create_image(0, 0, anchor="nw", image=tkimg)
    durum = {"bas": None, "kayit": False}

    def ciz():
        cv.delete("d")
        for x, y, r, t in pts:
            renk = "#00ff00" if t == "k" else "#00b4ff"
            cv.create_oval((x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s, outline=renk, width=2, tags="d")

    def bas(e, t):
        durum["bas"] = (e.x / s, e.y / s, t)

    def birak(e):
        if not durum["bas"]: return
        x, y, t = durum["bas"]; durum["bas"] = None; cv.delete("g")
        r = np.hypot(e.x / s - x, e.y / s - y)
        if r >= 3: son[t] = round(r)
        pts.append([round(x), round(y), son[t], t]); ciz()

    def surukle(e):
        if not durum["bas"]: return
        x, y, t = durum["bas"]; r = max(np.hypot(e.x / s - x, e.y / s - y), 1)
        cv.delete("g"); cv.create_oval((x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s, outline="yellow", tags="g")

    def geri(_=None):
        if pts: pts.pop(); ciz()

    def kaydet(_=None):
        data[foto.stem] = pts; yaz(data); durum["kayit"] = True; root.destroy()

    cv.bind("<ButtonPress-1>", lambda e: bas(e, "k")); cv.bind("<ButtonPress-3>", lambda e: bas(e, "c"))
    cv.bind("<ButtonRelease-1>", birak); cv.bind("<ButtonRelease-3>", birak)
    cv.bind("<B1-Motion>", surukle); cv.bind("<B3-Motion>", surukle)
    for k in ("z", "Z", "<BackSpace>"): root.bind(k, geri)
    root.bind("<Return>", kaydet); root.bind("<Escape>", lambda _: root.destroy())
    ciz(); root.mainloop()
    return durum["kayit"]


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f, "kaydedildi" if isaretle(f) else "vazgecildi")
