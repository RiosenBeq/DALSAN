"""Çalışma ortamı denetimi: kurulu OpenCV sürümü beklenen sürüm mü?

NEDEN VAR — bu GERÇEKTEN yaşandı ve bulunması saatler aldı. Bir makinede
`opencv-python 5.0.0`, `backend/requirements.txt`'in sabitlediği 4.10'u
gölgeledi. Sonuç şuydu:

  * Sistem AÇILDI, kameralar bağlandı, tespit çalıştı, hiçbir hata satırı yok.
  * Ama nesne kütüphanesi (ORB desen eşleştirme) 36 sorgunun HİÇBİRİNİ
    bulamadı — yani "tanıttığım nesne neden bulunmuyor" diye bir soru, hiçbir
    yerde cevabı yazmadan ortaya çıktı.

Sessiz bozulma, gürültülü bozulmadan çok daha pahalıdır. Bu modül o sessizliği
bozar: sürüm beklenenden farklıysa açılışta günlüğe ve Ana Sayfa'daki sistem
bilgisi tablosuna tek satır düşer.

SİSTEM YİNE DE AÇILIR. Sürüm farkı bir UYARIDIR, ön koşul değil: yanlış
sürümle bile bölge ihlali, güvenli mesafe ve KKD kuralları çalışmaya devam
eder. Açılışı durdurmak, çalışan bir güvenlik sistemini nesne kütüphanesi
uğruna kapatmak olurdu.
"""

from __future__ import annotations

# backend/requirements.txt'te SABİTLENEN ana sürüm. İkisi birlikte
# değişmelidir; tests/test_ortam.py bunu zorunlu tutar.
#
# Neden 4'e sabit: OpenCV 5, ORB ve renk histogramı davranışını değiştiriyor.
# Nesne kütüphanesinin eşleşme çıtası (NESNE_ESLESME_ESIGI=0,24) 4.x üzerinde
# ÖLÇÜLEREK seçildi; 5.x'te aynı çıta hiçbir şey bulmuyor.
BEKLENEN_ANA_SURUM = 4


def opencv_surumu() -> str:
    """Kurulu OpenCV sürümü; okunamazsa boş metin."""
    try:
        import cv2
    except ImportError:
        return ""
    return str(getattr(cv2, "__version__", ""))


def opencv_uyarisi(surum: str | None = None) -> str:
    """Sürüm beklenenden farklıysa Türkçe uyarı; sorun yoksa BOŞ metin.

    `surum` yalnızca testler için; olağan kullanımda kurulu sürüm okunur.
    """
    ham = opencv_surumu() if surum is None else surum
    if not ham:
        return ""
    try:
        ana = int(ham.split(".", 1)[0])
    except ValueError:
        # Beklenmeyen bir sürüm biçimi. Uyarı ÜRETİLMEZ: "sürümünüz yanlış"
        # demek, yalnızca sürüm metnini okuyamadığımız için kullanıcıyı
        # olmayan bir arızanın peşine düşürürdü.
        return ""
    if ana == BEKLENEN_ANA_SURUM:
        return ""
    return (
        f"Görüntü kütüphanesinin sürümü beklenenden farklı (kurulu {ham}, "
        f"beklenen {BEKLENEN_ANA_SURUM}.x). Kameralar ve kurallar çalışır, ama "
        "Nesneler sayfasındaki tanıma HATALI SONUÇ VEREBİLİR. Düzeltmek için "
        "Kontrol Paneli'nde Durdur → İlk Kurulumu Yap → Sistemi Başlat."
    )
