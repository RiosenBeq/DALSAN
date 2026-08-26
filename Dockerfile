# DALSAN İSG — fabrika sunucusu için tek container (CLAUDE.md §4).
# Geliştirmede Docker KULLANILMAZ; bu dosya yalnızca fabrika kurulumu içindir.
FROM python:3.12-slim

# OpenCV'nin çalışması için gereken sistem kütüphaneleri:
#  libgl1, libglib2.0-0 → görüntü işleme
#  libsm6, libxext6      → bazı OpenCV yapılarının bağımlılığı
#  ffmpeg                → RTSP akışının çözülmesi
# curl: sağlık kontrolü (healthcheck) için
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /uygulama

# Önce yalnızca bağımlılıklar: kod değişince bu katman yeniden kurulmaz
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY models/ models/
# Model dosyası olmadan container sessizce "tespit yapmayan" bir sisteme
# dönüşürdü. Derleme burada, ANLAŞILIR bir mesajla durur.
RUN test -s models/yolox_tiny.onnx || ( \
      echo "" && \
      echo "HATA: models/yolox_tiny.onnx bulunamadi." && \
      echo "Cozum: imaji derlemeden ONCE su komutu calistirin:" && \
      echo "        bash models/indir.sh" && \
      echo "" && exit 1 )


# veri/ ve .env container DIŞINDAN bağlanır (docker-compose.yml'e bakın):
# böylece container silinse de veritabanı, olay fotoğrafları ve ayarlar kalır.
WORKDIR /uygulama/backend

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Kontrol Paneli'nin kullandığı komutun aynısı — davranış birebir aynı olsun
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
