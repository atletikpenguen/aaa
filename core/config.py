"""
Merkezi Konfigürasyon Yönetimi
Bu dosya, .env dosyasındaki tüm ayarları okur ve projeye dağıtır.
"""
import os
from dotenv import load_dotenv

# .env dosyasını yükle (VPS deployment için paths helper kullan)
from .paths import get_env_path
dotenv_path = get_env_path()
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)

# --- Binance API Ayarları ---
API_KEY = os.getenv("BINANCE_API_KEY") or os.getenv("BINANCE_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET")

# --- Testnet Ayarı ---
USE_TESTNET = os.getenv('USE_TESTNET', 'false').lower() == 'true'

# --- Sunucu Ayarları ---
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")

# --- Log Ayarları ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Güvenlik ---
SECRET_KEY = os.getenv("SECRET_KEY", "lutfen_guvenli_bir_secret_key_belirleyin")

# --- Telegram Bot Ayarları ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

def check_api_keys():
    if not API_KEY or not API_SECRET:
        print("UYARI: Binance API anahtarları .env dosyasında bulunamadı veya okunamadı.")
        return False
    return True
