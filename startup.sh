#!/bin/bash
# VPS Startup Script - Trader Bot
# Bu script VPS'de trader bot'u başlatır

echo "🚀 Trader Bot VPS Startup"
echo "========================="

# Renkli çıktı
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Çalışma dizinini ayarla
cd "$(dirname "$0")"

echo -e "${BLUE}📍 Çalışma dizini: $(pwd)${NC}"

# 1. .env dosyası kontrolü
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env dosyası bulunamadı!${NC}"
    echo -e "${YELLOW}📝 env.example dosyasını .env olarak kopyalayın ve API anahtarlarınızı girin.${NC}"
    
    if [ -f "env.example" ]; then
        cp env.example .env
        echo -e "${GREEN}✅ .env dosyası oluşturuldu (env.example'dan)${NC}"
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
mkdir -p logs data

# 3. Executable kontrolü
if [ ! -f "trader_bot" ]; then
    echo -e "${RED}❌ trader_bot executable dosyası bulunamadı!${NC}"
    echo -e "${YELLOW}   Build işlemi gerekli: ./build.sh${NC}"
    exit 1
fi

# 4. Executable'ı çalıştırılabilir yap
chmod +x trader_bot

# 5. Port kontrolü
PORT=8000
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
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

# 6. Sistem bilgilerini göster
echo -e "${BLUE}💻 Sistem Bilgileri:${NC}"
echo "   OS: $(uname -s) $(uname -r)"
echo "   Arch: $(uname -m)"
echo "   CPU: $(nproc) core"
echo "   Memory: $(free -h | awk '/^Mem:/ {print $2}')"
echo "   Disk: $(df -h . | awk 'NR==2 {print $4}') free"
echo ""

# 7. Bot'u başlat
echo -e "${GREEN}🚀 Trader Bot başlatılıyor...${NC}"
echo -e "${BLUE}📱 Web Arayüzü: http://$(hostname -I | awk '{print $1}'):8000${NC}"
echo -e "${BLUE}🌐 Lokal Erişim: http://localhost:8000${NC}"
echo ""
echo -e "${YELLOW}💡 Durdurmak için: Ctrl+C${NC}"
echo -e "${YELLOW}🔧 Servis olarak çalıştırmak için: sudo systemctl start trader-bot${NC}"
echo ""

# Başlatma zamanını kaydet
echo "$(date): Bot başlatıldı" >> logs/startup.log

# Bot'u çalıştır
./trader_bot

# Bot kapandığında log'a kaydet
echo "$(date): Bot kapatıldı" >> logs/startup.log
echo -e "${GREEN}✅ Trader Bot kapatıldı.${NC}"
