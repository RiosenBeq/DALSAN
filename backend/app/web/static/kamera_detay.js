// Kamera detay sayfası: bölge çizimi ve kalibrasyon nokta seçimi.
// Koordinatlar NORMALİZE (0-1) kaydedilir — çözünürlük değişse de geçerli kalır.
//
// Bu sayfada bölgeleri YALNIZCA bu tuval çizer: görüntü sunucudan bölgesiz
// istenir (onizleme.js → ?bolgesiz=1). Tek çizen olduğu için renk, izleme
// ekranlarındaki sunucu çiziminin ve renk anahtarının rengiyle AYNI olmalıdır.
//
// Çizimi kolaylaştıran davranışlar (hepsi tarayıcıda, kütüphanesiz):
//   · fare gezerken son köşeden imlece KESİKLİ kenar önizlemesi,
//   · en az 3 köşe varken ilk nokta büyür; ona tıklamak alanı KAPATIR,
//   · "Son köşeyi geri al" ve Esc ile iptal,
//   · köşe sayacı + duruma göre değişen Türkçe kılavuz balonu,
//   · çizilen bölge, seçilen tipin rengiyle çizilir (renkler stil.css'te),
//   · DİKDÖRTGEN KİPİ: bir köşeden karşı köşeye sürükleyip bırakmak yeter
//     (yükleme alanı, tır parkı ve KKD alanlarının çoğu dikdörtgendir),
//   · KÖŞE SÜRÜKLEME: konmuş bir köşe fareyle tutulup taşınabilir — eskiden
//     tek yanlış köşe için tüm çizimi baştan yapmak gerekiyordu,
//   · ALANI OTOMATİK BUL: zemindeki boyalı alan sunucuda bulunur ve öneri
//     kartına tıklanınca hazır çizim tuvale yüklenir (app/web/alan_rotalari.py),
//   · TARALI DOLGU: çizilen ve seçilen alanlar çapraz taramayla dolar. Yalnız
//     çerçeve çizmek yetmiyordu — "alanın içi neresi" sorusu görüntüye
//     bakılarak cevaplanamıyor, yan yana iki bölgede hangi çizginin hangisine
//     ait olduğu anlaşılmıyordu. Sunucu da videoyu aynı biçimde tarar
//     (analiz/boru_hatti.py), böylece ekranla video aynı şeyi söyler,
//   · BÖLGEYE TIKLAYIP SEÇME: kayıtlı bir bölgenin içine tıklamak onu seçer;
//     seçili bölge taralı görünür ve Düzenle / Kapat / Sil düğmeleri çıkar.
//
// DÜZENLEME KİPİ: sayfa ?duzenle=<bölge id> ile açıldığında sunucu
// window.DUZENLENEN_BOLGE'yi doldurur. O bölgenin kayıtlı köşeleri tuvale
// yüklenir ve üzerinde değişiklik yapılabilir; hiç dokunulmazsa kayıtlı çizim
// olduğu gibi korunur (form boş poligon gönderir, sunucu eskisini saklar).
(function () {
  // Bölge rengi — boru_hatti.py _BOLGE_RENGI (mor) ve renk_anahtari.html ile aynı
  var BOLGE_RENGI = "#A03CC8";
  var BOLGE_DOLGU = saydam(BOLGE_RENGI, 0.12); // aynı morun saydam dolgusu
  var KAPATMA_YARICAPI = 14; // ilk noktaya bu kadar yakın tıklama alanı kapatır
  var TUTMA_YARICAPI = 12;   // köşeyi sürüklemek için bu kadar yakın tutmak yeter
  var SURUKLEME_ESIGI = 3;   // bu kadar pikselden az hareket "tıklama" sayılır
  var ILK_NOKTA_R = 8;       // kapatılabilir ilk köşe — büyük hedef
  var NOKTA_R = 5;           // diğer köşeler
  var KESIK = [7, 6];        // canlı kenar önizlemesinin kesik deseni
  var TARAMA_ARALIGI = 9;    // çapraz tarama çizgileri arası (px)
  var TARAMA_KALINLIGI = 2;

  // Bölge tipi → stil.css'teki renk değişkeni. Renkler tek yerde (stil.css
  // :root) tanımlıdır; burada sabit renk YAZILMAZ.
  var TIP_DEGISKENI = {
    pedestrian_path: "--bolge-yaya-yolu",
    loading_area: "--bolge-yukleme",
    truck_parking: "--bolge-tir-park",
    vehicle_area: "--bolge-arac",
    ppe_required: "--bolge-kkd",
    restricted: "--bolge-yasak"
  };

  var resim = document.getElementById("onizleme");
  var tuval = document.getElementById("cizim");
  if (!resim || !tuval) return;
  var baglam = tuval.getContext("2d");
  var kokStil = getComputedStyle(document.documentElement);

  var balon = document.getElementById("cizim-balonu");
  var balonNoktasi = document.getElementById("balon-noktasi");
  var balonTipAdi = document.getElementById("balon-tip-adi");
  var balonAdim = document.getElementById("balon-adim");
  var balonSayac = document.getElementById("balon-sayac");
  var tipSecimi = document.getElementById("bolge-tipi");
  var tipRengiKutusu = document.getElementById("tip-rengi");
  var kaydetDugmesi = document.getElementById("bolge-kaydet");
  var geriDugmesi = document.getElementById("cizim-geri");
  var temizleDugmesi = document.getElementById("cizim-temizle");
  var koseSayaci = document.getElementById("kose-sayaci");
  var poligonAlani = document.getElementById("polygon-alani");

  var mod = null; // null | "bolge" | "kalibrasyon"
  // Düzenlenen bölge (yoksa null). Kayıtlı köşeleri, Esc ile geri dönebilmek
  // için ayrıca saklanır.
  var duzenlenen = window.DUZENLENEN_BOLGE || null;
  var kayitliNoktalar = (duzenlenen && duzenlenen.poligon) ? duzenlenen.poligon : [];
  var bolgeNoktalari = [];
  var kalibrasyonNoktalari = [];
  var kapandi = false;  // ilk noktaya tıklanarak alan kapatıldı mı
  var imlec = null;     // farenin son konumu (0-1) — canlı kenar için
  var suruklenen = null;    // taşınmakta olan köşenin sırası (yoksa null)
  var tiklamaYut = false;   // sürükleme bitti → ardından gelen click yutulur
  var dikdortgenBasi = null; // dikdörtgen kipinde basılan ilk köşe (0-1)
  var seciliBolgeId = null;  // görüntüde tıklanarak seçilen kayıtlı bölge

  // --- renk yardımcıları ---

  // stil.css :root'taki bir renk değişkeni. Renkler tek yerde durur; bu
  // dosyaya sabit renk yazılmaz (tek istisna: kayıtlı bölgenin moru, çünkü o
  // sunucunun çizdiği renkle birebir aynı olmak zorunda).
  function degiskenRengi(ad) {
    return kokStil.getPropertyValue(ad).trim();
  }

  function seciliTipRengi() {
    var tip = tipSecimi ? tipSecimi.value : "";
    var degisken = TIP_DEGISKENI[tip];
    var renk = degisken ? degiskenRengi(degisken) : "";
    return renk || BOLGE_RENGI; // değişken bulunamazsa kayıtlı bölge rengi
  }

  function seciliTipAdi() {
    if (!tipSecimi || tipSecimi.selectedIndex < 0) return "Bölge";
    return tipSecimi.options[tipSecimi.selectedIndex].text;
  }

  // Altılık renk kodunu saydam dolguya çevirir (kod + alfa → rgba metni).
  // Renk beklenen biçimde değilse dolgu yapılmaz: yanlış bir renk basmaktansa
  // dolgusuz çizmek yeğdir.
  function saydam(renk, alfa) {
    var kod = String(renk).trim().replace("#", "");
    if (kod.length === 3) kod = kod[0] + kod[0] + kod[1] + kod[1] + kod[2] + kod[2];
    if (!/^[0-9a-f]{6}$/i.test(kod)) return null;
    var sayi = parseInt(kod, 16);
    return "rgba(" + ((sayi >> 16) & 255) + ", " + ((sayi >> 8) & 255) + ", " +
      (sayi & 255) + ", " + alfa + ")";
  }

  // Çapraz tarama deseni. Küçük bir çevrimdışı tuval bir kez çizilir ve
  // desen olarak tekrarlanır; her karede çizgi çizmekten çok daha ucuzdur.
  // Desenler renk başına önbelleklenir (bölge tipleri altı renk kullanır).
  var desenOnbellegi = {};
  function taramaDeseni(renk) {
    if (desenOnbellegi[renk]) return desenOnbellegi[renk];
    var kare = document.createElement("canvas");
    kare.width = TARAMA_ARALIGI;
    kare.height = TARAMA_ARALIGI;
    var kb = kare.getContext("2d");
    kb.strokeStyle = renk;
    kb.lineWidth = TARAMA_KALINLIGI;
    // Üç çizgi: desen kutusu tekrarlandığında çapraz çizgiler kesintisiz aksın.
    [-TARAMA_ARALIGI, 0, TARAMA_ARALIGI].forEach(function (kayma) {
      kb.beginPath();
      kb.moveTo(kayma, TARAMA_ARALIGI);
      kb.lineTo(kayma + TARAMA_ARALIGI, 0);
      kb.stroke();
    });
    var desen = baglam.createPattern(kare, "repeat");
    desenOnbellegi[renk] = desen;
    return desen;
  }

  // Nokta poligonun içinde mi (ışın yöntemi) — rules/geometri.py ile aynı
  // mantık. Bölgeye tıklayarak seçme buna dayanır.
  function noktaPoligonda(nokta, poligon) {
    var icinde = false;
    for (var i = 0, j = poligon.length - 1; i < poligon.length; j = i++) {
      var xi = poligon[i][0], yi = poligon[i][1];
      var xj = poligon[j][0], yj = poligon[j][1];
      if ((yi > nokta[1]) !== (yj > nokta[1])) {
        var kesisim = (xj - xi) * (nokta[1] - yi) / (yj - yi) + xi;
        if (nokta[0] < kesisim) icinde = !icinde;
      }
    }
    return icinde;
  }

  // --- tuval ölçüsü ---
  // Tuvalin çizim tamponu, ekrandaki kutusuyla BİREBİR aynı ölçüde olmalı.
  // Olmazsa tıkladığınız yer ile çizilen nokta birbirinden kayar.
  function boyutuEsitle() {
    var genislik = Math.round(tuval.clientWidth);
    var yukseklik = Math.round(tuval.clientHeight);
    if (genislik < 1 || yukseklik < 1) return;
    if (tuval.width === genislik && tuval.height === yukseklik) return;
    tuval.width = genislik;   // tampon boyutu değişince içerik silinir
    tuval.height = yukseklik; // (ciz() hemen ardından yeniden çizer)
  }

  function boyutla() {
    boyutuEsitle();
    ciz();
  }

  // --- çizim ---

  function ciz() {
    baglam.clearRect(0, 0, tuval.width, tuval.height);

    // Kayıtlı bölgeler (mor — renk anahtarındaki "Çizdiğiniz bölge" rengi).
    // Pasif bölge çizilmez: sistem onu değerlendirmiyor, ekranda da durmamalı.
    (window.MEVCUT_BOLGELER || []).forEach(function (bolge) {
      if (bolge.aktif === false) return;
      // Seçili bölge TARALI, diğerleri sade dolgulu: hangisini seçtiğiniz
      // görüntüye bakar bakmaz anlaşılsın.
      var secili = bolge.id === seciliBolgeId;
      cizPoligon(
        bolge.poligon,
        BOLGE_RENGI,
        secili ? taramaDeseni(BOLGE_RENGI) : BOLGE_DOLGU,
        bolge.ad,
        secili ? 3 : 2
      );
    });

    cizilmekteOlaniCiz();

    // Kalibrasyon noktaları (yeşil, numaralı)
    kalibrasyonNoktalari.forEach(function (nokta, i) {
      var x = nokta[0] * tuval.width, y = nokta[1] * tuval.height;
      baglam.fillStyle = degiskenRengi("--basari") || BOLGE_RENGI;
      baglam.beginPath(); baglam.arc(x, y, 7, 0, Math.PI * 2); baglam.fill();
      baglam.fillStyle = degiskenRengi("--dolu-metin");
      baglam.font = "bold 10px sans-serif";
      baglam.textAlign = "center"; baglam.textBaseline = "middle";
      baglam.fillText(String(i + 1), x, y);
    });
  }

  function cizPoligon(noktalar, cizgi, dolgu, etiket, kalinlik) {
    if (noktalar.length === 0) return;
    baglam.beginPath();
    noktalar.forEach(function (nokta, i) {
      var x = nokta[0] * tuval.width, y = nokta[1] * tuval.height;
      if (i === 0) baglam.moveTo(x, y); else baglam.lineTo(x, y);
    });
    if (noktalar.length > 2) baglam.closePath();
    // Dolgu ÖNCE, çizgi SONRA: taralı dolgu kenar çizgisinin üstüne taşmasın.
    if (dolgu) { baglam.fillStyle = dolgu; baglam.fill(); }
    baglam.strokeStyle = cizgi; baglam.lineWidth = kalinlik || 2; baglam.stroke();
    if (etiket) {
      baglam.fillStyle = cizgi;
      baglam.font = "12px sans-serif";
      baglam.textAlign = "left"; baglam.textBaseline = "top";
      baglam.fillText(etiket, noktalar[0][0] * tuval.width + 4, noktalar[0][1] * tuval.height + 4);
    }
  }

  // Çizilmekte olan bölge: seçilen tipin rengiyle, canlı kenar önizlemesiyle.
  function cizilmekteOlaniCiz() {
    // Dikdörtgen sürüklenirken: basılan köşeden imlece kadar canlı önizleme.
    // Kullanıcı bırakmadan önce alanın nereye oturacağını görür.
    if (dikdortgenBasi && imlec) {
      var dRenk = seciliTipRengi();
      cizPoligon(dikdortgenKoseleri(dikdortgenBasi, imlec), dRenk, taramaDeseni(dRenk), null);
    }
    if (bolgeNoktalari.length === 0) return;
    var renk = seciliTipRengi();
    var kapatilabilir = bolgeNoktalari.length >= 3 && !kapandi;

    // konmuş kenarlar (+ kapandıysa dolgu)
    baglam.beginPath();
    bolgeNoktalari.forEach(function (nokta, i) {
      var x = nokta[0] * tuval.width, y = nokta[1] * tuval.height;
      if (i === 0) baglam.moveTo(x, y); else baglam.lineTo(x, y);
    });
    if (kapandi) {
      // Alan kapanınca TARALI dolar: "bu alan artık seçili" demenin en açık yolu.
      baglam.closePath();
      baglam.fillStyle = taramaDeseni(renk);
      baglam.fill();
    }
    baglam.strokeStyle = renk; baglam.lineWidth = kapandi ? 3 : 2; baglam.stroke();

    // canlı kenar önizlemesi: son köşeden imlece kesikli çizgi. Kapatılabilir
    // durumdaysa ilk köşeye kadar da uzatılır — alanın nasıl kapanacağı görünür.
    if (!kapandi && imlec) {
      var son = bolgeNoktalari[bolgeNoktalari.length - 1];
      baglam.save();
      baglam.setLineDash(KESIK);
      baglam.strokeStyle = renk; baglam.lineWidth = 2;
      baglam.beginPath();
      baglam.moveTo(son[0] * tuval.width, son[1] * tuval.height);
      baglam.lineTo(imlec[0] * tuval.width, imlec[1] * tuval.height);
      if (kapatilabilir) {
        baglam.lineTo(bolgeNoktalari[0][0] * tuval.width, bolgeNoktalari[0][1] * tuval.height);
      }
      baglam.stroke();
      baglam.restore();
    }

    // köşeler: ilk köşe kapatılabilirken BÜYÜK çizilir (tıklama hedefi)
    bolgeNoktalari.forEach(function (nokta, i) {
      var buyuk = i === 0 && kapatilabilir;
      var x = nokta[0] * tuval.width, y = nokta[1] * tuval.height;
      baglam.beginPath();
      baglam.arc(x, y, buyuk ? ILK_NOKTA_R : NOKTA_R, 0, Math.PI * 2);
      baglam.fillStyle = renk; baglam.fill();
      baglam.strokeStyle = degiskenRengi("--dolu-metin");
      baglam.lineWidth = 2; baglam.stroke();
      // imleç kapatma mesafesindeyse ilk köşenin çevresine halka
      if (buyuk && imlec && pikselUzakligi(nokta, imlec) <= KAPATMA_YARICAPI) {
        baglam.beginPath();
        baglam.arc(x, y, ILK_NOKTA_R + 5, 0, Math.PI * 2);
        baglam.strokeStyle = renk; baglam.lineWidth = 2; baglam.stroke();
      }
    });
  }

  // --- konum yardımcıları ---

  function oranHesapla(olay) {
    var kutu = tuval.getBoundingClientRect();
    return [(olay.clientX - kutu.left) / kutu.width, (olay.clientY - kutu.top) / kutu.height];
  }

  function pikselUzakligi(a, b) {
    return Math.hypot((a[0] - b[0]) * tuval.width, (a[1] - b[1]) * tuval.height);
  }

  // --- kılavuz balonu, sayaç ve düğmeler ---

  function kilavuzuGuncelle() {
    if (!balon) return;
    if (!mod) { balon.hidden = true; return; }
    balon.hidden = false;

    if (mod === "kalibrasyon") {
      if (balonNoktasi) balonNoktasi.style.background = degiskenRengi("--basari");
      if (balonTipAdi) balonTipAdi.textContent = "Mesafe kalibrasyonu";
      if (balonAdim) {
        balonAdim.textContent = "Zeminde gerçek ölçüsünü bildiğiniz " +
          (kalibrasyonNoktalari.length + 1) + ". noktaya tıklayın. Vazgeçmek için Esc.";
      }
      if (balonSayac) balonSayac.textContent = kalibrasyonNoktalari.length + " / 4 nokta";
      return;
    }

    var renk = seciliTipRengi();
    var sayi = bolgeNoktalari.length;
    if (balonNoktasi) balonNoktasi.style.background = renk;

    if (mod === "dikdortgen") {
      if (balonTipAdi) balonTipAdi.textContent = seciliTipAdi() + " — dikdörtgen";
      if (balonAdim) {
        balonAdim.textContent = "Alanın bir köşesine basılı tutun, karşı köşesine " +
          "sürükleyip bırakın. Vazgeçmek için Esc.";
      }
      if (balonSayac) balonSayac.textContent = "sürükleyerek çizin";
      return;
    }
    if (balonTipAdi) {
      balonTipAdi.textContent = duzenlenen
        ? "\"" + duzenlenen.ad + "\" düzenleniyor — " + seciliTipAdi()
        : seciliTipAdi() + " çiziyorsunuz";
    }

    var adim;
    if (kapandi) {
      adim = duzenlenen
        ? "Köşeleri sürükleyerek düzeltebilirsiniz. Kaydetmek için \"Değişikliği " +
          "Kaydet\"e basın; baştan çizmek için \"Yeniden çiz\". Esc kayıtlı çizime döndürür."
        : "Alan kapandı. Köşeleri sürükleyerek düzeltebilir, sonra \"Bölgeyi " +
          "Kaydet\"e basabilirsiniz. Vazgeçmek için Esc.";
    } else if (sayi === 0) {
      adim = duzenlenen
        ? "Çizim temizlendi — kaydederseniz kayıtlı çizim olduğu gibi kalır. Yeni alan " +
          "çizmek için köşelere tıklayın; Esc kayıtlı çizime döndürür."
        : "Bölgenin köşelerine sırayla tıklayın (en az 3). Vazgeçmek için Esc.";
    } else if (sayi < 3) {
      adim = "Köşe eklemeye devam edin — en az " + (3 - sayi) + " köşe daha gerek.";
    } else {
      adim = "Bitirmek için İLK (büyük) noktaya tıklayın; ya da köşe eklemeye devam edin.";
    }
    if (balonAdim) balonAdim.textContent = adim;
    if (balonSayac) balonSayac.textContent = sayi + (kapandi ? " köşe · kapandı" : " köşe");
  }

  function durumuGuncelle() {
    var sayi = bolgeNoktalari.length;
    if (poligonAlani) poligonAlani.value = sayi > 0 ? JSON.stringify(bolgeNoktalari) : "";
    // Düzenlemede boş çizim "dokunmadım" demektir: sunucu kayıtlı çizimi korur.
    // 1-2 köşe ise alan değildir, kaydettirilmez.
    if (kaydetDugmesi) kaydetDugmesi.disabled = !(sayi >= 3 || (duzenlenen && sayi === 0));
    if (geriDugmesi) geriDugmesi.disabled = sayi === 0;
    if (temizleDugmesi) temizleDugmesi.disabled = sayi === 0;
    if (koseSayaci) {
      koseSayaci.textContent = sayi + " köşe" + (sayi >= 3 ? " ✓" : "") +
        (kapandi ? " · alan kapandı" : "");
      koseSayaci.className = sayi >= 3 ? "kose-sayaci tamam" : "kose-sayaci";
    }
    if (tipRengiKutusu) tipRengiKutusu.style.background = seciliTipRengi();
    kilavuzuGuncelle();
  }

  // Çizimi tümüyle bırakır: mod kapanır, kılavuz gizlenir, konan köşeler silinir.
  // Yarıda kalan kalibrasyon seçimi de temizlenir — yoksa ekranda karşılığı
  // olmayan "Nokta 1/2..." satırları kalır.
  function cizimiIptalEt() {
    var kalibrasyonSurerken = mod === "kalibrasyon";
    mod = null;
    bolgeNoktalari = [];
    kalibrasyonNoktalari = [];
    kapandi = false;
    imlec = null;
    suruklenen = null;
    dikdortgenBasi = null;
    tuval.classList.remove("aktif");
    if (kalibrasyonSurerken) {
      var kutu = document.getElementById("kalibrasyon-noktalar");
      var kaydet = document.getElementById("kalibrasyon-kaydet");
      if (kutu) kutu.innerHTML = "";
      if (kaydet) kaydet.disabled = true;
    }
    durumuGuncelle();
    ciz();
  }

  // --- fare ---

  tuval.addEventListener("click", function (olay) {
    // Köşe sürüklendikten sonra tarayıcı ayrıca bir "click" üretir; yutulmazsa
    // taşıdığınız köşenin yanına istemediğiniz yeni bir köşe konurdu.
    if (tiklamaYut) { tiklamaYut = false; return; }
    boyutuEsitle();  // tıklama ile çizim aynı ölçüde olsun
    if (!mod) {
      // Çizim kipi kapalıyken tıklama, KAYITLI bir bölgeyi seçer.
      bolgeSec(oranHesapla(olay));
      return;
    }
    var konum = oranHesapla(olay);
    if (mod === "dikdortgen") {
      return;  // dikdörtgen sürüklemeyle çizilir; tıklama köşe eklemez
    }
    if (mod === "bolge") {
      bolgeTiklamasi(konum);
    } else if (mod === "kalibrasyon" && kalibrasyonNoktalari.length < 4) {
      kalibrasyonNoktalari.push(konum);
      kalibrasyonSatiriEkle(kalibrasyonNoktalari.length);
      if (kalibrasyonNoktalari.length === 4) {
        mod = null;
        tuval.classList.remove("aktif");
      }
      kilavuzuGuncelle();
    }
    ciz();
  });

  // --- görüntüde bölge seçme ---
  //
  // Kullanıcı "hangi bölge nerede" sorusunu listeye bakarak değil, görüntüye
  // tıklayarak cevaplasın. Seçilen bölge taralı görünür ve yapılabilecekler
  // (Düzenle / Kapat / Sil) aynı yerde çıkar.

  var seciliKutu = document.getElementById("secili-bolge");

  function bolgeSec(konum) {
    var bolgeler = (window.MEVCUT_BOLGELER || []).filter(function (b) {
      return b.aktif !== false && noktaPoligonda(konum, b.poligon);
    });
    // Üst üste binen bölgelerde en KÜÇÜK olan seçilir: büyük bir bölgenin
    // içindeki küçük bölgeye başka türlü tıklanamazdı.
    bolgeler.sort(function (a, b) { return poligonAlani(a.poligon) - poligonAlani(b.poligon); });
    seciliBolgeId = bolgeler.length ? bolgeler[0].id : null;
    seciliBolgeyiYaz(bolgeler.length ? bolgeler[0] : null);
    ciz();
  }

  function poligonAlani(poligon) {
    var toplam = 0;
    for (var i = 0; i < poligon.length; i++) {
      var a = poligon[i], b = poligon[(i + 1) % poligon.length];
      toplam += a[0] * b[1] - b[0] * a[1];
    }
    return Math.abs(toplam) / 2;
  }

  function seciliBolgeyiYaz(bolge) {
    if (!seciliKutu) return;
    seciliKutu.textContent = "";
    if (!bolge) {
      seciliKutu.hidden = true;
      return;
    }
    seciliKutu.hidden = false;

    var baslik = document.createElement("span");
    baslik.className = "secili-adi";
    baslik.appendChild(Object.assign(document.createElement("b"), { textContent: bolge.ad }));
    if (bolge.tip_adi) {
      baslik.appendChild(Object.assign(document.createElement("span"), {
        className: "not", textContent: " · " + bolge.tip_adi }));
    }
    seciliKutu.appendChild(baslik);

    var duzenle = document.createElement("a");
    duzenle.className = "dugme ikincil kucuk";
    duzenle.href = "/kameralar/" + (window.KAMERA_ID || "") + "?duzenle=" + bolge.id;
    duzenle.textContent = "Düzenle";
    seciliKutu.appendChild(duzenle);

    seciliKutu.appendChild(gonderFormu(
      "/bolgeler/" + bolge.id + "/durum",
      bolge.aktif === false ? "Aç" : "Kapat",
      { enabled: bolge.aktif === false ? "1" : "0" },
      null
    ));
    seciliKutu.appendChild(gonderFormu(
      "/bolgeler/" + bolge.id + "/sil",
      "Sil",
      {},
      bolge.ad + " bölgesi silinsin mi? Bu bölgeye bağlı kurallar da silinir. " +
        "Adını veya çizimini değiştirmek için Sil değil, Düzenle'yi kullanın."
    ));

    var birak = document.createElement("button");
    birak.type = "button";
    birak.className = "metin-dugme";
    birak.textContent = "seçimi bırak";
    birak.addEventListener("click", function () {
      seciliBolgeId = null;
      seciliBolgeyiYaz(null);
      ciz();
    });
    seciliKutu.appendChild(birak);
  }

  // Sayfadaki diğer bölge işlemleriyle AYNI uç noktalara POST eden küçük form.
  // Ayrı bir JS yolu açılsaydı iki davranış zamanla ayrışırdı (onay metni,
  // yönlendirme, hata sayfası).
  function gonderFormu(adres, yazi, alanlar, onayMetni) {
    var form = document.createElement("form");
    form.method = "post";
    form.action = adres;
    form.className = "satir-form";
    if (onayMetni) form.dataset.onay = onayMetni;
    Object.keys(alanlar).forEach(function (ad) {
      var alan = document.createElement("input");
      alan.type = "hidden";
      alan.name = ad;
      alan.value = alanlar[ad];
      form.appendChild(alan);
    });
    form.appendChild(Object.assign(document.createElement("button"), {
      className: "dugme ikincil kucuk", textContent: yazi }));
    return form;
  }

  function bolgeTiklamasi(konum) {
    if (kapandi) return; // alan kapandı; yeni köşe eklenmez
    // İlk noktaya yakın tıklama alanı KAPATIR (en az 3 köşe varken).
    if (bolgeNoktalari.length >= 3 &&
        pikselUzakligi(bolgeNoktalari[0], konum) <= KAPATMA_YARICAPI) {
      kapandi = true;
      imlec = null;
    } else {
      bolgeNoktalari.push(konum);
    }
    durumuGuncelle();
  }

  // --- köşe sürükleme ve dikdörtgen çizimi ---
  //
  // Üçü de aynı üç olayı paylaşır (mousedown/mousemove/mouseup), bu yüzden
  // hangi işin sürdüğü tek yerde ayrılır: `suruklenen` bir köşe taşınıyor,
  // `dikdortgenBasi` bir dikdörtgen çiziliyor demektir.

  tuval.addEventListener("mousedown", function (olay) {
    if (!mod || mod === "kalibrasyon") return;
    boyutuEsitle();
    var konum = oranHesapla(olay);
    if (mod === "dikdortgen") {
      dikdortgenBasi = konum;
      imlec = konum;
      olay.preventDefault();  // sürüklerken görüntü "resim taşıma" başlatmasın
      return;
    }
    var sira = tutulanKose(konum);
    if (sira !== null) {
      suruklenen = sira;
      olay.preventDefault();
    }
  });

  tuval.addEventListener("mousemove", function (olay) {
    if (suruklenen !== null) {
      bolgeNoktalari[suruklenen] = sinirla(oranHesapla(olay));
      tiklamaYut = true;  // bu bir sürükleme; ardından gelen click köşe eklemesin
      durumuGuncelle();
      ciz();
      return;
    }
    if (dikdortgenBasi) {
      imlec = oranHesapla(olay);
      ciz();
      return;
    }
    if (mod !== "bolge" || kapandi || bolgeNoktalari.length === 0) return;
    imlec = oranHesapla(olay);
    ciz();
  });

  tuval.addEventListener("mouseup", function (olay) {
    if (suruklenen !== null) {
      suruklenen = null;
      durumuGuncelle();
      ciz();
      return;
    }
    if (!dikdortgenBasi) return;
    var bitis = oranHesapla(olay);
    // Yanlışlıkla tek tıklama: sürükleme sayılmayacak kadar küçükse alan
    // kurulmaz. Aksi halde görünmeyen, sıfır alanlı bir bölge oluşurdu.
    if (pikselUzakligi(dikdortgenBasi, bitis) < TUTMA_YARICAPI) {
      dikdortgenBasi = null;
      imlec = null;
      ciz();
      return;
    }
    bolgeNoktalari = dikdortgenKoseleri(dikdortgenBasi, bitis);
    kapandi = true;
    dikdortgenBasi = null;
    imlec = null;
    // Dikdörtgen bittiğinde normal çizim kipine dönülür: kullanıcı köşeleri
    // sürükleyip düzeltebilsin (dikdörtgen kipinde tuval sürüklemeyi
    // yeni bir dikdörtgenin başlangıcı sayardı).
    mod = "bolge";
    durumuGuncelle();
    ciz();
  });

  tuval.addEventListener("mouseleave", function () {
    // Fare tuvalin dışına çıkarken sürükleme bırakılmış sayılır; aksi halde
    // dışarıda bırakılan düğme yüzünden köşe imlece yapışık kalırdı.
    if (suruklenen !== null) {
      suruklenen = null;
      durumuGuncelle();
    }
    dikdortgenBasi = null;
    if (!imlec) { ciz(); return; }
    imlec = null;
    ciz();
  });

  // Çizilmiş köşelerden imlecin tutma mesafesindeki İLKİ (yoksa null).
  function tutulanKose(konum) {
    for (var i = 0; i < bolgeNoktalari.length; i++) {
      if (pikselUzakligi(bolgeNoktalari[i], konum) <= TUTMA_YARICAPI) return i;
    }
    return null;
  }

  function sinirla(konum) {
    return [Math.min(Math.max(konum[0], 0), 1), Math.min(Math.max(konum[1], 0), 1)];
  }

  // İki karşıt köşeden saat yönünde dört köşe üretir.
  function dikdortgenKoseleri(a, b) {
    var x1 = Math.min(a[0], b[0]), x2 = Math.max(a[0], b[0]);
    var y1 = Math.min(a[1], b[1]), y2 = Math.max(a[1], b[1]);
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]].map(sinirla);
  }

  // Düzenlemede Esc: yarım kalan yeni çizimi atıp KAYITLI çizime döner.
  function kayitliCizimeDon() {
    bolgeNoktalari = kayitliNoktalar.slice();
    kapandi = bolgeNoktalari.length >= 3;
    imlec = null;
    durumuGuncelle();
    ciz();
  }

  // Esc: çizimden vazgeçilir. Bölge düzenlerken bu, kayıtlı çizime dönmektir —
  // düzenlemeyi tümüyle bırakmak için sayfadaki "Vazgeç" bağlantısı var.
  document.addEventListener("keydown", function (olay) {
    if (olay.key !== "Escape" || !mod) return;
    if (duzenlenen && mod === "bolge") {
      kayitliCizimeDon();
      return;
    }
    cizimiIptalEt();
  });

  // --- bölge çizimi düğmeleri ---
  document.getElementById("cizim-baslat").addEventListener("click", function () {
    mod = "bolge";
    kapandi = false;
    seciliBolgeId = null;
    seciliBolgeyiYaz(null);
    // Düzenlerken bu düğme "Yeniden çiz"dir: yüklü köşeler silinir, kullanıcı
    // alanı baştan çizer. Kaydetmezse veritabanındaki çizim değişmez.
    if (duzenlenen) bolgeNoktalari = [];
    tuval.classList.add("aktif");
    durumuGuncelle();
    ciz();
  });

  var dikdortgenDugmesi = document.getElementById("cizim-dikdortgen");
  if (dikdortgenDugmesi) {
    dikdortgenDugmesi.addEventListener("click", function () {
      mod = "dikdortgen";
      kapandi = false;
      // Çizmeye geçiliyor: kayıtlı bölge seçimi bırakılır. "Çizime başla" ile
      // aynı davranış — iki düğmeden biri seçimi bırakıp öbürü bırakmasaydı
      // ekranda hem seçili hem çizilen alan taralı görünür, karışırdı.
      seciliBolgeId = null;
      seciliBolgeyiYaz(null);
      bolgeNoktalari = [];
      imlec = null;
      dikdortgenBasi = null;
      tuval.classList.add("aktif");
      durumuGuncelle();
      ciz();
    });
  }

  if (geriDugmesi) {
    geriDugmesi.addEventListener("click", function () {
      if (bolgeNoktalari.length === 0) return;
      bolgeNoktalari.pop();
      kapandi = false;  // kapalı alandan köşe silinince alan yeniden açılır
      durumuGuncelle();
      ciz();
    });
  }

  document.getElementById("cizim-temizle").addEventListener("click", function () {
    bolgeNoktalari = [];
    kapandi = false;
    imlec = null;
    durumuGuncelle();
    ciz();
  });

  if (tipSecimi) {
    // Tip değişince hem renk kutusu hem çizilmekte olan bölge yeni renge döner.
    tipSecimi.addEventListener("change", function () {
      durumuGuncelle();
      ciz();
    });
  }

  // --- kalibrasyon ---
  var kalibrasyonBaslat = document.getElementById("kalibrasyon-baslat");
  if (kalibrasyonBaslat) {
    kalibrasyonBaslat.addEventListener("click", function () {
      kalibrasyonNoktalari = [];
      document.getElementById("kalibrasyon-noktalar").innerHTML = "";
      document.getElementById("kalibrasyon-kaydet").disabled = true;
      mod = "kalibrasyon";
      tuval.classList.add("aktif");
      kilavuzuGuncelle();
      ciz();
    });

    document.getElementById("kalibrasyon-formu").addEventListener("submit", function () {
      var dunya = [];
      for (var i = 1; i <= 4; i++) {
        dunya.push([
          parseFloat(document.getElementById("dunya-x-" + i).value.replace(",", ".")),
          parseFloat(document.getElementById("dunya-y-" + i).value.replace(",", ".")),
        ]);
      }
      document.getElementById("image-points").value = JSON.stringify(kalibrasyonNoktalari);
      document.getElementById("world-points").value = JSON.stringify(dunya);
    });
  }

  function kalibrasyonSatiriEkle(no) {
    var satir = document.createElement("div");
    satir.className = "nokta-satiri";
    satir.innerHTML = "<b>Nokta " + no + ":</b> gerçek konumu (metre) " +
      'X <input id="dunya-x-' + no + '" required placeholder="örn. 0"> ' +
      'Y <input id="dunya-y-' + no + '" required placeholder="örn. 5">';
    document.getElementById("kalibrasyon-noktalar").appendChild(satir);
    if (no === 4) {
      document.getElementById("kalibrasyon-kaydet").disabled = false;
      var ipucu = document.createElement("p");
      ipucu.className = "not";
      ipucu.textContent = "İpucu: 1. noktayı (0,0) kabul edip diğerlerini ona göre metre " +
        "cinsinden yazın. Örn. 5 m sağdaki nokta: X=5, Y=0.";
      document.getElementById("kalibrasyon-noktalar").appendChild(ipucu);
    }
  }

  // --- ALANI OTOMATİK BUL ---
  //
  // Sunucu, zemindeki boyalı alanları bulup öneri listesi döner
  // (app/web/alan_rotalari.py). Burada yapılan üç şey var: isteği atmak,
  // önerileri kart olarak listelemek ve tıklanan kartın çizimini tuvale
  // yüklemek. Yüklenen ekran görüntüsü tuvalin arka planı olur — kamera
  // bağlı olmasa da bölge çizilebilsin diye.

  // --- ÇİZİM ARKA PLANI: dondur / yükle / canlıya dön ---
  //
  // Canlı akış saniyede bir yenilenirken köşe tıklamak zordur: tıkladığınız an
  // görüntü değişir ve nereye tıkladığınızı şaşırırsınız. "Kareyi dondur" o
  // anki kareyi sabitler. "Ekran görüntüsü yükle" ise kamera hiç bağlı
  // değilken bile (NVR'dan alınmış bir kare ile) çizim yapılmasını sağlar.
  //
  // Dondurma, onizleme.js'in okuduğu data-donmus ile yapılır: tazeleme durur,
  // görüntünün o anki karesi ekranda kalır.

  var kareDondur = document.getElementById("kare-dondur");
  var arkaplanDosya = document.getElementById("arkaplan-dosya");
  var canliyaDon = document.getElementById("canliya-don");
  var arkaplanRozeti = document.getElementById("arkaplan-rozeti");
  var arkaplanDurumu = document.getElementById("arkaplan-durumu");

  function arkaplanDurumunuYaz(metin, hataMi) {
    if (!arkaplanDurumu) return;
    arkaplanDurumu.textContent = metin || "";
    arkaplanDurumu.className = hataMi ? "hata-mesaji" : "not";
  }

  function donmusaGec(rozetYazisi) {
    resim.dataset.donmus = "1";
    if (arkaplanRozeti) {
      arkaplanRozeti.textContent = rozetYazisi;
      arkaplanRozeti.hidden = false;
    }
    if (canliyaDon) canliyaDon.hidden = false;
  }

  if (kareDondur) {
    kareDondur.addEventListener("click", function () {
      if (!resim.classList.contains("dolu")) {
        arkaplanDurumunuYaz(
          "Henüz görüntü gelmedi; dondurulacak kare yok. Kamera bağlanana kadar " +
          "beklemek yerine bir ekran görüntüsü yükleyebilirsiniz.",
          true
        );
        return;
      }
      donmusaGec("donduruldu");
      arkaplanDurumunuYaz(
        "Görüntü donduruldu. Artık bu karenin üstüne rahatça çizebilirsiniz.",
        false
      );
    });
  }

  if (canliyaDon) {
    canliyaDon.addEventListener("click", function () {
      delete resim.dataset.donmus;
      if (arkaplanRozeti) arkaplanRozeti.hidden = true;
      canliyaDon.hidden = true;
      arkaplanDurumunuYaz("Canlı görüntüye dönüldü.", false);
    });
  }

  if (arkaplanDosya) {
    arkaplanDosya.addEventListener("change", function () {
      if (arkaplanDosya.files && arkaplanDosya.files[0]) {
        // Aynı uç nokta kullanılır (app/web/alan_rotalari.py): görüntü hem
        // arka plan olur hem — varsa — alan önerisi döner. İki ayrı yol
        // açmak, aynı görüntünün iki kez yüklenmesi demekti.
        alanBul(arkaplanDosya.files[0], "ciz");
      }
    });
  }

  var alanBulCanli = document.getElementById("alan-bul-canli");
  var alanBulDurum = document.getElementById("alan-bul-durum");
  var alanOnerileri = document.getElementById("alan-onerileri");

  function alanDurumu(metin, hataMi) {
    if (!alanBulDurum) return;
    alanBulDurum.textContent = metin;
    alanBulDurum.className = hataMi ? "hata-mesaji" : "not";
  }

  // amac: "bul" → kullanıcı alan arıyor · "ciz" → yalnız arka plan istiyor,
  // öneri çıkarsa ikramdır. İkisi aynı uç noktayı kullanır; fark, bulunamadığında
  // kullanıcıya söylenen cümlededir — çizmek için yüklenen bir görüntüde
  // "bulunamadı" kırmızısı yersiz bir başarısızlık hissi verirdi.
  function alanBul(dosya, amac) {
    if (!alanOnerileri) return;
    var cizmekIcin = amac === "ciz";
    var veri = new FormData();
    if (dosya) veri.append("gorsel", dosya);
    alanOnerileri.textContent = "";
    var bekleme = cizmekIcin
      ? "Görüntü yükleniyor…"
      : (dosya ? "Yüklenen görüntü inceleniyor…" : "Canlı görüntü inceleniyor…");
    if (cizmekIcin) arkaplanDurumunuYaz(bekleme, false); else alanDurumu(bekleme, false);
    if (alanBulCanli) alanBulCanli.disabled = true;

    fetch("/kameralar/" + (alanBulCanli ? alanBulCanli.dataset.kamera : "") + "/alan-bul", {
      method: "POST",
      body: veri
    })
      .then(function (yanit) { return yanit.json(); })
      .then(function (sonuc) {
        // Yüklenen görüntü, öneri çıkmasa bile arka plan yapılır: kullanıcı
        // yine de o görüntünün üstüne elle çizebilmeli.
        if (sonuc.gorsel) arkaPlanaKoy(sonuc.gorsel);
        if (cizmekIcin) {
          arkaplanDurumunuYaz(
            sonuc.gorsel
              ? "Ekran görüntüsü yüklendi; üstüne çizebilirsiniz." +
                (sonuc.oneriler && sonuc.oneriler.length
                  ? " Sistem ayrıca " + sonuc.oneriler.length +
                    " hazır alan önerdi — aşağıdaki kartlara bakın."
                  : "")
              : (sonuc.mesaj || "Görüntü yüklenemedi."),
            !sonuc.gorsel
          );
        } else {
          alanDurumu(sonuc.mesaj || "", !sonuc.tamam);
        }
        onerileriListele(sonuc.oneriler || []);
        teshisiGoster(cizmekIcin ? null : sonuc.teshis);
      })
      .catch(function () {
        var hata = "Görüntü gönderilirken bağlantı hatası oldu. Sayfayı yenileyip " +
          "yeniden deneyin.";
        if (cizmekIcin) arkaplanDurumunuYaz(hata, true); else alanDurumu(hata, true);
      })
      .then(function () {
        if (alanBulCanli) alanBulCanli.disabled = false;
      });
  }

  // Yüklenen ekran görüntüsünü canlı önizlemenin YERİNE koyar ve tazelemeyi
  // durdurur (onizleme.js data-donmus'u okur). Aksi halde bir sonraki saniyede
  // canlı kare gelir ve kullanıcı başka bir görüntünün üstüne çizmiş olurdu.
  function arkaPlanaKoy(veriAdresi) {
    donmusaGec("yüklenen görüntü");
    resim.src = veriAdresi;
    resim.classList.add("dolu");
    var kutu = resim.closest(".onizleme-kutu");
    if (kutu) kutu.classList.add("dolu");
  }

  // Alan bulunamadığında sistemin "boya" saydığı pikselleri gösterir.
  // Boş bir teşhis görüntüsü, "eşiği kurcalayın" demekten daha açık bir
  // cevaptır: zemindeki boya tanınmıyor demektir.
  function teshisiGoster(veriAdresi) {
    var eskisi = document.getElementById("alan-teshisi");
    if (eskisi) eskisi.remove();
    if (!veriAdresi || !alanOnerileri) return;
    var kutu = document.createElement("figure");
    kutu.id = "alan-teshisi";
    kutu.className = "alan-teshisi";
    var resim = document.createElement("img");
    resim.src = veriAdresi;
    resim.alt = "Sistemin boya saydığı yerler işaretli teşhis görüntüsü";
    kutu.appendChild(resim);
    kutu.appendChild(Object.assign(document.createElement("figcaption"), {
      className: "not",
      textContent: "Teşhis: turuncu = sarı boya sayılan yerler, mavi = beyaz boya " +
        "sayılan yerler. Hiçbir yer işaretli değilse zemindeki boya soluk ya da " +
        "görüntü fazla karanlık demektir."
    }));
    alanOnerileri.parentNode.appendChild(kutu);
  }

  function onerileriListele(oneriler) {
    if (!alanOnerileri) return;
    alanOnerileri.textContent = "";
    oneriler.forEach(function (oneri) {
      var kart = document.createElement("button");
      kart.type = "button";
      kart.className = "alan-oneri";
      kart.appendChild(Object.assign(document.createElement("b"), {
        textContent: oneri.tip_adi
      }));
      kart.appendChild(Object.assign(document.createElement("span"), {
        className: "not",
        textContent: "görüntünün %" + oneri.alan_yuzdesi + "'i · " +
          oneri.poligon.length + " köşe · belirginlik %" + oneri.guven_yuzde
      }));
      kart.addEventListener("click", function () { oneriyiYukle(oneri); });
      alanOnerileri.appendChild(kart);
    });
  }

  // Öneriyi tuvale yükler ve bölge tipini de seçer. Kaydetme yapılmaz:
  // karar kullanıcınındır, köşeleri düzeltip kendisi kaydeder.
  function oneriyiYukle(oneri) {
    mod = "bolge";
    bolgeNoktalari = oneri.poligon.map(sinirla);
    kapandi = bolgeNoktalari.length >= 3;
    imlec = null;
    dikdortgenBasi = null;
    if (tipSecimi && oneri.tip) tipSecimi.value = oneri.tip;
    tuval.classList.add("aktif");
    durumuGuncelle();
    ciz();
    alanDurumu(
      "Çizim tuvale yüklendi. Köşeleri sürükleyerek düzeltin, ad verip \"Bölgeyi " +
      "Kaydet\"e basın.",
      false
    );
    var adAlani = document.querySelector("#bolge-formu input[name=name]");
    if (adAlani && !adAlani.value) adAlani.focus();
  }

  if (alanBulCanli) {
    alanBulCanli.addEventListener("click", function () { alanBul(null, "bul"); });
  }
  // Ölçü GÖRÜNTÜYE bağlanır, sabit bir bekleme süresine değil: görüntü gelene
  // kadar kutunun yüksekliği yanlıştır ve önizleme her saniye yeni bir kare
  // yükler. "load" her yeni karede, ResizeObserver ise kutu ölçüsü her
  // değiştiğinde (pencere, yazı tipi, yeni çözünürlük) ölçüyü tazeler.
  resim.addEventListener("load", boyutla);
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(boyutla).observe(tuval.parentNode || tuval);
  } else {
    window.addEventListener("resize", boyutla);  // ResizeObserver yoksa yedek
  }
  // Düzenleme kipi: kayıtlı köşeler tuvale yüklenir ve çizim kipi hemen açılır,
  // kullanıcı "hangi bölgeyi düzenliyorum" sorusunu görüntüde yanıtlar.
  if (duzenlenen) {
    mod = "bolge";
    bolgeNoktalari = kayitliNoktalar.slice();
    kapandi = bolgeNoktalari.length >= 3;
    tuval.classList.add("aktif");
  }
  durumuGuncelle();
  boyutla();
})();
