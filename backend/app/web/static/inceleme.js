/* Olay inceleme ekranı — klavyeyle önceki/sonraki olaya geçiş.
 *
 * Kısayol GİZLİ BİR ÖZELLİK DEĞİLDİR: ekranın altında "← önceki olay ·
 * → sonraki olay" ipucu her zaman yazılıdır. Aynı geçişi düğmelere basarak
 * da yapabilirsiniz; bu dosya yüklenmese bile ekran eksiksiz çalışır.
 *
 * İŞARETLEME kısayolu bilerek yoktur: tek tuşa basınca veritabanına yazan bir
 * kısayol, kısayolu bilmeyen kullanıcı için sessiz bir hata kaynağıdır.
 * İşaretleme yalnızca düğmeyle (ya da not kutusunda Enter ile) yapılır.
 */
(function () {
  "use strict";

  var kutu = document.getElementById("inceleme");
  if (!kutu) {
    return; // kuyruk boşken bu ekranda gezinecek olay yok
  }

  document.addEventListener("keydown", function (olay) {
    if (olay.ctrlKey || olay.altKey || olay.metaKey || olay.shiftKey) {
      return; // tarayıcının kendi kısayollarına dokunma
    }
    var hedef = olay.target;
    if (
      hedef &&
      (hedef.tagName === "INPUT" ||
        hedef.tagName === "TEXTAREA" ||
        hedef.tagName === "SELECT" ||
        hedef.isContentEditable)
    ) {
      return; // not yazarken ok tuşları imleci hareket ettirmeli
    }

    var id = null;
    if (olay.key === "ArrowRight") {
      id = kutu.getAttribute("data-sonraki");
    } else if (olay.key === "ArrowLeft") {
      id = kutu.getAttribute("data-onceki");
    }
    if (!id) {
      return; // listenin başında/sonundayız
    }
    olay.preventDefault();
    window.location.href = "/komuta/inceleme?olay=" + encodeURIComponent(id);
  });
})();
