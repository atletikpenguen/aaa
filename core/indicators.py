"""
OTT (Optimized Trend Tracker) ve diğer teknik indikatör hesaplamaları
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from .models import OTTResult, OTTMode
from .utils import logger


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """
    Exponential Moving Average hesapla
    """
    if len(prices) < period:
        return []
    
    # NumPy ile daha hızlı hesaplama
    prices_array = np.array(prices, dtype=float)
    alpha = 2.0 / (period + 1)
    
    # İlk değer SMA
    sma_first = np.mean(prices_array[:period])
    ema_values = [sma_first]
    
    # EMA hesaplama
    for i in range(period, len(prices_array)):
        ema = alpha * prices_array[i] + (1 - alpha) * ema_values[-1]
        ema_values.append(ema)
    
    return ema_values


def calculate_sma(prices: List[float], period: int) -> List[float]:
    """
    Simple Moving Average hesapla
    """
    if len(prices) < period or period <= 0:
        return []
    
    sma_values = []
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        if len(window) > 0 and period > 0:
            sma = sum(window) / period
            sma_values.append(sma)
    
    return sma_values


def calculate_ott(close_prices: List[float], period: int, opt: float, strategy_name: str = "Unknown") -> Optional[OTTResult]:
    """
    OTT (Optimized Trend Tracker) hesapla
    
    Args:
        close_prices: Kapanış fiyatları listesi
        period: EMA periyodu
        opt: Optimizasyon yüzdesi (2.0 = %2)
        strategy_name: Strateji adı (log için)
        
    Returns:
        OTTResult object veya None
    """
    try:
        if len(close_prices) < period:
            logger.warning(f"OTT hesaplama için yeterli veri yok. Gerekli: {period}, Mevcut: {len(close_prices)}")
            return None
        
        # EMA (baseline) hesapla
        ema_values = calculate_ema(close_prices, period)
        
        if not ema_values:
            logger.warning("EMA hesaplanamadı")
            return None
        
        # Son EMA değerini baseline olarak al
        baseline = ema_values[-1]
        current_price = close_prices[-1]
        
        # OTT bantları hesapla
        upper = baseline * (1 + opt / 100)
        lower = baseline * (1 - opt / 100)
        
        # OTT modu belirle (spesifikasyona göre basit tanım)
        # close > baseline → AL, değilse SAT
        mode = OTTMode.AL if current_price > baseline else OTTMode.SAT
        
        logger.info(f"OTT hesaplandı [{strategy_name}] - Mode: {mode}, Baseline: {baseline:.6f}, Price: {current_price:.6f}")
        
        return OTTResult(
            mode=mode,
            baseline=baseline,
            upper=upper,
            lower=lower,
            current_price=current_price
        )
        
    except Exception as e:
        logger.error(f"OTT hesaplama hatası: {e}")
        return None


def calculate_ott_detailed(close_prices: List[float], period: int, opt: float) -> Dict:
    """
    Detaylı OTT hesaplama - debug ve analiz için
    """
    result = {
        'valid': False,
        'baseline_history': [],
        'upper_history': [],
        'lower_history': [],
        'mode_history': [],
        'current': None
    }
    
    try:
        if len(close_prices) < period:
            return result
        
        # Tüm EMA değerlerini hesapla
        ema_values = calculate_ema(close_prices, period)
        
        if not ema_values:
            return result
        
        # Her bar için OTT değerlerini hesapla
        for i, (ema, price) in enumerate(zip(ema_values, close_prices[period-1:])):
            upper = ema * (1 + opt / 100)
            lower = ema * (1 - opt / 100)
            mode = OTTMode.AL if price > ema else OTTMode.SAT
            
            result['baseline_history'].append(ema)
            result['upper_history'].append(upper)
            result['lower_history'].append(lower)
            result['mode_history'].append(mode.value)
        
        # Son değerleri current olarak ayarla
        if ema_values:
            last_ema = ema_values[-1]
            last_price = close_prices[-1]
            
            result['current'] = OTTResult(
                mode=OTTMode.AL if last_price > last_ema else OTTMode.SAT,
                baseline=last_ema,
                upper=last_ema * (1 + opt / 100),
                lower=last_ema * (1 - opt / 100),
                current_price=last_price
            )
            result['valid'] = True
        
        return result
        
    except Exception as e:
        logger.error(f"Detaylı OTT hesaplama hatası: {e}")
        return result


def validate_ott_params(period: int, opt: float) -> bool:
    """OTT parametrelerini validate et"""
    if not isinstance(period, int) or period < 1 or period > 200:
        logger.error(f"Geçersiz OTT period: {period}. 1-200 arası olmalı.")
        return False
    
    if not isinstance(opt, (int, float)) or opt < 0.1 or opt > 10.0:
        logger.error(f"Geçersiz OTT opt: {opt}. 0.1-10.0 arası olmalı.")
        return False
    
    return True


def backtest_ott_signals(close_prices: List[float], period: int, opt: float) -> Dict:
    """
    OTT sinyallerini backtest et
    Returns: sinyal geçmişi ve istatistikler
    """
    signals = []
    stats = {
        'total_al_signals': 0,
        'total_sat_signals': 0,
        'mode_changes': 0,
        'accuracy': 0.0
    }
    
    try:
        if len(close_prices) < period + 1:
            return {'signals': signals, 'stats': stats}
        
        # Her bar için OTT hesapla
        for i in range(period, len(close_prices)):
            window_prices = close_prices[:i+1]
            ott_result = calculate_ott(window_prices, period, opt, "Backtest")
            
            if ott_result:
                signals.append({
                    'index': i,
                    'price': close_prices[i],
                    'mode': ott_result.mode.value,
                    'baseline': ott_result.baseline,
                    'upper': ott_result.upper,
                    'lower': ott_result.lower
                })
                
                if ott_result.mode == OTTMode.AL:
                    stats['total_al_signals'] += 1
                else:
                    stats['total_sat_signals'] += 1
        
        # Mod değişikliklerini say
        for i in range(1, len(signals)):
            if signals[i]['mode'] != signals[i-1]['mode']:
                stats['mode_changes'] += 1
        
        return {'signals': signals, 'stats': stats}
        
    except Exception as e:
        logger.error(f"OTT backtest hatası: {e}")
        return {'signals': signals, 'stats': stats}


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    RSI (Relative Strength Index) hesapla - opsiyonel ek indikatör
    """
    if len(prices) < period + 1:
        return []
    
    gains = []
    losses = []
    
    # Fiyat değişimlerini hesapla
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return []
    
    # İlk RS hesapla
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsi_values = []
    
    for i in range(period, len(gains)):
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        rsi_values.append(rsi)
        
        # Sonraki değer için ortalama güncelle
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    return rsi_values


def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict:
    """
    Bollinger Bands hesapla - opsiyonel ek indikatör
    """
    if len(prices) < period or period <= 0:
        return {'upper': [], 'middle': [], 'lower': []}
    
    try:
        middle = calculate_sma(prices, period)
        if not middle:
            return {'upper': [], 'middle': [], 'lower': []}
        
        upper = []
        lower = []
        
        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            if len(window) > 0:
                std = np.std(window)
                sma_idx = i - period + 1
                if 0 <= sma_idx < len(middle):
                    sma = middle[sma_idx]
                    upper.append(sma + (std_dev * std))
                    lower.append(sma - (std_dev * std))
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }
    except Exception as e:
        # Hata durumunda boş döndür
        return {'upper': [], 'middle': [], 'lower': []}


class TechnicalIndicators:
    """Teknik indikatör hesaplama sınıfı"""
    
    def __init__(self):
        self.cache = {}
    
    def get_ott(self, close_prices: List[float], period: int, opt: float, use_cache: bool = True) -> Optional[OTTResult]:
        """Cache'li OTT hesaplama"""
        cache_key = f"ott_{len(close_prices)}_{period}_{opt}"
        
        if use_cache and cache_key in self.cache:
            return self.cache[cache_key]
        
        result = calculate_ott(close_prices, period, opt, "Cached")
        
        if use_cache and result:
            # Cache'i temiz tut (en fazla 100 kayıt)
            if len(self.cache) > 100:
                # En eski kayıtları sil
                old_keys = list(self.cache.keys())[:50]
                for key in old_keys:
                    del self.cache[key]
            
            self.cache[cache_key] = result
        
        return result
    
    def clear_cache(self):
        """Cache'i temizle"""
        self.cache.clear()


# Global indikatör instance
indicators = TechnicalIndicators()
