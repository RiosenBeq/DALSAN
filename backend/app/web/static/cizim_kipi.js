// Sade / gelişmiş çizim kipi (kamera sayfası).
//
// NEDEN VAR — kamera sayfasında yedi ayrı araç yaşıyor: kareyi dondur, ekran
// görüntüsü yükle, alanları otomatik bul, çizime başla, dikdörtgen çiz, son
// köşeyi geri al, mesafe kalibrasyonu. Hepsi aynı anda ekrandayken ilk kez
// bölge çizen biri hangisine basacağını seçemiyor; oysa bölge çizmek için
// bunların yalnızca üçü gerekiyor.
//
// Sade kipte `data-gelismis` işaretli her şey GİZLENİR — ama DOM'dan
// SİLİNMEZ. Silinseydi kamera_detay.js açılışta o düğmeleri id ile arar,
// bulamaz ve sayfanın tamamı (çizim dahil) sessizce çalışmaz hale gelirdi.
// Gizleme CSS'tedir (stil.css → .kip-basit [data-gelismis]).
//
// Seçim tarayıcıda (localStorage) hatırlanır, SUNUCUDA saklanmaz: bu bir
// kayıt değil, o kişinin o bilgisayardaki ekran tercihi. Sunucuya yazılsaydı
// bir kullanıcının tercihi herkesin ekranını değiştirirdi.
(function () {
  "use strict";

  var ANAHTAR = "dalsan-cizim-kipi";
  var dugme = document.getElementById("kip-anahtari");
  if (!dugme) return;
  var not = document.getElementById("kip-notu");

  var BASIT_NOT =
    "Sade görünüm: bölge çizmek için gereken araçlar. Kareyi dondurma, " +
    "ekran görüntüsü yükleme, alanı otomatik bulma ve mesafe kalibrasyonu " +
    "için “Gelişmiş araçlar”a basın.";
  var GELISMIS_NOT =
    "Gelişmiş görünüm: tüm araçlar açık. Sayfa kalabalık geldiyse " +
    "“Sade görünüm”e dönebilirsiniz — çizdiğiniz bölgeler etkilenmez.";

  function oku() {
    try {
      return localStorage.getItem(ANAHTAR) === "gelismis";
    } catch (e) {
      // Gizli sekmede / site verisi kapalıyken localStorage okunamaz. Sayfa
      // yine çalışmalı: o oturumda sade kipte kalır.
      return false;
    }
  }

  function yaz(gelismis) {
    try {
      localStorage.setItem(ANAHTAR, gelismis ? "gelismis" : "basit");
    } catch (e) {
      /* hatırlanamadı; kip yine de bu sayfada geçerli */
    }
  }

  function uygula(gelismis) {
    var kok = document.documentElement;
    kok.classList.toggle("kip-gelismis", gelismis);
    kok.classList.toggle("kip-basit", !gelismis);
    dugme.textContent = gelismis ? "Sade görünüm" : "Gelişmiş araçlar";
    dugme.setAttribute("aria-pressed", gelismis ? "true" : "false");
    if (not) not.textContent = gelismis ? GELISMIS_NOT : BASIT_NOT;
  }

  // Açılıştaki sınıfı <head>'deki satır içi betik zaten koydu (gelişmiş
  // araçlar bir an görünüp kaybolmasın diye). Burada yalnızca düğmenin
  // yazısı ve not o sınıfla eşitlenir.
  uygula(oku());

  dugme.addEventListener("click", function () {
    var gelismis = !document.documentElement.classList.contains("kip-gelismis");
    yaz(gelismis);
    uygula(gelismis);
  });
})();
