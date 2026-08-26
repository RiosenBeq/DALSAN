# 06 — Operasyon

## 1. Kurulum (fabrika sunucusu)

```bash
git clone <repo> && cd dalsan-isg
cp .env.example .env          # doldur: DB şifresi, ADMIN_PASSWORD, ANNOUNCER, retention
bash models/download.sh       # model ağırlıkları (repoda yok)
docker compose up -d
docker compose exec api alembic upgrade head
docker compose ps             # üç servis de healthy olmalı
```

Erişim: `http://<sunucu-ip>:8080`

## 2. Servisler

| Servis | Görev | Restart | Healthcheck |
|---|---|---|---|
| `db` | PostgreSQL 16 | unless-stopped | `pg_isready` |
| `api` | FastAPI + frontend | unless-stopped | `GET /health` |
| `analyzer` | Görüntü alma + çıkarım + kural | unless-stopped | `GET /health` (iç port) + son kare zamanı |

Sunucu yeniden başladığında üçü de otomatik ayağa kalkar (K8). Hiçbiri manuel
başlatma gerektirmez.

## 3. Güncelleme

```bash
git pull
docker compose build
docker compose exec api alembic upgrade head   # ÖNCE migrasyon
docker compose up -d
docker compose logs -f --tail=100
```

Geri alma: `git checkout <önceki-tag>` → build → `alembic downgrade -1` → up.
Her migrasyonun `downgrade()` fonksiyonu **yazılmış ve denenmiş** olmalıdır.

## 4. Yedekleme

`deploy/backup.sh`:
- `pg_dump` → tarihli sıkıştırılmış dosya
- snapshot dizini arşivi
- son N kopya saklanır, eskiler silinir

Kurulum: sunucuda günlük zamanlanmış görev (cron / systemd timer). Runbook'ta adımlar var.

**Geri yükleme provası — devreye alma öncesi zorunlu (K7):**

```bash
bash deploy/restore.sh <yedek-dosyasi>
```

Test edilmemiş yedek yedek sayılmaz. 7. haftada bir kez tam prova yapılır ve
sonucu kabul tutanağına yazılır.

## 5. Retention (saklama süreleri)

Zamanlanmış görev günlük çalışır:

| Veri | Varsayılan | Not |
|---|---|---|
| Olay kaydı (DB) | 180 gün | KVKK politikasıyla uyumlu olmalı |
| Snapshot dosyaları | 90 gün | Disk büyümesinin ana kalemi |
| KKD ham crop'ları (`ppe_samples`) | 30 gün (etiketlenmemiş) | Etiketlenenler veri setine taşınır |
| Sistem olayları | 90 gün | |

Süreler `.env`'den ayarlanır. **DALSAN'ın KVKK saklama politikasıyla uyumu
1. haftada teyit edilir** — sistem politikayı teknik olarak zorlar, politikayı belirlemez.

Disk kullanımı günlük loglanır; eşik altına inince `system` tipi olay üretilir.

## 6. Log okuma

```bash
docker compose logs -f analyzer                      # canlı
docker compose logs analyzer | grep '"level":"ERROR"'
docker compose logs analyzer | grep '"camera_id":3'
```

Log formatı: JSON satır — `ts, level, component, camera_id, event, msg`.

## 7. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| Kamera "offline" | `analyzer` logunda o `camera_id`; RTSP URL; ağ erişimi; NVR eşzamanlı bağlantı limiti |
| Olay üretilmiyor | Kural `enabled` mı; bölge doğru mu; mesafe kuralında kalibrasyon var mı |
| KKD hiç olay üretmiyor | `min_person_height_px` çok yüksek olabilir; olay detayındaki `unknown` oranına bak |
| KKD çok fazla yanlış alarm | `04-KKD-BARET-YELEK.md` §8.3 tablosu |
| Uyarılar gecikiyor | GPU doluluğu; `sample_fps` düşür; substream kullan |
| Anons çalmıyor | `ANNOUNCER` ayarı; ses cihazı container'a bağlı mı; anons cooldown'u aktif olabilir |
| Disk doluyor | Retention görevi çalışıyor mu; snapshot dizini boyutu |
| Ekran boş / SSE kopuk | `api` logu; tarayıcı konsolu; oturum süresi dolmuş olabilir |

## 8. Devreye alma kontrol listesi (8. hafta)

- [ ] Üç servis de sunucu yeniden başlatma sonrası otomatik ayakta (K8)
- [ ] 3-4 kameranın tamamı ≥ 24 saat kesintisiz `online` (K1)
- [ ] Bölge ve kurallar arayüzden değiştirilebiliyor, restart gerekmiyor (K3)
- [ ] Test ihlali ≤ 2 sn içinde ekrana düşüyor (K4)
- [ ] Olay kaydı + snapshot doğru, filtre çalışıyor (K5)
- [ ] Anons: çalışıyor veya "altyapı uygun değil" olarak **yazılı** kayıt altında (K6)
- [ ] Yedek alındı, **geri yükleme prova edildi** (K7)
- [ ] KKD gölge modda ≥ 3 gün çalıştı, precision ölçüldü, eşikler ayarlandı (K10, K11)
- [ ] KKD anonsu ancak precision kabul edildikten **sonra** açıldı
- [ ] Retention görevi çalışıyor, KVKK süreleriyle uyumlu
- [ ] Kullanım dokümanı teslim edildi, kullanıcı eğitimi yapıldı (K9)
- [ ] Kabul tutanağı: K1-K11 madde madde işaretlendi
