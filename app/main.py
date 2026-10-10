"""LAQ - gomlek yeniden boyama web uygulamasi (FastAPI). Calistirma: ./run.sh"""
from __future__ import annotations

import hashlib
import hmac
import logging
import sys
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config

sys.path.insert(0, str(config.KOK / "kod"))     # motor: kod/boya.py, kod/seg/, kod/dugme_isaretle.py
from . import isler  # noqa: E402
from .isler import Hata  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
isci = isler.Isci()
COOKIE = "laq_oturum"
_SIR = hashlib.sha256(("laq-cookie:" + config.PAROLA).encode()).digest()
_basarisiz: dict[str, list[float]] = defaultdict(list)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(config.PAROLA) < 8:
        raise SystemExit("LAQ_PAROLA ortam değişkeni (en az 8 karakter) tanımlı değil.")
    if not config.MODEL.exists():
        raise SystemExit(f"Model yok: {config.MODEL}  ->  python scripts/model_indir.py")
    isler.kok()
    isci.baslat()
    threading.Thread(target=isler.temizlik_dongusu, daemon=True).start()
    yield


app = FastAPI(title="LAQ", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(Hata)
async def hata_isle(_: Request, e: Hata):
    return JSONResponse({"hata": e.mesaj}, status_code=e.kod)


@app.middleware("http")
async def guvenlik(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in config.ON_YUZ and origin.split("://", 1)[-1] != request.headers.get("host"):
            return JSONResponse({"hata": "Geçersiz istek kaynağı."}, status_code=403)
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > config.MAX_DOSYA * max(config.MAX_MANKEN, config.MAX_GOMLEK) + (1 << 20):
            return JSONResponse({"hata": "İstek çok büyük."}, status_code=413)
    r = await call_next(request)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Referrer-Policy", "same-origin")
    return r


# CORS en dista olmali (hata yanitlarina da baslik eklensin): son eklenen = en dis katman
app.add_middleware(CORSMiddleware, allow_origins=config.ON_YUZ, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"], max_age=600)


# ----------------------------------------------------------------------------- oturum
def _imza(exp: str) -> str:
    return hmac.new(_SIR, exp.encode(), hashlib.sha256).hexdigest()[:40]


def oturum(request: Request):
    c = request.cookies.get(COOKIE, "")
    exp, _, imza = c.partition(".")
    if not (exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(imza, _imza(exp))):
        raise Hata(401, "Giriş gerekli.")


def ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


class Giris(BaseModel):
    parola: str


@app.post("/api/giris")
async def giris(g: Giris, request: Request):
    a = ip(request)
    simdi = time.time()
    _basarisiz[a] = [t for t in _basarisiz[a] if simdi - t < 600]
    if len(_basarisiz[a]) >= 8:
        raise Hata(429, "Çok fazla hatalı deneme. 10 dakika sonra tekrar deneyin.")
    if not hmac.compare_digest(hashlib.sha256(g.parola.encode()).digest(), hashlib.sha256(config.PAROLA.encode()).digest()):
        _basarisiz[a].append(simdi)
        raise Hata(401, "Parola yanlış.")
    exp = str(int(simdi + config.OTURUM_GUN * 86400))
    r = JSONResponse({"tamam": True})
    r.set_cookie(COOKIE, f"{exp}.{_imza(exp)}", max_age=config.OTURUM_GUN * 86400, httponly=True,
                 secure=request.url.scheme == "https", samesite="lax")
    return r


@app.post("/api/cikis")
async def cikis():
    r = JSONResponse({"tamam": True})
    r.delete_cookie(COOKIE)
    return r


@app.get("/api/ben", dependencies=[Depends(oturum)])
async def ben():
    return {"tamam": True, "limit": {"manken": config.MAX_MANKEN, "gomlek": config.MAX_GOMLEK,
                                     "dosya_mb": config.MAX_DOSYA // 1048576, "sakla_gun": config.SAKLA_GUN}}


# ----------------------------------------------------------------------------- isler
def _gorunum(d: dict) -> dict:
    return {"id": d["id"], "manken": d["manken"], "gomlek": [{k: v for k, v in g.items() if k != "lab"} for g in d["gomlek"]],
            "uret": d["uret"], "kuyruk": isler.KUYRUK.qsize()}


@app.post("/api/is", dependencies=[Depends(oturum)])
async def is_olustur():
    return _gorunum(await run_in_threadpool(isler.yeni_is))


@app.get("/api/is/{iid}", dependencies=[Depends(oturum)])
async def is_durum(iid: str):
    d = isler.yukle_durum(iid)
    isler.dokun(iid)
    return _gorunum(d)


@app.delete("/api/is/{iid}", dependencies=[Depends(oturum)])
async def is_sil(iid: str):
    isler.yukle_durum(iid)
    isler.sil_is(iid)
    return {"tamam": True}


async def _yukle(iid: str, tur: str, dosyalar: list[UploadFile]):
    veri = []
    for f in dosyalar:
        b = await f.read(config.MAX_DOSYA + 1)
        veri.append((f.filename or "foto", b))
    await run_in_threadpool(isler.foto_ekle, iid, tur, veri)
    return _gorunum(isler.yukle_durum(iid))


@app.post("/api/is/{iid}/manken", dependencies=[Depends(oturum)])
async def manken_yukle(iid: str, dosyalar: list[UploadFile] = File(...)):
    return await _yukle(iid, "manken", dosyalar)


@app.post("/api/is/{iid}/gomlek", dependencies=[Depends(oturum)])
async def gomlek_yukle(iid: str, dosyalar: list[UploadFile] = File(...)):
    return await _yukle(iid, "gomlek", dosyalar)


@app.delete("/api/is/{iid}/{tur}/{kid}", dependencies=[Depends(oturum)])
async def foto_sil(iid: str, tur: str, kid: str):
    if tur not in ("manken", "gomlek") or not isler.KALEM_RE.match(kid):
        raise Hata(404, "Bulunamadı.")
    await run_in_threadpool(isler.foto_sil, iid, tur, kid)
    return _gorunum(isler.yukle_durum(iid))


def _dosya(iid: str, tur: str, kid: str, ek: str, tip: str, cache: str = "private, max-age=3600"):
    if tur not in ("m", "g") or not isler.KALEM_RE.match(kid):
        raise Hata(404, "Bulunamadı.")
    yol = isler.dizin(iid) / tur / f"{kid}.{ek}"
    if not yol.exists():
        raise Hata(404, "Henüz hazır değil.")
    return FileResponse(yol, media_type=tip, headers={"Cache-Control": cache})


@app.get("/api/is/{iid}/manken/{kid}/temel.jpg", dependencies=[Depends(oturum)])
async def temel(iid: str, kid: str):
    return _dosya(iid, "m", kid, "temel.jpg", "image/jpeg")


@app.get("/api/is/{iid}/manken/{kid}/tarali.jpg", dependencies=[Depends(oturum)])
async def tarali(iid: str, kid: str, v: int = 0):
    return _dosya(iid, "m", kid, "tarali.jpg", "image/jpeg")


@app.get("/api/is/{iid}/gomlek/{kid}/temel.jpg", dependencies=[Depends(oturum)])
async def gomlek_temel(iid: str, kid: str):
    return _dosya(iid, "g", kid, "temel.jpg", "image/jpeg")


@app.get("/api/is/{iid}/manken/{kid}/duzeltme.bin", dependencies=[Depends(oturum)])
async def duzeltme_al(iid: str, kid: str):
    d = isler.yukle_durum(iid)
    m = isler.bul(d, "manken", kid)
    yol = isler.dizin(iid) / "m" / f"{kid}.duzeltme.png"
    a = cv2.imdecode(np.fromfile(str(yol), np.uint8), cv2.IMREAD_GRAYSCALE) if yol.exists() else np.zeros((m["h"], m["w"]), np.uint8)
    return Response(a.tobytes(), media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


@app.put("/api/is/{iid}/manken/{kid}/duzeltme", dependencies=[Depends(oturum)])
async def duzeltme_koy(iid: str, kid: str, duzelt: UploadFile = File(...), dugme: str = Form("[]")):
    if not isler.KALEM_RE.match(kid):
        raise Hata(404, "Bulunamadı.")
    ham = await duzelt.read(8_000_000)
    await run_in_threadpool(isler.duzeltme_kaydet, iid, kid, ham, dugme)
    return _gorunum(isler.yukle_durum(iid))


@app.post("/api/is/{iid}/uret", dependencies=[Depends(oturum)])
async def uret(iid: str):
    await run_in_threadpool(isler.uret_baslat, iid)
    return _gorunum(isler.yukle_durum(iid))


@app.get("/api/is/{iid}/zip", dependencies=[Depends(oturum)])
async def zip_indir(iid: str):
    d = isler.yukle_durum(iid)
    yol = isler.dizin(iid) / "sonuc.zip"
    if not d["uret"]["zip"] or not yol.exists():
        raise Hata(404, "ZIP henüz hazır değil.")
    return FileResponse(yol, media_type="application/zip", filename="laq-sonuc.zip")


# arayuz de bu sunucudan acilabilir (GitHub Pages kullanilmazsa); API yollari yukarida oncelikli
app.mount("/", StaticFiles(directory=config.KOK / "static", html=True), name="static")
