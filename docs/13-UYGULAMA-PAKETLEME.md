# 13 - Uygulama Paketleme (teslim edilecek dosyayı üretme)

Bu belge tek bir soruyu cevaplar: **sistemi başka birine nasıl teslim ederim?**

Cevap: ona Python kurdurmuyoruz, "İlk Kurulumu Yap" dedirtmiyoruz. Tek bir
uygulama üretiyoruz; karşı taraf ona çift tıklıyor, hepsi bu.

> Uygulamanın kullanımı (pencerede ne var, düğmeler ne yapar) `docs/11` içinde.
> Burada yalnızca **üretim** anlatılıyor.

---

## 1. Önce şunu bilin: her işletim sistemi kendi uygulamasını üretir

| Üretmek istediğiniz | Üreteceğiniz bilgisayar |
|---|---|
| Mac uygulaması (`NextGen Detector.app`) | **Mac** |
| Windows uygulaması (`NextGen Detector.exe`) | **Windows** |

Bu bir tercih değil, kuralın kendisi: kullanılan paketleme aracı **çapraz
derleme yapmaz**. Mac'te Windows uygulaması üretilemez, Windows'ta Mac
uygulaması üretilemez.

Yani Windows uygulamasını üretmek için proje klasörünün bir Windows
bilgisayarda da bulunması gerekir (USB bellek, ağ paylaşımı ya da depodan
klonlama - hangisi kolaysa).

---

## 2. Mac'te nasıl üretilir

> **Önce bir kez:** Mac'te uygulama üretmek Apple'ın komut satırı araçlarını
> ister (`otool`). Kurulu değilse üretim durur ve ekranda ne yapılacağı yazar.
> Kurmak için Terminal'e tek satır: `xcode-select --install` - açılan
> pencerede "Yükle" deyip bitmesini bekleyin, sonra aşağıdan devam edin.
> Daha önce Xcode kurduysanız bu adım gerekmez.
>
> Üretim, bu bilgisayardaki geliştirme kurulumunun Python ortamını (`.venv`,
> Python 3.12, tkinter'lı) kullanır: önce `Baslat-Mac.command` ile **İlk
> Kurulumu Yap** yapılmış olmalı. Yapılmamışsa üretim durur ve bunu söyler.

1. `paketleme/Mac-Uygulama-Uret.command` dosyasına **çift tıklayın**.
2. Bir terminal penceresi açılır ve satırlar akmaya başlar. **2-5 dakika**
   sürer; ekran arada sessiz kalabilir, bu normaldir.
3. İş bitince Finder açılır. İçinde **NextGen Detector** uygulaması durur.
4. Bu uygulamayı karşı tarafa verin. Uygulamalar klasörüne sürüklenebilir.

Boyut yaklaşık **240 MB**'dir: Python'un kendisi, görüntü işleme
kütüphaneleri ve sistemin tamamı içindedir.

**Başka bir Mac'e verirken:** uygulama imzalı değildir (Apple Developer
hesabı ayrı bir iştir). Karşı taraf ilk açışta "geliştirici doğrulanamadı"
uyarısı alabilir. Çözüm: uygulamaya **sağ tıklayıp "Aç"** demek, sonra çıkan
pencerede yine "Aç"ı seçmek. Bir kez yapılır, sonraki açılışlarda sorulmaz.

---

## 3. Windows'ta nasıl üretilir

**Gereken tek şey:** Windows bilgisayarda Python 3.12 kurulu olmalı (daha yeni bir sürüm varsa 3.12 onunla yan yana kurulabilir; üretim betiği önce 3.12’yi arar).
Yoksa <https://www.python.org/downloads/> adresinden Python 3.12 kurun ve
kurulum ekranındaki **"Add Python to PATH"** kutusunu mutlaka işaretleyin.

> Microsoft Store'da çıkan "Python" uygulamasını kurmayın. Yukarıdaki
> adresten kurun.

**Adımlar**

1. Proje klasörünün tamamını Windows bilgisayara kopyalayın.
   Klasörü **kısa bir yola** koyun - örneğin `C:\NextGen`. (Sebebi §6'da.)
2. `paketleme\Windows-Uygulama-Uret.bat` dosyasına **çift tıklayın**.
3. Siyah bir pencere açılır ve altı adım sırayla akar. İlk seferde
   **5-15 dakika** sürer (paketler indirilir).
4. İş bitince Dosya Gezgini `dist` klasörünü açar. İçindeki
   `NextGen Detector` klasöründe iki şey vardır:

   ```
   NextGen Detector.exe   ← çift tıklanacak dosya
   _internal\             ← programın parçaları, dokunulmaz
   ```

5. **Teslim ederken klasörün TAMAMINI kopyalayın**, yalnız `.exe` dosyasını
   değil. Tek başına `.exe` çalışmaz.

Betik hata verirse pencere **kapanmaz**: son satırları kopyalayıp
gönderebilirsiniz.

---

## 3.1 Teslim edilen uygulama nasıl görünür

Çift tıklayınca **iki pencere** vardır ve ikisi de programın kendi
penceresidir; **olağan tarayıcı sekmesi hiçbir yoldan açılmaz** (operatör isteği
23.09.2026; yedek pencere aşağıda):

1. **Kontrol Paneli** - başlat/durdur ve sistem günlüğü. Windows'ta görev
   çubuğunda kendi simgesiyle, ayrı bir uygulama olarak durur (Python'un
   jenerik simgesi değil); Mac'te Dock'ta `.app` simgesiyle görünür.
2. **İzleme Ekranı** - asıl kullanılan ekran. Adres çubuğu, sekme şeridi ve
   yer imleri **yoktur**; sistem başlar başlamaz kendiliğinden açılır.

İzleme Ekranı'nı işletim sisteminin **kendi web görünümü** çizer: Windows'ta
WebView2 (Windows 10 ve 11 ile gelir), Mac'te WKWebView (macOS'un parçası).
Aracı `pywebview`'dir ve uygulamanın içinde gelir; karşı tarafın hiçbir şey
kurması gerekmez. Pencere programın ayrı bir kopyasında açılır ve Kontrol
Paneli'ne bağlıdır:

* "İzleme Ekranını Aç" pencere açıkken ikinci bir pencere açmaz, açık olanı
  öne getirir (küçültülmüşse eski boyutuna döner).
* Kontrol Paneli kapanınca (ya da çökünce) izleme penceresi de kapanır:
  sunucusu durmuş boş bir ekran ortada kalmaz.
* CSV ve veri seti indirmeleri pencerede çalışır: "Kaydet" penceresi açılır.
* Ekranın kendi bip sesi, web görünümü izin vermezse bir tıklama ister; ses
  çipi bunu "etkinleştirmek için tıklayın" diye gösterir (docs/17 R41).
  Hoparlör uyarıları sunucudan çalar, buna bağlı değildir.

Web görünümü kurulamazsa (Windows'ta WebView2 kaldırılmış ya da bozuk) ekran
bilgisayardaki **Edge / Chrome / Brave**'in uygulama kipinde açılır: yine
adres çubuğu ve sekme yoktur, Windows'ta Edge her kurulumda vardır. O da
yoksa olağan tarayıcı sekmesi **açılmaz**; Kontrol Paneli günlüğü neyin eksik
olduğunu ve ne yapılacağını yazar (Windows'ta Microsoft'un sitesinden ücretsiz
"WebView2 Runtime" kurulur). Sistem ve uyarı kanalları bu sırada çalışmaya
devam eder.

Pencerenin verisi (giriş çerezi, ekranın ses tercihi) kullanıcının tarayıcı
oturumundan ayrı durur: Windows'ta ve yedek pencerede `tarayici-profili`
klasöründe, Mac'te programın kendi penceresinde ise sistemin uygulamaya
ayırdığı yerde (uygulama kimliği `com.nextgen.detector`; pywebview Mac'te
klasör seçtirmez, o yüzden `tarayici-profili`'ni silmek Mac'te girişi
sıfırlamaz). Bu veri **yedeklenmez**: içinde kullanıcı verisi değil,
önbellek vardır.

## 3.2 Hazır paketi indirmek (Windows ya da Mac bilgisayar gerekmeden)

Uygulamayı üretmek için Windows ya da Mac bilgisayar bulmak şart değildir:
GitHub, `main` dalına gelen ve uygulamayı değiştiren her gönderimde üç paketi
kendi bilgisayarlarında üretir ve teslimden önce **gerçekten açıp sınar**:
izleme penceresi işletim sisteminin web görünümünde açılıp kapanmalı,
uygulamanın tamamı sistemi kendisi başlatıp izleme penceresini açmalı.
Sınamayı geçemeyen paket yayımlanmaz (`.github/workflows/uygulama-uret.yml`).

1. GitHub'da depo sayfasında **Actions** sekmesine girin.
2. Soldan **"Uygulama üret"**i seçin, en üstteki **yeşil** çalıştırmayı açın.
   Yenisini üretmek için sağdaki **"Run workflow"** düğmesi.
3. Sayfanın altındaki **Artifacts** bölümünden bilgisayarınıza uyanı indirin:

| Dosya | Bilgisayar |
|---|---|
| `NextGen-Detector-Windows.zip` | Windows 10 / 11 (64 bit) |
| `NextGen-Detector-Mac-Apple-M.zip` | Apple M1, M2, M3, M4 işlemcili Mac |
| `NextGen-Detector-Mac-Intel.zip` | Intel işlemcili Mac |

Mac'in işlemcisini görmek için: Elma menüsü → **Bu Mac Hakkında** → "Çip"
(Apple M…) ya da "İşlemci" (Intel) satırı. Paketler 30 gün durur, sonra aynı
düğmeyle yeniden üretilir. Aynı sayfada `ekran-goruntuleri-…` adıyla, sınama
sırasında o bilgisayarda alınmış ekran görüntüleri de vardır.

**İlk açılış:**

* **Windows:** zip'e sağ tıklayın → **Tümünü ayıkla**. Çıkan klasördeki
  `NextGen Detector.exe`'ye çift tıklayın. Klasörün tamamı birlikte durmalı;
  yalnız `.exe`'yi başka yere taşımayın. İlk açılıştaki mavi uyarı için §6.3.
* **Mac:** zip'e çift tıklayın, çıkan `NextGen Detector.app`'i
  **Uygulamalar** klasörüne sürükleyin. Uygulama Apple'a kayıtlı bir
  geliştirici imzası taşımadığı için macOS ilk açılışta onu açmaz. **Sistem
  Ayarları → Gizlilik ve Güvenlik**'e girin, aşağıdaki "NextGen Detector
  engellendi" satırında **"Yine de Aç"**a basın. Bir kez yapılır.

---

## 4. Üretilen uygulama nereye veri yazar

Uygulama kendi içine yazmaz (orası salt okunur olabilir, ör. Program
Files'ta). Veritabanı, kanıt fotoğrafları, günlük ve ayarlar kullanıcının
kendi klasörüne yazılır:

| | Yer |
|---|---|
| Mac | `~/Library/Application Support/NextGen Detector/` |
| Windows | `%LOCALAPPDATA%\NextGen Detector\` - açılışı kolay yolu: Başlat'a `%LOCALAPPDATA%` yazıp Enter, sonra `NextGen Detector` klasörü |

İçinde aynı düzen vardır:

```
veri/dalsan.db          ← olay kayıtları (yedeklenecek asıl dosya)
veri/goruntuler/        ← kanıt fotoğrafları
veri/videolar/          ← "Video ile Test" sayfasından yüklenen videolar
veri/loglar/sistem.log  ← günlük
.env                    ← ayarlar
models/                 ← tanıma modeli (ilk açılışta bir kez iner)
tarayici-profili/       ← izleme penceresinin önbelleği (YEDEKLENMEZ, silinebilir; Mac'te yalnız yedek pencere)
```

**Yedek alırken kopyalanacak klasör budur.**

Uygulamanın kendi metinleri de bu klasörü söyler: hata mesajları günlüğü,
giriş ve teşhis sayfası ayar dosyasını, kılavuz ve Anons sayfası seslerin,
yedek düğmesi yedeklerin yerini yukarıdaki biçimde
(`%LOCALAPPDATA%\NextGen Detector\veri\loglar\sistem.log` gibi) verir.
Sayfalarda görünen yol Dosya Gezgini'nin adres çubuğuna ya da Finder'da
**Git → Klasöre Git** kutusuna olduğu gibi yapıştırılabilir; Kontrol Paneli'nin
günlük penceresindeki yollar da öyledir ("saat [!] mesaj" satırları, ters bölüler
tek). Eski bir kurulumdan kalan kayıtlar programın yanındaki klasörden
okunuyorsa metinler "program klasörü" der (`backend/app/kaynaklar.py`).

Bu bilgisayardaki **geliştirme kurulumunun** veri yolu değişmedi: o hâlâ proje
klasöründeki `veri/` klasörünü kullanır. İkisi birbirine karışmaz.

> **Uygulamanın yanındaki eski kayıtlar:** uygulamanın durduğu klasörde zaten
> bir `veri/dalsan.db` varsa sistem oradan çalışmaya devam eder ve hiçbir şey
> taşımaz. Kayıtları haber vermeden taşımak, yapılabilecek en tehlikeli iştir.

---

## 5. Güncelleme - sistemde bir şey değişince ne yapılır

**İki farklı kurulum, iki farklı yol var.** Hangisinde olduğunuzu Kontrol
Paneli söyler: **"Güncelle" düğmesi varsa** git kurulumundasınız (§5.1),
yoksa paketlenmiş uygulamadasınız (§5.2). Kod git yerine ZIP ile alındıysa
düğme yine görünür ama basınca "Bu klasör bir git deposu değil" der; o zaman
yeni sürümün kodu bu klasörün üstüne kopyalanır (`veri/` ve `.env` korunur),
sonra **İlk Kurulumu Yap** paketleri tazeler. Fabrika sunucusundaki Docker ya
da systemd kurulumunda Kontrol Paneli yoktur; güncelleme komutla yapılır
(`06-OPERASYON.md` §3).

### 5.1 Git kurulumu - "Güncelle" düğmesi

Kodu kendi bilgisayarınızda değiştirip GitHub'a gönderdiniz; fabrika
sunucusunun (ya da ikinci bilgisayarın) onu alması gerekiyor:

1. Kontrol Paneli'nde **Durdur**.
2. **Güncelle**.
3. **Sistemi Başlat**.

Düğmenin yaptıkları, günlükte satır satır görünür:

| Adım | Neden |
|---|---|
| Sistem çalışıyor mu diye bakar | Çalışan bir program kendi kodunu değiştiremez |
| GitHub'da yeni sürüm var mı sorar | Yoksa hiçbir şey yapmaz, "Sistem guncel" der |
| Kaydedilmemiş kod değişikliği var mı bakar | Sunucuda elle düzeltilmiş bir dosya sessizce kaybolmamalı - varsa durur ve hangi dosya olduğunu yazar |
| **Veritabanının yedeğini alır** | Güncelleme yeni bir şema göçü getirmiş olabilir ve şemalar ileri yönlüdür; yedeksiz "güncelledim, bozuldu" geri alınamaz |
| Kodu çeker | `git pull --ff-only` |
| Paket listesi değiştiyse paketleri kurar | `requirements.txt` değişmediyse **kurulum yapılmaz** - her güncellemede pip çalıştırmak dakikalar alır ve gereksizdir |

> **Kayıtlarınız silinmez.** `veri/` klasörü git'e girmez; güncelleme
> kameralara, bölgelere, kurallara ve olay geçmişine dokunmaz. `.env` de öyle.

**Uzaktan güncelleme:** düğme bilgisayarın başındadır. Uzaktan güncellemek
isterseniz o bilgisayara uzak masaüstüyle bağlanıp Kontrol Paneli'ni orada
kullanın; Kontrol Paneli bir pencere olduğu için yalın SSH'ta açılmaz. Sunucu
kurulumunda SSH ile bağlanıp `06-OPERASYON.md` §3'teki komutları çalıştırın
(`15-UZAKTAN-ERISIM.md`). Güncelleme web arayüzüne **bilerek
konmadı**: oradan çalıştırılan bir `git pull`, şifreyi ele geçiren birine
sunucuda kod çalıştırma yolu açardı.

### 5.2 Paketlenmiş uygulama - yeni sürümü üstüne kopyalama

Paketlenmiş programda git deposu yoktur; "Güncelle" düğmesi de konmaz.
Yol şudur:

1. Kod tarafında değişiklik yapılır (Claude Code ile).
2. Üretim komutu **yeniden çalıştırılır** (§2 ya da §3).
3. Yeni uygulama, eskisinin **üstüne** kopyalanır.
   * Mac: yeni `.app`'i Uygulamalar klasörüne sürükleyip "Değiştir" deyin.
   * Windows: `dist\NextGen Detector` klasörünün tamamını, eskisinin üstüne
     kopyalayın.
4. Uygulamayı açın.

**Kayıtlar silinmez.** Veri kullanıcı klasöründedir (§4), uygulamanın içinde
değil; uygulamayı değiştirmek kayıtlara dokunmaz. Ayarlar (`.env`) da orada
kalır - yani daha önce girdiğiniz kameralar (veritabanında) ve eşikler
(`.env`'de) durmaya devam eder.

Emin olmak isterseniz güncellemeden önce §4'teki klasörün bir kopyasını alın.

---

## 6. Windows'a özgü altı tuzak (ve ne yapılacağı)

Bunların hepsi üretim betiğinde ya karşılanıyor ya da uyarı olarak
söyleniyor. Yine de burada dursun, çünkü hepsi "program bozuk" gibi görünür.

### 6.1 Microsoft Store'un sahte "python" takma adı
Windows 10/11'de Python kurulu **olmasa bile** `python` komutu vardır: sıfır
baytlık bir takma addır, çalıştırılınca Mağaza penceresi açılır ve hiçbir şey
üretilmez.
**Karşılandı:** betik önce `py` başlatıcısını dener (`py -3.12`, sonra `py -3`;
en son `python`) ve adayın gerçekten Python olduğunu `import sys` ile doğrular.
Doğrulanamazsa Türkçe kurulum yönergesi verir.

### 6.2 260 karakter yol sınırı
Windows'ta bir dosya yolu 260 karakteri geçemez. Üretim sırasında proje
klasörünün altında uzun adlar oluşur; klasör zaten derindeyse üretim
"dosya bulunamadı" gibi, sebebi hiç anlaşılmayan bir hatayla kırılır.
**Karşılandı:** betik ilk adımda yolun uzunluğunu ölçer, 80 karakteri
geçiyorsa uyarır ve klasörü `C:\NextGen` altına taşımanızı önerir.

### 6.3 SmartScreen - "bilinmeyen yayıncı"
Uygulama imzalı değildir. İlk çalıştırmada mavi bir pencere çıkar:
*"Windows bilgisayarınızı korudu"*.
**Yapılacak:** **"Daha fazla bilgi"** yazısına tıklayın, sonra beliren
**"Yine de çalıştır"** düğmesine basın. Bir kez yapılır.

Uygulamayı e-posta ya da USB ile taşıdıysanız dosya "engellenmiş" gelmiş
olabilir: `.exe` dosyasına sağ tıklayın → **Özellikler** → alttaki
**"Engellemeyi kaldır"** kutusunu işaretleyin → Tamam.

### 6.4 Windows Defender'ın yeni `.exe`'yi karantinaya alması
Yeni üretilmiş, imzasız, büyük bir `.exe` - Defender bunu bazen sessizce
siler. Belirtisi: üretim başarıyla bitiyor ama klasörde `.exe` yok.
**Karşılandı:** betik üretim sonunda dosyanın gerçekten orada olup olmadığına
bakar; yoksa ne yapılacağını yazar:
Windows Güvenliği → Virüs ve tehdit koruması → **Koruma geçmişi** →
"NextGen Detector" satırı → **"Cihazda izin ver"**.

Üretim sırasında kilitlenme yaşarsanız proje klasörünü aynı ekrandan
"hariç tutulan klasör" olarak ekleyin.

### 6.5 Satır sonları (CRLF)
Bir `.bat` dosyası Unix satır sonlarıyla (LF) gelirse Windows onu yanlış okur:
komutların sonuna görünmez bir karakter takılır ve hepsi "bulunamadı" der.
**Karşılandı:** `.gitattributes` içindeki `*.bat text eol=crlf` kuralı, depodan
klonlayan herkese doğru satır sonunu verir. `tests/test_paketleme.py` bunu
korur.

### 6.6 Türkçe karakterler ve konsol kodlaması
Windows konsolunun varsayılan kod sayfası (cp857 / cp1254) her Türkçe harfi
taşımaz; taşımadığı bir harf yüzünden satırlar okunamaz hâle gelir, bazen
üretim ortasında durur.
**Karşılandı:** üretim betiğinin kendi metinleri bilerek Türkçe harf içermez;
paketleme aracını çalıştırmadan hemen önce konsol ve Python aynı kodlamaya
(UTF-8) getirilir.

---

## 7. Teslim edilen uygulama açılmıyorsa

### Windows
Uygulama pencereli üretilir: arkasında siyah komut penceresi açılmaz. Bunun
bedeli, çökerse ekranda hiçbir şey görünmemesidir. Bu yüzden uygulamanın
içine bir **açılış kancası** kondu:

* Program açılırken çökerse ekrana **Türkçe bir uyarı penceresi** gelir ve
  kayıt dosyasının yerini söyler.
* Ayrıntı şu dosyaya yazılır:
  `%LOCALAPPDATA%\NextGen Detector\veri\loglar\acilis-hatasi.log`
* Son çalıştırmanın ekran çıktısı da yanındaki
  `son-calistirma.log` dosyasındadır (boyutu sınırlıdır, diski doldurmaz).

Destek isterken gönderilecek dosya budur.

### Mac
Aynı açılış kancası Mac uygulamasında da vardır: açılırken çökerse macOS'un
uyarı penceresi çıkar ve ayrıntı
`~/Library/Application Support/NextGen Detector/veri/loglar/acilis-hatasi.log`
dosyasına yazılır. Daha fazlası için Terminal'i açıp uygulamayı oradan
çalıştırın; panele düşen satırlar aynı anda terminale de yazılır:

```
"/Applications/NextGen Detector.app/Contents/MacOS/NextGen Detector"
```

### İzleme penceresi açılmıyorsa
Kontrol Paneli günlüğü sebebi yazar (örneğin "işletim sisteminin web görünümü
açılamadı"). Pencere bileşeninin pakette olduğunu ve bu bilgisayarda
yüklendiğini uygulamanın kendisi sınar; pencere açmaz, sonucu tek satırla
söyler; bileşen sağlamsa 0 koduyla biter (pywebview yoksa 3, web görünümü
yüklenemezse 4):

```
& ".\NextGen Detector.exe" --pencere-denetimi | Out-String   (Windows, PowerShell, uygulamanın klasöründe)
"/Applications/NextGen Detector.app/Contents/MacOS/NextGen Detector" --pencere-denetimi
```

Windows'ta satırdaki `motor edgechromium` WebView2'nin kurulu olduğunu,
`motor mshtml` kurulu olmadığını söyler: o durumda ekran yedek pencerede
açılır, WebView2 Runtime kurulunca kendi penceresine döner.

---

## 8. Üretimi yapan dosyalar (ne nerede)

| Dosya | Ne yapar |
|---|---|
| `paketleme/Mac-Uygulama-Uret.command` | Mac'te çift tıklanır, `.app` üretir |
| `paketleme/Windows-Uygulama-Uret.bat` | Windows'ta çift tıklanır, `.exe` üretir |
| `paketleme/paketleme_ortak.py` | **İki tarifin ortak bölümü** - pakete ne konacağı burada yazılıdır |
| `paketleme/NextGenDetector-mac.spec` | macOS'a özel olanlar (`.app` kabuğu, kamera izni, OpenSSL düzeltmesi) |
| `paketleme/NextGenDetector-windows.spec` | Windows'a özel olanlar (`.ico` simge; `.app` kabuğu yok) |
| `paketleme/acilis_kancasi.py` | Açılış kancası - iki tarif de takar: gizli konsolun yuttuğu hataları görünür kılar (§7) |
| `paketleme/requirements-paketleme.txt` | Paketleme aracı ve pakete giren pencere bileşeni (`pywebview`) |
| `.github/workflows/uygulama-uret.yml` | Üç paketi GitHub'ın Windows ve Mac bilgisayarlarında üretip sınar (§3.2) |
| `paketleme/pencere_sinamasi.py` | Üretilen paketi gerçekten açıp sınar: izleme penceresi ve uygulamanın tamamı |

Ortak bölümün ayrı bir dosyada olması bilinçlidir: iki tarif aynı listeleri
kopyala-yapıştır taşısaydı zamanla ayrışır, biri güncellenip diğeri
unutulurdu - ve hata yalnızca o platformda, üstelik ancak uygulama
açılmayınca görülürdü.

### 8.1 Üretimin ne kadarı önceden sınanıyor

`.app` ve `.exe` bu depoda **üretilemez** (PyInstaller çapraz derleme yapmaz),
ama üretimin sınanabilir her parçası `pytest` ile sınanıyor:

| Sınanan | Nasıl |
|---|---|
| İki tarif de hatasız **çalışıyor** | Sahte bir PyInstaller ile gerçekten koşturulur; yazım hatası, tanımsız değişken, bozuk yol burada görünür |
| Pakete konacak klasörler **var** | Tarifin listesindeki her yol diskte aranır |
| Yeni eklenen modüller **pakete giriyor** | Liste `collect_submodules("app")` ile üretilir; test bunun çalıştığını doğrular |
| Paketten sistem **gerçekten açılıyor** | Tarifin listesi geçici bir klasöre kopyalanır, `sys._MEIPASS` oraya kurulur ve sistem ayrı bir süreçte açılıp sayfaları istenir |
| Kayıtlar **pakete yazılmıyor** | Aynı testte: veritabanı ve `.env` kullanıcı klasöründe, paket klasörü el değmemiş olmalı |
| `.env.example` **eksiksiz** | Sistemin okuduğu her ayar örnekte yazıyor mu; örnekte okunmayan ayar var mı |
| İzleme penceresi **tarayıcı açmıyor** | Pencere süreci sahte bir `pywebview` ile gerçekten başlatılır: açılış, öne getirme, panelle kapanış, IE motorunun reddi ve yükleme zaman aşımı gerçek borularla sınanır; kodda `webbrowser` kullanımı yasaktır (`tests/test_uygulama_penceresi.py`) |

Tarifi çalıştıran testler (ilk üç satır) yalnızca **PyInstaller kuruluysa**
çalışır (araç bilerek `backend/requirements.txt`'te değildir); kurulu değilse
atlanır, kırılmaz. Öbür satırların testleri her `pytest` koşusunda çalışır.
Hepsini çalıştırmak için:

```bash
pip install -r paketleme/requirements-paketleme.txt
pytest tests/test_paketleme.py tests/test_mac_uygulamasi.py tests/test_paketlemeye_hazirlik.py \
       tests/test_ayarlar.py tests/test_uygulama_penceresi.py
```
