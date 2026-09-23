// Ekran uyarısı: ihlalde görünen bir bant + (isteğe bağlı) sesli uyarı ve
// Türkçe seslendirme. Anons sistemi sahaya bağlanana kadar (docs/08 R3) ihlali
// duyuran tek yol budur; bağlandıktan sonra da ekran başındaki kişi için kalır.
//
// Ses neden bu kadar dikkatli kuruluyor: tarayıcılar, kullanıcı sayfaya bir kez
// tıklamadan ses çalmayı engeller. Her uyarıda yeni bir AudioContext açan kod
// sessizce çalışmaz ve kimse fark etmez. Bu yüzden TEK bağlam kurulur, ilk
// kullanıcı hareketinde uyandırılır ve durumu ekranda yazılır.
window.Uyari = (function () {
  var SES_ANAHTARI = "dalsan-uyari-sesi";
  var KONUSMA_ANAHTARI = "dalsan-uyari-konusma";
  var baglam = null;
  var kutu = null;

  function ayarOku(anahtar) {
    try {
      return window.localStorage.getItem(anahtar) === "1";
    } catch (e) {
      return false; // gizli sekmede localStorage kapalı olabilir
    }
  }

  function ayarYaz(anahtar, acik) {
    try {
      window.localStorage.setItem(anahtar, acik ? "1" : "0");
    } catch (e) { /* kaydedilemiyorsa yalnızca bu oturum için geçerli */ }
  }

  function baglamAl() {
    if (baglam) return baglam;
    var Yapici = window.AudioContext || window.webkitAudioContext;
    if (!Yapici) return null;
    try {
      baglam = new Yapici();
    } catch (e) {
      return null;
    }
    return baglam;
  }

  // Tarayıcı kuralı: ses ancak gerçek bir kullanıcı hareketinden sonra çalar.
  // İlk tıklama/tuşta bağlamı uyandır; sonrası sessizce çalışır.
  function uyandir() {
    var b = baglamAl();
    if (b && b.state === "suspended") b.resume();
  }
  document.addEventListener("click", uyandir, { once: false });
  document.addEventListener("keydown", uyandir, { once: false });

  function sesCal() {
    var b = baglamAl();
    if (!b) return;
    if (b.state === "suspended") b.resume();
    try {
      var osilator = b.createOscillator();
      var kazanc = b.createGain();
      osilator.type = "square";
      osilator.frequency.value = 880;
      kazanc.gain.value = 0.08;
      osilator.connect(kazanc);
      kazanc.connect(b.destination);
      osilator.start();
      // İki kısa bip: tek uzun sesten daha dikkat çekicidir
      osilator.frequency.setValueAtTime(880, b.currentTime);
      osilator.frequency.setValueAtTime(660, b.currentTime + 0.18);
      osilator.stop(b.currentTime + 0.34);
    } catch (e) { /* ses çalınamadıysa uyarı yine de görünür */ }
  }

  function seslendir(metin) {
    if (!window.speechSynthesis) return;
    try {
      var soz = new window.SpeechSynthesisUtterance(metin);
      soz.lang = "tr-TR";
      soz.rate = 1.0;
      window.speechSynthesis.speak(soz);
    } catch (e) { /* seslendirme yoksa sessizce geç */ }
  }

  // Şu an bantta görünen olay: {id, onem}. Kritik bant daha hafif bir olayla
  // EZİLMEZ ve kendiliğinden kaybolmaz (docs/17 §11): olay bitince ya da
  // üstüne tıklanınca kapanır.
  var gosterilen = null;

  function kutuAl() {
    if (kutu) return kutu;
    kutu = document.createElement("div");
    kutu.className = "uyari-bandi";
    kutu.hidden = true;
    kutu.title = "Kapatmak için tıklayın";
    kutu.addEventListener("click", gizle);
    document.body.appendChild(kutu);
    return kutu;
  }

  function gizle() {
    var k = kutuAl();
    clearTimeout(k._zamanlayici);
    k.hidden = true;
    gosterilen = null;
  }

  // Bandın rengi olayın önemidir (docs/17 §11). Sınıf adına yalnız bilinen
  // değer yazılır; önemsiz (eski) olay varsayılan kırmızıda kalır.
  var ONEMLER = ["critical", "high", "medium", "low"];

  function goster(veri) {
    var k = kutuAl();
    if (gosterilen && gosterilen.onem === "critical" && veri.onem !== "critical") return;
    k.textContent = "⚠ " + (veri.kamera || "Kamera") + " — " + (veri.ozet || "İhlal");
    k.className = "uyari-bandi" + (ONEMLER.indexOf(veri.onem) !== -1 ? " onem-" + veri.onem : "");
    k.hidden = false;
    gosterilen = { id: veri.id, onem: veri.onem };
    clearTimeout(k._zamanlayici);
    if (veri.onem !== "critical") k._zamanlayici = setTimeout(gizle, 8000);
  }

  return {
    sesAcikMi: function () { return ayarOku(SES_ANAHTARI); },
    konusmaAcikMi: function () { return ayarOku(KONUSMA_ANAHTARI); },
    sesAyarla: function (acik) { ayarYaz(SES_ANAHTARI, acik); if (acik) sesCal(); },
    konusmaAyarla: function (acik) { ayarYaz(KONUSMA_ANAHTARI, acik); },
    // Canlı akış bir olayın bittiğini bildirince (static/canli.js)
    bitti: function (id) {
      if (gosterilen && gosterilen.id === id) gizle();
    },
    // Yeni bir ihlal geldiğinde çağrılır (olay akışından)
    duyur: function (veri) {
      if (!veri || veri.tip !== "violation") return;
      // GÖLGE MOD: kural çalıştı, olay listeye düştü, ama uyarı bandı ve ses
      // ÇIKMAZ. Gölge mod "kuralı sessizce dene" demektir; bandı gösterirsek
      // deneme aşamasındaki bir kural ekran başındaki kişiyi boşuna uyarır.
      if (veri.golge) return;
      goster(veri);
      if (ayarOku(SES_ANAHTARI)) sesCal();
      if (ayarOku(KONUSMA_ANAHTARI)) {
        seslendir((veri.kural || "İhlal") + ". " + (veri.kamera || ""));
      }
    },
  };
})();
