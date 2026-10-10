"use strict";
// Drive sekmesi: klasor gezme, yukleme, secme, indirme, tasima; secilenleri boyama islerine ekleme.
// app.js'ten api(), mesaj(), IS, API, ciz(), zamanla() kullanilir (cagri aninda hazirdirlar).
const D = { yol: "", veri: null, sec: new Set() };
const dq = encodeURIComponent;
const dbirlestir = (a, b) => (a ? a + "/" + b : b);

function boyutYaz(n) {
  return n > 1e6 ? (n / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1e3)) + " KB";
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// ------------------------------------------------------------------ sekmeler
function gorunumSec(ad) {
  localStorage.setItem("laq_gorunum", ad);
  $("#gDrive").hidden = ad !== "drive";
  $("#gIs").hidden = ad !== "is";
  $("#nDrive").classList.toggle("aktif", ad === "drive");
  $("#nIs").classList.toggle("aktif", ad === "is");
  $("#yeniIs").hidden = ad !== "is";
  if (ad === "drive") driveAc(D.yol).catch(() => driveAc(""));
}
$("#nDrive").onclick = () => gorunumSec("drive");
$("#nIs").onclick = () => gorunumSec("is");
$("#driveSec").onclick = () => gorunumSec("drive");
$("#driveAc").onclick = async () => { D.yol = IS.drive || ""; gorunumSec("drive"); };

// ------------------------------------------------------------------ liste
async function driveAc(yol) {
  const v = await api("/api/drive/liste?yol=" + dq(yol || ""));
  D.veri = v; D.yol = v.yol; D.sec.clear();
  driveCiz();
}
function yolCiz() {
  const k = $("#dYol");
  k.replaceChildren();
  const parcalar = D.yol ? D.yol.split("/") : [];
  const ekle = (metin, yol) => { const a = el("a", "", metin); a.onclick = () => driveAc(yol); k.append(a); };
  ekle("Drive", "");
  parcalar.forEach((p, i) => { k.append(" / "); ekle(p, parcalar.slice(0, i + 1).join("/")); });
}
function kartYap(oge, klasor) {
  const c = el("div", "dkart" + (D.sec.has(oge.yol) ? " sec" : ""));
  const cb = el("input"); cb.type = "checkbox"; cb.checked = D.sec.has(oge.yol);
  cb.onchange = () => { cb.checked ? D.sec.add(oge.yol) : D.sec.delete(oge.yol); c.classList.toggle("sec", cb.checked); secimCiz(); };
  const on = el("div", "on");
  if (klasor) { on.textContent = "📁"; on.onclick = () => driveAc(oge.yol); }
  else {
    const img = el("img"); img.loading = "lazy"; img.alt = "";
    img.src = `${API}/api/drive/kucuk?yol=${dq(oge.yol)}`;
    img.onerror = () => { img.remove(); on.textContent = "🖼"; };
    on.append(img); on.onclick = () => onizleAc(oge);
  }
  const ad = el("div", "ad", oge.ad);
  if (klasor) { ad.onclick = on.onclick; ad.style.cursor = "pointer"; }
  c.append(cb, on, ad, el("div", "bil", klasor ? `${oge.adet} öğe` : boyutYaz(oge.boyut)));
  return c;
}
function driveCiz() {
  yolCiz();
  $("#dUst").disabled = D.veri.ust === null;
  $("#dUst").onclick = () => D.veri.ust !== null && driveAc(D.veri.ust);
  const g = $("#dGrid");
  g.replaceChildren();
  for (const k of D.veri.klasorler) g.append(kartYap(k, true));
  for (const f of D.veri.dosyalar) g.append(kartYap(f, false));
  if (!g.children.length) g.append(el("div", "dbos", "Bu klasör boş — fotoğraf yükleyin veya buraya sürükleyin."));
  $("#dBilgi").textContent = `Sunucuda ${D.veri.bos_gb} GB boş alan var. Yüklenen dosyalar siz silene kadar saklanır.`;
  secimCiz();
}
function secimCiz() {
  const n = D.sec.size;
  $("#dSecim").hidden = n === 0;
  $("#dSayi").textContent = `${n} seçili`;
  $("#dAd").hidden = n !== 1;
  const tumu = D.veri && D.veri.klasorler.length + D.veri.dosyalar.length;
  $("#dTumu").textContent = tumu && n === tumu ? "Seçimi kaldır" : "Tümünü seç";
}
$("#dTumu").onclick = () => {
  const hepsi = [...D.veri.klasorler, ...D.veri.dosyalar].map((o) => o.yol);
  if (D.sec.size === hepsi.length) D.sec.clear(); else hepsi.forEach((y) => D.sec.add(y));
  driveCiz();
};
$("#dVazgec").onclick = () => { D.sec.clear(); driveCiz(); };

// ------------------------------------------------------------------ onizleme
function onizleAc(f) {
  $("#onizleImg").src = `${API}/api/drive/goruntu?yol=${dq(f.yol)}`;
  $("#onizleAd").textContent = f.ad;
  $("#onizleIndir").href = `${API}/api/drive/indir?yol=${dq(f.yol)}`;
  $("#onizle").hidden = false;
}
const onizleKapat = () => { $("#onizle").hidden = true; $("#onizleImg").removeAttribute("src"); };
$("#onizleKapat").onclick = onizleKapat;
$("#onizle").addEventListener("click", (e) => { if (e.target.id === "onizle") onizleKapat(); });
window.addEventListener("keydown", (e) => { if (e.key === "Escape") onizleKapat(); });

// ------------------------------------------------------------------ islemler
const secili = () => [...D.sec];
const sorgu = (liste) => liste.map((y) => "yol=" + dq(y)).join("&");

$("#dIndir").onclick = () => {
  const s = secili();
  const tekDosya = s.length === 1 && D.veri.dosyalar.some((f) => f.yol === s[0]);
  location.href = tekDosya ? `${API}/api/drive/indir?yol=${dq(s[0])}` : `${API}/api/drive/zip?${sorgu(s)}`;
};
async function iseEkle(tur) {
  const s = secili();
  mesaj(`${s.length} öğe işe ekleniyor…`);
  try {
    IS = await api(`/api/is/${IS.id}/${tur}/drive?${sorgu(s)}`, { method: "POST" });
    ciz(); zamanla();
    D.sec.clear(); driveCiz();
    mesaj(`Eklendi. Şu an işte ${IS.manken.length} manken, ${IS.gomlek.length} gömlek var. Üretmek için “Boyama” sekmesine geçin.`);
  } catch (e) { mesaj(e.message); }
}
$("#dManken").onclick = () => iseEkle("manken");
$("#dGomlek").onclick = () => iseEkle("gomlek");

$("#dSil").onclick = async () => {
  const s = secili();
  if (!confirm(`${s.length} öğe kalıcı olarak silinsin mi? (Klasörlerin içindekiler de silinir.)`)) return;
  try { await api("/api/drive/sil?" + sorgu(s), { method: "POST" }); await driveAc(D.yol); }
  catch (e) { mesaj(e.message); }
};
$("#dAd").onclick = async () => {
  const y = secili()[0], eski = y.split("/").pop();
  const ad = prompt("Yeni ad:", eski);
  if (!ad || ad === eski) return;
  try { await api(`/api/drive/ad?yol=${dq(y)}&ad=${dq(ad)}`, { method: "POST" }); await driveAc(D.yol); }
  catch (e) { mesaj(e.message); }
};
$("#dKlasor").onclick = async () => {
  const ad = prompt("Klasör adı:");
  if (!ad) return;
  try { await api("/api/drive/klasor?yol=" + dq(dbirlestir(D.yol, ad)), { method: "POST" }); await driveAc(D.yol); }
  catch (e) { mesaj(e.message); }
};
$("#dTasi").onclick = async () => {
  const s = secili();
  const { klasorler } = await api("/api/drive/klasorler");
  const sec = $("#tasiSec");
  sec.replaceChildren();
  for (const k of klasorler) {
    if (s.some((x) => k === x || k.startsWith(x + "/")) || k === D.yol) continue;   // kendi icine / ayni yere olmaz
    const o = el("option", "", k ? "Drive / " + k.split("/").join(" / ") : "Drive (ana klasör)"); o.value = k; sec.append(o);
  }
  if (!sec.children.length) { mesaj("Taşınacak başka klasör yok."); return; }
  $("#tasiPencere").hidden = false;
};
$("#tasiIptal").onclick = () => { $("#tasiPencere").hidden = true; };
$("#tasiTamam").onclick = async () => {
  $("#tasiPencere").hidden = true;
  try { await api(`/api/drive/tasi?${sorgu(secili())}&hedef=${dq($("#tasiSec").value)}`, { method: "POST" }); await driveAc(D.yol); }
  catch (e) { mesaj(e.message); }
};

// ------------------------------------------------------------------ yukleme (3 paralel, ilerleme cubuklu)
const RESIM = /\.(jpe?g|png|webp)$/i;
function driveYukle(dosyalar) {
  const hedef = D.yol;
  const gecerli = dosyalar.filter((f) => RESIM.test(f.name));
  if (gecerli.length < dosyalar.length) mesaj(`${dosyalar.length - gecerli.length} dosya atlandı (yalnızca jpg, png, webp).`);
  const bekleyen = [...gecerli];
  let acik = 0;
  const siradaki = () => {
    while (acik < 3 && bekleyen.length) { acik++; bir(bekleyen.shift()); }
  };
  const bitti = () => {
    acik--;
    if (!bekleyen.length && acik === 0 && D.yol === hedef && !$("#gDrive").hidden) driveAc(hedef).catch(() => {});
    siradaki();
  };
  function bir(f) {
    const k = el("div", "yk"); k.append(el("div", "", f.name)); const cubuk = el("i"); k.append(cubuk);
    $("#yuklemeler").append(k);
    const x = new XMLHttpRequest();
    x.open("PUT", `${API}/api/drive/dosya?yol=${dq(dbirlestir(hedef, f.name))}`);
    x.withCredentials = true;
    x.upload.onprogress = (e) => { if (e.lengthComputable) cubuk.style.width = (e.loaded / e.total * 100) + "%"; };
    x.onload = () => {
      if (x.status >= 200 && x.status < 300) { cubuk.style.width = "100%"; setTimeout(() => k.remove(), 1200); }
      else {
        let m = `Hata ${x.status}`;
        try { m = JSON.parse(x.responseText).hata || m; } catch (_) { /* json degil */ }
        if (x.status === 401) goster("giris");
        k.classList.add("hata"); k.firstChild.textContent = `${f.name} — ${m}`; setTimeout(() => k.remove(), 6000);
      }
      bitti();
    };
    x.onerror = () => { k.classList.add("hata"); k.firstChild.textContent = f.name + " — bağlantı hatası"; setTimeout(() => k.remove(), 6000); bitti(); };
    x.send(f);
  }
  siradaki();
}
$("#dDosya").onchange = (e) => { driveYukle([...e.target.files]); e.target.value = ""; };
let surukle = 0;
const driveGorunur = () => !$("#gDrive").hidden && $("#editor").hidden;
document.addEventListener("dragenter", (e) => { if (driveGorunur() && e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); surukle++; $("#gDrive").classList.add("uzerinde"); } });
document.addEventListener("dragover", (e) => { if (driveGorunur()) e.preventDefault(); });
document.addEventListener("dragleave", () => { if (--surukle <= 0) { surukle = 0; $("#gDrive").classList.remove("uzerinde"); } });
document.addEventListener("drop", (e) => {
  if (!driveGorunur()) return;
  e.preventDefault(); surukle = 0; $("#gDrive").classList.remove("uzerinde");
  if (e.dataTransfer?.files?.length) driveYukle([...e.dataTransfer.files]);
});
