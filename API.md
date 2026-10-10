# laq motoru - API notları

Tüm satır numaraları bu ZIP'teki dosyalara göredir. Dosyalar: `kod/boya.py` (motor), `kod/seg/pipeline.py` (SegFormer + renk), `kod/dugme_isaretle.py` (`yukle`, `JSON`), `kod/maske_duzelt.py` (`yukle_duzelt`).
Tüm görüntüler **BGR uint8** (OpenCV), tüm koordinatlar `yukle()` çıktısı uzayındadır (aşağıda b).

## a) Fonksiyon imzaları

```python
# kod/dugme_isaretle.py:14
yukle(p) -> np.ndarray                       # BGR uint8 (H, W, 3); p: dosya yolu (str/Path)

# kod/seg/pipeline.py:34
Segmenter(model_path: str | Path, threads: int = 4)

# kod/seg/pipeline.py:89
analyze_model(img: np.ndarray, seg: Segmenter) -> ShirtMask      # ShirtMask(mask: uint8 {0,1} (H,W), ref_lab: (L,a,b) 3 float)

# kod/seg/pipeline.py:191
extract_shirt_color(img: np.ndarray, seg: Segmenter) -> dict     # {"raw": {"lab": (L,a,b), "hex": "#rrggbb"}, "normalized": {...aynı...}}

# kod/boya.py:54   (manken başına 1 kez, renkten bağımsız)
hazirla(img: np.ndarray, sm: ShirtMask, seg: Segmenter, dugme_pts=(), duzelt: np.ndarray | None = None) -> dict

# kod/boya.py:139  (renk başına, hızlı)
boya(img: np.ndarray, h: dict, target_lab: tuple) -> np.ndarray   # BGR uint8, img ile aynı shape

# kod/maske_duzelt.py:17
yukle_duzelt(stem: str) -> np.ndarray | None     # kod/duzeltme/<stem>.png'yi uint8 (H,W) okur, yoksa None
```

Tam kullanım (smoke_test.py'nin özü):

```python
seg  = Segmenter("modeller/segformer_b2_clothes.onnx")                    # bir kez
m    = yukle("girdi/manken/IMG-20261008-WA0033.jpg")
h    = hazirla(m, analyze_model(m, seg), seg, dugme["IMG-20261008-WA0033"], duzelt_png_or_None)
lab  = extract_shirt_color(yukle("girdi/gomlek/IMG-20261008-WA0039.jpg"), seg)["normalized"]["lab"]
out  = boya(m, h, lab)                                                    # BGR uint8
```

`hazirla()` dönüş değeri (1280x853 örnek; H=1280, W=853; ölçüldü):

| anahtar | dtype | shape | değer aralığı / anlam |
|---|---|---|---|
| `M` | uint8 | (H,W) | {0,1} son gömlek maskesi (önizleme/“taralı” görüntü için bu kullanılır) |
| `alpha` | float32 | (H,W) | 0..1 kenar alfası (kenarlarda boya oranı) |
| `core` | uint8 | (H,W) | {0,1} tam boyanan iç bölge (`erode(M, 5)`) |
| `F` | float32 | (H,W,3) | BGR, 0..255 yerel kumaş rengi (kenar boyaması için) |
| `btn` | **float64** | (H,W) | 0..1 düğme koruma alfası (1 = orijinal piksel kalır) |
| `ref` | tuple(3 float) | - | (L,a,b) orijinal kumaş rengi, OpenCV 8-bit Lab ölçeği (ör. (114.0, 138.0, 140.0)) |

**Önbellek**: sonuç yalnızca numpy dizileri + bir tuple olduğundan pickle edilebilir. Ölçülen boyut (1280x853): ham/pickle 27,1 MB; `np.savez_compressed` 3,2 MB. `btn` float32'ye çevrilirse 4 MB kazanılır (sonuç farkı ihmal edilebilir). `ref` npz'den dizi olarak döner; `boya()` içinde `Ls, As, Bs = h["ref"]` ile açıldığı için dizi de olur. Önbellek anahtarı = (manken dosyası içeriği, dugme.json girdisi, duzelt PNG içeriği); bunlardan biri değişince `hazirla` yeniden çalışmalı.
Not: fırça düzeltmesi `hazirla` içinde en sonda (boya.py:129-135) ve sadece `alpha/core/M/btn`'ı değiştirir; SegFormer/GrabCut tekrar gerekmeden hızlı geri bildirim istenirse bu blok ayrı bir fonksiyona taşınabilir (şu an taşınmadı).
Thread güvenliği: `hazirla` içinde `cv2.setRNGSeed(0)` (global) var; aynı süreçte iki `hazirla` aynı anda çalıştırılmamalı (tek işçili kuyruk zaten bunu sağlar). `Segmenter.probs` kendi kilidine sahiptir.

## b) `duzelt=` parametresi (fırça düzeltmesi)

- Tek kanallı (8-bit gri) PNG; **değerler tam olarak** 0 = değişiklik yok, 1 = ekle (boyansın), 2 = çıkar (boyanmasın). Başka değerler (127, 255 vb.) yok sayılır; RGB/palet PNG gri okuyucuda değer bozar -> mutlaka 8-bit grayscale yazın.
- **Boyut kuralı**: PNG'nin shape'i `hazirla`ya verilen `img.shape[:2]` ile **birebir** aynı olmalı, yani `(H, W)` = `yukle(manken)` çıktısı. Aksi halde düzeltme **sessizce yok sayılır** (boya.py:129 `duzelt.shape == alpha.shape`, hata vermez).
- `yukle()` kuralı: uzun kenar > 1280 ise `k = 1280 / uzun_kenar`, `cv2.resize(img, None, fx=k, fy=k, INTER_AREA)`; boyutlar OpenCV tarafından **yuvarlanır** (dsize = round(W*k), round(H*k)). Ölçülen örnekler: 4000x3000 -> 1280x960; 3024x4032 -> 960x1280; 1281x853 -> 1280x852 (853*0.99922=852,33 -> 852); 1000x700 -> **değişmez** (uzun kenar ≤ 1280 ise küçük resim büyütülmez). En güvenlisi: sunucu `yukle()` çıktısının `shape`ini istemciye bildirsin, tarayıcı canvas'ı bu boyutta (CSS ölçeği ayrı) çizip PNG'yi tam bu boyutta üretsin. Piksel kayması/yeniden örnekleme yoktur: piksel (x,y) = `yukle()` görüntüsünün (x,y) pikseli.
- Uygulama (boya.py:129-135): 1 ve 2 maskeleri Gauss(σ=0.8) ile yumuşatılır; `alpha = max(alpha*(1-cikar_s), ekle_s)`; `core` ve `M` ekle=1 / çıkar=0 olarak zorlanır; ekle bölgesinde düğme koruması (`btn`) kalkar (ekle_s ile çarpılır), çıkarma düğmeye dokunmaz.
- Dosya adı: `kod/duzeltme/<manken_stem>.png` (örn. `IMG-20261008-WA0033.png`). Web uygulamasında dosyaya gerek yok; diziyi doğrudan `hazirla(..., duzelt=dizi)` ile verin.

## c) `kod/dugme.json` şeması

Anahtar = manken dosya adı **uzantısız** (`Path.stem`, örn. `IMG-20261008-WA0033`). Değer = düğme listesi; her öğe `[x, y, yarıçap]` (eski biçim: yarıçap < 6 ise "c", değilse "k" sayılır) veya `[x, y, yarıçap, tip]`. `tip`: `"k"` = metal kapak düğme (kumaşla aynı tonda, daire kenarı bulunur), `"c"` = çıt çıt dişi (gümüş, kumaştan farklı pikseller korunur). x, y, yarıçap tam sayı (piksel), **`yukle()` uzayında** (uzun kenar ≤ 1280). Merkez tam isabet gerekmez: "k" için ±max(4, r//3) px aranır. Boş liste `[]` = düğme yok. `hazirla`ya o mankenin listesi verilir (`dugme["<stem>"]`).
Dikkat: `boya.py`'nin `__main__` bölümü, json'da olmayan bir manken için tkinter penceresi açar; sunucuda bunun yerine her yeni mankene en az `[]` yazın.

Gerçek içerik (dosyanın tamamı):

```json
{
 "IMG-20261008-WA0033": [[395,480,7],[396,580,7],[381,694,7],[331,901,7],[443,505,5],[448,609,5],[444,718,5],[450,832,5],[456,936,5]],
 "IMG-20261008-WA0034": [[442,522,7],[436,625,7],[422,743,7],[410,860,7],[402,972,7]],
 "IMG-20261008-WA0035": [[172,950,5,"c"],[678,978,5,"c"]],
 "IMG-20261008-WA0036": [[390,555,7,"k"],[388,641,7,"k"],[380,749,7,"k"],[380,947,7,"k"],[444,588,5,"c"],[453,685,5,"c"],[475,764,5,"c"]],
 "IMG-20261008-WA0037": [[698,376,17,"k"],[108,557,16,"k"],[705,652,18,"k"],[703,963,18,"k"],[700,1263,17,"k"]],
 "IMG-20261008-WA0038": [[367,512,7],[373,614,7],[360,727,7],[308,934,7],[420,524,5],[443,627,5],[476,709,5]]
}
```

## d) EXIF yönü

Kodda **açık bir EXIF kodu yoktur**; yön `kod/dugme_isaretle.py:16` içindeki `cv2.imdecode(np.fromfile(...), cv2.IMREAD_COLOR)` ile kendiliğinden uygulanır (OpenCV `IMREAD_IGNORE_ORIENTATION` verilmedikçe EXIF yönünü uygular). Doğrulandı: EXIF Orientation=6 ile kaydedilmiş 300x200 JPEG, `yukle()` sonrası 200 genişlik x 300 yükseklik (döndürülmüş) geldi. Sonuçlar: (1) `dugme.json` ve `duzelt` PNG koordinatları **EXIF uygulanmış** görüntüye göredir; tarayıcı `<img>`/canvas da EXIF'i varsayılan uygular ama istemci tarafında doğrulayın, en güvenlisi önizlemeyi sunucudaki `yukle()` çıktısından (JPEG/PNG) üretmektir; (2) üretilen çıktı JPEG'inde EXIF yoktur; (3) `yukle` yerine PIL/başka okuyucu kullanırsanız yönü kendiniz uygulayın.

## e) Renk nasıl alınıyor (`extract_shirt_color`, pipeline.py:191)

- Girdi: askıdaki gömlek fotoğrafı (`yukle()` ile, BGR). SegFormer "üst giysi" olasılığı > 0,5 olan bölge, `erode(_k(25, s))` ile içeri çekilir (kenar/yaka/etiket dışarıda kalır; < 200 piksel kalırsa erode'suz bölge).
- İstatistik: bu bölgedeki piksellerin Lab'ı (OpenCV 8-bit) alınır, L'nin yüzde 15-85 aralığı dışı atılır (düğme/etiket/parlama), kalanın **medyanı** = kumaş rengi.
- İki varyant döner: `raw` (olduğu gibi) ve `normalized` (beyaz dengesi: arka plan olasılığı > 0,8 ve gömlekten uzak (41 px'ten fazla) piksellerin parlaklık yüzde 60-94 aralığının ortalaması beyaz referans kabul edilir, `WHITE_TARGET = 238` hedefiyle kanal kazancı = 238/ref, [0,6 .. 2,0] arasına kırpılır; sonra aynı medyan). **Motor `normalized` kullanır** (`boya.py:163`).
- `boya()`'ya verilen: `["normalized"]["lab"]` = `(L, a, b)` üçlüsü, OpenCV 8-bit Lab ölçeğinde float (L 0..255, a/b 128 merkezli). Hex de döner (`["hex"]`), ama boyamada kullanılmaz. Dosya yolu / RGB verilmez.
- Rengin mankene uygulanışı (`boya`): `L2 = Lt * min(L/Ls, 1.25)`, `a2 = At + (a-As)*0.35`, `b2 = Bt + (b-Bs)*0.35` (Ls,As,Bs = mankenin orijinal kumaş rengi `h["ref"]`).

## f) Çıktı kuralı (1080 px GENİŞLİK, Lanczos, JPEG q97)

Kodda: `kod/boya.py:178-184` (`--ig` bölümü):

```python
im = yukle(f)                                   # f: cikti_boya/ icindeki q96 calisma JPEG'i (!)
im = cv2.resize(im, (1080, round(im.shape[0] * 1080 / im.shape[1])), interpolation=cv2.INTER_LANCZOS4)
wr(dst / re.sub(r"IMG-\d{8}-", "", f.name), im, 97)
```

- Genişlik **1080'e sabitlenir** (uzun kenar değil); yükseklik oransal. 853 genişlikli dikey kareler büyütülür (x1,27), 1280 genişlikli yatay kareler küçülür.
- **Çift JPEG**: önce `boya()` çıktısı `wr(...)` ile q96 JPEG olarak yazılır (boya.py:15 `wr`, varsayılan q=96, `cv2.imencode(".jpg", im, [IMWRITE_JPEG_QUALITY, q])`), `--ig` bunu geri okuyup 1080'e büyütür ve q97 yazar. `referans/beklenen/` bu zincirle üretildi; birebir aynı sonucu isterseniz `boya()` çıktısını q96 encode/decode edip sonra 1080 + q97 uygulayın (`smoke_test.py` böyle yapar).- Dosya adı: `re.sub(r"IMG-\d{8}-", "", ad)`: `IMG-20261008-WA0033_IMG-20261008-WA0039.jpg` -> `WA0033_WA0039.jpg`. `--ig` bölümü artık `<proje>/instagram/` klasörüne yazar (boya.py:180). Web uygulaması bu adımı kendi kodunda yapar (`app/isler.py`, tek JPEG q97).

## g) Üçüncü parti importlar

Yalnızca üç paket: **numpy**, **opencv-python-headless** (`cv2`), **onnxruntime**. scipy, skimage, PIL, torch YOK (PIL sadece bu dokümandaki EXIF testinde kullanıldı, motor kullanmaz).
Standart kütüphane: json, re, sys, pathlib, threading, dataclasses, base64 (ve yalnızca GUI fonksiyonlarının içinde `tkinter`: `dugme_isaretle.isaretle()` ve `maske_duzelt.duzelt()`; tkinter importu **fonksiyon içine taşındı**, böylece tkinter olmayan sunucuda motor import hatası vermez; web arayüzünde bu iki GUI fonksiyonu çağrılmaz).

## h) İş parçacığı ayarları

- ONNX Runtime: `kod/seg/pipeline.py:34-37`, `Segmenter(..., threads=4)` -> `SessionOptions.intra_op_num_threads = threads`; `inter_op_num_threads` ayarlanmaz (varsayılan, sıralı yürütme olduğundan etkisiz); sağlayıcı yalnızca `CPUExecutionProvider`.
- OpenCV: `cv2.setNumThreads` **hiçbir yerde çağrılmaz** (varsayılan = tüm mantıksal çekirdekler; bu bilgisayarda 12). Ölçüm: 12 vs 4 OpenCV thread'i arasında fark yok (hazirla 2,1-2,8 sn her ikisinde). Sunucu için isteğe bağlı: uygulama başında `cv2.setNumThreads(4)`.
- Sunucu: 4 çekirdek, **AVX2 yok** (AVX var). Bu ONNX Runtime sürümünün (1.31.0) o CPU'da çalıştığı **doğrulanmadı**; ilk iş `python kod/smoke_test.py` çalıştırın.
- `analyze_model` + `hazirla` aynı sürecte tek işçi ile çalıştırılmalı (RNG tohumu global).

## i) Ayarlanabilir sabitler

Hepsi koddaki sabit değerlerdir (CLI/config yok); `ell(n)` = n x n elips çekirdek (boya.py:16), `_k(size, s)` = `size*s` çekirdek (s = max(0,5, uzun_kenar/1280) = 1,0).

### hazirla() (boya.py)
| ad / yer | değer | ne işe yarar |
|---|---|---|
| alt giysi erode (satır 58) | `lower>0,7`, `ell(5)` | pantolon/etek bölgesini maskeden çıkarma |
| cilt/saç eşiği (59) | skin>0,6, hair>0,6 | maskeden çıkarma |
| grow (63) | dilate `ell(25)`, `cd<8`, 80<L<185, skin<0,97, hair<0,5 | SegFormer'ın cilt saydığı açık yaka altını kumaş kromasıyla büyütme |
| grow open / close (65-66) | `ell(3)` / `ell(5)` | büyütmeyi temizleme |
| iç tişört `tee` (68) | L>165, `cd>9`, skin<0,5, **bg<0,3** | iç tişört; `bg<0,3` arka planı tişört sanmayı engeller (dış kenar halesi düzeltmesi) |
| tee min alan / dilate (69-70) | >800 px, `ell(7)` | küçük lekeleri atma, tişört kenarını genişletme |
| medyan (72) | `medianBlur(…, 7)` | tırtıklı yaka/kenar düzeltme |
| cilt komşu bölge (73-74) | dilate `ell(25)`, Gauss σ=2,2, eşik 0,5 | yaka/el kenarlarını ek pürüzsüzleştirme |
| küçük bileşen eşiği (77, 91) | alan > 0,05 x en büyük | küçük lekeleri atma |
| GrabCut (79-83) | bbox dilate `ell(31)`; kesin ön plan erode `ell(15)`, olası arka plan dilate `ell(15)`; **5 iterasyon**; `cv2.setRNGSeed(0)` | kenarı ±7 px içinde gerçek renk kenarına oturtma |
| gap (85) | L>165, `cd>9`, bg>0,15, dilate `ell(3)` | kol-gövde arası boşluk |
| tee gölge (87) | dilate `ell(7)` ve `cd>9` | beyaz iç tişörtün gri kenar gölgesi |
| GrabCut sonrası yumuşatma (88) | Gauss σ=1,2, eşik 0,5 | merdiven kenar düzeltme |
| inner / near (93-94) | `erode ell(7)` / `dilate ell(9)` | yerel kumaş rengi ve dış renk örnekleme bölgeleri |
| nconv σ (95, 98) | 5 | yerel renk yayılımı |
| Lab ağırlığı W (97) | (0,25, 2, 2) | alfa hesabında ton düşük, renk özü yüksek ağırlık |
| `notshirt` kalan eşiği (103) | `resid > 22` | kumaş-dış renk doğrusuna uzak pikselleri boyamama |
| arka plan bölgesi `bgs` (104) | Gauss σ=2, bg>0,5 | arka plan kenarı ayrımı |
| alfa rampası (106) | bg kenarı: (α-0,08)/0,55; diğer: (α-0,25)/0,65 | kenar alfası eşikleri (arka planda gevşek, tişört/ciltte sert) |
| `contrast` (107) | `|d|² > 10²` | kumaş/dış renk benzerse alfa güvenilmez -> maske |
| band (110-111) | `dilate ell(5)` (+ `dilate ell(9)` & arka plan); tişört yanında `dilate ell(3)` | kenar alfa bandı genişliği (2 px / arka planda 4 px / tişört yanında 1 px) |
| `core` (112) | `erode ell(5)` | tam boyanan iç bölge |
| saç bölgesi (116-126) | hair>0,5 & upper>0,1; σ=2 eşik 0,5; `hp`: hair>0,5 & `cd>12`; nconv σ 25 (F2) / σ 6 (H); `r2<25`; `|dh|>15`; yumuşatma σ=1,5; rampa (ah-0,2)/0,6 | saç telleri arasından görünen kumaş için yumuşak alfa |
| son alfa yumuşatma (127) | Gauss σ=0,6 | |
| fırça düzeltme yumuşatma (131) | Gauss σ=0,8 | `duzelt` kenar yumuşatma |

### dugme_maske() (boya.py:25)
| ad | değer | anlam |
|---|---|---|
| açı örnekleri | 48 | daire kenarı dışa doğru L gradyanı örnekleme |
| arama aralığı | merkez ±max(4, r//3), yarıçap ±max(1, r//8) | "k" daire uydurma |
| dış halka payı | `r + 0.3` | düğme dış kenar halkası boyalı kalır |
| "c" dairesi | `r + 2` | çıt çıt arama bölgesi |
| "c" yerel kumaş rengi | nconv σ=6, dışlama `dilate ell(9)` | |
| "c" fark eşiği | `(d-14)/20`, Lab ağırlığı (0,7,1,1), `close ell(3)`, Gauss σ=0,7 | kumaştan farklı pikselleri koruma |

### boya() (boya.py:139)
| ad | değer | anlam |
|---|---|---|
| `0.35` | kroma koruma (a,b farkı) | orijinal kumaş doku/gölge renk varyasyonunun yeni renge taşınma oranı |
| `1.25` | L oranı tavanı | parlak bölge aşırı açılmasın |
| `t` Gauss σ | 1,0 | iç bölge / kenar geçişi |

### analyze_model() / Segmenter (pipeline.py)
| ad | değer | anlam |
|---|---|---|
| model girişi | 512x512 RGB, ImageNet mean/std | SegFormer girişi (en-boy oranı korunmaz) |
| `tc` | `clip(0,5 * nötr_mesafe, 6, 14)` | "kumaş sayılan" kroma yarıçapı |
| gölge kuralı | alan < 4 s² veya ortalama L < 0,62 x kumaş L | koyu gölge kumaşa dahil |
| `lit_edge` | A ≥ dA-8, B < dB+2,5, L < 195, dist < 11, skin<0,3, hair<0,3; band `_k(13)` | aydınlık kenar yakalama |
| iç kırpma | `erode _k(9)` ve upper<0,25 | model sınırı taşmasını kırpma |
| bileşen filtresi / delik | > %2 x en büyük; delik < 120 s² | |
| son yumuşatma | Gauss 1,6 s, eşik 0,5 | |
| `yukle` uzun kenar | 1280 (dugme_isaretle.py:14) | tüm koordinatların uzayı |
| `WHITE_TARGET` | 238 | renk çıkarmada beyaz referans (extract_shirt_color) |
| Segmenter `threads` | 4 | ORT intra-op thread sayısı |
| çıktı | genişlik 1080, `INTER_LANCZOS4`, q97 (çalışma dosyası q96) | boya.py:182-183, 15 |

## j) Bellek

Ölçüm (Windows, Python 3.11.9, 1280x853 manken, model yüklü süreç): tek süreçte tepe çalışma kümesi (peak working set) **≈ 1,4 GB** (model yükleme + `analyze_model` sonrası ≈ 800-870 MB; `hazirla()` kendi payı yaklaşık +300 MB RSS / +500 MB tepe). `hazirla` sonucu 27 MB (bellekte). `boya()` belleği ayrıca ölçülmedi. 16 GB RAM'li sunucuda tek işçi rahat; paralel işçi sayısı = bellek / 1,5 GB, ama 4 çekirdekte 1 işçi önerilir.
