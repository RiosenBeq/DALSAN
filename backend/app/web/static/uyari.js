// Ekran uyarısı: ihlalde görünen bir bant + (isteğe bağlı) sesli uyarı ve
// Türkçe seslendirme. Anons sistemi sahaya bağlanana kadar (docs/08 R3) ihlali
// duyuran tek yol budur; bağlandıktan sonra da ekran başındaki kişi için kalır.
//
// Ses neden bu kadar dikkatli kuruluyor: tarayıcılar, kullanıcı sayfaya bir kez
// tıklamadan ses çalmayı engeller. Her uyarıda yeni bir AudioContext açan kod
// sessizce çalışmaz ve kimse fark etmez. Bu yüzden TEK bağlam kurulur, ilk
// kullanıcı hareketinde uyandırılır ve durumu ekranda yazılır.
//
// Sesin çalışmadığı hiçbir durum sessiz kalmaz (docs/17 R41): canlı akışlı
// sayfalarda köşede bir ses çipi durur - ses kapalıysa "açmak için tıklayın",
// tarayıcı sesi bekletiyorsa "etkinleştirmek için tıklayın", çalınamadıysa
// "sesli uyarı çalışmıyor". Her şey yolundayken çip görünmez.
window.Uyari = (function () {
  var SES_ANAHTARI = "dalsan-uyari-sesi";
  var KONUSMA_ANAHTARI = "dalsan-uyari-konusma";
  var baglam = null;
  var kutu = null;
  var sistemKutusu = null;
  var cip = null;
  var cipEtkin = false; // yalnız canlı akışlı sayfalarda (static/canli.js açar)
  var sesHatasi = ""; // son bip denemesinin hatası; başarılı çalma temizler
  var okumaHatasi = ""; // son Türkçe okuma denemesinin hatası
  // localStorage kapalıysa (gizli sekme) ayar bu oturum boyunca burada durur;
  // yoksa sesi açmak hiç mümkün olmazdı.
  var bellek = {};

  function ayarOku(anahtar) {
    try {
      var deger = window.localStorage.getItem(anahtar);
      if (deger !== null) return deger === "1";
    } catch (e) {
      // localStorage kapalı: bellekteki değer geçerli
    }
    return bellek[anahtar] === true;
  }

  function ayarYaz(anahtar, acik) {
    bellek[anahtar] = acik;
    try {
      window.localStorage.setItem(anahtar, acik ? "1" : "0");
    } catch (e) {
      // kaydedilemiyor: ayar yalnızca bu oturum için geçerli (bellekte)
    }
  }

  function sesDestekleniyor() {
    return !!(window.AudioContext || window.webkitAudioContext);
  }

  function baglamAl() {
    if (baglam) return baglam;
    var Yapici = window.AudioContext || window.webkitAudioContext;
    if (!Yapici) return null;
    try {
      baglam = new Yapici();
      baglam.onstatechange = cipiGuncelle;
    } catch (e) {
      sesHatasi = "tarayıcı ses çalamıyor";
      cipiGuncelle();
      return null;
    }
    return baglam;
  }

  // Tarayıcı kuralı: ses ancak gerçek bir kullanıcı hareketinden sonra çalar.
  // İlk tıklama/tuşta bağlamı uyandır; sonrası sessizce çalışır. Bağlam burada,
  // hareketin İÇİNDE kurulur: önceden kurulan bağlam "askıda" doğar.
  function uyandir() {
    var b = baglamAl();
    if (b && b.state === "suspended") {
      var soz = b.resume();
      if (soz && soz.then) soz.then(cipiGuncelle, cipiGuncelle);
    }
    cipiGuncelle();
  }
  document.addEventListener("click", uyandir, { once: false });
  document.addEventListener("keydown", uyandir, { once: false });

  function sesCal() {
    var b = baglamAl();
    if (!b) {
      sesHatasi = "tarayıcı ses çalamıyor";
      cipiGuncelle();
      return;
    }
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
      sesHatasi = "";
    } catch (e) {
      // Uyarı bandı yine görünür; ama sesin çalmadığı çiple söylenir (R41)
      sesHatasi = "ses çalınamadı";
    }
    cipiGuncelle();
  }

  function seslendir(metin) {
    if (!window.speechSynthesis) {
      okumaHatasi = "bu tarayıcı Türkçe okuyamıyor";
      cipiGuncelle();
      return;
    }
    try {
      var soz = new window.SpeechSynthesisUtterance(metin);
      soz.lang = "tr-TR";
      soz.rate = 1.0;
      soz.onerror = function () {
        okumaHatasi = "Türkçe okunamadı";
        cipiGuncelle();
      };
      soz.onend = function () {
        okumaHatasi = "";
        cipiGuncelle();
      };
      window.speechSynthesis.speak(soz);
    } catch (e) {
      okumaHatasi = "Türkçe okunamadı";
      cipiGuncelle();
    }
  }

  // ---- ses çipi (R41) ----

  function cipAl() {
    if (cip) return cip;
    cip = document.createElement("button");
    cip.type = "button";
    cip.className = "ses-cipi";
    cip.hidden = true;
    cip.addEventListener("click", function () {
      if (!ayarOku(SES_ANAHTARI)) ayarYaz(SES_ANAHTARI, true);
      // Tıklamanın kendisi kullanıcı hareketidir: bağlam burada uyanır ve
      // deneme bipi çalar; olmuyorsa çip sebebini yazar.
      uyandir();
      sesCal();
    });
    document.body.appendChild(cip);
    return cip;
  }

  function cipiGuncelle() {
    if (!cipEtkin) return;
    var c = cipAl();
    var metin = "";
    var sinif = "";
    if (!ayarOku(SES_ANAHTARI)) {
      metin = "Bu ekranda sesli uyarı KAPALI - açmak için tıklayın";
      sinif = "kapali";
    } else if (!sesDestekleniyor() || sesHatasi) {
      metin =
        "⚠ Sesli uyarı çalışmıyor - " +
        (sesHatasi || "tarayıcı ses çalamıyor") +
        ". Denemek için tıklayın";
      sinif = "hata";
    } else if (!baglam || baglam.state === "suspended") {
      metin = "Sesli uyarı beklemede - etkinleştirmek için tıklayın";
      sinif = "bekliyor";
    } else if (ayarOku(KONUSMA_ANAHTARI) && okumaHatasi) {
      metin = "⚠ Sesli okuma çalışmıyor - " + okumaHatasi;
      sinif = "hata";
    }
    c.textContent = metin;
    c.className = "ses-cipi" + (sinif ? " " + sinif : "");
    c.hidden = !metin;
    document.body.classList.toggle("ses-cipi-var", !!metin);
  }

  // ---- ihlal bandı ----

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
    k.textContent = "⚠ " + (veri.kamera || "Kamera") + " - " + (veri.ozet || "İhlal");
    k.className = "uyari-bandi" + (ONEMLER.indexOf(veri.onem) !== -1 ? " onem-" + veri.onem : "");
    k.hidden = false;
    gosterilen = { id: veri.id, onem: veri.onem };
    clearTimeout(k._zamanlayici);
    if (veri.onem !== "critical") k._zamanlayici = setTimeout(gizle, 8000);
  }

  // ---- sistem bandı ----
  // Kamera koptu, analiz takıldı gibi sistem olayları ihlal bandını ezmez;
  // ayrı, sessiz bir bantta 8 sn görünür (docs/17 §11). Süren durum sistem
  // şeridinde kalır (static/sistem_seridi.js).

  function sistemKutusuAl() {
    if (sistemKutusu) return sistemKutusu;
    sistemKutusu = document.createElement("div");
    sistemKutusu.className = "sistem-bandi";
    sistemKutusu.hidden = true;
    sistemKutusu.title = "Kapatmak için tıklayın";
    sistemKutusu.addEventListener("click", function () {
      sistemKutusu.hidden = true;
    });
    document.body.appendChild(sistemKutusu);
    return sistemKutusu;
  }

  function sistemGoster(veri) {
    var k = sistemKutusuAl();
    var kamera = veri.kamera && veri.kamera !== "-" ? veri.kamera + " - " : "";
    k.textContent = "Sistem: " + kamera + (veri.ozet || "sistem olayı");
    k.hidden = false;
    clearTimeout(k._zamanlayici);
    k._zamanlayici = setTimeout(function () {
      k.hidden = true;
    }, 8000);
  }

  return {
    sesAcikMi: function () { return ayarOku(SES_ANAHTARI); },
    konusmaAcikMi: function () { return ayarOku(KONUSMA_ANAHTARI); },
    sesAyarla: function (acik) {
      ayarYaz(SES_ANAHTARI, acik);
      if (acik) sesCal();
      cipiGuncelle();
    },
    konusmaAyarla: function (acik) {
      ayarYaz(KONUSMA_ANAHTARI, acik);
      cipiGuncelle();
    },
    // Canlı akışlı sayfa açılınca (static/canli.js): ses çipi görünür olur
    cipiEtkinlestir: function () {
      cipEtkin = true;
      cipiGuncelle();
    },
    // Canlı akış bir olayın bittiğini bildirince (static/canli.js)
    bitti: function (id) {
      if (gosterilen && gosterilen.id === id) gizle();
    },
    // Yeni bir olay geldiğinde çağrılır (olay akışından)
    duyur: function (veri) {
      if (!veri) return;
      if (veri.tip === "system") {
        sistemGoster(veri);
        return;
      }
      if (veri.tip !== "violation") return;
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
