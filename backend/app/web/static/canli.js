// Canlı olay akışı (SSE). Sayfada #canli-liste varsa son olayları listeler;
// her ihlalde Uyari.duyur() çağrılır (bant + isteğe bağlı ses/seslendirme).
// Hem Olaylar hem Ana Sayfa bu dosyayı kullanır — iki ayrı kopya kod olmasın.
(function () {
  var ONEMLER = ["critical", "high", "medium", "low"];
  var liste = document.getElementById("canli-liste");
  var durum = document.getElementById("canli-durum");
  if (!liste && !durum) return;

  function durumYaz(metin, sinif) {
    if (durum) {
      durum.textContent = metin;
      durum.className = "rozet " + sinif;
    }
  }

  var kaynak;
  try {
    kaynak = new EventSource("/olaylar/akis");
  } catch (e) {
    durumYaz("canlı akış açılamadı", "kirmizi");
    return;
  }

  kaynak.onopen = function () { durumYaz("canlı", "yesil"); };
  kaynak.onerror = function () { durumYaz("bağlantı koptu — yeniden deneniyor", "kirmizi"); };

  kaynak.onmessage = function (olay) {
    var veri;
    try {
      veri = JSON.parse(olay.data);
    } catch (e) {
      return;
    }
    // Süren bir olay bitti (kişi alandan çıktı, çift ayrıldı): satırdaki
    // "sürüyor" işareti süreye döner, o olayın bandı kapanır.
    if (veri.guncelleme === "bitti") {
      if (window.Uyari && window.Uyari.bitti) window.Uyari.bitti(veri.id);
      var isaret = liste && liste.querySelector('li[data-olay="' + Number(veri.id) + '"] .surec-hapi');
      if (isaret) {
        isaret.className = "surec-hapi bitti";
        isaret.textContent = "bitti" + (veri.sure_metni ? " · " + veri.sure_metni : "");
      }
      return;
    }
    if (window.Uyari) window.Uyari.duyur(veri);
    if (!liste) return;

    var bos = liste.querySelector(".bos");
    if (bos) bos.remove();

    // Metin DOM ile kurulur, innerHTML ile DEĞİL: kamera/bölge adı HTML olarak
    // yorumlanmamalı (kullanıcı verisi ekrana ham basılmaz).
    var satir = document.createElement("li");
    satir.className = veri.tip === "violation" ? "ihlal" : "sistem";
    satir.setAttribute("data-olay", String(Number(veri.id)));
    // Önem: satırın rengi ve başındaki hap (Kritik / Yüksek / Orta / Düşük).
    // Değer sunucunun sabit listesinden gelir; yine de sınıf adına yalnız
    // bilinen değer yazılır.
    if (veri.tip === "violation" && ONEMLER.indexOf(veri.onem) !== -1) {
      satir.classList.add("onem-" + veri.onem);
      var hap = document.createElement("span");
      hap.className = "onem-hapi onem-" + veri.onem;
      hap.textContent = veri.onem_adi || "";
      satir.appendChild(hap);
      satir.appendChild(document.createTextNode(" "));
    }
    var zaman = document.createElement("b");
    zaman.textContent = veri.zaman || "";
    satir.appendChild(zaman);
    satir.appendChild(
      document.createTextNode(" · " + (veri.kamera || "—") + " · " + (veri.ozet || "") + " · ")
    );
    var bag = document.createElement("a");
    bag.href = "/olaylar/" + veri.id;
    bag.textContent = "aç";
    satir.appendChild(bag);
    if (veri.suruyor) {
      var surec = document.createElement("span");
      surec.className = "surec-hapi suruyor";
      var nokta = document.createElement("span");
      nokta.className = "durum-noktasi";
      nokta.setAttribute("aria-hidden", "true");
      surec.appendChild(nokta);
      surec.appendChild(document.createTextNode("sürüyor"));
      satir.appendChild(document.createTextNode(" "));
      satir.appendChild(surec);
    }
    liste.prepend(satir);
    while (liste.children.length > 8) liste.removeChild(liste.lastChild);
  };
})();
