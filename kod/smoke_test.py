"""Duman testi: 1 manken x 1 renk uretir, referans/beklenen/ icindeki karsiligiyla piksel farkini yazdirir.
Kullanim: python kod/smoke_test.py [manken_adi_parcasi] [gomlek_adi_parcasi]   (varsayilan: ilk manken + ilk gomlek)
Ortalama mutlak fark > 2 ise FAIL (cikis kodu 1). Beklenen: ~0 (ayni kod + ayni kutuphane surumleri)."""
import json, sys, time
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from seg.pipeline import Segmenter, analyze_model, extract_shirt_color
from dugme_isaretle import JSON, yukle
from maske_duzelt import yukle_duzelt
from boya import R, hazirla, boya

jpg = lambda im, q: cv2.imdecode(cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
sec = lambda klasor, i: next(f for f in sorted((R / "girdi" / klasor).glob("*.jpg")) if (sys.argv[i] if len(sys.argv) > i else "") in f.name)

mp, gp = sec("manken", 1), sec("gomlek", 2)
ref_yol = R / "referans" / "beklenen" / mp.stem / f"{gp.stem}.jpg"
t0 = time.perf_counter()
seg = Segmenter(R / "modeller" / "segformer_b2_clothes.onnx")
dugme = json.loads(JSON.read_text()) if JSON.exists() else {}
renk = extract_shirt_color(yukle(gp), seg)["normalized"]["lab"]
m = yukle(mp)
h = hazirla(m, analyze_model(m, seg), seg, dugme.get(mp.stem, ()), yukle_duzelt(mp.stem))
t1 = time.perf_counter()
out = boya(m, h, renk)
t2 = time.perf_counter()
# boya.py --ig ile ayni yol: q96 calisma JPEG'i -> oku -> 1080 genislik Lanczos -> q97
out = jpg(out, 96)
out = jpg(cv2.resize(out, (1080, round(out.shape[0] * 1080 / out.shape[1])), interpolation=cv2.INTER_LANCZOS4), 97)
print(f"{mp.name} x {gp.name}: hazirla {t1 - t0:.1f} sn (model yukleme dahil), boya {t2 - t1:.2f} sn")
ref = cv2.imdecode(np.fromfile(str(ref_yol), np.uint8), cv2.IMREAD_COLOR)
if ref is None or ref.shape != out.shape:
    print("FAIL: referans yok veya boyut farkli", ref_yol, None if ref is None else ref.shape, out.shape); sys.exit(1)
d = np.abs(out.astype(np.int16) - ref.astype(np.int16))
print(f"ortalama mutlak fark {d.mean():.3f}   %99 yuzdelik {np.percentile(d, 99):.1f}   maks {d.max()}")
ok = d.mean() <= 2
print("OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
