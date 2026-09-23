"""Tespit motorunun HIZ ölçüm düzeneği (kıyas takımı).

Bu paket motoru DEĞİŞTİRMEZ; bugünkü halinin bir kareyi kaç milisaniyede
işlediğini ve dört kameralık bütçeyi (docs/05 §3: 4 × 6 fps) karşılayıp
karşılamadığını sayılarla ortaya koyar.

Neden burada duruyor: `tests/` altındadır çünkü ürünün çalışması için gerekli
değildir; fabrikadaki sunucuya kurulan programın parçası değildir. Aynı
gerekçeyle `tests/nesne_kiyas/` de buradadır.

Neden gerekli: "CPU yetersiz, GPU şart" cümlesi bir donanım satın alma
kararıdır; ölçülmeden tekrar edilmemelidir. Ölçüm sonuçları
`docs/AUDIT-OLCUM.md` dosyasındadır.

Kullanım (depo kökünden):

    .venv/bin/python -m tests.hiz_kiyas            # iki ölçüm de
    .venv/bin/python -m tests.hiz_kiyas --tek      # yalnız tek akış
    .venv/bin/python -m tests.hiz_kiyas --dort     # yalnız dört kamera

Model dosyaları gerekir: `bash models/indir.sh`.
"""
