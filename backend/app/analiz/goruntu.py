"""Görüntü kalitesi: iyileştirme ve teşhis.

Fabrika kameraları çoğu zaman idealin uzağındadır: yıllanmış lens, tozlu kapak,
karşıdan güneş, gece düşük ışık, düşük bit hızında ezilmiş H.264 görüntüsü.
Model bu karelerde daha az nesne bulur. Burada iki şey yapılır:

1. **İyileştirme** (isteğe bağlı, `.env` → GORUNTU_IYILESTIRME): kontrast
   yerel olarak dengelenir (CLAHE). Karanlık köşedeki insanı görünür kılar;
   zaten iyi olan görüntüyü belirgin biçimde bozmaz.
2. **Teşhis**: karenin ne kadar karanlık/bulanık olduğu ölçülür ve kamera
   sayfasında Türkçe yazılır. Kullanıcı "sistem neden göremiyor" sorusuna
   cevabı ekranda bulur; kamerayı temizlemek ya da ışık eklemek çoğu zaman
   eşik oynamaktan daha etkilidir.

Not: iyileştirme yapılırsa hem tespit hem önizleme AYNI kareyi kullanır —
kullanıcı ekranda modelin gördüğü görüntüyü görür (docs/09: dürüstlük).
"""

from __future__ import annotations

import cv2
import numpy as np

# CLAHE parametreleri: klip 2.0 tipik değerdir; 8x8 karo, hareketli sahnede
# blok sınırlarının göze batmadığı en küçük ayrıntı düzeyi.
_KLIP_SINIRI = 2.0
_KARO = (8, 8)

# Teşhis eşikleri (0-255 parlaklık ve Laplace varyansı). Fabrika kameralarında
# ölçülen tipik değerlere göre seçildi; amaç kesin karar değil, YÖNLENDİRME.
_KARANLIK_ESIGI = 55.0
_PARLAK_ESIGI = 205.0
_BULANIK_ESIGI = 40.0
_DUSUK_KONTRAST_ESIGI = 22.0


def iyilestir(kare: np.ndarray) -> np.ndarray:
    """Yerel kontrast dengeleme (CLAHE) — renk bozulmasın diye yalnız L kanalı.

    LAB uzayında yapılır: RGB kanallarını ayrı ayrı dengelemek renkleri kaydırır
    ve reflektörlü yeleğin sarısı bozulurdu.
    """
    lab = cv2.cvtColor(kare, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=_KLIP_SINIRI, tileGridSize=_KARO).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def kalite_olc(kare: np.ndarray) -> dict:
    """Karenin parlaklık/kontrast/netlik ölçüleri + Türkçe teşhis.

    Ölçüm küçültülmüş kopyada yapılır: 7x24 çalışan sistemde her karede tam
    çözünürlükte Laplace almak gereksiz işlemci yükü olurdu.
    """
    if kare is None or kare.size == 0:
        return {"sorun": "yok", "mesaj": "", "parlaklik": 0.0, "netlik": 0.0, "kontrast": 0.0}

    kucuk = cv2.resize(kare, (320, 180), interpolation=cv2.INTER_AREA)
    gri = cv2.cvtColor(kucuk, cv2.COLOR_BGR2GRAY)
    parlaklik = float(gri.mean())
    kontrast = float(gri.std())
    netlik = float(cv2.Laplacian(gri, cv2.CV_64F).var())

    sorun, mesaj = "yok", ""
    if parlaklik < _KARANLIK_ESIGI:
        sorun = "karanlik"
        mesaj = (
            "Görüntü çok karanlık. Tespit isabeti düşer: alana ışık ekleyin ya da "
            "kameranın gece modunu açın. Geçici çözüm olarak .env dosyasında "
            "GORUNTU_IYILESTIRME=otomatik yapabilirsiniz."
        )
    elif parlaklik > _PARLAK_ESIGI:
        sorun = "parlak"
        mesaj = (
            "Görüntü aşırı parlak (kameraya doğrudan güneş/ışık geliyor olabilir). "
            "Kamerayı yeniden konumlandırmak en kalıcı çözümdür."
        )
    elif netlik < _BULANIK_ESIGI:
        sorun = "bulanik"
        mesaj = (
            "Görüntü bulanık. Lens tozlu/buğulu olabilir ya da odak kaymıştır; "
            "kamera camını silmek çoğu zaman yeter. Düşük bit hızlı akış da "
            "bulanıklık yapar: NVR'da ana akışı (substream yerine) deneyin."
        )
    elif kontrast < _DUSUK_KONTRAST_ESIGI:
        sorun = "dusuk_kontrast"
        mesaj = (
            "Görüntünün kontrastı düşük (sisli/dumanlı görünüm). .env dosyasında "
            "GORUNTU_IYILESTIRME=otomatik belirgin fark yaratabilir."
        )
    return {
        "sorun": sorun,
        "mesaj": mesaj,
        "parlaklik": round(parlaklik, 1),
        "netlik": round(netlik, 1),
        "kontrast": round(kontrast, 1),
    }
