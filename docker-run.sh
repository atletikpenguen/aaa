#!/bin/bash
# ===============================================
# Docker Run Script - Trading Bot
# Bu script Docker container'ı güvenli şekilde çalıştırır
# ===============================================

# Renkli çıktı
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🐳 Trading Bot Docker Başlatılıyor...${NC}"
echo "=================================="

# Çalışma dizinini ayarla
cd "$(dirname "$0")"

# 1. .env dosyası kontrolü
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env dosyası bulunamadı!${NC}"
    if [ -f "env.example" ]; then
        echo -e "${YELLOW}📝 env.example'dan .env oluşturuluyor...${NC}"
        cp env.example .env
        echo -e "${GREEN}✅ .env dosyası oluşturuldu${NC}"
        echo -e "${YELLOW}⚠️  Lütfen .env dosyasını düzenleyip API anahtarlarınızı girin!${NC}"
        echo -e "${YELLOW}   nano .env${NC}"
        exit 1
    else
        echo -e "${RED}❌ env.example dosyası da bulunamadı!${NC}"
        exit 1
    fi
fi

# 2. Gerekli dizinleri oluştur
echo -e "${BLUE}📁 Gerekli dizinler oluşturuluyor...${NC}"
mkdir -p data logs

# 3. Docker kontrolü
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker yüklü değil!${NC}"
    echo -e "${YELLOW}   Docker kurulumu için: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose yüklü değil!${NC}"
    echo -e "${YELLOW}   Docker Compose kurulumu gerekli${NC}"
    exit 1
fi

# 4. Port kontrolü
PORT=8000
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Port $PORT zaten kullanımda!${NC}"
    echo -e "${BLUE}🔍 Port kullanım bilgisi:${NC}"
    lsof -Pi :$PORT -sTCP:LISTEN
    echo ""
    read -p "Devam etmek istiyor musunuz? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 5. Eski container'ı durdur (varsa)
echo -e "${BLUE}🛑 Eski container'lar durduruluyor...${NC}"
docker-compose down 2>/dev/null || true

# 6. Container'ı build et ve çalıştır
echo -e "${GREEN}🔨 Container build ediliyor...${NC}"
docker-compose build

echo -e "${GREEN}🚀 Container başlatılıyor...${NC}"
docker-compose up -d

# 7. Durum kontrolü
sleep 5
echo -e "${BLUE}📊 Container durumu:${NC}"
docker-compose ps

echo ""
echo -e "${GREEN}✅ Trading Bot başlatıldı!${NC}"
echo -e "${BLUE}📱 Web Arayüzü: http://localhost:8000${NC}"
echo -e "${BLUE}🌐 VPS Erişim: http://$(hostname -I | awk '{print $1}'):8000${NC}"
echo ""
echo -e "${YELLOW}💡 Komutlar:${NC}"
echo -e "${YELLOW}   Durdurmak: docker-compose down${NC}"
echo -e "${YELLOW}   Logları görmek: docker-compose logs -f${NC}"
echo -e "${YELLOW}   Yeniden başlatmak: docker-compose restart${NC}"
echo ""

# 8. Logları göster
echo -e "${BLUE}📋 Son loglar:${NC}"
docker-compose logs --tail=20
