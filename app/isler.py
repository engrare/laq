"""Is (job) deposu + tek iscili kuyruk. Motor (kod/) yalnizca isci thread'inde calisir."""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import secrets
import shutil
import threading
import time
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import config

log = logging.getLogger("laq")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
KALEM_RE = re.compile(r"^[mg]\d{1,3}$")
KILIT = threading.RLock()
KUYRUK: "queue.Queue[tuple]" = queue.Queue()
UZANTI = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


class Hata(Exception):
    def __init__(self, kod: int, mesaj: str):
        super().__init__(mesaj)
        self.kod, self.mesaj = kod, mesaj


# ----------------------------------------------------------------------------- depo
def kok() -> Path:
    p = config.VERI / "isler"
    p.mkdir(parents=True, exist_ok=True)
    return p


def dizin(iid: str) -> Path:
    if not ID_RE.match(iid):
        raise Hata(404, "Bulunamadı.")
    return kok() / iid


def yukle_durum(iid: str) -> dict:
    f = dizin(iid) / "durum.json"
    with KILIT:
        if not f.exists():
            raise Hata(404, "İş bulunamadı (süresi dolmuş olabilir).")
        return json.loads(f.read_text())


def kaydet_durum(d: dict):
    f = dizin(d["id"]) / "durum.json"
    tmp = f.with_suffix(".tmp")
    with KILIT:
        tmp.write_text(json.dumps(d, ensure_ascii=False))
        tmp.replace(f)


def yeni_is() -> dict:
    iid = secrets.token_urlsafe(12)
    d = {"id": iid, "olusturma": time.time(), "manken": [], "gomlek": [], "sayac": {"m": 0, "g": 0},
         "uret": {"durum": "yok", "adim": 0, "toplam": 0, "mesaj": "", "zip": False}}
    for alt in ("m", "g", "out"):
        (dizin(iid) / alt).mkdir(parents=True, exist_ok=True)
    kaydet_durum(d)
    return d


def sil_is(iid: str):
    with KILIT:
        shutil.rmtree(dizin(iid), ignore_errors=True)


def dokun(iid: str):
    f = dizin(iid) / "durum.json"
    try:
        if time.time() - f.stat().st_mtime > 3600:
            os.utime(f)
    except OSError:
        pass


def bul(d: dict, tur: str, kid: str) -> dict:
    for k in d[tur]:
        if k["id"] == kid:
            return k
    raise Hata(404, "Bulunamadı.")


def guvenli_ad(ad: str, kullanilan: set) -> str:
    stem = Path(ad or "foto").stem
    stem = re.sub(r"^IMG-\d{8}-", "", stem)
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")[:40] or "foto"
    ad, n = stem, 2
    while ad.lower() in kullanilan:
        ad, n = f"{stem}-{n}", n + 1
    return ad


# ----------------------------------------------------------------------------- yukleme
def foto_ekle(iid: str, tur: str, dosyalar: list[tuple[str, bytes]]) -> list[dict]:
    """tur: 'manken' | 'gomlek'. dosyalar: (orijinal_ad, bayt). Dogrular, kaydeder, kuyruga atar."""
    from dugme_isaretle import yukle  # motor (kod/)
    kisa, limit = ("m", config.MAX_MANKEN) if tur == "manken" else ("g", config.MAX_GOMLEK)
    eklenen = []
    with KILIT:
        d = yukle_durum(iid)
        if d["uret"]["durum"] in ("kuyrukta", "calisiyor"):
            raise Hata(409, "Üretim sürerken fotoğraf eklenemez.")
        if len(d[tur]) + len(dosyalar) > limit:
            raise Hata(413, f"En fazla {limit} {tur} fotoğrafı yüklenebilir.")
        kullanilan = {k["ad"].lower() for k in d[tur]}
        for ad, veri in dosyalar:
            if len(veri) > config.MAX_DOSYA:
                raise Hata(413, f"{ad}: dosya {config.MAX_DOSYA // 1048576} MB sınırını aşıyor.")
            try:
                im = Image.open(BytesIO(veri))
                fmt, (w, h) = im.format, im.size
            except Exception:
                raise Hata(422, f"{ad}: geçerli bir fotoğraf değil (JPEG/PNG/WEBP).")
            if fmt not in UZANTI or w * h > config.MAX_PIKSEL:
                raise Hata(422, f"{ad}: desteklenmeyen biçim veya çok büyük çözünürlük.")
            d["sayac"][kisa] += 1
            kid = f"{kisa}{d['sayac'][kisa]}"
            yol = dizin(iid) / kisa / f"{kid}{UZANTI[fmt]}"
            yol.write_bytes(veri)
            try:
                img = yukle(yol)
            except Exception:
                yol.unlink(missing_ok=True)
                raise Hata(422, f"{ad}: fotoğraf okunamadı.")
            cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tofile(str(dizin(iid) / kisa / f"{kid}.temel.jpg"))
            k = {"id": kid, "ad": guvenli_ad(ad, kullanilan), "dosya": yol.name, "w": img.shape[1], "h": img.shape[0],
                 "durum": "bekliyor", "hata": None, "istek": 1, "v": 0}
            kullanilan.add(k["ad"].lower())
            if tur == "manken":
                k.update(dugme=[], duzeltme=False)
            else:
                k.update(hex=None, lab=None)
            d[tur].append(k)
            eklenen.append(k)
        kaydet_durum(d)
    for k in eklenen:
        KUYRUK.put(("hazirla" if tur == "manken" else "renk", iid, k["id"]))
    return eklenen


def foto_sil(iid: str, tur: str, kid: str):
    kisa = "m" if tur == "manken" else "g"
    with KILIT:
        d = yukle_durum(iid)
        if d["uret"]["durum"] in ("kuyrukta", "calisiyor"):
            raise Hata(409, "Üretim sürerken silinemez.")
        k = bul(d, tur, kid)
        d[tur].remove(k)
        d["uret"].update(zip=False)
        for f in (dizin(iid) / kisa).glob(f"{kid}.*"):
            f.unlink(missing_ok=True)
        kaydet_durum(d)


def duzeltme_kaydet(iid: str, mid: str, ham: bytes, dugme_json: str):
    """Tarayicidan gelen duzeltme (w*h bayt, 0/1/2) + dugme listesi. maske_duzelt.py ile ayni PNG biciminde saklanir."""
    with KILIT:
        d = yukle_durum(iid)
        if d["uret"]["durum"] in ("kuyrukta", "calisiyor"):
            raise Hata(409, "Üretim sürerken düzenlenemez.")
        m = bul(d, "manken", mid)
        if len(ham) != m["w"] * m["h"]:
            raise Hata(422, f"Düzeltme boyutu hatalı: {m['w']}x{m['h']} bekleniyordu.")
        try:
            dg = json.loads(dugme_json or "[]")
            temiz = []
            for p in dg:
                x, y, r = (int(p[0]), int(p[1]), int(p[2]))
                tip = p[3] if len(p) > 3 else ("c" if r < 6 else "k")
                if tip not in ("k", "c") or not (0 <= x < m["w"] and 0 <= y < m["h"] and 1 <= r <= 80):
                    raise ValueError
                temiz.append([x, y, r, tip])
            if len(temiz) > config.MAX_DUGME:
                raise ValueError
        except Exception:
            raise Hata(422, "Düğme listesi geçersiz.")
        a = np.frombuffer(ham, np.uint8).reshape(m["h"], m["w"])
        a = np.where(a > 2, 0, a).astype(np.uint8)
        yol = dizin(iid) / "m" / f"{mid}.duzeltme.png"
        if a.any():
            cv2.imencode(".png", a)[1].tofile(str(yol))
        else:
            yol.unlink(missing_ok=True)
        m.update(dugme=temiz, duzeltme=bool(a.any()), durum="bekliyor", hata=None, istek=m["istek"] + 1)
        d["uret"].update(zip=False)
        kaydet_durum(d)
    KUYRUK.put(("hazirla", iid, mid))


def uret_baslat(iid: str):
    with KILIT:
        d = yukle_durum(iid)
        if not d["manken"] or not d["gomlek"]:
            raise Hata(422, "En az bir manken ve bir gömlek fotoğrafı gerekli.")
        if d["uret"]["durum"] in ("kuyrukta", "calisiyor"):
            raise Hata(409, "Üretim zaten sürüyor.")
        d["uret"] = {"durum": "kuyrukta", "adim": 0, "toplam": 0, "mesaj": "Sırada…", "zip": False}
        kaydet_durum(d)
    KUYRUK.put(("uret", iid, ""))


# ----------------------------------------------------------------------------- isci
class Isci:
    def __init__(self):
        self.seg = None
        self.th = threading.Thread(target=self.dongu, name="isci", daemon=True)

    def baslat(self):
        self.th.start()
        # cokme sonrasi yarim kalanlari yeniden kuyruga al
        for f in kok().glob("*/durum.json"):
            try:
                d = json.loads(f.read_text())
            except Exception:
                continue
            for tur, gorev in (("manken", "hazirla"), ("gomlek", "renk")):
                for k in d[tur]:
                    if k["durum"] in ("bekliyor", "hesaplaniyor"):
                        k["durum"] = "bekliyor"
                        KUYRUK.put((gorev, d["id"], k["id"]))
            if d["uret"]["durum"] in ("kuyrukta", "calisiyor"):
                d["uret"]["durum"] = "kuyrukta"
                KUYRUK.put(("uret", d["id"], ""))
            kaydet_durum(d)

    def motor(self):
        if self.seg is None:
            from seg.pipeline import Segmenter
            self.seg = Segmenter(config.MODEL, threads=4)
        return self.seg

    def dongu(self):
        while True:
            gorev, iid, kid = KUYRUK.get()
            try:
                if not (dizin(iid) / "durum.json").exists():
                    continue
                {"hazirla": self.hazirla, "renk": self.renk, "uret": self.uret}[gorev](iid, kid)
            except Exception as e:  # noqa: BLE001
                log.exception("gorev basarisiz: %s %s %s", gorev, iid, kid)
                self.hata(gorev, iid, kid, str(e))

    def hata(self, gorev, iid, kid, mesaj):
        with KILIT:
            try:
                d = yukle_durum(iid)
            except Hata:
                return
            if gorev == "uret":
                d["uret"].update(durum="hata", mesaj=f"Hata: {mesaj[:200]}")
            else:
                k = bul(d, "manken" if gorev == "hazirla" else "gomlek", kid)
                k.update(durum="hata", hata=mesaj[:200])
            kaydet_durum(d)

    # ---- manken: maske + dugme + duzeltme -> hazir.npz + tarali.jpg
    def hazirla(self, iid, mid):
        from boya import hazirla
        from dugme_isaretle import yukle
        from seg.pipeline import ShirtMask, analyze_model
        with KILIT:
            d = yukle_durum(iid)
            m = bul(d, "manken", mid)
            if m["durum"] != "bekliyor":
                return
            m["durum"] = "hesaplaniyor"
            istek, dugme = m["istek"], [tuple(p) for p in m["dugme"]]
            kaydet_durum(d)
        mk = dizin(iid) / "m"
        img = yukle(mk / m["dosya"])
        analiz = mk / f"{mid}.analiz.npz"
        if analiz.exists():
            sm = ShirtMask.load(analiz)
        else:
            sm = analyze_model(img, self.motor())
            sm.save(analiz)
        dz = mk / f"{mid}.duzeltme.png"
        duzelt = cv2.imdecode(np.fromfile(str(dz), np.uint8), cv2.IMREAD_GRAYSCALE) if dz.exists() else None
        h = hazirla(img, sm, self.motor(), dugme, duzelt)
        np.savez_compressed(mk / f"{mid}.hazir.npz", M=h["M"], alpha=h["alpha"].astype(np.float32), core=h["core"],
                            F=h["F"].astype(np.float32), btn=h["btn"].astype(np.float32), ref=np.array(h["ref"], np.float64))
        v = img.copy()
        M = h["M"] > 0
        v[M] = (v[M] * 0.5 + np.array([0, 0, 255]) * 0.5).astype(np.uint8)   # kirmizi = boyanacak
        v[h["btn"] > 0.5] = (0, 255, 0)                                      # yesil = korunan dugme
        cv2.imencode(".jpg", v, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tofile(str(mk / f"{mid}.tarali.jpg"))
        with KILIT:
            d = yukle_durum(iid)
            try:
                m = bul(d, "manken", mid)
            except Hata:
                return
            m.update(durum="hazir" if m["istek"] == istek else "bekliyor", hata=None, v=m["v"] + 1)
            kaydet_durum(d)

    # ---- gomlek: renk
    def renk(self, iid, gid):
        from dugme_isaretle import yukle
        from seg.pipeline import extract_shirt_color
        with KILIT:
            d = yukle_durum(iid)
            g = bul(d, "gomlek", gid)
            if g["durum"] != "bekliyor":
                return
            g["durum"] = "hesaplaniyor"
            kaydet_durum(d)
        r = extract_shirt_color(yukle(dizin(iid) / "g" / g["dosya"]), self.motor())["normalized"]
        with KILIT:
            d = yukle_durum(iid)
            try:
                g = bul(d, "gomlek", gid)
            except Hata:
                return
            g.update(durum="hazir", hata=None, hex=r["hex"], lab=[float(x) for x in r["lab"]])
            kaydet_durum(d)

    # ---- uretim: tum manken x renk -> out/*.jpg + sonuc.zip
    def uret(self, iid, _):
        from boya import boya
        from dugme_isaretle import yukle
        with KILIT:
            d = yukle_durum(iid)
            d["uret"].update(durum="calisiyor", mesaj="Hazırlanıyor…")
            kaydet_durum(d)

        def adim(mesaj, say=1):
            with KILIT:
                dd = yukle_durum(iid)
                dd["uret"]["adim"] += say
                dd["uret"]["mesaj"] = mesaj
                kaydet_durum(dd)

        # bekleyen maske/renk islerini burada sirayla bitir
        bekleyen = [("hazirla", k["id"]) for k in d["manken"] if k["durum"] != "hazir"] + \
                   [("renk", k["id"]) for k in d["gomlek"] if k["durum"] != "hazir"]
        with KILIT:
            d = yukle_durum(iid)
            d["uret"]["toplam"] = len(bekleyen) + len(d["manken"]) * len(d["gomlek"]) + 1
            kaydet_durum(d)
        for gorev, kid in bekleyen:
            tur = "manken" if gorev == "hazirla" else "gomlek"
            for _ in range(5):   # istek sayaci degisirse (kullanici duzenledi) tekrar
                with KILIT:
                    k = bul(yukle_durum(iid), tur, kid)
                if k["durum"] == "hazir":
                    break
                if k["durum"] in ("bekliyor", "hata"):
                    dd = yukle_durum(iid)
                    bul(dd, tur, kid)["durum"] = "bekliyor"
                    kaydet_durum(dd)
                    (self.hazirla if gorev == "hazirla" else self.renk)(iid, kid)
            adim(f"{'Maske' if tur == 'manken' else 'Renk'} hazırlandı: {k['ad']}")
        d = yukle_durum(iid)
        for k in d["manken"] + d["gomlek"]:
            if k["durum"] != "hazir":
                raise RuntimeError(f"{k['ad']} hazırlanamadı: {k.get('hata')}")
        out = dizin(iid) / "out"
        for f in out.glob("*"):
            f.unlink()
        for mk in d["manken"]:
            img = yukle(dizin(iid) / "m" / mk["dosya"])
            z = np.load(dizin(iid) / "m" / f"{mk['id']}.hazir.npz")
            h = {"M": z["M"], "alpha": z["alpha"], "core": z["core"], "F": z["F"], "btn": z["btn"], "ref": tuple(z["ref"])}
            for g in d["gomlek"]:
                sonuc = boya(img, h, tuple(g["lab"]))
                gen = config.CIKTI_GENISLIK
                sonuc = cv2.resize(sonuc, (gen, round(sonuc.shape[0] * gen / sonuc.shape[1])), interpolation=cv2.INTER_LANCZOS4)
                cv2.imencode(".jpg", sonuc, [cv2.IMWRITE_JPEG_QUALITY, config.CIKTI_KALITE])[1].tofile(str(out / f"{mk['ad']}_{g['ad']}.jpg"))
                adim(f"{mk['ad']} × {g['ad']}")
        zip_yol = dizin(iid) / "sonuc.zip"
        with zipfile.ZipFile(zip_yol.with_suffix(".tmp"), "w", zipfile.ZIP_STORED) as zf:
            for f in sorted(out.glob("*.jpg")):
                zf.write(f, f.name)
        zip_yol.with_suffix(".tmp").replace(zip_yol)
        with KILIT:
            dd = yukle_durum(iid)
            dd["uret"].update(durum="bitti", mesaj="Hazır", zip=True, adim=dd["uret"]["toplam"])
            kaydet_durum(dd)


# ----------------------------------------------------------------------------- temizlik
def temizlik_dongusu():
    while True:
        try:
            sinir = time.time() - config.SAKLA_GUN * 86400
            for p in kok().iterdir():
                f = p / "durum.json"
                if p.is_dir() and (not f.exists() or f.stat().st_mtime < sinir):
                    log.info("eski is siliniyor: %s", p.name)
                    shutil.rmtree(p, ignore_errors=True)
        except Exception:  # noqa: BLE001
            log.exception("temizlik hatasi")
        time.sleep(3600)
