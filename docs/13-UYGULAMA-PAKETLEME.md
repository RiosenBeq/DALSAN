# 13 — Uygulama Paketleme (teslim edilecek dosyayı üretme)

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
klonlama — hangisi kolaysa).

---

## 2. Mac'te nasıl üretilir

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

**Gereken tek şey:** Windows bilgisayarda Python 3.11 veya üstü kurulu olmalı.
Yoksa <https://www.python.org/downloads/> adresinden Python 3.12 kurun ve
kurulum ekranındaki **"Add Python to PATH"** kutusunu mutlaka işaretleyin.

> Microsoft Store'da çıkan "Python" uygulamasını kurmayın. Yukarıdaki
> adresten kurun.

**Adımlar**

1. Proje klasörünün tamamını Windows bilgisayara kopyalayın.
   Klasörü **kısa bir yola** koyun — örneğin `C:\NextGen`. (Sebebi §6'da.)
2. `paketleme\Windows-Uygulama-Uret.bat` dosyasına **çift tıklayın**.
3. Siyah bir pencere açılır ve altı adım sırayla akar. İlk seferde
   **5-15 dakika** sürer (paketler indirilir).
4. İş bitince Dosya Gezgini açılır ve `dist\NextGen Detector` klasörünü
   gösterir. İçinde iki şey vardır:

   ```
   NextGen Detector.exe   ← çift tıklanacak dosya
   _internal\             ← programın parçaları, dokunulmaz
   ```

5. **Teslim ederken klasörün TAMAMINI kopyalayın**, yalnız `.exe` dosyasını
   değil. Tek başına `.exe` çalışmaz.

Betik hata verirse pencere **kapanmaz**: son satırları kopyalayıp
gönderebilirsiniz.

---

## 4. Üretilen uygulama nereye veri yazar

Uygulamanın kendi içine yazılamaz (işletim sistemi izin vermez). Veritabanı,
kanıt fotoğrafları, günlük ve ayarlar kullanıcının kendi klasörüne yazılır:

| | Yer |
|---|---|
| Mac | `~/Library/Application Support/NextGen Detector/` |
| Windows | `%LOCALAPPDATA%\NextGen Detector\` — açılışı kolay yolu: Başlat'a `%LOCALAPPDATA%` yazıp Enter, sonra `NextGen Detector` klasörü |

İçinde aynı düzen vardır:

```
veri/dalsan.db          ← olay kayıtları (yedeklenecek asıl dosya)
veri/goruntuler/        ← kanıt fotoğrafları
veri/loglar/sistem.log  ← günlük
.env                    ← ayarlar
models/                 ← tanıma modeli (ilk açılışta bir kez iner)
```

**Yedek alırken kopyalanacak klasör budur.**

Bu bilgisayardaki **geliştirme kurulumunun** veri yolu değişmedi: o hâlâ proje
klasöründeki `veri/` klasörünü kullanır. İkisi birbirine karışmaz.

> **Uygulamanın yanındaki eski kayıtlar:** uygulamanın durduğu klasörde zaten
> bir `veri/dalsan.db` varsa sistem oradan çalışmaya devam eder ve hiçbir şey
> taşımaz. Kayıtları haber vermeden taşımak, yapılabilecek en tehlikeli iştir.

---

## 5. Güncelleme — sistemde bir şey değişince ne yapılır

**İki farklı kurulum, iki farklı yol var.** Hangisinde olduğunuzu Kontrol
Paneli söyler: **"Güncelle" düğmesi varsa** git kurulumundasınız (§5.1),
yoksa paketlenmiş uygulamadasınız (§5.2).

### 5.1 Git kurulumu — "Güncelle" düğmesi

Kodu kendi bilgisayarınızda değiştirip GitHub'a gönderdiniz; fabrika
sunucusunun (ya da ikinci bilgisayarın) onu alması gerekiyor:

1. Kontrol Paneli'nde **Durdur**.
2. **Güncelle**.
3. **Sistemi Başlat**.

Düğmenin yaptıkları, günlükte satır satır görünür:

| Adım | Neden |
|---|---|
| Sistem çalışıyor mu diye bakar | Çalışan bir program kendi kodunu değiştiremez |
| GitHub'da yeni sürüm var mı sorar | Yoksa hiçbir şey yapmaz, "Sistem güncel" der |
| **Veritabanının yedeğini alır** | Güncelleme yeni bir şema göçü getirmiş olabilir ve şemalar ileri yönlüdür; yedeksiz "güncelledim, bozuldu" geri alınamaz |
| Kaydedilmemiş kod değişikliği var mı bakar | Sunucuda elle düzeltilmiş bir dosya sessizce kaybolmamalı — varsa durur ve hangi dosya olduğunu yazar |
| Kodu çeker | `git pull --ff-only` |
| Paket listesi değiştiyse paketleri kurar | `requirements.txt` değişmediyse **kurulum yapılmaz** — her güncellemede pip çalıştırmak dakikalar alır ve gereksizdir |

> **Kayıtlarınız silinmez.** `veri/` klasörü git'e girmez; güncelleme
> kameralara, bölgelere, kurallara ve olay geçmişine dokunmaz. `.env` de öyle.

**Uzaktan güncelleme:** düğme sunucunun başındadır. Uzaktan güncellemek
isterseniz sunucuya uzak masaüstü / SSH ile bağlanıp Kontrol Paneli'ni orada
kullanın (`15-UZAKTAN-ERISIM.md`). Güncelleme web arayüzüne **bilerek
konmadı**: oradan çalıştırılan bir `git pull`, şifreyi ele geçiren birine
sunucuda kod çalıştırma yolu açardı.

### 5.2 Paketlenmiş uygulama — yeni sürümü üstüne kopyalama

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
kalır — yani daha önce girdiğiniz kameralar ve eşikler durmaya devam eder.

Emin olmak isterseniz güncellemeden önce §4'teki klasörün bir kopyasını alın.

---

## 6. Windows'a özgü altı tuzak (ve ne yapılacağı)

Bunların hepsi üretim betiğinde ya karşılanıyor ya da uyarı olarak
söyleniyor. Yine de burada dursun, çünkü hepsi "program bozuk" gibi görünür.

### 6.1 Microsoft Store'un sahte "python" takma adı
Windows 10/11'de Python kurulu **olmasa bile** `python` komutu vardır: sıfır
baytlık bir takma addır, çalıştırılınca Mağaza penceresi açılır ve hiçbir şey
üretilmez.
**Karşılandı:** betik önce `py -3`'ü dener ve adayın gerçekten Python olduğunu
`import sys` ile doğrular. Doğrulanamazsa Türkçe kurulum yönergesi verir.

### 6.2 260 karakter yol sınırı
Windows'ta bir dosya yolu 260 karakteri geçemez. Üretim sırasında proje
klasörünün altında uzun adlar oluşur; klasör zaten derindeyse üretim
"dosya bulunamadı" gibi, sebebi hiç anlaşılmayan bir hatayla kırılır.
**Karşılandı:** betik ilk adımda yolun uzunluğunu ölçer, 80 karakteri
geçiyorsa uyarır ve klasörü `C:\NextGen` altına taşımanızı önerir.

### 6.3 SmartScreen — "bilinmeyen yayıncı"
Uygulama imzalı değildir. İlk çalıştırmada mavi bir pencere çıkar:
*"Windows bilgisayarınızı korudu"*.
**Yapılacak:** **"Daha fazla bilgi"** yazısına tıklayın, sonra beliren
**"Yine de çalıştır"** düğmesine basın. Bir kez yapılır.

Uygulamayı e-posta ya da USB ile taşıdıysanız dosya "engellenmiş" gelmiş
olabilir: `.exe` dosyasına sağ tıklayın → **Özellikler** → alttaki
**"Engellemeyi kaldır"** kutusunu işaretleyin → Tamam.

### 6.4 Windows Defender'ın yeni `.exe`'yi karantinaya alması
Yeni üretilmiş, imzasız, büyük bir `.exe` — Defender bunu bazen sessizce
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
Terminal'i açıp uygulamayı oradan çalıştırın; panele düşen satırlar aynı anda
terminale de yazılır:

```
"/Applications/NextGen Detector.app/Contents/MacOS/NextGen Detector"
```

---

## 8. Üretimi yapan dosyalar (ne nerede)

| Dosya | Ne yapar |
|---|---|
| `paketleme/Mac-Uygulama-Uret.command` | Mac'te çift tıklanır, `.app` üretir |
| `paketleme/Windows-Uygulama-Uret.bat` | Windows'ta çift tıklanır, `.exe` üretir |
| `paketleme/paketleme_ortak.py` | **İki tarifin ortak bölümü** — pakete ne konacağı burada yazılıdır |
| `paketleme/NextGenDetector-mac.spec` | macOS'a özel olanlar (`.app` kabuğu, kamera izni, OpenSSL düzeltmesi) |
| `paketleme/NextGenDetector-windows.spec` | Windows'a özel olanlar (`.ico` simge, gizli konsol, açılış kancası) |
| `paketleme/acilis_kancasi.py` | Gizli konsolun yuttuğu hataları görünür kılar (§7) |
| `paketleme/requirements-paketleme.txt` | Paketleme aracının kendisi |

Ortak bölümün ayrı bir dosyada olması bilinçlidir: iki tarif aynı listeleri
kopyala-yapıştır taşısaydı zamanla ayrışır, biri güncellenip diğeri
unutulurdu — ve hata yalnızca o platformda, üstelik ancak uygulama
açılmayınca görülürdü.
