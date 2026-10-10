"""SegFormer-b2-clothes ONNX modelini indirir ve sha256 dogrular -> modeller/segformer_b2_clothes.onnx
Lisans uyarisi: model NVIDIA SegFormer lisansina baglidir (yalnizca ticari olmayan kullanim). README'ye bakin."""
import hashlib, sys, urllib.request
from pathlib import Path

URL = "https://huggingface.co/Xenova/segformer_b2_clothes/resolve/main/onnx/model.onnx"
SHA256 = "12aee5578c95cd43706062d9a37e7359b320c147c92c437681c730a580716ef4"
HEDEF = Path(__file__).resolve().parent.parent / "modeller" / "segformer_b2_clothes.onnx"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


if HEDEF.exists() and sha(HEDEF) == SHA256:
    print("Model zaten var, sha256 dogru."); sys.exit(0)
HEDEF.parent.mkdir(exist_ok=True)
tmp = HEDEF.with_suffix(".part")
print("Indiriliyor:", URL)
urllib.request.urlretrieve(URL, tmp)
if sha(tmp) != SHA256:
    tmp.unlink(); sys.exit("HATA: sha256 uyusmuyor, dosya silindi.")
tmp.replace(HEDEF)
print("Tamam:", HEDEF)
