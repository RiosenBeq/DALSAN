# DALSAN İSG Görüntü Analiz Sistemi

Fabrikadaki mevcut kameralardan (3-4 adet, RTSP) görüntü alıp **insan, forklift ve
tır** tespit eden; **bölge ihlali**, **güvenli mesafe** ve **KKD (baret/yelek)**
kurallarını değerlendiren; ihlalde ekrana ve (altyapı uygunsa) anonsa uyarı düşüren;
her olayı kanıt fotoğrafıyla kaydeden, **tek sunucuda çalışan** erken uyarı sistemi.

> Sistem, İSG prosedürlerinin yerine geçmez; onları destekleyen bir erken uyarı
> katmanıdır. Kaçırılan ihlal bilinen sınırdır, yanlış alarm ise ciddi kusurdur —
> tüm eşikler bu ilkeyle seçilmiştir (bkz. `docs/00-PROJE-BAGLAMI.md`).

## Hızlı başlangıç (geliştirme — Mac/Windows)

1. [Python 3.12](https://www.python.org/downloads/) kurun
   (Windows'ta **"Add Python to PATH"** işaretli olmalı).
2. Proje klasöründe **Baslat-Mac.command** / **Baslat-Windows.bat** dosyasına çift tıklayın.
3. Kontrol Paneli'nde **İlk Kurulumu Yap** → **Sistemi Başlat**.
4. Tarayıcı `http://127.0.0.1:8080` adresinde açılır. Giriş ekranı/şifre yoktur:
   sistem yalnızca bu bilgisayardan açılır (fabrika sunucusuna çıkmadan önce
   şifre geri eklenecek — `docs/07-YOL-HARITASI.md` #0).

Tespit modeli repoda değildir; sistem ilk açılışta **kendisi indirir** (internet
gerekir, ~20 MB). Ana sayfada "Tespit modeli: Hazır" görünene kadar bekleyin.
Elle indirmek isterseniz: `bash models/indir.sh`.

Gerçek kamera olmadan denemek için: Kameralar → Yeni Kamera → kaynak tipi
**Video dosyası** seçip bilgisayardaki bir .mp4 dosyasının tam yolunu verin — sistem
onu kamera gibi izler. Kamera sayfasındaki durum satırı bağlanamama sebebini
(dosya bulunamadı, kameraya ulaşılamıyor, şifre yanlış olabilir…) açıkça yazar.

## Ne yapar

| Yetenek | Durum |
|---|---|
| Kamera yönetimi (RTSP/video), otomatik yeniden bağlanma, canlı önizleme, bağlantı teşhisi | ✅ |
| Canlı sayım (insan/araç), ekranda renk anahtarı, görüntü kalitesi teşhisi | ✅ |
| Yaya yolu kuralı (tek tıkla) — insanların yürüyüş yolunu kullanması | ✅ |
| İhlalde ekran bandı + sesli uyarı + Türkçe seslendirme, anons deneme düğmesi | ✅ |
| İnsan / araç tespiti (**NextGen AI** tespit motoru) + ByteTrack takip | ✅ |
| Bölge çizimi (tarayıcıda poligon) ve bölge ihlali kuralı | ✅ |
| Güvenli mesafe kuralı (4 nokta zemin kalibrasyonu, metre cinsinden) | ✅ |
| Olay kaydı + kanıt fotoğrafı + canlı uyarı ekranı (SSE) + CSV | ✅ |
| Anons altyapısı (ses kartı / HTTP IP hoparlör / kapalı) | ✅ arayüz hazır, saha entegrasyonu bekliyor |
| Giriş şifresi | ⏳ bilerek kapalı; fabrika kurulumundan önce (docs/07 #0) |
| KKD (baret/yelek) veri toplama + uygulama içi etiketleme | ✅ |
| KKD modeli eğitimi ve gölge mod | ⏳ saha verisi toplandıktan sonra |
| Forklift'e özel sınıf | ⏳ saha görüntüsüyle ince ayar gerekiyor (şimdilik araç olarak görünür) |

## Mimari (kısaca)

**Tek program:** FastAPI web arayüzü + arka planda analiz iş parçacığı.
**Tek veritabanı dosyası:** `veri/dalsan.db` (SQLite). Yedek almak = `veri/`
klasörünü kopyalamak. Gerekçeler: `docs/09-BASITLESTIRME-KARARLARI.md`.

```
Kamera (RTSP) → son-kare deseni → NextGen AI tespit → ByteTrack takip
   → KURAL MOTORU (saf, kamerasız test edilir: backend/app/rules/)
   → olay + kanıt fotoğrafı → SQLite → canlı ekran (SSE) + anons
```

`backend/app/rules/` klasörü **saftır**: OpenCV, torch, sqlite3, FastAPI import
edemez. Tüm eşik/cooldown/zamansal oylama mantığı sahte veriyle milisaniyeler
içinde test edilir; bu kural `tests/rules/test_saflik.py` ile korunur.

## Test ve kalite

```bash
.venv/bin/python -m pytest        # tüm testler
.venv/bin/python -m pytest tests/rules -q   # kural motoru (hızlı, kamerasız)
.venv/bin/ruff check .
```

## Tespit motoru ve lisanslar

Arayüzde tespit motoru **NextGen AI** adıyla görünür (Hızlı / İsabetli). Bu ad
kurulumun ürün adıdır; ekrandaki adı üreten tek yer
`backend/app/analiz/model_adi.py`'dir. Dosya adları, indirme adresleri ve
`.env` içindeki `MODEL_DOSYASI` anahtarı özgün hâliyle kalır — sistem modeli
onlarla bulur.

Altta çalışan açık kaynak bileşenlerin telif ve lisans atfı depo kökündeki
`LICENSE-THIRD-PARTY` dosyasındadır.

## Doküman haritası

Kamera yerleşimi, görüntü kalitesi ve hassasiyet ayarı için:
`docs/12-KAMERA-VE-GORUNTU-KALITESI.md`.

Tüm tasarım kararları `docs/` altındadır; çelişki durumunda
`docs/09-BASITLESTIRME-KARARLARI.md` geçerlidir. Çalışma yöntemi için
`docs/10-YAPAY-ZEKA-ILE-CALISMA.md`, ilerleme kaydı için `docs/ILERLEME.md`.
