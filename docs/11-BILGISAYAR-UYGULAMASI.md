# 11 — Masaüstü Uygulaması (Mac & Windows)

## 1. Neyin uygulaması bu

Karışmaması gereken iki şey var:

| | Nerede çalışır | Ne işe yarar |
|---|---|---|
| **Kontrol Paneli** (bu uygulama) | Senin Mac/Windows bilgisayarında | Sistemi başlat/durdur, durumu gör, hata günlüğünü oku |
| **İzleme Ekranı** | Tarayıcıda açılır | Kameralar, bölgeler, kurallar, olaylar — asıl kullanılan ekran |

İzleme ekranı zaten Mac ve Windows'ta çalışır, çünkü **tarayıcı sayfasıdır.**
Ayrıca ek bir program kurmaya gerek yoktur; fabrikadaki bilgisayardan da,
İSG müdürünün dizüstünden de aynı adres açılır.

Kontrol Paneli'nin çözdüğü sorun ayrıdır: **terminal/komut satırı kullanmadan**
sistemi yönetebilmek.

## 2. Kurulum

### Mac

1. https://www.python.org/downloads/ → Python 3.12 indir, kur
2. DALSAN klasörünü masaüstüne koy
3. `Baslat-Mac.command` dosyasına **çift tıkla**

İlk açılışta macOS "geliştirici doğrulanamadı" diyebilir:
**Sağ tık → Aç → Aç** yaparsan bir daha sormaz.

> Homebrew ile kurulmuş Python kullanıyorsan pencere açılmayabilir.
> Terminalde `brew install python-tk` çalıştır, ya da python.org sürümünü kur.

### Windows

1. https://www.python.org/downloads/ → Python 3.12 indir
2. Kurulum ekranında **"Add Python to PATH" kutusunu işaretle** (en kritik adım)
3. DALSAN klasörünü masaüstüne koy
4. `Baslat-Windows.bat` dosyasına **çift tıkla**

SmartScreen uyarısı çıkarsa: **Daha fazla bilgi → Yine de çalıştır**

## 3. Pencerede ne var

```
┌──────────────────────────────────────────────────────┐
│  DALSAN İSG Görüntü Analiz Sistemi                   │
│  Bu pencereyi kapatırsanız sistem durur.             │
├──────────────────────────────────────────────────────┤
│  Python              Hazır (sürüm 3.12)              │
│  Gerekli paketler    Kurulu                          │
│  Sistem kodu         Hazır                           │
│  Sistem durumu       ÇALIŞIYOR — http://127.0.0.1... │
├──────────────────────────────────────────────────────┤
│ [İlk Kurulumu Yap] [Sistemi Başlat] [Durdur] [Aç]    │
├──────────────────────────────────────────────────────┤
│  Sistem günlüğü                                      │
│  ▶ Gerekli paketler kuruluyor                        │
│  ✓ SİSTEM ÇALIŞIYOR                                  │
└──────────────────────────────────────────────────────┘
```

| Bölüm | Anlamı |
|---|---|
| **Durum satırları** | 1,5 saniyede bir kendini yeniler. Hepsi yeşilse hazırsın. |
| **İlk Kurulumu Yap** | Sadece bir kez. Python ortamını hazırlar, paketleri kurar. Birkaç dakika sürer. |
| **Sistemi Başlat** | Sistemi çalıştırır ve izleme ekranını tarayıcıda açar. |
| **Durdur** | Düzgün şekilde kapatır. |
| **İzleme Ekranını Aç** | Tarayıcıyı tekrar açar (yanlışlıkla kapattıysan). |
| **Sistem günlüğü** | Olan biten. **Bir sorun olduğunda buradaki kırmızı satırları kopyalayıp Claude Code'a yapıştır.** |

## 4. Günlük kullanım

```
Çift tıkla → "Sistemi Başlat" → tarayıcı açılır → çalış → "Durdur"
```

Pencereyi kapatmak da sistemi durdurur; ayrıca "Durdur"a basman şart değil.

## 5. Durum satırları ne diyor

| Yazı | Anlamı | Ne yapmalısın |
|---|---|---|
| Python: **Hazır** | Tamam | — |
| Python: **3.10 veya üstü gerekiyor** | Sürüm eski | python.org'dan 3.12 kur |
| Paketler: **Kurulmamış** | İlk kurulum yapılmamış | "İlk Kurulumu Yap"a bas |
| Sistem kodu: **Henüz yazılmadı** | Normal — kod Claude Code ile üretilecek | Geliştirmeye devam |
| Sistem: **ÇALIŞIYOR** | Her şey yolunda | İzleme ekranını aç |
| Sistem: **Durdu** | Kapalı | "Sistemi Başlat"a bas |

## 6. Fabrika sunucusunda durum farklı

Fabrikadaki sunucuda bu pencere **kullanılmaz.** Orada sistem:

- Bilgisayar açılır açılmaz **kendiliğinden** başlar
- Kimse başında olmadan 7 gün 24 saat çalışır
- Çökerse kendini yeniden başlatır

Kontrol Paneli, **senin geliştirme ve test bilgisayarın** içindir. Fabrika kurulumu
8. haftada bir kez yapılır ve Claude Code adım adım yönlendirir.

## 7. Teslim edilen uygulamanın farkı

Sistemi **başka birine teslim ederken** ondan Python kurmasını, "İlk Kurulumu
Yap"a basmasını istemeyin. Tek bir uygulama üretilir; karşı taraf ona çift
tıklar, hepsi bu.

> **Nasıl üretilir:** Mac ve Windows için adım adım anlatım, üretilen
> uygulamanın veriyi nereye yazdığı, güncelleme ve sorun giderme
> **`docs/13-UYGULAMA-PAKETLEME.md`** içindedir. Burada yalnızca panelin
> davranış farkı yazılı.

Teslim edilen uygulamanın penceresi, bu bilgisayardaki panelden **iki noktada**
ayrılır:

| | Bu bilgisayarda (geliştirme) | Teslim edilen uygulama |
|---|---|---|
| "İlk Kurulumu Yap" | Var — Python ortamı kurulur | **Yok** — her şey içinde gelir |
| Başlama | "Sistemi Başlat"a basılır | **Kendiliğinden başlar** (pencere açıkken sistem çalışır) |

Geri kalan her şey aynıdır: Durdur, İzleme Ekranını Aç, sistem günlüğü ve
"pencereyi kapatırsanız sistem durur" kuralı değişmez.

Kayıtlar da farklı yerde durur — teslim edilen uygulama kendi içine yazamaz,
kullanıcının kendi klasörüne yazar. Bu bilgisayardaki geliştirme kurulumunun
veri yolu **değişmedi**: o hâlâ proje klasöründeki `veri/` klasörünü kullanır.
Yerlerin tam listesi `docs/13` §4'te.

## 8. Bu uygulama nasıl geliştirilebilir (ileride)

Bugün gerekmeyen ama sonradan eklenebilecekler:

| Özellik | Ne zaman gerekir |
|---|---|
| Uygulamayı imzalama (Apple / Windows sertifikası) | "Doğrulanamadı" ve "bilinmeyen yayıncı" uyarıları rahatsız etmeye başladığında |
| Fabrika sunucusuna uzaktan bağlanıp durumunu gösterme | Uzaktan bakım yapmaya başladığında |
| Kamera bağlantısı koptuğunda masaüstü bildirimi | Sisteme günlük bağımlılık arttığında |
| Tek düğmeyle yedek alma | Yedeği elle kopyalamak zahmetli gelmeye başladığında |

Hiçbiri bugün gerekli değil. Uygulama, ihtiyaç doğduğunda bunların eklenmesini
engellemeyecek şekilde yazıldı — ama bugün yazılmadılar.
