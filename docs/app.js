"use strict";
// API adresi: static/config.js (window.LAQ_API). Bos = arayuz ile ayni sunucu.
const API = (window.LAQ_API || "").replace(/\/$/, "");
const $ = (s) => document.querySelector(s);
let IS = null;          // sunucudaki is durumu
let LIMIT = {};
let zamanlayici = null;

async function api(yol, secenek = {}) {
  const r = await fetch(API + yol, { credentials: "include", ...secenek });
  if (r.status === 401 && !yol.endsWith("/giris")) { goster("giris"); throw new Error("Giriş gerekli"); }
  let veri = null;
  try { veri = await r.json(); } catch (_) { /* json degil */ }
  if (!r.ok) throw new Error((veri && veri.hata) || `Hata ${r.status}`);
  return veri;
}
function mesaj(t) { const e = $("#mesaj"); e.textContent = t || ""; e.hidden = !t; }
function goster(ad) { $("#giris").hidden = ad !== "giris"; $("#uygulama").hidden = ad !== "uygulama"; }

// ------------------------------------------------------------------ giris
$("#girisForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#girisHata").textContent = "";
  try {
    await api("/api/giris", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parola: $("#parola").value }) });
    $("#parola").value = "";
    await baslat();
  } catch (err) { $("#girisHata").textContent = err.message; }
});
$("#cikis").onclick = async () => { await api("/api/cikis", { method: "POST" }); goster("giris"); };

async function baslat() {
  try { const b = await api("/api/ben"); LIMIT = b.limit; } catch (_) { return; }
  goster("uygulama");
  $("#limitBilgi").textContent = `En fazla ${LIMIT.manken} manken, ${LIMIT.gomlek} gömlek; dosya başına ${LIMIT.dosya_mb} MB. İşler ${LIMIT.sakla_gun} gün sonra otomatik silinir.`;
  const kayitli = localStorage.getItem("laq_is");
  if (kayitli) { try { IS = await api("/api/is/" + kayitli); } catch (_) { IS = null; } }
  if (!IS) await yeniIs();
  ciz(); zamanla();
}
async function yeniIs() {
  IS = await api("/api/is", { method: "POST" });
  localStorage.setItem("laq_is", IS.id);
  ciz();
}
$("#yeniIs").onclick = async () => {
  if (IS && (IS.manken.length || IS.gomlek.length) && !confirm("Mevcut işi bırakıp yeni iş başlatılsın mı? (Eski iş sunucuda silinir.)")) return;
  if (IS) { try { await api("/api/is/" + IS.id, { method: "DELETE" }); } catch (_) { /* yok say */ } }
  await yeniIs(); mesaj("");
};

// ------------------------------------------------------------------ yukleme
function suruklePanel(kutu, tur) {
  const girdi = kutu.querySelector("input");
  girdi.addEventListener("change", () => { yukle(tur, [...girdi.files]); girdi.value = ""; });
  kutu.addEventListener("dragover", (e) => { e.preventDefault(); kutu.classList.add("uzerinde"); });
  kutu.addEventListener("dragleave", () => kutu.classList.remove("uzerinde"));
  kutu.addEventListener("drop", (e) => { e.preventDefault(); kutu.classList.remove("uzerinde"); yukle(tur, [...e.dataTransfer.files]); });
}
suruklePanel($("#mYukle"), "manken");
suruklePanel($("#gYukle"), "gomlek");

async function yukle(tur, dosyalar) {
  dosyalar = dosyalar.filter((f) => f.type.startsWith("image/"));
  for (let i = 0; i < dosyalar.length; i++) {
    mesaj(`Yükleniyor: ${i + 1}/${dosyalar.length} (${dosyalar[i].name})`);
    const fd = new FormData();
    fd.append("dosyalar", dosyalar[i]);
    try { IS = await api(`/api/is/${IS.id}/${tur}`, { method: "POST", body: fd }); ciz(); }
    catch (e) { mesaj(e.message); return; }
  }
  mesaj(""); zamanla();
}

// ------------------------------------------------------------------ cizim
const DURUM = { bekliyor: "sırada", hesaplaniyor: "hesaplanıyor…", hazir: "hazır", hata: "hata" };
function kart(tur, k, tiklaninca) {
  const d = document.createElement("div");
  d.className = "kart";
  const img = document.createElement("img");
  img.src = `${API}/api/is/${IS.id}/${tur}/${k.id}/temel.jpg`;
  img.loading = "lazy";
  const ad = document.createElement("div"); ad.className = "ad"; ad.textContent = k.ad;
  const r = document.createElement("span"); r.className = "rozet " + k.durum; r.textContent = DURUM[k.durum] || k.durum;
  if (k.hata) r.title = k.hata;
  d.append(img, ad, r);
  if (tur === "gomlek" && k.hex) { const o = document.createElement("span"); o.className = "ornek"; o.style.background = k.hex; o.title = k.hex; d.append(" ", o); }
  if (tiklaninca) img.onclick = tiklaninca;
  return d;
}
function silDugmesi(tur, k) {
  const b = document.createElement("button");
  b.className = "sil"; b.textContent = "×"; b.title = "Sil";
  b.onclick = async () => {
    try { IS = await api(`/api/is/${IS.id}/${tur}/${k.id}`, { method: "DELETE" }); ciz(); } catch (e) { mesaj(e.message); }
  };
  return b;
}
function ciz() {
  if (!IS) return;
  const m = $("#mListe"), g = $("#gListe"), mk = $("#maskeler");
  m.replaceChildren(); g.replaceChildren(); mk.replaceChildren();
  for (const k of IS.manken) {
    const c = kart("manken", k); c.append(silDugmesi("manken", k)); m.append(c);
    const mc = kart("manken", k, () => editorAc(k.id));
    if (k.durum === "hazir") mc.querySelector("img").src = `${API}/api/is/${IS.id}/manken/${k.id}/tarali.jpg?v=${k.v}`;
    mk.append(mc);
  }
  for (const k of IS.gomlek) { const c = kart("gomlek", k); c.append(silDugmesi("gomlek", k)); g.append(c); }
  const calisiyor = ["kuyrukta", "calisiyor"].includes(IS.uret.durum);
  const bekleyen = [...IS.manken, ...IS.gomlek].some((k) => k.durum === "bekliyor" || k.durum === "hesaplaniyor");
  $("#uret").disabled = calisiyor || !IS.manken.length || !IS.gomlek.length;
  $("#uret").textContent = calisiyor ? "Üretiliyor…" : bekleyen ? "Tüm görselleri üret (hesaplama bitince başlar)" : "Tüm görselleri üret";
  $("#ilerleme").hidden = IS.uret.durum === "yok";
  const u = IS.uret;
  $("#bar").max = Math.max(1, u.toplam); $("#bar").value = u.adim;
  $("#ilerlemeYazi").textContent = `${u.mesaj || ""} ${u.toplam ? `(${u.adim}/${u.toplam})` : ""}`;
  $("#indirSatir").hidden = !u.zip;
  $("#indir").href = `${API}/api/is/${IS.id}/zip`;
  if (u.durum === "hata") mesaj(u.mesaj);
}
$("#uret").onclick = async () => {
  try { IS = await api(`/api/is/${IS.id}/uret`, { method: "POST" }); mesaj(""); ciz(); zamanla(); } catch (e) { mesaj(e.message); }
};

function zamanla() {
  clearTimeout(zamanlayici);
  const is = IS && ([...IS.manken, ...IS.gomlek].some((k) => k.durum === "bekliyor" || k.durum === "hesaplaniyor") || ["kuyrukta", "calisiyor"].includes(IS.uret.durum));
  if (!is) return;
  zamanlayici = setTimeout(async () => {
    try {
      const onceki = JSON.stringify(IS);
      IS = await api("/api/is/" + IS.id);
      if (JSON.stringify(IS) !== onceki) { if ($("#editor").hidden) ciz(); editorGuncelle(); }
    } catch (_) { /* gecici ag hatasi */ }
    zamanla();
  }, 1500);
}

// ================================================================== EDITOR
const ed = { id: null, w: 0, h: 0, mod: "ekle", labels: null, dugme: [], geri: [], olcek: 1, tx: 0, ty: 0, izler: true, orijinal: false,
             imgData: null, ptr: new Map(), cizim: null, pinch: null, bekliyor: false };
const gorus = $("#gorus"), sahne = $("#sahne"), edImg = $("#edImg"), ov = $("#edOv"), dg = $("#edDg"), halka = $("#halka");

async function editorAc(mid) {
  const m = IS.manken.find((k) => k.id === mid);
  if (!m || m.durum === "bekliyor" || m.durum === "hesaplaniyor") { mesaj("Bu fotoğrafın maskesi henüz hesaplanıyor, birkaç saniye bekleyin."); return; }
  if (["kuyrukta", "calisiyor"].includes(IS.uret.durum)) { mesaj("Üretim sürerken düzenlenemez."); return; }
  ed.id = mid; ed.w = m.w; ed.h = m.h; ed.geri = []; ed.orijinal = false; ed.bekliyor = false;
  const bin = await fetch(`${API}/api/is/${IS.id}/manken/${mid}/duzeltme.bin`, { credentials: "include", cache: "no-store" });
  ed.labels = new Uint8Array(await bin.arrayBuffer());
  if (ed.labels.length !== ed.w * ed.h) ed.labels = new Uint8Array(ed.w * ed.h);
  ed.dugme = JSON.parse(JSON.stringify(m.dugme || []));
  for (const c of [ov, dg]) { c.width = ed.w; c.height = ed.h; }
  sahne.style.width = ed.w + "px"; sahne.style.height = ed.h + "px";
  ed.imgData = ov.getContext("2d").createImageData(ed.w, ed.h);
  for (let i = 0; i < ed.labels.length; i++) boyaPiksel(i);
  ov.getContext("2d").putImageData(ed.imgData, 0, 0);
  resimYukle(m);
  $("#editor").hidden = false; document.body.style.overflow = "hidden";
  sigdir(); dugmeCiz(); modSec("ekle"); edDurum("");
}
function resimYukle(m) {
  edImg.src = ed.orijinal ? `${API}/api/is/${IS.id}/manken/${m.id}/temel.jpg` : `${API}/api/is/${IS.id}/manken/${m.id}/tarali.jpg?v=${m.v}`;
  $("#goster").textContent = ed.orijinal ? "Taralı" : "Orijinal";
}
function sigdir() {
  const r = gorus.getBoundingClientRect();
  ed.olcek = Math.min(r.width / ed.w, r.height / ed.h);
  ed.tx = (r.width - ed.w * ed.olcek) / 2; ed.ty = (r.height - ed.h * ed.olcek) / 2;
  donustur();
}
function donustur() { sahne.style.transform = `translate(${ed.tx}px,${ed.ty}px) scale(${ed.olcek})`; }
function edDurum(t) { $("#edDurum").textContent = t; }

function boyaPiksel(i) {
  const v = ed.labels[i], d = ed.imgData.data, j = i * 4;
  if (v === 1) { d[j] = 255; d[j + 1] = 170; d[j + 2] = 0; d[j + 3] = 120; }
  else if (v === 2) { d[j] = 0; d[j + 1] = 170; d[j + 2] = 255; d[j + 3] = 120; }
  else { d[j] = d[j + 1] = d[j + 2] = d[j + 3] = 0; }
}
function nokta(x, y, r, deger) {
  const x0 = Math.max(0, Math.floor(x - r)), x1 = Math.min(ed.w - 1, Math.ceil(x + r));
  const y0 = Math.max(0, Math.floor(y - r)), y1 = Math.min(ed.h - 1, Math.ceil(y + r));
  if (x1 < x0 || y1 < y0) return;
  for (let yy = y0; yy <= y1; yy++) for (let xx = x0; xx <= x1; xx++) {
    if ((xx - x) ** 2 + (yy - y) ** 2 <= r * r) { const i = yy * ed.w + xx; ed.labels[i] = deger; boyaPiksel(i); }
  }
  ov.getContext("2d").putImageData(ed.imgData, 0, 0, x0, y0, x1 - x0 + 1, y1 - y0 + 1);
}
function cizgi(a, b, r, deger) {
  const adim = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y) / Math.max(1, r / 3));
  for (let t = 0; t <= adim; t++) nokta(a.x + (b.x - a.x) * t / adim, a.y + (b.y - a.y) * t / adim, r, deger);
}
function dugmeCiz() {
  const c = dg.getContext("2d");
  c.clearRect(0, 0, ed.w, ed.h);
  c.lineWidth = Math.max(1.5, 2 / ed.olcek);
  for (const [x, y, r, tip] of ed.dugme) {
    c.strokeStyle = tip === "c" ? "#38bdf8" : "#4ade80";
    c.beginPath(); c.arc(x, y, r, 0, 7); c.stroke();
  }
}
function anlik() { return { labels: ed.labels.slice(), dugme: JSON.parse(JSON.stringify(ed.dugme)) }; }
function geriKoy() { ed.geri.push(anlik()); if (ed.geri.length > 30) ed.geri.shift(); }
$("#geri").onclick = () => {
  const s = ed.geri.pop(); if (!s) return;
  ed.labels = s.labels; ed.dugme = s.dugme;
  for (let i = 0; i < ed.labels.length; i++) boyaPiksel(i);
  ov.getContext("2d").putImageData(ed.imgData, 0, 0); dugmeCiz();
};

function modSec(m) {
  ed.mod = m;
  document.querySelectorAll("#arac .mod").forEach((b) => b.classList.toggle("aktif", b.dataset.mod === m));
  const dugme = m === "k" || m === "c";
  if (dugme) $("#boyut").value = m === "k" ? 7 : 5;
  gorus.style.cursor = m === "kaydir" ? "grab" : "crosshair";
  halkaGuncelle();
}
document.querySelectorAll("#arac .mod").forEach((b) => (b.onclick = () => modSec(b.dataset.mod)));
$("#boyut").oninput = halkaGuncelle;
$("#goster").onclick = () => { ed.orijinal = !ed.orijinal; resimYukle(IS.manken.find((k) => k.id === ed.id)); };
$("#izler").onclick = () => { ed.izler = !ed.izler; ov.style.display = dg.style.display = ed.izler ? "" : "none"; $("#izler").textContent = "İzler: " + (ed.izler ? "açık" : "kapalı"); };
$("#kapat").onclick = () => {
  if (ed.geri.length && !confirm("Kaydedilmemiş değişiklikler var. Kapatılsın mı?")) return;
  $("#editor").hidden = true; document.body.style.overflow = ""; ed.id = null; ciz();
};

// ---- nokta -> resim koordinati
function resimKonum(e) {
  const r = gorus.getBoundingClientRect();
  return { x: (e.clientX - r.left - ed.tx) / ed.olcek, y: (e.clientY - r.top - ed.ty) / ed.olcek };
}
function fircaYaricap() { return +$("#boyut").value; }
function halkaGuncelle(e) {
  const brush = ed.mod === "ekle" || ed.mod === "cikar", dugme = ed.mod === "k" || ed.mod === "c";
  if (!(brush || dugme) || (e && e.pointerType === "touch")) { halka.style.display = "none"; return; }
  const d = fircaYaricap() * 2 * ed.olcek;
  halka.style.width = halka.style.height = d + "px";
  if (e) { const r = gorus.getBoundingClientRect(); halka.style.left = e.clientX - r.left + "px"; halka.style.top = e.clientY - r.top + "px"; halka.style.display = "block"; }
}
gorus.addEventListener("contextmenu", (e) => e.preventDefault());
gorus.addEventListener("pointerleave", () => { halka.style.display = "none"; });
gorus.addEventListener("wheel", (e) => {
  e.preventDefault();
  const r = gorus.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
  zoom(Math.exp(-e.deltaY * 0.0015), px, py);
  halkaGuncelle(e);
}, { passive: false });
function zoom(carpan, px, py) {
  const yeni = Math.min(Math.max(ed.olcek * carpan, 0.2), 12);
  carpan = yeni / ed.olcek;
  ed.tx = px - (px - ed.tx) * carpan; ed.ty = py - (py - ed.ty) * carpan; ed.olcek = yeni;
  donustur(); halkaGuncelle(); dugmeCiz();
}

gorus.addEventListener("pointerdown", (e) => {
  gorus.setPointerCapture(e.pointerId);
  ed.ptr.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (ed.ptr.size === 2) {                      // iki parmak: yakinlastir/kaydir; devam eden darbeyi birak
    ed.cizim = null;
    const [a, b] = [...ed.ptr.values()];
    ed.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 };
    return;
  }
  if (ed.ptr.size > 2) return;
  const kaydir = ed.mod === "kaydir" || e.button === 1;
  if (kaydir) { ed.cizim = { tur: "kaydir", x: e.clientX, y: e.clientY }; gorus.style.cursor = "grabbing"; return; }
  const p = resimKonum(e);
  if (ed.mod === "ekle" || ed.mod === "cikar") {
    geriKoy();
    const sag = e.button === 2;                 // sag tus = ters islem (masaustu aracindaki gibi)
    const deger = (ed.mod === "ekle") !== sag ? 1 : 2;
    ed.cizim = { tur: "firca", deger, son: p };
    nokta(p.x, p.y, fircaYaricap(), deger);
  } else {
    const r = fircaYaricap();
    const var_ = ed.dugme.findIndex(([x, y, rr]) => Math.hypot(x - p.x, y - p.y) <= Math.max(rr, 4) + 3);
    geriKoy();
    if (var_ >= 0) ed.dugme.splice(var_, 1);   // var olan duguneye tikla = sil
    else if (p.x >= 0 && p.y >= 0 && p.x < ed.w && p.y < ed.h) ed.dugme.push([Math.round(p.x), Math.round(p.y), r, ed.mod]);
    dugmeCiz();
  }
});
gorus.addEventListener("pointermove", (e) => {
  halkaGuncelle(e);
  const onceki = ed.ptr.get(e.pointerId);
  if (!onceki) return;
  ed.ptr.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (ed.ptr.size === 2 && ed.pinch) {
    const [a, b] = [...ed.ptr.values()];
    const d = Math.hypot(a.x - b.x, a.y - b.y), cx = (a.x + b.x) / 2, cy = (a.y + b.y) / 2;
    const r = gorus.getBoundingClientRect();
    ed.tx += cx - ed.pinch.cx; ed.ty += cy - ed.pinch.cy;
    zoom(d / ed.pinch.d, cx - r.left, cy - r.top);
    ed.pinch = { d, cx, cy };
    return;
  }
  if (!ed.cizim) return;
  if (ed.cizim.tur === "kaydir") {
    ed.tx += e.clientX - ed.cizim.x; ed.ty += e.clientY - ed.cizim.y; ed.cizim.x = e.clientX; ed.cizim.y = e.clientY; donustur();
  } else if (ed.cizim.tur === "firca") {
    const p = resimKonum(e);
    cizgi(ed.cizim.son, p, fircaYaricap(), ed.cizim.deger); ed.cizim.son = p;
  }
});
function birak(e) {
  ed.ptr.delete(e.pointerId);
  if (ed.ptr.size < 2) ed.pinch = null;
  if (ed.ptr.size === 0) { ed.cizim = null; gorus.style.cursor = ed.mod === "kaydir" ? "grab" : "crosshair"; }
}
gorus.addEventListener("pointerup", birak);
gorus.addEventListener("pointercancel", birak);
window.addEventListener("resize", () => { if (!$("#editor").hidden) sigdir(); });
window.addEventListener("keydown", (e) => {
  if ($("#editor").hidden) return;
  if ((e.key === "z" || e.key === "Z") && !e.target.matches("input")) $("#geri").click();
  if (e.key === "[") { $("#boyut").value = Math.max(2, fircaYaricap() - 2); halkaGuncelle(); }
  if (e.key === "]") { $("#boyut").value = Math.min(60, fircaYaricap() + 2); halkaGuncelle(); }
});

// ---- kaydet -> sunucu yeniden hesaplar
$("#kaydet").onclick = async () => {
  const fd = new FormData();
  fd.append("duzelt", new Blob([ed.labels]), "duzelt.bin");
  fd.append("dugme", JSON.stringify(ed.dugme));
  $("#kaydet").disabled = true; edDurum("Gönderiliyor…");
  try {
    IS = await api(`/api/is/${IS.id}/manken/${ed.id}/duzeltme`, { method: "PUT", body: fd });
    ed.geri = []; ed.bekliyor = true; edDurum("Hesaplanıyor (≈15 sn)…"); zamanla();
  } catch (e) { edDurum(e.message); $("#kaydet").disabled = false; }
};
function editorGuncelle() {
  if (!ed.bekliyor || $("#editor").hidden) return;
  const m = IS.manken.find((k) => k.id === ed.id);
  if (!m) return;
  if (m.durum === "hazir") {
    ed.bekliyor = false; $("#kaydet").disabled = false; edDurum("Güncellendi ✓");
    ed.orijinal = false; resimYukle(m); dugmeCiz();
  } else if (m.durum === "hata") { ed.bekliyor = false; $("#kaydet").disabled = false; edDurum("Hata: " + (m.hata || "")); }
}

baslat();
