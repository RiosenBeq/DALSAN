# İlerleme

## Forklift tanıyan model (23.09.2026)

Operatör: *"forklifti tanıması lazım ve bunun gibi eğitilmesi gerekiyorsa en iyi şekilde
eğit"*. Karar kaydı ve lisans çerçevesi docs/17 §16, yöntem §12.3.

- **Sorun ölçüldü:** hazır model (NextGen AI Hızlı), Open Images'teki 104 forklift
  fotoğrafında forkliftlerin yalnız %59'unu araç olarak bile buluyor; gerisini hiç görmüyor.
- **Yöntem: donuk resmi model + ek baş.** Resmi YOLOX modeli hiç değişmez; yanına yalnız
  forklift ve el transpaletini öğrenen küçük bir baş eğitilir, ikisi tek ONNX'te birleşir.
  Eğitimsiz birleşik model ürünün kendi `Tespitci`siyle 591 görüntüde resmi modelle bit bit
  aynı sonucu verdi (güven farkı 0, hız aynı); eğitimden sonra da resmi kısımların 450
  tensörü (222 BN istatistiği dahil) bit bit aynı kaldı. Böylece insan ve araç tanıma yapı
  gereği korunur, COCO görüntüsü ve öğretmen etiketi gerekmez (S20 riski artmaz).
- **Kişi önceliği:** birleşik modelde forklift puanı `x (1 - insan)^k`. Her yerde "forklift"
  diyen bozuk bir ek başla denendi: düz birleştirmede kişilerin %100'ü kayboldu; k = 1'de
  resmi modelin 0,5 ve üstü güvenle bulduğu 369 kişiden hiçbiri kaybolmadı.
- **Veri:** LOCO (CC0 1.0). Etiketler sabit commit'ten, görüntü arşivi (769 MB) TUM'un
  sunucusundan GitHub makinesinde iner (yoklama işiyle doğrulandı; bu geliştirme ortamından
  erişilemiyor). Ortam ayrık bölme: 2-3-5 eğitim, 1-4 test.
- **Eğitim hattı** (`egitim/forklift/`, `.github/workflows/forklift-egit*.yml`): veri
  hazırlama, CPU eğitimi (6 saatlik iş sınırı için ara kayıtlı bacaklar), dışa aktarım ve
  sözleşme denetimi, ürünün tespit motoruyla ölçüm, adayların ön sürüm olarak yayımı.
  Ürün dışıdır (CLAUDE.md §4 istisnası); saha görüntüsü bu hatta girmez.
- **Uygulama tarafı:** tespit modeli açılışta sözleşmeye göre sınanır (yanlış dışa aktarılmış
  model reddedilir); forklift sınıflı modelde yalnız "Tır/Araç" seçili kurallar kurulum
  listesinde söylenir; paket sınaması modelin gerçekten yüklendiğini bekler; modeller bu
  deponun yayınından SHA-256 ile iner; Ayarlar'da "Tanıma modeli" seçimi.
- **GitHub'da sınandı:** duman çalıştırması (3) 12 işin hepsinde yeşil: LOCO arşivi 2 dakikada
  indi ve SHA-256'sı sabitlendi, üç bacaklı zincir ara kayıttan sürdü, eski sınıflar resmi
  modelle aynı çıktı, model testleri makinede de geçti; ölçümde insan ve araç kaybı 0.
  İlk tam eğitim isteği (çalıştırma 4) bir kip hatasıyla dumana düştü: kuyruk ifadesi push
  olayının commit listesinden değişen dosyaları okuyordu, Actions'ta o liste boş gelir. Kip
  artık yalnız git farkından verilir, kuyruk kaldırıldı; tam eğitim çalıştırma 5'te sürüyor
  (tiny 30, s 20 devir; tiny'de adım 1,3 sn, aday başına tahminen 2,5-4 saat).
- **İlk tam eğitim (çalıştırma 5, 23-24.09.2026): dört adayın hiçbiri geçmedi.** tiny ve s,
  v1 ve v2; 6 saat 4 dakika sürdü, adaylar `forklift-r5` ön sürümünde. LOCO testinde (2277
  görüntü, 124 forklift kutusu) **tek bir doğru forklift tespiti yok** (forklift bulma oranı 0,
  en iyi forklift AP50 0,011). Resmi kısım yapı gereği korundu: insan ve araç kaybı 0,
  gecikme resmi modelin 1,0-1,17 katı. Hiçbir aday uygulamaya kaydedilmedi, varsayılan model
  değişmedi.
- **Neden (eğitim günlüğü ve tanı):** v1 ve v2'de kutu ve nesne puanı resmi modelin DONUK
  kutu dalından gelir. Kutu kaybı eğitim boyunca 3,0-3,8'de kaldı (eşleşen çapalarda resmi
  kutunun IoU'su ortalama en çok ~0,57; YOLOX sınıf hedefini bu IoU yapar), nesne kaybı
  düşmedi, gerçek kutu başına yalnız 1-4 çapa ön plan oldu; tiny-v1'in 20 test görüntüsündeki
  en yüksek forklift puanı 0,18. Resmi kutunun iyi oturduğu Open Images forklift
  fotoğraflarında bile (kutuların %97'sinde IoU'su 0,5 üstü bir çapa var) forklift puanının
  medyanı 0,06 ve hiçbirinde 0,35'i geçmiyor (k = 0 adaylarıyla). Sınıf dalını da eğiten v2
  v1'den farksız: darboğaz donuk kutu ve nesne dalı.
- **v3 kipi:** ek baş kendi kutu dalını (iki 3x3 evrişim + kutu ve nesne katmanı, resmi
  daldan başlar) öğrenir. Birleşik modelde forklift puanı eşlenen bütün resmi puanları
  geçtiği çapada kutu da ek baştan gelir; öteki her çapada kutu ve insan/araç puanları resmi
  modelinkiyle aynı kalır (denetim bunu çapa çapa sınar, kip model kartından okunur).
  Ölçüme tanı metrikleri eklendi (adayın ve resmi modelin kutu tavanı `fk_kutu_tavani`,
  `fk_kutu_tavani_resmi`; `fk_puan50_medyan`, `fk_kazanir50`): sonraki sonuçta sorunun
  kutuda mı puanda mı olduğu doğrudan görünür. Bacak iş akışının girdi
  denetimi yalnız v1 ve v2'yi kabul ediyordu, v3'ü GitHub'da ilk adımda düşürecekti:
  gönderimden önce bulundu, plandan geçen her varyantı bacağın denetiminde çalıştıran test
  eklendi.
- **Yerel sığdırma sınaması:** v1 ve v3 aynı 75 Open Images forklift fotoğrafında (101
  kutu) 30 devir eğitilip AYNI fotoğraflarda ölçüldü (genelleme değil, öğrenme kapasitesi
  sınaması): forklift puanının eşiği (0,35) ve eşlenen bütün resmi puanları geçtiği kutu oranı
  v1'de %41, v3'te %78; nesne kaybı v1'de 3,1'de kaldı, v3'te 2,0'a indi.
- **Duman (çalıştırma 6):** v3 GitHub'da eğitildi, dışa aktarıldı ve sözleşme denetiminden
  geçti (20 test görüntüsünde 3149 çapada kutu ek baştan geldi, öteki her çapada kutu ve
  insan/araç puanları resmi modelle aynı); model testleri makinede de geçti.
- **Bağımsız inceleme:** v3'te araç korumasının ölçümü iyi bir adayı haksız yere
  düşürebilirdi: doğru yeniden etiketlenen aracın kutusu oynayınca "kayıp araç" sayılıyordu
  (kapı 0) ve kutusu oynayan tır-forklift dönüşümü araç setinin kapısından kaçabiliyordu.
  Araç koruması artık adayın etiket görünümüyle (adayın sınıfları, resmi modelin kutuları)
  ölçülür; gerçek modellerle eski ve yeni ölçüm kodu v1'de gecikme dışında birebir aynı sonucu
  verdi. Ölçüm artık görüntü başına model başına bir ham çıkarımla AP'yi, bu görünümü ve tanıyı
  birlikte çıkarır.
- **İkinci tam eğitim istendi:** tiny-v3 (50 devir) ve s-v3 (30 devir).

## Hata avı ve uygulama üretim hattı (23.09.2026)

Operatör: *"bugları da çözüp tamamen profesyonel ve basitçe yapılabilen bir
sistem haline getir"*, *"windowsta exe uygulama olacak macbookta da öyle"*.

- **Tarama:** tanıtım kurulumunda (örnek video, kamera, iki bölge, kurallar,
  iki hoparlör kanalı) 24 sayfa türünün tamamı tarayıcı otomasyonuyla gezildi,
  1440 ve uygulama penceresinin en küçüğü olan 1024 genişlikte. Sunucu hatası,
  konsol hatası, kırık istek, kırık görsel ve yatay taşma: **yok**. Formlar
  sayfanın kendi değerleriyle gönderildi (ayarlar, kural ekle/düzenle, olay
  durumu, kamera düzenle, hoparlör ve anons deneme, filtreler): hepsi temiz.
  Canlı ekranlar olay akarken 20'şer saniye izlendi: konsol hatası yok.
- **Bulunan hata (düzeltildi):** kurala anons mesajı seçilmemişse (formun
  varsayılanı buydu) ya da mesaj kapatılmışsa süpervizör olayı dağıtıcıya hiç
  vermiyordu. Tanıtımda 1364 ekran teslimine karşı **sıfır** hoparlör teslimi
  vardı ve `/saglik` yine "uyarı garantisi var" diyordu. docs/17 K21'e ve
  operatörün hoparlör isteğine aykırıydı. Artık olay kendi adıyla duyurulur:
  ses çıkışı uyarı tonunu çalar, IP hoparlör olayın adını okur, garanti ve
  "ulaşmadı" denetimi çalışır. Çalışan tanıtımda doğrulandı: Bluetooth
  hoparlör 30 sn arayla tonu çaldı, aradaki tekrarlar bastırıldı. Uçtan uca
  test iki durumu da sınar; eski satırı geri koymak testi kırıyor.
- **Üretim hattı:** `.github/workflows/uygulama-uret.yml` Windows, Apple M
  çipli Mac ve Intel Mac paketlerini üretir ve yayımlamadan önce açar. İlk
  çalıştırmada Windows (Server 2025, WebView2 152) ve Apple M Mac'te bütün
  adımlar geçti: pencere bileşeni pakette, izleme penceresi gerçek web
  görünümünde açıldı (motor Edge WebView2, canlı akış var), HAZIR dedi, öne
  geldi, kanal kapanınca kendini kapattı; uygulamanın tamamı sistemi başlattı
  ve Kontrol Paneli izleme penceresini kendiliğinden açtı. Windows paketi
  123 MB (açılınca 307 MB).
- **Ağ politikası:** bu çalışma ortamı GitHub'ın paket deposuna
  (`productionresultssa15.blob.core.windows.net`) erişemiyor; paketler ve
  sınama sırasında alınan ekran görüntüleri GitHub'da Actions sayfasından
  indirilir (docs/13 §3.2).

## İzleme ekranı kendi penceresinde, tarayıcısız (23.09.2026)

Operatör: *"zaten exe olarak olması lazım tarayıcı da açılmaması lazım ve bunu
en iyi uygulama şeklinde yap fabrikada olacağı için"*.

- **Asıl yol:** işletim sisteminin web görünümü (Windows'ta WebView2, Mac'te
  WKWebView), `pywebview` 6.2.1 ile; yalnız pakete girer (CLAUDE.md §4
  istisnası). Pencere programın ayrı bir kopyasıdır (`--izleme-penceresi`) ve
  Kontrol Paneli ile iki satırlık bir dil konuşur: sayfa yüklenince `HAZIR`,
  düğmeye basılınca `GOSTER` (açık pencere öne gelir, ikincisi açılmaz). Panel
  kapanınca ya da çökünce kanal kapanır, pencere de kapanır. Pencerenin
  açılışı arka planda beklenir; panel donmaz.
- **Yedek:** web görünümü kurulamazsa Edge/Chrome/Brave uygulama kipi (adres
  çubuğu yok). Olağan tarayıcı sekmesine düşüş **kaldırıldı**; ikisi de
  olmazsa günlük ne yapılacağını yazar (WebView2 Runtime kur).
- **pywebview 6.2.1'in kaynağında bulunan dört tuzak:** (1) WebView2 yoksa
  Windows'ta sessizce Internet Explorer motoruna düşer; izleme ekranı orada
  çalışmaz, `initialized` olayında reddedilir. (2) Varsayılan ayarda yeni
  pencere isteyen bağlantılar TARAYICIYI açar; kapatıldı. (3) İndirmeler
  varsayılan olarak kapalıdır; açıldı (kaydetme penceresi). (4) `settings`
  bir `dict` değil (`UserDict`): `isinstance(..., dict)` ile korunan bir atama
  hiç çalışmazdı; ilk taslakta bu hata vardı, testle görüldü.
- **Mac'te CSV:** `download` işareti olmayan bağlantı WKWebView'de dosyayı
  indirmez, pencerede düz metin olarak açar ve geri düğmesi yoktur. Üç CSV
  bağlantısına işaret kondu; test tüm şablonları korur.
- **Yapılmayan:** ekran bipinin tıklamasız çalması için WebView2'ye
  `--autoplay-policy` bayrağı verilmedi. Microsoft bu bayrakları deneme
  içindir diye tarif ediyor ve üründe kaldırılmasını istiyor. Ses çipi
  tıklama gerektiğini gösterir; hoparlör uyarıları buna bağlı değil.
- **Doğrulanan:** süreç dili gerçek borularla, pywebview'ün davranışını taklit
  eden sahte bir kütüphaneyle sınandı: açılış, öne getirme, panelle kapanış,
  kullanıcı kapatınca sürecin bitmesi, IE motorunun reddi, yükleme zaman
  aşımı, pywebview yokken yedek. İki bilerek bozma denemesini (arka plan işini
  daemon olmayan yapmak, IE reddini kaldırmak) testler yakaladı. PyInstaller
  6.22.2 kurulu Python 3.12'de paketleme testleri 92/92 geçti.
- **DOĞRULANMADI:** gerçek Windows/Mac penceresi bu ortamda açılamaz (Linux,
  ekran yok). Paketin pencere bileşenini gerçekten içerdiği, uygulamanın
  Windows/Mac'te üretilip `--pencere-denetimi` ile sınanmasıyla görülecek.

## Yazım kuralı: çizgi işareti (23.09.2026)

Operatör kararı: sistem genelinde çizgi işareti olarak yalnız düz tire (`-`)
kullanılır. Depodaki 234 dosyada 1893 tipografik çizgi (uzun çizgi, orta çizgi,
eksi işareti) düz tireye çevrildi: kod, yorum, arayüz metni, şablon, CSS/JS,
belge. Anlam değişmedi: yer tutucu "-" hem sunucuda hem `uyari.js`'te aynı
karakterdir. Kural CLAUDE.md §7 ve §8'de ve docs/17 §16 karar kaydında;
`tests/test_yazim_kurallari.py` depoda bu karakterlerden biri kalırsa dosya ve
satırıyla kırmızı olur. Statik damga o gün `?v=39`, 4b'den sonra `?v=40`.

## Hız ve CPU (23.09.2026)

Operatör: *"hızlı ve az CPU yesin"*. Ölçüm bu ortamda (4 çekirdek, CPU,
yolox_tiny) yapıldı. En büyük kayıp ONNX Runtime'ın iş parçacıklarının her
çıkarımdan sonra boşta DÖNEREK beklemesiydi: kamera saniyede 6 kare verdiği
için aradaki bekleme uzun ve dönme işlemciyi boşa yakıyordu. `tespit.py`
artık oturumu dönme kapalı açar (`session.intra_op/inter_op.allow_spinning=0`).

| Ölçüm | Önce | Sonra |
|---|---|---|
| Saniyede 6 çıkarım, yalnız model (`ort_kiyas`) | CPU %115,5, p50 26,5 ms | CPU %57,6, p50 36,3 ms |
| Çalışan sistem, 1 kamera (vtest.avi, 6 kare/sn) | CPU %111, işleme p50 34 ms | CPU %52, işleme p50 41 ms |
| 4 kamera tam yük (`tests.hiz_kiyas --dort`), tiny | bütçe %100,4, p50/p90 68/107 ms | bütçe %100,1, p50/p90 114/162 ms |
| 4 kamera tam yük, s (İsabetli) | bütçe %50,1 | bütçe %43,4 |
| Aynı ölçümün süreç CPU'su | %350 | %252 |

CPU yüzdeleri tek çekirdeğe göredir. Hızlı modelde işlenen kare sayısı
değişmedi; gecikme 500 ms hedefinin çok altında kaldı. İsabetli model CPU'da
zaten 4 kameraya yetmiyordu (GPU ister, S1).

## Operatör istekleri (23.09.2026): hoparlör, forklift, uyarı kayıtları

Operatör: *"forklifti de tanıtmadıysan tanıt ve risk anında hoparlörden uyarı
verdiğinden emin ol (bağlı hoparlör) ve sistemde uyarı loglarını da tut 15
günde bir de temizlensin ama öncesinde temizlenmeden olan loglar masaüstüne
kaydedilsin"*.

**Risk anında hoparlör.** Zincir uçtan uca sınandı: forklift yayanın 2,4 m
yanından geçer, güvenli mesafe kuralı (hazır kuralın anonsuyla) olay açar,
gerçek `AnonsYoneticisi` "Tüm fabrika" ses çıkışı kanalındaki Bluetooth
hoparlörü `paplay --device=bluez_output…` ile çalar ve teslim kaydı olaya
bağlı "ok" olur (`tests/test_uctan_uca_olaylar.py`; gerçek ses çalınmaz,
çalıcı komutu kaydedilir). Sınarken bir boşluk çıktı: ses dosyaları ürünle
gelmiyor (docs/14 §2.3) ve mesaja WAV bağlanmamışsa ses çıkışı kanalı susuyor,
uyarı "ulaşmadı" sayılıyordu; ilk kurulumda bu her kural için böyleydi. Artık
hoparlör susmaz: WAV yoksa, bulunamazsa ya da proje klasörü dışındaysa
üretilmiş uyarı tonu çalar (`olaylar/ton.py`, test sesiyle aynı üretici, daha
yüksek ve uzun); teslim kaydı "sözlü anons yerine uyarı tonu çalındı" der.
Sahada yapılacak: her mesaja sözlü kayıt bağlamak ve "Anonsu Dene" ile
dinlemek (docs/06 §8'de madde).

**Forklift.** Bugünkü tespit modeli (hazır YOLOX, COCO) forklift sınıfı
içermez: forklift çoğu zaman araç (car/truck, ekranda "tır") olarak görülür ve
güvenli mesafe, hız ve yaya yolunda araç kuralları onu araç olarak işler; hiç
görülmediği de olur (docs/08 R1). Forkliftin kendisini tanıması eğitim ister
ve bu ortamda yapılamaz: sahadan KVKK dayanaklı etiketli kareler (S11: İSG +
NextGen), GPU'lu ayrı bir makine (eğitim ürün dışı, S31) ve kamu veri seti
(LOCO) ya da yeni ön eğitimli ağırlık kullanılacaksa hukuk görüşü (S20,
operatöre hiç gösterilmedi). Ürün tarafında eksik olan tek parça yazıldı:
docs/17 §4.2'deki sınıf listesi artık modelin ONNX üst verisinden
(`dalsan_classes`) okunuyor. Forklift sınıflı bir model konunca sistem
forklifti ayrı sınıf olarak üretir, insan eşiği doğru indekse uygulanır,
katalogda olmayan sınıf atlanıp günlüğe yazılır, okunamayan liste modeli
açmaz. Kurulum listesinin ilk adımı forkliftin ayrı sınıf olarak tanınıp
tanınmadığını söyler. Model gelince doğruluk `tests/dogruluk_kiyas` ile ölçülür
(forklift AP50 ≥ 0,90; docs/06 §8) ve car/truck ayrımı ancak ondan sonra açılır
(docs/17 §12.3-5).

**Uyarı kayıtları: 15 günde bir önce masaüstüne, sonra temizlik.** "Uyarı
logu" teslim kaydıdır (`alert_deliveries`: hangi uyarı, hangi kanal, sonuç,
gecikme); olaylar ve kanıt fotoğrafları bu kararın dışındadır (süreleri S5'te).
`olaylar/uyari_arsivi.py`: sistemdeki en eski kayıt `UYARI_KAYDI_ARSIV_GUN`
(15) günü doldurunca bakım o ana kadarki kayıtları masaüstündeki "NextGen
Detector uyarı kayıtları" klasörüne BOM'lu, noktalı virgüllü, formül kaçışlı
CSV olarak yazar, diske işler, geri okuyup satır sayısını doğrular ve ancak
sonra yalnız yazdığı satırları siler. Yazılamazsa hiçbir satır silinmez ve
Olaylar'a `ALERT_ARCHIVE_FAILED` düşer. Dondurulan olayın kaydı ne arşivlenir
ne silinir. Arşiv, süresi dolan olaylardan ÖNCE çalışır (olay silinince teslim
kaydı da giderdi). Masaüstü: Windows'ta bilinen klasör API'si (OneDrive
yönlendirmesi), macOS `~/Desktop`, Linux XDG (Türkçe "Masaüstü"); Docker'da ve
masaüstüsüz sunucuda `veri/arsiv/uyari-kayitlari`. Şema 011 imha kaydına sayı
ve dosya ekler; Ayarlar'da süre, klasör ve imha günlüğünde arşiv dosyası
görünür. CSV yazıcısı web katmanından `app/csv_yazici.py`'ye taşındı (bakım da
aynı kaçışla yazsın). DOĞRULANMADI: Windows'taki masaüstü API çağrısı (bu
ortamda Windows yok; yedek yolu sınandı).

## Eksik denetimi (23.09.2026)

GÖREV ve docs/17 §13-§14 satır satır koda ve belgelere karşı tarandı. Açık
soruya ya da sahaya bağlı olmayan maddelerin hepsi yapıldı. Bu denetimde
tamamlananlar:

- **K26 (kodda eksikti):** kalibrasyonun şeritle kontrol ölçümü yok (S7), bu
  yüzden mesafe ve hız olayı `kalibrasyon_dogrulanmadi` işaretini taşır, ekran
  değeri "≈ 1,85 m" diye yaklaşık yazar ve inceleme ekranı "Kalibrasyon:
  doğrulanmadı" der (docs/03).
- **docs/06 §8:** saha kabul listesine §13'ün 5e satırının istediği ama listede
  olmayan beş madde eklendi: kamera kablosu çekme, bölgelerin sahaya oturması
  ve kalibrasyon, bütün sesli kanallar kapalıyken kırmızı uyarı, hedef
  donanımda `tests/hiz_kiyas`, uzun süreli çalışma provası.
- **docs/07 #24-#29:** koşullu maddelerin (Ç35: "cevap evet değilse docs/07'ye
  satır olur") altısının satırı yoktu: dışlama kipi, kalibrasyon kontrol
  ölçümü, `/metrics`, systemd bildirimi, KKD uyum istatistiği, olay yazıcı
  kuyruğu.
- **S37:** aylık çalışma süresi hedefinin (≥ %99,5) paydası hiçbir belgede
  tanımlı değildi; docs/17 §16'ya soru olarak yazıldı.

**Açık soru bekleyen (kodlanmadı):**

| Madde | Bekleyen |
|---|---|
| GPU imajı, ayrı GPU gereksinim dosyası, hedef donanımda duman testi (5a) | S1 |
| systemd bildirimi (5b); container'ın root olmayan kullanıcıyla çalışması, R32 (5d) | S1 |
| `DISK_DUR_GB`: disk dolarken fotoğraf ve kırpık yazımını durdurma (5b) | S35 |
| Saklama günleri, roller, olay klibi, erişim izinin saklama süresi (5c) | S5 |
| Yüz bulanıklaştırma (5c) | S27 |
| `/metrics` ve `METRIK_ANAHTARI` | S13 |
| Kalibrasyonun şeritle kontrol ölçümü (2c) | S7 |
| ByteTrack yeni iz eşiğinin insan eşiğiyle hizalanması | S15 (kayıtlı saha videosu) |
| Kamera yerleşimi, gece ışığı, RTSP ses kanalı, VLAN | S6 |
| Aylık çalışma süresi yüzdesi | S37 |
| Yeni ön eğitimli ağırlık ya da kamu veri seti | S20 (operatöre hiç gösterilmedi) |

**Varsayılanla kapanan koşullu maddeler (kodlanmaz, docs/07):** webhook (S4),
dakika sınırı ve birleştirme (S23), Bluetooth yeniden bağlanma bekçisi (S9),
uygulama içi eşleştirme (S8), dışlama kipi (S3), KKD uyum istatistiği (S34).

**Saha ve ölçüm bekleyen:** tespit doğruluğu (`tests/dogruluk_kiyas`, etiketli
saha kareleri), hedef donanımda hız ve uyarı gecikmesi, KKD precision (model ve
en az 3 günlük gölge), yanlış alarm / saat, hoparlör gecikmesi, uzun süreli
prova. Kayıt kuyruğu (5b) yalnız ölçüm gerektirirse yazılır: sahada
`/saglik?ayrinti=1` içindeki her kameranın `ihlal_yaz_p90_ms` değerine bakılır.
Çalışan temsilcisine danışma maddesi avukat görüşünü bekliyor (docs/18).

## Faz 5 sertleştirme (23.09.2026)

**5b - R34 ve NTP.** Örnekleme hızı değişince hat artık yeniden kurulmuyor:
eskiden süpervizör hattı atıyordu ve izler, kalış sayaçları, cooldown'lar,
bölge sayımları gidiyor, açık olaylar "kamera değişti" diye kapanıyordu; aynı
kişiye yeniden uyarı üretilebiliyordu. `KameraHatti.fps_guncelle` yalnız
saniyeden kareye çevrilen iki sayıyı yeni hıza göre günceller: ByteTrack'in
kayıp iz hafızası (`max_time_lost`) ve kural/sayaç kayıp toleransı
(`ceil(TAKIP_HAFIZA_SN × fps)`). Testler aynı hat, aynı takipçi, aynı
değerlendirici ve aynı takip kimliğinin korunduğunu, süpervizörün hattı
bırakmadığını sınıyor. NTP bir belge maddesidir: docs/06 §1.2.3
(timedatectl/timesyncd, chrony, kameralar ve NVR aynı saatte) ve kabul
listesinde bir madde.

**5c - KVKK tabanı (docs/17 §10, şema 010).** Olay dondurma: olay sayfasında
sebepli "Dondur"; bakım dondurulan olayı, kanıt fotoğrafını ve teslim kaydını
süre dolsa da silmez; listede "dondurulmuş" rozeti. İmha kaydı: her bakım
koşusu `purge_log`'a sayıları ve o günkü gün sayılarını yazar. Erişim izi
(`web/erisim_izi.py`): kanıt fotoğrafı ve KKD kırpığı görüntüleme, olay ve rapor
CSV'si, KKD veri seti, gerçekten değişen ayarların adları, kural kaydı / hazır
kural / silme / gölge-anons, dondurma ve KKD kapısı; istemci adresiyle, şifre,
çerez, değer ve adres olmadan; aynı kaydın dakika içindeki tekrar görüntülenmesi
bir kez. Ayarlar → KVKK iki kaydı ve dondurulan olay sayısını gösterir.
Mahremiyet kontrolü: kamera sayfasında elle onay (`cameras.privacy_checked_at`,
010'a bu yüzden eklendi), adres değişince kalkar; kurulum listesinde zorunlu,
kırmızı olmayan adım 9. Belgeler: docs/18-KVKK.md (uyum kartı, avukat teyidi
bekler), docs/06 §1.4 ağ bölümlendirmesi, §5 dondurma ve imha kaydı, §8 kabul
maddeleri. Yapılmayanlar: yüz bulanıklaştırma (S27), roller (S5), çalışan
temsilcisi maddesi (avukata sorulacak).

**5e - tespit doğruluk takımı (docs/17 §14).** `tests/dogruluk_kiyas`: YOLO
dışa aktarım biçimli etiketli saha karelerinde (CVAT, Label Studio, Roboflow;
`siniflar.txt`'te `car=truck` gibi eşleme) sahada çalışan `Tespitci`'yi
.env eşikleriyle çağırır ve sınıf başına kutu/tahmin sayısı, recall@IoU 0,5,
precision ve AP50 (VOC her nokta enterpolasyonu) basar; GÖREV §4.8 hedefini
"tuttu / tutmadı / ölçülmedi" yazar, 50 kutunun altını "az örnek" işaretler,
isterse JSON'a yazar. Pytest kapısı değildir, veri depoya girmez; hesap
`tests/test_dogruluk_kiyas.py`'de sınanır. Saha verisi yok: ölçüm yapılmadı
(S6, S11, S15).

**5a - Python 3.12 (hedef sürüm).** Tam takım Python 3.12.3'te, gereksinimler
sıfırdan kurulmuş bir ortamda koşuldu (onnxruntime 1.30.0, opencv 4.10.0.84,
supervision 0.25.1, numpy 2.5.3, fastapi 0.141.1): 1770 geçti, 17 atlandı; 3.11
geliştirme ortamıyla aynı sonuç. GPU imajı ve hedef donanımda duman testi S1'i
bekliyor.

**Ölçüm: erişim izinin maliyeti.** Olay listesi en çok 200 küçük resim açar ve
her biri bir `access_log` yazması demektir. Bu ortamın diskinde (WAL,
synchronous=FULL) 200 ayrı yazma + commit toplam 64,6 ms, ortanca 0,29 ms, p90
0,44 ms sürdü; ayrı bir yazıcı iş parçacığı gerekmedi. Hedef sunucunun diski
farklıdır; liste sayfası orada yavaşlarsa ilk adım yazmaları toplu yapmaktır.

## Faz 4 uyarı kanalları (23.09.2026)

Plan: `docs/17-V2-TASARIM.md` §7 ve §13 (4a-4e satırları), operatörün kabul ettiği
varsayılanlarla: webhook (S4), dakika sınırı ve birleştirme (S23), Bluetooth
yeniden bağlanma bekçisi (S9) ve uygulama içi eşleştirme (S8) kodlanmaz;
kapsayıcıda ses yolu (A) (S29); tek sesli kanal Bluetooth ise çalar ve kırmızı
uyarır (S32).

**4a-1 - hoparlör adresinde SSRF reddi (R30).** IP hoparlör adresi bu bilgisayarı
(`127.x`, `localhost`, `::1`, `0.0.0.0`) ya da bağlantı-yerel ağı (`169.254.x.x`,
`fe80::`) gösteremez. Hoparlör formu kaydetmez; her anons gönderimi de yeniden
denetler, istek hiç çıkmaz. Adres ad ise çözülür ve her sonuç denetlenir
(`2130706433` gibi yazımlar da yakalanır). Özel ağ adresleri serbest. Hata ve
günlük adresi maskeli yazar. 127.0.0.1:9'u "bağlantı reddedildi" örneği olarak
kullanan iki test, fabrika ağı adresi ve sahte `urlopen` ile aynı davranışı
sınıyor.

**4a-2 - kanal satırları (K22).** Uyarı kanalının tek tanım yeri artık
`speaker_zones`: her satır ya bu bilgisayarın bir ses çıkışı (kablolu amfi ya da
Bluetooth hoparlör, `kind='ses_karti'`, `device`) ya da bir IP hoparlör
(`kind='http'`, `address`).

- *4a-2a:* şema 009 (`kind`, `device`, `health`, `health_changed_at`;
  `alert_deliveries` teslim kaydı). `.env`'deki `ANONS` / `ANONS_SES_CIHAZI` /
  `ANONS_HTTP_ADRESI` ilk açılışta bir kez "Tüm fabrika" satırına aktarılır ve
  duyulan davranış aynı kalır: `ses_karti` ve `null` ayarında hiç kullanılmayan
  eski bölgeler kapalı aktarılır. Adım `sema_surumu`'na yazılır; yarıda kalırsa
  yeniden denenir, silinen satır geri gelmez.
- *4a-2b:* olay, kameranın bölümündeki BÜTÜN açık kanallardan, bölümde kanal
  yoksa "Tüm fabrika" kanallarından duyurulur; hiç kanal yoksa ses çıkmaz ve bu
  söylenir.
- *4a-2c:* Komuta → Anons ekranında "Uyarı kanalları" listesi: her satırın kendi
  Dene düğmesi ve düzenleme formu (tür, bağlı çıkışlardan öneri listesi, o anki
  varsayılan çıkış önceden yazılı, adres). Linux'ta çıkış adı boş bırakılamaz
  (R37); test sesi kayıtlı satırın çıkışına çalar (R39). Rozetler: kapalı,
  çıkış seçilmedi (eski boş kayıt), görünmüyor (çıkış listede yok; liste
  okunamazsa ya da çıkışı işletim sistemi seçiyorsa hiçbir şey iddia edilmez).
  390 px'te kanal formunun 30 px taşması giderildi. Statik damga `?v=38`.
- *4a-2d:* üç `.env` anahtarı emekli: Ayarlar sayfasında Anons grubu yalnız
  `ANONS_HTTP_BICIMI` ve `ANONS_BEKLEME_SN`'yi tutar; eski /anons sayfasında
  kanal özeti; `/anons/ses-cikisi` ve `/anons/test-sesi` kalktı (çıkış adı bir
  daha `.env`'e yazılmaz, R14 yapı gereği kapanır); kurulum listesinin anons
  adımı açık kanal sayar. docs/14 kanal ekranına göre yeniden yazıldı.

**4a-3 - uyarı dağıtıcısı (§7.3).** Her çıkışın (ses çıkışı ya da IP hoparlör
adresi) tek işçisi ve öncelikli kuyruğu var (`olaylar/dagitici.py`): aynı
hoparlörde iki ses üst üste binmez, farklı hoparlörler birbirini beklemez;
aynı çıkışı gösteren iki satır tek ses çalar. Sıra önem sonra geliş; deneme en
sonda. Kritik uyarı çalan kritik olmayan sesi keser (çalıcı `Popen` + 100 ms
yoklama, Windows'ta `PlaySound(None)`); HTTP yalnız sırada öne geçer. Tekrar
aralığından uzun bekleyen kritik olmayan öğe `stale`. Bastırma (kamera, mesaj,
kanal) başına ve yalnız başarılı çalmada tükenir (R20); kritik açılış
denetlenmez. Her deneme `alert_deliveries`'e tek bir kayıt iş parçacığından
yazılır (`olaylar/teslim.py`): `ok`, `failed`, `preempted`, `stale`,
`suppressed_cooldown`, gölge kural için `shadow`, ekran kanalı için `ok` ya da
`no_listener` (SSE istemci sayacı, `olaylar/ekran.py`; bilgi, garantiye
sayılmaz). Olay satırı yazılamadıysa `event_id` boş kalır. Kare → çalıcı
başlangıcı `frame_to_start_ms`. Anons ekranında "Teslim kaydı" (24 saat: oran,
p50/p90, bastırılan/bayat/kesilen, izleme ekranı) ve kanal başına sayılar;
`/saglik?ayrinti=1` gecikme, ekran ve kuyruk sayısı verir. Kanal "Dene"si analiz
açıkken çıkışın kuyruğundan geçer ve sonucu yazılım gecikmesiyle gösterir.
Kapanışta kuyruklar en çok 3 sn boşaltılır. Eski kayıtlar bakımda ihlal
saklama süresiyle silinir.

**4b - kanal sağlığı ve uyarı garantisi (§7.4, K21, R37).** "anons-saglik" iş
parçacığı (`olaylar/kanal_sagligi.py`) her açık kanalı 10 sn'de bir yoklar:
ses çıkışı Linux'ta `pactl` listesinde mi (Bluetooth'ta aynı adres de sayılır),
Mac'te varsayılan çıkış mı, Windows'ta her zaman "bilinmiyor"; IP hoparlörde
≤3 sn TCP bağlantısı (R30 reddi "koptu"). Çalıcı yoksa (container, R36) "koptu",
boş çıkış adı "bilinmiyor" (`cihaz_bagli_mi("")` artık None, R37). Durum
makinesi 30 sn kesintisiz yanıtsızlıkta bir kez `AUDIO_CHANNEL_DOWN` (süren
olay), iki ardışık yanıtta `AUDIO_CHANNEL_UP` yazar; "bilinmiyor" olay üretmez.
`speaker_zones.health` kararlaşmış değeri tutar (şüpheli geçişte son karar
korunur; açılışta önceki çalışmanın kararından başlanır; çıkışı değişen ya da
kapatılan kanalın açık olayı `kanal_degisti` ile kapanır). İş parçacığı analiz
iş parçacığının açılış süpürmesinden sonra başlar, kapanış kaydından önce durur.
Yönlendirme koptu kanalı atlar; bölümde sağlıklı kanal kalmazsa "Tüm fabrika"ya
düşer (`fallback` teslim satırı), her şey koptuysa yine dener. Gölgede olmayan
olayın açılışı hiçbir sesli/uzak kanala ulaşmazsa (bastırılan ulaşmış sayılır,
ekran sayılmaz) kamera başına 5 dk'da bir `ALERT_UNDELIVERED` (aradakiler
sayılır), CRITICAL günlük ve `/saglik` `uyari_ulasmiyor` (hazırlığı bozar);
ulaşan uyarı ya da başarılı "Dene" siler. `/saglik` dar gövdeye
`uyari_garantisi` (true / false / null), sorunlara `sesli_kanal_yok`,
`yedek_ses_kanali_yok`, `tek_kanal_bluetooth` (S32: çalar, kırmızı), oturumlu
ayrıntıya `kanallar` eklendi. Kontrol Paneli, sistem şeridi ve kurulum listesi
bunları kırmızı gösterir; kurulum listesinde sesli kanal adımı artık zorunlu
(Ç39: kanal yoksa kırmızı). Anons ekranında rozetler analiz açıkken sağlık
kararıdır: bağlı / koptu / bilinmiyor / denetleniyor. Bluetooth sink'in profil
soneki değişirse ses aynı adresli sink'in bugünkü adına çalınır (4d'nin ad
çözümü). Yeni ayarlar: `ANONS_SAGLIK_ARALIGI_SN` (10), `ANONS_KOPUK_ESIGI_SN`
(30), `ULASMAYAN_UYARI_ARALIGI_SN` (300). Belgeler: docs/14 §2.1.1, §4, §4.3,
§7; docs/06 §2.

**4c - webhook: kodlanmadı** (S4 varsayılanı: alıcı sistem yok). docs/07 #4.

**4d - Bluetooth (§7.5).** Sink seçimi zorunlu ve varsayılan önceden seçili
(4a-2). MAC ayrıca saklanmaz: sink adından çözülür, önek ve profil soneki koda
yazılmaz (`bluez_output.` ve `bluez_sink.`, `AA_BB_…` ve `AA:BB:…` biçimleri
testte); yeniden bağlanan hoparlörün soneki değişirse aynı hoparlör sayılır ve
ses bugünkü adına çalınır. Kopma algısı 4b'dedir. Yeniden bağlanma bekçisi
(S9) ve programdan tara/eşleştir (S8) kodlanmadı: docs/07 #22, docs/14 §8.
Linux'ta `bluetoothctl trust` şartı docs/14 §2.1.1'de.

**4e - container ses yolu (S29 yol A), WAV'lar, saha ölçümü.** İmaja
`pulseaudio-utils` (paplay, pactl) girdi; ses yolu isteğe bağlı
`docker-compose.ses.yml` ile açılır: host'un PulseAudio/PipeWire soketi
bağlanır, `PULSE_SERVER` tanımlanır, container soketin sahibinin numarasıyla
çalışır; `privileged`, host ağı, `NET_ADMIN`/`NET_RAW`, `/dev/snd`, D-Bus
verilmez ve `tests/test_kapsayici_ses.py` bunu kilitler. Ana compose'daki
eski `/dev/snd` önerisi kaldırıldı (ALSA Bluetooth'u görmez). Ses sunucusuna
bağlanılamıyorsa (`pactl info` başarısız) ses çıkışı kanalı "bilinmiyor"
değil "koptu" sayılır: ses yolu açılmamış container sessiz kalmaz. Birleşik
yapılandırma `docker compose config` ile doğrulandı; imaj bu ortamda
derlenemedi (Docker sunucusu yok, Debian aynası kapalı): paket adı ve yol
hedef sunucuda DOĞRULANMADI. WAV'ların yeri `veri/sesler/` (açılışta oluşur,
yedeğe girer, container'da bağlıdır). docs/14 §1.1 kanal tablosu, §2.3 sekiz
mesaj ve lisans notu (işletim sistemi sesleri yalnız deneme), §2.4 Docker'da
ses, §8 sınırlar; docs/06 §1.2 ses yolu komutu, §8 kabul maddeleri, §8.1
telefon videosuyla gecikme ölçümü. docs/07 #16 (anons kayıt defteri) 4a-3 ile
kapandı; #23 hız sınırı ve birleştirme (S23) koşullu satır.

## Faz 3 KKD (23.09.2026)

Plan: `docs/17-V2-TASARIM.md` §5 ve §13 (3a-3e satırları). Operatör Faz 3 ve Faz 4
sorularının varsayılanlarını kabul etti; karar kaydı docs/17 §16'da.

**3a - politika belgesi.** `docs/kkd-politika.md` şablonu İSG ile doldurulmayı
bekliyor. Belgede şunlar var:
- Rev.02 imza satırları;
- kapsam soruları (S3);
- docs/04 §5.3'teki on soru: her birinin sistemdeki karşılığı (etiket kuralı,
  bölge çizimi ya da kural ayarı) ve cevap gelene kadarki sistem varsayılanı;
- zor örnek kodları.

**3b - KKD verisi.** Şema 008 örneklere üç sütun ekliyor: kişi boyu, netlik
(kırpığın Laplacian varyansı) ve zor örnek kodu. Kurallara da onaylı model
sürümü sütunu geliyor (3d kullanacak). Otomatik örnekleme boyu ve netliği
kaydediyor.

KKD sayfasında iki yenilik var:
- her kartın üstünde **Zor örnek** seçimi (beyaz kep, reflektörlü mont, gece
  yansıması, sırt çantası, yağmurluk, kabindeki sürücü);
- **Veri seti** bölümü: eğitim / doğrulama / test sayıları ve **Veri setini
  dışa aktar (.zip)** düğmesi.

Bölmenin birimi yerel gün; günler sırayla ayrılıyor, rastgele bölme yok. Zip'te
kırpıklar, etiket CSV'si, bölme ve her dosyanın sha256'sı var. Testler iki şeyi
denetliyor: aynı kamera ve gün iki kümede olamıyor, manifest dosyalarla tutarlı.
Biçim docs/04 §5.4'te. Statik damga `?v=34`.

**3c - KKD sınıflandırıcısı.** `models/kkd.onnx` konunca ONNX Runtime ile
çalışıyor. Sözleşme docs/04 §6.6'da: girdi RGB 0-1 128×256; normalizasyon modelin
içinde; `baret` ve `yelek` çıktıları olasılık, sıra var / yok / görünmüyor.
Yüklemede sırayla dört şey denetleniyor:
- `models/SHA256SUMS`'ta özet satırı var mı;
- özet dosyayla tutuyor mu;
- dosya açılıyor mu;
- sıfır görüntüyle deneme çalıştırması sözleşmeye uyuyor mu.

Biri tutmazsa model yüklenmiyor. Olaylar'a "Model yüklenemedi" düşüyor (kod adı
artık iki modeli de kapsıyor), sistem modelsiz devam ediyor. Karedeki kişiler tek
toplu çağrıda değerlendiriliyor. Eşik uygulanmıyor: "görünmüyor" belirsiz sayılıyor,
düşük güven kararını kural veriyor. Gözlem kırpığın netliğini de taşıyor (3d'deki
`min_netlik` için).

KKD sayfasının üstünde **KKD modeli** kartı var: doğrulandı ve sürüm, yüklü değil,
yüklenemedi (sebebiyle) ya da analiz kapalı. Önizlemede KKD zorunlu alandaki kişinin
kutusu renk alıyor; yalnız kuralın istediği kalemlere bakılıyor:
- yeşil: istenen kalemler var;
- ince kırmızı: eksik görüldü (ihlal kalın kırmızı);
- gri: belirsiz.

Renk her 5. karedeki gözlemle titremesin diye son gözlem yalnız çizim için tutuluyor.
Hız kıyasına `--kkd` turu eklendi; model yoksa tur atlanıyor, sayı uydurulmuyor.
Gerçek model olmadığı için testler sahte ORT oturumuyla koşuyor. Statik damga `?v=35`.

**3d - KKD kararı.** Baret ve yelek artık ayrı karar, ayrı olay ve ayrı bekleme:
- yalnız yelek eksikse yalnız "Yelek yok" (orta) açılıyor;
- ikisi eksikse "Baret yok" (yüksek) ve "Yelek yok" iki ayrı olay oluyor;
- bir kalem belirsize dönerse yalnız onun olayı kapanıyor.

Olay anahtarı kalemi taşıyor; yaşam döngüsünün iz denetimi buna göre düzeldi.
Şüpheli karede iki kalem de belirsiz yazılıyor (belirsiz asla olay değil):
- forklift/tır kabinindeki sürücü (varsayılan açık; ayak noktası araç kutusunda
  ya da kişi kutusunun %60'ı araçla örtüşüyor);
- üst üste iki kişi;
- bulanık kırpık.

Son ikisinin eşiği boş = kapalı; gölge ölçümüyle seçilecek. Dördü de kural
formunda.

KKD kuralı gölgede doğuyor: hazır kural (2c-4'te atlanmıştı) da formdan kurulan
da. Form anonsu açamıyor. Anonsu Komuta → Uyarı zinciri açıyor ve o an yüklü
model sürümünü onaylı olarak yazıyor. Süpervizör yüklü modeli onaylı sürümle
karşılaştırıyor. Farklıysa ya da hiç onaylanmamışsa kuralı gölgeye alıyor ve
"KKD modeli değişti" yazıyor. Pencere ve bekleme süreleri sıfırlanmıyor.

**3e-1 - anons kapısı ve gölge karnesi.** KKD anonsu artık bir kapıdan geçiyor.
Kapı baret ve yelek için ayrı, yüklü model sürümü başına ve kameralar arasında
toplu. Dört şart:
- precision (incelendi ÷ incelendi + yanlış alarm) en az 0,90;
- o kalemin bu sürümle ilk olayından bu yana en az 3 gün;
- en az 30 incelenmiş olay (tek doğru olayla %100 çıkıp kapı açılmasın, S33);
- incelenmemiş olay kalmamış.

Eşikler Ayarlar → KKD anons kapısı (`KKD_KAPI_*`). Yeni model sürümü sayacı
sıfırdan başlatıyor. Uyarı zincirinde KKD satırının altında kalem başına karne
satırı var: "Precision: 0,93 (30 incelenmiş olay, kapsama %100, model …)". Kapı
kapalıysa "Anonsu aç" gri, eksik şartlar yazıyor ve düğme ancak "Ölçülmeden
açıyorum" kutusuyla gönderiliyor. Kapı sunucuda da denetleniyor. Onayla açılınca
Olaylar'a "KKD anonsu ölçülmeden açıldı" (`PPE_GATE_OVERRIDDEN`) eksik şartlarla
yazılıyor. KKD sayfasında "Gölge karnesi ve anons kapısı" bölümü dört şartı
işaretleriyle gösteriyor. Precision ve kapsama aşağı yuvarlanıyor; ölçülmeyen
sayının yerinde "ölçülecek" yazıyor. Statik damga `?v=36`.

**3e-2 - raporda olay koduna göre yanlış alarm.** Dönem raporunda yeni
"Olay koduna göre" tablosu var. Baret yok ve Yelek yok ayrı satırda, yanlış
alarm oranları da ayrı. Kodu olmayan eski olaylar kural tipinin adıyla "(eski
kayıt)" diye görünüyor. Bütün kırılım tablolarında oranın yanında artık
inceleme kapsamı yazıyor: "%20 (kapsama %78)". Kapsama aşağı yuvarlanıyor;
işaretli sayısı hücrenin ipucunda ve CSV'de. CSV'ye "Kapsama" sütunu eklendi.
Dar ekranda kırılım tablolarının başlığı bir sütun kayıktı ("İhlal" başlığı
Pay sütununun üstündeydi); düzeldi. Statik damga `?v=37`.

**3e-3 - değerlendirme raporu.** `app/egitim/degerlendirme.py` veri seti zip'ini
ve modeli alıp tek HTML dosyası yazıyor (docs/04 §6.7). Model sahadaki yoldan
yükleniyor (özet ve sözleşme denetimi), veri setindeki her dosya manifest'le
doğrulanıyor, düşük güven kuraldaki gibi belirsiz sayılıyor. Raporda şunlar var:
- baret ve yelek için var / yok / görünmüyor karışıklık tablosu;
- "yok" precision ve recall, belirsiz oranı;
- en kötü 50 hatanın görüntüleri (önce yanlış "yok");
- kamera, gün ve zor örnek kırılımı;
- model kartı.

Görüntüler dosyanın içinde; dışa bağlantı yok. Testler sahte ORT oturumu ve
gerçek JPEG'lerle kurulan bir veri setiyle beklenen karışıklık tablosunu
sınıyor; bozuk dosya, boş test kümesi, zip olmayan dosya ve özeti tutmayan
model anlaşılır hatayla duruyor.

## Faz 5d kalan güvenlik (23.09.2026)

Plan: `docs/17-V2-TASARIM.md` §10.5 (R16, R18, R31, R32) ve §13 (5d satırı).
Faz 3 operatörün cevaplarını beklediği için soru bağlamayan bu adım öne alındı.

**R31 - CSV formül enjeksiyonu.** Olay listesi ve rapor CSV'leri artık tek bir
yazıcıdan geçiyor (`web/ortak.CsvYazici`). `=`, `+`, `-`, `@`, sekme ya da satır
başıyla başlayan metin hücresinin başına tek tırnak ekleniyor: adı
`=HYPERLINK(...)` olan bir kamera Excel'de formüle dönüşmüyor. Sayı hücreleri
değişmiyor. Web katmanında kaçışsız `csv.writer` kalmadığını bir test denetliyor.

**R18 - adresteki şifre.** Üç form adresi artık •••• ile basıyor:
- kamera düzenleme;
- hoparlör bölgesi;
- Ayarlar'daki IP hoparlör adresi.

•••• olduğu gibi kalırsa kayıtlı kullanıcı adı ve şifre korunuyor, ip ya da yol
değişse de. Yeni kimlik yazılırsa o geçerli. docs/17 yalnız kamera formunu
sayıyordu; öbür ikisinde aynı şifre açıkta kalacaktı.

Anons HTTP hatası tam adresi günlüğe yazıyordu; artık adres de hata sebebi de
maskeli. Bozuk adreste urllib'in hatası `try` dışında doğuyor ve adresle
birlikte ham çıkıyordu; o da düzeldi. Günlük biçimleyicisi de son savunma
olarak her satırı maskeliyor. Maske deseni tek yerde (`loglama.ADRES_KIMLIGI`);
şifrede ham `@` olsa da tamamı gizleniyor.

**R16 - çerez anahtarı.** Oturum çerezinin imza anahtarı şifreyle birlikte
kuruluma özgü rastgele bir sırdan türüyor: `veri/oturum.anahtar`. Dosya ilk
girişte üretiliyor ve yalnız sahibi okuyabiliyor. Ele geçen bir çerezle şifre
artık çevrimdışı denenemiyor; şifre değişince oturumlar yine düşüyor. Dosya
bozuksa yenisi üretiliyor. Yazılamıyorsa giriş yine çalışıyor, sır o çalışma
boyunca bellekte duruyor. **Bu sürüme geçince herkes bir kez yeniden giriş
yapar.**

**R32 ertelendi.** Container'ı root dışı kullanıcıyla çalıştırmak, mevcut Docker
kurulumlarında `veri/` klasörünün sahipliğini değiştirmeyi gerektiriyor;
değiştirilmezse güncellemeden sonra sistem veritabanına yazamaz. İmaj bu
ortamda derlenemediği için değişiklik doğrulanamaz. S1 (kurulum Docker mı,
systemd mi?) cevaplanınca yapılacak; `ffmpeg` paketi RTSP provasından sonra
kalkacak (docs/17).

## Faz 2e KVKK tabanı ve ölçüm (23.09.2026)

Plan: `docs/17-V2-TASARIM.md` §5.5, §5.8, §10.2, §14 ve §13 (2e satırı).

**2e-1 - KKD veri toplama kapısı.** KKD sayfasının en üstünde **"Veri toplama:
KAPALI - Rev.02 onayı bekleniyor"** kartı var. Kapı varsayılan olarak kapalı
(S10); kapalıyken hiçbir kişi görüntüsü saklanmıyor. Açmak için "Rev.02 ek
protokolü imzalandı ve çalışanlara aydınlatma yapıldı" kutusu işaretleniyor;
onaysız açma reddediliyor. Açılış ve kapanış Olaylar'a **"KKD veri toplama
açıldı / kapatıldı"** (`PPE_COLLECTION_CHANGED`) olarak düşüyor. Örnekleme
kapıyı her örnekten hemen önce okuyor: kapatınca toplama ilk denemede duruyor,
yeniden başlatma gerekmiyor; kapı okunamazsa kapalı sayılıyor. Örnek alınmayan
durumlar:
- KKD muaf alandaki (`ppe_exempt`) kişi;
- KKD kuralının `min_person_height_px`'inden kısa kişi (sayı kuraldan okunuyor).

Muaf alan KKD kuralının kararından da oyuldu (docs/03 §3). Bu tipin kuralı
2c-1'den beri bekliyordu; eskiden muaf alan hiçbir şeyi etkilemiyordu. Şemada
yüz, gömme, isim/sicil ya da iz→personel eşlemesi taşıyabilecek bir sütun
olmadığını bir test denetliyor (docs/17 §10.2). Statik damga `?v=32`.

**2e-2 - uçtan uca senaryo takımı.** `tests/fixtures/senaryolar/*.json` +
`tests/test_uctan_uca_olaylar.py`. Her senaryo için sentetik bir mp4 yazılıyor,
kareler gerçek hattan geçiyor ve olaylar veritabanına kadar izleniyor:
takip → kural → yaşam döngüsü → olay satırı. Dedektör yerine senaryoyu okuyan
bir sahte var; model gerekmiyor ve sonuç belirlenimci. Kod, önem, başlangıç,
bitiş ve bitiş sebebi ±0,5 sn ile karşılaştırılıyor. İlk beş sahne:
- yasak alana giren ve çıkan kişi;
- geçitten geçen yaya (olay yok) ile yolu geçitsiz geçen yaya;
- yanından geçen forklift (histerezisle tek yakınlık olayı);
- bir an görünmeyen kişi (tek olay);
- hız aşımı (durunca biter).

Beklenen zamanlar elle hesaplandı, ölçüm geometriyle birebir tuttu. Biçim ve
"sahadan gelen yanlış alarm buraya eklenir" yöntemi docs/03'ün ekinde.

**2e-3 - rapor: analiz edilen süre ve yanlış alarm / saat.** Komuta → Rapor'da
yeni bir tablo var. Her kamera için dört sayı gösteriyor:
- analiz edilen süre;
- incelemesi tam süre, kapsama yüzdesiyle;
- yanlış alarm / saat;
- gölgede kalan yanlış alarm.

Payda olay değil saat: `analysis_hours` (2d-2), yani tespit modeli yüklüyken
işlenen süre; kopukluk ve model yokluğu sayılmıyor. Oran yalnız incelemesi tam
kamera × gün dilimlerinden hesaplanıyor: o günün gölgede olmayan her ihlali
"İncelendi" ya da "Yanlış alarm" işaretli olmalı. Hiç tam gün yoksa hücrede
**"ölçülemedi"** yazıyor. Hedef (saatte en çok 2) aşılınca oran kırmızı. Tablo
ihlalsiz dönemde de görünüyor, çünkü "0 / sa" en iyi sonuçtur. CSV'de aynı
satırlar var.

Olaylarını bilemediğimiz dilim tam sayılmıyor; sayılsaydı "olaysız gün" sanılıp
oranı sıfıra çekerdi:
- silinmiş kameranın saatleri: olayları kamerasız kalıyor. Kimliği yeniden
  kullanılan yeni kamera eski saatleri devralmıyor, kuruluş zamanıyla ayrılıyor;
- 200 000 olay sınırına dayanınca eksik okunan en eski günler.

Kapsama aşağı yuvarlanıyor: %99,6 "%100" görünmüyor. Çok küçük oran "0" değil
"< 0,01 / sa" yazıyor. Dar ekranda kamera adı kendi satırına çıkıyor; 390 px
telefonda taşma yok (ölçüldü). Statik damga `?v=33`.

## Faz 2d görünür arıza ve sağlık (23.09.2026)

Plan: `docs/17-V2-TASARIM.md` §3.5, §3.6, §9 ve §13 (2d satırı). Alt adımlar
ayrı commit'lerdir; her birinden sonra tam paket ve `tests/rules` yeşil.

**2d-1 - fail-safe sırası.** Kayıt yapılamasa da uyarı duyuruluyor. Eskiden
ihlalin kural satırı okunamazsa ya da olay satırı yazılamazsa (kilitli
veritabanı, dolu disk) istisna anonsa hiç ulaşmadan döngüde yutuluyordu: ihlal
ne kayda geçiyor ne duyuruluyordu. Şimdi olay yazılamazsa günlüğe CRITICAL
satır düşüyor, `/saglik` `"sorunlar"`'a `olay_yazilamadi` ekleniyor (bir sonraki
başarılı kayıt temizliyor) ve anons **yine** çalıyor. Kural satırı okunamazsa
gölge ve anons kararı bellekteki kural haritasından veriliyor (yapılandırma
damgasıyla tazelenir, motorun kural imzasına girmez); gölgedeki kural bellekten
tanınıp susuyor. Okunabildiğinde yine satırın kendisi kullanılıyor: gölge modu
açıp kapatmak bir sonraki ihlalde hemen etkili. Açılışı yazılamayan olay "açık"
sayılmıyor; hatırlatma geldiğinde satırı yazılıyor.

**2d-2 - bekçi, yavaşlama, analiz saatleri.** Analiz döngüsü her turda nabız
bırakıyor; `analiz/bekci.py` 10 sn'de bir bakıyor. Görüntü gelirken nabız
`BEKCI_ESIGI_SN`'den (90) eskiyse ya da analiz iş parçacığı ölmüşse Olaylar'a
**"Analiz takıldı / Analiz durdu"** düşüyor (bekçinin kendi bağlantısıyla),
günlüğe CRITICAL satır, `/saglik`'e `analiz_takildi` / `analiz_olu`. Aynı sorun
bir kez bildiriliyor; model yüklenirken ya da hiç görüntü yokken takılma
sayılmıyor. `BEKCI_TEPKISI=yeniden_baslat` ise program olayı yazıp kendini
kapatıyor (Docker/systemd yeniden açar); masaüstü paketinde Kontrol Paneli de
kapanmasın diye her durumda yalnız uyarıyor. Bir kamerada `ANALIZ_HATA_ESIGI`
(30) kare üst üste işlenemezse kameranın hattı yeniden kuruluyor (açık olayları
"işleme hattı yeniden kuruldu" sebebiyle bitiyor) ve **"Analiz yavaşladı"**
yazılıyor; eskiden hata yalnız günlükte kalıyor, kamera sessizce analizsiz
akıyordu. İşlenen hız hedefin `FPS_UYARI_ORANI` katının altında
`ANALIZ_YAVAS_SURE_SN` (60) kalırsa da aynı olay bir kez yazılıyor; hedef,
ayarlanan hız ile kameranın gerçekten verdiği hızın küçüğü (saniyede 3 kare
veren kameradan 6 kare istenmez). `analysis_hours`'a kamera × saat başına analiz
edilen süre (model yüklüyken işlenen ardışık kareler arası, 5 sn'den uzun
boşluk sayılmaz), işlenen ve başarısız kare sayısı dakikada bir yazılıyor;
yazılamazsa birikim kaybolmuyor. Dört yeni ayar Ayarlar → **Analiz sağlığı**
grubunda.

**2d-3a - `/saglik` ve sağlık ekranı.** `/saglik` artık `hazir` veriyor: analiz
çalışıyor, model hazır ve hizmeti bozan bir sorun yoksa true. Her durumda 200 ve
`"calisiyor"` dönüyor (Kontrol Paneli'nin sözleşmesi). `?hazirlik=1` ise hazır
olmayan sistemde 503 dönüyor; Docker healthcheck buna geçti. Kimliksiz gövde
dar: durum, analiz, model, hazır ve sorun kodları. Kamera başına okunan ve
işlenen hız, işleme süresi (p50/p90), son karenin yaşı, boş disk ve analiz
turunun yaşı `?ayrinti=1` ile ve oturum açıkken geliyor; kamera adı yok,
yalnız id. Yeni sorun kodları `model_yuklenemedi` ve `ort_paket_cakismasi`.
Veritabanı okunamazsa kod artık `veritabani_acilamadi` (eskiden
`saglik_dogrulanamadi`). Kalibrasyon bekleyen kural ve paket çakışması
`hazir`'ı bozmuyor: yapılandırma eksiği Docker'ı "unhealthy" yapmamalı; ekran
yine kırmızı gösteriyor. Komuta → Sağlık'ta okunan ve işlenen hız ayrı
sütunlarda (R12: ekran "işlenen" deyip okunanı gösteriyordu). İşlenen hız
hedefin altındaysa ▼ ve açıklama çıkıyor; hücrenin ipucunda hedef ve işleme
süresi (p90) var. `uyari_garantisi` alanı ses kanalı sağlığıyla birlikte 4b'de
gelecek; bugün hesaplanamıyor. Statik damga `?v=30`.

**2d-3b - Kontrol Paneli satırı ve uvicorn günlüğü.** Kontrol Paneli'nde yeni
bir **Analiz** satırı var. Kırmızı olduğu durumlar: sistem hazır değil (model
yüklenemedi, analiz takıldı ya da durdu, olaylar kaydedilemiyor) ya da sesli
uyarı hiçbir kanala ulaşmıyor. Gri olduğu durumlar: model yükleniyor ya da
sesli uyarının ulaştığı doğrulanamıyor. Kalibrasyon bekleyen kural sarı
görünüyor. "Sistem durumu" satırı yine "ÇALIŞIYOR"; portun bu sisteme ait
olduğu yine `durum: "calisiyor"` ile anlaşılıyor (`bizim_sunucumuz_mu`
bozulmadı; JSON'u sözlük olmayan bir cevap artık istisna fırlatmıyor). Sağlık
gövdesi aynı istekte alınıyor, ikinci istek yok. uvicorn'un günlükleri
(`uvicorn`, `uvicorn.error`, `uvicorn.access`) artık aynı JSON biçiminde ve
`sistem.log`'da; paketli programda panel penceresine de düşüyor. Erişim
günlüğüne yalnız değiştiren istekler ve 4xx/5xx yanıtlar yazılıyor. Başarılı
GET'ler yazılmıyor: paneldeki 1,5 sn'lik yoklama dönen günlüğü iki günde
doldururdu.

**2d-4 - komuta ekranlarında canlı uyarı ve sistem şeridi.** Eskiden ihlal
bandı yalnız Olaylar ve Ana Sayfa'da çıkıyordu. Operatörün başında durduğu
komuta ekranları uyarı betiklerini hiç yüklemiyordu. Artık bütün komuta
ekranlarında **ihlal bandı** ve ekran sesi var. Başlıkta bir **"uyarı akışı
açık"** hapı duruyor; akış koparsa kırmızıya dönüyor.

Üstte bir **sistem şeridi** var ve 5 sn'de bir `/saglik?ayrinti=1`'e bakıyor.
Kırmızı olduğu durumlar:
- uyarı üretilmiyor ya da kaydedilmiyor (analiz takıldı, durdu ya da
  çalışmıyor; "Analiz yapılmıyor - model yüklenemedi"; olay yazılamadı);
- kritik bir kural kalibrasyon bekliyor;
- bir kameradan görüntü gelmiyor.

Gri olduğu durumlar: sunucuya ulaşılamıyor ya da model yükleniyor. Her şey
yolundayken şerit gizli; ekranın varlığı "sorun yok" demek olmadığı için yeşile
dönmüyor. Sorun metinleri sunucudan geliyor (`web/ortak.py
SAGLIK_SORUN_METINLERI`). Yapılandırma notu (kalibrasyon) analizin hiç
çalışmadığını gizlemiyor. `/saglik` hazırlığı bozan sorunları başa alıyor.

Sistem olayları (kamera koptu, analiz takıldı…) ayrı, sessiz bir bantta 8 sn
görünüyor ve kritik ihlal bandını ezmiyor. R41: ekran sesinin boş `catch`'leri
kalktı. Sağ altta bir ses çipi çıkıyor:
- "Bu ekranda sesli uyarı KAPALI - açmak için tıklayın";
- "beklemede - etkinleştirmek için tıklayın" (tarayıcı sesi ilk tıklamaya kadar
  bekletir);
- "çalışmıyor".

Her şey yolundayken çip görünmüyor. Gizli sekmede ses ayarı artık oturum
boyunca bellekte tutuluyor; eskiden sesi açmak hiç mümkün değildi. Statik
damga `?v=31`.

**Uçtan uca kabul (docs/17 §13, 2d).** Gerçek uygulama analiz açık ve model
dosyası yokken çalıştırıldı:
- `/saglik` `model: hata`, `hazir: false`, `model_yuklenemedi` verdi;
  `?hazirlik=1` 503 döndü; gövdenin `durum`'u yine `calisiyor`'du, yani Kontrol
  Paneli satırı "ÇALIŞIYOR" kalıyor.
- Olaylar'a "Tespit modeli yüklenemedi" düştü.
- Komuta, Duvar ve Sağlık ekranlarında kırmızı "Analiz yapılmıyor - model
  yüklenemedi" şeridi çıktı.
- `?ayrinti=1` her kamera için okunan ve işlenen hızı, p50/p90 alanlarını verdi.
- uvicorn satırları `sistem.log`'da JSON olarak duruyordu.

Tarayıcı JS hatası yok.

## Faz 2c şema 007 ve olay modeli (23.09.2026)

Plan: `docs/17-V2-TASARIM.md` §6, §8.2, §8.4 ve §13 (2c satırı). Alt adımlar
ayrı commit'lerdir; her birinden sonra tam paket ve `tests/rules` yeşil.

**2c-1 - şema 007 ve göç yedeği.** `zones.zone_type` üzerindeki CHECK kalktı
(tipin tek kaynağı `rules/tipler.py BOLGE_TIPI_KODLARI`; süpervizör bilinmeyen
tipi atlıyor). Yeni bölge tipleri: **Yaya-araç geçidi** (`crossing`) ve **KKD
muaf alan** (`ppe_exempt`) - kendi renk, simge ve çipleriyle; kuralları 2c-4'te.
`events`'e olay kodu, önem ve bitiş sütunları; eski olayların bitişi
başlangıcına eşitlendi (hiçbiri "sürüyor" görünmez). `analysis_hours`,
kapalı doğan KKD veri toplama kapısı ve üç taslak anons mesajı (yaya yolunda
araç, araç yolunda yaya, yasak alana giriş). Kurulu bir veritabanında bu göçten
önce otomatik yedek alınıyor (`veri/yedekler/goc-oncesi-007_…db`); yedek
alınamazsa göç yapılmıyor. Anons mesajı değişince yeni metin yeniden
başlatmadan çalıyor (R19).

**2c-2 - olay kodları ve önem.** Sözlük `rules/olay_kodu.py`'de: 26 kod, her
birinin Türkçe adı ve varsayılan önemi (Kritik / Yüksek / Orta / Düşük /
Sistem). Kural motoru her ihlale kodunu ve önemini değerlendirmeden sonra
atıyor; değerlendiricilere ve 85 eski kural testine dokunulmadı (33 yeni kural
testi eklendi). Kuralın `severity`'si `warning` ise kodun önemi geçerli; araç
yolundaki yaya, aynı bölgede bir aracın ayak noktası varken Yüksek oluyor.
Sistem olaylarının hepsi kodlu. **"Kamera çevrimdışı" artık süren bir olay:**
kamera dönünce görüntünün geri geldiği anla kapanıyor; kamera kapatılır,
silinir ya da adresi değişirse de kapanıyor. Süreç açılırken önceki
çalışmadan açık kalan olaylar kapatılıyor ve **"Sistem başladı"** yazılıyor
(önceki çalışma "Sistem durdu" yazamadan bittiyse bu olayda söyleniyor);
düzgün kapanışta açık olaylar kapatılıp **"Sistem durdu"** yazılıyor. Model
yüklenemeyince beklenmeyen hata yolu da olay yazıyor (eskiden yalnız tipli
hata yolu yazıyordu). Sistem olayı yazılamazsa (kilitli veritabanı) analiz
durmuyor, model atılmıyor; hata günlüğe düşüyor.

**Kapanış gerçekten çalışıyor.** Ölçerken bulundu: tarayıcıda Olaylar ya da
bir komuta ekranı açıkken (canlı akış, SSE) uvicorn kapanışta bu bağlantıyı
sonsuza kadar bekliyordu - 30 sn sonra hâlâ kapanmamıştı. Kontrol Paneli
8 sn sonra süreci zorla kapattığı için kapanış kodu fabrikada neredeyse hiç
çalışmıyordu: kameralar düzgün durmuyor, "Sistem durdu" yazılamıyordu. Bütün
başlatma yollarına (panelin iki kipi, Dockerfile, systemd birimi) 3 sn'lik
kapanış süresi eklendi; açık akışla kapanış 3,2 sn'de bitiyor ve olay
yazılıyor. Paketlenmiş kipte "Durdur" artık sunucu iş parçacığının bitmesini
bekliyor (port hemen kapanıyordu, pencere o arada kapatılırsa kapanış yarım
kalırdı). Testi gerçek bir sunucu ve açık bir akışla koşuyor; süre
verilmediğinde aynı testin takıldığı karşı deneyle doğrulandı.

**2c-2b - olay ekranları.** Olaylar listesinde "Tip" sütunu **önem hapı**
oldu: Kritik (dolu kırmızı), Yüksek (kırmızı), Orta (kehribar), Düşük ve
Sistem (gri); 007 öncesi olaylar "İhlal" yazar ve eski başlıklarını korur.
Kodlu olayın başlığı kodun adı ("Yasak alana giriş", "Baret ve yelek yok",
"Araç-yaya yakınlığı - 1,42 m"). Süren olayda nefes alan noktalı
"sürüyor · 4 dk", biten olayda "bitti · 12 sn". Yeni süzgeçler: önem ve
"Yalnız sürenler". Olay sayfasında bitiş, süre, "Neden bitti" ve olay kodu.
CSV'ye dört sütun **sona** eklendi (Önem, Olay kodu, Bitiş, Süre); eski
sütunların yeri değişmedi. Komuta ekranında satır rengi artık önemden:
kritik kalın şeritli kırmızı, yüksek kırmızı, orta sarı, düşük ve sistem
nötr; incelenen olay rengini korur, yanlış alarm griye döner. Canlı akış
önemi taşıyor: uyarı bandı ve canlı liste önemin rengini alıyor,
seslendirme kodun adını okuyor. Öğe kartındaki "Forklift-insan yakınlığı"
adı sözlükten gelen "Araç-yaya yakınlığı" oldu (aynı olay aynı ekranda iki
adla görünüyordu). Kılavuza "Önem: uyarı ne kadar ciddi?" bölümü eklendi.
Statik dosya damgası `?v=27`.

**2c-3 - olay yaşam döngüsü.** İhlal artık başı ve sonu olan bir olay
(`rules/olay_durumu.py`, docs/03 §5.3): açılışta satır "sürüyor" doğar, kişi
içeride kaldıkça kuralın bekleme süresi dolunca **yeni satır açılmadan** anons
tekrarlanır, koşul `bitis_s` (yeni kural parametresi, varsayılan 3 sn) boyunca
görülmeyince olay biter; bitiş koşulun son görüldüğü andır. Uzun bir ihlal
Olaylar'ı artık her iki dakikada bir yeni satırla doldurmuyor. Sınırda gidip
gelen ya da bir an görünmeyen kişi tek olay kalıyor; KKD olayı oy belirsize
dönünce "belirsiz" sebebiyle kapanıyor ve belirsizken hatırlatma üretmiyor.
Kural düzenlenince ya da silinince yalnız o kuralın açık olayı biter (motor
artık yalnız değişen kuralın değerlendiricisini yeniden kuruyor; eskiden bir
kuralı düzenlemek aynı kameradaki bütün kuralların durumunu sıfırlıyordu).
Kamera görüntüsü kesilince açık ihlaller "kamera görüntüsü kesildi" diye
kapanıyor. Canlı akış olayın bittiğini de bildiriyor: listede "sürüyor"
işareti süreye dönüyor, **kritik uyarı bandı kendiliğinden kaybolmuyor**, olay
bitince ya da tıklanınca kapanıyor. Önem (`severity`) artık kural imzasında;
önem değişikliği yeniden başlatmadan uygulanıyor. Statik damga `?v=28`.

**2c-4 - geçit, histerezis, ek hazır kurallar.** Yaya-araç geçidindeki
(crossing) ayak noktası bölge ihlali sayılmıyor (`gecit_haric`, varsayılan
açık): geçitten karşıya geçen yaya ya da forklift uyarı üretmez. Açılmış
mesafe olayı, mesafe `distance_m + histerezis_m` (varsayılan 0,5 m) aşılınca
bitiyor; eşiğin hemen üstünde gidip gelen çift tek olay. R21: bölgeye bağlı
mesafe kuralı, bölgesi kapalıyken kapalı bölgenin poligonunu kullanıyor,
bölge yüklenemezse bütün kareye yayılıyordu; artık çalışmıyor. Kamera
sayfasına iki **ek hazır kural** geldi - **yaya yolunda araç** ve **araç
yolunda yaya**; birincil kuralın yanına kurulur, **gölge modda** doğar ve
şema 007'nin mesajlarına bağlanır. Yasak bölgenin hazır kuralı artık
«Bu alana giriş yasaktır.» anonsuna bağlı (eskiden anonssuzdu; mevcut
kurallar değişmedi). Kalibrasyonsuz kamerada etkin bir güvenli mesafe ya da
hız kuralı varsa kurulum listesinde kırmızı **"Kalibrasyon bekleniyor"**
maddesi çıkıyor ve `/saglik` `"sorunlar": ["kritik_kural_pasif"]` veriyor.

**2c-4c - kural formu.** Formda **Önem** seçimi var: "Varsayılan (Yüksek)" gibi,
kuralın olay türünden hesaplanan önemi ve hangi olaylardan geldiğini söylüyor
("Baret yok: Yüksek; Yelek yok: Orta"). Varsayılanın altına inmek sarı kutuda
onay istiyor ve sunucu da denetliyor; yükseltmek serbest. Kurallar listesinde
**Önem** sütunu var. `bitis_s` (dört tip), `gecit_haric` (bölge) ve
`histerezis_m` (mesafe) formda. Kaydetmek, formda olmayan bir parametreyi artık
varsayılana döndürmüyor: aynı tipte önceki değer korunuyor. Form varsayılanları
şemadan geliyor (R25). Cooldown yeni kuralda tipin varsayılanıyla doluyor
(90 / 120 / 180 sn; eskiden hep 120). Başka tipin alanı artık düzenlenen kuralın
değerini göstermiyor; örneğin KKD alanındaki kalış süresi, düzenlenen bölge
kuralınınkini gösteriyordu. Olmayan bir kuralı "düzenleyip kaydetmek" artık
sessizce geçmiyor. Kurulum listesindeki kalibrasyon maddesi çoğulu düzgün
yazıyor ("… kameralarındaki … kuralları"). Sınıf kutularının katalogdan ve
etkin modelden gelmesi, `SINIF_KATALOGU` ile F3'e kaldı. Statik damga `?v=29`.

Tasarımda açık kalan iki nokta kodda şöyle kapandı: `ZONE_INTRUSION`'ın
varsayılan önemi **Orta** (tasarım "kural satırından" diyordu ama bütün
satırlar `warning`); kapanış sebeplerine `kamera_degisti` eklendi. Bitiş hiçbir
zaman başlangıçtan önce yazılmıyor (saat geri alınsa bile).

## Faz 2b takip ve kamera (23.09.2026)

**Takip hafızası.** ByteTrack'in kayıp iz tamponu hiç verilmiyordu (varsayılan
30); supervision onu kare hızına ölçeklediği için hafıza hangi fps olursa olsun
1 sn idi. Artık `.env TAKIP_HAFIZA_SN` (2 sn): 6 fps'te 12 kare. Kuralların ve
bölge sayacının kayıp toleransı da aynı süreden türüyor (`ceil(sn × fps)`);
yoksa takipçi izi 2 sn beklerken kural 0,83 sn'de bırakır, kalış sayacı yine
sıfırlanırdı. Verilmediğinde her iki taraf eski değerinde: `tests/rules`
85 test değişmeden yeşil.

**Kamera bağlantısı.** Tek bir 60 sn eşiği ikiye ayrıldı: ilk bağlantıya 60 sn
tolerans (iç sabit), akan görüntünün kesilmesine `KAMERA_KOPUK_ESIGI_SN` (10 sn) -
kopan bir kamera bir dakika boyunca "çevrimiçi" görünüyordu. "Tekrar çevrimiçi"
olayı görüntü `KAMERA_UP_KARARLILIK_SN` (5 sn) kesintisiz akınca yazılıyor; gidip
gelen bağlantı olay seli üretmiyor (ekrandaki durum anlık kalıyor). RTSP açılış
ve okumasına OpenCV zaman aşımı geçiyor (5/10 sn); yanıt vermeyen bir sunucuya
karşı ölçüldü: açılış tam 2,0 ve 4,0 sn'de bırakıldı. Yeni ayarlar Ayarlar →
Takip ve kamera bağlantısı'nda.

**Zaman ve ölçüm.** Kurala işlendiği an değil karenin zamanı gidiyor (R29).
Kamera başına işlenen fps ile işleme ve olay yazma süreleri (p90) tutuluyor;
/saglik ayrıntısında 2d'de gösterilecek. Yeni kameranın varsayılan örnekleme
hızı `.env KARE_ORNEKLEME_FPS`'ten geliyor (formda sabit 6 yazıyordu).

## Faz 2a güvenlik tabanı ve öğe dili (23.09.2026)

Plan: `docs/17-V2-TASARIM.md` §10.5 ve §13. Her madde Faz 0 denetiminde
(`docs/AUDIT.md`) koddan doğrulanmış bir açıktır; testleri `tests/test_guvenlik.py`.

**Giriş (R7, R9, R15).** Yanlış şifre kilidi `X-Forwarded-For` uydurularak
atlatılabiliyordu: her deneme "yeni adres" sayılıyordu. Artık adresi yalnız
uvicorn yazar, o da güvendiği vekilden (`FORWARDED_ALLOW_IPS`). Ayarlar
sayfası kurulu şifreyi `type=text` kutuda değeriyle basıyordu; kutu artık
noktalı ve boş, boş bırakmak şifreyi korur. Türkçe harfli şifre
`hmac.compare_digest`'te TypeError → 500 veriyordu; karşılaştırma bayt üzerinden.

**Host izin listesi + köken denetimi (R8).** `web/kaynak_denetimi.py`, tek ara
katman. İzinsiz `Host` → 421 (DNS yeniden bağlama: saldırganın adı bu makineye
çözülünce tarayıcı yanıtları okuyabiliyordu). Durum değiştiren istekte
`Origin`/`Referer` izinli değilse, `Origin: null` ise ya da `Sec-Fetch-Site`
`cross-site`/`same-site` ise 403 (CSRF); üç başlık da yoksa geçer (tarayıcı
dışı istemci). Plandan bir adım sıkı: `same-site` de reddediliyor - port
karşılaştırılmadığı için aynı makinenin başka portundaki bir sayfa
(127.0.0.1:8100) izinli Origin taşıyordu; tarayıcı o isteğe `same-site` der,
sistemin kendi sayfası her zaman `same-origin`. Gerçek Chromium'da denendi:

    kendi formu (olay durumu)  → 303   kendi fetch'i (KKD etiket) → 204
    127.0.0.1:8100'den form    → 403   evil.test'ten form         → 403
    evil.test:8099 GET (yeniden bağlama) → 421   saldırı kamerası oluşmadı

Yeni ayar `IZINLI_SUNUCU_ADLARI` (Ayarlar → Güvenlik). **Davranış değişikliği:**
ağa açık kurulumda başka cihazdan sunucunun IP'siyle girmek için o IP listeye
yazılmalı; yazılmamışsa sayfa ne yapılacağını söyler, açılışta da uyarı düşer.
`docs/15` ve Kılavuz buna göre güncellendi. `/docs`, `/redoc`, `/openapi.json`
kapatıldı (bütün rotaları girişsiz listeliyordu).

**Anons, ayar dosyası, model (R14, R17, R26, winsound).** Windows'ta ses artık
stdlib `winsound` ile çalınıyor; yol PowerShell komut metnine gömülmüyor ve
`SND_NODEFAULT` sayesinde bozuk dosya "bip" çalıp başarılı dönmüyor. `.env`'e
yazılan değerde satır sonu ve kontrol karakteri reddediliyor - önce
çalıştırılarak doğrulandı: `hdmi\nYONETICI_SIFRESI=` ses çıkışı adı şifreyi
siliyordu. Model indirmesi SHA-256 ile doğrulanıyor (özetler resmi yayından iki
ayrı indirmeyle ölçüldü; `models/SHA256SUMS`, `indir.sh`, Dockerfile ve kod aynı
değerleri taşıyor, test eşitliği denetliyor). docs/06'daki systemd birimi var
olmayan `app.main:uygulama`'yı gösteriyordu; `app.main:app` - iki komut da
çalıştırılarak denendi.

**Python, Docker, ONNX Runtime (R10, R13, R27, S19).** Kontrol Paneli yalnız
Python 3.12 kabul ediyor; 3.14 kullanıcısına "çok eski" değil "henüz
desteklenmiyor, 3.12 yan yana kurulabilir" deniyor, betikler önce 3.12'yi
arıyor, 3.11 ile kurulmuş eski `.venv` İlk Kurulum'da `--clear` ile yeniden
kuruluyor. Docker'da şifre zorunlu (kapsayıcı 0.0.0.0'ı dinler, SUNUCU_ADRESI
kilidi orada işlemiyordu). **Davranış değişikliği:** Docker'da ayarlar artık
`ayar/.env` (dizin bağlama); tek dosya `:ro` bağlamada Ayarlar sayfası hiç
kaydedemiyordu. Eski kurulumda bir kez `mkdir -p ayar && mv .env ayar/.env`.
ONNX Runtime 1.19.2 → 1.30.0 (CVE-2026-14647'nin gömülü `onnx`'i; Intel Mac'te
ortam işaretçisiyle 1.23.2). Dört hedefte cp312 tekerleği indirilerek
doğrulandı; gerçek bir fotoğrafta (bus.jpg) iki model de otobüsü ve kişileri
buldu. Model açılmazsa artık GPU sağlayıcısı hatası (CPU'da çalışmaya devam),
sağlam dosya + kurulum sorunu (özet tutuyor) ve bozuk dosya ayrı söyleniyor;
iki ORT paketi birlikte kuruluysa uyarılıyor. İmaj burada derlenmedi (Docker yok).

**Öğe dili.** İnsan, forklift, tır, yaya yolu, baret, yelek, hoparlör, Bluetooth
için simgeler (Lucide ISC + elle çizilmiş yelek) ve tek tablo (`web/ortak.py`
`OGELER`): olay listesi, canlı akış, komuta ekranı ("Öğelere göre ihlaller"),
inceleme kuyruğu, KKD ilerleme kartları (docs/04 §4.5 asgari sayıları), anons
ve kamera sayfaları, Kılavuz'da simge sözlüğü. Olay listesi telefonda karta
dönüşüyor (altı sütunlu tablo 375 px'te özeti yatay kaydırmanın arkasına
saklıyordu).

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
Atomiklik bozulmuyor. Test bu veri kaybını kalıcı olarak bekliyor - mekanizma
kapatılınca kırmızı oluyor, denendi.

Karar mantığı (`rules/hiz.py`) tek kareye bakmıyor: aynı takibin son N
ölçümünün **ortancasını** alıyor. Kare başına hız ölçümü gürültülüdür; beş
ölçümün dördü 0,5 m/sn biri 20 m/sn ise ortalama 4,4 m/sn çıkar ve duran
forklift ceza yerdi, ortanca 0,5 m/sn kalıyor. Ekrana yazılan sayı da bu
ortanca. Ayar m/sn tutuluyor (`hiz_mps` ile aynı birim), formda km/sa
karşılığı anında yazılıyor - fabrika hız levhaları km/sa'dır.

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
sahte bir PyInstaller ile koşturuluyordu, **Mac tarifi koşturulamıyordu** -
OpenSSL düzeltmesi `otool` çağırıyor ve o araç yalnız macOS'ta var. Düzeltme
artık macOS dışında kendini atlıyor, tarif her yerde çalıştırılabiliyor;
tarifteki bir yazım hatası artık kullanıcının Mac'inde değil burada görünüyor.

İki gerçek hata daha çıktı: `otool` yoksa üretim ham İngilizce traceback ile
ölüyordu (artık Türkçe duruyor ve `xcode-select --install` diyor), ve `_ssl`
bağımlılığı çözülemezse kod uyarı yazıp **devam ediyordu** - üretilen uygulama
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
sayfa giriş ister. Şifresizken kurulum listesi ve Ayarlar sayfası uyarır -
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
Emniyet kilidi: ağa açık + şifresiz kurulum **açılışta reddedilir** - o haliyle
ağdaki herkes kamera silebilirdi, uyarıyla geçiştirilecek bir durum değil.

Şifre eklemek tek başına yetmiyordu: sınırsız deneme şifreyi fiilen yok sayar.
Aynı adresten 5 yanlış denemeden sonra adres 5 dakika kilitleniyor ve
kilitliyken **doğru şifre de** kabul edilmiyor. Ters vekil arkasında çalışırsa
oturum çerezi `secure` işaretleniyor ve gerçek istemci adresi
`X-Forwarded-For`un ilk değerinden okunuyor.

Yeni belge `15-UZAKTAN-ERISIM.md`: üç seviye (yalnız sunucu / fabrika ağı /
fabrika dışı), fabrika dışı için sıralı öneri (VPN veya Tailscale → tünel →
port açma, sonuncusu **önerilmez**) ve KVKK uyarısı - fabrika içindeki
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

**Taralı alan.** Bölgeler artık çapraz taramayla dolu çiziliyor - hem tarayıcı
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
Üst üste binen bölgelerde küçük olan seçiliyor - büyük bir bölgenin içindeki
küçüğe başka türlü tıklanamazdı.

**Çizim arka planı ayrıldı.** Ekran görüntüsü yükleme, "otomatik alan bul"
akışına bağlıydı; artık kendi başına bir seçim. Üç düğme: **Kareyi dondur**
(canlı akış saniyede yenilenirken köşe tıklamak zordu), **Ekran görüntüsü yükle**
(kamera takılmadan önce hazırlık), **Canlıya dön**. Yüklenen görüntü yine diske
yazılmıyor.

**Giderilen hata.** Tarayıcı, HTML olmayan yanıtlarda (ör. `/saglik` JSON'u)
`<link rel="icon">` etiketini göremediği için kök dizinden `/favicon.ico`
istiyor ve her seferinde konsola 404 düşüyordu - sistemde arıza varmış izlenimi
veren, aslında olmayan bir hata. Rota eklendi.

**Gerçek tarayıcıda doğrulandı** (Chromium): 19 sayfanın hepsi 200; bölge
seçme, kare dondurma, ekran görüntüsü yükleme, öneri yükleme, dikdörtgen çizme
ve köşe sürükleme tek tek denendi. **JavaScript hatası 0, konsol hatası 0,
4xx yanıt 0.**

804 test yeşil (öncesi 795), ruff temiz.


## Alan tanıma, bölge sayımı ve anons bağlama (09.09.2026)

Üç konu birden ele alındı: fabrika alanının tanınması, videoda sayım ve anons
sistemine bağlanma.

**Fabrika alanını tanıma (`analiz/alan_bulucu.py` - yeni).** Fabrika zemininde
alan zaten boyalıdır; sistem artık o boyayı bulup hazır bir bölge çizimi
**önerir**. İki geçiş vardır: kapama geçişi dolu alanları (beyaz çerçeveli
yükleme sahası) bulur, kümeleme geçişi ise iki paralel çizgiyle işaretli yaya
yolunu bulur - aradaki yol da alana dahil edilir; ilk geçiş iki çizgiyi ayrı
ayrı "çok ince" diye eliyordu. Öneri karar DEĞİLDİR: veritabanına hiçbir şey
yazılmaz, kullanıcı kartına tıklayıp köşeleri düzelterek kendisi kaydeder.
Ölçüldü: iki paralel kesikli sarı çizgi 4 köşeyle ~24 ms'de bulunuyor, boyasız
betonda hiçbir öneri üretilmiyor (yanlış öneri yok).

**Ekran görüntüsünden alan tanıma.** Kamera henüz takılmamışken de bölge
hazırlanabilsin diye NVR'dan alınmış bir kare yüklenebiliyor; görüntü hem
taranıyor hem çizim tuvalinin arka planı oluyor. **Yüklenen görüntü diske
yazılmaz** (KVKK + en az parça) - kalıcı olan tek şey kaydedilen bölge.
Alan bulunamadığında sistemin "boya" saydığı yerleri işaretleyen bir **teşhis
görüntüsü** dönüyor; boş bir maske, eşik oynamaktan daha açık bir yanıttır.

**Çizim kolaylıkları.** Dikdörtgen kipi (bir köşeden karşı köşeye sürükle) ve
**köşe sürükleme** eklendi - eskiden tek yanlış köşe için tüm çizim baştan
yapılıyordu.

**Bölge sayımı (`rules/sayim.py` - yeni, SAF).** Bölge çizilen her kamerada
kural gerektirmeden çalışır. Üç sayı üç ayrı soruyu cevaplar: içeride kaç var,
sayaç sıfırlandığından beri kaç ayrı nesne girdi, aynı anda en çok kaç görüldü.
Sayım **takip bazlıdır**: bölgede on dakika duran kişi bir kez sayılır (kare
bazlı sayım 6 kare/sn ile on dakikada 3600 "kişi" üretirdi). Sayılar canlı
görüntünün üstünde, bölgenin köşesinde de yazıyor. Sayım kural DEĞİLDİR: ihlal
üretmez, anons tetiklemez - yanlış sayım kimseyi yanlış uyarmaz.

**Anons sistemine bağlanma (R3 kapandı).** Eskiden tek bir JSON gövdesi
gönderiliyordu ve sahadaki IP hoparlörlerin çoğu bunu anlamazdı. Artık üç biçim
var (`json` / `form` / `get`) ve adreste `{anahtar}` / `{metin}` yer tutucuları
dolduruluyor. `str.format` bilerek kullanılmadı: anons sisteminin kendi süslü
parantezleri (`?q={id}`) `KeyError` fırlatıp anonsu tamamen susturur ve bu
sahada teşhisi en zor arızadır. **Bulunan hata:** "Bu hoparlörü dene" düğmesi
biçimi geçirmiyordu - GET bekleyen bir cihazda deneme "başarılı" derken gerçek
anons sessizce başarısız olacaktı.

**Yeni belge: `docs/14-ANONS-SISTEMI-BAGLAMA.md`** - hangi altyapıda hangi yol,
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


## Mac / Windows uyumu - baştan aşağı denetim (02.09.2026)

Bağımsız bir denetimle bulunan ve giderilenler (en kritikten):

- **Windows'ta çift tıklama Microsoft Mağazası'nı açıyordu.** `where python`
  Windows 10/11'de Python KURULU OLMASA BİLE başarılıdır: PATH'te sıfır baytlık
  bir "python.exe" takma adı vardır. Yardım mesajı hiç görünmüyordu. Artık
  `py -3` denenip adayın gerçekten Python olduğu doğrulanıyor.
- **Hata anında pencere kapanıyordu** - kullanıcının kopyalayacak satırı
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
  komut bozuluyordu - hem hata hem enjeksiyon yüzeyi.
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
  veriyor - çok karanlık / aşırı parlak / bulanık / düşük kontrast, her biri için
  ne yapılacağıyla birlikte. `.env` → `GORUNTU_IYILESTIRME=otomatik` yerel
  kontrast dengeleme (CLAHE) uyguluyor; yalnız parlaklık kanalında çalıştığı için
  reflektörlü yeleğin sarısını bozmuyor. Tespit ve önizleme aynı kareyi
  kullanıyor: ekranda modelin gördüğü görüntü var.
- **Windows konsol kodlaması:** Türkçe karakter içeren bir log satırı Windows'un
  cp1254 konsolunda `UnicodeEncodeError` verip log sistemini çökertebiliyordu;
  akışlar UTF-8'e alındı, ayar hatası mesajı da güvenli yazılıyor.
- **Yeni doküman:** `docs/12-KAMERA-VE-GORUNTU-KALITESI.md` - kamera yerleşimi,
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
  tarafından yutulmuyor - tam da uyarı üretmesi gereken durum.
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
Anons artık analiz iş parçacığını **bloklamıyor** - anons sunucusu kapalıyken tüm
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
  hızı değişince takip hafızası yanlış kalıyordu - ikisi de düzeltildi.
- Konfigürasyon damgası uygulamadan önce yazılıyordu: yarıda kalan yenileme
  değişikliği kalıcı olarak yutuyordu.
- Çevrimdışı kamerada "son kare" zamanı siliniyordu - en çok gereken bilgi.
- Saklama süresi fotoğrafı siliyor ama kaydı temizlemiyordu (kırık resim).
- KKD kuralı yanlış tipte bir bölgeye bağlanabiliyor ve sessizce hiç çalışmıyordu.
- Anons adresi şemasız yazılırsa her ihlalde hata veriyordu - açılışta engellendi.
- Canlı uyarı listesi kamera adını HTML olarak yorumluyordu.
- Olay filtresinde sayısal olmayan değer 500 veriyordu.
- Docker sağlık kontrolü ana sayfayı çağırıyor, 30 saniyede bir tüm `veri/`
  klasörünü tarıyordu → hafif `/saglik` ucu eklendi.
- `docs/06-OPERASYON.md` terk edilmiş PostgreSQL + Alembic + 3 servis mimarisini
  anlatıyordu; içindeki her komut hatalıydı - baştan yazıldı.

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
  "Kameraya ağ üzerinden ulaşılamıyor (IP:port)", "ulaşıldı ama akış açılamadı -
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

- **Windows uyumu düzeltildi:** anons sesi (PowerShell SoundPlayer - `afplay`/`aplay` Windows'ta yok), kamera arka ucu (DirectShow), saat dilimi veritabanı (`tzdata` bağımlılığı).
- **Docker desteği:** üç proje için de Dockerfile + docker-compose. Veri ve ayarlar container dışında (silinse de kaybolmaz), sağlık kontrolü ve otomatik yeniden başlatma var; GPU ve ses kartı blokları Linux için hazır ve yorumlu.
- Model dosyası yoksa imaj derlemesi **anlaşılır bir mesajla durur** - modelsiz, hiçbir şey tespit etmeyen sessiz container tuzağı kapatıldı.
- **NASIL-CALISIR.md** yazıldı: sistemin işleyişi, Mac/Windows/Docker kurulumu, hangi ortamda neyin çalıştığını gösteren dürüst tablo, sorun giderme ve yedekleme.
- Docker bu makinede kurulu olmadığı için imaj derlemesi **denenemedi**; Dockerfile'lar statik olarak doğrulandı.

## Adım 2-7 + altyapılar - Sistem uçtan uca çalışır durumda (26.08.2026)

- **Kamera katmanı:** RTSP (TCP) / video dosyası kaynağı, "son kare" deseni, üstel beklemeli otomatik yeniden bağlanma, çevrimiçi/çevrimdışı takibi ve sistem olayları. Kamera CRUD + 1 sn'de yenilenen canlı önizleme (tespit kutuları çizili).
- **Tespit + takip:** YOLOX (Apache-2.0, ADR-002) ONNX Runtime ile - torch gerekmez; `models/indir.sh` modelleri indirir. ByteTrack (supervision) ile kalıcı takip ID. Forklift, saha verisiyle ince ayara kadar araç sınıfı üzerinden görünür (R1).
- **Kural motoru (`rules/`, saf):** üç kural tipi eksiksiz - bölge ihlali (inside/outside + kalış), güvenli mesafe (homografi + hareket koşulu + ardışık kare; kalibrasyonsuz kamerada bilerek pasif), KKD (üç durum + zamansal oylama; **belirsiz asla olay üretmez**). Cooldown ortak filtre; restart'sız konfig yayılımı durumu korur.
- **Olaylar:** kanıt fotoğrafı önce/DB sonra, rule_snapshot, SSE canlı uyarı paneli, filtreli liste, olay durumu (Yeni/İncelendi/Yanlış alarm + not), CSV dışa aktarma, korumalı fotoğraf servisi.
- **Kalibrasyon:** görüntüde 4 nokta tıkla + metre gir → homografi (saf numpy); arayüzde "kalibrasyon bekleniyor" rozetleri.
- **Anons:** Null / ses kartı (afplay-aplay) / HTTP adaptörleri + ekrandan bağımsız, daha uzun anons cooldown'u. Somut sistem bilgisi bekleniyor (R3).
- **KKD altyapısı:** KKD bölgelerinden saatlik limitle otomatik crop toplama + uygulama içi etiketleme sayfası (Var/Yok/Belirsiz). Model 9. adımda eğitilecek; o zamana dek KKD kuralı olay üretmez (belirsiz), veri biriktirir.
- **Güvenlik/işletim:** tek şifreli oturum (imzalı çerez), RTSP maskeleme, günlük retention + disk uyarısı, tek tıkla veritabanı yedeği.
- 92 test yeşil (kural motoru + web + entegrasyon), ruff temiz; gerçek görüntüyle uçtan uca doğrulandı (tespit → olay + kanıt fotoğrafı).
- Ayrıca: Kontrol Paneli'nin Mac'te açılmama sorunu çözüldü (çalıştırma izni + karantina + Python 3.12/tkinter).


## Adım 1 - Proje iskeleti + veritabanı + ana sayfa (26.08.2026)

- backend/ iskeleti kuruldu: .env'den okunan tek ayar kaynağı (ayarlar.py), SQLite bağlantısı (yabancı anahtar + WAL + busy_timeout) ve sürümlü şema düzeni (sema/001_ilk.sql → 7 tablo + 5 anons mesajı seed).
- Zaman yönetimi tek yerde (zaman.py: UTC sakla, İstanbul göster), JSON satır log (loglama.py → ekran + veri/loglar/sistem.log), tiplenmiş hatalar ve merkezi hata yakalayıcı (hatalar.py) eklendi.
- Teşhis ana sayfası hazır: şema sürümü, tablo listesi, maskeli aktif ayarlar, disk durumu ve "Henüz kamera eklenmedi".
- rules/ klasörü boş açıldı; saflık kuralı tests/rules/test_saflik.py ile korunuyor (doğrudan, dinamik ve dolaylı yasaklı import'lar testi kırmızı yapar).
- 30 test yeşil, ruff temiz; sıradaki iş: Adım 2 - kamera ekleme + görüntü alma.
