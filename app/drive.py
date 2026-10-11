"""LAQ drive: fotograflarin yuklenip secildigi, sonuclarin geri yazildigi ayri klasor.

Kok: config.DRIVE (ustune cikilamaz). Yalnizca fotograf (jpg/png/webp) kabul edilir.
Tum yollar kokten gorelidir. Erisim: oturum cookie'si (main.py'de bagimlilik olarak eklenir).
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import secrets
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, ImageOps

from . import config
from .isler import Hata

UZANTILAR = {".jpg", ".jpeg", ".png", ".webp"}
GECICI = ".yukleniyor-"
KOK = config.DRIVE
KUCUK = config.VERI / "kucuk"
VARSAYILAN = ("Mankenler", "Gömlekler", "Sonuçlar")
AD_YASAK = re.compile(r'[\x00-\x1f/\\]')

router = APIRouter(prefix="/api/drive")


def hazirla():
    KOK.mkdir(parents=True, exist_ok=True)
    KUCUK.mkdir(parents=True, exist_ok=True)
    for ad in VARSAYILAN:
        (KOK / ad).mkdir(exist_ok=True)
    for f in KOK.rglob(GECICI + "*"):   # yarim kalan yuklemeler
        f.unlink(missing_ok=True)


def guvenli(yol: str, link: bool = False) -> Path:
    """KOK icinde kalir. link=True: son bilesen cozulmez (sil/ad/tasi sembolik baglantiyi izlemesin)."""
    temiz = os.path.normpath((yol or "").strip("/"))
    if temiz in (".", ""):
        return KOK
    if temiz.split(os.sep)[0] == "..":
        raise Hata(400, "Geçersiz yol.")
    ham = KOK / temiz
    if link:
        ust = ham.parent.resolve()
        if ust != KOK and KOK not in ust.parents:
            raise Hata(400, "Geçersiz yol.")
        return ust / ham.name
    tam = ham.resolve()
    if tam != KOK and KOK not in tam.parents:
        raise Hata(400, "Geçersiz yol.")
    return tam


def goreli(p: Path) -> str:
    try:
        r = str(p.relative_to(KOK))
    except ValueError:
        return ""
    return "" if r == "." else r


def resim_mi(ad: str) -> bool:
    return Path(ad).suffix.lower() in UZANTILAR


def ad_dogrula(ad: str) -> str:
    ad = (ad or "").strip()
    if not ad or ad in (".", "..") or AD_YASAK.search(ad) or ad.startswith(GECICI) or len(ad) > 120:
        raise Hata(400, "Geçersiz ad.")
    return ad


def benzersiz(hedef: Path) -> Path:
    """Ayni ad varsa 'ad (2).jpg' diye devam eder."""
    if not os.path.lexists(hedef):
        return hedef
    n = 2
    while os.path.lexists(hedef.with_name(f"{hedef.stem} ({n}){hedef.suffix}")):
        n += 1
    return hedef.with_name(f"{hedef.stem} ({n}){hedef.suffix}")


def resimler(yollar: list[str]) -> list[Path]:
    """Secilen dosyalar + secilen klasorlerin icindeki (ust duzey) fotograflar; sirali, tekrarsiz."""
    out, gorulen = [], set()
    for y in yollar:
        p = guvenli(y)
        if p.is_dir():
            adaylar = sorted((e for e in p.iterdir() if e.is_file() and resim_mi(e.name) and not e.name.startswith(".")),
                             key=lambda e: e.name.lower())
        elif p.is_file() and resim_mi(p.name):
            adaylar = [p]
        else:
            raise Hata(404, f"Bulunamadı: {y}")
        for e in adaylar:
            if e not in gorulen:
                gorulen.add(e)
                out.append(e)
    return out


def sonuc_klasoru(proje: str) -> Path:
    """Sonuçlar/<proje adı>/<tarih saat>/ ; ayni ad varsa numaralanir."""
    ad = AD_YASAK.sub("-", proje).strip(" .")[:80] or "Proje"
    ana = KOK / "Sonuçlar" / ad
    ana.mkdir(parents=True, exist_ok=True)
    zaman = time.strftime("%Y-%m-%d %H.%M")
    p, n = ana / zaman, 2
    while p.exists():
        p, n = ana / f"{zaman} ({n})", n + 1
    p.mkdir()
    return p


# ----------------------------------------------------------------------------- okuma
@router.get("/liste")
def liste(yol: str = ""):
    d = guvenli(yol)
    if not d.is_dir():
        raise Hata(404, "Klasör yok.")
    klasorler, dosyalar = [], []
    for e in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if e.name.startswith("."):
            continue
        if e.is_dir():
            klasorler.append({"ad": e.name, "yol": goreli(e), "adet": sum(1 for x in e.iterdir() if not x.name.startswith("."))})
        elif resim_mi(e.name):
            st = e.stat()
            dosyalar.append({"ad": e.name, "yol": goreli(e), "boyut": st.st_size, "zaman": int(st.st_mtime)})
    return {"yol": goreli(d), "ust": goreli(d.parent) if d != KOK else None, "klasorler": klasorler, "dosyalar": dosyalar,
            "bos_gb": round(shutil.disk_usage(KOK).free / 1e9, 1)}


@router.get("/klasorler")
def klasorler():
    """Tasima penceresi icin tum klasorler (kok = '')."""
    out = [""]
    for p in sorted(KOK.rglob("*"), key=lambda x: str(x).lower()):
        if p.is_dir() and not any(b.startswith(".") for b in p.relative_to(KOK).parts):
            out.append(goreli(p))
            if len(out) >= 1000:
                break
    return {"klasorler": out}


def _kucuk_uret(p: Path, cikis: Path):
    tmp = cikis.with_suffix(f".{secrets.token_hex(4)}.tmp")
    try:
        with Image.open(p) as im:
            im.draft("RGB", (640, 640))          # JPEG'i kucuk boyda coz: cok daha hizli
            im = ImageOps.exif_transpose(im)
            im.thumbnail((320, 320))
            im.convert("RGB").save(tmp, format="JPEG", quality=80)
        tmp.replace(cikis)
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/kucuk")
async def kucuk(yol: str):
    p = guvenli(yol)
    if not p.is_file() or not resim_mi(p.name):
        raise Hata(404, "Dosya yok.")
    st = p.stat()
    cikis = KUCUK / (hashlib.sha1(f"{p}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest() + ".jpg")
    if not cikis.exists():
        try:
            await run_in_threadpool(_kucuk_uret, p, cikis)
        except Exception:
            raise Hata(404, "Önizleme üretilemedi.")
    return FileResponse(cikis, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/goruntu")
def goruntu(yol: str):
    p = guvenli(yol)
    if not p.is_file() or not resim_mi(p.name):
        raise Hata(404, "Dosya yok.")
    return FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/indir")
def indir(yol: str):
    p = guvenli(yol)
    if not p.is_file():
        raise Hata(404, "Dosya yok.")
    return FileResponse(p, filename=p.name)


class _Havuz(io.RawIOBase):
    def __init__(self):
        self.tampon = bytearray()

    def writable(self):
        return True

    def write(self, b):
        self.tampon += b
        return len(b)

    def al(self) -> bytes:
        c, self.tampon = bytes(self.tampon), bytearray()
        return c


@router.get("/zip")
def zip_indir(yol: list[str] = Query()):
    kokler = [guvenli(y) for y in yol]
    if any(k == KOK or not k.exists() for k in kokler):
        raise Hata(404, "Bulunamadı.")
    dosyalar = []
    for k in kokler:
        for f in ([k] if k.is_file() else sorted(x for x in k.rglob("*") if x.is_file())):
            if not f.name.startswith("."):
                guvenli(goreli(f))                       # sembolik baglanti kacagina karsi
                dosyalar.append((f, str(f.relative_to(k.parent))))

    def akis():
        havuz = _Havuz()
        with zipfile.ZipFile(havuz, "w", zipfile.ZIP_STORED) as z:     # fotograflar zaten sikisik
            for f, ad in dosyalar:
                with f.open("rb") as src, z.open(ad, "w", force_zip64=True) as dst:
                    while parca := src.read(1 << 20):
                        dst.write(parca)
                        yield havuz.al()
        yield havuz.al()

    ad = f"{kokler[0].name}.zip" if len(kokler) == 1 else f"laq-drive-{time.strftime('%Y-%m-%d')}.zip"
    return StreamingResponse(akis(), media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(ad)}"})


# ----------------------------------------------------------------------------- yazma
@router.put("/dosya")
async def yukle(request: Request, yol: str):
    """Govde = dosya icerigi. yol = klasor/ad.jpg ; ayni ad varsa 'ad (2).jpg' olur."""
    hedef = guvenli(yol)
    ad_dogrula(hedef.name)
    if not resim_mi(hedef.name):
        raise Hata(415, "Yalnızca fotoğraf (jpg, png, webp) yüklenebilir.")
    if not hedef.parent.is_dir() or hedef == KOK:
        raise Hata(404, "Klasör yok.")
    if shutil.disk_usage(KOK).free < config.DRIVE_BOS_MIN_GB * 1e9:
        raise Hata(507, "Sunucuda yeterli disk alanı yok.")
    tmp = hedef.parent / f"{GECICI}{secrets.token_hex(8)}"
    boyut = 0
    try:
        with tmp.open("wb") as f:
            async for parca in request.stream():
                boyut += len(parca)
                if boyut > config.DRIVE_MAX_DOSYA:
                    raise Hata(413, f"Dosya {config.DRIVE_MAX_DOSYA // 1048576} MB sınırını aşıyor.")
                f.write(parca)
        try:
            with Image.open(tmp) as im:
                if im.format not in ("JPEG", "PNG", "WEBP") or im.size[0] * im.size[1] > config.MAX_PIKSEL:
                    raise ValueError
        except Exception:
            raise Hata(422, "Geçerli bir fotoğraf değil (veya çözünürlük çok büyük).")
        son = benzersiz(hedef)
        tmp.rename(son)
    finally:
        tmp.unlink(missing_ok=True)
    return {"tamam": True, "yol": goreli(son)}


@router.post("/klasor")
def klasor(yol: str):
    d = guvenli(yol)
    ad_dogrula(d.name)
    if d == KOK or d.exists():
        raise Hata(409, "Bu isimde bir öğe zaten var.")
    if not d.parent.is_dir():
        raise Hata(404, "Üst klasör yok.")
    d.mkdir()
    return {"tamam": True, "yol": goreli(d)}


@router.post("/ad")
def yeniden_adlandir(yol: str, ad: str):
    kaynak = guvenli(yol, link=True)
    ad = ad_dogrula(ad)
    if kaynak == KOK or not os.path.lexists(kaynak):
        raise Hata(404, "Bulunamadı.")
    if kaynak.is_file() and not resim_mi(ad):
        raise Hata(400, "Uzantı jpg, png veya webp olmalı.")
    hedef = kaynak.with_name(ad)
    if os.path.lexists(hedef):
        raise Hata(409, "Bu isimde bir öğe zaten var.")
    kaynak.rename(hedef)
    return {"tamam": True, "yol": goreli(hedef)}


@router.post("/tasi")
def tasi(yol: list[str] = Query(), hedef: str = ""):
    h = guvenli(hedef)
    if not h.is_dir():
        raise Hata(404, "Hedef klasör yok.")
    for y in yol:
        k = guvenli(y, link=True)
        if k == KOK or not os.path.lexists(k):
            raise Hata(404, "Bulunamadı.")
        if k == h or k in h.parents:
            raise Hata(400, "Klasör kendi içine taşınamaz.")
        if k.parent == h:
            continue
        if os.path.lexists(h / k.name):
            raise Hata(409, f'"{k.name}" hedefte zaten var.')
        k.rename(h / k.name)
    return {"tamam": True}


@router.post("/sil")
def sil(yol: list[str] = Query()):
    for y in yol:
        p = guvenli(y, link=True)
        if p == KOK or not os.path.lexists(p):
            raise Hata(404, "Bulunamadı.")
        if p.parent == KOK and p.name in VARSAYILAN:
            raise Hata(400, f'"{p.name}" klasörü silinemez.')
        p.unlink() if p.is_symlink() or not p.is_dir() else shutil.rmtree(p)
    return {"tamam": True}
