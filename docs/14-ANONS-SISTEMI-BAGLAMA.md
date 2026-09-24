# 14 - Anons Sistemine Bağlama Kılavuzu

Sistemin ihlalde **hoparlörden konuşabilmesi** için fabrikanın mevcut anons
altyapısına bağlanması gerekir. Bu belge o işi adım adım tarif eder.

> **Önce şunu bilin:** Anons kurulamıyorsa proje durmaz (kabul kriteri K6,
> `01-MVP-KAPSAM.md`): sesli kanal yokken de uyarılar ekranda görünür, olaylar
> kanıt fotoğrafıyla kaydedilir. Ama sistem bu eksiği **gizlemez** (docs/17
> K21, Ç39): kurulum listesindeki "Sesli anons" adımı, sistem şeridi ve
> Kontrol Paneli kırmızı yazar; her ihlal "Uyarı hiçbir sesli kanala
> ulaşamadı" diye kaydedilir ve sistem "hazır değil" görünür (§4.3). Sahadaki
> kişinin duymadığı bir uyarı, ekrandaki bir uyarıyla aynı güvenliği vermez.
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
| Hiçbiri, ya da bilinmiyor | **Şimdilik kanal eklemeyin** (yalnız ekran uyarısı; ekranlar bunu kırmızı gösterir) | - |

**Önerimiz:** Şüphedeyseniz **A ile başlayın.** Sunucuya bir ses kablosu takıp
amfinin hat girişine (AUX / LINE IN) vermek, çoğu fabrikada yarım saatlik
iştir ve hiçbir ağ ayarı gerektirmez.

### 1.1 Kanal türleri

| Kanal | Sesi nereden çıkar | Uyarı garantisine sayılır mı | Sağlığı nasıl izlenir (§4.3) |
|---|---|---|---|
| Ses çıkışı: kablolu amfi | Bu bilgisayarın ses kartı → amfinin hat girişi | Evet | Linux: çıkış listede mi · Mac: varsayılan çıkış · Windows: okunamaz ("bilinmiyor") |
| Ses çıkışı: Bluetooth hoparlör | Bu bilgisayarın Bluetooth'u | Evet, ama **tek sesli kanal olamaz** (GÖREV §7) | Linux: hoparlör listede mi (Bluetooth adresiyle) |
| IP hoparlör | Ağdaki cihaz, HTTP isteğiyle | Evet | Adresine TCP bağlantısı (≤3 sn) |
| Ekran (izleme penceresi) | Tarayıcıda uyarı bandı ve tarayıcının sesi | **Hayır**, yalnız bilgi | Açık pencere sayısı (teslim kaydında) |
| Webhook, e-posta, SMS | - | - | Yok: kodlanmadı (docs/17 S4, `07-YOL-HARITASI.md` #4) |

Docker'da (fabrika sunucusu) ses çıkışı kanalı için container'a ses yolu
açılır: §2.4.

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

   **Linux'ta hoparlöre "güven" (trust) verin; şarttır.** Güvenilmeyen cihaz
   kapatılıp açıldığında kendiliğinden bağlanamaz:

   ```bash
   bluetoothctl devices           # hoparlörün adresini bulun: AA:BB:CC:DD:EE:FF
   bluetoothctl trust AA:BB:CC:DD:EE:FF
   bluetoothctl connect AA:BB:CC:DD:EE:FF
   ```

   Hoparlör kapatılıp açılınca kendiliğinden bağlanıyor mu, kurulumda bir
   kez deneyin. Bağlanmıyorsa sistem kanalı 30 sn içinde **"koptu"** gösterir
   ve uyarı "Tüm fabrika" kanalına düşer, ama hoparlörü **program yeniden
   bağlamaz** (yeniden bağlanma bekçisi yazılmadı, docs/17 §7.5-3, S9):
   yukarıdaki `connect` komutu ya da işletim sisteminin Bluetooth menüsü
   gerekir. Sahada bu sık oluyorsa `07-YOL-HARITASI.md` #22'ye bakın.
2. **Komuta → Anons sistemi → + Yeni kanal**: Tür = **Ses çıkışı**, "Ses
   çıkışı" kutusunda listeden hoparlörü seçin (Linux'ta adı
   `bluez_output.…` ile başlar).
3. Kanalın satırındaki **▶ Dene**'ye basın: üç kısa bip duymalısınız.

> **Kalıcı kurulum için kablo tercih edin.** Bluetooth iki yerde zayıftır:
> menzil ve hoparlörün kendi pili bitince sessizce düşmesi. Menzil açık alanda
> tipik olarak ~10 m'dir; metal raf, duvar ve iş makinesi gövdesi bunu kısaltır,
> motor ve kompresör gürültüsü de küçük bir hoparlörün sesini bastırır. Birden
> fazla bölüme ses gerekiyorsa her bölüme ayrı bir hoparlör (ayrı bir kanal)
> koyun; tek hoparlörle bütün fabrikayı kapsamaya çalışmayın. Sistem bu düşmeyi fark eder (§4.3): 30 sn görünmeyen
> kanal **"koptu"** olur, olay listesine "Ses kanalı koptu" düşer ve o bölümün
> uyarısı "Tüm fabrika" kanalından duyurulur. Ama birinin fark etmesi yine
> ekrana ya da Kontrol Paneli'ne bağlıdır. Kablolu bağlantıda bu risk yoktur.
>
> **Bluetooth tek uyarı kanalı olamaz** (GÖREV §7). Sesli kanalların hepsi
> Bluetooth hoparlörse (ya da Bluetooth dışındakiler şu an kopuksa) ses yine
> çalar, ama sistem şeridi, Kontrol Paneli ve kurulum listesi bunu **kırmızı**
> gösterir (`tek_kanal_bluetooth`). Yanına kablolu bir çıkış ya da bir IP
> hoparlör ekleyin.
>
> Hoparlör kapatılıp açılınca işletim sistemi onu bazen başka bir profil
> adıyla bağlar (`bluez_output.AA_BB_….1` → `….a2dp-sink`). Sistem adın içindeki
> Bluetooth adresine bakar: adres aynıysa aynı hoparlör sayılır ve ses bugünkü
> adına çalınır; kanalı yeniden seçmeniz gerekmez.

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

Her anons mesajının bir `.wav` dosyası olmalıdır. Sekiz mesaj sistemle
birlikte gelir ama **ses dosyaları gelmez** - metni siz seslendirirsiniz.
Metinler taslaktır; son hâlini İSG belirler (docs/17 S21) ve Anons sayfasından
değiştirilir.

**Dosya bağlanana kadar hoparlör susmaz.** Mesaja ses dosyası bağlanmamışsa,
bağlı dosya bulunamıyorsa ya da proje klasörünün dışındaysa ses çıkışı kanalı
sözlü anons yerine üretilmiş bir uyarı tonu (kesik "bip", yaklaşık 2 sn) çalar
ve teslim kaydına "sözlü anons yerine uyarı tonu çalındı" yazılır. Uyarı yine
ulaşmış sayılır. Anons sayfasında bu mesajlar "ses dosyası yok" rozetiyle
görünür. Ton bir yedektir: kim ne yapmalı söylemez, sözlü kayıt yine gerekir
(operatör isteği 23.09.2026: risk anında hoparlörden uyarı verilsin).

**Kurala mesaj seçilmemişse de hoparlör susmaz.** Kural formunda "mesaj yok"
seçili kalmışsa (ya da kuralın mesajı kapatılmış, silinmişse) olay kendi
adıyla duyurulur. Ses çıkışı uyarı tonunu çalar ve teslim kaydına "kurala
anons mesajı bağlanmamış" (mesaj kapatılmışsa "kuralın anons mesajı kapalı")
yazılır. IP hoparlöre `uyari` anahtarı ve olayın Türkçe adı gider: metni
seslendiren cihaz adı okur (örneğin "Yükleme alanında yaya"), dosya çalan
cihaza `uyari` adıyla bir uyarı sesi yüklenmelidir (aşağıdaki tablo, §3.3
Örnek 1). "Uyarı ulaşmadı" denetimi bu olaylar için de çalışır (docs/17 K21).
Bir kuralı tamamen susturmanın yolu **gölge mod**dur.

| Mesaj anahtarı | Varsayılan metin |
|---|---|
| `safe_distance` | Lütfen iş makinelerinden güvenli mesafede durunuz. |
| `pedestrian_path` | Lütfen yaya yolunu kullanınız. |
| `vehicle_position` | Lütfen aracınızı belirlenen alana konumlandırınız. |
| `helmet` | Lütfen baretinizi takınız. |
| `vest` | Lütfen reflektörlü yeleğinizi giyiniz. |
| `vehicle_on_walkway` | Dikkat, yaya yolunda araç var. |
| `person_in_vehicle_lane` | Lütfen araç yolundan çıkınız. |
| `restricted_entry` | Bu alana giriş yasaktır. |
| `uyari` | Mesajı olmayan (ya da kapalı) kuralın olayı: metin olayın adıdır. Ses çıkışında dosya gerekmez, uyarı tonu çalar; dosya çalan IP hoparlöre bu adla bir uyarı sesi yükleyin |

Dosyaları **`veri/sesler/`** klasörüne koyun (sistem açılışta bu klasörü
kendisi açar). `veri/` altında oldukları için yedeğe girerler ve Docker'da
container'a bağlı klasörde dururlar.

Ses dosyası üretmenin yolları:

1. **İnsan sesi (en iyi).** Telefonla kaydedin, `.wav` olarak dışa aktarın.
   Fabrikada tanıdık bir ses, sentetik sesten daha çok dikkat çeker. Kaydı
   yapan kişinin sesinin anonsta kullanılmasına onay vermesi yeterlidir.
2. **Anons firmasından isteyin.** Çoğu firma bunu ücretsiz yapar.
3. **Bilgisayarın kendi seslendirmesi yalnız DENEME içindir.** macOS ve
   Windows metinden ses üretir, ama bu seslerle üretilen dosyanın fabrikada
   kalıcı kullanımına lisansın izin verdiği doğrulanmadı (macOS sistem sesleri
   kişisel ve ticari olmayan kullanım içindir; Windows koşulları
   doğrulanmadı). Açık kaynak Türkçe sentetik sesler de (piper `tr_TR-dfki`)
   ticari olmayan lisanslıdır (docs/16 §3). Kalıcı kayıt için 1 ya da 2.

**Dosya biçimi:** WAV, 16 bit, 44.1 kHz, tek kanal (mono) yeterlidir. MP3
**çalışmaz** - Windows'un yerleşik çalıcısı MP3 desteklemez, bu yüzden WAV şart.

Dosyaları program klasörünün içine (ör. `veri/sesler/`) koyun ve **Anons**
sayfasında her mesajın yanına yolunu yazın: `veri/sesler/baret.wav`.

> Yol, program klasörüne **göre** yazılır. Klasörün dışına çıkan bir yol
> (`../` ya da `C:\...`) güvenlik gereği reddedilir.

---

### 2.4 Docker'da ses (fabrika sunucusu)

Fabrika sunucusunda sistem Docker container'ında çalışır; container'ın kendi
ses kartı yoktur. Ses çıkışı kanalı, **host'ta çalışan ses sunucusuna**
(PulseAudio ya da PipeWire'ın `pipewire-pulse`'u) çalar: imajda yalnız
`paplay` ve `pactl` vardır, host'un ses soketi container'a bağlanır
(docs/17 §7.6 yol A, S29). Bluetooth hoparlör de o ses sunucusunda bir
çıkıştır; eşleştirme ve "trust" host'ta bir kez yapılır (§2.1.1).

Ses yolu **isteğe bağlıdır**: yalnız IP hoparlör kullanan kurulumda gerekmez.
Açmak için, host'ta sesin çalacağı kullanıcıyla:

```bash
id -u ; id -g              # kullanıcı ve grup numarası (çoğu kurulumda 1000)
pactl info                 # "Server Name" satırı ses sunucusunun çalıştığını gösterir
pactl list short sinks     # çıkışlar; Bluetooth hoparlör "bluez_…" ile başlar
sudo chown -R "$(id -u):$(id -g)" veri ayar    # container artık root değil
docker compose -f docker-compose.yml -f docker-compose.ses.yml up -d
```

Numara 1000 değilse son komutun başına `DALSAN_UID=<numara> DALSAN_GID=<grup>`
yazın. `docker-compose.ses.yml` container'ı bu kullanıcının numarasıyla
çalıştırır (ses sunucusu yalnız kendi kullanıcısına çalar) ve soketi
`/run/dalsan-ses/native` olarak bağlar. **Verilmeyenler:** `privileged`, host
ağı, `NET_ADMIN`, `NET_RAW`, `/dev/snd`, D-Bus (docs/16 §4). Kanal eklendikten
sonra satırdaki **▶ Dene** ile sınayın.

Ekransız sunucuda ses sunucusu kullanıcı oturumu olmadan da çalışmalıdır:
PipeWire'da WirePlumber'ın `main-systemwide` profili ya da
`monitor.bluez.seat-monitoring = disabled`; PulseAudio'da önce mevcut
`default.pa` okunur (docs/16 §4). Kontrol listesi: `bluetoothctl --version`,
`pactl info`, `id -u`, `/etc/bluetooth/main.conf`.

| Belirti | Sebep | Çözüm |
|---|---|---|
| `docker compose up` "bind source path does not exist" der | Soket yok: ses sunucusu çalışmıyor ya da numara yanlış | `pactl info` host'ta çalışıyor mu; `DALSAN_UID` doğru mu |
| Kanal "koptu", sebep "ses sunucusuna bağlanılamadı" | Ses yolu açılmadan container başlatıldı ya da soket erişilemiyor | Yukarıdaki komutla iki dosyayla başlatın |
| **▶ Dene** "Access denied" / "Connection refused" | PulseAudio çerez istiyor (PipeWire istemez) | Çerezi bağlayın: `docker-compose.ses.yml`'e `- "/home/<kullanıcı>/.config/pulse/cookie:/run/dalsan-ses/cookie:ro"` ve ortam değişkeni `PULSE_COOKIE: /run/dalsan-ses/cookie` |
| Sistem açılmıyor, günlükte "izin yok" | `veri/` ya da `ayar/` hâlâ root'a ait | `sudo chown -R "$(id -u):$(id -g)" veri ayar` |

> **DOĞRULANMADI:** Bu yol hedef sunucuda henüz derlenip denenmedi; imaj bu
> depoda derlenemiyor (docs/17 §7.6). İlk sahada deneyişte sonucu bu bölüme
> yazın. Kopmuş bir Bluetooth sink'e `paplay`'in hata koduyla döndüğü de
> doğrulanmadı; kanal sağlığı bu yüzden ayrıca yoklanır (§4.3).

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

Cihazda sekiz mesajın yanında `uyari` sesi de olmalı: mesajı olmayan kuralın
olayı `http://10.0.0.9/play?file=uyari` ile gelir. Yoksa cihaz ya hata verir
("uyarı ulaşmadı" alarmı çıkar) ya da sessizce hiçbir şey çalmaz.

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
   duyurulur (bir bölümde hem amfi hem IP hoparlör olabilir). **Koptu**
   durumundaki kanal atlanır (§4.3);
2. bölümde açık kanal yoksa ya da bölümün bütün kanalları koptuysa **bölümü
   boş** olan kanallardan (**Tüm fabrika**). Atlanan kanal teslim kaydına
   "Tüm fabrika'dan duyuruldu" diye yazılır;
3. o da yoksa ses çıkmaz: uyarı yalnızca ekranda görünür, olay listesine
   "Uyarı hiçbir sesli kanala ulaşamadı" düşer ve sistem "hazır değil" görünür
   (§4.3). Her şey koptuysa kanallar yine denenir: belki şimdi bağlanmışlardır.

Bölümlü kanal var ama "Tüm fabrika" kanalı yoksa Kontrol Paneli bunu sarı
yazar (`yedek_ses_kanali_yok`): kanalı olmayan ya da kanalları kopan bölüm susar.

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

### 4.2 Uyarılar hangi sırayla çalar

Her ÇIKIŞIN (bir ses çıkışı ya da bir IP hoparlör adresi) kendi sırası vardır:
aynı hoparlörde iki ses üst üste binmez, farklı hoparlörler birbirini beklemez.
İki bölümün kanalı aynı hoparlörü gösteriyorsa onların sesi de sıraya girer.

- **Önem sırası:** Kritik (araç-yaya yakınlığı) önce, sonra Yüksek, Orta, Düşük.
  Aynı önemde gelen önce çalar. "Dene" düğmeleri gerçek bir uyarının önüne geçmez.
- **Kesme:** kritik bir uyarı gelince, ses çıkışında o an çalan daha düşük
  önemli ses kesilir ve kritik olan hemen çalar. IP hoparlöre giden istek
  kesilemez; kritik olan yalnız sırada öne geçer.
- **Bayat uyarı çalınmaz:** sırada tekrar aralığından (Ayarlar → Anons, varsayılan
  30 sn) uzun bekleyen kritik olmayan uyarı atılır; geçmiş bir durumu anlatan
  anons da yanlış alarmdır.
- **Tekrar bastırma:** aynı kamera ve mesaj, aynı kanaldan tekrar aralığı içinde
  bir kez çalar. Bastırma yalnız ses **gerçekten çaldıysa** başlar: çalamayan bir
  hoparlör bir sonraki ihlalde yeniden denenir. Kritik bir olayın açılışı
  bastırılmaz: aynı kamerada ikinci, ayrı bir yakınlık da duyurulur.

Her deneme **teslim kaydına** yazılır (Anons sistemi → Teslim kaydı): son 24
saatte kaç deneme çaldı, kaçı bastırıldı, bayatladı ya da kesildi ve kare → ses
yazılım gecikmesi (p50/p90). Gölge moddaki kural için "çalsaydı" kaydı da
tutulur; hoparlör susar.

**Teslim kaydı 15 günde bir masaüstüne alınır** (operatör isteği 23.09.2026).
Sistemdeki en eski kayıt 15 günü doldurunca o ana kadarki bütün kayıtlar
masaüstündeki "NextGen Detector uyarı kayıtları" klasörüne
`uyari-kayitlari_<ilk gün>_<son gün>.csv` olarak yazılır (Excel'de açılır:
zaman, kamera, bölüm, uyarı, önem, olay no, kanal, sonuç, gecikme), dosya geri
okunup doğrulanır, sonra sistemden silinir. Dosya yazılamazsa hiçbir kayıt
silinmez ve Olaylar'a "Uyarı kayıtları arşivlenemedi" düşer. Süre ve klasör
Ayarlar → Saklama süreleri'ndedir (`UYARI_KAYDI_ARSIV_GUN`,
`UYARI_KAYDI_ARSIV_KLASORU`); masaüstü olmayan sunucuda ve Docker'da klasör
`veri/arsiv/uyari-kayitlari`'dır. Temizlikten hemen sonra "son 24 saat"
sayıları yeni kayıtlarla yeniden dolar.

### 4.3 Kanal sağlığı ve uyarı garantisi

Analiz çalışırken her açık kanal **10 saniyede bir** yoklanır
(`ANONS_SAGLIK_ARALIGI_SN`, docs/17 §7.4):

| Kanal | Nasıl yoklanır |
|---|---|
| Ses çıkışı (Linux) | Çıkışın adı `pactl` listesinde mi (Bluetooth'ta aynı adres de sayılır). Çalıcı (`paplay`/`aplay`) yoksa "bağlı değil"; çıkış adı boşsa "bilinmiyor" (varsayılan çıkış denetlenemez, R37). |
| Ses çıkışı (Mac) | Varsayılan çıkış kanalın beklediği mi; okunamazsa "bilinmiyor". |
| Ses çıkışı (Windows) | Her zaman **"bilinmiyor"**: varsayılan çıkış ek modül olmadan okunamıyor. |
| IP hoparlör | Adresin sunucusuna ≤3 sn TCP bağlantısı. "Ulaşılabilir", duyuldu demek değildir. |

Kanal satırındaki rozet bu kararı gösterir: **bağlı** (yeşil), **koptu**
(kırmızı), **bilinmiyor** ya da **denetleniyor** (gri). Tek bir yoklamanın
kaçması rozeti değiştirmez: kanal ancak **30 saniye kesintisiz** yanıt vermezse
"koptu" olur (`ANONS_KOPUK_ESIGI_SN`) ve olay listesine bir kez "Ses kanalı
koptu" düşer; iki ardışık yoklamada yanıt verince "Ses kanalı tekrar bağlandı"
düşer ve önceki olay kapanır. Analiz kapalıyken rozet, sayfa açılırken bakılan
anlık durumdur ("açık" / "görünmüyor").

**Uyarı garantisi.** Gölge modda olmayan her ihlalin açılışı en az bir sesli ya
da uzak kanaldan **çalmış** olmalıdır (ses çıkışında çalıcı hatasız bitti, IP
hoparlörde 2xx yanıt; aynı anons az önce o kanaldan çaldığı için bastırıldıysa
da sayılır). Hiçbir kanal çalamadıysa:

- olay listesine **"Uyarı hiçbir sesli kanala ulaşamadı"** düşer (aynı kamera
  için en çok 5 dakikada bir, `ULASMAYAN_UYARI_ARALIGI_SN`; aradakiler sayılıp
  bir sonraki kayda yazılır),
- günlüğe CRITICAL satır yazılır,
- `/saglik` `hazir=false`, `sorunlar=["uyari_ulasmiyor"]` olur; Kontrol Paneli ve
  sistem şeridi kırmızı yazar. Sonraki ulaşan uyarı ya da kanal satırındaki
  başarılı bir **▶ Dene** bunu siler.

Ekran uyarısı bu garantiye **sayılmaz**: izleme penceresinin açık olması,
hoparlörlerin hepsi susmuşken "uyarı ulaştı" demenin gerekçesi olamaz. Olaydan
**önce** de görünür: `/saglik` `uyari_garantisi` "şu an en az bir sesli kanal
bağlı mı" sorusunu `true` / `false` / `null` (doğrulanamıyor, ör. Windows) diye
cevaplar; sistem şeridi `false`'ta kırmızı, `null`'da gri satır gösterir.

**Dürüst sınır.** "Çaldı", sesin kanala teslim edildiğidir; bir insanın duyduğu
değildir. Kopmuş bir Bluetooth sink'e `paplay`'in hata koduyla döndüğü hedef
sunucuda henüz DOĞRULANMADI (docs/17 §7.4); bu yüzden kanal sağlığı ayrıca
yoklanır.

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
| Kanal satırında kırmızı "koptu" | Kanal 30 sn'den uzun süredir yanıt vermiyor; uyarı bölümün öbür kanalından ya da Tüm fabrika'dan duyuruluyor | Açıklamadaki "Son yoklama" sebebine bakın: Bluetooth kapalı, IP hoparlör ağdan düşmüş, container'da ses aracı yok (§4.3) |
| Kanal satırında gri "bilinmiyor" | Durum bu bilgisayarda okunamıyor (Windows'ta her zaman; Linux'ta çıkış listesi okunamadı) | Uyarı yine denenir; sonucu teslim kaydında görünür. Kanal satırındaki **▶ Dene** ile sınayın |
| "Son uyarı hiçbir hoparlöre ulaşmadı" | Bir ihlalin açılışı hiçbir sesli kanaldan çalamadı | Teslim kaydında hangi kanalın neden çalamadığına bakın; düzeltip **▶ Dene**'ye basın |
| "Sesli uyarı yalnız Bluetooth hoparlöre dayanıyor" | Bluetooth dışında bağlı sesli kanal yok (GÖREV §7) | Kablolu bir ses çıkışı ya da IP hoparlör ekleyin (§2.1.1) |
| Kontrol Paneli: "“Tüm fabrika” sesli kanalı yok" | Bölümlü kanal var, yedek yok | Bölümü boş bir kanal ekleyin (§4) |
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
| Hoparlör söz yerine yalnız uyarı tonu çalıyor | Kurala anons mesajı bağlanmamış ya da mesaj kapalı | Kurallar → kuralı düzenle → anons mesajı seç; mesajı Anons sayfasında açın |
| Mesajı olmayan kuralda IP hoparlör çalmıyor | Dosya çalan cihazda `uyari` sesi yok | Cihaza `uyari` adıyla bir uyarı sesi yükleyin ya da kurala anons mesajı seçin |

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
| Kopan Bluetooth hoparlörü programın yeniden bağlaması | Yeniden bağlanma bekçisi yazılmadı (docs/17 §7.5-3, S9): önce hoparlörün kendiliğinden bağlanıp bağlanmadığı sahada görülmeli. Program kopmayı algılar, "koptu" gösterir ve uyarıyı yedek kanala düşürür (§4.3). `07-YOL-HARITASI.md` #22. |
| Bluetooth hoparlörü programın içinden tarama ve eşleştirme | İşletim sisteminin işi; programdan eşleştirmede her sistemde ayrı izin ve diyalog çıkar (docs/17 §7.5, S8). |
| Webhook ile dış sisteme bildirim | Alıcı sistem yok (docs/17 S4); `07-YOL-HARITASI.md` #4. |
| Kanal başına dakika sınırı ve aynı uyarıların birleştirilmesi | Değer verilmedi (docs/17 §7.3-5/6, S23); bugün tekrar bastırma var (§4.2). `07-YOL-HARITASI.md` #23. |
| Sunucuda metinden konuşma, ses dosyası üretme | Ticari kullanılabilir çevrimdışı Türkçe ses yok (docs/16 §3); kayıt insan sesiyle (§2.3). |
