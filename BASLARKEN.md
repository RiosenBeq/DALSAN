# Başlarken - 10 Dakikalık Rehber

## 0. Klasörü nereye koymalı

Proje klasörünü **OneDrive, iCloud Drive veya Google Drive içine KOYMAYIN.**
Bu klasörler dosyaları arka planda eşitler; veritabanı dosyası (`veri/dalsan.db`)
eşitleme sırasında kilitlenir ve sistem "veritabanı kilitli" hatası verir.

Güvenli yerler: `C:\DALSAN` (Windows) veya `~/DALSAN` (Mac).
Yolun kısa olması Windows'ta ayrıca uzun-yol sorununu da önler.

## 1. Python'u kur (bir kez)

https://www.python.org/downloads/ → **Python 3.12** (yalnız 3.12 desteklenir;
daha yeni bir sürüm kuruluysa 3.12 onunla yan yana kurulabilir)

> **Windows'ta:** Kurulum ekranındaki **"Add Python to PATH"** kutusunu işaretle.
> (İşaretlemeyi unutursan da başlatıcı `py` komutuyla çalışmayı dener.)

> **Mac'te:** Kurulumdan sonra **Uygulamalar → Python 3.12** klasöründeki
> **"Install Certificates.command"** dosyasına bir kez çift tıkla. Bunu
> atlarsan tespit modeli indirilemez ("sertifika doğrulanamadı" hatası).

## 2. Kontrol Paneli'ni aç

| Mac | Windows |
|---|---|
| `Baslat-Mac.command` → çift tık | `Baslat-Windows.bat` → çift tık |
| Uyarı çıkarsa: sağ tık → Aç → Aç | Uyarı çıkarsa: Daha fazla bilgi → Yine de çalıştır |

## 3. "İlk Kurulumu Yap"a bas

Birkaç dakika sürer. Pencereyi kapatma. Bitince "KURULUM TAMAMLANDI" yazar.

## 4. "Sistem kodu: Hazır" yazmalı

"Sistem kodu: Hazır" yazısını göreceksin: sistemin kodu bu klasörde hazırdır.
"Henüz yazılmadı" yazıyorsa klasör eksik kopyalanmıştır (`backend/app/main.py`
yok); klasörü eksiksiz yeniden kopyala.

## 5. Claude Code'a ilk mesajın

> CLAUDE.md ve docs/ klasöründeki tüm dokümanları oku.
>
> `docs/10-YAPAY-ZEKA-ILE-CALISMA.md` §4'teki sıralamada, `docs/ILERLEME.md`'ye
> göre **henüz bitmemiş ilk adımı** yap.
>
> Sadece bu adımı yap, sonrakine geçme. Bitince Kontrol Paneli'nde ne göreceğimi yaz.

## 6. Denemeyi unutma

Claude Code "tamam" dediğinde:
Kontrol Paneli → **Sistemi Başlat** → izleme ekranı (adres çubuğu olmayan bir
pencere) açılmalı.

**Açılmadıysa** günlük penceresindeki `[HATA]` (ve `[!]`) ile başlayan satırları
kopyala, Claude Code'a yapıştır:

> Şunu yapmaya çalıştım: sistemi başlattım.
> Bekliyordum: izleme ekranı açılacaktı.
> Onun yerine bu oldu: [hata metnini yapıştır]

## 7. Her çalışan aşamadan sonra

> Şu an her şey çalışıyor. Kaydet ve ne yaptığımızı yaz.

Bu, **projeyi kurtaracak tek alışkanlıktır.** Atlamayın.

---

## Bilmen gereken tek klasör

```
veri/
 ├── dalsan.db      ← TÜM veritabanı bu tek dosya
 ├── goruntuler/    ← olay fotoğrafları
 ├── loglar/
 ├── nesneler/      ← Nesneler sayfasına yüklenen fotoğraflar
 ├── sesler/        ← anons ses dosyaları (.wav)
 ├── videolar/      ← "Video ile Test"e yüklenen videolar
 └── yedekler/
```

**Yedekleme = `veri/` klasörünü harici diske kopyalamak.** Hepsi bu.
Haftada bir yap.

---

## Sırada ne var

| Önce oku | Neden |
|---|---|
| `docs/10-YAPAY-ZEKA-ILE-CALISMA.md` | Çalışma yöntemi - **en önemlisi** |
| `docs/11-BILGISAYAR-UYGULAMASI.md` | Kontrol Paneli detayları |
| `docs/08-RISKLER-VE-ACIK-KARARLAR.md` §2 | 1. haftada DALSAN'a sorulacaklar |
| `docs/04-KKD-BARET-YELEK.md` §5.3 | KKD politika soruları - etiketlemeden önce |
