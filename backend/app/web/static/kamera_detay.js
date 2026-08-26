// Kamera detay sayfası: bölge çizimi ve kalibrasyon nokta seçimi.
// Koordinatlar NORMALİZE (0-1) kaydedilir — çözünürlük değişse de geçerli kalır.
(function () {
  var resim = document.getElementById("onizleme");
  var tuval = document.getElementById("cizim");
  if (!resim || !tuval) return;
  var baglam = tuval.getContext("2d");

  var mod = null; // null | "bolge" | "kalibrasyon"
  var bolgeNoktalari = [];
  var kalibrasyonNoktalari = [];

  function boyutla() {
    tuval.width = tuval.clientWidth;
    tuval.height = tuval.clientHeight;
    ciz();
  }
  window.addEventListener("resize", boyutla);

  function ciz() {
    baglam.clearRect(0, 0, tuval.width, tuval.height);

    // Kayıtlı bölgeler (turuncu)
    (window.MEVCUT_BOLGELER || []).forEach(function (bolge) {
      cizPoligon(bolge.poligon, "rgba(234,120,40,0.9)", "rgba(234,120,40,0.12)", bolge.ad);
    });
    // Çizilmekte olan bölge (mavi)
    if (bolgeNoktalari.length > 0) {
      cizPoligon(bolgeNoktalari, "rgba(29,78,216,1)", "rgba(29,78,216,0.15)", null, true);
    }
    // Kalibrasyon noktaları (yeşil, numaralı)
    kalibrasyonNoktalari.forEach(function (nokta, i) {
      var x = nokta[0] * tuval.width, y = nokta[1] * tuval.height;
      baglam.fillStyle = "#15803d";
      baglam.beginPath(); baglam.arc(x, y, 7, 0, 7); baglam.fill();
      baglam.fillStyle = "#fff";
      baglam.font = "bold 10px sans-serif";
      baglam.textAlign = "center"; baglam.textBaseline = "middle";
      baglam.fillText(String(i + 1), x, y);
    });
  }

  function cizPoligon(noktalar, cizgi, dolgu, etiket, noktalariGoster) {
    if (noktalar.length === 0) return;
    baglam.beginPath();
    noktalar.forEach(function (nokta, i) {
      var x = nokta[0] * tuval.width, y = nokta[1] * tuval.height;
      if (i === 0) baglam.moveTo(x, y); else baglam.lineTo(x, y);
    });
    if (noktalar.length > 2) baglam.closePath();
    baglam.strokeStyle = cizgi; baglam.lineWidth = 2; baglam.stroke();
    baglam.fillStyle = dolgu; baglam.fill();
    if (noktalariGoster) {
      noktalar.forEach(function (nokta) {
        baglam.fillStyle = cizgi;
        baglam.beginPath();
        baglam.arc(nokta[0] * tuval.width, nokta[1] * tuval.height, 4, 0, 7);
        baglam.fill();
      });
    }
    if (etiket && noktalar.length > 0) {
      baglam.fillStyle = cizgi;
      baglam.font = "12px sans-serif";
      baglam.textAlign = "left"; baglam.textBaseline = "top";
      baglam.fillText(etiket, noktalar[0][0] * tuval.width + 4, noktalar[0][1] * tuval.height + 4);
    }
  }

  tuval.addEventListener("click", function (olay) {
    if (!mod) return;
    var kutu = tuval.getBoundingClientRect();
    var x = (olay.clientX - kutu.left) / kutu.width;
    var y = (olay.clientY - kutu.top) / kutu.height;
    if (mod === "bolge") {
      bolgeNoktalari.push([x, y]);
      document.getElementById("polygon-alani").value = JSON.stringify(bolgeNoktalari);
      document.getElementById("bolge-kaydet").disabled = bolgeNoktalari.length < 3;
    } else if (mod === "kalibrasyon" && kalibrasyonNoktalari.length < 4) {
      kalibrasyonNoktalari.push([x, y]);
      kalibrasyonSatiriEkle(kalibrasyonNoktalari.length);
      if (kalibrasyonNoktalari.length === 4) {
        mod = null;
        tuval.classList.remove("aktif");
      }
    }
    ciz();
  });

  // --- bölge çizimi ---
  document.getElementById("cizim-baslat").addEventListener("click", function () {
    mod = "bolge";
    tuval.classList.add("aktif");
  });
  document.getElementById("cizim-temizle").addEventListener("click", function () {
    bolgeNoktalari = [];
    document.getElementById("polygon-alani").value = "";
    document.getElementById("bolge-kaydet").disabled = true;
    ciz();
  });

  // --- kalibrasyon ---
  var kalibrasyonBaslat = document.getElementById("kalibrasyon-baslat");
  if (kalibrasyonBaslat) {
    kalibrasyonBaslat.addEventListener("click", function () {
      kalibrasyonNoktalari = [];
      document.getElementById("kalibrasyon-noktalar").innerHTML = "";
      document.getElementById("kalibrasyon-kaydet").disabled = true;
      mod = "kalibrasyon";
      tuval.classList.add("aktif");
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

  setTimeout(boyutla, 150);  // resim yüklenince ölçüler otursun
  boyutla();
})();
