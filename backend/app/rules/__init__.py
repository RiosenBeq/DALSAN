"""SAF karar mantığı — bu klasör kutsaldır (CLAUDE.md §6).

Bu klasördeki dosyalar ŞUNLARI IMPORT EDEMEZ:
    cv2 (OpenCV), torch, ultralytics, sqlite3, fastapi
İzinli olanlar: Python standart kütüphanesi (sqlite3 hariç), numpy, pydantic.

Neden: tüm eşik, cooldown, zamansal oylama ve KKD karar mantığı kameraya
bağlanmadan, sahte veriyle, saniyeler içinde test edilebilsin diye. Yazılım
bilmeyen bir kullanıcı için doğruluğun kontrol edilebildiği tek yer burasıdır.

Girdi: list[Tespit] (sınıf, kutu, takip_id, hız, kkd_gozlemi) + bölgeler +
kalibrasyon + kural parametreleri. Çıktı: list[Ihlal].

Bu klasör 5. adımda (kural motoru) dolacak. Saflık kuralı şimdiden
tests/rules/test_saflik.py ile korunuyor: yasaklı bir import buraya girerse
test kırmızıya döner.
"""
