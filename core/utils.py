"""
Yardımcı fonksiyonlar - Yuvarlama, zaman, logger vb.
"""

import math
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import pandas as pd
from colorama import init, Fore, Back, Style
from logging.handlers import RotatingFileHandler

# Colorama'yı initialize et
init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Renkli log formatter"""
    
    # Renk kodları
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
        
        # Özel anahtar kelimeler için renkler
        'BUY': Fore.GREEN + Style.BRIGHT,
        'SELL': Fore.RED + Style.BRIGHT,
        'ORDER': Fore.MAGENTA + Style.BRIGHT,
        'TRADE': Fore.CYAN + Style.BRIGHT,
        'PROFIT': Fore.GREEN + Style.BRIGHT,
        'LOSS': Fore.RED + Style.BRIGHT,
        'EMIR': Fore.MAGENTA + Style.BRIGHT,
        'İŞLEM': Fore.CYAN + Style.BRIGHT,
        'KAR': Fore.GREEN + Style.BRIGHT,
        'ZARAR': Fore.RED + Style.BRIGHT,
    }
    
    def format(self, record):
        # Temel formatı uygula
        log_message = super().format(record)
        
        # Özel anahtar kelimeleri renklendir
        for keyword, color in self.COLORS.items():
            if keyword in ['BUY', 'SELL', 'ORDER', 'TRADE', 'PROFIT', 'LOSS', 'EMIR', 'İŞLEM', 'KAR', 'ZARAR']:
                # Büyük ve küçük harf duyarlı değil
                import re
                pattern = rf'\b{re.escape(keyword)}\b'
                log_message = re.sub(pattern, f"{color}{keyword}{Style.RESET_ALL}", log_message, flags=re.IGNORECASE)
        
        # Levelname'i renklendir
        level_color = self.COLORS.get(record.levelname, '')
        if level_color:
            log_message = log_message.replace(record.levelname, f"{level_color}{record.levelname}{Style.RESET_ALL}")
        
        return log_message


class TerminalCleaner:
    """Terminal temizleme yöneticisi"""
    
    def __init__(self, clear_interval: int = 1000):  # 5 dakika varsayılan
        self.clear_interval = clear_interval
        self.last_clear_time = time.time()
        self.line_count = 0
        self.max_lines = 1000  # Maksimum satır sayısı
    
    def should_clear(self) -> bool:
        """Terminal temizlenmeli mi?"""
        current_time = time.time()
        time_elapsed = current_time - self.last_clear_time
        
        # Zaman bazlı veya satır sayısı bazlı temizleme
        if time_elapsed >= self.clear_interval or self.line_count >= self.max_lines:
            return True
        return False
    
    def clear_terminal(self):
        """Terminali temizle"""
        try:
            # İşletim sistemine göre temizleme
            if os.name == 'nt':  # Windows
                os.system('cls')
            else:  # Unix/Linux/Mac
                os.system('clear')
            
            # Temizleme sonrası bilgi mesajı
            print(f"{Fore.CYAN}🔄 Terminal temizlendi - {datetime.now().strftime('%H:%M:%S')}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}📊 Sistem çalışmaya devam ediyor...{Style.RESET_ALL}")
            print("-" * 80)
            
            # Sayaçları sıfırla
            self.last_clear_time = time.time()
            self.line_count = 0
            
        except Exception as e:
            print(f"Terminal temizleme hatası: {e}")
    
    def increment_line_count(self):
        """Satır sayısını artır"""
        self.line_count += 1


class CleanConsoleHandler(logging.StreamHandler):
    """Temizleme özellikli console handler"""
    
    def __init__(self, clear_interval: int = 300):
        super().__init__()
        self.cleaner = TerminalCleaner(clear_interval)
    
    def emit(self, record):
        # Temizleme kontrolü
        if self.cleaner.should_clear():
            self.cleaner.clear_terminal()
        
        # Satır sayısını artır
        self.cleaner.increment_line_count()
        
        # Normal log yazma
        super().emit(record)


def get_daily_log_filename() -> str:
    """Günlük log dosya adını oluştur (YYYYMMDD-app.log formatında)"""
    from .paths import get_logs_dir
    today = datetime.now().strftime("%Y%m%d")
    return os.path.join(get_logs_dir(), f"{today}-app.log")


def cleanup_old_logs(days_to_keep: int = 30):
    """
    Eski log dosyalarını temizle
    
    Args:
        days_to_keep: Kaç günlük log dosyası tutulacak (varsayılan 30 gün)
    """
    try:
        import glob
        from datetime import timedelta
        
        # Logs klasöründe tüm günlük log dosyalarını bul
        from .paths import get_logs_dir
        log_pattern = os.path.join(get_logs_dir(), "*-app.log")
        log_files = glob.glob(log_pattern)
        
        # Bugünden itibaren kaç gün önceki dosyaları sil
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        deleted_count = 0
        for log_file in log_files:
            try:
                # Dosya adından tarihi çıkar (YYYYMMDD-app.log formatından)
                filename = os.path.basename(log_file)
                date_str = filename.split('-')[0]  # YYYYMMDD kısmını al
                
                # Tarihi parse et
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                # Eski dosya ise sil
                if file_date < cutoff_date:
                    os.remove(log_file)
                    deleted_count += 1
                    print(f"🗑️ Eski log dosyası silindi: {filename}")
                    
            except (ValueError, IndexError) as e:
                # Dosya adı formatı uygun değilse atla
                continue
                
        if deleted_count > 0:
            print(f"✅ {deleted_count} adet eski log dosyası temizlendi")
            
    except Exception as e:
        print(f"❌ Log temizleme hatası: {e}")


def get_log_file_info() -> dict:
    """Log dosyaları hakkında bilgi al"""
    try:
        import glob
        
        from .paths import get_logs_dir
        log_pattern = os.path.join(get_logs_dir(), "*-app.log")
        log_files = glob.glob(log_pattern)
        
        info = {
            'total_files': len(log_files),
            'files': [],
            'total_size_mb': 0
        }
        
        for log_file in sorted(log_files, reverse=True):  # En yeni önce
            try:
                filename = os.path.basename(log_file)
                file_size = os.path.getsize(log_file)
                file_size_mb = round(file_size / (1024 * 1024), 2)
                
                # Dosya adından tarihi çıkar
                date_str = filename.split('-')[0]
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                info['files'].append({
                    'filename': filename,
                    'date': file_date.strftime("%Y-%m-%d"),
                    'size_mb': file_size_mb
                })
                
                info['total_size_mb'] += file_size_mb
                
            except (ValueError, IndexError):
                continue
                
        info['total_size_mb'] = round(info['total_size_mb'], 2)
        return info
        
    except Exception as e:
        return {'error': str(e)}


def setup_logger(name: str = "trading_bot", log_file: str = None, clear_interval: int = 300) -> logging.Logger:
    """
    Logger kurulumu - Günlük log dosyaları ile Terminal temizleme özellikli
    
    Args:
        name: Logger adı
        log_file: Log dosya yolu (None ise günlük dosya kullanılır)
        clear_interval: Terminal temizleme aralığı (saniye)
    """
    # Günlük log dosya adını oluştur
    if log_file is None:
        log_file = get_daily_log_filename()
    
    # Logs klasörünü oluştur
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Environment'dan log seviyesini al
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Eğer handler zaten varsa, tekrar ekleme
    if logger.handlers:
        return logger
    
    # Günlük log dosyası için basit FileHandler (RotatingFileHandler yerine)
    # Çünkü her gün yeni dosya oluşturulacak
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    
    # Temizleme özellikli console handler
    console_handler = CleanConsoleHandler(clear_interval)
    console_handler.setLevel(log_level)
    
    # Formatters
    # Normal formatter (dosya için)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Renkli formatter (terminal için)
    console_formatter = ColoredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def clear_terminal_manual():
    """Manuel terminal temizleme"""
    cleaner = TerminalCleaner()
    cleaner.clear_terminal()


def round_to_tick(price: float, tick_size: float) -> float:
    """Fiyatı tick size'a yuvarla"""
    if tick_size == 0 or price <= 0:
        return price
    
    try:
        # Decimal kullanarak hassas yuvarlama
        decimal_price = Decimal(str(price))
        decimal_tick = Decimal(str(tick_size))
        
        # En yakın tick'e yuvarla - güvenli bölme
        rounded = decimal_tick * (decimal_price / decimal_tick).quantize(Decimal('1'), rounding=ROUND_DOWN)
        return float(rounded)
    except (ZeroDivisionError, InvalidOperation):
        return price


def floor_to_step(quantity: float, step_size: float) -> float:
    """Miktarı step size'a aşağı yuvarla (floor)"""
    if step_size == 0 or quantity <= 0:
        return quantity
    
    try:
        # Decimal kullanarak hassas floor işlemi
        decimal_qty = Decimal(str(quantity))
        decimal_step = Decimal(str(step_size))
        
        # Floor to step - güvenli bölme
        floored = decimal_step * (decimal_qty / decimal_step).quantize(Decimal('1'), rounding=ROUND_DOWN)
        return float(floored)
    except (ZeroDivisionError, InvalidOperation):
        return quantity


def is_valid_min_qty(quantity: float, min_qty: float) -> bool:
    """Minimum miktar kontrolü"""
    return quantity >= min_qty


def is_valid_min_notional(quantity: float, price: float, min_notional: float) -> bool:
    """Minimum işlem tutarı kontrolü"""
    notional = quantity * price
    return notional >= min_notional


def get_precision(value: float) -> int:
    """Bir sayının ondalık basamak sayısını bul"""
    decimal_value = Decimal(str(value))
    return abs(decimal_value.as_tuple().exponent)


def calculate_quantity(usdt_amount: float, price: float, step_size: float, min_qty: float) -> Tuple[float, bool]:
    """
    USDT tutarından miktar hesapla ve validasyon yap
    Returns: (quantity, is_valid)
    """
    if price <= 0 or usdt_amount <= 0:
        return 0.0, False
    
    try:
        # Ham miktar hesapla - güvenli bölme
        raw_quantity = usdt_amount / price
    except ZeroDivisionError:
        return 0.0, False
    
    # Step size'a yuvarla
    quantity = floor_to_step(raw_quantity, step_size)
    
    # Minimum miktar kontrolü
    is_valid = is_valid_min_qty(quantity, min_qty)
    
    return quantity, is_valid


def get_timeframe_seconds(timeframe: str) -> int:
    """Timeframe'i saniyeye çevir"""
    timeframe_map = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "1d": 86400
    }
    return timeframe_map.get(timeframe, 60)


def is_bar_closed(current_time: datetime, timeframe: str, last_bar_time: Optional[datetime] = None) -> bool:
    """
    Bar kapanışını kontrol et
    Returns: True if a new bar has closed since last_bar_time
    """
    if last_bar_time is None:
        return True
    
    # Timeframe saniye cinsinden
    tf_seconds = get_timeframe_seconds(timeframe)
    
    # Current bar start time
    current_timestamp = int(current_time.timestamp())
    current_bar_start = (current_timestamp // tf_seconds) * tf_seconds
    
    # Last bar start time
    last_timestamp = int(last_bar_time.timestamp())
    last_bar_start = (last_timestamp // tf_seconds) * tf_seconds
    
    # Yeni bar başladı mı?
    return current_bar_start > last_bar_start


def get_bar_start_time(timestamp: datetime, timeframe: str) -> datetime:
    """Verilen zaman için bar başlangıç zamanını hesapla"""
    tf_seconds = get_timeframe_seconds(timeframe)
    ts = int(timestamp.timestamp())
    bar_start = (ts // tf_seconds) * tf_seconds
    return datetime.fromtimestamp(bar_start, tz=timezone.utc)


def get_last_closed_bar_data(ohlcv_data: List[List]) -> Optional[dict]:
    """
    OHLCV verisinden son kapalı bar'ı al
    ohlcv_data format: [[timestamp, open, high, low, close, volume], ...]
    """
    if not ohlcv_data or len(ohlcv_data) < 2:
        return None
    
    # Son önceki bar'ı al (son bar henüz kapanmamış olabilir)
    last_closed = ohlcv_data[-2]
    
    return {
        'timestamp': datetime.fromtimestamp(last_closed[0] / 1000, tz=timezone.utc),
        'open': float(last_closed[1]),
        'high': float(last_closed[2]),
        'low': float(last_closed[3]),
        'close': float(last_closed[4]),
        'volume': float(last_closed[5])
    }


def calculate_grid_levels(gf: float, y: float, max_levels: int = 50) -> dict:
    """
    Grid seviyelerini hesapla
    Returns: {
        'buy_levels': [price1, price2, ...],  # GF altındaki alım seviyeleri
        'sell_levels': [price1, price2, ...]  # GF üstündeki satım seviyeleri
    }
    """
    buy_levels = []
    sell_levels = []
    
    # Alım seviyeleri (GF altında)
    for i in range(1, max_levels + 1):
        buy_price = gf - (i * y)
        if buy_price > 0:  # Negatif fiyat olmasın
            buy_levels.append(buy_price)
    
    # Satım seviyeleri (GF üstünde)
    for i in range(1, max_levels + 1):
        sell_price = gf + (i * y)
        sell_levels.append(sell_price)
    
    return {
        'buy_levels': buy_levels,
        'sell_levels': sell_levels
    }


def format_number(number: float, precision: int = 8) -> str:
    """Sayıyı format'la (trailing zeros'ları kaldır)"""
    formatted = f"{number:.{precision}f}"
    # Trailing zeros'ları kaldır
    formatted = formatted.rstrip('0').rstrip('.')
    return formatted


def safe_float(value, default: float = 0.0) -> float:
    """Güvenli float dönüşümü"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Güvenli int dönüşümü"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def create_csv_line(trade_data: dict) -> str:
    """Trade verisinden CSV satırı oluştur"""
    return f"{trade_data['timestamp']},{trade_data['side']},{trade_data['price']},{trade_data['quantity']},{trade_data['z']},{trade_data['notional']},{trade_data['gf_before']},{trade_data['gf_after']}\n"


def parse_csv_line(line: str) -> dict:
    """CSV satırından trade verisini parse et"""
    parts = line.strip().split(',')
    if len(parts) >= 8:
        return {
            'timestamp': parts[0],
            'side': parts[1],
            'price': safe_float(parts[2]),
            'quantity': safe_float(parts[3]),
            'z': safe_int(parts[4]),
            'notional': safe_float(parts[5]),
            'gf_before': safe_float(parts[6]),
            'gf_after': safe_float(parts[7])
        }
    return {}


def generate_strategy_id() -> str:
    """Yeni strateji ID'si oluştur"""
    import uuid
    return str(uuid.uuid4())[:8]


def validate_symbol(symbol: str) -> bool:
    """Sembol validasyonu"""
    valid_symbols = ["BTCUSDT", "ETHUSDT", "AVAXUSDT", "SOLUSDT", "DOGEUSDT"]
    return symbol in valid_symbols


def validate_timeframe(timeframe: str) -> bool:
    """Timeframe validasyonu"""
    valid_timeframes = ["1m", "5m", "15m", "1h", "1d"]
    return timeframe in valid_timeframes


def get_next_bar_time(current_time: datetime, timeframe: str) -> datetime:
    """Sonraki bar zamanını hesapla"""
    tf_seconds = get_timeframe_seconds(timeframe)
    current_timestamp = int(current_time.timestamp())
    next_bar_start = ((current_timestamp // tf_seconds) + 1) * tf_seconds
    return datetime.fromtimestamp(next_bar_start, tz=timezone.utc)


def sleep_until_next_bar(timeframe: str) -> int:
    """Sonraki bar'a kadar beklenecek saniye sayısını hesapla"""
    now = datetime.now(timezone.utc)
    next_bar = get_next_bar_time(now, timeframe)
    sleep_seconds = (next_bar - now).total_seconds()
    
    # En az 1 saniye bekle
    return max(1, int(sleep_seconds))


class PerformanceTracker:
    """Performans izleme sınıfı"""
    
    def __init__(self):
        self.start_times = {}
        self.metrics = {}
    
    def start(self, operation: str):
        """İşlem başlangıcını kaydet"""
        self.start_times[operation] = datetime.now()
    
    def end(self, operation: str):
        """İşlem bitişini kaydet ve süreyi hesapla"""
        if operation in self.start_times:
            duration = (datetime.now() - self.start_times[operation]).total_seconds()
            if operation not in self.metrics:
                self.metrics[operation] = []
            self.metrics[operation].append(duration)
            del self.start_times[operation]
            return duration
        return 0
    
    def get_average(self, operation: str) -> float:
        """Ortalama süreyi al"""
        if operation in self.metrics and self.metrics[operation]:
            return sum(self.metrics[operation]) / len(self.metrics[operation])
        return 0.0
    
    def get_stats(self) -> dict:
        """Tüm istatistikleri al"""
        stats = {}
        for operation, durations in self.metrics.items():
            if durations:
                stats[operation] = {
                    'count': len(durations),
                    'average': sum(durations) / len(durations),
                    'min': min(durations),
                    'max': max(durations),
                    'total': sum(durations)
                }
        return stats


def setup_binance_trading_logger():
    """
    Binance alış veriş işlemleri için özel logger - LOG_LEVEL'dan bağımsız
    Her zaman terminal ve günlük log dosyasına yazar
    """
    binance_logger = logging.getLogger("binance_trading")
    
    # Her zaman INFO level'ında çalışsın
    binance_logger.setLevel(logging.INFO)
    
    # Eğer handler zaten varsa, tekrar ekleme
    if binance_logger.handlers:
        return binance_logger
    
    # Günlük log dosyasına yazacak
    daily_log_file = get_daily_log_filename()
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler(daily_log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Console handler - terminale yazacak
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = ColoredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    binance_logger.addHandler(file_handler)
    binance_logger.addHandler(console_handler)
    
    # Ana logger'dan bağımsız olsun
    binance_logger.propagate = False
    
    return binance_logger


def log_trading_action(message: str, action_type: str = "INFO"):
    """
    Trading işlemleri için özel log fonksiyonu
    action_type: 'BUY', 'SELL', 'ORDER', 'TRADE', 'PROFIT', 'LOSS' vb.
    """
    # Normal trading logger'ı al
    trading_logger = logging.getLogger("trading_bot")
    
    # Action type'ı mesaja ekle
    formatted_message = f"[{action_type}] {message}"
    
    # Log level'ını belirle
    if action_type in ['ERROR', 'LOSS', 'ZARAR']:
        trading_logger.error(formatted_message)
    elif action_type in ['WARNING', 'WARN']:
        trading_logger.warning(formatted_message)
    else:
        trading_logger.info(formatted_message)


def log_binance_trading_action(message: str, action_type: str = "INFO"):
    """
    Binance alış veriş işlemleri için özel log fonksiyonu
    LOG_LEVEL'dan bağımsız olarak her zaman terminal ve app.log'a yazar
    action_type: 'BUY', 'SELL', 'ORDER', 'TRADE', 'PROFIT', 'LOSS' vb.
    """
    # Binance trading logger'ı al (LOG_LEVEL'dan bağımsız)
    binance_logger = setup_binance_trading_logger()
    
    # Action type'ı mesaja ekle
    formatted_message = f"[BINANCE-{action_type}] {message}"
    
    # Her zaman INFO olarak logla (LOG_LEVEL'dan bağımsız)
    binance_logger.info(formatted_message)


# Global logger instance
logger = setup_logger()

# Global performance tracker
perf_tracker = PerformanceTracker()
