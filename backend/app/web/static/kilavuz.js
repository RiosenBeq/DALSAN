/* Kılavuz yardımcıları — İKİ kabuğun da (temel.html ve komuta_temel.html)
 * kullandığı TEK dosya:
 *
 *   1) Ekranın üstündeki açıklama şeridini gizleme/gösterme. Tercih yalnızca
 *      bu tarayıcıda saklanır (localStorage) — sunucuya hiçbir şey yazılmaz.
 *   2) Karmaşık alanların yanındaki "?" ipucu balonları.
 *
 * Kütüphane yok, derleme adımı yok (CLAUDE.md §4). Bu dosya hiç yüklenmese
 * bile ekran eksiksiz çalışır: şerit açık kalır, ipucu metinleri gizli kalır.
 */
(function () {
  "use strict";

  // ==================================================================
  // 1) AÇIKLAMA ŞERİDİ
  // ==================================================================

  var ANAHTAR_ONEKI = "dalsan-serit-";
  var GIZLI = "gizli";

  function tercihOku(ekran) {
    try {
      return window.localStorage.getItem(ANAHTAR_ONEKI + ekran);
    } catch (hata) {
      // Gizli sekmede ya da site verisi engelliyken localStorage okumak hata
      // fırlatır. Tercih okunamıyorsa doğru davranış açıklamayı GÖSTERMEKtir:
      // kılavuz metnini kaybetmek, gereksiz göstermekten kötüdür.
      return null;
    }
  }

  function tercihYaz(ekran, deger) {
    try {
      window.localStorage.setItem(ANAHTAR_ONEKI + ekran, deger);
      return true;
    } catch (hata) {
      // Yazılamadıysa şerit yine de bu sayfada gizlenir; yalnızca bir sonraki
      // açılışta geri gelir. Kullanıcıya hata göstermeye değmez.
      return false;
    }
  }

  function seritiAyarla(ekran, gizliMi) {
    var serit = document.querySelector('[data-serit="' + ekran + '"]');
    var acici = document.querySelector('[data-serit-ac="' + ekran + '"]');
    if (serit) serit.hidden = gizliMi;
    if (acici) acici.hidden = !gizliMi;
  }

  var acikSerit = document.querySelector("[data-serit]");
  if (acikSerit) {
    var ekranAdi = acikSerit.getAttribute("data-serit");
    if (tercihOku(ekranAdi) === GIZLI) seritiAyarla(ekranAdi, true);
  }

  // ==================================================================
  // 2) İPUCU BALONLARI
  // ==================================================================
  //
  // Balon bir <button>'ın yanındaki <span>'dir: düğme olduğu için klavyeyle
  // (Tab + Enter/Boşluk) de açılır. Aynı anda yalnızca bir balon açık kalır.

  function tumBalonlariKapat(haric) {
    var acikDugmeler = document.querySelectorAll('.ipucu-dugme[aria-expanded="true"]');
    for (var i = 0; i < acikDugmeler.length; i++) {
      if (acikDugmeler[i] === haric) continue;
      acikDugmeler[i].setAttribute("aria-expanded", "false");
      var balon = document.getElementById(acikDugmeler[i].getAttribute("aria-controls"));
      if (balon) balon.hidden = true;
    }
  }

  // Tek dinleyici (olay delegasyonu): ipucu düğmeleri sayfanın her yerinde
  // olabilir ve bazıları sonradan gelen içerikte bulunur.
  document.addEventListener("click", function (olay) {
    var hedef = olay.target;
    if (!hedef || !hedef.closest) return;

    var kapat = hedef.closest("[data-serit-kapat]");
    if (kapat) {
      var kapatilan = kapat.getAttribute("data-serit-kapat");
      tercihYaz(kapatilan, GIZLI);
      seritiAyarla(kapatilan, true);
      var geriDugmesi = document.querySelector('[data-serit-ac="' + kapatilan + '"]');
      if (geriDugmesi) geriDugmesi.focus();
      return;
    }

    var ac = hedef.closest("[data-serit-ac]");
    if (ac) {
      var acilan = ac.getAttribute("data-serit-ac");
      tercihYaz(acilan, "acik");
      seritiAyarla(acilan, false);
      return;
    }

    var dugme = hedef.closest(".ipucu-dugme");
    if (dugme) {
      // Bazı ipuçları bir <label>'ın içindedir. Varsayılan davranışı durdurmazsak
      // tıklama etikete geçer ve kullanıcı farkında olmadan onay kutusunu
      // değiştirir — açıklamaya bakmak ayarı değiştirmemeli.
      olay.preventDefault();
      var acikti = dugme.getAttribute("aria-expanded") === "true";
      tumBalonlariKapat(dugme);
      dugme.setAttribute("aria-expanded", acikti ? "false" : "true");
      var balonu = document.getElementById(dugme.getAttribute("aria-controls"));
      if (balonu) balonu.hidden = acikti;
      return;
    }

    // Balonun kendi içine tıklamak (metni seçmek) onu kapatmasın.
    if (hedef.closest(".ipucu-balon")) return;
    tumBalonlariKapat(null);
  });

  document.addEventListener("keydown", function (olay) {
    if (olay.key !== "Escape") return;
    tumBalonlariKapat(null);
  });
})();
