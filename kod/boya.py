"""Manken ayni model gomlegi giyiyorsa: mankendeki gomlegi yeniden boyar (CatVTON yok).
Dugme/cep/kol/doku mankenden aynen kalir. Kullanim: python kod/boya.py [manken_adi_parcasi] [--ig] [--isaretle]
  dugme.json'da olmayan manken icin once dugme isaretleme penceresi acilir (--isaretle: hepsini yeniden isaretle).
- Kenarlarda piksel basina 'gomlek orani' (alfa) hesaplanir: p' = p + alfa*(boyali(F) - F); tasma olmaz.
- Dugmeler kod/dugme.json'daki konumlardan hassas maskelenir ve boyanmaz."""
import json, re, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from seg.pipeline import Segmenter, analyze_model, extract_shirt_color
from dugme_isaretle import JSON, yukle
from maske_duzelt import yukle_duzelt

R = Path(__file__).resolve().parent.parent
wr = lambda p, im, q=96: cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tofile(str(p))
ell = lambda n: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


def nconv(img, w, s):
    """agirlikli (normalize) bulaniklastirma: sadece w>0 piksellerin yerel ortalamasi"""
    w = w.astype(np.float32)
    return cv2.GaussianBlur(img.astype(np.float32) * w[..., None], (0, 0), s) / (cv2.GaussianBlur(w, (0, 0), s)[..., None] + 1e-4)


def dugme_maske(img, noktalar, kumas):
    """Dugme alfasi (0..1); json'da yaklasik [x, y, yaricap, tip] (tip yoksa: yaricap < 6 -> "c").
    "k" metal kapak (kumasla ayni tonda): merkez +-max(4, r/3) px / yaricap +-max(1, r/8) icinde, cevresi boyunca disa dogru
      koyu->acik kenari en guclu daire secilir; daire ici aynen kalir.
    "c" cit-cit disisi (gumus, kumastan farkli): +2 px cevrede yerel kumas rengine uzak pikseller kalir."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = cv2.GaussianBlur(lab[..., 0], (0, 0), 0.8)
    gx, gy = cv2.Sobel(L, cv2.CV_32F, 1, 0), cv2.Sobel(L, cv2.CV_32F, 0, 1)
    co, si = np.cos(np.linspace(0, 2 * np.pi, 48, endpoint=False)), np.sin(np.linspace(0, 2 * np.pi, 48, endpoint=False))
    yy, xx = np.mgrid[:L.shape[0], :L.shape[1]]
    out, D = np.zeros(L.shape, np.float32), np.zeros(L.shape, np.uint8)
    for x, y, rad, *tip in noktalar:
        if (tip[0] if tip else "c" if rad < 6 else "k") == "c":
            cv2.circle(D, (int(x), int(y)), int(rad) + 2, 1, -1); continue
        def skor(c):
            cx, cy, r = c
            px = np.clip(np.round(cx + r * co).astype(int), 0, L.shape[1] - 1); py = np.clip(np.round(cy + r * si).astype(int), 0, L.shape[0] - 1)
            return (gx[py, px] * co + gy[py, px] * si).mean()
        e, er = max(4, rad // 3), max(1, rad // 8)                    # yakin cekimde (buyuk dugme) arama alani da buyur
        cx, cy, r = max(((cx, cy, r) for cx in range(x - e, x + e + 1) for cy in range(y - e, y + e + 1)
                         for r in range(rad - er, rad + er + 1)), key=skor)
        out = np.maximum(out, np.clip(r + 0.3 - np.hypot(xx - cx, yy - cy), 0, 1))   # dis kenar halkasi (orijinal acik kahve) boyali kalsin
    if D.any():
        Fl = nconv(lab, kumas & (cv2.dilate(D, ell(9)) == 0), 6)       # cit-cit disindaki yerel kumas rengi
        d = np.sqrt((((lab - Fl) * (0.7, 1, 1)) ** 2).sum(2))
        b = cv2.morphologyEx(np.clip((d - 14) / 20, 0, 1) * D, cv2.MORPH_CLOSE, ell(3))
        out = np.maximum(out, cv2.GaussianBlur(b, (0, 0), 0.7) * D)
    return out

def hazirla(img, sm, seg, dugme_pts=(), duzelt=None):
    """Mankene ozel (renkten bagimsiz) kisim: maske, kenar alfasi, yerel kumas rengi, dugme alfasi. Manken basina 1 kez."""
    p = seg.probs(img)
    M = sm.mask.copy().astype(np.uint8)
    lower = cv2.erode((p["lower"] > 0.7).astype(np.uint8), ell(5)) > 0
    M[(p["skin"] > 0.6) | (p["hair"] > 0.6) | lower] = 0
    # SegFormer acik renkli yaka altini cilt sayar; kromu kumasa yakin (cilde degil) piksellerle maskeyi buyut
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 1.0), cv2.COLOR_BGR2LAB).astype(np.float32)
    cd = np.hypot(lab[..., 1] - sm.ref_lab[1], lab[..., 2] - sm.ref_lab[2])
    grow = (cv2.dilate(M, ell(25)) > 0) & (M == 0) & (cd < 8) & (lab[..., 0] > 80) & (lab[..., 0] < 185) \
           & (p["skin"] < 0.97) & (p["hair"] < 0.5) & ~lower
    grow = cv2.morphologyEx(grow.astype(np.uint8), cv2.MORPH_OPEN, ell(3))
    M = cv2.morphologyEx(np.maximum(M, grow), cv2.MORPH_CLOSE, ell(5))
    # ic tisort: parlak + kumas kromasindan uzak + cilt degil; kenar golgesi dahil maskeden cikar
    tee = ((lab[..., 0] > 165) & (cd > 9) & (p["skin"] < 0.5) & (p["bg"] < 0.3)).astype(np.uint8)   # arka plan degil
    n, lbl, st, _ = cv2.connectedComponentsWithStats(tee, 8)
    tee = cv2.dilate(np.isin(lbl, 1 + np.nonzero(st[1:, cv2.CC_STAT_AREA] > 800)[0]).astype(np.uint8), ell(7)) > 0
    M[tee] = 0
    M = (cv2.medianBlur(M * 255, 7) > 127).astype(np.uint8)         # tirtikli yaka/kenar cikintilarini duzelt
    zone = cv2.dilate((p["skin"] > 0.5).astype(np.uint8), ell(25)) > 0   # cilde komsu kenarlar (yaka/el): ek Gauss ile pürüzsüz
    M = np.where(zone, cv2.GaussianBlur(M.astype(np.float32), (0, 0), 2.2) > 0.5, M > 0).astype(np.uint8)
    n, lbl, st, _ = cv2.connectedComponentsWithStats(M, 8)
    if n > 1:                                                      # sol/sag panel ayri bilesen olabilir; yalnizca kucuk lekeleri at
        M = np.isin(lbl, 1 + np.nonzero(st[1:, cv2.CC_STAT_AREA] > 0.05 * st[1:, cv2.CC_STAT_AREA].max())[0]).astype(np.uint8)
    # GrabCut: kenari +-7 px icinde gercek renk kenarina oturt (yaka/cilt, sac telleri, maskedeki delikler)
    x, y, w, h = cv2.boundingRect(cv2.dilate(M, ell(31)))
    gc = np.where(cv2.erode(M, ell(15)) > 0, cv2.GC_FGD, np.where(M > 0, cv2.GC_PR_FGD,
                  np.where(cv2.dilate(M, ell(15)) > 0, cv2.GC_PR_BGD, cv2.GC_BGD))).astype(np.uint8)[y:y + h, x:x + w].copy()
    cv2.setRNGSeed(0)                                              # GrabCut kmeans: her calismada ayni sonuc (maske_duzelt duzeltmesi tutarli kalsin)
    cv2.grabCut(np.ascontiguousarray(img[y:y + h, x:x + w]), gc, None, np.zeros((1, 65)), np.zeros((1, 65)), 5, cv2.GC_INIT_WITH_MASK)
    M = np.zeros_like(M); M[y:y + h, x:x + w] = gc & 1
    gap = cv2.dilate(((lab[..., 0] > 165) & (cd > 9) & (p["bg"] > 0.15)).astype(np.uint8), ell(3)) > 0   # kol-govde arasi arka plan boslugu (SegFormer burada bg~0.2-0.3)
    M[tee | gap | (p["hair"] > 0.6)] = 0
    M[(cv2.dilate(tee.astype(np.uint8), ell(7)) > 0) & (cd > 9)] = 0       # beyaz ic tisortun gri kenar golgesi (kumas kromasinda degil) boyanmasin
    M = (cv2.GaussianBlur(M.astype(np.float32), (0, 0), 1.2) > 0.5).astype(np.uint8)   # graf-kesim merdivenlerini yumusat
    n, lbl, st, _ = cv2.connectedComponentsWithStats(M, 8)
    if n > 1:
        M = np.isin(lbl, 1 + np.nonzero(st[1:, cv2.CC_STAT_AREA] > 0.05 * st[1:, cv2.CC_STAT_AREA].max())[0]).astype(np.uint8)

    inner = cv2.erode(M, ell(7))
    near = cv2.dilate(M, ell(9))
    F = nconv(img, inner, 5)                                       # yerel kumas rengi (boyama icin, BGR)
    # alfa: Lab'da ton 0.25, renk ozu 2 agirlikli; isik alan yaka kenari tonca cilde, renk ozunce kumasa yakin
    W = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32) * np.float32((0.25, 2, 2))
    Fw, Bw = nconv(W, inner, 5), nconv(W, 1 - near, 5)            # yerel kumas / disaridaki renk (arka plan/cilt/pantolon/tisort)
    d = Fw - Bw
    alpha = ((W - Bw) * d).sum(2) / ((d * d).sum(2) + 1e-3)
    # kumas->dis renk dogrusuna uzak pikseller (tisort altindaki koyu golge gibi) kumas degildir: maske disinda boyama
    resid = np.linalg.norm(W - (Bw + np.clip(alpha, 0, 1)[..., None] * d), axis=2)
    notshirt = (M == 0) & (resid > 22)
    bgs = cv2.GaussianBlur(p["bg"], (0, 0), 2) > 0.5
    # tisort/cilt kenarinda sert esik (yansima boyanmasin), arka plan kenarinda gevsek esik (keskinlestirme halesi boyansin)
    alpha = np.where(bgs, np.clip((alpha - 0.08) / 0.55, 0, 1), np.clip((alpha - 0.25) / 0.65, 0, 1))
    contrast = (d * d).sum(2) > 10 ** 2                            # kumas ile disari rengi benzerse alfa guvenilmez -> maske
    soft = cv2.GaussianBlur(M.astype(np.float32), (0, 0), 1.0)
    alpha = np.where(contrast, np.minimum(alpha, cv2.dilate(M, ell(7)).astype(np.float32)), soft)
    band = (cv2.dilate(M, ell(5)) > 0) | ((cv2.dilate(M, ell(9)) > 0) & bgs)   # arka plana komsu kenarda 4 px (acik kenar seridi), digerinde 2 px
    band = np.where(cv2.dilate(tee.astype(np.uint8), ell(15)) > 0, cv2.dilate(M, ell(3)) > 0, band)   # ic tisort kenarinda 1 px: tasma/kose lekesi olmasin
    core = cv2.erode(M, ell(5))                                    # GrabCut kenari ~1 px dogru: 2 px iceride tam boya
    alpha = np.where(core > 0, 1.0, np.where(band & ~notshirt, alpha, 0.0))
    # sac telleri arasindan gorunen kumas (SegFormer: sac, ust giysi ~0.15-0.3): ikili maske yamali durur; piksel basina
    # kumas (F2) ile yerel sac rengi (H) arasindaki konumdan yumusak alfa
    hz = (cv2.GaussianBlur(((p["hair"] > 0.5) & (p["upper"] > 0.1)).astype(np.float32), (0, 0), 2) > 0.5) & (near == 0)
    if hz.any():
        hp = ((p["hair"] > 0.5) & (cd > 12)).astype(np.float32)     # saf sac pikselleri
        F2, H = nconv(img, inner, 25), nconv(img, hp, 6)
        dh = F2 - H
        ah = ((img.astype(np.float32) - H) * dh).sum(2) / ((dh * dh).sum(2) + 1e-3)
        r2 = np.linalg.norm(img.astype(np.float32) - (H + np.clip(ah, 0, 1)[..., None] * dh), axis=2)
        ok = (cv2.GaussianBlur(hp, (0, 0), 6) > 0.05) & (r2 < 25) & ((dh * dh).sum(2) > 15 ** 2)
        hz = cv2.GaussianBlur((hz & ok).astype(np.float32), (0, 0), 1.5)  # bolge kenari yumusak
        alpha = alpha * (1 - hz) + np.clip((ah - 0.2) / 0.6, 0, 1) * ok * hz
        F = np.where((hz > 0)[..., None], F2, F)
    alpha = cv2.GaussianBlur(alpha.astype(np.float32), (0, 0), 0.6)
    btn = dugme_maske(img, dugme_pts, cv2.erode(M, ell(3)) > 0)
    if duzelt is not None and duzelt.shape == alpha.shape:         # maske_duzelt.py firca duzeltmesi: 1 = boyansin, 2 = boyanmasin
        ek, cik = (duzelt == 1), (duzelt == 2)
        ek_s, cik_s = (cv2.GaussianBlur(x.astype(np.float32), (0, 0), 0.8) for x in (ek, cik))
        alpha = np.maximum(alpha * (1 - cik_s), ek_s)
        core = np.where(cik, 0, np.where(ek, 1, core)).astype(core.dtype)
        M = np.where(cik, 0, np.where(ek, 1, M)).astype(M.dtype)
        btn = btn * (1 - ek_s)
    return dict(M=M, alpha=alpha, core=core, F=F, btn=btn, ref=sm.ref_lab)


def boya(img, h, target_lab):
    """Renge ozel kisim (hizli): hazirla() ciktisiyla gomlegi target_lab rengine boyar."""
    alpha, core, F = h["alpha"], h["core"], h["F"]
    Ls, As, Bs = h["ref"]; Lt, At, Bt = target_lab
    def rc(bgr):
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        L2 = np.clip(Lt * np.minimum(lab[..., 0] / max(Ls, 1.0), 1.25), 0, 255)
        return cv2.cvtColor(np.dstack([L2, At + (lab[..., 1] - As) * 0.35, Bt + (lab[..., 2] - Bs) * 0.35]).clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)
    Fu = np.clip(F, 0, 255).astype(np.uint8)
    full = rc(img)
    edge = img.astype(np.float32) + alpha[..., None] * (rc(Fu) - Fu.astype(np.float32))   # kenar: p + a*(F'-F)
    t = cv2.GaussianBlur(core.astype(np.float32), (0, 0), 1.0)[..., None]   # maske ici: carpimsal boya (acik kenar grilesmesin)
    res = t * full + (1 - t) * edge

    bf = h["btn"][..., None]
    res = res * (1 - bf) + img.astype(np.float32) * bf              # dugme: orijinal
    return res.clip(0, 255).astype(np.uint8)


if __name__ == "__main__":
    from dugme_isaretle import isaretle
    seg = Segmenter(R / "modeller" / "segformer_b2_clothes.onnx")
    out = R / "cikti_boya"; out.mkdir(exist_ok=True)
    flt = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    renkler = [(gp.stem, extract_shirt_color(yukle(gp), seg)["normalized"]) for gp in sorted((R / "girdi" / "gomlek").glob("*.jpg"))]
    yeni = []
    for mp in sorted((R / "girdi" / "manken").glob("*.jpg")):
        if flt not in mp.name: continue
        dugme = json.loads(JSON.read_text()) if JSON.exists() else {}
        if "--isaretle" in sys.argv or mp.stem not in dugme:
            print(f"{mp.name}: acilan pencerede dugmeleri isaretleyin (dugme yoksa direkt Enter)")
            if not isaretle(mp) and mp.stem not in dugme:
                print(f"{mp.name}: isaretlenmedi, atlandi"); continue
            dugme = json.loads(JSON.read_text())
        m = yukle(mp); h = hazirla(m, analyze_model(m, seg), seg, dugme[mp.stem], yukle_duzelt(mp.stem))
        v = m.copy(); M = h["M"] > 0; v[M] = (v[M] * .5 + np.array([0, 0, 255]) * .5).astype(np.uint8); v[h["btn"] > 0.5] = (0, 255, 0)
        wr(out / f"_maske_{mp.stem}.jpg", v)                       # kontrol: kirmizi = boyanan, yesil = dugme
        for gs, c in renkler:
            f = out / f"{mp.stem}_{gs}.jpg"; wr(f, boya(m, h, c["lab"])); yeni.append(f); print(f.name, c["hex"])
    # Instagram: 1080 genislik, Lanczos buyutme
    if "--ig" in sys.argv:
        dst = R / "instagram"; dst.mkdir(parents=True, exist_ok=True)
        for f in yeni:
            im = yukle(f); im = cv2.resize(im, (1080, round(im.shape[0] * 1080 / im.shape[1])), interpolation=cv2.INTER_LANCZOS4)
            wr(dst / re.sub(r"IMG-\d{8}-", "", f.name), im, 97)
        print("Instagram:", dst)
