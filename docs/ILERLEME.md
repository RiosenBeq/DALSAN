# İlerleme

## Kalan işlerin bitirilmesi: hız kuralı, rapor, paketleme (09.09.2026)

Üç iş kalmıştı; üçü de yapıldı ve maine gitti.

**Dördüncü kural tipi: araç hız sınırı (yol haritası #15 kapandı).** Hız verisi
zaten hesaplanıyordu (`Tespit.hiz_mps`) ama hiçbir kural onu okumuyordu; iş
teknik bir sebeple ertelenmişti: `rules.rule_type` bir CHECK kısıtıyla üç tipe
kapalı ve SQLite'ta CHECK değiştirmek tabloyu yeniden kurmak demek.

Tehlike **ölçülerek** doğrulandı: yabancı anahtar zorlaması açıkken
`DROP TABLE rules`, `events.rule_id … ON DELETE SET NULL` eylemini tetikliyor
ve tüm olay geçmişinin kural bağlantısı sessizce siliniyor.

    ONCE  : [{'id': 1, 'rule_id': 1}, {'id': 2, 'rule_id': 2}]
    SONRA : [{'id': 1, 'rule_id': None}, {'id': 2, 'rule_id': None}]

Çözüm, göç betiğine konan bir işaret satırı: `app/veritabani.py` onu görünce
yabancı anahtarı **işlem dışında** kapatıyor, sonra geri açıyor ve
`PRAGMA foreign_key_check` ile bağlantıların sağlam kaldığını doğruluyor.
Atomiklik bozulmuyor. Test bu veri kaybını kalıcı olarak bekliyor — mekanizma
kapatılınca kırmızı oluyor, denendi.

Karar mantığı (`rules/hiz.py`) tek kareye bakmıyor: aynı takibin son N
ölçümünün **ortancasını** alıyor. Kare başına hız ölçümü gürültülüdür; beş
ölçümün dördü 0,5 m/sn biri 20 m/sn ise ortalama 4,4 m/sn çıkar ve duran
forklift ceza yerdi, ortanca 0,5 m/sn kalıyor. Ekrana yazılan sayı da bu
ortanca. Ayar m/sn tutuluyor (`hiz_mps` ile aynı birim), formda km/sa
karşılığı anında yazılıyor — fabrika hız levhaları km/sa'dır.

**Dönem raporu (yol haritası #3'ün ana kısmı kapandı).** Komuta → Rapor:
kural / kamera / bölüm / bölge kırılımı, saatlik ve günlük dağılım, özet
kartları. PDF için **yeni kütüphane kurulmadı**; sayfa yazdırmaya hazır
tasarlandı ve tarayıcının "PDF olarak kaydet" adımı yeterli. Excel çıktısı
noktalı virgüllü, BOM'lu CSV.

Rapor dışarıya gidecek bir belge olduğu için sayıların **ne olmadığı** da
yazıyor: yanlış alarm oranı yalnızca işaretlenmiş olaylar üzerinden
hesaplanıyor (incelenmemiş olay "doğru uyarı" sayılmaz), gölge moddaki
kuralların olayları sayılıyor ama "hoparlörden anons çalmamış" diye
belirtiliyor, sistem olayları hiç girmiyor. Gün ve saat kovaları Türkiye
saatine göre dolduruluyor: SQL'de gruplansaydı sütunlar 3 saat kayar ve gece
vardiyası yanlış güne düşerdi.

**Paketleme doğrulaması.** `.app`/`.exe` bu depoda üretilemez, ama üretimin
sınanabilir her parçası artık testte. En büyük boşluk şuydu: Windows tarifi
sahte bir PyInstaller ile koşturuluyordu, **Mac tarifi koşturulamıyordu** —
OpenSSL düzeltmesi `otool` çağırıyor ve o araç yalnız macOS'ta var. Düzeltme
artık macOS dışında kendini atlıyor, tarif her yerde çalıştırılabiliyor;
tarifteki bir yazım hatası artık kullanıcının Mac'inde değil burada görünüyor.

İki gerçek hata daha çıktı: `otool` yoksa üretim ham İngilizce traceback ile
ölüyordu (artık Türkçe duruyor ve `xcode-select --install` diyor), ve `_ssl`
bağımlılığı çözülemezse kod uyarı yazıp **devam ediyordu** — üretilen uygulama
açılmazdı; artık duruyor.

Yeni uçtan uca test, tarifin dosya listesini geçici bir klasöre kopyalayıp
`sys._MEIPASS`'i oraya kuruyor ve sistemi **ayrı bir süreçte** açıyor: şablon,
stil ve şema betikleri pakette gerçekten bulunuyor mu, kayıtlar pakete değil
kullanıcı klasörüne mi yazılıyor. Tariften `backend/sema` çıkarılınca kırmızı
oluyor, denendi. `.env.example` eksiksizliği de kilitlendi (29 ayar, iki yönlü).

940 test yeşil (öncesi 865), ruff temiz. Kural formu ve rapor ekranı gerçek
Chromium'da denendi: konsol hatası 0, yatay taşma 0 (1440 px ve 390 px),
yazdırma kipinde sol raf ve filtre gizli. Tarayıcı iki gerçek arayüz hatası
yakaladı ve düzeltildi: rapordaki gün çubukları görünmüyordu (histogram sütunu
üç satırlı bir ızgaradır, sayı gözü atlanınca yüzdelik yükseklik sıfırlanıyor)
ve tarih/saat kartları 46 px'lik rakam ölçüsünde kutudan taşıyordu.


## Fabrikaya çıkış şartları, uzaktan erişim ve güncelleme (09.09.2026)

Üç istek arka arkaya geldi ve üçü de "sistem fabrikada tek başına ayakta
kalabilmeli" başlığının altında.

**Giriş şifresi (yol haritası #0 kapandı).** `.env` → `YONETICI_SIFRESI`.
BOŞKEN giriş sorulmaz; tek makinede çalışan bugünkü kurulum birebir aynı
kalır ve geliştirme sırasında her açılışta şifre yazmak gerekmez. Doluyken her
sayfa giriş ister. Şifresizken kurulum listesi ve Ayarlar sayfası uyarır —
sessiz bir güvenlik açığı, olmayan güvenlikten kötüdür.

**Yedekten geri yükleme (K7 kapandı).** Kontrol Paneli'nde düğme; web
arayüzünde değil, çünkü sistem çalışırken veritabanı dosyası açıktır ve
altından değiştirmek veri kaybıdır. Üç koruma: çalışan sistemde reddeder,
önce güvenlik kopyası alır, bayat `-wal`/`-shm` dosyalarını siler (kalırlarsa
SQLite eski günlüğü yeni veritabanının üstüne uygular).

**Otomatik açılış (K8 kapandı).** Docker'da `restart: unless-stopped` zaten
vardı; eksik olan provasıydı. Reboot provası ve Docker'sız kurulum için
systemd birimi `06-OPERASYON.md` §1.2.1'e yazıldı.

**Uzaktan erişim.** `.env` → `SUNUCU_ADRESI` ile sistem ağa açılabiliyor.
Emniyet kilidi: ağa açık + şifresiz kurulum **açılışta reddedilir** — o haliyle
ağdaki herkes kamera silebilirdi, uyarıyla geçiştirilecek bir durum değil.

Şifre eklemek tek başına yetmiyordu: sınırsız deneme şifreyi fiilen yok sayar.
Aynı adresten 5 yanlış denemeden sonra adres 5 dakika kilitleniyor ve
kilitliyken **doğru şifre de** kabul edilmiyor. Ters vekil arkasında çalışırsa
oturum çerezi `secure` işaretleniyor ve gerçek istemci adresi
`X-Forwarded-For`un ilk değerinden okunuyor.

Yeni belge `15-UZAKTAN-ERISIM.md`: üç seviye (yalnız sunucu / fabrika ağı /
fabrika dışı), fabrika dışı için sıralı öneri (VPN veya Tailscale → tünel →
port açma, sonuncusu **önerilmez**) ve KVKK uyarısı — fabrika içindeki
insanların görüntüsünü dışarı taşımak DALSAN'ın hukuk biriminin kararıdır.

**GitHub'dan güncelleme.** Kontrol Paneli'nde "Güncelle" düğmesi: Durdur →
Güncelle → Başlat. Önce veritabanının yedeğini alır (şema göçleri ileri
yönlüdür), kaydedilmemiş kod değişikliğinin üstüne yazmaz, paket listesi
değişmediyse pip'i hiç çalıştırmaz. Web arayüzüne bilerek konmadı: oradan
çalıştırılan bir `git pull`, şifreyi ele geçiren birine sunucuda kod
çalıştırma yolu açardı.

859 test yeşil (öncesi 804), ruff temiz. Giriş akışı gerçek Chromium'da iki
kipte de denendi: JavaScript hatası 0, konsol hatası 0.


## Taralı alan gösterimi ve çizim arka planı (09.09.2026)

Bölge çiziminde üç eksik kapatıldı; hepsi "hangi alanı seçtim, sistem neyi
görüyor" sorusunun cevabını ekranda vermeye yönelik.

**Taralı alan.** Bölgeler artık çapraz taramayla dolu çiziliyor — hem tarayıcı
tuvalinde hem **videonun üstünde**. Yalnız çerçeve çizmek yetmiyordu: alanın içi
neresi belli olmuyor, yan yana iki bölgede hangi çizginin hangisine ait olduğu
anlaşılmıyordu. İki taraf aynı deseni kullanıyor, böylece ekran ile video aynı
şeyi söylüyor. Tarama bir vurgu, örtü değil: çizgiler alanın ~%8'ini kaplıyor,
altındaki tespit kutuları okunur kalıyor (test bunu koruyor).

**Sunucu tarafında hız ölçüldü** (1080p, bölge sınır kutusu karenin ~%65'i):
tam kare boolean maskesi 22,2 ms/kare, dağınık koordinatlarla fancy-index
7,2 ms, sınır kutusunda `cv2.addWeighted` + `copyTo` **1,1 ms**. Fark
aritmetikte değil bellek erişiminde: 164 bin dağınık koordinata tek tek gitmek,
bitişik bir bloğu taramaktan pahalı. Maske ve tamponlar bölge çizimi
değişmedikçe yeniden üretilmiyor; tarama aralığı ve kalınlığı da çözünürlüğe
oranlı (sabit piksel 480p'de seyrek, 1080p'de saç teli gibi çıkıyordu).

**Bölgeye tıklayıp seçme.** Görüntüde bir bölgenin içine tıklamak onu seçiyor:
taralı görünüyor, adı ve tipi yazıyor, yanında Düzenle / Kapat / Sil çıkıyor.
Üst üste binen bölgelerde küçük olan seçiliyor — büyük bir bölgenin içindeki
küçüğe başka türlü tıklanamazdı.

**Çizim arka planı ayrıldı.** Ekran görüntüsü yükleme, "otomatik alan bul"
akışına bağlıydı; artık kendi başına bir seçim. Üç düğme: **Kareyi dondur**
(canlı akış saniyede yenilenirken köşe tıklamak zordu), **Ekran görüntüsü yükle**
(kamera takılmadan önce hazırlık), **Canlıya dön**. Yüklenen görüntü yine diske
yazılmıyor.

**Giderilen hata.** Tarayıcı, HTML olmayan yanıtlarda (ör. `/saglik` JSON'u)
`<link rel="icon">` etiketini göremediği için kök dizinden `/favicon.ico`
istiyor ve her seferinde konsola 404 düşüyordu — sistemde arıza varmış izlenimi
veren, aslında olmayan bir hata. Rota eklendi.

**Gerçek tarayıcıda doğrulandı** (Chromium): 19 sayfanın hepsi 200; bölge
seçme, kare dondurma, ekran görüntüsü yükleme, öneri yükleme, dikdörtgen çizme
ve köşe sürükleme tek tek denendi. **JavaScript hatası 0, konsol hatası 0,
4xx yanıt 0.**

804 test yeşil (öncesi 795), ruff temiz.


## Alan tanıma, bölge sayımı ve anons bağlama (09.09.2026)

Üç konu birden ele alındı: fabrika alanının tanınması, videoda sayım ve anons
sistemine bağlanma.

**Fabrika alanını tanıma (`analiz/alan_bulucu.py` — yeni).** Fabrika zemininde
alan zaten boyalıdır; sistem artık o boyayı bulup hazır bir bölge çizimi
**önerir**. İki geçiş vardır: kapama geçişi dolu alanları (beyaz çerçeveli
yükleme sahası) bulur, kümeleme geçişi ise iki paralel çizgiyle işaretli yaya
yolunu bulur — aradaki yol da alana dahil edilir; ilk geçiş iki çizgiyi ayrı
ayrı "çok ince" diye eliyordu. Öneri karar DEĞİLDİR: veritabanına hiçbir şey
yazılmaz, kullanıcı kartına tıklayıp köşeleri düzelterek kendisi kaydeder.
Ölçüldü: iki paralel kesikli sarı çizgi 4 köşeyle ~24 ms'de bulunuyor, boyasız
betonda hiçbir öneri üretilmiyor (yanlış öneri yok).

**Ekran görüntüsünden alan tanıma.** Kamera henüz takılmamışken de bölge
hazırlanabilsin diye NVR'dan alınmış bir kare yüklenebiliyor; görüntü hem
taranıyor hem çizim tuvalinin arka planı oluyor. **Yüklenen görüntü diske
yazılmaz** (KVKK + en az parça) — kalıcı olan tek şey kaydedilen bölge.
Alan bulunamadığında sistemin "boya" saydığı yerleri işaretleyen bir **teşhis
görüntüsü** dönüyor; boş bir maske, eşik oynamaktan daha açık bir yanıttır.

**Çizim kolaylıkları.** Dikdörtgen kipi (bir köşeden karşı köşeye sürükle) ve
**köşe sürükleme** eklendi — eskiden tek yanlış köşe için tüm çizim baştan
yapılıyordu.

**Bölge sayımı (`rules/sayim.py` — yeni, SAF).** Bölge çizilen her kamerada
kural gerektirmeden çalışır. Üç sayı üç ayrı soruyu cevaplar: içeride kaç var,
sayaç sıfırlandığından beri kaç ayrı nesne girdi, aynı anda en çok kaç görüldü.
Sayım **takip bazlıdır**: bölgede on dakika duran kişi bir kez sayılır (kare
bazlı sayım 6 kare/sn ile on dakikada 3600 "kişi" üretirdi). Sayılar canlı
görüntünün üstünde, bölgenin köşesinde de yazıyor. Sayım kural DEĞİLDİR: ihlal
üretmez, anons tetiklemez — yanlış sayım kimseyi yanlış uyarmaz.

**Anons sistemine bağlanma (R3 kapandı).** Eskiden tek bir JSON gövdesi
gönderiliyordu ve sahadaki IP hoparlörlerin çoğu bunu anlamazdı. Artık üç biçim
var (`json` / `form` / `get`) ve adreste `{anahtar}` / `{metin}` yer tutucuları
dolduruluyor. `str.format` bilerek kullanılmadı: anons sisteminin kendi süslü
parantezleri (`?q={id}`) `KeyError` fırlatıp anonsu tamamen susturur ve bu
sahada teşhisi en zor arızadır. **Bulunan hata:** "Bu hoparlörü dene" düğmesi
biçimi geçirmiyordu — GET bekleyen bir cihazda deneme "başarılı" derken gerçek
anons sessizce başarısız olacaktı.

**Yeni belge: `docs/14-ANONS-SISTEMI-BAGLAMA.md`** — hangi altyapıda hangi yol,
kablo uyarıları (hat girişi, hoparlör çıkışı değil), ses dosyası hazırlama, üç
biçimin örnekleri, bölüm bölüm anons, devreye alma sırası, sorun giderme tablosu
ve **anons firmanıza soracaklarınızın listesi**. Kılavuz sayfasına da iki yeni
bölüm eklendi (5 · Sayma, 8 · Anons).

**Giderilen kırılganlık.** Takip katmanındaki sınıf→numara sözlüğü elle
yazılıydı; modele yeni bir sınıf eklendiğinde (ör. saha verisiyle ince ayarlı
gerçek forklift modeli) `KeyError` verip o kamerayı **her karede** çökertecekti.
Artık `rules/tipler.py` içindeki tek kanonik listeden türetiliyor ve tanınmayan
sınıf çökme yerine atlanıp bir kez günlüğe yazılıyor.

786 test yeşil (öncesi 718), ruff temiz.


## Mac / Windows uyumu — baştan aşağı denetim (02.09.2026)

Bağımsız bir denetimle bulunan ve giderilenler (en kritikten):

- **Windows'ta çift tıklama Microsoft Mağazası'nı açıyordu.** `where python`
  Windows 10/11'de Python KURULU OLMASA BİLE başarılıdır: PATH'te sıfır baytlık
  bir "python.exe" takma adı vardır. Yardım mesajı hiç görünmüyordu. Artık
  `py -3` denenip adayın gerçekten Python olduğu doğrulanıyor.
- **Hata anında pencere kapanıyordu** — kullanıcının kopyalayacak satırı
  kalmıyordu (destek akışının tamamı buna dayanır). `pause` eklendi.
- **Kontrol Paneli günlüğü Türkçe büyük harfte donuyordu.** Alt süreç UTF-8
  yazarken panel cp1254 çözüyordu; Ş ve Ğ (0x9E) cp1254'te tanımsız olduğu için
  "SİSTEM BAŞLATILIYOR" satırı `UnicodeDecodeError` verip günlük penceresini
  sessizce donduruyordu. Artık UTF-8 okunuyor ve hata yutulmuyor.
- **Kurulum Intel Mac'te kırılıyordu.** opencv-python 5.x ve onnxruntime 1.29
  o platform için hazır paket yayınlamıyor; pip kaynaktan derlemeye kalkıp
  dakikalarca hata basıyordu. Sürümler sabitlendi; Python alt sınırı
  bağımlılıkların gerçekten istediği 3.11'e çekildi.
- **Panel çökerse sistem kilitleniyordu:** sunucu sahipsiz çalışmaya devam
  ediyor, "Durdur" onu bulamıyor, "Başlat" da kapalı kalıyordu. Artık PID
  dosyasıyla sahipsiz süreç sahiplenilip durdurulabiliyor. Windows'ta önce
  nazik kapatma (CTRL_BREAK) deneniyor: kapanış kodu artık gerçekten çalışıyor.
- **Türkçe klasör adında KKD fotoğrafları kayboluyordu.** `cv2.imwrite` yolu
  işletim sisteminin kod sayfasıyla kodlar ve `C:\Users\Gökhan\...` gibi bir
  yolda hata FIRLATMADAN başarısız olur; veritabanında var görünen, diskte
  olmayan örnekler oluşuyordu.
- **Tek kilitli dosya bakımın tamamını iptal ediyordu** (Windows'ta Defender
  veya yedekleme açık tutunca `PermissionError`); artık atlanıp devam ediliyor.
- **"Anonsu Dene" yalan söylüyordu:** komutun çıkış kodu hiç bakılmıyordu, ses
  çıkmasa da "gönderildi" yazıyordu. Artık sonuç bekleniyor ve sebep yazılıyor.
  Anons kapalıyken (ANONS=null) bunu açıkça söylüyor. Ses dosyası **.wav**
  olmak zorunda (Windows yalnız WAV çalar) ve yol POSIX biçiminde saklanıyor.
- **PowerShell tırnak kaçışı:** yolda kesme işareti varsa ("Ali'nin Sesleri")
  komut bozuluyordu — hem hata hem enjeksiyon yüzeyi.
- **Mac başlatıcısı** artık `/usr/bin/python3` yer tutucusunu en sona bırakıyor
  ("geliştirici araçları gerekiyor" penceresi iki kez açılıyordu) ve ZIP'ten
  gelen dosyanın çalıştırma iznini kendisi tazeliyor.
- **`.gitattributes` eklendi:** Windows'ta klonlanan depoda `Baslat-Mac.command`
  CRLF'e çevrilip Mac'te çalışmaz hale geliyordu.
- **Mac'te model indirme sertifika hatası** artık doğru teşhis ediliyor:
  "Install Certificates.command dosyasına çift tıklayın".
- **Görüntü üzerindeki etiketler:** OpenCV yalnız ASCII çizer, "tır" ekranda
  "t?r" görünüyordu. Overlay'de ASCII karşılıklar kullanılıyor; arayüz ve renk
  anahtarı tam Türkçe kaldı.
- **Dokümanlar düzeltildi:** DirectShow arka ucu ve bilgisayar kamerası desteği
  vaat ediliyordu, ikisi de yok. OneDrive/iCloud içine kurulum uyarısı,
  `chmod +x` talimatı ve macOS sertifika adımı eklendi.

172 test yeşil (17 yeni platform testi), ruff temiz.

## Sınıf görselleri, yaya yolu kuralı ve görüntü kalitesi (02.09.2026)

- **Sınıf görselleri ve renk anahtarı:** İnsan yeşil, forklift turuncu, tır/araç
  mavi, ihlal kırmızı (kalın), bölge mor. Kişi kutusunda **baret (B)** ve
  **reflektörlü yelek (Y)** rozetleri; yelek sahadaki gibi **sarı**. Üç durum
  gösterilir: dolu = var, kırmızı çarpı = yok, gri soru işareti = belirsiz.
  Kamera sayfasına simgeli **renk anahtarı** eklendi; renkler koddaki tabloyla
  birebir aynı (test bunu koruyor). Etiketler koyu dış hatla yazılıyor: açık
  zeminde (beton) kaybolmuyor.
- **Yaya yolu kuralı:** Bölgeyi "Yaya yolu" tipiyle çizip tek düğmeye basmak
  yetiyor. Kural, yolun **dışında** 5 saniyeden uzun kalan kişiyi uyarıyor ve
  "Lütfen yaya yolunu kullanınız." anonsuna bağlanıyor. Yolun kenarına bir adım
  atan kişi uyarı üretmiyor. Gerçek görüntüyle doğrulandı: yolun üstündeki
  kişiler uyarı üretmedi, yolun dışındaki üç kişi tam 5 saniyede uyarı üretti.
- **Görüntü kalitesi:** Sistem kareyi ölçüyor ve kamera sayfasında Türkçe uyarı
  veriyor — çok karanlık / aşırı parlak / bulanık / düşük kontrast, her biri için
  ne yapılacağıyla birlikte. `.env` → `GORUNTU_IYILESTIRME=otomatik` yerel
  kontrast dengeleme (CLAHE) uyguluyor; yalnız parlaklık kanalında çalıştığı için
  reflektörlü yeleğin sarısını bozmuyor. Tespit ve önizleme aynı kareyi
  kullanıyor: ekranda modelin gördüğü görüntü var.
- **Windows konsol kodlaması:** Türkçe karakter içeren bir log satırı Windows'un
  cp1254 konsolunda `UnicodeEncodeError` verip log sistemini çökertebiliyordu;
  akışlar UTF-8'e alındı, ayar hatası mesajı da güvenli yazılıyor.
- **Yeni doküman:** `docs/12-KAMERA-VE-GORUNTU-KALITESI.md` — kamera yerleşimi,
  sistemin tanıdığı nesneler ve renkleri, kalite sorunları ve çözümleri,
  hassasiyet ayarının sırası, forklift hakkında dürüst not, yaya yolu kurulumu.
  `docs/03` yaya yolu bölümüyle, README ve CLAUDE.md haritası güncellendi.

155 test yeşil (14 yeni), ruff temiz.

## Tanıma / sayma / uyarı turu + derin hata taraması (02.09.2026)

**Tespit isabeti (kullanıcı önceliği):**
- Sınıf seçimi artık **sınıf farkındalıklı**: 80 COCO sınıfı üzerinde argmax alınıyordu;
  bir insanı 0.35 ile "insan", 0.40 ile "sırt çantası" bulduğunda insan TAMAMEN
  düşüyordu. Artık yalnızca ilgilendiğimiz sınıflara bakılıyor.
- **İnsan için ayrı, daha düşük eşik** (kaçırılan insan, kaçırılan araçtan risklidir).
- **NMS sınıf farkındalıklı**: forkliftin yanındaki insan artık aracın kutusu
  tarafından yutulmuyor — tam da uyarı üretmesi gereken durum.
- Çok küçük kutular eleniyor (uzaktaki gürültü yanlış alarm üretmesin).
- Tüm eşikler `.env`'e taşındı (CLAUDE.md §7: koda gömülü eşik yasak):
  `TESPIT_GUVEN_ESIGI`, `TESPIT_INSAN_GUVEN_ESIGI`, `TESPIT_NMS_ESIGI`,
  `TESPIT_EN_KUCUK_KENAR_PX`.
- `CIKARIM_CIHAZI=cuda` seçilip CUDA yoksa sistem sessizce CPU'ya düşüyordu;
  artık ana sayfada Türkçe uyarı çıkıyor.

**Sayım (kullanıcı önceliği):** Ana sayfada ve kamera sayfasında **canlı sayım**
kutuları: o anda görünen insan / tır / forklift sayısı (takip bazlı, tek karelik
parlamalar sayılmaz), son 24 saatteki ihlal ve incelenmemiş ihlal sayısı.

**Uyarı (kullanıcı önceliği):** İhlalde ekranın altında kırmızı **uyarı bandı**,
isteğe bağlı **sesli uyarı** ve **Türkçe seslendirme**. Ses, tarayıcı kuralları
gereği ilk tıklamada uyandırılıyor (eskiden her uyarıda yeni ses bağlamı açan kod
sessizce çalışmazdı). Yeni **Anons sayfası**: mesaj metinleri düzenlenir, ses
dosyası bağlanır ve **"Anonsu Dene"** ile saha kurulumu sistemi kurmadan denenir.
Anons artık analiz iş parçacığını **bloklamıyor** — anons sunucusu kapalıyken tüm
kameralar 5 saniye kör kalıyordu.

**Derin tarama (36 ajanlı çapraz doğrulama) ile bulunup giderilen hatalar:**
- **Bakım hiç çalışmıyordu:** 24 saatlik sayaç makinenin AÇIK KALMA süresine
  bağlıydı; her akşam kapatılan bilgisayarda saklama süresi temizliği ve disk
  uyarısı hiç devreye girmiyordu (KVKK + disk dolması riski).
- **Kamera iş parçacığı sessizce ölüyordu:** bozuk port ("554a") gibi bir adreste
  yakalanmayan hata iş parçacığını öldürüyor, kamera sonsuza dek "çevrimdışı"
  kalıyordu. Artık hiçbir hata iş parçacığını sonlandırmıyor.
- **Bağlanıp kare vermeyen akış CPU'yu %100 döndürüyordu** (NVR bağlantı limiti,
  desteklenmeyen H.265): artık üstel bekleme burada da uygulanıyor.
- **Kural formunda iki alan aynı adı taşıyordu:** "Bölgede en az kalış" değeri
  sessizce yok sayılıyordu. Görünmeyen alanlar artık gönderilmiyor.
- **Olay tarih filtresi UTC gününe göre çalışıyordu:** Türkiye saatiyle gece
  00:00-03:00 arası olaylar yanlış güne düşüyordu.
- **Adında kesme işareti olan kamera onay sorulmadan siliniyordu** (onay metni JS
  içine gömülüydü). Onay artık tek merkezden, veri özniteliğiyle kuruluyor.
- Kamera adresi değişince eski kameranın karesi önizlemede kalıyordu; örnekleme
  hızı değişince takip hafızası yanlış kalıyordu — ikisi de düzeltildi.
- Konfigürasyon damgası uygulamadan önce yazılıyordu: yarıda kalan yenileme
  değişikliği kalıcı olarak yutuyordu.
- Çevrimdışı kamerada "son kare" zamanı siliniyordu — en çok gereken bilgi.
- Saklama süresi fotoğrafı siliyor ama kaydı temizlemiyordu (kırık resim).
- KKD kuralı yanlış tipte bir bölgeye bağlanabiliyor ve sessizce hiç çalışmıyordu.
- Anons adresi şemasız yazılırsa her ihlalde hata veriyordu — açılışta engellendi.
- Canlı uyarı listesi kamera adını HTML olarak yorumluyordu.
- Olay filtresinde sayısal olmayan değer 500 veriyordu.
- Docker sağlık kontrolü ana sayfayı çağırıyor, 30 saniyede bir tüm `veri/`
  klasörünü tarıyordu → hafif `/saglik` ucu eklendi.
- `docs/06-OPERASYON.md` terk edilmiş PostgreSQL + Alembic + 3 servis mimarisini
  anlatıyordu; içindeki her komut hatalıydı — baştan yazıldı.

141 test yeşil (29 yeni), ruff temiz. Gerçek görüntüyle uçtan uca doğrulandı:
3 insan + 1 araç tespiti, canlı sayım, kutulu önizleme, anons denemesi.

## Kamera ekleme hataları + şifresiz giriş (02.09.2026)

- **Giriş/şifre kaldırıldı** (kullanıcı kararı, geliştirme aşaması): giriş sayfası,
  oturum çerezi, `YONETICI_SIFRESI` ayarı ve Çıkış düğmesi gitti; her sayfa doğrudan
  açılır. Fabrika sunucusuna çıkmadan önce geri eklenecek → `docs/07` #0.
- **Kamera eklenince düşen sahte "Kamera çevrimdışı" olayı giderildi:** yeni ya da
  yeniden başlatılan kamera ilk 60 sn **"bağlanıyor"** sayılır (sarı rozet); olay
  yalnızca gerçek geçişlerde üretilir. Sistem her açılışta tüm kameralar için
  "çevrimdışı → tekrar çevrimiçi" olay çifti üretmiyor artık.
- **Bağlanamama SEBEBİ kamera sayfasında:** "Video dosyası bulunamadı: …",
  "Kameraya ağ üzerinden ulaşılamıyor (IP:port)", "ulaşıldı ama akış açılamadı —
  kullanıcı adı/şifre veya yol yanlış olabilir". Ulaşılamayan adreste OpenCV'nin
  uzun beklemesi yerine 3 sn'lik ağ ön kontrolü.
- **Form hataları tarayıcıda ham JSON yerine Türkçe hata sayfası** ("Geri dön ve
  düzelt"); FastAPI'nin İngilizce 422'si de Türkçeye çevrildi (hangi alan hatalı).
- **Video dosyası yolu temizlenir** (tırnak, `file://`, `\ ` kaçışı, `~`) ve dosya
  yoksa kayıt anında anlaşılır mesajla reddedilir (Mac/Windows yol kopyalama tarifi).
- **Tespit modeli otomatik indirilir:** dosya yoksa ilk açılışta bir kez (ana sayfada
  "İndiriliyor…" rozeti). Terminalde `models/indir.sh` çalıştırmak gerekmez.
- Küçükler: önizlemede kırık resim simgesi yerine "görüntü bekleniyor…" kutusu;
  pasif kamera listede "çevrimiçi" görünmüyor; bölge nokta sayısı doğru;
  CSV indirme ekrandaki filtreyi taşıyor; analiz iş parçacığı model kurulamazsa
  (ör. eksik paket) sessizce ölmüyor, sebebi ana sayfada yazıyor.
- 112 test yeşil, ruff temiz; gerçek sunucuda modelsiz açılış → otomatik indirme →
  video kaynağıyla tespit uçtan uca doğrulandı.

## Platform uyumu + Docker (26.08.2026)

- **Windows uyumu düzeltildi:** anons sesi (PowerShell SoundPlayer — `afplay`/`aplay` Windows'ta yok), kamera arka ucu (DirectShow), saat dilimi veritabanı (`tzdata` bağımlılığı).
- **Docker desteği:** üç proje için de Dockerfile + docker-compose. Veri ve ayarlar container dışında (silinse de kaybolmaz), sağlık kontrolü ve otomatik yeniden başlatma var; GPU ve ses kartı blokları Linux için hazır ve yorumlu.
- Model dosyası yoksa imaj derlemesi **anlaşılır bir mesajla durur** — modelsiz, hiçbir şey tespit etmeyen sessiz container tuzağı kapatıldı.
- **NASIL-CALISIR.md** yazıldı: sistemin işleyişi, Mac/Windows/Docker kurulumu, hangi ortamda neyin çalıştığını gösteren dürüst tablo, sorun giderme ve yedekleme.
- Docker bu makinede kurulu olmadığı için imaj derlemesi **denenemedi**; Dockerfile'lar statik olarak doğrulandı.

## Adım 2-7 + altyapılar — Sistem uçtan uca çalışır durumda (26.08.2026)

- **Kamera katmanı:** RTSP (TCP) / video dosyası kaynağı, "son kare" deseni, üstel beklemeli otomatik yeniden bağlanma, çevrimiçi/çevrimdışı takibi ve sistem olayları. Kamera CRUD + 1 sn'de yenilenen canlı önizleme (tespit kutuları çizili).
- **Tespit + takip:** YOLOX (Apache-2.0, ADR-002) ONNX Runtime ile — torch gerekmez; `models/indir.sh` modelleri indirir. ByteTrack (supervision) ile kalıcı takip ID. Forklift, saha verisiyle ince ayara kadar araç sınıfı üzerinden görünür (R1).
- **Kural motoru (`rules/`, saf):** üç kural tipi eksiksiz — bölge ihlali (inside/outside + kalış), güvenli mesafe (homografi + hareket koşulu + ardışık kare; kalibrasyonsuz kamerada bilerek pasif), KKD (üç durum + zamansal oylama; **belirsiz asla olay üretmez**). Cooldown ortak filtre; restart'sız konfig yayılımı durumu korur.
- **Olaylar:** kanıt fotoğrafı önce/DB sonra, rule_snapshot, SSE canlı uyarı paneli, filtreli liste, olay durumu (Yeni/İncelendi/Yanlış alarm + not), CSV dışa aktarma, korumalı fotoğraf servisi.
- **Kalibrasyon:** görüntüde 4 nokta tıkla + metre gir → homografi (saf numpy); arayüzde "kalibrasyon bekleniyor" rozetleri.
- **Anons:** Null / ses kartı (afplay-aplay) / HTTP adaptörleri + ekrandan bağımsız, daha uzun anons cooldown'u. Somut sistem bilgisi bekleniyor (R3).
- **KKD altyapısı:** KKD bölgelerinden saatlik limitle otomatik crop toplama + uygulama içi etiketleme sayfası (Var/Yok/Belirsiz). Model 9. adımda eğitilecek; o zamana dek KKD kuralı olay üretmez (belirsiz), veri biriktirir.
- **Güvenlik/işletim:** tek şifreli oturum (imzalı çerez), RTSP maskeleme, günlük retention + disk uyarısı, tek tıkla veritabanı yedeği.
- 92 test yeşil (kural motoru + web + entegrasyon), ruff temiz; gerçek görüntüyle uçtan uca doğrulandı (tespit → olay + kanıt fotoğrafı).
- Ayrıca: Kontrol Paneli'nin Mac'te açılmama sorunu çözüldü (çalıştırma izni + karantina + Python 3.12/tkinter).


## Adım 1 — Proje iskeleti + veritabanı + ana sayfa (26.08.2026)

- backend/ iskeleti kuruldu: .env'den okunan tek ayar kaynağı (ayarlar.py), SQLite bağlantısı (yabancı anahtar + WAL + busy_timeout) ve sürümlü şema düzeni (sema/001_ilk.sql → 7 tablo + 5 anons mesajı seed).
- Zaman yönetimi tek yerde (zaman.py: UTC sakla, İstanbul göster), JSON satır log (loglama.py → ekran + veri/loglar/sistem.log), tiplenmiş hatalar ve merkezi hata yakalayıcı (hatalar.py) eklendi.
- Teşhis ana sayfası hazır: şema sürümü, tablo listesi, maskeli aktif ayarlar, disk durumu ve "Henüz kamera eklenmedi".
- rules/ klasörü boş açıldı; saflık kuralı tests/rules/test_saflik.py ile korunuyor (doğrudan, dinamik ve dolaylı yasaklı import'lar testi kırmızı yapar).
- 30 test yeşil, ruff temiz; sıradaki iş: Adım 2 — kamera ekleme + görüntü alma.
