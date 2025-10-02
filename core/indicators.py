"""
OTT (Optimized Trend Tracker) ve diğer teknik indikatör hesaplamaları
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from .models import OTTResult, OTTMode
from .utils import logger


def calculate_cmo(prices: List[float], period: int = 9) -> List[float]:
    """
    Chande Momentum Oscillator (CMO) hesapla
    """
    try:
        if len(prices) < period + 1:
            return []
        
        cmo_values = []
        
        for i in range(period, len(prices)):
            # Son period+1 fiyatı al
            price_slice = prices[i-period:i+1]
            
            # Fiyat değişimlerini hesapla
            gains = []
            losses = []
            
            for j in range(1, len(price_slice)):
                change = price_slice[j] - price_slice[j-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            
            # CMO hesapla
            sum_gains = sum(gains)
            sum_losses = sum(losses)
            
            if sum_gains + sum_losses == 0:
                cmo = 0
            else:
                cmo = ((sum_gains - sum_losses) / (sum_gains + sum_losses)) * 100
            
            cmo_values.append(cmo)
        
        return cmo_values
        
    except Exception as e:
        logger.error(f"CMO hesaplama hatası: {e}")
        return []


def calculate_vidya(prices: List[float], period: int = 20, cmo_period: int = 9) -> List[float]:
    """
    VIDYA (Variable Index Dynamic Average) hesapla
    """
    try:
        if len(prices) < max(period, cmo_period) + 1:
            return []
        
        # CMO hesapla
        cmo_values = calculate_cmo(prices, cmo_period)
        
        if not cmo_values:
            return []
        
        # Alpha değeri
        alpha = 2.0 / (period + 1)
        
        # VIDYA hesaplama
        vidya_values = []
        vma = prices[period-1]  # İlk değer
        
        # CMO değerleri ile VIDYA hesapla
        start_idx = max(period, cmo_period)
        
        for i in range(start_idx, len(prices)):
            cmo_idx = i - start_idx
            if cmo_idx < len(cmo_values):
                cmo = cmo_values[cmo_idx]
                # VIDYA formülü: vma = vma[1] + alpha * abs(cmo) * (close - vma[1])
                vma = vma + alpha * abs(cmo) / 100.0 * (prices[i] - vma)
                vidya_values.append(vma)
            else:
                vidya_values.append(vma)
        
        return vidya_values
        
    except Exception as e:
        logger.error(f"VIDYA hesaplama hatası: {e}")
        return []


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """
    Exponential Moving Average hesapla - OVERFLOW KORUMALI VERSİYON
    """
    try:
        # Güvenlik kontrolleri - overflow önleme
        max_safe_value = 1e15  # 1 katrilyon - çok büyük değerler için limit
        min_safe_value = 1e-15  # Çok küçük değerler için limit
        
        if len(prices) < period or period <= 0:
            return []
        
        # Fiyat değerlerini güvenli aralıkta kontrol et
        safe_prices = []
        for price in prices:
            try:
                price_float = float(price)
                if abs(price_float) > max_safe_value or price_float <= 0:
                    logger.warning(f"EMA hesaplama - Geçersiz fiyat: {price_float}")
                    return []
                safe_prices.append(price_float)
            except (ValueError, TypeError, OverflowError):
                logger.warning(f"EMA hesaplama - Fiyat dönüşüm hatası: {price}")
                return []
        
        # NumPy ile daha hızlı hesaplama - overflow korumalı
        try:
            prices_array = np.array(safe_prices, dtype=float)
            alpha = 2.0 / (period + 1)
            
            # Alpha değeri kontrolü
            if alpha <= 0 or alpha > 1:
                logger.warning(f"EMA hesaplama - Geçersiz alpha: {alpha}")
                return []
            
            # İlk değer SMA - overflow korumalı
            sma_first = np.mean(prices_array[:period])
            if abs(sma_first) > max_safe_value or sma_first <= 0:
                logger.warning(f"EMA hesaplama - Geçersiz SMA: {sma_first}")
                return []
            
            ema_values = [sma_first]
            
            # EMA hesaplama - overflow korumalı
            for i in range(period, len(prices_array)):
                try:
                    ema = alpha * prices_array[i] + (1 - alpha) * ema_values[-1]
                    
                    # Overflow kontrolü
                    if abs(ema) > max_safe_value or ema <= 0:
                        logger.warning(f"EMA hesaplama - Overflow riski: {ema}")
                        # Son geçerli değeri kullan
                        ema = ema_values[-1]
                    
                    ema_values.append(ema)
                    
                except (OverflowError, ValueError) as e:
                    logger.warning(f"EMA hesaplama - Hesaplama hatası: {e}")
                    # Son geçerli değeri kullan
                    ema_values.append(ema_values[-1])
            
            return ema_values
            
        except (OverflowError, ValueError, ZeroDivisionError) as e:
            logger.error(f"EMA hesaplama - NumPy hatası: {e}")
            return []
            
    except Exception as e:
        logger.error(f"EMA hesaplama - Genel hata: {e}")
        return []


def calculate_sma(prices: List[float], period: int) -> List[float]:
    """
    Simple Moving Average hesapla - OVERFLOW KORUMALI VERSİYON
    """
    try:
        # Güvenlik kontrolleri - overflow önleme
        max_safe_value = 1e15  # 1 katrilyon - çok büyük değerler için limit
        min_safe_value = 1e-15  # Çok küçük değerler için limit
        
        if len(prices) < period or period <= 0:
            return []
        
        # Fiyat değerlerini güvenli aralıkta kontrol et
        safe_prices = []
        for price in prices:
            try:
                price_float = float(price)
                if abs(price_float) > max_safe_value or price_float <= 0:
                    logger.warning(f"SMA hesaplama - Geçersiz fiyat: {price_float}")
                    return []
                safe_prices.append(price_float)
            except (ValueError, TypeError, OverflowError):
                logger.warning(f"SMA hesaplama - Fiyat dönüşüm hatası: {price}")
                return []
        
        sma_values = []
        for i in range(period - 1, len(safe_prices)):
            window = safe_prices[i - period + 1:i + 1]
            if len(window) > 0 and period > 0:
                try:
                    sma = sum(window) / period
                    
                    # Overflow kontrolü
                    if abs(sma) > max_safe_value or sma <= 0:
                        logger.warning(f"SMA hesaplama - Overflow riski: {sma}")
                        # Son geçerli değeri kullan veya varsayılan değer
                        if sma_values:
                            sma = sma_values[-1]
                        else:
                            sma = safe_prices[i]  # Mevcut fiyatı kullan
                    
                    sma_values.append(sma)
                    
                except (OverflowError, ValueError, ZeroDivisionError) as e:
                    logger.warning(f"SMA hesaplama - Hesaplama hatası: {e}")
                    # Son geçerli değeri kullan veya mevcut fiyatı
                    if sma_values:
                        sma_values.append(sma_values[-1])
                    else:
                        sma_values.append(safe_prices[i])
        
        return sma_values
        
    except Exception as e:
        logger.error(f"SMA hesaplama - Genel hata: {e}")
        return []


def calculate_ott(close_prices: List[float], period: int, opt: float, strategy_name: str = "Unknown") -> Optional[OTTResult]:
    """
    OTT (Optimized Trend Tracker) hesapla - PINE SCRIPT MANTĞI
    
    Pine Script koduna göre:
    1. VIDYA (Variable Index Dynamic Average) hesapla
    2. Trailing stop mantığı ile longStop/shortStop hesapla
    3. OTT trend çizgisi hesapla
    4. OTT < OTT_SUP → AL, OTT ≥ OTT_SUP → SAT
    
    Args:
        close_prices: Kapanış fiyatları listesi
        period: VIDYA periyodu (20)
        opt: Factor değeri (2.0)
        strategy_name: Strateji adı (log için)
        
    Returns:
        OTTResult object veya None
    """
    try:
        # Güvenlik kontrolleri
        if len(close_prices) < period + 9:  # VIDYA için CMO(9) + period gerekli
            logger.warning(f"OTT hesaplama için yeterli veri yok. Gerekli: {period + 9}, Mevcut: {len(close_prices)}")
            return None
        
        # VIDYA (destek çizgisi) hesapla
        vidya_values = calculate_vidya(close_prices, period, cmo_period=9)
        
        if not vidya_values:
            logger.warning("VIDYA hesaplanamadı")
            return None
        
        # Son VIDYA değerini al (OTT_SUP)
        vma = float(vidya_values[-1])  # OTT_SUP (destek çizgisi)
        current_price = float(close_prices[-1])
        
        # Factor ve offset hesaplama
        factor = float(opt)  # opt = factor (2.0)
        offset = vma * factor / 100.0
        
        # Trailing stop hesaplama
        long_stop = vma - offset
        short_stop = vma + offset
        
        # Basit trend yönü belirleme (fiyat > vma → uptrend)
        dir_value = 1 if current_price > vma else -1
        
        # OTT trend çizgisi hesaplama
        if dir_value == 1:
            ott_line = long_stop * (1 + factor / 200)
        else:
            ott_line = short_stop * (1 - factor / 200)
        
        # OTT sinyal mantığı: OTT < OTT_SUP → AL, OTT ≥ OTT_SUP → SAT
        # ott_line = OTT, vma = OTT_SUP
        mode = OTTMode.AL if ott_line < vma else OTTMode.SAT
        
        logger.info(f"OTT Pine Script mantığı [{strategy_name}]:")
        logger.info(f"  VMA (OTT_SUP): {vma:.2f}")
        logger.info(f"  OTT Line: {ott_line:.2f}")
        logger.info(f"  Factor: {factor}, Offset: {offset:.2f}")
        logger.info(f"  Long Stop: {long_stop:.2f}, Short Stop: {short_stop:.2f}")
        logger.info(f"  Mode: {mode} (OTT {ott_line:.2f} {'<' if ott_line < vma else '>='} OTT_SUP {vma:.2f})")
        
        return OTTResult(
            mode=mode,
            baseline=ott_line,  # OTT trend çizgisi
            upper=short_stop,   # Resistance
            lower=long_stop,    # Support  
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
