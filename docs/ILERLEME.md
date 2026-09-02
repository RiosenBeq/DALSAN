# İlerleme

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
