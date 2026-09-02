// Canlı önizleme: data-kamera taşıyan her <img> 1 sn'de bir yenilenir.
// Sunucu 204 dönerse (henüz kare yok) görüntü boş kalır, "bekleniyor" yazısı durur;
// ilk kare gelince yazı kalkar. Kırık resim simgesi hiç görünmez.
//
// Kamera sayfasında ayrıca #kare-durumu[data-kamera] varsa 2 sn'de bir
// durum.json sorulur: bağlanıyor / çevrimiçi / çevrimdışı + bağlanamama SEBEBİ.
(function () {
  var resimler = document.querySelectorAll("img.canli-onizleme[data-kamera]");

  function yenile(resim) {
    var kamera = resim.dataset.kamera;
    fetch("/kameralar/" + kamera + "/onizleme.jpg", { cache: "no-store" })
      .then(function (yanit) {
        if (yanit.status !== 200) return null;
        return yanit.blob();
      })
      .then(function (veri) {
        if (!veri) return;
        var eski = resim.dataset.sonUrl;
        resim.src = URL.createObjectURL(veri);
        if (eski) URL.revokeObjectURL(eski);
        resim.dataset.sonUrl = resim.src;
        resim.classList.add("dolu");
        var kutu = resim.closest(".onizleme-kutu");
        if (kutu) kutu.classList.add("dolu");
      })
      .catch(function () { /* ağ hatasında bir sonraki tur dener */ });
  }

  resimler.forEach(function (resim) {
    yenile(resim);
    setInterval(function () { yenile(resim); }, 1000);
  });

  // --- canlı durum satırı (yalnız kamera detay sayfası) ---
  var durumSatiri = document.getElementById("kare-durumu");
  if (!durumSatiri || !durumSatiri.dataset.kamera) return;
  var rozet = document.getElementById("durum-rozeti");
  var ROZETLER = {
    online: ["çevrimiçi", "yesil"],
    connecting: ["bağlanıyor", "sari"],
    offline: ["çevrimdışı", "kirmizi"],
    pasif: ["pasif", "gri"],
    kapali: ["analiz kapalı", "gri"]
  };

  function durumuGuncelle() {
    fetch("/kameralar/" + durumSatiri.dataset.kamera + "/durum.json", { cache: "no-store" })
      .then(function (yanit) { return yanit.ok ? yanit.json() : null; })
      .then(function (veri) {
        if (!veri) return;
        var metin = veri.mesaj || "";
        if (veri.son_deneme && veri.durum !== "online") metin += " (son deneme: " + veri.son_deneme + ")";
        durumSatiri.textContent = metin;
        durumSatiri.className = veri.durum === "offline" ? "hata-mesaji" : "not";
        var r = ROZETLER[veri.durum];
        if (rozet && r) { rozet.textContent = r[0]; rozet.className = "rozet " + r[1]; }
      })
      .catch(function () { /* bir sonraki tur */ });
  }
  durumuGuncelle();
  setInterval(durumuGuncelle, 2000);
})();
