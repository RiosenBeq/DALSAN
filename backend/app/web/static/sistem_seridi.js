// Sistem şeridi (docs/17 §11): komuta ekranlarının üstünde, 5 sn'de bir
// /saglik?ayrinti=1'e bakar.
//
// Kırmızı: uyarı üretilmiyor ya da kaydedilmiyor (analiz takıldı / durdu, model
// yüklenemedi, olay yazılamıyor), kritik bir kural çalışmıyor, bir kameradan
// görüntü gelmiyor; Faz 4'te sesli uyarı hiçbir kanala ulaşmıyor.
// Gri: durum doğrulanamıyor (sunucuya ulaşılamıyor, model yükleniyor; Faz 4'te
// sesli uyarının ulaştığı doğrulanamıyor).
//
// Her şey yolundayken GİZLİDİR ve yeşile dönmez: ekranın kendisi uyarı
// garantisine sayılmaz; bakan bir tarayıcının varlığı "sorun yok" demek değil.
(function () {
  var serit = document.getElementById("sistem-seridi");
  if (!serit) return;
  var yazi = serit.querySelector(".serit-metni");
  // Kod → Türkçe metin sunucudan gelir (web/ortak.py SAGLIK_SORUN_METINLERI):
  // metin iki yerde yazılmaz.
  // "Hazır değil"i açıklayan kodlar da oradan (web/rotalar.py
  // HAZIRLIGI_BOZAN_SORUNLAR): kalibrasyon bekleyen kural gibi bir yapılandırma
  // eksiği, analizin hiç çalışmadığını gizlememeli.
  var metinler = oku("data-metinler", {});
  var bozanlar = oku("data-bozanlar", []);
  var sonMetin = null;

  function oku(ad, varsayilan) {
    try {
      return JSON.parse(serit.getAttribute(ad) || "null") || varsayilan;
    } catch (e) {
      return varsayilan; // bozuk öznitelik: şerit yine çalışır, kodlar yazılmaz
    }
  }

  function goster(metin, renk) {
    // Yalnız değişince dokunulur: ekran okuyucu (aria-live) her 5 sn'de
    // aynı cümleyi yeniden okumasın.
    if (metin === sonMetin) return;
    sonMetin = metin;
    if (!metin) {
      serit.hidden = true;
      return;
    }
    yazi.textContent = metin;
    serit.className = "sistem-seridi " + renk;
    serit.hidden = false;
  }

  function degerlendir(govde) {
    var sorunlar = govde.sorunlar || [];
    var kirmizi = [];
    var gri = [];
    sorunlar.forEach(function (kod) {
      if (metinler[kod]) kirmizi.push(metinler[kod]);
    });
    var aciklandi = sorunlar.some(function (kod) {
      return bozanlar.indexOf(kod) !== -1;
    });
    if (govde.hazir === false && !aciklandi) {
      if (govde.model === "yukleniyor" || govde.model === "indiriliyor") {
        gri.push("Analiz hazırlanıyor — tespit modeli yükleniyor");
      } else {
        kirmizi.unshift(
          govde.analiz ? "Sistem hazır değil — uyarı üretilemiyor" : "Analiz çalışmıyor — uyarı üretilmiyor"
        );
      }
    }
    var kopuk = (govde.kameralar || []).filter(function (k) {
      return k.durum === "offline";
    }).length;
    if (kopuk) kirmizi.push(kopuk + " kameradan görüntü gelmiyor");
    // uyari_garantisi Faz 4'te gelir; yokken (undefined) hiçbir şey söylenmez
    if (govde.uyari_garantisi === false) kirmizi.push("Sesli uyarı hiçbir kanala ulaşmıyor");
    if (govde.uyari_garantisi === null) gri.push("Sesli uyarının ulaştığı doğrulanamıyor");
    if (kirmizi.length) return [kirmizi.concat(gri).join(" · "), "kirmizi"];
    if (gri.length) return [gri.join(" · "), "gri"];
    return [null, ""];
  }

  function yenile() {
    fetch("/saglik?ayrinti=1", { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (yanit) {
        if (!yanit.ok) throw new Error("HTTP " + yanit.status);
        return yanit.json();
      })
      .then(function (govde) {
        var sonuc = degerlendir(govde);
        goster(sonuc[0], sonuc[1]);
      })
      .catch(function () {
        goster("Sistem durumu alınamıyor — sunucuya ulaşılamıyor", "gri");
      });
  }

  yenile();
  setInterval(yenile, 5000);
})();
