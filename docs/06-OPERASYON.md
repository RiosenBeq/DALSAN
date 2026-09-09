# 06 — Operasyon

> Bu doküman **çalışan sistemi** anlatır. Mimari `docs/09-BASITLESTIRME-KARARLARI.md`
> ile sadeleştirildi: tek program, tek SQLite dosyası, tek container. Eski
> PostgreSQL + Alembic + üç servis kurgusu **artık yoktur**.

---

## 1. Kurulum

### 1.1 Günlük kullanım / geliştirme (Mac, Windows)

Docker gerekmez. Kontrol Paneli yeter:

| Mac | Windows |
|---|---|
| `Baslat-Mac.command` → çift tık | `Baslat-Windows.bat` → çift tık |

**İlk Kurulumu Yap** → **Sistemi Başlat**. Tarayıcı `http://127.0.0.1:8080`
adresinde açılır. Tespit modeli yoksa sistem ilk açılışta **kendisi indirir**
(internet gerekir); ana sayfadaki "Tespit modeli" satırı "Hazır" olana kadar bekleyin.

Ayrıntı: `NASIL-CALISIR.md`.

### 1.2 Fabrika sunucusu (Linux + Docker)

```bash
git clone <depo-adresi> && cd DALSAN
cp .env.example .env       # saklama süreleri, ANONS, tespit eşikleri
                           # anons bağlama tarifi: docs/14-ANONS-SISTEMI-BAGLAMA.md
bash models/indir.sh       # model ağırlıkları repoda yoktur
docker compose up -d
docker compose ps          # tek servis: dalsan — durum "healthy" olmalı
```

Erişim: `http://127.0.0.1:8080` (compose varsayılanı sunucunun kendisine açar).

> **Ağa açmadan önce:** giriş şifresi şu an bilerek kapalıdır (`docs/07` #0).
> `docker-compose.yml` içindeki port satırını `"8080:8080"` yapmadan ÖNCE şifre
> geri eklenmelidir; aksi halde ağdaki herkes kural değiştirebilir.

Şema **otomatik** uygulanır: açılışta `backend/sema/*.sql` sırayla çalışır ve
uygulananlar `sema_surumu` tablosuna yazılır. Ayrı migrasyon komutu yoktur.

### 1.3 Verinin ve ayarların yeri

İki soru birbirinden ayrıdır ve ikisi de `backend/app/kaynaklar.py` içinde,
**tek yerde** çözülür:

| | Depodan çalışırken (bugün) | Paketlenmiş programda |
|---|---|---|
| Kaynak dosyalar (şablon, stil, şema betiği) | depo kökü | programın açtığı geçici klasör (`sys._MEIPASS`) |
| Yazılabilir veri (`veri/`, `models/`, `.env`) | depo kökü | macOS: `~/Library/Application Support/NextGen Detector/` · Windows: `%LOCALAPPDATA%\NextGen Detector\` |

Neden ayrı: paketlenmiş uygulamanın kendisi **salt okunurdur**; veritabanı,
günlük ve indirilen model oraya yazılamaz.

**Veri asla kendiliğinden taşınmaz.** Paketlenmiş program, kendi yanındaki
klasörde bir `veri/dalsan.db` bulur ve yeni konum boşsa **eski konumu
kullanmaya devam eder**; durumu günlüğe yazar. Sessiz kopyalama yapılsaydı,
yarıda kalan bir taşımada ya da yedeğini eski klasörde arayan kullanıcıda
kayıtlar kaybolmuş sayılırdı.

Paketlenmiş programda `.env` dosyası ilk açılışta `.env.example`'dan **bir kez**
üretilir; sonraki açılışlarda üzerine yazılmaz.

---

## 2. Servis

Tek servis: `dalsan` (FastAPI + arka planda analiz iş parçacığı).

| Özellik | Değer |
|---|---|
| Restart | `unless-stopped` — sunucu yeniden başlarsa sistem kendiliğinden kalkar (K8) |
| Healthcheck | `GET /saglik` (30 sn arayla) |
| Veri | `./veri` container dışında bağlı — container silinse de kaybolmaz |
| Ayarlar | `./.env` salt okunur bağlanır |

`/saglik` ucu bilerek ucuzdur (JSON: çalışıyor mu, analiz açık mı, model durumu).
Ana sayfa `veri/` klasörünün tamamını tarayıp boyut hesapladığı için sağlık
kontrolünde kullanılmaz.

---

## 3. Güncelleme

```bash
git pull
docker compose build
docker compose up -d
docker compose logs -f --tail=100
```

Şema değişikliği varsa açılışta kendiliğinden uygulanır. Geri alma:
`git checkout <önceki-sürüm>` → `docker compose build` → `up -d`.

> Şema betikleri **geri alınamaz** (Alembic yoktur — `docs/09` kararı). Geri
> dönüş yolu yedektir: sürüm yükseltmeden ÖNCE `veri/` klasörünü kopyalayın.

---

## 4. Yedekleme

**Tam yedek = `veri/` klasörünü ve `.env` dosyasını kopyalamak.** Hepsi bu.

```bash
cp -R veri/ /yedek/dalsan-$(date +%Y-%m-%d)/
cp .env    /yedek/dalsan-$(date +%Y-%m-%d)/
```

Sistem çalışırken güvenli veritabanı kopyası için: ana sayfadaki
**"Veritabanını Yedekle"** düğmesi (`veri/yedekler/` içine SQLite backup API ile
yazar, WAL uyumludur). Fotoğrafları kapsamaz — haftalık tam yedeği ihmal etmeyin.

**Geri yükleme provası — devreye almadan önce zorunlu (K7):**

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
| Etiketlenmemiş KKD kırpıkları | `KKD_HAM_VERI_SAKLAMA_GUN` | 30 gün | **Etiketlenenler silinmez** — eğitim veri setidir |
| Sistem olayları | `SISTEM_OLAY_SAKLAMA_GUN` | 90 gün | |

Bu dört süre, disk uyarı sınırı, anons adresi ve tespit eşikleri **arayüzden**
de değiştirilebilir: soldaki raftan **Sistem ayarları** (`/ayarlar`). Sayfa
`.env` dosyasını açıklama satırlarını bozmadan günceller ve değeri yazmadan
önce açılıştaki doğrulayıcıdan geçirir — geçersiz bir ayar dosyaya yazılmaz.
**Değişiklik, sistem yeniden başlatılınca geçerli olur.**

Fotoğrafı silinen olayın kaydı korunur, yalnızca fotoğraf bağlantısı temizlenir
(olay ekranında kırık resim çıkmaz).

Boş disk `DISK_UYARI_GB` altına inince Olaylar listesine `Sistem` tipi bir uyarı
düşer. **DALSAN'ın KVKK saklama politikasıyla uyum 1. haftada teyit edilir** —
sistem politikayı teknik olarak zorlar, politikayı belirlemez.

---

## 6. Log okuma

Günlük dosyası: `veri/loglar/sistem.log` (5 MB'ta döner, son 3 kopya saklanır).
Kontrol Paneli aynı satırları penceresinde gösterir.

```bash
tail -f veri/loglar/sistem.log
grep '"level": "ERROR"' veri/loglar/sistem.log
grep '"bilesen": "kamera"' veri/loglar/sistem.log
docker compose logs -f            # Docker kurulumunda
```

Biçim: her satır tek bir JSON nesnesi — `ts, level, bilesen, mesaj`.
Sorun bildirirken kırmızı/`ERROR` satırlarını **olduğu gibi** kopyalayın.

---

## 7. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| Kamera "bağlanıyor"da kalıyor | Kamera sayfasındaki durum satırı sebebi yazar (ulaşılamıyor / şifre / dosya yok). İlk bağlantı 30 sn sürebilir |
| Kamera "çevrimdışı" | Aynı durum satırı + `veri/loglar/sistem.log` içinde `"bilesen": "kamera"`; NVR eşzamanlı bağlantı limiti sık sebeptir |
| "Tespit modeli: Yüklenemedi" | İnternet yoksa `bash models/indir.sh` ile elle indirin; dosya bozuksa silip tekrar indirin |
| Kutular çıkmıyor / nesne kaçıyor | `.env` içinde `TESPIT_GUVEN_ESIGI` ve `TESPIT_INSAN_GUVEN_ESIGI` değerlerini kademeli düşürün (0,05'lik adımlarla). Uzak nesnede `TESPIT_EN_KUCUK_KENAR_PX` düşürülür |
| Çok fazla yanlış tespit | Aynı eşikleri yükseltin; **NextGen AI İsabetli** (`MODEL_DOSYASI=models/yolox_s.onnx`) daha isabetlidir (daha yavaş) |
| Olay üretilmiyor | Kural açık mı; bölge doğru tipte mi; mesafe kuralında kalibrasyon var mı (Kurallar sayfasındaki rozet söyler) |
| KKD hiç olay üretmiyor | Model henüz eğitilmedi — bu **beklenen** davranıştır (docs/04). Veri toplanıyor mu: KKD sekmesi |
| KKD çok fazla yanlış alarm | `04-KKD-BARET-YELEK.md` §8.3 tablosu |
| Uyarılar gecikiyor | Kamera `sample_fps` değerini düşürün; substream kullanın; `CIKARIM_CIHAZI=cuda` (yalnız NVIDIA'lı Linux) |
| "cuda seçili ama CPU ile çalışıyor" | Ana sayfada uyarı olarak görünür: NVIDIA sürücüsü + `onnxruntime-gpu` gerekir, ya da `.env`'de `cpu` yapın |
| Anons çalmıyor | **Anons** sayfası → "Anonsu Dene". Sonuç satırı sebebi yazar (ses dosyası yok / adres yanlış / komut bulunamadı) |
| Ekranda uyarı sesi gelmiyor | Tarayıcı kuralı: sayfaya bir kez tıklayın. Anons sayfasındaki kutuyu işaretleyin |
| Disk doluyor | Ana sayfadaki "Boş alan"; saklama sürelerini kısaltın; `veri/goruntuler` en büyük kalemdir |
| Canlı uyarı paneli "bağlantı koptu" | Sunucu durmuş olabilir; Kontrol Paneli'nden yeniden başlatın |

---

## 8. Devreye alma kontrol listesi (8. hafta)

- [ ] Sistem, sunucu yeniden başlatma sonrası kendiliğinden ayakta (K8)
- [ ] 3-4 kameranın tamamı ≥ 24 saat kesintisiz `çevrimiçi` (K1)
- [ ] Bölge ve kurallar arayüzden değiştirilebiliyor, restart gerekmiyor (K3)
- [ ] Test ihlali ≤ 2 sn içinde ekrana düşüyor (K4)
- [ ] Olay kaydı + kanıt fotoğrafı doğru, filtre çalışıyor (K5)
- [ ] Anons: **Anons sayfasından denendi**, çalışıyor veya "altyapı uygun değil" olarak yazılı kayıt altında (K6)
- [ ] Yedek alındı, **geri yükleme prova edildi** (K7)
- [ ] KKD gölge modda ≥ 3 gün çalıştı, precision ölçüldü, eşikler ayarlandı (K10, K11)
- [ ] KKD anonsu ancak precision kabul edildikten **sonra** açıldı
- [ ] Bakım (retention) çalıştığı günlükten doğrulandı, KVKK süreleriyle uyumlu
- [ ] **Giriş şifresi geri eklendi** (`docs/07` #0) — ağa açık kurulumda zorunlu
- [ ] Kullanım dokümanı teslim edildi, kullanıcı eğitimi yapıldı (K9)
- [ ] Kabul tutanağı: K1-K11 madde madde işaretlendi
