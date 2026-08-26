# Başlarken — 10 Dakikalık Rehber

## 1. Python'u kur (bir kez)

https://www.python.org/downloads/ → **Python 3.12**

> **Windows'ta:** Kurulum ekranındaki **"Add Python to PATH"** kutusunu işaretle.
> Bu kutuyu atlarsan hiçbir şey çalışmaz.

## 2. Kontrol Paneli'ni aç

| Mac | Windows |
|---|---|
| `Baslat-Mac.command` → çift tık | `Baslat-Windows.bat` → çift tık |
| Uyarı çıkarsa: sağ tık → Aç → Aç | Uyarı çıkarsa: Daha fazla bilgi → Yine de çalıştır |

## 3. "İlk Kurulumu Yap"a bas

Birkaç dakika sürer. Pencereyi kapatma. Bitince "KURULUM TAMAMLANDI" yazar.

## 4. Sistem kodu henüz yok — normal

"Sistem kodu: Henüz yazılmadı" yazısını göreceksin. Doğru olan bu.
Kod, Claude Code ile adım adım üretilecek.

## 5. Claude Code'a ilk mesajın

> CLAUDE.md ve docs/ klasöründeki tüm dokümanları oku.
>
> `docs/10-YAPAY-ZEKA-ILE-CALISMA.md` §4'teki sıralamanın **1. adımını** yap:
> proje iskeleti, SQLite veritabanı ve boş bir ana sayfa.
>
> Sadece bu adımı yap, sonrakine geçme. Bitince Kontrol Paneli'nde ne göreceğimi yaz.

## 6. Denemeyi unutma

Claude Code "tamam" dediğinde:
Kontrol Paneli → **Sistemi Başlat** → tarayıcı açılmalı.

**Açılmadıysa** günlük penceresindeki kırmızı satırları kopyala, Claude Code'a yapıştır:

> Şunu yapmaya çalıştım: sistemi başlattım.
> Bekliyordum: tarayıcı açılacaktı.
> Onun yerine bu oldu: [hata metnini yapıştır]

## 7. Her çalışan aşamadan sonra

> Şu an her şey çalışıyor. Kaydet ve ne yaptığımızı yaz.

Bu, **projeyi kurtaracak tek alışkanlıktır.** Atlamayın.

---

## Bilmen gereken tek klasör

```
veri/
 ├── dalsan.db      ← TÜM veritabanı bu tek dosya
 ├── goruntuler/    ← olay fotoğrafları
 ├── loglar/
 └── yedekler/
```

**Yedekleme = `veri/` klasörünü harici diske kopyalamak.** Hepsi bu.
Haftada bir yap.

---

## Sırada ne var

| Önce oku | Neden |
|---|---|
| `docs/10-YAPAY-ZEKA-ILE-CALISMA.md` | Çalışma yöntemi — **en önemlisi** |
| `docs/11-BILGISAYAR-UYGULAMASI.md` | Kontrol Paneli detayları |
| `docs/08-RISKLER-VE-ACIK-KARARLAR.md` §2 | 1. haftada DALSAN'a sorulacaklar |
| `docs/04-KKD-BARET-YELEK.md` §5.3 | KKD politika soruları — etiketlemeden önce |
