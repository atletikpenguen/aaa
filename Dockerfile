# ===============================================
# Trading Bot Docker Container
# Bu dosya trading bot'u Docker konteynerinde çalıştırmak için oluşturuldu
# Güvenlik ve performans için optimize edildi
# ===============================================

# Python 3.9 slim image kullan (daha küçük ve güvenli)
FROM python:3.9-slim

# Sistem güncellemeleri ve gerekli paketler
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# Python environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Gerekli dizinleri oluştur
RUN mkdir -p /app/data /app/logs /app/static

# Requirements dosyasını kopyala ve bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY . .

# Port'u expose et
EXPOSE 8000

# Health check ekle
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Non-root user oluştur (güvenlik)
RUN useradd --create-home --shell /bin/bash trader
RUN chown -R trader:trader /app
USER trader

# Uygulamayı başlat
CMD ["python", "app.py"]
