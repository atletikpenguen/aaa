# VPS Deployment için Path Helper
# Bu dosya PyInstaller ile executable oluşturulduğunda dosya yollarını doğru şekilde yönetir
# Lokal geliştirme sırasında normal yolları kullanır

import sys
import os
from pathlib import Path

def is_frozen():
    """PyInstaller ile paketlenmiş mi kontrol et"""
    return getattr(sys, 'frozen', False)

def get_base_path():
    """Ana dizin yolunu al"""
    if is_frozen():
        # Executable'dan çalışıyorsa, executable'ın bulunduğu dizin
        return os.path.dirname(sys.executable)
    else:
        # Normal Python'dan çalışıyorsa, proje ana dizini
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_logs_dir():
    """Logs dizini yolunu al"""
    logs_path = os.path.join(get_base_path(), "logs")
    Path(logs_path).mkdir(exist_ok=True)  # Yoksa oluştur
    return logs_path

def get_data_dir():
    """Data dizini yolunu al"""
    data_path = os.path.join(get_base_path(), "data")
    Path(data_path).mkdir(exist_ok=True)  # Yoksa oluştur
    return data_path

def get_templates_dir():
    """Templates dizini yolunu al"""
    if is_frozen():
        # Executable için templates dizini executable yanında
        return os.path.join(get_base_path(), "templates")
    else:
        # Normal çalışma için mevcut templates dizini
        return os.path.join(get_base_path(), "templates")

def get_static_dir():
    """Static dizini yolunu al"""
    if is_frozen():
        # Executable için static dizini executable yanında
        return os.path.join(get_base_path(), "static")
    else:
        # Normal çalışma için mevcut static dizini
        return os.path.join(get_base_path(), "static")

def get_env_path():
    """.env dosyası yolunu al"""
    return os.path.join(get_base_path(), ".env")

def get_requirements_path():
    """requirements.txt dosyası yolunu al"""
    return os.path.join(get_base_path(), "requirements.txt")

def ensure_directories():
    """Gerekli dizinleri oluştur"""
    dirs = [
        get_logs_dir(),
        get_data_dir(),
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    print(f"✅ Gerekli dizinler hazırlandı: {get_base_path()}")

# VPS deployment bilgileri
def get_deployment_info():
    """Deployment bilgilerini döndür"""
    return {
        "is_frozen": is_frozen(),
        "base_path": get_base_path(),
        "logs_dir": get_logs_dir(),
        "data_dir": get_data_dir(),
        "templates_dir": get_templates_dir(),
        "static_dir": get_static_dir(),
        "env_path": get_env_path()
    }

if __name__ == "__main__":
    # Test için
    print("🔍 Path Helper Test:")
    info = get_deployment_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    ensure_directories()
