# CLAUDE.md — DALSAN İSG Görüntü Analiz Sistemi

Claude Code'un bu depoda çalışırken uyacağı kurallar. Her oturumun başında okunur.

> **ÖNEMLİ:** Projeyi yazılım bilmeyen bir kişi, yapay zeka yardımıyla yürütüyor.
> Bu, kalite standardını düşürmez — **basitlik standardını yükseltir.**
> Kullanıcı kodu okuyup onaylamayacak; sistemin **davranışını** deneyerek onaylayacak.

---

## 1. Proje tek cümleyle

Fabrikadaki **3-4 mevcut kameradan** görüntü alıp **insan, forklift, tır** tespit eden;
**bölge ihlali**, **güvenli mesafe** ve **KKD (baret/yelek)** kurallarını değerlendiren;
ihlalde ekrana ve (mümkünse) anonsa uyarı düşüren; her olayı kanıt fotoğrafıyla kaydeden,
**tek sunucuda çalışan** erken uyarı sistemi.

---

## 2. Altın kural

> **"Bu, `docs/01-MVP-KAPSAM.md` §1'deki uçtan uca akışın çalışması için gerekli mi?"**

Hayırsa kod yazılmaz — `docs/07-YOL-HARITASI.md`'ye satır olarak eklenir.

---

## 3. İkinci altın kural: en az parça

Bir işi iki yolla yapabiliyorsan, **kullanıcının öğrenmesi/bakması gereken parça
sayısı az olanı** seç. Teorik üstünlük ikinci kriterdir.

Yeni bir araç, kütüphane, servis veya çalışma zamanı eklemeden önce sor:
**"Bu olmadan yapılabilir mi?"** Cevap evetse ekleme.

---

## 4. Teknoloji — sabit, tartışmaya kapalı

| Katman | Karar |
|---|---|
| Dil | Python 3.12 |
| Web çatısı | FastAPI |
| Arayüz | **Jinja2 şablonu + sade JavaScript.** React/Vue/Node.js **YOK** |
| Veritabanı | **SQLite** — tek dosya: `veri/dalsan.db` |
| Süreç | **TEK program.** Analiz, FastAPI içinde arka plan iş parçacığı olarak çalışır |
| Şema | Sürümlü SQL betikleri: `backend/sema/001_*.sql`. Alembic **YOK** |
| Görüntü | OpenCV (RTSP over TCP) |
| Takip | `supervision` (ByteTrack) |
| Test | pytest |
| Biçim/lint | ruff |
| Docker | Geliştirmede **YOK**. Fabrika sunucusunda tek container |

Gerekçeler: `docs/09-BASITLESTIRME-KARARLARI.md`

---

## 5. Klasör yapısı

```
dalsan-isg/
├── CLAUDE.md
├── Baslat-Mac.command          # çift tıkla
├── Baslat-Windows.bat          # çift tıkla
├── masaustu/dalsan_launcher.py # kontrol paneli
├── .env / .env.example
├── backend/
│   ├── requirements.txt
│   ├── sema/                   # 001_ilk.sql, 002_...  (sıralı, geri alınabilir)
│   └── app/
│       ├── main.py             # TEK giriş noktası
│       ├── ayarlar.py          # .env okur — tek kaynak
│       ├── veritabani.py       # SQLite bağlantısı, şema uygulama
│       ├── modeller.py         # tablo tanımları
│       ├── web/                # rotalar + templates/ + static/
│       ├── analiz/             # kamera, tespit, takip, kkd_siniflandirici, boru_hatti,
│       │                       #   alan_bulucu (zemindeki boyadan bölge önerisi)
│       ├── rules/              # SAF karar mantığı — aşağıya bak (sayim.py dahil)
│       ├── olaylar/            # olay yazımı, fotoğraf, anons
│       └── egitim/             # veri seti, eğitim, HTML rapor
├── tests/
├── veri/                       # dalsan.db, goruntuler/, loglar/, yedekler/  (git'e girmez)
└── docs/
```

---

## 6. `rules/` kutsaldır

`rules/` şunları **import edemez**: OpenCV, torch, ultralytics, sqlite3, FastAPI.
İzinli: stdlib, numpy, pydantic.

Girdi: `list[Tespit]` (sınıf, kutu, takip_id, hız, kkd_gozlemi) + bölgeler +
kalibrasyon + kural parametreleri. Çıktı: `list[Ihlal]`.

**Neden:** Tüm eşik, cooldown, zamansal oylama ve KKD karar mantığı kameraya
bağlanmadan, sahte veriyle, saniyeler içinde test edilebilsin diye. Yazılım bilmeyen
bir kullanıcı için bu, doğruluğun kontrol edilebildiği tek yerdir.

Kural mantığına dokunan her değişiklikten sonra `pytest tests/rules` çalıştır ve
sonucu kullanıcıya **göster**.

---

## 7. Asla yapma

| Yasak | Yerine |
|---|---|
| `except:` / `except Exception: pass` | Tiplenmiş hata + log |
| Sabit kodlanmış eşik, yol, IP, şifre | `.env` veya veritabanındaki kural parametresi |
| `rules/` içine OpenCV/torch/sqlite import | Veriyi dataclass olarak geçir |
| Kare başına KKD/mesafe kararı | Takip bazlı zamansal oylama |
| "Belirsiz"i ihlal saymak | Üç durum: `var` / `yok` / `belirsiz` |
| Node.js, npm, derleme adımı eklemek | Sunucu tarafı şablon + sade JS |
| Yeni servis/container/kütüphane "ileride lazım" diye | `docs/07-YOL-HARITASI.md` |
| Model ağırlıklarını commit'lemek | `models/indir.sh` |
| "Şimdilik geçici çözüm" | Doğrusunu yap veya işi böl |
| Kullanıcıya kod okutup onay istemek | Davranışı tarif et: "şunu yap, şunu görmelisin" |

---

## 8. Kullanıcıyla iletişim biçimi

- **Küçük adımlar.** Bir istekte 10+ dosya değişiyorsa işi böl ve önce ilkini yap.
- **Her adımın sonunda deneme talimatı ver:** "Kontrol Paneli'nde Başlat'a bas,
  tarayıcıda Kameralar sekmesini aç, listede şunu görmelisin."
- **Hata mesajlarını sadeleştirme** — kullanıcı günlükten kopyalayıp yapıştıracak.
- **Terminal komutu vermek yerine** mümkünse Kontrol Paneli'ne düğme ekle.
- **Türkçe konuş.** Kod içi isimler İngilizce, kullanıcıya görünen her şey Türkçe.
- Her çalışan aşamadan sonra git commit'i öner.

---

## 9. Test komutları

```bash
pytest                    # tümü
pytest tests/rules -q     # kural motoru (hızlı, kamerasız)
ruff check . && ruff format .
```

---

## 10. Doküman haritası

| Dosya | İçerik |
|---|---|
| `00-PROJE-BAGLAMI.md` | Müşteri, ticari çerçeve, kapsam sınırı, KVKK |
| `01-MVP-KAPSAM.md` | Karar matrisi, kabul kriterleri, uçtan uca akış |
| `02-MIMARI.md` | Mimari ve veri modeli *(→ 09 ile güncellendi)* |
| `03-KURAL-MOTORU.md` | Dört kural tipinin tam davranış tanımı |
| `04-KKD-BARET-YELEK.md` | KKD: veri toplama, etiketleme, eğitim, eşik ayarı |
| `05-TEKNOLOJI-KARARLARI.md` | Teknoloji seçimleri + ADR *(→ 09 ile güncellendi)* |
| `06-OPERASYON.md` | Kurulum, yedek, retention, sorun giderme |
| `07-YOL-HARITASI.md` | Phase 2 ve fabrika geneli yayılım |
| `08-RISKLER-VE-ACIK-KARARLAR.md` | Risk kaydı, kapatılacak kararlar |
| **`09-BASITLESTIRME-KARARLARI.md`** | **Çelişki varsa BU dosya geçerlidir** |
| `10-YAPAY-ZEKA-ILE-CALISMA.md` | Kullanıcının çalışma yöntemi |
| `11-BILGISAYAR-UYGULAMASI.md` | Kontrol Paneli kullanımı |
| `12-KAMERA-VE-GORUNTU-KALITESI.md` | Kamera yerleşimi, görüntü kalitesi, hassasiyet ayarı, sınıf renkleri, yaya yolu kuralı |
| `13-UYGULAMA-PAKETLEME.md` | Teslim edilecek uygulamayı üretme (Mac `.app` / Windows `.exe`), veri yeri, güncelleme, Windows tuzakları |
| `15-UZAKTAN-ERISIM.md` | Fabrika ağına ve fabrika dışına açma: üç seviye, VPN/Tailscale önerisi, kaba kuvvet koruması, KVKK uyarısı |
| `14-ANONS-SISTEMI-BAGLAMA.md` | Anons altyapısına bağlanma: ses kartı / IP hoparlör, üç HTTP biçimi, devreye alma sırası, anons firmanıza soracaklarınız |

Bir karar bu dosyalarda yoksa **uydurma — sor.**
