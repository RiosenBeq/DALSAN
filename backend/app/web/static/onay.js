// Silme onayı — İKİ kabuğun da (temel.html ve komuta_temel.html) kullandığı
// TEK dosya. Onay metni data-onay özniteliğinden okunur, JS kaynağına
// gömülmez: adında kesme işareti olan bir kayıt ("Rampa 1'in önü") onay
// penceresini bozar ve kayıt SORULMADAN silinirdi.
//
// Ayrı dosya olmasının nedeni: aynı sekiz satır iki şablona kopyalansaydı,
// biri güncellenip diğeri unutulduğunda bir ekranda onay sorulur, öbüründe
// sorulmazdı — hangisi olduğunu da kimse fark etmezdi.
document.addEventListener("submit", function (olay) {
  var metin = olay.target.getAttribute && olay.target.getAttribute("data-onay");
  if (metin && !window.confirm(metin)) olay.preventDefault();
});
