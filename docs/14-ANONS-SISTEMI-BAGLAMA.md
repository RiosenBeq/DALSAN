# 14 - Anons Sistemine Bağlama Kılavuzu

Sistemin ihlalde **hoparlörden konuşabilmesi** için fabrikanın mevcut anons
altyapısına bağlanması gerekir. Bu belge o işi adım adım tarif eder.

> **Önce şunu bilin:** Anons **zorunlu değildir.** Hiç sesli kanal
> tanımlanmamışken sistem tam olarak çalışır: uyarılar ekranda görünür, olaylar
> kanıt fotoğrafıyla kaydedilir. Anons yalnızca "sahadaki kişi de duysun"
> adımıdır. Anons kurulamıyorsa proje durmaz (kabul kriteri K6,
> `01-MVP-KAPSAM.md`).
>
> **Kanal nedir:** sesin çıktığı her yer bir **uyarı kanalıdır**: bu
> bilgisayarın bir ses çıkışı (kablolu amfi ya da Bluetooth hoparlör) ya da
> ağdaki bir IP hoparlör. Kanallar **Komuta → Anons sistemi → Uyarı kanalları**
> listesinde eklenir, düzenlenir ve tek tek denenir (docs/17 K22). Eklenen ya
> da değiştirilen kanal çalışan sisteme kendiliğinden iner; yeniden başlatma
> gerekmez.

---

## 1. Önce karar: sizde hangi altyapı var?

Fabrikada anons üç biçimden birinde bulunur. Hangisi olduğunu bilmiyorsanız
§6'daki soruları elektrikçinize ya da anons firmanıza sorun.

| Sizdeki durum | Seçilecek yol | Zorluk |
|---|---|---|
| Hoparlörler bir **amplifikatöre** (amfi) bağlı, amfinin ses girişi var | **A - Ses çıkışı kanalı** | En kolay |
| Hoparlörler **ağ üzerinden** çalışıyor (IP hoparlör, PoE, "SIP" ya da "IP paging") | **B - IP hoparlör kanalı** | Orta |
| Anonsu bir **bilgisayar programı / anons sunucusu** yönetiyor | **B - IP hoparlör kanalı** | Orta |
| Hiçbiri, ya da bilinmiyor | **Şimdilik kanal eklemeyin** (yalnız ekran uyarısı) | - |

**Önerimiz:** Şüphedeyseniz **A ile başlayın.** Sunucuya bir ses kablosu takıp
amfinin hat girişine (AUX / LINE IN) vermek, çoğu fabrikada yarım saatlik
iştir ve hiçbir ağ ayarı gerektirmez.

---

## 2. Yol A - Ses kartı (en kolay)

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

### 2.1.1 Bluetooth hoparlör

Kablo çekmek istemiyorsanız Bluetooth bir hoparlör de kullanabilirsiniz.
Sistem açısından fark yoktur: Bluetooth hoparlör de bir **ses çıkışıdır.**

1. Hoparlörü **işletim sisteminden eşleştirin** (Windows: Ayarlar → Bluetooth
   ve cihazlar · Mac: Sistem Ayarları → Bluetooth · Linux: `bluetoothctl` ya
   da masaüstünün Bluetooth ayarı). Program eşleştirmeyi kendisi yapmaz:
   yapmaya kalkan bir yazılım, işletim sisteminin zaten yaptığı işi ikinci
   kez, daha kötü yapmış olurdu.
2. **Komuta → Anons sistemi → + Yeni kanal**: Tür = **Ses çıkışı**, "Ses
   çıkışı" kutusunda listeden hoparlörü seçin (Linux'ta adı
   `bluez_output.…` ile başlar).
3. Kanalın satırındaki **▶ Dene**'ye basın: üç kısa bip duymalısınız.

> **Kalıcı kurulum için kablo tercih edin.** Bluetooth iki yerde zayıftır:
> menzil (fabrikada duvar ve metal raf çok) ve hoparlörün kendi pili bitince
> sessizce düşmesi. Sistem bu düşmeyi fark eder ve kanal satırında kırmızı
> **"görünmüyor"** yazar, ama uyarıyı görmek için birinin ekrana bakması
> gerekir. Kablolu bağlantıda böyle bir risk yoktur.

### 2.2 Kanalı ekleme

**Komuta → Anons sistemi → Uyarı kanalları → + Yeni kanal**:

| Alan | Ne yazılır |
|---|---|
| Ad | "Sevkiyat amfisi" |
| Bölüm | Kameranın bölümü; boş bırakılırsa **Tüm fabrika** (§4) |
| Tür | **Ses çıkışı (kablolu ya da Bluetooth)** |
| Ses çıkışı | Listeden amfinin bağlı olduğu çıkış (o anki varsayılan önceden yazılı gelir) |

Kaydedin ve satırdaki **▶ Dene** ile sınayın. Yeniden başlatma gerekmez.

### 2.2.1 Hangi çıkıştan çalsın?

Bilgisayarda birden fazla ses çıkışı olabilir (dahili hoparlör, HDMI ekran,
Bluetooth hoparlör, USB ses kartı). Kanal formundaki "Ses çıkışı" kutusu o an
bağlı çıkışları önerir; kapalı bir Bluetooth hoparlörün adı elle de yazılabilir.

Seçimin programdan yapılabilmesi işletim sistemine bağlıdır ve formda
dürüstçe yazar:

| İşletim sistemi | Çıkış nasıl seçilir |
|---|---|
| **Linux** (fabrika sunucusu) | Listeden seçilir, kanal o çıkışa çalar. **Boş bırakılamaz:** "varsayılan çıkış" denetlenemez; Bluetooth hoparlör koparsa işletim sistemi sesi sessizce dahili hoparlöre devrederdi (docs/17 §7.2, R37). |
| **Mac** | Sistem Ayarları → Ses → Çıkış. Anons her zaman **varsayılan** çıkışa çalar; alan boş kalabilir. |
| **Windows** | Görev çubuğundaki hoparlör simgesi → çıkış cihazı. Anons **varsayılan** çıkışa çalar; alan boş kalabilir. |

Sebebi: Mac'in `afplay`'i ve Windows'un `winsound` ses çalıcısı cihaz
seçeneği almaz. Arayüzde çalışmayan bir seçim göstermek en kötüsü olurdu:
kullanıcı hoparlörü seçer, ses başka yerden çıkar ve sebebini hiçbir zaman
öğrenemezdi.

Kanalın **▶ Dene** düğmesi her üç sistemde de çalışır ve mesaj/ses dosyası
hazırlamanızı beklemez: kanalın kayıtlı çıkışından üç kısa bip çalar ve
yalnızca "bu hoparlörden ses çıkıyor mu" sorusunu cevaplar.

### 2.3 Ses dosyalarını hazırlama

Her anons mesajının bir `.wav` dosyası olmalıdır. Beş temel mesaj sistemle
birlikte gelir ama **ses dosyaları gelmez** - metni siz seslendirirsiniz.

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
**çalışmaz** - Windows'un yerleşik çalıcısı MP3 desteklemez, bu yüzden WAV şart.

Dosyaları program klasörünün içine (ör. `veri/sesler/`) koyun ve **Anons**
sayfasında her mesajın yanına yolunu yazın: `veri/sesler/baret.wav`.

> Yol, program klasörüne **göre** yazılır. Klasörün dışına çıkan bir yol
> (`../` ya da `C:\...`) güvenlik gereği reddedilir.

---

## 3. Yol B - IP hoparlör / anons sunucusu (HTTP)

Sistem, ihlalde anons cihazının adresine bir **HTTP isteği** gönderir.
Cihazlar bu isteği tek tip beklemez; bu yüzden üç biçim desteklenir.

### 3.1 Hangi biçim?

Biçim **Ayarlar → Anons** bölümündeki `ANONS_HTTP_BICIMI` ayarıdır ve bütün
IP hoparlör kanalları için ortaktır. Üç değer alır:

| Biçim | Ne gönderilir | Tipik cihaz |
|---|---|---|
| `json` *(varsayılan)* | Gövdede `{"key": "...", "text": "..."}` | Anons sunucusu, yazılım geçidi |
| `form` | Gövdede `key=...&text=...` | Gömülü web arayüzlü amfi, röle kartı |
| `get` | Sadece adres çağrılır (gövde yok) | "Adresi çağır, sesi çal" diyen IP hoparlörler |

### 3.2 Adres ve yer tutucular

IP hoparlör kanalının adresine iki yer tutucu yazılabilir; sistem gönderirken
bunları doldurur:

| Yer tutucu | Yerine yazılan |
|---|---|
| `{anahtar}` | Mesaj anahtarı (`helmet`, `vest`, `safe_distance` …) |
| `{metin}` | Anons metninin tamamı |

**`get` biçiminde adres, hangi mesajın çalınacağını taşımak ZORUNDADIR**;
yoksa her ihlalde aynı ses çalar. Kanal formu `{anahtar}` ya da `{metin}`
taşımayan adresi kaydetmez ve nedenini söyler.

### 3.3 Üç örnek

Her örnekte kanal, **+ Yeni kanal** formunda Tür = **IP hoparlör** ile
eklenir; biçim Ayarlar → Anons'tan seçilir.

**Örnek 1 - Cihaz, dosya adını adreste istiyor:**
```
Biçim (Ayarlar → Anons):  get
Kanal adresi:             http://10.0.0.9/play?file={anahtar}
```
Baret ihlalinde çağrılan adres: `http://10.0.0.9/play?file=helmet`

**Örnek 2 - Cihaz, metni okuyup seslendiriyor (metinden konuşma):**
```
Biçim (Ayarlar → Anons):  get
Kanal adresi:             http://10.0.0.9/tts?msg={metin}
```

**Örnek 3 - Anons sunucusu JSON bekliyor (varsayılan):**
```
Biçim (Ayarlar → Anons):  json
Kanal adresi:             http://10.0.0.9:8080/anons
```
Gönderilen gövde: `{"key": "helmet", "text": "Lütfen baretinizi takınız."}`

### 3.4 Adres kullanıcı adı/şifre içeriyorsa

`http://kullanici:sifre@10.0.0.9/play` biçiminde yazılabilir. Sistem bu adresi
**maskeler** - şifre hiçbir sayfada, hiçbir hata mesajında ve günlükte
(`veri/loglar/sistem.log`) görünmez; formda `••••` olarak durur ve öyle
bırakılırsa kayıtlı şifre korunur (docs/17 R18).

### 3.5 Adres bu bilgisayarı gösteremez

Hoparlör adresi `127.0.0.1`, `localhost`, `::1`, `0.0.0.0` ya da bağlantı-yerel
bir adres (`169.254.x.x`, `fe80::`) olamaz; form bunu kaydetmez ve anons
gönderilirken de yeniden denetlenir (docs/17 R30). Hoparlör fabrika ağındadır
(`10.x`, `172.16-31.x`, `192.168.x` serbesttir). Adres bir ad ise (`anons.fabrika`)
ad çözülür ve sonuç da aynı denetimden geçer.

---

## 4. Bölüm bölüm anons

Fabrikanın öbür ucundaki çalışanın, kendisiyle ilgisi olmayan bir uyarıyı
duymaması için kanallar **bölüme** bağlanır. Kanal formundaki "Bölüm" kutusu
kameraların bölümlerini listeler.

Seçim kuralı (`app/olaylar/anons.py` → `bolgeleri_sec`, docs/17 §7.3-1):

1. Olay, kameranın bölümüyle **birebir eşleşen BÜTÜN** açık kanallardan
   duyurulur (bir bölümde hem amfi hem IP hoparlör olabilir);
2. bölümde açık kanal yoksa **bölümü boş** olan kanallardan (**Tüm fabrika**);
3. o da yoksa ses çıkmaz: uyarı yalnızca ekranda görünür ve Anons ekranı bunu
   yazar ("sesli kanal yok").

> **Sık yapılan hata:** Kameranın alanı `sevkiyat`, hoparlörünki `Sevkiyat`
> yazılırsa eşleşme olmaz (büyük/küçük harf duyarlıdır). İkisini kopyala-yapıştır
> yapın.

Her kanalın satırında **▶ Dene** düğmesi vardır ve kanal kapalıyken de çalışır.
Kabloyu ve adresi, kanalı açmadan önce buradan sınayın. Mesaj listesindeki
"Dene" ise mesajı **Tüm fabrika** kanallarından çalar; Tüm fabrika kanalı yoksa
bunu söyler.

### 4.1 Eski kurulumdan geçiş (tek seferlik)

Eskiden anons `.env` dosyasındaki `ANONS`, `ANONS_SES_CIHAZI` ve
`ANONS_HTTP_ADRESI` satırlarıyla kurulurdu. Güncellemeden sonraki ilk açılışta
bu değerler **bir kez** kanal listesine aktarılır ve duyulan davranış aynı
kalır (docs/17 K22):

| Eski `.env` | Aktarımdan sonra |
|---|---|
| `ANONS=ses_karti` | "Tüm fabrika" = bu bilgisayarın seçili ses çıkışı. Eski hoparlör bölgeleri **kapalı** aktarılır (o ayarda hiç kullanılmıyorlardı); kullanmak için listeden açın. |
| `ANONS=http` | "Tüm fabrika" kanalı yoksa `.env` adresi o kanal olur. |
| `ANONS=null` | Kanal eklenmez; eski hoparlör bölgeleri kapalı aktarılır. |

Aktarım günlüğe yazılır. Sonra o üç satır okunmaz; silebilirsiniz. Aktarılan
bir kanalı sonradan silerseniz geri gelmez.

---

## 5. Devreye alma sırası - bu sırayı bozmayın

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
| "sesli kanal yok" yazıyor | Açık kanal yok | Anons sistemi → **+ Yeni kanal** (§2.2, §3) |
| Kanal satırında kırmızı "görünmüyor" | Ses çıkışı şu an bilgisayarda yok (Bluetooth hoparlör kapalı ya da menzil dışı) | Hoparlörü açın, sayfayı yenileyin; kalıcı kurulumda kablo tercih edin |
| Kanal satırında "çıkış seçilmedi" | Eski kayıtta çıkış adı boş (Linux) | Düzenle → çıkışı listeden seçip kaydedin |
| "Mesaj denenemedi: … Tüm fabrika kanalı yok" | Mesaj denemesi Tüm fabrika kanalından çalar | Kanalları kendi **▶ Dene** düğmeleriyle sınayın ya da bölümü boş bir kanal ekleyin |
| "Ses çalma komutu bulunamadı" | Linux'ta `alsa-utils` yok | `sudo apt install alsa-utils` |
| "…mesajına ses dosyası bağlanmamış" | WAV yolu boş | Anons sayfasında dosya yolunu yazın |
| "Dosya biçimi desteklenmiyor olabilir" | MP3 verilmiş | WAV'a çevirin (§2.3) |
| "Anons adresine ulaşılamadı" | Cihaz kapalı / farklı ağ / yanlış port | Aynı ağda mı, adresi tarayıcıda açılıyor mu? |
| Deneme çalışıyor, gerçek anons çalmıyor | Kural **gölge modda** | Uyarı zinciri → "Anonsu aç" |
| Her ihlalde **aynı** ses çalıyor | `get` biçiminde adres `{anahtar}` taşımıyor | Adrese `{anahtar}` ekleyin (§3.2) |
| Hoparlör aynı olayda üst üste bağırıyor | Bekleme süresi kısa | `ANONS_BEKLEME_SN` değerini artırın |
| Yanlış bölümün hoparlörü çalıyor | Bölüm adları eşleşmiyor | Kamera **Alan**ı ile kanalın **Bölüm**ü birebir aynı olmalı (§4) |
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
| Kanal başına ayrı HTTP biçimi | Fabrikadaki hoparlörler aynı marka olur; kullanıcıya öğrenmesi gereken ikinci bir kavram çıkarmamak için biçim tek yerde (Ayarlar → Anons, `ANONS_HTTP_BICIMI`) durur. |
| Gece vardiyasında ses seviyesini düşürme | Sistem ses seviyesini yönetmez; amfinin işidir. Çalışmayan bir düğme, olmayan bir özellikten kötüdür. |
