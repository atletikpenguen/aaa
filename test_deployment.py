# VPS Deployment Test Script
# Bu script deployment öncesi ve sonrası testler yapar

import os
import sys
import subprocess
from pathlib import Path

def test_paths():
    """Path helper'ı test et"""
    print("🔍 Path Helper Test...")
    try:
        from core.paths import get_deployment_info, ensure_directories
        
        info = get_deployment_info()
        print("✅ Path helper çalışıyor")
        
        for key, value in info.items():
            print(f"   {key}: {value}")
        
        ensure_directories()
        print("✅ Gerekli dizinler oluşturuldu")
        return True
    except Exception as e:
        print(f"❌ Path helper hatası: {e}")
        return False

def test_imports():
    """Tüm importları test et"""
    print("\n📦 Import Test...")
    try:
        # Ana modüller
        from core import config, storage, binance, utils
        from core.models import Strategy, State, Trade
        from core.strategy_engine import strategy_engine
        
        print("✅ Core modüller import edildi")
        
        # FastAPI modülleri
        import fastapi
        import uvicorn
        import ccxt
        import pandas
        import numpy
        
        print("✅ Bağımlılık modülleri import edildi")
        return True
    except Exception as e:
        print(f"❌ Import hatası: {e}")
        return False

def test_config():
    """Konfigürasyon test et"""
    print("\n⚙️ Config Test...")
    try:
        from core.config import API_KEY, API_SECRET, HTTP_PORT, HTTP_HOST
        
        print(f"   HTTP_HOST: {HTTP_HOST}")
        print(f"   HTTP_PORT: {HTTP_PORT}")
        print(f"   API_KEY: {'✅ Set' if API_KEY else '❌ Not Set'}")
        print(f"   API_SECRET: {'✅ Set' if API_SECRET else '❌ Not Set'}")
        
        if not API_KEY or not API_SECRET:
            print("⚠️  API anahtarları .env dosyasında ayarlanmalı")
            return False
        
        print("✅ Konfigürasyon OK")
        return True
    except Exception as e:
        print(f"❌ Config hatası: {e}")
        return False

def test_storage():
    """Storage sistemi test et"""
    print("\n💾 Storage Test...")
    try:
        from core.storage import storage
        
        # Test dizinlerinin varlığını kontrol et
        if not os.path.exists(storage.base_path):
            print(f"❌ Storage dizini bulunamadı: {storage.base_path}")
            return False
        
        print(f"✅ Storage dizini: {storage.base_path}")
        return True
    except Exception as e:
        print(f"❌ Storage hatası: {e}")
        return False

def test_build_files():
    """Build dosyalarını kontrol et"""
    print("\n🔨 Build Files Test...")
    
    required_files = [
        'trader_bot.spec',
        'build.sh',
        'startup.sh',
        'update.sh',
        'trader-bot.service',
        'VPS_DEPLOYMENT_GUIDE.md'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
        else:
            print(f"✅ {file}")
    
    if missing_files:
        print(f"❌ Eksik dosyalar: {', '.join(missing_files)}")
        return False
    
    print("✅ Tüm build dosyaları mevcut")
    return True

def test_executable_build():
    """Executable build test et"""
    print("\n🏗️ Executable Build Test...")
    
    if not os.path.exists('venv'):
        print("❌ Sanal çevre bulunamadı")
        return False
    
    # PyInstaller kurulu mu kontrol et
    try:
        result = subprocess.run(['pip', 'show', 'pyinstaller'], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ PyInstaller kurulu değil")
            return False
    except:
        print("❌ pip komutu çalıştırılamadı")
        return False
    
    print("✅ PyInstaller kurulu")
    print("💡 Executable oluşturmak için: ./build.sh")
    return True

def main():
    """Ana test fonksiyonu"""
    print("🧪 VPS Deployment Test Suite")
    print("=" * 40)
    
    tests = [
        ("Path Helper", test_paths),
        ("Imports", test_imports),
        ("Config", test_config),
        ("Storage", test_storage),
        ("Build Files", test_build_files),
        ("Executable Build", test_executable_build)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test hatası: {e}")
            results.append((test_name, False))
    
    # Sonuçları göster
    print("\n" + "=" * 40)
    print("📊 Test Sonuçları:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Toplam: {passed}/{total} test başarılı")
    
    if passed == total:
        print("\n🎉 Tüm testler başarılı! VPS deployment'a hazır.")
        print("\n📋 Sonraki adımlar:")
        print("1. ./build.sh - Executable oluştur")
        print("2. VPS'ye yükle")
        print("3. ./startup.sh - Bot'u başlat")
    else:
        print("\n⚠️ Bazı testler başarısız. Sorunları düzeltin.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
