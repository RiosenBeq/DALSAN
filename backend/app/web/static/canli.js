// Canlı olay akışı (SSE). Sayfada #canli-liste varsa son olayları listeler;
// her ihlalde Uyari.duyur() çağrılır (bant + isteğe bağlı ses/seslendirme).
// Hem Olaylar hem Ana Sayfa bu dosyayı kullanır — iki ayrı kopya kod olmasın.
(function () {
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
    if (window.Uyari) window.Uyari.duyur(veri);
    if (!liste) return;

    var bos = liste.querySelector(".bos");
    if (bos) bos.remove();

    // Metin DOM ile kurulur, innerHTML ile DEĞİL: kamera/bölge adı HTML olarak
    // yorumlanmamalı (kullanıcı verisi ekrana ham basılmaz).
    var satir = document.createElement("li");
    satir.className = veri.tip === "violation" ? "ihlal" : "sistem";
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
    liste.prepend(satir);
    while (liste.children.length > 8) liste.removeChild(liste.lastChild);
  };
})();
