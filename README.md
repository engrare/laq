# LAQ – gömlek yeniden boyama

Mankenin giydiği gömleği, askıdaki gömlek fotoğrafının rengine boyar. Düğme, cep, dikiş, kumaş dokusu, kollar, eller ve iç tişört mankenden aynen kalır; yalnızca renk değişir. Yalnızca CPU'da çalışır (GPU gerekmez).

**Sınırlar:** manken ve askıdaki gömlek AYNI model olmalıdır. Sistem cep ya da düğme eklemez. Otomatik maske çok iyidir ama kusursuz değildir (saç altı, el-kol teması); web arayüzündeki fırça ile elle düzeltilir.

## Nasıl çalışır
1. **Drive** sekmesi (Google Drive gibi): fotoğraflar klasörlere yüklenir, seçilir, indirilir, taşınır, silinir. Seçilen fotoğraflar (ya da klasörün içindekiler) "Manken olarak ekle" / "Gömlek olarak ekle" ile bir boyama işine eklenir.
2. Sunucu her mankenin gömlek maskesini çıkarır (SegFormer-b2-clothes ONNX + GrabCut) ve "taralı" önizleme gösterir (kırmızı = boyanacak, yeşil = korunan düğme).
3. Tarayıcıda fırça (ekle/çıkar), zoom/pan, geri al ve düğme işaretleme ile maske düzeltilir.
4. "Üret": her manken × her renk görseli 1080 px genişlikte üretilir; sonuçlar Drive'da `Sonuçlar/<tarih saat>/` klasörüne yazılır (ZIP de indirilebilir).

Ölçülen süreler (4 çekirdekli AVX2'siz CPU): manken başına maske ≈ 14 sn, askı fotoğrafından renk okuma ≈ 6 sn, yeni renk başına boyama ≈ 0,2 sn.

## Kurulum
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/model_indir.py        # modeli indirir, sha256 doğrular
cp .env.example .env                            # LAQ_PAROLA'yı doldurun
./run.sh                                        # http://127.0.0.1:8101
```
Uygulama yalnızca `127.0.0.1`'i dinler; HTTPS için bir ters vekil (reverse proxy) ya da tünel kullanın. Python 3.11+ ve `numpy`, `opencv-python-headless`, `onnxruntime`, `pillow`, `fastapi`, `uvicorn`, `python-multipart` gerekir.

## Yayın: GitHub Pages (arayüz) + sunucu (API)
Arayüz (`static/`) statik dosyalardır; GitHub Pages'te `docs/` klasöründen yayınlanabilir, API ise ayrı bir sunucuda çalışır:
- `docs/config.js` içindeki `window.LAQ_API`, API adresini gösterir (ör. `https://laq-api.example.com`).
- API tarafında `LAQ_ON_YUZ` arayüzün adresini içermelidir (CORS + Origin denetimi).
- Çerez `SameSite=Lax` olduğundan arayüz ve API **aynı kayıtlı alan adının** alt alan adları olmalıdır (ör. `laq.example.com` ve `laq-api.example.com`).
- Pages kullanılmazsa `./run.sh` arayüzü de kendisi sunar (`config.js` boş = aynı sunucu).

## Ayarlar (ortam değişkenleri)
| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `LAQ_PAROLA` | (zorunlu, ≥8 karakter) | Tek giriş parolası |
| `LAQ_PORT` | 8101 | Dinlenen port |
| `LAQ_ON_YUZ` | `https://laq.engrare.com` | İzin verilen arayüz adres(ler)i, virgülle ayrılır |
| `LAQ_VERI` | `./data` | Yüklenen/üretilen veri klasörü |
| `LAQ_SAKLA_GUN` | 7 | Eski işlerin otomatik silinme süresi |
| `LAQ_MAX_DOSYA_MB` | 15 | Dosya başına boyut sınırı |
| `LAQ_MAX_MANKEN`, `LAQ_MAX_GOMLEK` | 12, 12 | İş başına fotoğraf sayısı |
| `LAQ_DRIVE` | `/mnt/hdd/drive/laq-drive` | Drive klasörü (kod ve iş verisinden ayrı; siz silene kadar kalır) |
| `LAQ_DRIVE_MAX_DOSYA_MB` | 40 | Drive'a yüklenen dosya başına sınır |
| `LAQ_DRIVE_BOS_MIN_GB` | 5 | Diskte bu kadar yer kalmazsa yükleme reddedilir |

## Yapı
- `kod/` – motor: `boya.py` (`hazirla()` manken başına bir kez, `boya()` renk başına), `seg/pipeline.py` (SegFormer, renk okuma). Ayrıntılar: `API.md`.
- `app/` – FastAPI uygulaması: giriş, tek işçili kuyruk, iş deposu, Drive (`drive.py`), API.
- `index.html`, `app.js`, `drive.js`, `style.css` (kökte; özel repoda `static/`) – tarayıcı arayüzü ve fırça editörü (bağımlılıksız JS).
- `scripts/model_indir.py` – model indirme + sha256.

## Lisans uyarısı
Kullanılan `segformer_b2_clothes` modeli, NVIDIA SegFormer lisansına (NVIDIA Source Code License) bağlıdır: **yalnızca ticari olmayan (araştırma/değerlendirme) kullanım**. Model bu depoda dağıtılmaz. Ticari kullanım için modeli lisansı uygun bir alternatifle değiştirin. Bu deponun kendi kodu için henüz bir lisans dosyası seçilmemiştir.
