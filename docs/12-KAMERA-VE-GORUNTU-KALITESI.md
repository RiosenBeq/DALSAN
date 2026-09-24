# 12 - Kamera Yerleşimi ve Görüntü Kalitesi

> **Bu dokümanın tek iddiası:** Sistemin isabetini en çok belirleyen şey model
> değil, **kameranın gördüğü görüntüdür.** Eşik ayarlamak, kirli bir lensi
> silmenin yerini tutmaz.

---

## 1. Sistem neyi tanır

| Nesne | Nasıl tanınır | Ekrandaki rengi |
|---|---|---|
| **İnsan** | Hazır model (COCO `person`) | Yeşil |
| **Tır / araç** | Hazır model (`truck`, `bus`, `car`) | Mavi |
| **Forklift** | Hazır modellerde forklift sınıfı yoktur; forklift **araç (tır)** olarak görünür (docs/08 R1). Forklift tanıyan model seçildiğinde ayrı sınıf olur (§5) | Turuncu (forklift tanıyan modelle) |
| **Baret** | KKD sınıflandırıcısı - **henüz eğitilmedi**, veri toplanıyor (docs/04) | Kişi kutusunda **B** rozeti |
| **Reflektörlü yelek** | Aynı sınıflandırıcı | Kişi kutusunda **Y** rozeti, **sarı** |
| **Kural ihlali** | Kural motoru | Kutu **kırmızıya** döner ve kalınlaşır |
| **Çizdiğiniz bölge** | - | Mor çerçeve |

Rozetlerin üç durumu vardır: **dolu = var**, **kırmızı çarpı = yok**,
**gri soru işareti = belirsiz**. **Belirsiz asla ihlal sayılmaz** (docs/04 §1).
KKD modeli yüklü değilken kişi kutusunda B/Y rozeti hiç çizilmez ve kural motoru
herkesi belirsiz sayar - bu normaldir, arıza değil.

Aynı tablo arayüzde de vardır: kamera sayfasındaki **Renk anahtarı**.

---

## 2. Kamera yerleşimi - en çok fark yaratan beş şey

1. **Yükseklik ve açı.** 3-4 metre yükseklik, yere doğru ~30° eğim. Çok tepeden
   bakan kamera insanları "yukarıdan daire" gibi gösterir; model bunu zor tanır.
2. **Kişi görüntüde kaç piksel?** İnsan boyu ekranda **en az 80-100 piksel**
   olmalı. Baret kararı için **120 piksel** gerekir (baret, boyun yaklaşık 1/8'i).
   Kamera çok uzaksa hiçbir eşik ayarı bunu kurtarmaz.
3. **Karşıdan ışık yok.** Kamera güneşe, pencereye veya projektöre bakmamalı;
   siluete düşen insan tanınmaz.
4. **Görüş yolu açık olsun.** Direk, raf, asılı branda kişinin alt yarısını
   kapatıyorsa sistem zemin temasını göremez ve bölge kararı yanlış olur.
5. **Ana akış (main stream) kullanın.** NVR'ın "substream" akışı genelde
   352x288'dir; bu çözünürlükte uzaktaki kişi birkaç piksele düşer.

---

## 3. Görüntü kalitesi bozuksa ne olur, ne yapılır

Sistem kendisi ölçer: kamera sayfasında görüntü kalitesi sorunluysa **sarı bir
uyarı satırı** çıkar ve ne yapılacağını yazar. Ölçülen dört durum:

| Uyarı | Anlamı | Yapılacak |
|---|---|---|
| **Görüntü çok karanlık** | Ortalama parlaklık çok düşük | Alana ışık ekleyin; kameranın gece modunu (IR) açın; `.env` → `GORUNTU_IYILESTIRME=otomatik` |
| **Görüntü aşırı parlak** | Kameraya doğrudan ışık geliyor | Kamerayı yeniden konumlandırın (kalıcı çözüm budur) |
| **Görüntü bulanık** | Netlik düşük | Kamera camını silin; odağı kontrol edin; substream yerine ana akışı deneyin |
| **Görüntünün kontrastı düşük** | Sisli/dumanlı görünüm | `.env` → `GORUNTU_IYILESTIRME=otomatik` |

### `GORUNTU_IYILESTIRME=otomatik` ne yapar

Her karede **yerel kontrast dengeleme** (CLAHE) uygular: karanlık köşedeki insanı
görünür kılar, aşırı parlak bölgeyi bastırır. Yalnızca parlaklık kanalında
çalışır, **renkleri bozmaz** - reflektörlü yeleğin sarısı sarı kalır.

Bedeli: kare başına birkaç milisaniye işlemci. Görüntü zaten iyiyse belirgin
fayda sağlamaz; **önce uyarı satırına bakın**, gerek yoksa kapalı bırakın.

Tespit ve önizleme **aynı** kareyi kullanır: ekranda modelin gördüğü görüntüyü
görürsünüz. Sistem size, kendi kararını verdiğinden farklı bir görüntü göstermez.

---

## 4. Hassasiyet ayarı - sırasıyla deneyin

Eşikler `.env` dosyasındadır ve değiştirdikten sonra sistem yeniden başlatılır.

```
TESPIT_GUVEN_ESIGI=0.35          # genel eşik (araç vb.)
TESPIT_INSAN_GUVEN_ESIGI=0.28    # insan için ayrı ve daha düşük
TESPIT_NMS_ESIGI=0.45            # üst üste binen kutuların birleştirilmesi
TESPIT_EN_KUCUK_KENAR_PX=12      # bundan küçük kutular atılır
```

**Nesne kaçıyorsa** (kutu çıkmıyor):
1. Önce kamera sayfasındaki kalite uyarısına bakın - sorun genelde oradadır.
2. `TESPIT_INSAN_GUVEN_ESIGI` değerini **0,05'lik adımlarla** düşürün (0,28 → 0,23 → 0,18).
3. Uzaktaki küçük nesne için `TESPIT_EN_KUCUK_KENAR_PX` değerini düşürün (12 → 8).
4. Hâlâ olmuyorsa daha isabetli modele geçin: Ayarlar → "Tanıma modeli" →
   **NextGen AI İsabetli**, sonra sistemi yeniden başlatın (masaüstünde Kontrol
   Paneli'nde Durdur → Sistemi Başlat; sunucuda docs/06 §7)
   (daha yavaş ama küçük nesnelerde belirgin daha iyi; ilk açılışta kendisi iner).

**Yanlış tespit çoksa** (olmayan nesneye kutu):
1. Aynı eşikleri **yükseltin** (insan eşiği genel eşiği geçemez: daha yüksek
   yazılırsa insanda da genel eşik uygulanır).
2. `TESPIT_EN_KUCUK_KENAR_PX` değerini yükseltin (12 → 20): uzak gürültü elenir.
3. Kalabalık sahnede kutular birbirine giriyorsa `TESPIT_NMS_ESIGI` değerini
   0,5-0,6 arasında deneyin.

> **İlke (docs/00):** Kaçırılan ihlal bilinen sınırdır; **yanlış alarm ciddi
> kusurdur.** Kullanıcı yanlış alarma alışırsa gerçek uyarıya da bakmaz.
> Bu yüzden varsayılanlar temkinlidir ve gevşetme kararı sizindir.

---

## 5. Forklift hakkında dürüst not

Hazır modellerde (**NextGen AI Hızlı** ve **İsabetli**, COCO sınıfları)
**forklift sınıfı yoktur.** Forklift bu modellerle çoğu zaman `truck` (tır/araç)
olarak görünür ve güvenli mesafe kuralı onu araç sayar - yani kural **çalışır**,
ama ekranda "forklift" yerine "tır" yazar.

Forklift tanıyan model ayrı bir eğitim hattında hazırlanır: açık LOCO veri
setiyle (CC0) GitHub Actions'ta eğitilir ve hazır modelin insan ve araç
tespitine dokunmadan üstüne forklift sınıfı ekler (`egitim/forklift/`, docs/17
§12.3). Aday ancak `egitim/forklift/esikler.json`'daki geçitleri geçerse
kaydedilir: insan ve araç tespitinde kayıp yok denecek kadar az, forklift
yakalama oranı en az %60, yanlış alarm ve gecikme sınırları içinde. Kaydedilen
model Ayarlar → "Tanıma modeli"nde seçilebilir olur; varsayılan model saha
ölçümü ve operatör onayı olmadan değişmez. Bir modelin hangi sınıfları
tanıdığı model dosyasının içinden okunur (`dalsan_classes`,
`backend/app/analiz/tespit.py`): yeni model için kod değişmez.

**Bugün kayıtlı forklift modeli yok.** İki tam eğitimin adayları geçitleri geçemedi.
İkincisinde (24.09.2026) forklift kutuları doğru bulundu ama başka depolardaki
forkliftlerin ancak dörtte biri tanındı (geçit en az %60). Sıradaki adım bu
fabrikanın kendi kameralarıdır ve yolu hazır (24.09.2026): **Forklift** sayfası
kareleri toplar ve etiketletir, eğitim kapalı bir bilgisayarda tek komutla yapılır,
çıkan model aynı geçitlerle yeniden denetlenip aynı sayfadan kurulur ve Ayarlar'da
seçilebilir olur (docs/06 §9, docs/17 §12.6). Sahada henüz kare toplanmadı.

Seçilen forklift modeli inmezse ya da açılamazsa sistem durmaz: tabanındaki
hazır modelle insan ve araç tespitine devam eder, ana sayfada sebebini yazar ve
Olaylar'a "Seçili model yerine hazır model çalışıyor" düşer (docs/06 §7).

---

## 6. Kamera ekleme sırasında sık karşılaşılanlar

| Belirti | Sebep / çözüm |
|---|---|
| "Kameraya ağ üzerinden ulaşılamıyor" | IP veya port yanlış; kamera kapalı; ağ kablosu takılı değil |
| "Kameraya ulaşıldı ama görüntü akışı açılamadı" | Kullanıcı adı/şifre veya akış yolu yanlış. Şifrede `@ : / #` varsa `%40 %3A %2F %23` yazın |
| "Kameraya bağlanıldı ama görüntü gelmedi" | NVR'ın eşzamanlı bağlantı sınırı dolmuş olabilir; ya da akış H.265 ve çözülemiyor - kamerada H.264 seçin |
| "Video dosyası bulunamadı" | Tam yol gerekir. Mac: dosyayı Finder'da seçip **Option+Command+C**. Windows: dosyaya **Shift + sağ tık → "Yol olarak kopyala"** |
| Kamera "bağlanıyor"da kalıyor | İlk bağlantı 30 saniye sürebilir; 60 saniye içinde görüntü gelmezse "çevrimdışı" olur ve sebebi yazar. Çalışırken kopan kamera ise ~10 saniyede "çevrimdışı" görünür (Ayarlar → Takip ve kamera bağlantısı) |

RTSP adresini kameranın/NVR'ın arayüzünden ya da kurulumu yapan firmadan
alabilirsiniz. Yaygın biçim:
`rtsp://kullanici:sifre@192.168.1.64:554/Streaming/Channels/102`

---

## 7. Yaya yolu (yürüyüş yolu) kuralı

Fabrikada çizili bir yürüyüş yolu varsa ve insanların oradan yürümesi
bekleniyorsa:

1. Kamera sayfasında **"Çizime başla"** ile yolun üzerini poligon olarak çizin,
   tipini **"Yaya yolu"** seçin ve kaydedin.
2. Bölgeler listesinin altında çıkan **"… için yaya yolu kuralı ekle"**
   düğmesine basın.

Kural şunu yapar: yaya yolunun **dışında** 5 saniyeden uzun kalan **kişi** uyarı
üretir. Yolun kenarına bir adım atan kişi uyarı üretmez; bu süre bilerek uzundur.
Uyarı, "Lütfen yaya yolunu kullanınız." anonsuna bağlanır.

**Bölgeyi çizerken:** karar kişinin **ayaklarının** bulunduğu noktaya göre
verilir. Yolu, üzerine basılan zemin alanı olarak çizin - havada duran bir
dikdörtgen değil.

Aynı kuralı elle kurmak isterseniz: Kurallar → Yeni Kural → Bölge ihlali →
Koşul: **"Bölge DIŞINDA olmak ihlal"**.


---

## Zemindeki boyadan alan tanıma

Kamera sayfasındaki **"Alanları otomatik bul"** düğmesi, zemindeki sarı ve
beyaz boyayı arayıp hazır bir bölge çizimi önerir. Sayfa sade görünümle açılır:
bu düğme ve aşağıdaki **Kareyi dondur** / **Ekran görüntüsü yükle** düğmeleri,
sayfanın üstündeki **Gelişmiş araçlar**'a basınca görünür (seçim tarayıcıda
hatırlanır). Öneriyi kabul etmek zorunda değilsiniz: kartına tıklarsanız çizim
tuvale yüklenir, köşelerini sürükleyip düzeltirsiniz. **Sistem hiçbir bölgeyi
kendiliğinden kaydetmez.**

### Ne bulur, ne bulamaz

| Zemin | Sonuç |
|---|---|
| İki paralel sarı çizgiyle işaretli yaya yolu (kesikli de olur) | Bulunur - aradaki yol da alana dahil edilir |
| Beyaz çerçeveyle işaretli yükleme sahası | Bulunur |
| Sarı-siyah taramalı yasak bölge | Çoğu zaman bulunur (sarı baskınsa) |
| Boyasız beton | **Bulunamaz** - elle çizmeniz gerekir |
| Solmuş, tozla kaplanmış boya | Bulunamayabilir |
| Karanlık ya da aşırı parlak görüntü | Bulunamaz - önce görüntü kalitesi düzeltilmeli |

"Bulunamadı" bir arıza değildir; her fabrika zemininde boya yoktur.

### Neden bulamadığını görmek

Alan bulunamadığında ekranda bir **teşhis görüntüsü** çıkar: sistemin boya saydığı
pikseller işaretlidir (turuncu = sarı sayılan, mavi = beyaz sayılan yerler).

- **Hiçbir yer işaretli değilse:** boya soluk ya da görüntü fazla karanlık. Önce
  bu sayfanın başındaki görüntü kalitesi adımlarını uygulayın; boya tanınmıyorsa
  eşik oynamak işe yaramaz.
- **Her yer işaretliyse:** görüntü aşırı parlak ya da zemin zaten beyaza yakın.
  Kameranın pozlamasını kısın.
- **Boya işaretli ama alan önerilmemişse:** işaretli bölge karenin %1,2'sinden
  küçük ya da %82'sinden büyüktür. Kameranın açısı alanın tamamını görmüyor olabilir.

### Çizim arka planını siz seçersiniz

Canlı görüntü her saniye yenilendiği için köşe tıklamak zor olabilir: tam
tıkladığınız an kare değişir. Canlı görüntünün altındaki satırdan arka planı
kendiniz seçersiniz.

| Düğme | Ne yapar |
|---|---|
| **Kareyi dondur** | O anki kareyi sabitler; tazeleme durur, rahatça çizersiniz |
| **Ekran görüntüsü yükle** | NVR'dan aldığınız bir kareyi (ya da telefon fotoğrafını) arka plan yapar |
| **Canlıya dön** | Tazelemeyi yeniden başlatır |

Yüklediğiniz görüntü **sunucuya kaydedilmez**; yalnız o an incelenir ve
tarayıcıda arka plan olur. Kalıcı olan tek şey, kaydettiğiniz bölgedir.

### Seçili alan taralı görünür

Görüntüde bir bölgenin **içine tıklayın**: o bölge çapraz taramayla dolar, adı
ve tipi yazar, yanında **Düzenle · Kapat · Sil** düğmeleri çıkar. Bölge
listesinde satır aramanıza gerek kalmaz.

Tarama yalnızca tarayıcıdaki çizim tuvalinde değil, **canlı görüntünün kendisinde
de** vardır: analiz, bölgeleri videoya taralı çizer. Böylece ekranda gördüğünüz
alanla sistemin değerlendirdiği alan aynıdır - "acaba bölge doğru yere mi oturdu"
sorusu görüntüye bakarak cevaplanır.

Tarama bir **vurgu**, örtü değildir: canlı görüntüde çizgiler, çözünürlüğe göre
alanın yaklaşık %7-22'sini kaplar (720p'de ~%7, 1080p'de ~%22); aradaki görüntü
açık kalır, altındaki insan ve araç kutuları okunur kalır.

Üst üste binen iki bölgeye tıklarsanız **küçük olan** seçilir - büyük bir bölgenin
içindeki küçük bölgeye başka türlü tıklanamazdı.

### Kamera henüz takılmadıysa

**"Ekran görüntüsü yükle"** ile NVR'dan aldığınız bir kareyi ya da telefonla
çektiğiniz bir fotoğrafı verebilirsiniz. Sistem alanları o görüntüde arar ve
görüntü, çizim yaparken arka plan olur - böylece **kamera bağlanmadan önce**
bölgeler ve kurallar hazırlanabilir.

Yüklediğiniz görüntü **sunucuya kaydedilmez**: yalnız o an incelenir. Kalıcı olan
tek şey, kaydettiğiniz bölgedir.

### Elinizdeki bir videoyla baştan sona deneme

Ekran görüntüsü bölge çizdirir ama **kuralları çalıştırmaz**: hareket yoktur,
takip yoktur, dolayısıyla ihlal de çıkmaz. Gerçek bir denemeye ihtiyacınız
varsa **Kameralar → Video ile Test** sayfasını kullanın.

1. **Gözat** ile bilgisayarınızdaki bir video dosyasını seçin (MP4, MOV, AVI,
   MKV, M4V - en fazla 1 GB). Dosyanın tam yolunu yazmanız gerekmez.
2. **Videoyu Yükle**'ye basın. Sistem videoyu bir kamera gibi izlemeye başlar
   ve sizi doğrudan o kameranın sayfasına götürür.
3. Görüntünün üstüne **bölgeleri çizin**, yanlarındaki **hazır kural**
   düğmelerine basın.
4. **Olaylar** sayfasında bulunan ihlalleri kanıt fotoğraflarıyla görün.

Kural motoru, takip ve olay kaydı canlı kameradakinin **aynısıdır** - taklidi
değil. Yani burada gördüğünüz sonuç, aynı kamera gerçekten bağlandığında da
göreceğiniz sonuçtur.

**"Video bitince dursun" kutusu (varsayılan işaretli).** İki farklı iş için
iki davranış vardır:

| Kutu | Ne olur | Ne zaman |
|---|---|---|
| **İşaretli** | Video bir kez baştan sona izlenir, sonra durum **"analiz tamamlandı"** olur | "Bu videoda kaç ihlal var?" sorusunun cevabını almak için |
| İşaretsiz | Video başa sarıp sürekli döner | Eşik ve bölge ayarını denerken görüntünün hiç kesilmemesi için |

İşareti kaldırırsanız aynı ihlal her turda yeniden yazılır ve olay listesi
kopyalarla dolar; o yüzden "kaç ihlal çıktı" sorusunu ancak işaretli kipte
cevaplayabilirsiniz.

Bittikten sonra **Yeniden çalıştır** düğmesi videoyu baştan oynatır (bölgeleri
değiştirip sonucu yeniden ölçmek için). **Duraklat** analizi durdurur ama
videoyu ve bulunan olayları saklar. **Sil** hem kamerayı hem yüklenen dosyayı
kaldırır; bulunan olaylar geçmişte kalır.

Yüklenen videolar `veri/videolar` klasöründe durur ve **kendiliğinden
silinmez** - kanıt fotoğraflarının aksine saklama süresi bakımı onlara
dokunmaz. Yeriniz daralırsa bu sayfadan **Sil** deyin.

### Alan çizimini kolaylaştıran diğer davranışlar

- **Dikdörtgen çiz:** bir köşeden karşı köşeye sürükleyip bırakın. Yükleme alanı,
  tır park alanı ve KKD alanlarının çoğu dikdörtgendir; dört tıklamanın üçünde
  hizayı tutturmak zordur.
- **Köşe sürükleme:** çizim bittikten sonra köşeleri fareyle taşıyabilirsiniz.
  Tek yanlış köşe için tüm çizimi baştan yapmanız gerekmez.
- **İlk noktaya tıklayarak kapatma:** üç köşeden sonra ilk nokta büyür.
- **Alan kapanınca taralı dolar:** "bu alan artık seçili" demenin en açık yolu.

---

## Bölgedeki nesneleri sayma

Bölge çizdiğiniz anda sayım başlar - **kural kurmanız gerekmez.** Sayılar
kamera sayfasındaki *Bölge sayımı* bölümünde görünür; o anki sayı ayrıca Canlı
duvar gibi izleme ekranlarında, canlı görüntünün üstünde bölgenin köşesinde
yazar (kamera sayfasının kendi görüntüsünde bölgeleri tarayıcı çizdiği için
orada yazmaz).

| Sayı | Cevapladığı soru |
|---|---|
| İçeride | Şu anda bölgede kaç nesne var? |
| Giren | Sayaç sıfırlandığından beri kaç **ayrı** nesne girdi? |
| En çok | Aynı anda en fazla kaç tane görüldü? (sınıf başına) |

Aynı kişi bölgede ne kadar dursa da bir kez sayılır. Vardiya başında
**"Giriş sayaçlarını sıfırla"** düğmesine basın; "giren" ve "en çok"
sıfırlanır, "içeride" sıfırlanmaz.

**Sayım hiçbir uyarı ya da anons üretmez.** İhlal için bölgeye bir kural
bağlamanız gerekir.

Sayının doğruluğu doğrudan tespit doğruluğuna bağlıdır: bu sayfadaki görüntü
kalitesi adımları sayımı da iyileştirir. Kişiler kutulanmıyorsa sayı da düşük
çıkar - önce canlı görüntüde kutulara bakın.
