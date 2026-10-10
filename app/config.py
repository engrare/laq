"""Ayarlar: hepsi ortam degiskenlerinden (.env). LAQ_PAROLA zorunlu."""
import os
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
PAROLA = os.environ.get("LAQ_PAROLA", "")
VERI = Path(os.environ.get("LAQ_VERI", KOK / "data")).resolve()
# Drive: ayri klasor (uygulama kodundan ve is verisinden bagimsiz); yuklenen fotograflar ve sonuclar burada kalir
DRIVE = Path(os.environ.get("LAQ_DRIVE", "/mnt/hdd/drive/laq-drive")).resolve()
DRIVE_MAX_DOSYA = int(float(os.environ.get("LAQ_DRIVE_MAX_DOSYA_MB", "40")) * 1024 * 1024)
DRIVE_BOS_MIN_GB = float(os.environ.get("LAQ_DRIVE_BOS_MIN_GB", "5"))
SAKLA_GUN = float(os.environ.get("LAQ_SAKLA_GUN", "7"))
MAX_DOSYA = int(float(os.environ.get("LAQ_MAX_DOSYA_MB", "15")) * 1024 * 1024)
MAX_MANKEN = int(os.environ.get("LAQ_MAX_MANKEN", "12"))
MAX_GOMLEK = int(os.environ.get("LAQ_MAX_GOMLEK", "12"))
MAX_PIKSEL = 60_000_000
MAX_DUGME = 200
OTURUM_GUN = 30
# Arayuzun yayinlandigi adres(ler) (GitHub Pages). API baska alt alan adinda ise CORS/Origin icin gerekli, virgulle ayrilir.
ON_YUZ = [o.strip().rstrip("/") for o in os.environ.get("LAQ_ON_YUZ", "https://laq.engrare.com,http://laq.engrare.com").split(",") if o.strip()]
MODEL = KOK / "modeller" / "segformer_b2_clothes.onnx"
CIKTI_GENISLIK = 1080
CIKTI_KALITE = 97
# 0 = bu sunucu yalnizca API'dir (arayuz GitHub Pages'ten gelir); 1 = arayuz de buradan acilir
ARAYUZ_SUN = os.environ.get("LAQ_ARAYUZ", "1") != "0"
