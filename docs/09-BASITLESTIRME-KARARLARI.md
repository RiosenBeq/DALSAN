# 09 — Sadeleştirme Kararları

> **Bu dosya, önceki dosyalardaki bazı teknik kararları DEĞİŞTİRİR.**
> Çelişki görürsen bu dosya geçerlidir.

## Neden değişti

Önceki kararlar "deneyimli bir yazılım ekibi geliştirecek" varsayımıyla alınmıştı.
Gerçek durum farklı: sistemi **yazılım bilmeyen bir kişi, yapay zeka yardımıyla**
geliştirecek ve bakımını yapacak.

Bu, iyi mühendisliğin tanımını değiştirmez ama **doğru takası** değiştirir:

| Eski öncelik | Yeni öncelik |
|---|---|
| Teorik olarak en sağlam mimari | **Bozulduğunda tek başına tamir edilebilen mimari** |
| Her bileşen kendi işine en uygun araç | **Toplam parça sayısı en az olan çözüm** |
| Ölçeklenmeye hazır | Bugün çalışan; ölçeklenme geldiğinde değiştirilebilir |

Bir kişi için **anlamadığı 5 parça, anladığı 2 parçadan daha risklidir** — çalışsalar bile.

---

## Değişen kararlar

| # | Eskiden | Şimdi | Neden |
|---|---|---|---|
| 1 | 2 ayrı süreç (api + analyzer) | **Tek program** | Tek şey başlar, tek şey durur, tek yerde hata aranır. 3-4 kamerada ayırmanın hiçbir faydası yok. |
| 2 | PostgreSQL (Docker container) | **SQLite (tek dosya)** | Yedekleme "şu dosyayı kopyala"ya iner. Kurulacak veritabanı sunucusu yok. 3-4 kamerada Postgres'in tek avantajı devreye girmiyor. |
| 3 | React + Vite + TypeScript + Tailwind (Node.js gerekir) | **HTML şablonu + sade JavaScript** | Node.js, npm, derleme adımı tamamen ortadan kalkıyor. Bilgisayarda kurulacak tek şey Python. |
| 4 | Docker Compose, 3 container | **Geliştirmede Docker yok; fabrikada tek container** | Docker'ı öğrenmek/onarmak ayrı bir uzmanlık. Mac ve Windows'ta sadece Python yeter. |
| 5 | Etiketleme için CVAT / Label Studio kurulumu | **Uygulamanın içinde etiketleme sayfası** | Ayrı bir araç kurmak, öğrenmek, veri aktarmak yok. Üç düğme: Var / Yok / Belirsiz. |
| 6 | Alembic migrasyonları | **Basit sürümlü şema betikleri** | Alembic güçlü ama kendi öğrenme eğrisi var. SQLite'ta sade bir `sema/001_*.sql` düzeni aynı işi görür. |
| 7 | Eğitim için ayrı script + manuel değerlendirme | **Tek komut → HTML rapor** | Rapor: doğruluk oranı + en kötü 50 hatanın görüntü ızgarası. Sayı okumak yerine **bakarak** karar verilir. |

## Değişmeyen kararlar (bunlar hâlâ doğru)

- Python + FastAPI
- `rules/` klasörünün saf ve bağımsız kalması (yapay zekanın kural mantığını test edebilmesi için **daha da önemli**)
- Üç kural tipi: bölge ihlali, güvenli mesafe, KKD
- KKD'de üç durumlu karar (`var` / `yok` / `belirsiz`) ve zamansal oylama
- KKD'nin gölge modda devreye alınması
- Git kullanımı (bkz. `10-YAPAY-ZEKA-ILE-CALISMA.md` — "geri alma düğmesi")
- Testler (yapay zekanın kendi işini doğrulama aracı)
- Tüm risk ve KVKK değerlendirmeleri

---

## Yeni sistem: kaç parça var

**Bilgisayarında (Mac/Windows) kurulu olacak tek şey: Python.**

```
Senin bilgisayarın                    Fabrika sunucusu
─────────────────                     ────────────────
Python 3.12                           Python 3.12
  └── DALSAN klasörü                    └── DALSAN klasörü
        ├── Baslat-Mac.command                └── otomatik başlar
        ├── Baslat-Windows.bat
        ├── backend/      (program)
        ├── veri/
        │    ├── dalsan.db      ← TÜM VERİTABANI BU TEK DOSYA
        │    ├── goruntuler/    ← olay fotoğrafları
        │    ├── loglar/
        │    └── yedekler/
        └── models/       (yapay zeka modelleri)
```

**Yedekleme artık şu:** `veri/` klasörünü kopyala. Hepsi bu.

## Fabrika sunucusu neden yine de Linux + ekran kartı

Bu değişmiyor ve değişemez:

- Yapay zeka görüntü analizi **ekran kartı (GPU)** ister. İşlemciyle 3-4 kamera bile
  KKD için yetersiz kalır.
- Ekran kartının Docker içinden kullanılması güvenilir şekilde yalnızca Linux'ta çalışır.
- Sistem 7 gün 24 saat, kimse başında olmadan çalışacak.

**Ama:** senin Mac/Windows bilgisayarında geliştirme ve test yapman için ekran kartı
gerekmez. Video dosyalarıyla ve düşük hızda çalışır. Fabrikaya kurulum, Claude Code'un
adım adım yönlendireceği **tek seferlik** bir iştir.

Windows sunucu da mümkündür (WSL2 + CUDA) ama fabrika ortamında 7x24 için önerilmez.
Bu, 8. haftada bir kez yapılacak iştir, günlük iş değil.

---

## Ne kaybettik

Dürüst olmak gerekirse üç şey:

1. **40+ kameraya çıkarken SQLite yetmez** → PostgreSQL'e geçiş gerekir.
   Bugün ödemediğimiz maliyeti o gün ödeyeceğiz. Ama o gün muhtemelen yanında
   yardım alacak biri olacak ve sistem kendini kanıtlamış olacak. Bugün ödemek,
   hiç ulaşamama riskini artırıyordu.

2. **Analiz çökerse ekran da gider** (tek program olduğu için). Karşılığında:
   sistem kendini otomatik yeniden başlatır ve hata günlüğü tek dosyada olur.
   Aslında **teşhis kolaylaşıyor.**

3. **Arayüz React kadar zengin olmayacak.** MVP'nin ihtiyacı (tablo, form, çizim
   alanı, canlı liste) sade JavaScript ile fazlasıyla karşılanır.

Üçü de kabul edilebilir. Kazanılan: **öğrenilecek/bakılacak parça sayısı 8'den 2'ye indi.**
