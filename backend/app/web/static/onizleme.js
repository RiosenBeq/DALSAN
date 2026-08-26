// Canlı önizleme: data-kamera taşıyan her <img> 1 sn'de bir yenilenir.
// Sunucu 204 dönerse (henüz kare yok) mevcut görüntü korunur.
(function () {
  var resimler = document.querySelectorAll("img.canli-onizleme[data-kamera]");
  if (resimler.length === 0) return;

  function yenile(resim) {
    var kamera = resim.dataset.kamera;
    fetch("/kameralar/" + kamera + "/onizleme.jpg", { cache: "no-store" })
      .then(function (yanit) {
        if (yanit.status === 204) {
          var durum = document.getElementById("kare-durumu");
          if (durum) durum.textContent =
            "Henüz kare gelmedi — kamera bağlanıyor olabilir (ilk bağlantı 30 sn sürebilir).";
          return null;
        }
        var durum2 = document.getElementById("kare-durumu");
        if (durum2) durum2.textContent = "";
        return yanit.blob();
      })
      .then(function (veri) {
        if (!veri) return;
        var eski = resim.dataset.sonUrl;
        resim.src = URL.createObjectURL(veri);
        if (eski) URL.revokeObjectURL(eski);
        resim.dataset.sonUrl = resim.src;
      })
      .catch(function () { /* ağ hatasında bir sonraki tur dener */ });
  }

  resimler.forEach(function (resim) {
    setInterval(function () { yenile(resim); }, 1000);
  });
})();
