# 06 - Operasyon

> Bu doküman **çalışan sistemi** anlatır. Mimari `docs/09-BASITLESTIRME-KARARLARI.md`
> ile sadeleştirildi: tek program, tek SQLite dosyası, sunucuda tek container. Eski
> PostgreSQL + Alembic + üç servis kurgusu **artık yoktur**.
>
> **İlk aşamada fabrikada sunucu yok** (operatör kararı 24.09.2026): sistem
> fabrikanın Windows bilgisayarında, paketlenmiş uygulamayla çalışır (§1.5).
> §1.2'deki Linux + Docker kurulumu sunucuya geçilirse geçerlidir.

---

## 1. Kurulum

### 1.1 Geliştirme ve deneme bilgisayarı (Mac, Windows)

Fabrikanın bilgisayarına bu kurulum değil, paketlenmiş uygulama kurulur (§1.5).
Burada Docker gerekmez. Kontrol Paneli yeter:

| Mac | Windows |
|---|---|
| `Baslat-Mac.command` → çift tık | `Baslat-Windows.bat` → çift tık |

**İlk Kurulumu Yap** → **Sistemi Başlat**. İzleme ekranı adres çubuğu olmayan bir
pencerede açılır (bu kurulumda Edge, Chrome ya da Brave'in uygulama kipi; paketlenmiş
uygulamada programın kendi penceresi, docs/11), adresi `http://127.0.0.1:8080`. Tespit modeli yoksa sistem ilk açılışta **kendisi indirir**
(internet gerekir); ana sayfadaki "Tespit modeli" satırı "Hazır" olana kadar bekleyin.
Şirket ağında güvenlik duvarı varsa bu ilk indirme için `github.com` ve GitHub'ın dosya
sunucusu `release-assets.githubusercontent.com` açık olmalı: hazır modeller YOLOX'un resmi
yayınından, kayıtlı bir forklift modeli olduğunda o da bu deponun kendi yayınından
(GitHub Release) iner (bugün kayıtlı forklift modeli yok, docs/12 §5; fabrikanın kendi
görüntüsüyle eğitilen model internetten inmez, Forklift sayfasından kurulur, §9).
İkisi de SHA-256 ile doğrulanır; tutmayan dosya kullanılmaz.

Ayrıntı: `NASIL-CALISIR.md`.

### 1.2 Fabrika sunucusu (Linux + Docker; ilk aşamada yok)

```bash
git clone <depo-adresi> DALSAN && cd DALSAN
mkdir -p ayar && cp .env.example ayar/.env
                           # ayar/.env: YONETICI_SIFRESI (ZORUNLU), saklama süreleri,
                           # tespit eşikleri. Uyarı kanalları ekrandan eklenir (docs/14)
bash models/indir.sh       # model ağırlıkları repoda yoktur; indirilen dosya doğrulanır
docker compose up -d
docker compose ps          # tek servis: dalsan - durum "healthy" olmalı
```

Anons bu sunucunun **ses çıkışından** (kablolu amfi ya da Bluetooth hoparlör)
çalacaksa container'a ses yolu açılır; ayrıntı ve ön koşullar docs/14 §2.4:

```bash
sudo chown -R "$(id -u):$(id -g)" veri ayar
docker compose -f docker-compose.yml -f docker-compose.ses.yml up -d
```

Erişim: `http://127.0.0.1:8080` (compose varsayılanı sunucunun kendisine açar).

> **Docker'da ayarlar `ayar/.env` dosyasındadır** ve klasör olarak bağlanır
> (tek dosya bağlandığında ekrandaki Ayarlar sayfası kaydedemiyordu). Eski bir
> Docker kurulumundan geliyorsanız bir kez: `mkdir -p ayar && mv .env ayar/.env`.
> Dosya yoksa sistem açılmaz ve `docker compose logs` bu tarifi yazar.
>
> **Şifre Docker'da zorunludur.** `YONETICI_SIFRESI` boşsa sistem açılmayı
> reddeder: kapsayıcı ağ arayüzlerinin hepsini dinler ve `docker-compose.yml`
> içindeki port satırı `"8080:8080"` yapıldığı anda şifresiz sistem ağa açılır,
> ağdaki herkes kamera silebilir, kural değiştirebilir ve hoparlörden anons
> yaptırabilirdi. Şifre en az 6 karakter olmalıdır. Port satırını açarken
> tarayıcıya yazılacak adresi `IZINLI_SUNUCU_ADLARI` satırına ekleyin (docs/15).
> Ekrandan da ayarlanabilir: **Komuta → Ayarlar → Güvenlik**.

Şema **otomatik** uygulanır: açılışta `backend/sema/*.sql` sırayla çalışır ve
uygulananlar `sema_surumu` tablosuna yazılır. Ayrı migrasyon komutu yoktur.

### 1.2.1 Sunucu yeniden başlayınca sistem kendiliğinden kalkmalı (K8)

Fabrikanın Windows bilgisayarında (ilk aşama) bu işi paketlenmiş uygulamanın
kendisi yapar; bilgisayarda yapılacak ayarlar ve provası §1.5'te.

Docker kurulumunda bu **hazırdır**: `docker-compose.yml` içindeki
`restart: unless-stopped` satırı, sunucu yeniden başladığında container'ı da
başlatır. Tek koşul, Docker servisinin kendisinin açılışta başlamasıdır:

```bash
sudo systemctl enable docker
```

**Provası (atlanmayacak):** sunucuyu gerçekten yeniden başlatın ve sistem
kendiliğinden açılmış mı bakın.

```bash
sudo reboot
# sunucu açıldıktan ~1 dk sonra:
docker compose ps            # durum "healthy" olmalı
curl -fs "http://127.0.0.1:8080/saglik?hazirlik=1"   # "hazir": true
```

**Docker kullanılmıyorsa** (sistem doğrudan Python ile çalışıyorsa) aynı işi
systemd yapar. `/etc/systemd/system/dalsan.service` dosyasını oluşturun -
`<KURULUM-YOLU>` ve `<KULLANICI>` kendi değerlerinizle değişir:

```ini
[Unit]
Description=DALSAN ISG Goruntu Analiz Sistemi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<KULLANICI>
WorkingDirectory=<KURULUM-YOLU>
Environment=DALSAN_HIZMET=1
ExecStart=<KURULUM-YOLU>/.venv/bin/python -m uvicorn app.main:app \
          --host 127.0.0.1 --port 8080 --app-dir backend \
          --timeout-graceful-shutdown 3
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dalsan
sudo systemctl status dalsan      # "active (running)" olmalı
```

`Restart=always`, sistem bir hata yüzünden kapanırsa da 10 saniye içinde
yeniden başlatır - 7x24 çalışmanın gereği. `DALSAN_HIZMET=1` uygulamaya
systemd hizmeti olarak çalıştığını söyler: hata mesajları ve kılavuz o zaman
"Kontrol Paneli'nde Durdur'a basın" yerine "sistemi sunucuda yeniden başlatın"
der (`backend/app/kaynaklar.py` `kurulum_turu`; Docker kendiliğinden tanınır).

**Takılan analiz de yeniden başlar.** Analiz takılırsa (görüntü geliyor ama
90 sn'dir hiçbir kare işlenmiyor) bekçi "Analiz takıldı" olayı yazar ve komuta
ekranlarında kırmızı şerit çıkar. Takılan bir iş parçacığı program içinden
kurtarılamaz; bu yüzden varsayılan tepki (`BEKCI_TEPKISI=yeniden_baslat`,
24.09.2026'dan beri) programı yeniden başlatmaktır: program olayı yazıp kendini
kapatır (çıkış kodu 70), `restart: unless-stopped` ya da `Restart=always`
yeniden açar (systemd'de bunu birimdeki `DALSAN_HIZMET=1` bildirir). Başlat
betiğiyle kurulan masaüstü sisteminde bu işi Kontrol Paneli yapar: sunucu onun
alt sürecidir, 70 koduyla kapanınca panel yeniden başlatır; bir saatte üçten
fazla olursa durur ve günlükte söyler. Paketlenmiş Windows uygulamasında sunucu
Kontrol Paneli'yle aynı süreçtedir; paneli gözetmen yeniden açar (§1.5).
Programı yeniden açan kimse yoksa (elle çalıştırılan sunucu, Mac uygulaması)
program kendini kapatmaz, yalnız uyarır. Her kurulumda yalnız uyarmak için
Ayarlar → Analiz sağlığı → "Takılınca ne yapılsın" → **Yalnız uyar** seçilir
ya da `.env`'e (Docker'da `ayar/.env`)

```
BEKCI_TEPKISI=uyar
```

yazılır: yalnız olay, günlük ve kırmızı şerit.

### 1.2.2 Yedekten geri yükleme provası (K7)

**Prova edilmemiş bir yedek, yedek değildir.** Kurulum tamamlandıktan sonra
bunu bir kez yapın:

1. İzleme ekranının ana sayfasındaki (komuta rafında **Teşhis**)
   **"Veritabanını Yedekle"** düğmesine basın → `veri/yedekler/` altına bir
   `.db` dosyası düşer.
2. Sisteme bir deneme kamerası ekleyin (sonra silinecek).
3. Kontrol Paneli'nde **Durdur**'a basın. *(Geri yükleme sistem çalışırken
   yapılamaz: veritabanı dosyası açıktır ve altından değiştirmek veri kaybıdır.
   Düğme zaten reddeder.)*
4. **"Yedekten Geri Yükle"** → 1. adımdaki dosyayı seçin → onaylayın.
5. **Sistemi Başlat** → deneme kamerasının **kaybolmuş** olması gerekir.

Geri yükleme, mevcut veritabanının bir kopyasını `veri/yedekler/` altına
`geri-yukleme-oncesi-...db` adıyla alır; yanlış yedeği seçtiyseniz aynı
düğmeyle ona dönebilirsiniz.

Docker kurulumunda Kontrol Paneli yoktur; orada geri yükleme elle yapılır:

```bash
docker compose stop
cp veri/dalsan.db veri/yedekler/geri-yukleme-oncesi-$(date +%F_%H-%M).db
cp veri/yedekler/<SECILEN-YEDEK>.db veri/dalsan.db
rm -f veri/dalsan.db-wal veri/dalsan.db-shm   # bayat WAL yeni dosyayı bozar
docker compose start
```

> `-wal` ve `-shm` dosyalarını silmek **şart**: SQLite bunları bulursa eski
> günlüğü yeni veritabanının üstüne uygular.

### 1.2.3 Saat eşitleme (NTP)

Olayın zamanı, kanıt fotoğrafının adı, rapor dilimleri ve saklama süreleri
sunucunun saatine dayanır. Saat kayarsa kanıtın zamanı yanlış olur: "14:02'de
yaya yolunda forklift" kaydı gerçekte 14:07'de olmuş olabilir ve kameranın
kendi kaydıyla (NVR) eşleşmez; hukuki süreçte kanıtın değeri düşer. Sunucu
saati ağdan eşitlenmelidir (docs/17 §9.5):

```bash
timedatectl status          # "System clock synchronized: yes" ve "NTP service: active" görünmeli
sudo timedatectl set-ntp true      # Ubuntu'da hazır gelen systemd-timesyncd'yi açar
```

Fabrika ağından dışarıya NTP çıkışı yoksa yerel NTP sunucusunun adresini bilgi
işlemden alın ve `/etc/systemd/timesyncd.conf` içinde `[Time]` altına
`NTP=<yerel sunucu>` yazıp `sudo systemctl restart systemd-timesyncd` çalıştırın.
chrony kullanan sunucuda denetim `chronyc tracking` ("Leap status : Normal"),
ayar `/etc/chrony/chrony.conf`'tadır.

- Docker container'ı saati host'tan alır; ayrıca ayar gerekmez.
- **Kameraların ve NVR'nin saati de aynı NTP sunucusuna** bağlanmalıdır:
  olay zamanıyla kamera kaydının zamanı ancak böyle eşleşir.
- Yazılım süreleri (kalış, bekleme, bekçi) monotonik saatle ölçer; saatin ileri
  geri alınması bunları bozmaz ve bitiş zamanı başlangıçtan önce yazılmaz
  (`olaylar/yazici.py`). Etkilenen, kayda yazılan duvar saatidir.

### 1.3 Verinin ve ayarların yeri

İki soru birbirinden ayrıdır ve ikisi de `backend/app/kaynaklar.py` içinde,
**tek yerde** çözülür:

| | Depodan çalışırken (bugün) | Paketlenmiş programda |
|---|---|---|
| Kaynak dosyalar (şablon, stil, şema betiği) | depo kökü | paketin içindeki kaynak klasörü (`sys._MEIPASS`; Windows'ta `_internal`) |
| Yazılabilir veri (`veri/`, `models/`, `.env`) | depo kökü | macOS: `~/Library/Application Support/NextGen Detector/` · Windows: `%LOCALAPPDATA%\NextGen Detector\` |

Neden ayrı: paketlenmiş uygulamanın kendisi **salt okunur olabilir** (ör.
Program Files'ta); veritabanı, günlük ve indirilen model bu yüzden oraya yazılmaz.

**Veri asla kendiliğinden taşınmaz.** Paketlenmiş program, kendi yanındaki
klasörde bir `veri/dalsan.db` bulur ve yeni konum boşsa **eski konumu
kullanmaya devam eder**; durumu günlüğe yazar. Sessiz kopyalama yapılsaydı,
yarıda kalan bir taşımada ya da yedeğini eski klasörde arayan kullanıcıda
kayıtlar kaybolmuş sayılırdı.

Paketlenmiş programda `.env` dosyası ilk açılışta `.env.example`'dan **bir kez**
üretilir; sonraki açılışlarda üzerine yazılmaz.

`veri/oturum.anahtar` giriş çerezlerini imzalayan, kuruluma özgü rastgele
sırdır. İlk girişte üretilir ve yalnız sahibi okuyabilir. Kimseyle paylaşmayın.
Silinirse yenisi üretilir ve açık oturumlar bir kez düşer; başka zararı yoktur.

### 1.4 Ağ bölümlendirmesi (KVKK m.12 teknik tedbir)

Kod değil, belgedir; fabrikanın ağ ekibiyle birlikte doldurulur (docs/17 §10.1,
docs/18 §1). İlke: kamera görüntüsü yalnız gerektiği yere gider.

- **Kameralar ayrı bir ağda (VLAN)** durur; ofis ağındaki bir bilgisayar kameraya
  doğrudan bağlanamaz.
- **Sunucu yalnız şunlara erişir:** kamera ağı (RTSP), yönetim ağı (ekranlar ve
  Kontrol Paneli, `IZINLI_SUNUCU_ADLARI`), anons cihazları (IP hoparlör).
- **Dışarıya tek çıkış model indirmedir** (`models/indir.sh`, ilk kurulum). Analiz
  internet istemez; kurulumdan sonra bu çıkış kapatılabilir.
- **Uzaktan erişim** yalnız docs/15'teki yolla (VPN); sunucu internete açılmaz.

| Ağ | Alt ağ / VLAN | Sunucunun erişimi | Not |
|---|---|---|---|
| Kamera ağı | (doldurun) | RTSP 554 | Kameralar ve NVR |
| Yönetim ağı | (doldurun) | 8080 (yalnız izinli adresler) | İSG ekranları |
| Anons | (doldurun) | IP hoparlörün HTTP portu | Yalnız IP hoparlör kullanılıyorsa |
| İnternet | - | Kapalı (kurulumdan sonra) | Model indirme için geçici açılır |

### 1.5 Fabrikanın Windows bilgisayarı (ilk aşama, sunucusuz)

Operatör kararı (24.09.2026): *"bu uygulamayı fabrikanın windows bilgisayarında
çalıştırcm ona göre lütfen bil sunucu olmayacak ilk etapta"*. İlk aşamada sistem
fabrikanın olağan bir Windows bilgisayarında, **paketlenmiş Windows
uygulamasıyla** (`NextGen Detector.exe`; üretimi ve ilk açılışı docs/13 §3,
§3.2) çalışır. Docker, systemd, Python kurulumu ve Başlat betiği yoktur; tespit
işlemcide yapılır (paket yalnız CPU ONNX Runtime içerir). Sunucu donanımı, GPU
ve Docker ile systemd arasındaki seçim sonraki aşamanın açık kararıdır
(docs/17 §16 S1).

**Program siz kapatana kadar açık kalır** (operatör: *"uygulamayı bir kere
açınca ben kapatana kadar otomatik açılmayı ve bu tarz senaryoları düşünüp buna
göre kodla lütfen"*; `masaustu/surekli_calisma.py`, docs/11 §7.1):

| Ne olursa | Program ne yapar |
|---|---|
| Analiz takılır (bekçi), sistem beklenmedik şekilde durur ya da program çöker | Program birkaç saniye içinde yeniden açılır ve sistemi başlatır; bir saatte en çok 3 kez. Sınır dolunca son bir kez açılır ve bu sefer takılırsa kendini kapatmaz, yalnız uyarır: pencere açık kalır ve sorunu gösterir. Bilgisayarı yeniden başlatmak sayacı sıfırlar |
| Elektrik kesilir ya da Windows yeniden başlar (güncelleme dahil) | Windows oturumu açılınca kendiliğinden başlar |
| Bilgisayar boşta kalır | Sistem çalışırken Windows uykuya geçmez. Ekran kapanabilir; uyarı sesi yine çalar. Bilgisayarı elle uyutmak (menüden, kapağı kapatarak) engellenmez |
| Program açıkken yeniden açılır | İkinci kopya açılmaz, açık Kontrol Paneli öne gelir |
| Kontrol Paneli penceresi kapatılır | "Sistem kapatılsın mı?" diye sorar, varsayılan cevap **Hayır**. **Evet** derseniz sistem durur ve Windows açılışında da başlamaz: siz yeniden açana kadar kapalı kalır |
| Windows kapanıyor ya da oturum kapanıyor | Program yeniden açılmaya çalışmaz |

**Durdur** düğmesi yalnız sistemi durdurur: program açık kalır ve bilgisayar
yeniden başlarsa sistem yine kendiliğinden başlar. Tamamen kapatmak için
pencereyi kapatın.

Kontrol Paneli'ndeki **Sürekli çalışma** satırı bunların durumunu söyler; her
şey yolundaysa: "Açık - takılır ya da bilgisayar yeniden başlarsa kendiliğinden
açılır. Bilgisayar uyumuyor." Sarı yazı sorunu ve ne yapılacağını söyler (ör.
program Görev Yöneticisi'nde başlangıçta kapatılmışsa). Panel her açılışta neden (yeniden)
açıldığını günlüğüne yazar (Windows açılışı, bekçi, çıkış koduyla çökme,
sınırın dolması); yeniden açılışların kaydı
`%LOCALAPPDATA%\NextGen Detector\veri\loglar\gozetmen.log` dosyasındadır.

**Bilgisayarda bir kez yapılacaklar** (bunları program yapamaz):

- [ ] **BIOS/UEFI:** elektrik gelince bilgisayar kendiliğinden açılsın. Ayarın
      adı üreticiye göre değişir ("Restore on AC Power Loss", "AC Recovery"
      gibi); değeri **Power On**. Yapılmazsa elektrik kesintisinden sonra
      bilgisayar kapalı kalır, program da açılmaz.
- [ ] **Programa ayrılmış tek bir Windows hesabı.** Veri Windows kullanıcısı
      başınadır (`%LOCALAPPDATA%\NextGen Detector`): program başka bir hesapta
      açılırsa kameraları, kuralları ve kayıtları görmez.
- [ ] **Bu hesapta Windows'un otomatik oturum açması.** Program oturum
      açılınca başlar; otomatik oturum açma yoksa biri oturum açana kadar
      bekler. Oturum kendiliğinden açıldığı için bilgisayarın başına geçen
      herkes bu hesaptadır: bilgisayar **kilitli bir odada** durur.
- [ ] **Sürekli elektrik:** dizüstü bilgisayar fişte kalır.
- [ ] **Windows Update etkin saatleri** ayarlanır. Güncellemenin yeniden
      başlatması yine de sorun değildir: program oturum açılınca geri gelir.
- [ ] **Saat:** Windows'un "Saati otomatik olarak ayarla" (İngilizce
      Windows'ta "Set time automatically") ayarı açık kalır; olayın ve kanıt
      fotoğrafının zamanı bilgisayarın saatine dayanır (§1.2.3).
- [ ] **İlk açılışta internet:** tespit modeli bir kez iner (yaklaşık 20-35 MB;
      §1.1'deki adresler açık olmalı); sonra sistem internetsiz çalışır.
- [ ] **SmartScreen ve virüs koruması:** program imzasız olduğu için uyarabilir,
      kendini Windows açılışına eklemesine de; izin verin (docs/13 §6.3, §6.4).
- [ ] **Görev Yöneticisi > Başlangıç uygulamaları**'nda "NextGen Detector"
      etkin görünür. Orada kapatılırsa program buna dokunmaz, yalnız Kontrol
      Paneli uyarır.

**Ses:** Windows'ta anons bilgisayarın varsayılan ses çıkışına çalar ve bu
kanalın sağlığı okunamaz ("bilinmiyor", gri; docs/14 §2.2.1, docs/17 §7.7):
hoparlörü devreye almada **▶ Dene** ile sahada dinleyerek doğrulayın (§8).

**Yedek:** Teşhis'teki **"Veritabanını Yedekle"** aynı diskteki
`veri\yedekler` klasörüne yazar; disk bozulursa yedek de gider.
`%LOCALAPPDATA%\NextGen Detector\veri` klasörünü ve `.env` dosyasını düzenli
olarak (haftada bir, §4) bir USB diske kopyalayın.

**Güncelleme ve kaldırma:** önce Kontrol Paneli'ni kapatın ve soruya **Evet**
deyin, sonra program klasörünü yenisiyle değiştirin, sonra yeni
`NextGen Detector.exe`'yi açın; Windows açılışı kaydı kendiliğinden yeniden
yazılır (docs/13 §5.2). Kaldırmak için önce kapatın, sonra program klasörünü
silin; kayıtlar `%LOCALAPPDATA%\NextGen Detector` altında kalır.

**Hız:** Windows'ta henüz ölçülmedi. Tek ölçüm 4 çekirdekli, 2.1 GHz Intel
Xeon, GPU'suz bir makinede yapıldı: hızlı model (`yolox_tiny`) 4 kamera × 6
kare/sn'yi bütçenin %100'üyle karşıladı, pay kalmadı (docs/AUDIT-OLCUM.md §1,
docs/ILERLEME.md "Hız ve CPU"). Bundan daha çok çekirdekli bir bilgisayar
seçin ve hızı devreye almada fabrikanın bilgisayarında ölçün: kameralar
bağlıyken **Komuta → Kamera sağlığı**'nda her kameranın "İşlenen fps"i
hedefi (kamera başına 6) tutmalı (§8).

---

## 2. Servis

Tek servis: `dalsan` (FastAPI + arka planda analiz iş parçacığı).

| Özellik | Değer |
|---|---|
| Restart | `unless-stopped` - sunucu yeniden başlarsa sistem kendiliğinden kalkar (K8) |
| Healthcheck | `GET /saglik?hazirlik=1` (30 sn arayla); sistem hazır değilse 503 → "unhealthy" |
| Veri | `./veri` container dışında bağlı - container silinse de kaybolmaz |
| Ayarlar | `./ayar/.env`, dizinle ve yazılabilir bağlanır (Ayarlar sayfası kaydedebilsin diye, R27) |

`/saglik` ucu bilerek ucuzdur: ana sayfa `veri/` klasörünün tamamını tarayıp
boyut hesapladığı için sağlık kontrolünde kullanılmaz. Her durumda 200 ve
`"durum": "calisiyor"` döner (Kontrol Paneli portun bu sisteme ait olduğunu
buna bakarak anlar); yalnız `?hazirlik=1` hazır olmayan sistemde 503 döner.
Docker "unhealthy" container'ı **yeniden başlatmaz** - bu yalnız görünürlüktür;
takılan analizi varsayılan `BEKCI_TEPKISI=yeniden_baslat` ile bekçi kapatır ve
Docker, systemd, Kontrol Paneli ya da Windows uygulamasının gözetmeni yeniden
açar (§1.2.1, §1.5); `uyar` seçiliyse ya da yeniden açan yoksa yalnız uyarır.

Şifresiz gövde yalnız `durum`, `analiz`, `model`, `hazir`, `uyari_garantisi` ve
`sorunlar` kodlarını verir. Kamera başına okunan/işlenen hız, işleme süresi
(p50/p90), son karenin yaşı, boş disk, analiz turunun yaşı, uyarı gecikmesi ve
kanalların adı/türü/sağlığı (`kanallar`) `?ayrinti=1` ile ve oturum açıkken gelir
(şifre tanımlı değilse oturum gerekmez).

`uyari_garantisi` (docs/17 §7.4): şu an en az bir sesli/uzak kanal (ses çıkışı ya
da IP hoparlör) bağlı mı. `true` bağlı · `false` kanal yok ya da hepsi koptu ·
`null` doğrulanamıyor (bir kanalın durumu okunamıyor, ör. Windows'ta her zaman;
ya da analiz kapalı). Ekran kanalı sayılmaz: izleme penceresinin açık olması
"uyarı duyuluyor" demek değildir. Kontrol Paneli `false`'ta kırmızı, `null`'da
gri satır gösterir.

| `sorunlar` kodu | Anlamı | `hazir`'ı bozar |
|---|---|---|
| `analiz_takildi` | Görüntü geliyor ama analiz ilerlemiyor (bekçi) | evet |
| `analiz_olu` | Analiz iş parçacığı çalışmıyor | evet |
| `model_yuklenemedi` | Tespit modeli yüklenemedi | evet |
| `model_yedekte` | Seçili forklift modeli inmedi ya da açılamadı; sistem tabanındaki hazır modelle çalışıyor: insan ve araç tespiti sürer, forklift ayrı sınıf olarak tanınmaz (`MODEL_FALLBACK` yazıldı) | hayır |
| `veritabani_acilamadi` | Sağlık denetimi veritabanını okuyamadı | evet |
| `olay_yazilamadi` | Son ihlal kayda geçmedi (anons yine çaldı) | evet |
| `uyari_ulasmiyor` | Son uyarı hiçbir sesli/uzak kanala ulaşmadı (`ALERT_UNDELIVERED` yazıldı); sonraki ulaşan uyarı ya da başarılı bir kanal denemesi siler | evet |
| `kritik_kural_pasif` | Mesafe ya da hız kuralı kalibrasyon bekliyor, çalışmıyor | hayır (ekranda kırmızı) |
| `sesli_kanal_yok` | Açık sesli kanal yok: uyarılar hoparlörden duyulmaz | hayır (ekranda kırmızı) |
| `tek_kanal_bluetooth` | Sesli uyarı yalnız Bluetooth hoparlöre dayanıyor (GÖREV §7); Bluetooth dışında bağlı kanal yok | hayır (ekranda kırmızı) |
| `yedek_ses_kanali_yok` | Bölümlü kanal var ama "Tüm fabrika" kanalı yok: kanalı olmayan ya da kanalı kopan bölüm susar | hayır (Kontrol Paneli sarı) |
| `ort_paket_cakismasi` | İki ONNX Runtime paketi birlikte kurulu; GPU sessizce kaybolabilir | hayır |

---

## 3. Güncelleme

```bash
git pull
bash models/indir.sh      # yeni sürümün getirdiği model dosyaları (var olanlar atlanır)
docker compose build
docker compose up -d
docker compose logs -f --tail=100
```

Şema değişikliği varsa açılışta kendiliğinden uygulanır. `models/indir.sh` imaja
girecek modelleri sunucuda indirir; Ayarlar'da seçilebilen her model (kayıtlı
forklift modeli dahil) böylece imajın içinde olur. Container'ın kendi indirdiği
model imaj yeniden kurulunca kaybolur ve yeniden iner (internet gerekir).
Forklift modeli isteğe bağlıdır: kayıtlı olduğunda inmezse betik uyarı yazıp
öteki modellerle biter (bugün kayıtlı forklift modeli yok, docs/12 §5).

> **23.09.2026 sürümüne geçerken bir kez:** ayar dosyası artık `ayar/.env`
> olarak bağlanıyor ve Docker'da şifre zorunlu. `docker compose up -d`'den önce
> `mkdir -p ayar && mv .env ayar/.env` yapın ve `YONETICI_SIFRESI`'nin dolu
> olduğunu kontrol edin; yoksa sistem açılmaz ve sebebini günlüğe yazar.
>
> Aynı sürümde oturum çerezleri kuruluma özgü bir sırla imzalanmaya başladı
> (R16): güncellemeden sonra herkes **bir kez** yeniden giriş yapar.

**systemd kurulumunda** (Docker'sız, §1.2.1) aynı iş:

```bash
git pull
.venv/bin/python -m pip install -r backend/requirements.txt
bash models/indir.sh      # isteğe bağlı: sistem eksik modeli açılışta kendisi indirir
sudo systemctl restart dalsan
journalctl -u dalsan -f   # ya da: tail -f veri/loglar/sistem.log
```

Masaüstü kurulumunda (Başlat betikleri) güncelleme Kontrol Paneli'nin
**Güncelle** düğmesiyledir (docs/13 §5.1); düğme önce veritabanını yedekler.

Paketlenmiş uygulamada (fabrikanın Windows bilgisayarı, §1.5) önce Kontrol
Paneli kapatılır ve soruya **Evet** denir, sonra program klasörü yenisiyle
değiştirilir, sonra yeni program açılır (docs/13 §5.2).

Geri alma:
`git checkout <önceki-sürüm>` → `docker compose build` → `up -d`
(systemd'de `git checkout <önceki-sürüm>` → `sudo systemctl restart dalsan`).

> Şema betikleri **geri alınamaz** (Alembic yoktur - `docs/09` kararı). Geri
> dönüş yolu yedektir: sürüm yükseltmeden ÖNCE `veri/` klasörünü kopyalayın.

---

## 4. Yedekleme

**Tam yedek = `veri/` klasörünü ve ayar dosyasını kopyalamak.** Hepsi bu.
Ayar dosyası Docker kurulumunda `ayar/.env`, Başlat betikleriyle kurulan
Kontrol Paneli kurulumunda proje kökündeki `.env`'dir; paketlenmiş uygulamada
`veri/` ve `.env` docs/13 §4'teki kullanıcı klasöründedir.

```bash
mkdir -p       /yedek/dalsan-$(date +%Y-%m-%d)       # önce klasör: yoksa veri/ içeriği klasörsüz kopyalanır
cp -R veri/    /yedek/dalsan-$(date +%Y-%m-%d)/
cp ayar/.env   /yedek/dalsan-$(date +%Y-%m-%d)/     # Docker; panelde: cp .env
```

Sistem çalışırken güvenli veritabanı kopyası için: ana sayfadaki
**"Veritabanını Yedekle"** düğmesi (`veri/yedekler/` içine SQLite backup API ile
yazar, WAL uyumludur). Fotoğrafları kapsamaz - haftalık tam yedeği ihmal etmeyin.

Forklift sayfasından kurulan model (`models/nextgen_forklift_*_yerel_*`) `veri/`'de değil
`models/` klasöründedir ve bu yedeğe girmez: eğitimin `KURULACAK` klasöründeki iki
dosyayı saklayın, yeni kurulumda aynı sayfadan yeniden kurulur (§9).

**Geri yükleme provası - devreye almadan önce zorunlu (K7):**

```bash
docker compose down
mv veri veri-eski && cp -R /yedek/dalsan-YYYY-AA-GG/veri veri
docker compose up -d          # olaylar ve fotoğraflar yerinde mi, ekrandan bakın
```

Test edilmemiş yedek yedek sayılmaz. 7. haftada bir kez tam prova yapılır ve
sonucu kabul tutanağına yazılır.

---

## 5. Retention (saklama süreleri)

Bakım, analiz süreci içinde **uygulama açıldıktan hemen sonra bir kez** ve sonra
her 24 saatlik çalışma süresinde bir çalışır. Ayrı zamanlanmış görev yoktur.

| Veri | Ayar | Varsayılan | Not |
|---|---|---|---|
| İhlal olayları (DB) | `OLAY_SAKLAMA_GUN` | 180 gün | KVKK politikasıyla uyumlu olmalı |
| Kanıt fotoğrafları | `GORUNTU_SAKLAMA_GUN` | 90 gün | Disk büyümesinin ana kalemi |
| Etiketlenmemiş KKD kırpıkları | `KKD_HAM_VERI_SAKLAMA_GUN` | 30 gün | **Etiketlenenler silinmez** - eğitim veri setidir |
| Etiketlenmemiş forklift kareleri | `FORKLIFT_HAM_VERI_SAKLAMA_GUN` | 30 gün | **Etiketlenenler silinmez** - eğitim veri setidir; Forklift sayfasından silinir (§9) |
| Sistem olayları | `SISTEM_OLAY_SAKLAMA_GUN` | 90 gün | |
| Uyarı teslim kaydı | `UYARI_KAYDI_ARSIV_GUN` | 15 gün | Silinmeden önce masaüstüne CSV (aşağıda); 0 = kapalı, kayıt olayla gider |

Bu süreler, disk uyarı sınırı, anons (hoparlör) ayarları ve tespit eşikleri
**arayüzden** de değiştirilebilir: soldaki raftan **Sistem ayarları** (`/ayarlar`);
hoparlör adresleri ise Anons sistemi ekranındaki kanal listesindedir. Sayfa
`.env` dosyasını açıklama satırlarını bozmadan günceller ve değeri yazmadan
önce açılıştaki doğrulayıcıdan geçirir - geçersiz bir ayar dosyaya yazılmaz.
**Değişiklik, sistem yeniden başlatılınca geçerli olur.**

Fotoğrafı silinen olayın kaydı korunur, yalnızca fotoğraf bağlantısı temizlenir
(olay ekranında kırık resim çıkmaz).

**Dondurulan olay silinmez.** Hukuki süreçte gereken olay, olay sayfasındaki
**Dondur** ile (sebep zorunlu) saklama temizliğinden çıkarılır: olay, kanıt
fotoğrafı ve uyarı teslim kaydı kalır; dondurma kaldırılınca bir sonraki bakımda
süresi dolmuşsa silinir (docs/18 §3).

**Uyarı kayıtları önce masaüstüne yazılır, sonra silinir** (operatör isteği
23.09.2026). Sistemdeki en eski teslim kaydı `UYARI_KAYDI_ARSIV_GUN` günü
(15) doldurunca o ana kadarki kayıtlar "NextGen Detector uyarı kayıtları"
klasörüne CSV olarak yazılır ve geri okunup doğrulanır; ancak ondan sonra
silinir. Masaüstü yoksa (Docker, masaüstüsüz sunucu) klasör
`veri/arsiv/uyari-kayitlari`'dır; Docker'da bu, sunucudaki bağlı `veri/`
klasörünün içidir. Dosya yazılamazsa hiçbir kayıt silinmez, Olaylar'a
"Uyarı kayıtları arşivlenemedi" düşer ve bakım ertesi gün yeniden dener.
Dondurulan olayın teslim kaydı arşive de girmez, silinmez de. Masaüstündeki
kopyalar sistemin saklama süresine tabi değildir; ne kadar tutulacağına
müşterinin KVKK politikası karar verir (docs/18).

**Her bakım koşusu imha kaydı yazar** (silinen olay, fotoğraf, KKD örneği, forklift karesi,
dondurulduğu için atlanan olay, arşivlenip silinen uyarı kaydı ve dosyası,
o günkü gün sayıları). Kayıt ve erişim izi
Ayarlar sayfasının en altındaki "KVKK: erişim ve imha kayıtları" bölümündedir;
ikisi de silinmez (docs/18 §2, §4).

Boş disk `DISK_UYARI_GB` altına inince Olaylar listesine `Sistem` tipi bir uyarı
düşer. **DALSAN'ın KVKK saklama politikasıyla uyum 1. haftada teyit edilir** -
sistem politikayı teknik olarak zorlar, politikayı belirlemez.

---

## 6. Log okuma

Günlük dosyası: `veri/loglar/sistem.log` (5 MB'ta döner, son 3 kopya saklanır).
Windows ve Mac uygulamasında bu klasör kullanıcı klasöründedir (docs/13 §4);
hata mesajları dosyanın yerini kuruluma göre söyler.
Kontrol Paneli aynı kayıtları penceresinde okunur biçimde gösterir: "saat
[HATA] mesaj" (hata), "saat [!] mesaj" (uyarı), işaretsiz satır bilgidir;
`ayrinti` alanı yalnız dosyadadır.

```bash
tail -f veri/loglar/sistem.log
grep '"level": "ERROR"' veri/loglar/sistem.log
grep '"bilesen": "kamera"' veri/loglar/sistem.log
docker compose logs -f            # Docker kurulumunda
```

Biçim: her satır tek bir JSON nesnesi - `ts, level, bilesen, mesaj`; teknik
ayrıntı (dosya yolu, hata izi) varsa dosyada `ayrinti` alanı da bulunur.
Sorun bildirirken `ERROR` satırlarını (panelde `[HATA]` ile başlayanları)
**olduğu gibi** kopyalayın.

Web sunucusunun (uvicorn) satırları da aynı biçimde ve aynı dosyadadır:
`"bilesen": "uvicorn.error"` sunucunun açılışı, kapanışı ve beklenmeyen
hataları; `"bilesen": "uvicorn.access"` HTTP istekleri. Erişim satırlarından
yalnız **değiştiren** istekler (kural, kamera, bölge kaydı: POST/PUT/DELETE) ve
hata yanıtları (4xx/5xx) yazılır. Başarılı sayfa ve yoklama istekleri yazılmaz:
Kontrol Paneli 1,5 sn'de bir sağlık ucunu yoklar, hepsi yazılsaydı dönen günlük
önemli satırları iki günde dışarı iterdi.

```bash
grep '"bilesen": "uvicorn' veri/loglar/sistem.log
```

**Beklenen tek `ERROR` satırı:** sistem durdurulurken bir tarayıcıda Olaylar ya
da komuta ekranı açıksa uvicorn `Cancel 1 running task(s), timeout graceful
shutdown exceeded` yazar. Ekranın canlı akışı kendiliğinden bitmez; kapanış
onu 3 sn bekleyip keser (başlatma komutlarındaki `--timeout-graceful-shutdown 3`),
sayfa da kendiliğinden yeniden bağlanır. Bu süre olmasaydı kapanış hiç bitmez,
Kontrol Paneli süreci zorla kapatırdı. Hemen ardından Olaylar'da "Sistem durdu"
görünmelidir.

---

## 7. Sorun giderme

Aşağıda "yeniden başlatın" kurulum türüne göre şudur: masaüstünde Kontrol
Paneli'nde **Durdur**, sonra **Sistemi Başlat**; Docker'da `docker compose
restart`; systemd'de `sudo systemctl restart dalsan`.

| Belirti | Bakılacak yer |
|---|---|
| Kamera "bağlanıyor"da kalıyor | Kamera sayfasındaki durum satırı sebebi yazar (ulaşılamıyor / şifre / dosya yok). İlk bağlantı 30 sn sürebilir |
| Kamera "çevrimdışı" | Aynı durum satırı + `veri/loglar/sistem.log` içinde `"bilesen": "kamera"`; NVR eşzamanlı bağlantı limiti sık sebeptir |
| "Tespit modeli: Yüklenemedi" | İnternet yoksa `bash models/indir.sh` ile elle indirin; dosya bozuksa silip tekrar indirin |
| Kutular çıkmıyor / nesne kaçıyor | `.env` içinde `TESPIT_GUVEN_ESIGI` ve `TESPIT_INSAN_GUVEN_ESIGI` değerlerini kademeli düşürün (0,05'lik adımlarla). Uzak nesnede `TESPIT_EN_KUCUK_KENAR_PX` düşürülür |
| Çok fazla yanlış tespit | Aynı eşikleri yükseltin; **NextGen AI İsabetli** daha isabetlidir (daha yavaş): Ayarlar → "Tanıma modeli"nden seçip yeniden başlatın |
| Ana sayfada "Forklift modeli" satırı "… kullanılamadığı için sistem … ile çalışıyor" diyor; Olaylar'da "Seçili model yerine hazır model çalışıyor" | Seçili forklift modeli inmedi (genelde internet) ya da açılamadı. Sistem durmadı: tabanındaki hazır modelle insan ve araç tespiti sürüyor, yalnız "Forklift" seçili kurallar uyarı vermiyor. Satır sebebi yazar; sebebi giderip yeniden başlatın. Seçim değişmez: her açılışta önce forklift modeli denenir. Fabrika eğitimi modelinde satır "dosyası bulunamadı" derse dosya silinmiş ya da taşınmıştır (Docker'da imaj yeniden kurulunca, §9): Forklift sayfasında aynı iki dosyayla yeniden kurun. `/saglik` bu sırada `model_yedekte` der (§2) |
| "Tespit modeli: ... yayın yerinde bulunamadı" | İnternet çalışıyor, model dosyası yayında yok: Ayarlar → "Tanıma modeli"nden başka model seçip yeniden başlatın, destek ekibine haber verin |
| Forklift modeline geçince bazı kurallar forklifte tepki vermiyor | Kurulum listesindeki "Araç kuralları tanıma modeline uyuyor mu?" adımı kuralları kamera, bölge ve türüyle söyler: yalnız "Tır/Araç" seçili kurallarda "Forklift"i de işaretleyin (tır park alanının bölge kuralı bilerek yalnız tırdır). Forkliftsiz modele dönünce yalnız "Forklift" seçili kurallar aynı adımda görünür. Kapalı kameranın kuralı sayılmaz |
| Forklift sayfasına yeni kare düşmüyor | "Kare toplama" **KAPALI** olabilir (varsayılan); KVKK dayanağından sonra açılır (§9). Açıksa: "Sınır doldu" yazıyorsa toplam sınıra (`FORKLIFT_ORNEK_EN_COK`, 3000) varıldı, kareleri etiketleyip eğitim verisini indirin ya da silin. Kamera başına saatte en çok `FORKLIFT_ORNEK_SAAT_LIMIT` (12) araçlı kare, araçsız kare bunun altıda biri saklanır; analiz açık olmalı |
| Forklift sayfasında "Model ölçüm kapılarından geçmedi; program onu kurmaz. Kalan: …" | Eğitimin adayı kapılardan geçmedi. `SONUC.txt`'deki önerilere bakın (çoğu zaman daha çok ve daha çeşitli etiketli kare); kapılar değiştirilmez (docs/17 §12.3-8) |
| Eğitim penceresi "Python 3.12 bulunamadi" ya da "Durdu, cikis kodu …" | Python 3.12'yi python.org'dan kurun. Kod 1: internet kesildi ya da bir adım yarıda kaldı; aynı zip'i yeniden bırakın, biten adımlar atlanır. Kod 2: iletideki adımı yapın (ör. çalışma klasörünün yolunda Türkçe karakter, boş disk). Ayrıntı `C:\NextGen-Forklift\gunluk.txt` |
| Olay üretilmiyor | Kural açık mı; bölge doğru tipte mi; mesafe kuralında kalibrasyon var mı (Kurallar sayfasındaki rozet söyler) |
| KKD sayfasına yeni örnek düşmüyor | Sayfanın üstündeki "Veri toplama" kapısı **KAPALI** olabilir (varsayılan). Rev.02 onayından sonra açılır; kapalıyken kişi görüntüsü bilerek toplanmaz. Açıksa: kişi KKD zorunlu alanda mı, muaf alanın dışında mı, kural boyundan (`min_person_height_px`) uzun mu |
| KKD hiç olay üretmiyor | Model henüz eğitilmedi - bu **beklenen** davranıştır (docs/04). KKD sekmesinin üstündeki "KKD modeli" kartı durumu yazar; veri toplanıyor mu da orada |
| KKD sekmesinde "KKD modeli yüklenmedi" | Model dosyası `models/SHA256SUMS`'taki özetle tutmuyor ya da özet satırı yok, açılamıyor veya sözleşmeye uymuyor (docs/04 §6.6). Kartta sebep yazar; modeli veren uzmandan doğru dosyayı ve özet satırını isteyin, sonra yeniden başlatın. Bu sırada diğer kurallar çalışır |
| KKD çok fazla yanlış alarm | `04-KKD-BARET-YELEK.md` §8.3 tablosu; kabindeki sürücü için kuralın "sürücüyü değerlendirme" kutusu, üst üste kişi ve bulanıklık için kural formundaki iki eşik (docs/03 §3) |
| Olaylar'da "KKD modeli değişti … gölge moda alındı" | Yüklü KKD modeli, anonsu açılırken onaylanan sürüm değil (ya da hiç onaylanmamış). Beklenen güvenlik davranışı: olaylar kaydedilir, hoparlör susar. Yeni sürüm gölgede incelenip ölçüldükten sonra anons Komuta → Uyarı zinciri'nden yeniden açılır |
| Uyarı zincirinde KKD satırının "Anonsu aç" düğmesi gri, "Anons kapısı kapalı" | Kapının şartlarından biri eksik; satır hangisi olduğunu yazar, ayrıntı KKD sayfasındaki "Gölge karnesi"nde. Çoğunlukla incelenmemiş olay kalmıştır: Komuta → İnceleme'de o KKD olaylarını işaretleyin. Eşikler Ayarlar → KKD anons kapısı. Ölçmeden açmak mümkündür ("ölçülmeden açıyorum" kutusu) ama karar Olaylar'a "KKD anonsu ölçülmeden açıldı" olarak yazılır |
| Rapor'daki bir satırda yanlış alarm oranı yanında "(kapsama %40)" | O satırdaki olayların yalnız %40'ı işaretli: oran bu kısımdan hesaplandı ve satırı temsil etmeyebilir. Komuta → İnceleme'de kalanları işaretleyin. Baret ve yelek oranları "Olay koduna göre" tablosunda ayrı satırdadır |
| Rapor'da yanlış alarm / saat "ölçülemedi" ya da kapsama düşük | O kameranın bazı günlerinde işaretlenmemiş ihlal var. Komuta → İnceleme'de o günlerin olaylarını "İncelendi" ya da "Yanlış alarm" diye işaretleyin: oran yalnız bütün ihlalleri işaretli günlerden hesaplanır. "Analiz edilen: -" ise o dönemde analiz kaydı yok (model yüklenmemiş, kamera kopuk ya da dönem bu kayıt başlamadan önce) |
| Uyarılar gecikiyor | Kamera `sample_fps` değerini düşürün; substream kullanın; `CIKARIM_CIHAZI=cuda` (yalnız NVIDIA'lı Linux) |
| "CIKARIM_CIHAZI=cuda seçili ama … sistem CPU ile çalışıyor" | Ana sayfada uyarı olarak görünür: NVIDIA sürücüsü + `onnxruntime-gpu` gerekir, ya da `.env`'de `cpu` yapın |
| Anons çalmıyor | **Anons** sayfası → "Anonsu Dene". Sonuç satırı sebebi yazar (ses dosyası yok / adres yanlış / komut bulunamadı) |
| Ekranda uyarı sesi gelmiyor | Sağ alttaki ses çipi sebebini yazar: "KAPALI" ise tıklayın (ses bu tarayıcıda açılır); "beklemede" ise sayfaya bir kez tıklayın (tarayıcı kuralı: ses ancak bir tıklamadan sonra çalar); "çalışmıyor" ise tarayıcı ses çalamıyor - başka bir tarayıcı deneyin. Çip yoksa ekran sesi çalışıyordur |
| Komuta ekranının üstünde kırmızı şerit | Uyarı üretilmiyor ya da kaydedilmiyor (analiz takıldı, model yüklenemedi…), kritik bir kural çalışmıyor, bir kameradan görüntü gelmiyor ya da sesli uyarı hoparlöre ulaşmıyor (sesli kanal yok, kanallar koptu, yalnız Bluetooth); şerit hangisi olduğunu yazar, "Ayrıntı →" Sağlık ekranını açar. Gri şerit: durum doğrulanamıyor (sunucuya ulaşılamıyor, model yükleniyor ya da sesli uyarının ulaştığı doğrulanamıyor) |
| Disk doluyor | Ana sayfadaki "Boş alan"; saklama sürelerini kısaltın; `veri/goruntuler` en büyük kalemdir |
| Herkes aynı anda oturumdan düştü | Şifre değişti, sistem yeni sürüme güncellendi ya da `veri/oturum.anahtar` silindi veya bozuldu (yenisi üretilir; bozulduysa günlükte uyarı). Yeniden giriş yapmak yeter |
| Kamera ya da hoparlör formunda adres `••••@` ile görünüyor | Beklenen: kullanıcı adı ve şifre sayfaya basılmaz. •••• olduğu gibi bırakılırsa kayıtlı şifre korunur, ip ya da yol değişse de. Değiştirmek için •••• yerine `kullanici:sifre` yazın |
| Canlı uyarı paneli "bağlantı koptu" | Sunucu durmuş olabilir; yeniden başlatın |
| Olaylar'da "Analiz takıldı" ya da "Analiz durdu" | Görüntü geliyor ama analiz ilerlemiyor: o sürede **hiçbir uyarı üretilmiyor**. Varsayılan ayarda (`BEKCI_TEPKISI=yeniden_baslat`) program kendini kapatır ve Docker, systemd, Kontrol Paneli ya da Windows uygulamasının gözetmeni onu yeniden açar (§1.2.1, §1.5). Yeniden açan yoksa (Mac uygulaması, elle çalıştırılan sunucu) ya da "Yalnız uyar" seçiliyse sistemi yeniden başlatın. `veri/loglar/sistem.log` içinde `"bilesen": "bekci"` satırından önceki hatalara bakın |
| Olaylar'da "Analiz yavaşladı" | Ya kamerada kare üst üste işlenemedi (hattı yeniden kuruldu; günlükte "Kare işlenemedi" satırları sebebi yazar) ya da işlenen görüntü hızı hedefin altında kaldı: kamera `sample_fps`'ini düşürün, kamera sayısını azaltın ya da daha güçlü donanım kullanın. Eşikler Ayarlar → Analiz sağlığı |
| Olaylar'da "Sistem başladı - önceki çalışma düzgün kapanmamıştı" | Sistem "Sistem durdu" yazamadan kapandı: elektrik kesintisi, bilgisayarın kapatılması, görev yöneticisinden sonlandırma ya da çökme. O sırada açık kalan olaylar "Sistem yeniden başladı; olay açık kalmıştı" sebebiyle kapatılmıştır. Sık görülüyorsa `veri/loglar/sistem.log`'un kapanıştan önceki son satırlarına bakın |

---

## 8. Devreye alma kontrol listesi (8. hafta)

- [ ] Sistem, sunucu (ilk aşamada fabrikanın Windows bilgisayarı) yeniden başlatma sonrası kendiliğinden ayakta (K8)
- [ ] Windows bilgisayarında (ilk aşama, §1.5): bilgisayarın fişi çekildi ve geri takıldı;
      bilgisayar kendiliğinden açıldı, Windows oturumu kendiliğinden açıldı ve program
      geri geldi (sistem çalışıyor); Olaylar'da "Sistem başladı - önceki çalışma
      düzgün kapanmamıştı"
- [ ] Windows bilgisayarında Görev Yöneticisi > Başlangıç uygulamaları'nda "NextGen
      Detector" etkin
- [ ] Windows bilgisayarında Kontrol Paneli'nin "Sürekli çalışma" satırı "Açık - …"
      diyor
- [ ] Sunucu saati NTP ile eşitleniyor (`timedatectl`: "synchronized: yes"; Windows bilgisayarında "Saati otomatik olarak ayarla" açık, §1.5); kameralar ve NVR aynı NTP'de (§1.2.3)
- [ ] 3-4 kameranın tamamı ≥ 24 saat kesintisiz `çevrimiçi` (K1)
- [ ] Bir kameranın kablosu çekildi: ~10 sn içinde kamera "çevrimdışı" ve Olaylar'da
      "Kamera çevrimdışı"; takılınca birkaç saniye sonra "Kamera tekrar çevrimiçi"
      (`KAMERA_KOPUK_ESIGI_SN`, `KAMERA_UP_KARARLILIK_SN`)
- [ ] Bölge ve kurallar arayüzden değiştirilebiliyor, restart gerekmiyor (K3)
- [ ] Bölgeler sahadaki yere oturuyor: her kamerada canlı önizlemede bölge çizgileri
      yerdeki işaretlerle (yaya yolu, yasak alan, geçit) çakışıyor; bir kişi bölge
      sınırında yürüdü ve olay doğru bölgede açıldı
- [ ] Mesafe ya da hız kuralı olan her kamera kalibre edildi: kurulum listesinde
      "Kalibrasyon bekleniyor" yok. Kalibrasyonun kontrol ölçümü yalnız docs/17 S7
      cevabı "evet" ise yapılır
- [ ] Test ihlali ≤ 2 sn içinde ekrana düşüyor (K4)
- [ ] Olay kaydı + kanıt fotoğrafı doğru, filtre çalışıyor (K5)
- [ ] Anons: **Anons sayfasından denendi**, çalışıyor veya "altyapı uygun değil" olarak yazılı kayıt altında (K6)
- [ ] Her bölümde test anonsu duyuldu: Anons sistemi → her kanal satırında **▶ Dene**, sahada bir kişi dinledi; Teslim kaydında "çaldı"
- [ ] Kuralların anons mesajlarına ses dosyası bağlandı: Anons sayfasında "ses dosyası
      yok" rozeti kalmadı (bağlanmayan mesajda hoparlör sözlü anons yerine yalnız uyarı
      tonu çalar, docs/14 §2.3); her mesaj **Anonsu Dene** ile sahada dinlendi
- [ ] Her kurala anons mesajı seçildi: Uyarı zincirinde "mesaj yok - uyarı tonu çalar"
      satırı kalmadı (mesajsız kural hoparlörü susturmaz ama kimin ne yapacağını söylemez)
- [ ] Forklift tanıyan model seçildiyse kurulum listesinde "Araç kuralları tanıma modeline
      uyuyor mu?" adımı kalmadı; o model varsayılan yapılmadan önce saha ölçümü (forklift
      AP50 ≥ 0,90, aşağıdaki doğruluk maddesi) tutanakta (docs/17 §12.3-8)
- [ ] Sesli kanalların hepsi Bluetooth değil (kurulum listesinde "Sesli anons" adımı yeşil; GÖREV §7)
- [ ] Bluetooth hoparlör kapatıldı: ~30-40 sn içinde rozet "koptu", Olaylar'da "Ses kanalı koptu"; bu sırada üretilen test ihlali "Tüm fabrika" kanalından **duyuldu**; hoparlör açılınca "tekrar bağlandı" (kendiliğinden bağlanmadıysa bu tutanağa yazıldı, docs/14 §2.1.1)
- [ ] Hoparlör gecikmesi telefon videosuyla ölçüldü ve tutanağa yazıldı (§8.1)
- [ ] Bütün sesli kanallar kapatıldı ve test ihlali üretildi: izleme ekranı açıkken
      bile sistem şeridinde ve Kontrol Paneli'nde kırmızı "Son uyarı hiçbir hoparlöre
      ulaşmadı", Olaylar'da "Uyarı hiçbir sesli kanala ulaşamadı"; kanallar açılıp
      bir kanalda **▶ Dene** çalınca kırmızı kalktı
- [ ] Yedek alındı, **geri yükleme prova edildi** (K7)
- [ ] KKD gölge modda ≥ 3 gün çalıştı, precision ölçüldü, eşikler ayarlandı (K10, K11)
- [ ] KKD anonsu ancak precision kabul edildikten **sonra** açıldı: KKD sayfasındaki
      gölge karnesinde baret ve yelek için "kapı açık"; Olaylar'da "KKD anonsu
      ölçülmeden açıldı" kaydı yok (varsa gerekçesi tutanağa yazıldı)
- [ ] Hedef donanımda hız ölçüldü: `.venv/bin/python -m tests.hiz_kiyas` (KKD modeli
      konduysa `--kkd` turu da); kamera başına en az 6 kare/sn (docs/17 §14) ve
      `/saglik?ayrinti=1` içinde her kameranın `islenen_fps`'i; komut ve ham çıktı
      tutanağa (docs/AUDIT-OLCUM). Paketlenmiş uygulamada `.venv` yoktur: fabrikanın
      Windows bilgisayarında ölçü `islenen_fps` ve Komuta → Kamera sağlığı'ndaki
      "İşlenen fps"tir (§1.5)
- [ ] Tespit doğruluğu KVKK dayanaklı etiketli saha karelerinde ölçüldü: `.venv/bin/python -m tests.dogruluk_kiyas --klasor veri/dogruluk --json dogruluk.json` (insan recall ≥ 0,95; tır ve forklift AP50 ≥ 0,90; kare ve kutu sayısıyla tutanağa, docs/17 §14). Kareler `veri/` altında kalır, depoya girmez
- [ ] Yanlış alarm hedefi ölçüldü: Komuta → Rapor'da her kamera için incelemesi tam günlerden hesaplanan yanlış alarm / saat, hedefin (saatte en çok 2) altında (`17-V2-TASARIM.md` §14)
- [ ] Bakım (retention) çalıştığı günlükten doğrulandı, KVKK süreleriyle uyumlu
- [ ] Uzun süreli çalışma provası yapıldı; süre operatörle belirlenir (docs/17 §13
      5e). Sonunda Rapor'daki analiz edilen saat ile Olaylar'daki "Analiz takıldı",
      "Analiz yavaşladı", "Kamera çevrimdışı" ve "Sistem durdu" sayıları tutanağa
      yazıldı
- [ ] **Giriş şifresi geri eklendi** (`docs/07` #0) - ağa açık kurulumda zorunlu
- [ ] Kullanım dokümanı teslim edildi, kullanıcı eğitimi yapıldı (K9)
- [ ] Her açık kameranın görüş alanında mahremiyet alanı olmadığı kamera sayfasında onaylandı (kurulum listesi adım 9)
- [ ] Ağ bölümlendirmesi tablosu ağ ekibiyle dolduruldu (§1.4)
- [ ] KVKK uyum kartı (docs/18) avukatla gözden geçirildi; aydınlatma metni ve levha asıldı
- [ ] Kabul tutanağı: K1-K11 madde madde işaretlendi

### 8.1 Uyarı gecikmesini ölçmek (telefon videosu)

Yazılımın payı ekranda ölçülür: Anons sistemi → Teslim kaydı → "Kare → ses
(yazılım)" kartı (p50 ve p90) ve `/saglik?ayrinti=1` → `uyari_gecikmesi`. Bu sayı
kameradan gelen karenin yakalandığı andan çalıcının ya da HTTP isteğinin
başladığı ana kadardır. Bluetooth'un (A2DP) ve hoparlörün kendi tamponu
yazılımdan **ölçülemez**; "100-250 ms" gibi bir sayı ölçüm değildir, yazılmaz
(docs/17 §7.10). Toplam gecikme sahada şöyle ölçülür:

1. Kural gölge modda **değil**, anonsu açık bir kamera seçin; bir kişi yasak
   alanın ya da yaya yolunun dışında beklesin.
2. Telefonu, **aynı karede** hem izleme ekranını hem hoparlörü görecek (ve
   duyacak) biçimde koyun; mümkünse 60 kare/sn ile video kaydı başlatın.
3. Kişi alana adım atsın; uyarı çalana kadar kayda devam edin.
4. Videoyu kare kare ilerletin: ekranda uyarı bandının çıktığı kare ile
   sesin ilk duyulduğu (ses dalgasında yükseldiği) kare arasındaki kare
   sayısını sayın. Kare sayısı ÷ kare hızı = ekran → ses gecikmesi (60 kare/sn'de
   her kare yaklaşık 17 ms).
5. Kişinin alana girdiği kare ile uyarı bandının çıktığı kare arasını da
   sayın: bu, kameranın, ağın ve analizin payıdır.
6. Her kanal türü için (kablolu, Bluetooth, IP hoparlör) en az 5 deneme yapın;
   en kötüsünü ve ortancasını tutanağa yazın, Teslim kaydının p90'ını yanına
   ekleyin.

---

## 9. Forklift modelini fabrikanın kendi görüntüsüyle eğitmek

Hazır model forklifti çoğu zaman "tır" olarak görür; açık veriyle (LOCO) yapılan iki
eğitim kapılardan geçemedi. Çare bu fabrikanın kendi kameralarıdır. Fotoğraf çekmek ya da
kod yazmak gerekmez; tasarım ve denetimler docs/17 §12.6'da, adım adım kılavuz kaynak
klasöründeki `egitim/forklift/YEREL-EGITIM.md`'dedir.

1. **Önce KVKK.** Kareler çalışanları da gösterir. Forklift sayfasında "Kare toplamayı
   aç"a basmadan önce çalışanlara aydınlatma yapılmış ve bu amacın hukuki dayanağı
   (Rev.02 ya da ek protokol) olmalıdır; sayfa bunu onay kutusuyla sorar (docs/18).
   Kapatmak her an mümkündür ve hemen geçerlidir.
2. **Toplama (bir iki hafta).** Analiz açıkken program araç ya da forklift görünen kareyi
   kamera başına saatte en çok 12 kez, araçsız kareyi daha seyrek saklar; toplam 3000
   karede durur. Kareler `veri/goruntuler/forklift-ornekler/` altındadır (paketlenmiş
   uygulamada `%LOCALAPPDATA%\NextGen Detector\veri\goruntuler\forklift-ornekler`);
   etiketlenmeyenler 30 gün sonra silinir (§5).
3. **Etiketleme.** Forklift sayfası → "Etiketlemeye başla". Hedef: en az iki ayrı günden
   birkaç yüz kare. Son günler (yaklaşık dörtte biri) test içindir: test günlerinde en az
   50 forklift kutusu ve birkaç "Forklift yok" karesi olsun. Eksik olanı sayfa uyarı
   olarak yazar.
4. **Eğitim (kapalı bir bilgisayarda).** "Eğitim verisini indir (.zip)" → zip'i o
   bilgisayara (internete, paylaşılan klasöre değil) taşıyın → programın GitHub'daki
   kaynak klasörünü ZIP olarak indirip açın → zip'i `egitim\forklift\Egit-Windows.bat`'ın
   üstüne bırakın. Gerekenler: Windows 10/11, Python 3.12, en az 8 GB bellek, 6 GB boş
   disk, indirmeler için internet (fabrika kareleri hiçbir yere gitmez). İlk seferde
   yaklaşık 1 GB paket ve 770 MB LOCO iner; eğitim bilgisayarın hızına göre birkaç
   saatten bir güne kadar sürer ve kesilirse aynı zip'le kaldığı yerden devam eder. İzleme
   bilgisayarında da düşük öncelikle çalışabilir ama canlı izlemeyi yavaşlatabilir: gece
   ya da ayrı bir bilgisayar daha iyidir. Sonuç `C:\NextGen-Forklift\SONUC.txt`'dedir.
5. **Kurulum.** "GEÇTİ" yazıyorsa Forklift sayfası → "4. Modeli kur" → `KURULACAK`
   klasöründeki iki dosyayı (model `.onnx` ve ölçümü `.olcum.json`) seçip "Denetle ve
   kur". Program kapıları yeniden denetler; geçmeyeni kurmaz. Kurulan model Ayarlar →
   "Tanıma modeli" listesine gelir; **siz seçip kaydetmedikçe çalışan model değişmez.**
   Seçince sistemi yeniden başlatın ve kurulum listesinde "Araç kuralları tanıma modeline
   uyuyor mu?" adımına bakın: yalnız "Tır/Araç" seçili kurallarda "Forklift"i de
   işaretleyin. Modeli varsayılan yapmadan önce saha ölçümü tutanağa girer (§8).
6. **"KALDI" yazıyorsa** hangi ölçümün kaldığı ve ne yapılacağı `SONUC.txt`'dedir (çoğu
   zaman daha çok ve daha çeşitli kare). Yeni kareleri etiketleyip yeni zip'le eğitimi
   yeniden çalıştırın; kapılar değiştirilmez.

Kurulan model `models/` klasöründedir (paketlenmiş uygulamada `%LOCALAPPDATA%\NextGen
Detector\models`): programın klasörünü yenisiyle değiştirmek (§3) ona dokunmaz, ama §4'teki
yedeğe girmez; `KURULACAK`'taki iki dosyayı saklayın. **Docker'da** (sonraki aşama) model
container'ın içine kurulur: `docker compose restart`'tan sağ çıkar, imaj yeniden kurulunca
(güncelleme) kaybolur ve sistem hazır modele düşer (`MODEL_FALLBACK`). Kalıcı olsun diye iki
dosyayı sunucudaki `models/` klasörüne de koyun: imaj her kurulduğunda içine girer
(Docker'da denenmedi).
