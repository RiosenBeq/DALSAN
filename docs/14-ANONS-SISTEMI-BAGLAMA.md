# 14 — Anons Sistemine Bağlama Kılavuzu

Sistemin ihlalde **hoparlörden konuşabilmesi** için fabrikanın mevcut anons
altyapısına bağlanması gerekir. Bu belge o işi adım adım tarif eder.

> **Önce şunu bilin:** Anons **zorunlu değildir.** `ANONS=null` iken sistem
> tam olarak çalışır — uyarılar ekranda görünür, olaylar kanıt fotoğrafıyla
> kaydedilir. Anons yalnızca "sahadaki kişi de duysun" adımıdır. Anons
> kurulamıyorsa proje durmaz (kabul kriteri K6, `01-MVP-KAPSAM.md`).

---

## 1. Önce karar: sizde hangi altyapı var?

Fabrikada anons üç biçimden birinde bulunur. Hangisi olduğunu bilmiyorsanız
§6'daki soruları elektrikçinize ya da anons firmanıza sorun.

| Sizdeki durum | Seçilecek yol | Zorluk |
|---|---|---|
| Hoparlörler bir **amplifikatöre** (amfi) bağlı, amfinin ses girişi var | **A — Ses kartı** | En kolay |
| Hoparlörler **ağ üzerinden** çalışıyor (IP hoparlör, PoE, "SIP" ya da "IP paging") | **B — HTTP** | Orta |
| Anonsu bir **bilgisayar programı / anons sunucusu** yönetiyor | **B — HTTP** | Orta |
| Hiçbiri, ya da bilinmiyor | **Şimdilik kapalı** (`ANONS=null`) | — |

**Önerimiz:** Şüphedeyseniz **A ile başlayın.** Sunucuya bir ses kablosu takıp
amfinin hat girişine (AUX / LINE IN) vermek, çoğu fabrikada yarım saatlik
iştir ve hiçbir ağ ayarı gerektirmez.

---

## 2. Yol A — Ses kartı (en kolay)

Sunucunun ses çıkışı, mevcut amfinin hat girişine bağlanır. Sistem ihlalde
kayıtlı bir `.wav` dosyasını çalar; amfi onu hoparlörlere dağıtır.

### 2.1 Fiziksel bağlantı

```
[DALSAN sunucusu] --3,5 mm ses kablosu--> [Amfi: AUX / LINE IN] --> [Hoparlörler]
```

- Kablo: 3,5 mm jack → amfinin istediği uç (çoğu amfide RCA ya da 6,35 mm jack).
- **Hoparlör çıkışına DEĞİL, hat girişine (LINE IN / AUX) bağlanır.** Hoparlör
  çıkışı yüksek güçlüdür ve sunucunun ses kartını bozar.
- Amfide "öncelik" (priority) girişi varsa onu tercih edin: anons sırasında
  müzik/radyo otomatik susar.

### 2.2 Ayar

Ayarlar sayfasından (**Komuta → Ayarlar**) ya da `.env` dosyasından:

```
ANONS=ses_karti
```

Sistemi yeniden başlatın (Kontrol Paneli → Durdur → Sistemi Başlat).

### 2.3 Ses dosyalarını hazırlama

Her anons mesajının bir `.wav` dosyası olmalıdır. Beş temel mesaj sistemle
birlikte gelir ama **ses dosyaları gelmez** — metni siz seslendirirsiniz.

| Mesaj anahtarı | Varsayılan metin |
|---|---|
| `safe_distance` | Lütfen iş makinelerinden güvenli mesafede durunuz. |
| `pedestrian_path` | Lütfen yaya yolunu kullanınız. |
| `vehicle_position` | Lütfen aracınızı belirlenen alana konumlandırınız. |
| `helmet` | Lütfen baretinizi takınız. |
| `vest` | Lütfen reflektörlü yeleğinizi giyiniz. |

Ses dosyası üretmenin üç yolu:

1. **İnsan sesi (en iyi).** Telefonla kaydedin, `.wav` olarak dışa aktarın.
   Fabrikada tanıdık bir ses, sentetik sesten daha çok dikkat çeker.
2. **Bilgisayarın kendi seslendirmesi.** macOS ve Windows metinden ses üretir.
3. **Anons firmasından isteyin.** Çoğu firma bunu ücretsiz yapar.

**Dosya biçimi:** WAV, 16 bit, 44.1 kHz, tek kanal (mono) yeterlidir. MP3
**çalışmaz** — Windows'un yerleşik çalıcısı MP3 desteklemez, bu yüzden WAV şart.

Dosyaları program klasörünün içine (ör. `veri/sesler/`) koyun ve **Anons**
sayfasında her mesajın yanına yolunu yazın: `veri/sesler/baret.wav`.

> Yol, program klasörüne **göre** yazılır. Klasörün dışına çıkan bir yol
> (`../` ya da `C:\...`) güvenlik gereği reddedilir.

---

## 3. Yol B — IP hoparlör / anons sunucusu (HTTP)

Sistem, ihlalde anons cihazının adresine bir **HTTP isteği** gönderir.
Cihazlar bu isteği tek tip beklemez; bu yüzden üç biçim desteklenir.

### 3.1 Hangi biçim?

`ANONS_HTTP_BICIMI` ayarı üç değer alır:

| Biçim | Ne gönderilir | Tipik cihaz |
|---|---|---|
| `json` *(varsayılan)* | Gövdede `{"key": "...", "text": "..."}` | Anons sunucusu, yazılım geçidi |
| `form` | Gövdede `key=...&text=...` | Gömülü web arayüzlü amfi, röle kartı |
| `get` | Sadece adres çağrılır (gövde yok) | "Adresi çağır, sesi çal" diyen IP hoparlörler |

### 3.2 Adres ve yer tutucular

`ANONS_HTTP_ADRESI` içine iki yer tutucu yazılabilir; sistem gönderirken
bunları doldurur:

| Yer tutucu | Yerine yazılan |
|---|---|
| `{anahtar}` | Mesaj anahtarı (`helmet`, `vest`, `safe_distance` …) |
| `{metin}` | Anons metninin tamamı |

**`get` biçiminde adres, hangi mesajın çalınacağını taşımak ZORUNDADIR** —
yoksa her ihlalde aynı ses çalar. Sistem bunu açılışta denetler ve `{anahtar}`
yoksa anlaşılır bir hatayla durur.

### 3.3 Üç örnek

**Örnek 1 — Cihaz, dosya adını adreste istiyor:**
```
ANONS=http
ANONS_HTTP_BICIMI=get
ANONS_HTTP_ADRESI=http://10.0.0.9/play?file={anahtar}
```
Baret ihlalinde çağrılan adres: `http://10.0.0.9/play?file=helmet`

**Örnek 2 — Cihaz, metni okuyup seslendiriyor (metinden konuşma):**
```
ANONS=http
ANONS_HTTP_BICIMI=get
ANONS_HTTP_ADRESI=http://10.0.0.9/tts?msg={metin}
```

**Örnek 3 — Anons sunucusu JSON bekliyor (varsayılan):**
```
ANONS=http
ANONS_HTTP_BICIMI=json
ANONS_HTTP_ADRESI=http://10.0.0.9:8080/anons
```
Gönderilen gövde: `{"key": "helmet", "text": "Lütfen baretinizi takınız."}`

### 3.4 Adres kullanıcı adı/şifre içeriyorsa

`http://kullanici:sifre@10.0.0.9/play` biçiminde yazılabilir. Sistem bu adresi
**ekranda maskeler** — şifre hiçbir sayfada, hiçbir hata mesajında görünmez.
Yalnızca `veri/loglar/sistem.log` dosyasına düşer.

---

## 4. Bölüm bölüm anons (hoparlör bölgeleri)

Varsayılanda tüm ihlaller aynı adrese gider. Fabrikanın öbür ucundaki çalışanın,
kendisiyle ilgisi olmayan bir uyarıyı duymaması için **hoparlör bölgeleri**
tanımlanır.

**Komuta → Anons sistemi → Hoparlör bölgeleri** bölümünden:

| Alan | Ne yazılır |
|---|---|
| Ad | "Sevkiyat holü hoparlörü" |
| Bölüm | Kameranın **Alan** alanıyla **birebir aynı** metin: `Sevkiyat` |
| Adres | O bölümün hoparlörünün adresi |

Seçim kuralı (`app/olaylar/anons.py` → `bolge_sec`):

1. Kameranın bölümüyle **birebir eşleşen** açık bölge,
2. yoksa **bölümü boş** olan bölge ("tüm fabrika"),
3. o da yoksa `.env`'deki tek adres.

> **Sık yapılan hata:** Kameranın alanı `sevkiyat`, hoparlörünki `Sevkiyat`
> yazılırsa eşleşme olmaz (büyük/küçük harf duyarlıdır). İkisini kopyala-yapıştır
> yapın.

Her hoparlörün yanında **"Bu hoparlörü dene"** düğmesi vardır; anons ayarınız
`null` olsa bile çalışır. Kabloyu ve adresi, sistemi anonsa açmadan önce
buradan sınayın.

---

## 5. Devreye alma sırası — bu sırayı bozmayın

Yeni kurulan bir kuralı ilk günden anonsa açmak, sistem henüz ayarlanmamışken
çalışanı yanlış uyarır ve **bir daha düzelmeyen bir güven kaybı** yaratır.

```
1. Kural kurulur, GÖLGE MODDA bırakılır
      → olay yazılır, ekranda görünür, hoparlör SUSAR
2. En az 3 gün (KKD kurallarında daha uzun) böyle çalışır
3. Komuta → Olay inceleme'den olaylar tek tek işaretlenir
      → "Doğru uyarı" / "Yanlış alarm"
4. Yanlış alarm oranı kabul edilebilir mi?
      HAYIR → eşikler ayarlanır, 2. adıma dönülür
      EVET  → 5. adıma geçilir
5. Komuta → Uyarı zinciri → "Anonsu aç"
```

Gölge mod ayrı bir kurulum değildir; her kuralın bir düğmesidir
(`Komuta → Uyarı zinciri`).

---

## 6. Anons firmanıza / elektrikçinize soracaklarınız

Bu listeyi olduğu gibi iletebilirsiniz:

1. Fabrikadaki hoparlörler bir **amplifikatöre mi** bağlı, yoksa **ağ üzerinden
   (IP) mi** çalışıyor?
2. Amfi varsa: **boş bir hat girişi (LINE IN / AUX)** var mı? Anons önceliği
   (priority) girişi var mı?
3. IP ise: hoparlörleri **HTTP isteğiyle** tetiklemek mümkün mü? Mümkünse
   **örnek bir adres** yazabilir misiniz?
4. Cihaz **hazır ses dosyası** mı çalıyor, yoksa gönderilen **metni
   seslendirebiliyor** mu?
5. Anons cihazı, DALSAN sunucusuyla **aynı ağda** mı? Arada güvenlik duvarı
   varsa hangi port açılmalı?
6. Anons sırasında çalan **müzik/radyo otomatik susuyor** mu?
7. Ses dosyası isteniyorsa: hangi **biçim** (WAV/MP3), hangi **örnekleme hızı**?

---

## 7. Sorun giderme

| Belirti | Sebep | Çözüm |
|---|---|---|
| "Anons KAPALI" yazıyor | `ANONS=null` | Ayarlar'dan `ses_karti` ya da `http` seçip **yeniden başlatın** |
| "Ses çalma komutu bulunamadı" | Linux'ta `alsa-utils` yok | `sudo apt install alsa-utils` |
| "…mesajına ses dosyası bağlanmamış" | WAV yolu boş | Anons sayfasında dosya yolunu yazın |
| "Dosya biçimi desteklenmiyor olabilir" | MP3 verilmiş | WAV'a çevirin (§2.3) |
| "Anons adresine ulaşılamadı" | Cihaz kapalı / farklı ağ / yanlış port | Aynı ağda mı, adresi tarayıcıda açılıyor mu? |
| Deneme çalışıyor, gerçek anons çalmıyor | Kural **gölge modda** | Uyarı zinciri → "Anonsu aç" |
| Her ihlalde **aynı** ses çalıyor | `get` biçiminde adres `{anahtar}` taşımıyor | Adrese `{anahtar}` ekleyin (§3.2) |
| Hoparlör aynı olayda üst üste bağırıyor | Bekleme süresi kısa | `ANONS_BEKLEME_SN` değerini artırın |
| Yanlış bölümün hoparlörü çalıyor | Bölüm adları eşleşmiyor | Kamera **Alan**ı ile hoparlör **Bölüm**ü birebir aynı olmalı (§4) |
| Ekranda uyarı var, hoparlör hiç çalmıyor | Kurala anons mesajı bağlanmamış | Kurallar → kuralı düzenle → anons mesajı seç |

Her denemenin sonucu **Anons sistemi** sayfasında son satır olarak yazar
(çalındı / çalınamadı + sebep). Bir şey çalışmıyorsa önce oraya bakın.

---

## 8. Neler bilerek YAPILMADI

| Beklenebilecek özellik | Neden yok |
|---|---|
| SIP/VoIP ile doğrudan hoparlöre çağrı | Ayrı bir yığın (SIP kütüphanesi, ses kodlayıcı) demektir. IP hoparlörlerin neredeyse tamamının HTTP tetikleyicisi var; onu kullanmak tek satır ayar. |
| Metinden konuşma (sunucuda) | Yeni bir çalışma zamanı ve dil modeli. Ses dosyasını bir kez kaydetmek, hem daha net hem bedelsiz. `get` biçimiyle cihazın kendi seslendirmesi kullanılabilir. |
| Anonsun gerçekten duyulduğunun doğrulanması | Geri besleme mikrofonu ve ölçüm gerektirir. Bugün cihazın "aldım" yanıtı kaydedilir; ötesi `07-YOL-HARITASI.md` #16. |
| Bölge başına ayrı HTTP biçimi | Fabrikadaki hoparlörler aynı marka olur; kullanıcıya öğrenmesi gereken ikinci bir kavram çıkarmamak için biçim tek yerde (`.env`) durur. |
| Gece vardiyasında ses seviyesini düşürme | Sistem ses seviyesini yönetmez; amfinin işidir. Çalışmayan bir düğme, olmayan bir özellikten kötüdür. |
