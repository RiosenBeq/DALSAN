# 12 — Kamera Yerleşimi ve Görüntü Kalitesi

> **Bu dokümanın tek iddiası:** Sistemin isabetini en çok belirleyen şey model
> değil, **kameranın gördüğü görüntüdür.** Eşik ayarlamak, kirli bir lensi
> silmenin yerini tutmaz.

---

## 1. Sistem neyi tanır

| Nesne | Nasıl tanınır | Ekrandaki rengi |
|---|---|---|
| **İnsan** | Hazır model (COCO `person`) | Yeşil |
| **Tır / araç** | Hazır model (`truck`, `bus`, `car`) | Mavi |
| **Forklift** | **Şimdilik araç olarak** görünür — hazır modelde forklift sınıfı yoktur (docs/08 R1). Saha görüntüsüyle ince ayar yapılınca ayrı sınıf olur | Turuncu (ayrı sınıf geldiğinde) |
| **Baret** | KKD sınıflandırıcısı — **henüz eğitilmedi**, veri toplanıyor (docs/04) | Kişi kutusunda **B** rozeti |
| **Reflektörlü yelek** | Aynı sınıflandırıcı | Kişi kutusunda **Y** rozeti, **sarı** |
| **Kural ihlali** | Kural motoru | Kutu **kırmızıya** döner ve kalınlaşır |
| **Çizdiğiniz bölge** | — | Mavi çerçeve |

Rozetlerin üç durumu vardır: **dolu = var**, **kırmızı çarpı = yok**,
**gri soru işareti = belirsiz**. **Belirsiz asla ihlal sayılmaz** (docs/04 §1).
KKD modeli eğitilene kadar tüm kişiler belirsiz görünür — bu normaldir, arıza değil.

Aynı tablo arayüzde de vardır: kamera sayfasındaki **Renk anahtarı**.

---

## 2. Kamera yerleşimi — en çok fark yaratan beş şey

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
| **Kontrast düşük** | Sisli/dumanlı görünüm | `.env` → `GORUNTU_IYILESTIRME=otomatik` |

### `GORUNTU_IYILESTIRME=otomatik` ne yapar

Her karede **yerel kontrast dengeleme** (CLAHE) uygular: karanlık köşedeki insanı
görünür kılar, aşırı parlak bölgeyi bastırır. Yalnızca parlaklık kanalında
çalışır, **renkleri bozmaz** — reflektörlü yeleğin sarısı sarı kalır.

Bedeli: kare başına birkaç milisaniye işlemci. Görüntü zaten iyiyse belirgin
fayda sağlamaz; **önce uyarı satırına bakın**, gerek yoksa kapalı bırakın.

Tespit ve önizleme **aynı** kareyi kullanır: ekranda modelin gördüğü görüntüyü
görürsünüz. Sistem size, kendi kararını verdiğinden farklı bir görüntü göstermez.

---

## 4. Hassasiyet ayarı — sırasıyla deneyin

Eşikler `.env` dosyasındadır ve değiştirdikten sonra sistem yeniden başlatılır.

```
TESPIT_GUVEN_ESIGI=0.35          # genel eşik (araç vb.)
TESPIT_INSAN_GUVEN_ESIGI=0.28    # insan için ayrı ve daha düşük
TESPIT_NMS_ESIGI=0.45            # üst üste binen kutuların birleştirilmesi
TESPIT_EN_KUCUK_KENAR_PX=12      # bundan küçük kutular atılır
```

**Nesne kaçıyorsa** (kutu çıkmıyor):
1. Önce kamera sayfasındaki kalite uyarısına bakın — sorun genelde oradadır.
2. `TESPIT_INSAN_GUVEN_ESIGI` değerini **0,05'lik adımlarla** düşürün (0,28 → 0,23 → 0,18).
3. Uzaktaki küçük nesne için `TESPIT_EN_KUCUK_KENAR_PX` değerini düşürün (12 → 8).
4. Hâlâ olmuyorsa daha isabetli modele geçin — **NextGen AI İsabetli**:
   `MODEL_DOSYASI=models/yolox_s.onnx`
   (daha yavaş ama küçük nesnelerde belirgin daha iyi; ilk açılışta kendisi iner).

**Yanlış tespit çoksa** (olmayan nesneye kutu):
1. Aynı eşikleri **yükseltin**.
2. `TESPIT_EN_KUCUK_KENAR_PX` değerini yükseltin (12 → 20): uzak gürültü elenir.
3. Kalabalık sahnede kutular birbirine giriyorsa `TESPIT_NMS_ESIGI` değerini
   0,5-0,6 arasında deneyin.

> **İlke (docs/00):** Kaçırılan ihlal bilinen sınırdır; **yanlış alarm ciddi
> kusurdur.** Kullanıcı yanlış alarma alışırsa gerçek uyarıya da bakmaz.
> Bu yüzden varsayılanlar temkinlidir ve gevşetme kararı sizindir.

---

## 5. Forklift hakkında dürüst not

Hazır COCO modelinde **forklift sınıfı yoktur.** Forklift bugün çoğu zaman
`truck` (tır/araç) olarak görünür ve güvenli mesafe kuralı onu araç sayar —
yani kural **çalışır**, ama ekranda "forklift" yerine "tır" yazar.

Gerçek forklift sınıfı, sahadan toplanan görüntülerle ince ayar yapıldığında
gelir (3-4. hafta işi, docs/08 R1). O gün değişecek tek yer
`backend/app/analiz/tespit.py` içindeki sınıf eşleme tablosudur.

---

## 6. Kamera ekleme sırasında sık karşılaşılanlar

| Belirti | Sebep / çözüm |
|---|---|
| "Kameraya ağ üzerinden ulaşılamıyor" | IP veya port yanlış; kamera kapalı; ağ kablosu takılı değil |
| "Ulaşıldı ama görüntü akışı açılamadı" | Kullanıcı adı/şifre veya akış yolu yanlış. Şifrede `@ : / #` varsa `%40 %3A %2F %23` yazın |
| "Kameraya bağlanıldı ama görüntü gelmedi" | NVR'ın eşzamanlı bağlantı sınırı dolmuş olabilir; ya da akış H.265 ve çözülemiyor — kamerada H.264 seçin |
| "Video dosyası bulunamadı" | Tam yol gerekir. Mac: dosyayı Finder'da seçip **Option+Command+C**. Windows: dosyaya **Shift + sağ tık → "Yol olarak kopyala"** |
| Kamera "bağlanıyor"da kalıyor | İlk bağlantı 30 saniye sürebilir; 60 saniye sonra "çevrimdışı" olur ve sebebi yazar |

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
verilir. Yolu, üzerine basılan zemin alanı olarak çizin — havada duran bir
dikdörtgen değil.

Aynı kuralı elle kurmak isterseniz: Kurallar → Yeni Kural → Bölge ihlali →
Koşul: **"Bölge DIŞINDA olmak ihlal"**.
