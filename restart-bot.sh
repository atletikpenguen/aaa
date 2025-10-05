#!/bin/bash
# Trading Bot Restart Script

echo "🔄 Trading Bot yeniden başlatılıyor..."

# Bot'u durdur
docker-compose down

# 5 saniye bekle
sleep 5

# Bot'u yeniden başlat
docker-compose up -d

# Durum kontrolü
docker-compose ps

echo "✅ Trading Bot yeniden başlatıldı!"
