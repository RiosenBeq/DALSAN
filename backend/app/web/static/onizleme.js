// Canlı önizleme: data-kamera taşıyan her <img> 1 sn'de bir yenilenir.
// Sunucu 204 dönerse (henüz kare yok) görüntü boş kalır, "bekleniyor" yazısı durur;
// ilk kare gelince yazı kalkar. Kırık resim simgesi hiç görünmez.
//
// Kamera sayfasında ayrıca #kare-durumu[data-kamera] varsa 2 sn'de bir
// durum.json sorulur: bağlanıyor / çevrimiçi / çevrimdışı + bağlanamama SEBEBİ.
(function () {
  var resimler = document.querySelectorAll("img.canli-onizleme[data-kamera]");

  // data-bolgesiz taşıyan görüntüye bölgeleri ÇİZİLMEMİŞ kare istenir: bölge
  // çizim sayfası bölgeleri kendi tuvaline çizer, sunucu da çizerse aynı bölge
  // ekranda iki kez (iki ayrı çizgi hâlinde) görünür.
  function adres(resim) {
    var yol = "/kameralar/" + resim.dataset.kamera + "/onizleme.jpg";
    return resim.dataset.bolgesiz === "1" ? yol + "?bolgesiz=1" : yol;
  }

  function yenile(resim) {
    fetch(adres(resim), { cache: "no-store" })
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
  var sayimKutusu = document.getElementById("canli-sayim");
  var kaliteKutusu = document.getElementById("kalite-uyarisi");
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
        if (sayimKutusu) sayimiYaz(veri.sayim_tr || {});
        if (kaliteKutusu) {
          var kalite = veri.kalite || {};
          kaliteKutusu.textContent = kalite.mesaj || "";
          kaliteKutusu.hidden = !kalite.mesaj;
        }
      })
      .catch(function () { /* bir sonraki tur */ });
  }
  function sayimiYaz(sayim) {
    var adlar = Object.keys(sayim);
    sayimKutusu.textContent = "";
    if (adlar.length === 0) {
      var bos = document.createElement("div");
      bos.className = "sayim-kutu bos-sayim";
      bos.appendChild(Object.assign(document.createElement("span"), {
        className: "sayi", textContent: "—" }));
      bos.appendChild(Object.assign(document.createElement("span"), {
        textContent: "şu an görünen nesne yok" }));
      sayimKutusu.appendChild(bos);
      return;
    }
    adlar.sort().forEach(function (ad) {
      var kutu = document.createElement("div");
      kutu.className = "sayim-kutu";
      kutu.appendChild(Object.assign(document.createElement("span"), {
        className: "sayi", textContent: String(sayim[ad]) }));
      kutu.appendChild(Object.assign(document.createElement("span"), { textContent: ad }));
      sayimKutusu.appendChild(kutu);
    });
  }

  durumuGuncelle();
  setInterval(durumuGuncelle, 2000);
})();
