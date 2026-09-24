# 11 - Masaüstü Uygulaması (Mac & Windows)

## 1. Neyin uygulaması bu

Karışmaması gereken iki şey var:

| | Nerede çalışır | Ne işe yarar |
|---|---|---|
| **Kontrol Paneli** (bu uygulama) | Senin Mac/Windows bilgisayarında | Sistemi başlat/durdur, durumu gör, hata günlüğünü oku |
| **İzleme Ekranı** | Kendi uygulama penceresinde açılır | Kameralar, bölgeler, kurallar, olaylar - asıl kullanılan ekran |

İzleme ekranı **kendi penceresinde** açılır: adres çubuğu, sekme şeridi ve yer
imleri yoktur; görev çubuğunda (Windows) ve Dock'ta (Mac) ayrı bir uygulama
olarak durur. İçeride bir web sayfası çalışıyor olması bir ayrıntıdır ve
kullanıcıya görünmez.

> **Nasıl çalışıyor:** paketlenmiş uygulamada (docs/13) ekranı işletim
> sisteminin kendi web görünümü çizer (Windows'ta WebView2, Mac'te WKWebView).
> Uygulamanın içinde gelir, ek bir şey indirmeniz gerekmez ve **tarayıcı
> açılmaz**. Bu belgedeki `Baslat-Mac.command` / `Baslat-Windows.bat`
> kurulumunda o bileşen yoktur: ekran Edge, Chrome ya da Brave'in adres
> çubuksuz "uygulama kipi"nde açılır. Web görünümü kurulamazsa paketlenmiş
> uygulama da bu yedek pencereye geçer. İkisi de olmazsa Kontrol Paneli
> günlüğü ne yapılacağını yazar (Windows'ta "WebView2 Runtime" kurulur,
> Mac'te bu üç tarayıcıdan biri kurulur ya da paketlenmiş uygulama
> kullanılır). Sistem ve uyarılar bu sırada çalışmaya devam eder. Ayrıntı:
> docs/13 §3.1.

Ağ üzerinden erişim açıldıysa (docs/15) başka bir bilgisayardan, örneğin İSG
müdürünün dizüstünden, ekran o bilgisayarın tarayıcısıyla açılır; bu
bilgisayarda tarayıcı açılmaz.

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
> Terminalde `brew install python@3.12 python-tk@3.12` çalıştır, ya da python.org sürümünü kur.

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
│  Sistem durumu       ÇALIŞIYOR - http://127.0.0.1... │
│  Analiz              Hazır - uyarılar üretiliyor     │
├──────────────────────────────────────────────────────┤
│ [İlk Kurulumu Yap] [Sistemi Başlat] [Durdur]         │
│ [İzleme Ekranını Aç] [Yedekten Geri Yükle] [Güncelle]│
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
| **Sistemi Başlat** | Sistemi çalıştırır ve izleme ekranını kendi penceresinde açar. |
| **Durdur** | Düzgün şekilde kapatır. |
| **İzleme Ekranını Aç** | İzleme penceresini açar; programın kendi penceresi zaten açıksa öne getirir (tarayıcının uygulama kipindeki yedek pencerede her basış yeni bir pencere açar). |
| **Yedekten Geri Yükle** | Yalnız sistem durmuşken: seçilen yedeği geri yükler, önce mevcut veritabanının bir kopyasını `veri/yedekler/` altına alır (docs/06 §1.2.2). |
| **Güncelle** | Yalnız sistem durmuşken: GitHub'daki yeni sürümü çeker, önce veritabanını yedekler (docs/13 §5.1). Teslim edilen uygulamada yoktur. |
| **Sistem günlüğü** | Olan biten. Sunucunun satırları "saat [!] mesaj" biçimindedir: `[HATA]` hata, `[!]` uyarıdır, işaretsiz satır bilgidir (renk yoktur). **Bir sorun olduğunda `[HATA]` ve `[!]` satırlarını kopyalayıp Claude Code'a yapıştır.** |

## 4. Günlük kullanım

```
Çift tıkla → "Sistemi Başlat" → izleme penceresi açılır → çalış → "Durdur"
```

Pencereyi kapatmak da sistemi durdurur; ayrıca "Durdur"a basman şart değil.

## 5. Durum satırları ne diyor

| Yazı | Anlamı | Ne yapmalısın |
|---|---|---|
| Python: **Hazır** | Tamam | - |
| Python: **… çok eski; Python 3.12 gerekiyor** ya da **… henüz desteklenmiyor; Python 3.12 gerekiyor** | Desteklenen tek sürüm 3.12 | python.org'dan 3.12 kur (yeni sürümle yan yana kurulabilir) |
| Gerekli paketler: **Kurulmamış** ya da **Eksik** | İlk kurulum yapılmamış ya da yarım kalmış | "İlk Kurulumu Yap"a bas |
| Sistem kodu: **Henüz yazılmadı** | Normal - kod Claude Code ile üretilecek | Geliştirmeye devam |
| Sistem durumu: **ÇALIŞIYOR** | Sunucu çalışıyor; uyarı üretilip üretilmediğini "Analiz" satırı söyler | İzleme ekranını aç |
| Sistem durumu: **Durdu** | Kapalı | "Sistemi Başlat"a bas |
| Sistem durumu: **8080 portunu başka bir program tutuyor** | XAMPP / MAMP, Tomcat, Jenkins gibi bir program portu kullanıyor | O programı kapatıp "Sistemi Başlat"a bas |
| Analiz: **Hazır - uyarılar üretiliyor** | Tamam | - |
| Analiz: sarı, kırmızı ya da gri yazı | Sistem çalışıyor ama bir eksik ya da sorun var (uyarı üretilmiyor, duyulmayabilir ya da doğrulanamıyor); yazı sebebi söyler (docs/06 §2) | docs/06 §7 |

## 6. Fabrikada durum farklı

**İlk aşamada fabrikada sunucu yok** (operatör kararı 24.09.2026): sistem
fabrikanın Windows bilgisayarında **teslim edilen uygulamayla** (§7) çalışır ve
orada kullanılan pencere o uygulamanın Kontrol Paneli'dir. Program orada siz
kapatana kadar açık kalır: takılır ya da çökerse kendini yeniden açar,
bilgisayar yeniden başlayınca Windows oturumu açılınca kendiliğinden başlar
(§7.1). Bilgisayarda bir kez yapılacaklar (BIOS, otomatik oturum açma):
docs/06 §1.5.

Sonraki aşamada bir fabrika sunucusu kurulursa (donanımı ve kurulum biçimi
docs/17 §16 S1'de açık) orada bu pencere **kullanılmaz.** Orada sistem:

- Bilgisayar açılır açılmaz **kendiliğinden** başlar
- Kimse başında olmadan 7 gün 24 saat çalışır
- Çökerse kendini yeniden başlatır

Başlat betikleriyle açılan Kontrol Paneli (§2-§5), **senin geliştirme ve test
bilgisayarın** içindir. Fabrika kurulumu 8. haftada bir kez yapılır ve Claude
Code adım adım yönlendirir.

## 7. Teslim edilen uygulamanın farkı

Sistemi **başka birine teslim ederken** ondan Python kurmasını, "İlk Kurulumu
Yap"a basmasını istemeyin. Tek bir uygulama üretilir; karşı taraf ona çift
tıklar, hepsi bu.

> **Nasıl üretilir:** Mac ve Windows için adım adım anlatım, üretilen
> uygulamanın veriyi nereye yazdığı, güncelleme ve sorun giderme
> **`docs/13-UYGULAMA-PAKETLEME.md`** içindedir. Burada yalnızca panelin
> davranış farkı yazılı.

Teslim edilen uygulamanın penceresi, bu bilgisayardaki panelden **şu
noktalarda** ayrılır:

| | Bu bilgisayarda (geliştirme) | Teslim edilen uygulama |
|---|---|---|
| "İlk Kurulumu Yap" | Var - Python ortamı kurulur | **Yok** - her şey içinde gelir |
| Başlama | "Sistemi Başlat"a basılır | **Kendiliğinden başlar.** Windows'ta siz kapatana kadar açık kalır, bilgisayar yeniden başlayınca da kendiliğinden açılır (§7.1); Mac'te pencere açıkken sistem çalışır |
| "Güncelle" | Var - GitHub'dan çeker | **Yok** - yeni uygulama eskisinin üstüne kopyalanır (docs/13 §5.2) |
| Durum satırları | Python, Gerekli paketler, Sistem kodu, Sistem durumu, Analiz | **Sistem durumu** ve **Analiz**; Windows'ta ayrıca **Sürekli çalışma** |
| Pencere başlığı | DALSAN İSG - Kontrol Paneli | NextGen Detector - Kontrol Paneli |
| Pencereyi kapatmak | Sistemi durdurur | Önce "Sistem kapatılsın mı?" diye sorar (varsayılan cevap Hayır); Evet'te sistem durur |

Geri kalan her şey aynıdır: Durdur, İzleme Ekranını Aç, Yedekten Geri Yükle ve
sistem günlüğü.

Kayıtlar da farklı yerde durur - teslim edilen uygulama kendi içine yazmaz,
kullanıcının kendi klasörüne yazar. Bu bilgisayardaki geliştirme kurulumunun
veri yolu **değişmedi**: o hâlâ proje klasöründeki `veri/` klasörünü kullanır.
Yerlerin tam listesi `docs/13` §4'te.

### 7.1 Windows'ta: siz kapatana kadar açık

Operatör isteği (24.09.2026): *"uygulamayı bir kere açınca ben kapatana kadar
otomatik açılmayı ve bu tarz senaryoları düşünüp buna göre kodla lütfen"*.
Teslim edilen Windows uygulamasında çift tıklanan `NextGen Detector.exe`
penceresiz küçük bir **gözetmendir**: Kontrol Paneli'ni kendisi açar ve açık
tutar (docs/13 §3.1).

- **Takılırsa ya da çökerse kendini yeniden açar.** Analiz takılır (bekçi),
  sistem beklenmedik şekilde durur ya da panel çökerse panel birkaç saniye
  içinde yeniden açılır ve sistemi başlatır; bir saatte en çok 3 kez. Sınır
  dolunca son bir kez açılır: bu sefer takılırsa kapanmaz, yalnız uyarır ve
  pencere sorunu gösterir. Gözetimli panel çökerse hata penceresi çıkmaz, hata
  `acilis-hatasi.log`'a yazılır (docs/13 §7).
- **Windows açılışında başlar.** Program kendini Windows'un "oturum açılınca
  başlat" listesine yazar: elektrik kesintisinden ya da Windows güncellemesinin
  yeniden başlatmasından sonra oturum açılınca kendiliğinden başlar.
- **Bilgisayar uyumaz.** Sistem çalışırken Windows uykuya geçmez; ekran
  kapanabilir, uyarı sesi yine çalar. Bilgisayarı elle uyutmak engellenmez.
- **Tek kopya.** Program açıkken yeniden açılırsa ikinci kopya açılmaz, açık
  Kontrol Paneli öne gelir; bulunamazsa "NextGen Detector zaten çalışıyor"
  der.
- **Kapatmak bir karardır.** Pencereyi kapatınca "Sistem kapatılsın mı?" diye
  sorulur, varsayılan cevap **Hayır**. **Evet** derseniz sistem durur, program
  Windows açılışından çıkar ve siz yeniden açana kadar kapalı kalır. **Durdur**
  düğmesi yalnız sistemi durdurur, programı açık bırakır.

Pencerenin üst satırı bunu söyler: "Siz kapatana kadar açık kalır: bilgisayar
yeniden başlasa da kendiliğinden açılır." **Sürekli çalışma** satırı
durumu yazar:

| Yazı | Anlamı | Ne yapmalısın |
|---|---|---|
| **Açık - takılır ya da bilgisayar yeniden başlarsa kendiliğinden açılır.** (sonunda "Bilgisayar uyumuyor.") | Her şey yolunda | - |
| **Windows açılışında kapatılmış (Görev Yöneticisi > Başlangıç uygulamaları): açın.** | Program Windows açılışında kapatılmış; program buna dokunmaz | Görev Yöneticisi'nde "NextGen Detector"ı etkinleştir |
| **Windows açılışına eklenemedi - bilgisayar yeniden başlarsa programı elle açın.** | Windows açılışındaki kayıt bu programı göstermiyor | Sebep `veri\loglar\gozetmen.log`'da; virüs koruması uyardıysa izin ver (docs/06 §1.5) |
| **Kapalı - takılırsa yalnız uyarır (son bir saatte 3 kez yeniden açıldı).** | Yeniden açma sınırı doldu | Günlükteki `[HATA]` satırlarını destek ekibine ilet; bilgisayarı yeniden başlatmak sayacı sıfırlar |

Panel her açılışta neden (yeniden) açıldığını günlüğüne yazar: Windows
açılışında kendiliğinden başladı, analiz takıldığı için bekçi kapatıp açtı,
program beklenmedik şekilde kapandı (çıkış koduyla) ya da sınır doldu.
Fabrikanın bilgisayarında bir kez yapılacaklar (BIOS, otomatik oturum açma,
ayrı Windows hesabı) docs/06 §1.5'tedir. Mac uygulamasında gözetmen, Windows
açılışında başlama ve uyku engeli yoktur; kapatma sorusu orada da sorulur.

## 8. Bu uygulama nasıl geliştirilebilir (ileride)

Bugün gerekmeyen ama sonradan eklenebilecekler:

| Özellik | Ne zaman gerekir |
|---|---|
| Uygulamayı imzalama (Apple / Windows sertifikası) | "Doğrulanamadı" ve "bilinmeyen yayıncı" uyarıları rahatsız etmeye başladığında |
| Fabrika sunucusuna uzaktan bağlanıp durumunu gösterme | Uzaktan bakım yapmaya başladığında |
| Kamera bağlantısı koptuğunda masaüstü bildirimi | Sisteme günlük bağımlılık arttığında |
| Panelden tek düğmeyle tam yedek (fotoğraflar dahil; veritabanının yedeği bugün de izleme ekranının ana sayfasında tek düğmedir: "Veritabanını Yedekle") | Yedeği elle kopyalamak zahmetli gelmeye başladığında |

Hiçbiri bugün gerekli değil. Uygulama, ihtiyaç doğduğunda bunların eklenmesini
engellemeyecek şekilde yazıldı - ama bugün yazılmadılar.
