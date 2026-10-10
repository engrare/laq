"""Ayarlar: hepsi ortam degiskenlerinden (.env). LAQ_PAROLA zorunlu."""
import os
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
PAROLA = os.environ.get("LAQ_PAROLA", "")
VERI = Path(os.environ.get("LAQ_VERI", KOK / "data")).resolve()
SAKLA_GUN = float(os.environ.get("LAQ_SAKLA_GUN", "7"))
MAX_DOSYA = int(float(os.environ.get("LAQ_MAX_DOSYA_MB", "15")) * 1024 * 1024)
MAX_MANKEN = int(os.environ.get("LAQ_MAX_MANKEN", "12"))
MAX_GOMLEK = int(os.environ.get("LAQ_MAX_GOMLEK", "12"))
MAX_PIKSEL = 60_000_000
MAX_DUGME = 200
OTURUM_GUN = 30
MODEL = KOK / "modeller" / "segformer_b2_clothes.onnx"
CIKTI_GENISLIK = 1080
CIKTI_KALITE = 97
