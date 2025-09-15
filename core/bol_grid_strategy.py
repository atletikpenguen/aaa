"""
BOL-Grid Strategy Implementation
Bollinger Bands tabanlı Grid stratejisi
"""

import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from .base_strategy import BaseStrategy
from .models import (
    Strategy, State, TradingSignal, OrderSide, OTTMode, OTTResult, 
    MarketInfo, Trade, BollingerBands, BollingerPosition, BollingerCrossSignal
)
from .indicators import calculate_bollinger_bands
from .utils import (
    logger, round_to_tick, calculate_quantity
)
from .bol_grid_debug import get_bol_grid_debugger


class BollingerGridStrategy(BaseStrategy):
    """
    BOL-Grid strateji implementasyonu
    
    STRATEJI AKIŞI:
    1. İlk alım: Fiyat Bollinger Alt Bandını cross-above ile geçer
    2. Ek alımlar: Fiyat tekrar alt bandı geçer + min düşüş % sağlanır
    3. Kısmi satış: Fiyat orta/üst bandı cross-below + min kar % sağlanır
    4. Döngü kapanışı: Kalan pozisyon < initial_usdt/6
    
    DÖNGÜ SİSTEMİ:
    - D1-1: İlk döngü, ilk alım
    - D1-2: İlk döngü, ikinci alım
    - D1-3: İlk döngü, kısmi satış
    - D2-1: İkinci döngü başlangıcı
    """
    
    def __init__(self):
        super().__init__("BOL-Grid")
        # Environment'dan debug modunu al - Manuel olarak aktifleştir
        self.debug_enabled = True  # Manuel olarak aktifleştirildi
        self.detailed_debug = True  # Manuel olarak aktifleştirildi
    
    def _debug_log(self, strategy_id: str, message: str, level: str = "INFO"):
        """BOL-Grid özel debug log"""
        if self.debug_enabled:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_message = f"[BOL-GRID DEBUG] {strategy_id} | {timestamp} | {message}"
            
            if level == "ERROR":
                logger.error(log_message)
            elif level == "WARNING":
                logger.warning(log_message)
            else:
                logger.info(log_message)
    
    def _detailed_debug_log(self, strategy_id: str, section: str, data: Dict[str, Any], level: str = "INFO"):
        """BOL-Grid detaylı debug log - veri yapılarını güzel formatla"""
        if self.debug_enabled and self.detailed_debug:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # Veriyi güzel formatla
            formatted_data = []
            for key, value in data.items():
                if isinstance(value, float):
                    formatted_data.append(f"  {key}: {value:.6f}")
                elif isinstance(value, list):
                    if len(value) > 0 and isinstance(value[0], dict):
                        formatted_data.append(f"  {key}: [{len(value)} items]")
                        for i, item in enumerate(value[:3]):  # İlk 3 item
                            formatted_data.append(f"    [{i}] {item}")
                        if len(value) > 3:
                            formatted_data.append(f"    ... ve {len(value)-3} item daha")
                    else:
                        formatted_data.append(f"  {key}: {value}")
                else:
                    formatted_data.append(f"  {key}: {value}")
            
            data_str = "\n".join(formatted_data)
            log_message = f"[BOL-GRID DETAILED] {strategy_id} | {timestamp} | {section}\n{data_str}"
            
            if level == "ERROR":
                logger.error(log_message)
            elif level == "WARNING":
                logger.warning(log_message)
            else:
                logger.info(log_message)
    
    def _log_bollinger_analysis(self, strategy_id: str, current_price: float, bands: BollingerBands, cross_signal: BollingerCrossSignal):
        """Bollinger Bands analizini detaylı logla"""
        if self.debug_enabled and self.detailed_debug:
            # Fiyat pozisyonu hesapla - güvenli
            try:
                # Güvenli bölme işlemleri
                price_vs_upper = 0.0
                price_vs_middle = 0.0
                price_vs_lower = 0.0
                band_width = 0.0
                
                if bands.upper > 0:
                    price_vs_upper = ((current_price - bands.upper) / bands.upper) * 100
                if bands.middle > 0:
                    price_vs_middle = ((current_price - bands.middle) / bands.middle) * 100
                    band_width = ((bands.upper - bands.lower) / bands.middle) * 100
                if bands.lower > 0:
                    price_vs_lower = ((current_price - bands.lower) / bands.lower) * 100
                    
            except (ZeroDivisionError, TypeError, ValueError) as e:
                self._debug_log(strategy_id, f"⚠️ Bollinger analiz hesaplama hatası: {e}", "WARNING")
                price_vs_upper = price_vs_middle = price_vs_lower = band_width = 0.0
            
            analysis_data = {
                "current_price": current_price,
                "bollinger_bands": {
                    "upper": bands.upper,
                    "middle": bands.middle,
                    "lower": bands.lower
                },
                "price_position": {
                    "vs_upper_pct": price_vs_upper,
                    "vs_middle_pct": price_vs_middle,
                    "vs_lower_pct": price_vs_lower
                },
                "band_analysis": {
                    "width_pct": band_width,
                    "cross_signal": cross_signal.value
                }
            }
            
            self._detailed_debug_log(strategy_id, "📊 BOLLINGER BANDS ANALYSIS", analysis_data)
    
    def _log_cycle_status(self, strategy_id: str, custom_data: Dict[str, Any]):
        """Döngü durumunu detaylı logla"""
        if self.debug_enabled and self.detailed_debug:
            cycle_data = {
                "cycle_number": custom_data.get('cycle_number', 0),
                "cycle_step": custom_data.get('cycle_step', 'D0'),
                "cycle_trades": custom_data.get('cycle_trades', 0),
                "positions": {
                    "count": len(custom_data.get('positions', [])),
                    "total_quantity": custom_data.get('total_quantity', 0),
                    "average_cost": custom_data.get('average_cost', 0)
                },
                "price_tracking": {
                    "last_buy_price": custom_data.get('last_buy_price', 0),
                    "last_sell_price": custom_data.get('last_sell_price', 0)
                }
            }
            
            self._detailed_debug_log(strategy_id, "🔄 CYCLE STATUS", cycle_data)
    
    def _log_signal_decision(self, strategy_id: str, signal: TradingSignal, reason_data: Dict[str, Any]):
        """Sinyal kararını detaylı logla"""
        if self.debug_enabled and self.detailed_debug:
            signal_data = {
                "should_trade": signal.should_trade,
                "side": signal.side.value if signal.side else None,
                "quantity": signal.quantity,
                "reason": signal.reason,
                "decision_factors": reason_data
            }
            
            self._detailed_debug_log(strategy_id, "🎯 SIGNAL DECISION", signal_data)
    
    async def initialize_state(self, strategy: Strategy) -> Dict[str, Any]:
        """BOL-Grid için initial state"""
        self._debug_log(strategy.id, "🔧 BOL-Grid state initialize ediliyor")
        
        return {
            "cycle_number": 0,
            "cycle_step": "D0",
            "positions": [],
            "average_cost": 0.0,
            "total_quantity": 0.0,
            "last_bollinger": {
                "upper": 0.0,
                "middle": 0.0,
                "lower": 0.0
            },
            "last_prices": [],
            "last_buy_price": 0.0,
            "last_sell_price": 0.0,
            "cycle_trades": 0
        }
    
    def _detect_bollinger_cross(
        self, 
        current_price: float, 
        prev_price: float,
        current_bands: BollingerBands,
        prev_bands: BollingerBands
    ) -> BollingerCrossSignal:
        """Bollinger Band cross sinyallerini tespit et"""
        
        # Güvenlik kontrolleri
        if current_price <= 0 or prev_price <= 0:
            return BollingerCrossSignal.NO_CROSS
        
        if (current_bands.upper <= 0 or current_bands.middle <= 0 or current_bands.lower <= 0 or
            prev_bands.upper <= 0 or prev_bands.middle <= 0 or prev_bands.lower <= 0):
            return BollingerCrossSignal.NO_CROSS
        
        # Debug: Cross kontrollerini logla - strategy ID'ye ihtiyaç var
        # Bu fonksiyon strategy ID'siz çağrılıyor, o yüzden logger kullan
        from .utils import logger
        
        logger.info(f"🔍 CROSS DEBUG: prev_price={prev_price:.6f}, current_price={current_price:.6f}")
        logger.info(f"🔍 PREV BANDS: L={prev_bands.lower:.6f}, M={prev_bands.middle:.6f}, U={prev_bands.upper:.6f}")
        logger.info(f"🔍 CURR BANDS: L={current_bands.lower:.6f}, M={current_bands.middle:.6f}, U={current_bands.upper:.6f}")
        
        # Cross above lower band
        lower_cross_condition = prev_price <= prev_bands.lower and current_price > current_bands.lower
        logger.info(f"🔍 LOWER CROSS CHECK: prev_price <= prev_bands.lower ({prev_price:.6f} <= {prev_bands.lower:.6f}) = {prev_price <= prev_bands.lower}")
        logger.info(f"🔍 LOWER CROSS CHECK: current_price > current_bands.lower ({current_price:.6f} > {current_bands.lower:.6f}) = {current_price > current_bands.lower}")
        logger.info(f"🔍 LOWER CROSS RESULT: {lower_cross_condition}")
        
        if lower_cross_condition:
            logger.info(f"✅ CROSS_ABOVE_LOWER TESPIT EDILDI!")
            return BollingerCrossSignal.CROSS_ABOVE_LOWER
        
        # Cross below middle band
        middle_cross_condition = prev_price >= prev_bands.middle and current_price < current_bands.middle
        if middle_cross_condition:
            logger.info(f"✅ CROSS_BELOW_MIDDLE TESPIT EDILDI!")
            return BollingerCrossSignal.CROSS_BELOW_MIDDLE
            
        # Cross below upper band
        upper_cross_condition = prev_price >= prev_bands.upper and current_price < current_bands.upper
        if upper_cross_condition:
            logger.info(f"✅ CROSS_BELOW_UPPER TESPIT EDILDI!")
            return BollingerCrossSignal.CROSS_BELOW_UPPER
        
        logger.info(f"❌ NO_CROSS - hiçbir cross koşulu sağlanmadı")
        return BollingerCrossSignal.NO_CROSS
    
    def _calculate_average_cost(self, positions: List[Dict]) -> float:
        """Pozisyonların ağırlıklı ortalama maliyetini hesapla"""
        if not positions:
            return 0.0
        
        total_cost = sum(pos['quantity'] * pos['price'] for pos in positions)
        total_quantity = sum(pos['quantity'] for pos in positions)
        
        return total_cost / total_quantity if total_quantity > 0 else 0.0
    
    def _should_close_cycle(self, remaining_quantity: float, initial_usdt: float, current_price: float) -> bool:
        """Döngünün kapanıp kapanmayacağını kontrol et (1/6 kuralı)"""
        if remaining_quantity <= 0:
            return True
            
        remaining_value = remaining_quantity * current_price
        threshold = initial_usdt / 6
        
        return remaining_value < threshold
    
    def _get_bollinger_bands(self, ohlcv_data: List, period: int, std_dev: float) -> Tuple[BollingerBands, BollingerBands]:
        """Mevcut ve önceki Bollinger Bands'leri hesapla"""
        if not ohlcv_data or len(ohlcv_data) < period + 1:
            # Yetersiz veri durumunda default değerler
            default_bands = BollingerBands(upper=0.0, middle=0.0, lower=0.0)
            return default_bands, default_bands
        
        try:
            # Fiyat listesini hazırla - güvenli
            closes = []
            for candle in ohlcv_data:
                if len(candle) >= 5 and candle[4] is not None:
                    try:
                        price = float(candle[4])
                        if price > 0:  # Sıfırdan büyük fiyatları al
                            closes.append(price)
                    except (ValueError, TypeError):
                        continue
            
            if len(closes) < period + 1:
                default_bands = BollingerBands(upper=0.0, middle=0.0, lower=0.0)
                return default_bands, default_bands
            
            # Bollinger Bands hesapla
            bb_result = calculate_bollinger_bands(closes, period, std_dev)
            
            if not bb_result['upper'] or len(bb_result['upper']) < 2:
                default_bands = BollingerBands(upper=0.0, middle=0.0, lower=0.0)
                return default_bands, default_bands
            
            # Son ve önceki değerler - güvenli
            current_upper = bb_result['upper'][-1] if bb_result['upper'] else 0.0
            current_middle = bb_result['middle'][-1] if bb_result['middle'] else 0.0
            current_lower = bb_result['lower'][-1] if bb_result['lower'] else 0.0
            
            prev_upper = bb_result['upper'][-2] if len(bb_result['upper']) >= 2 else current_upper
            prev_middle = bb_result['middle'][-2] if len(bb_result['middle']) >= 2 else current_middle
            prev_lower = bb_result['lower'][-2] if len(bb_result['lower']) >= 2 else current_lower
            
            # Sıfır değerleri kontrol et
            if current_upper <= 0 or current_middle <= 0 or current_lower <= 0:
                default_bands = BollingerBands(upper=0.0, middle=0.0, lower=0.0)
                return default_bands, default_bands
            
            current_bands = BollingerBands(
                upper=current_upper,
                middle=current_middle,
                lower=current_lower
            )
            
            prev_bands = BollingerBands(
                upper=prev_upper,
                middle=prev_middle,
                lower=prev_lower
            )
            
            return current_bands, prev_bands
            
        except Exception as e:
            # Hata durumunda default değerler döndür
            default_bands = BollingerBands(upper=0.0, middle=0.0, lower=0.0)
            return default_bands, default_bands
    
    async def calculate_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        current_price: float, 
        ott_result: Optional[OTTResult],  # BOL-Grid'de kullanılmaz, None olabilir
        market_info: MarketInfo,
        ohlcv_data: list = None
    ) -> TradingSignal:
        """BOL-Grid sinyal hesaplama - Sadece Bollinger Bands kullanır, OTT kullanmaz"""
        
        # AŞAMA 1: Güvenlik kontrolleri
        self._debug_log(strategy.id, f"🔍 AŞAMA 1: Güvenlik kontrolleri başlıyor - Fiyat: {current_price}")
        if current_price <= 0:
            self._debug_log(strategy.id, f"❌ AŞAMA 1 HATA: Geçersiz fiyat: {current_price}", "ERROR")
            return TradingSignal(should_trade=False, reason="Geçersiz fiyat")
        self._debug_log(strategy.id, f"✅ AŞAMA 1: Güvenlik kontrolleri tamamlandı")
            
        self._debug_log(strategy.id, f"🔍 AŞAMA 2: BOL-Grid sinyal hesaplaması başlıyor - Fiyat: {current_price}")
        # Not: ott_result parametresi BOL-Grid'de kullanılmaz, None olarak gelir
        
        # AŞAMA 3: Parametreleri al
        self._debug_log(strategy.id, f"🔍 AŞAMA 3: Parametreler alınıyor")
        try:
            params = strategy.parameters
            initial_usdt = params.get('initial_usdt', 100.0)
            min_drop_pct = params.get('min_drop_pct', 2.0)
            min_profit_pct = params.get('min_profit_pct', 1.0)
            bollinger_period = params.get('bollinger_period', 250)
            bollinger_std = params.get('bollinger_std', 2.0)
            self._debug_log(strategy.id, f"✅ AŞAMA 3: Parametreler alındı - initial_usdt: {initial_usdt}, bollinger_period: {bollinger_period}")
        except Exception as e:
            self._debug_log(strategy.id, f"❌ AŞAMA 3 HATA: Parametre alma hatası: {e}", "ERROR")
            return TradingSignal(should_trade=False, reason=f"Parametre hatası: {e}")
        
        # AŞAMA 4: Detaylı parametre logu
        self._debug_log(strategy.id, f"🔍 AŞAMA 4: Parametre logu oluşturuluyor")
        try:
            param_data = {
                "initial_usdt": initial_usdt,
                "min_drop_pct": min_drop_pct,
                "min_profit_pct": min_profit_pct,
                "bollinger_period": bollinger_period,
                "bollinger_std": bollinger_std
            }
            self._detailed_debug_log(strategy.id, "⚙️ STRATEGY PARAMETERS", param_data)
            self._debug_log(strategy.id, f"✅ AŞAMA 4: Parametre logu tamamlandı")
        except Exception as e:
            self._debug_log(strategy.id, f"❌ AŞAMA 4 HATA: Parametre logu hatası: {e}", "ERROR")
        
        # AŞAMA 5: Mevcut state durumunu logla
        self._debug_log(strategy.id, f"🔍 AŞAMA 5: State durumu kontrol ediliyor")
        try:
            custom_data = state.custom_data or {}
            self._log_cycle_status(strategy.id, custom_data)
            self._debug_log(strategy.id, f"✅ AŞAMA 5: State durumu loglandı")
        except Exception as e:
            self._debug_log(strategy.id, f"❌ AŞAMA 5 HATA: State logu hatası: {e}", "ERROR")
        
        # AŞAMA 6: OHLCV verisi kontrolü
        self._debug_log(strategy.id, f"🔍 AŞAMA 6: OHLCV verisi kontrol ediliyor")
        if not ohlcv_data:
            self._debug_log(strategy.id, "❌ AŞAMA 6 HATA: OHLCV verisi yok, sinyal üretilemiyor", "WARNING")
            return TradingSignal(should_trade=False, reason="OHLCV verisi yok")
        self._debug_log(strategy.id, f"✅ AŞAMA 6: OHLCV verisi mevcut - {len(ohlcv_data)} veri noktası")
        
        # AŞAMA 7: Bollinger Bands hesapla
        self._debug_log(strategy.id, f"🔍 AŞAMA 7: Bollinger Bands hesaplanıyor - period: {bollinger_period}, std: {bollinger_std}")
        try:
            current_bands, prev_bands = self._get_bollinger_bands(ohlcv_data, bollinger_period, bollinger_std)
            prev_price = float(ohlcv_data[-2][4]) if len(ohlcv_data) >= 2 else current_price
            self._debug_log(strategy.id, f"✅ AŞAMA 7: Bollinger Bands hesaplandı - Upper: {current_bands.upper}, Middle: {current_bands.middle}, Lower: {current_bands.lower}")
            
            self._debug_log(strategy.id, f"📈 Bollinger Bands - Upper: {current_bands.upper:.4f}, Middle: {current_bands.middle:.4f}, Lower: {current_bands.lower:.4f}")
            
            # OHLCV veri analizi
            ohlcv_analysis = {
                "data_points": len(ohlcv_data),
                "current_price": current_price,
                "prev_price": prev_price,
                "price_change_pct": ((current_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0
            }
            self._detailed_debug_log(strategy.id, "📊 OHLCV DATA ANALYSIS", ohlcv_analysis)
            
        except Exception as e:
            self._debug_log(strategy.id, f"❌ AŞAMA 7 HATA: Bollinger Bands hesaplama hatası: {e}", "ERROR")
            return TradingSignal(should_trade=False, reason=f"Bollinger Bands hatası: {e}")
        
        # AŞAMA 8: Cross sinyalini tespit et
        self._debug_log(strategy.id, f"🔍 AŞAMA 8: Cross sinyali tespit ediliyor")
        try:
            cross_signal = self._detect_bollinger_cross(current_price, prev_price, current_bands, prev_bands)
            self._debug_log(strategy.id, f"✅ AŞAMA 8: Cross sinyali tespit edildi: {cross_signal}")
        except Exception as e:
            self._debug_log(strategy.id, f"❌ AŞAMA 8 HATA: Cross sinyal tespit hatası: {e}", "ERROR")
            return TradingSignal(should_trade=False, reason=f"Cross sinyal hatası: {e}")
        
        # AŞAMA 9: Bollinger Bands detaylı analizi
        self._debug_log(strategy.id, f"🔍 AŞAMA 9: Bollinger Bands detaylı analizi yapılıyor")
        try:
            self._log_bollinger_analysis(strategy.id, current_price, current_bands, cross_signal)
            self._debug_log(strategy.id, f"✅ AŞAMA 9: Bollinger Bands analizi tamamlandı")
        except Exception as e:
            self._debug_log(strategy.id, f"❌ AŞAMA 9 HATA: Bollinger analiz hatası: {e}", "ERROR")
        
        # AŞAMA 10: Cross sinyal kontrolü
        self._debug_log(strategy.id, f"🔍 AŞAMA 10: Cross sinyal kontrolü - Sinyal: {cross_signal}")
        if cross_signal != BollingerCrossSignal.NO_CROSS:
            self._debug_log(strategy.id, f"🎯 Cross tespit edildi: {cross_signal.value}")
        
        # AŞAMA 11: State'den pozisyon bilgilerini al
        self._debug_log(strategy.id, f"🔍 AŞAMA 11: State pozisyon bilgileri alınıyor")
        try:
            positions = state.custom_data.get('positions', [])
            average_cost = state.custom_data.get('average_cost', 0.0)
            total_quantity = state.custom_data.get('total_quantity', 0.0)
            cycle_number = state.custom_data.get('cycle_number', 0)
            cycle_step = state.custom_data.get('cycle_step', 'D0')
            last_buy_price = state.custom_data.get('last_buy_price', 0.0)
            self._debug_log(strategy.id, f"✅ AŞAMA 11: State bilgileri alındı - positions: {len(positions)}, avg_cost: {average_cost}, total_qty: {total_quantity}")
        except Exception as e:
            self._debug_log(strategy.id, f"❌ AŞAMA 11 HATA: State bilgileri alma hatası: {e}", "ERROR")
            return TradingSignal(should_trade=False, reason=f"State hatası: {e}")
        
        self._debug_log(strategy.id, f"💰 Mevcut durum: Pozisyon={len(positions)}, Toplam miktar={total_quantity}, Ort maliyet={average_cost}")
        
        # ALIM LOGİĞİ
        if cross_signal == BollingerCrossSignal.CROSS_ABOVE_LOWER:
            
            # İlk alım (döngü başlangıcı)
            if not positions:
                self._debug_log(strategy.id, "✅ İlk alım sinyali - Yeni döngü başlıyor")
                
                # Miktarı market adımlarına göre hesapla ve doğrula
                quantity, is_valid = calculate_quantity(
                    initial_usdt, current_price, market_info.step_size, market_info.min_qty
                )
                if not is_valid:
                    self._debug_log(strategy.id, "❌ İlk alım miktarı min_qty'yi sağlamıyor", "WARNING")
                    return TradingSignal(should_trade=False, reason="Minimum miktar sağlanmadı")
                from .utils import is_valid_min_notional
                if not is_valid_min_notional(quantity, current_price, market_info.min_notional):
                    self._debug_log(strategy.id, "❌ İlk alım min_notional'ı sağlamıyor", "WARNING")
                    return TradingSignal(should_trade=False, reason="Minimum notional sağlanmadı")
                
                # Detaylı alım kararı logu
                buy_decision_data = {
                    "action": "first_buy",
                    "cycle_number": cycle_number + 1,
                    "cycle_step": f'D{cycle_number + 1}-1',
                    "quantity": quantity,
                    "price": current_price,
                    "usdt_amount": initial_usdt,
                    "reason": "Alt band cross-above - İlk alım"
                }
                self._detailed_debug_log(strategy.id, "💰 FIRST BUY DECISION", buy_decision_data)
                
                signal = TradingSignal(
                    should_trade=True,
                    side=OrderSide.BUY,
                    quantity=quantity,
                    reason=f"BOL-Grid İlk Alım - Alt band cross-above @ {current_price}",
                    strategy_specific_data={
                        'cycle_action': 'first_buy',
                        'cycle_info': f'D{cycle_number + 1}-1',
                        'bollinger_bands': current_bands.dict()
                    }
                )
                
                self._log_signal_decision(strategy.id, signal, buy_decision_data)
                
                # Debug sistemi ile analiz logla
                if self.debug_enabled and self.detailed_debug:
                    debugger = get_bol_grid_debugger(strategy.id)
                    debugger.log_signal_analysis(
                        current_price=current_price,
                        bands=current_bands.dict(),
                        cross_signal=cross_signal.value,
                        positions=positions,
                        average_cost=average_cost,
                        decision=buy_decision_data
                    )
                
                return signal
            
            # Ek alım kontrolü
            else:
                # Aynı döngüde son alımın üstünde alım yapma
                if current_price >= last_buy_price:
                    self._debug_log(strategy.id, f"⚠️ Son alımın üstünde fiyat ({current_price} >= {last_buy_price}), alım yapılmıyor")
                    
                    # Detaylı red logu
                    reject_data = {
                        "action": "additional_buy_rejected",
                        "reason": "price_too_high",
                        "current_price": current_price,
                        "last_buy_price": last_buy_price,
                        "price_diff": current_price - last_buy_price,
                        "price_diff_pct": ((current_price - last_buy_price) / last_buy_price) * 100
                    }
                    self._detailed_debug_log(strategy.id, "❌ ADDITIONAL BUY REJECTED", reject_data)
                    
                    return TradingSignal(should_trade=False, reason="Son alımın üstünde fiyat")
                
                # Min düşüş kontrolü - güvenli hesaplama
                try:
                    if average_cost > 0:
                        drop_pct = ((average_cost - current_price) / average_cost) * 100
                    else:
                        drop_pct = 0.0
                        self._debug_log(strategy.id, "⚠️ Average cost 0, drop_pct = 0 olarak ayarlandı")
                except ZeroDivisionError:
                    drop_pct = 0.0
                    self._debug_log(strategy.id, "❌ Drop pct hesaplama hatası, 0 olarak ayarlandı")
                
                if drop_pct >= min_drop_pct:
                    self._debug_log(strategy.id, f"✅ Ek alım sinyali - Düşüş: {drop_pct:.2f}%")
                    
                    # Ek alım miktarını market kurallarına göre hesapla
                    quantity, is_valid = calculate_quantity(
                        initial_usdt, current_price, market_info.step_size, market_info.min_qty
                    )
                    if not is_valid:
                        self._debug_log(strategy.id, "❌ Ek alım miktarı min_qty'yi sağlamıyor", "WARNING")
                        return TradingSignal(should_trade=False, reason="Minimum miktar sağlanmadı")
                    from .utils import is_valid_min_notional
                    if not is_valid_min_notional(quantity, current_price, market_info.min_notional):
                        self._debug_log(strategy.id, "❌ Ek alım min_notional'ı sağlamıyor", "WARNING")
                        return TradingSignal(should_trade=False, reason="Minimum notional sağlanmadı")
                    cycle_trades = state.custom_data.get('cycle_trades', 0) + 1
                    
                    # Detaylı ek alım kararı logu
                    additional_buy_data = {
                        "action": "additional_buy",
                        "cycle_number": cycle_number,
                        "cycle_step": f'D{cycle_number}-{cycle_trades + 1}',
                        "quantity": quantity,
                        "price": current_price,
                        "usdt_amount": initial_usdt,
                        "drop_pct": drop_pct,
                        "min_drop_required": min_drop_pct,
                        "average_cost": average_cost,
                        "reason": f"Alt band cross-above + {drop_pct:.2f}% düşüş"
                    }
                    self._detailed_debug_log(strategy.id, "💰 ADDITIONAL BUY DECISION", additional_buy_data)
                    
                    signal = TradingSignal(
                        should_trade=True,
                        side=OrderSide.BUY,
                        quantity=quantity,
                        reason=f"BOL-Grid Ek Alım - {drop_pct:.2f}% düşüş @ {current_price}",
                        strategy_specific_data={
                            'cycle_action': 'additional_buy',
                            'cycle_info': f'D{cycle_number}-{cycle_trades + 1}',
                            'bollinger_bands': current_bands.dict()
                        }
                    )
                    
                    self._log_signal_decision(strategy.id, signal, additional_buy_data)
                    
                    # Debug sistemi ile analiz logla
                    if self.debug_enabled and self.detailed_debug:
                        debugger = get_bol_grid_debugger(strategy.id)
                        debugger.log_signal_analysis(
                            current_price=current_price,
                            bands=current_bands.dict(),
                            cross_signal=cross_signal.value,
                            positions=positions,
                            average_cost=average_cost,
                            decision=additional_buy_data
                        )
                    
                    return signal
                else:
                    self._debug_log(strategy.id, f"⚠️ Yetersiz düşüş ({drop_pct:.2f}% < {min_drop_pct}%), alım yapılmıyor")
                    
                    # Detaylı red logu
                    reject_data = {
                        "action": "additional_buy_rejected",
                        "reason": "insufficient_drop",
                        "drop_pct": drop_pct,
                        "min_drop_required": min_drop_pct,
                        "current_price": current_price,
                        "average_cost": average_cost,
                        "price_diff": average_cost - current_price
                    }
                    self._detailed_debug_log(strategy.id, "❌ ADDITIONAL BUY REJECTED", reject_data)
        
        # SATIŞ LOGİĞİ
        elif cross_signal in [BollingerCrossSignal.CROSS_BELOW_MIDDLE, BollingerCrossSignal.CROSS_BELOW_UPPER]:
            
            if positions and total_quantity > 0:
                # Min kar kontrolü - güvenli hesaplama
                try:
                    if average_cost > 0:
                        profit_pct = ((current_price - average_cost) / average_cost) * 100
                    else:
                        profit_pct = 0.0
                        self._debug_log(strategy.id, "⚠️ Average cost 0, profit_pct = 0 olarak ayarlandı")
                except ZeroDivisionError:
                    profit_pct = 0.0
                    self._debug_log(strategy.id, "❌ Profit pct hesaplama hatası, 0 olarak ayarlandı")
                
                if profit_pct >= min_profit_pct:
                    
                    # Döngü kapanış kontrolü
                    if self._should_close_cycle(total_quantity, initial_usdt, current_price):
                        self._debug_log(strategy.id, f"✅ Döngü kapanış sinyali - Tüm pozisyon satılacak")
                        
                        # Detaylı döngü kapanış logu
                        cycle_close_data = {
                            "action": "cycle_close",
                            "cycle_number": cycle_number,
                            "cycle_step": f'D{cycle_number} (TAMAMLANDI)',
                            "quantity": total_quantity,
                            "price": current_price,
                            "profit_pct": profit_pct,
                            "min_profit_required": min_profit_pct,
                            "average_cost": average_cost,
                            "remaining_value": total_quantity * current_price,
                            "threshold": initial_usdt / 6,
                            "reason": f"Orta/üst band cross-below + {profit_pct:.2f}% kar + 1/6 kuralı"
                        }
                        self._detailed_debug_log(strategy.id, "🔄 CYCLE CLOSE DECISION", cycle_close_data)
                        
                        signal = TradingSignal(
                            should_trade=True,
                            side=OrderSide.SELL,
                            quantity=total_quantity,
                            reason=f"BOL-Grid Döngü Kapanış - {profit_pct:.2f}% kar @ {current_price}",
                            strategy_specific_data={
                                'cycle_action': 'cycle_close',
                                'cycle_info': f'D{cycle_number} (TAMAMLANDI)',
                                'bollinger_bands': current_bands.dict()
                            }
                        )
                        
                        self._log_signal_decision(strategy.id, signal, cycle_close_data)
                        
                        # Debug sistemi ile analiz logla
                        if self.debug_enabled and self.detailed_debug:
                            debugger = get_bol_grid_debugger(strategy.id)
                            debugger.log_signal_analysis(
                                current_price=current_price,
                                bands=current_bands.dict(),
                                cross_signal=cross_signal.value,
                                positions=positions,
                                average_cost=average_cost,
                                decision=cycle_close_data
                            )
                        
                        return signal
                    
                    # Kısmi satış (yarı yarıya)
                    else:
                        # Kısmi satış miktarını step_size'a indir ve min_qty kontrolü yap
                        from .utils import floor_to_step, is_valid_min_qty, is_valid_min_notional
                        sell_quantity = floor_to_step(total_quantity / 2, market_info.step_size)
                        if not is_valid_min_qty(sell_quantity, market_info.min_qty):
                            self._debug_log(strategy.id, "❌ Kısmi satış miktarı min_qty'nin altında", "WARNING")
                            return TradingSignal(should_trade=False, reason="Minimum miktar sağlanmadı")
                        if not is_valid_min_notional(sell_quantity, current_price, market_info.min_notional):
                            self._debug_log(strategy.id, "❌ Kısmi satış min_notional'ı sağlamıyor", "WARNING")
                            return TradingSignal(should_trade=False, reason="Minimum notional sağlanmadı")
                        cycle_trades = state.custom_data.get('cycle_trades', 0) + 1
                        
                        self._debug_log(strategy.id, f"✅ Kısmi satış sinyali - {sell_quantity} miktar satılacak")
                        
                        # Detaylı kısmi satış logu
                        partial_sell_data = {
                            "action": "partial_sell",
                            "cycle_number": cycle_number,
                            "cycle_step": f'D{cycle_number}-{cycle_trades + 1}',
                            "quantity": sell_quantity,
                            "price": current_price,
                            "profit_pct": profit_pct,
                            "min_profit_required": min_profit_pct,
                            "average_cost": average_cost,
                            "remaining_quantity": total_quantity - sell_quantity,
                            "remaining_value": (total_quantity - sell_quantity) * current_price,
                            "threshold": initial_usdt / 6,
                            "reason": f"Orta/üst band cross-below + {profit_pct:.2f}% kar"
                        }
                        self._detailed_debug_log(strategy.id, "💰 PARTIAL SELL DECISION", partial_sell_data)
                        
                        signal = TradingSignal(
                            should_trade=True,
                            side=OrderSide.SELL,
                            quantity=sell_quantity,
                            reason=f"BOL-Grid Kısmi Satış - {profit_pct:.2f}% kar @ {current_price}",
                            strategy_specific_data={
                                'cycle_action': 'partial_sell',
                                'cycle_info': f'D{cycle_number}-{cycle_trades + 1}',
                                'bollinger_bands': current_bands.dict()
                            }
                        )
                        
                        self._log_signal_decision(strategy.id, signal, partial_sell_data)
                        
                        # Debug sistemi ile analiz logla
                        if self.debug_enabled and self.detailed_debug:
                            debugger = get_bol_grid_debugger(strategy.id)
                            debugger.log_signal_analysis(
                                current_price=current_price,
                                bands=current_bands.dict(),
                                cross_signal=cross_signal.value,
                                positions=positions,
                                average_cost=average_cost,
                                decision=partial_sell_data
                            )
                        
                        return signal
                else:
                    self._debug_log(strategy.id, f"⚠️ Yetersiz kar ({profit_pct:.2f}% < {min_profit_pct}%), satış yapılmıyor")
                    
                    # Detaylı red logu
                    reject_data = {
                        "action": "sell_rejected",
                        "reason": "insufficient_profit",
                        "profit_pct": profit_pct,
                        "min_profit_required": min_profit_pct,
                        "current_price": current_price,
                        "average_cost": average_cost,
                        "price_diff": current_price - average_cost
                    }
                    self._detailed_debug_log(strategy.id, "❌ SELL REJECTED", reject_data)
        
        # Sinyal yok - debug logla
        no_signal_data = {
            "action": "no_signal",
            "reason": "BOL-Grid sinyal koşulları sağlanmadı",
            "cross_signal": cross_signal.value,
            "positions_exist": len(positions) > 0,
            "current_price": current_price
        }
        self._detailed_debug_log(strategy.id, "❌ NO SIGNAL", no_signal_data)
        
        # Debug sistemi ile analiz logla
        if self.debug_enabled and self.detailed_debug:
            debugger = get_bol_grid_debugger(strategy.id)
            debugger.log_signal_analysis(
                current_price=current_price,
                bands=current_bands.dict(),
                cross_signal=cross_signal.value,
                positions=positions,
                average_cost=average_cost,
                decision=no_signal_data
            )
        
        return TradingSignal(should_trade=False, reason="BOL-Grid sinyal koşulları sağlanmadı")
    
    async def process_fill(
        self, 
        strategy: Strategy, 
        state: State, 
        trade: Trade
    ) -> Dict[str, Any]:
        """Fill işlemi sonrası state güncelleme"""
        
        self._debug_log(strategy.id, f"🔄 Fill işlemi işleniyor: {trade.side} {trade.quantity} @ {trade.price}")
        
        # Trade'den strateji özel verilerini al
        strategy_data = trade.strategy_specific_data or {}
        cycle_action = strategy_data.get('cycle_action', '')
        
        # Mevcut state verilerini al
        custom_data = state.custom_data or {}
        positions = custom_data.get('positions', [])
        cycle_number = custom_data.get('cycle_number', 0)
        cycle_trades = custom_data.get('cycle_trades', 0)
        
        # Fill işlemi öncesi durum
        pre_fill_data = {
            "trade": {
                "side": trade.side.value,
                "quantity": trade.quantity,
                "price": trade.price,
                "cycle_action": cycle_action
            },
            "current_state": {
                "cycle_number": cycle_number,
                "cycle_trades": cycle_trades,
                "positions_count": len(positions),
                "total_quantity": custom_data.get('total_quantity', 0),
                "average_cost": custom_data.get('average_cost', 0)
            }
        }
        self._detailed_debug_log(strategy.id, "🔄 PRE-FILL STATE", pre_fill_data)
        
        if trade.side == OrderSide.BUY:
            # Yeni pozisyon ekle
            positions.append({
                'quantity': trade.quantity,
                'price': trade.price,
                'timestamp': trade.timestamp.isoformat()
            })
            
            # İlk alımsa döngü numarasını artır
            if cycle_action == 'first_buy':
                cycle_number += 1
                cycle_trades = 1
            else:
                cycle_trades += 1
            
            # Ortalama maliyet ve toplam miktar hesapla
            total_cost = sum(pos['quantity'] * pos['price'] for pos in positions)
            total_quantity = sum(pos['quantity'] for pos in positions)
            average_cost = total_cost / total_quantity if total_quantity > 0 else 0.0
            
            # Son alım fiyatını güncelle
            last_buy_price = trade.price
            
            self._debug_log(strategy.id, f"💰 Alım sonrası: Toplam miktar={total_quantity}, Ort maliyet={average_cost}")
            
            # Fill işlemi sonrası durum
            post_fill_data = {
                "action": "buy_fill_processed",
                "new_state": {
                    "cycle_number": cycle_number,
                    "cycle_step": f'D{cycle_number}-{cycle_trades}',
                    "cycle_trades": cycle_trades,
                    "positions_count": len(positions),
                    "total_quantity": total_quantity,
                    "average_cost": average_cost,
                    "last_buy_price": last_buy_price
                },
                "calculation": {
                    "total_cost": sum(pos['quantity'] * pos['price'] for pos in positions),
                    "new_position": {
                        "quantity": trade.quantity,
                        "price": trade.price
                    }
                }
            }
            self._detailed_debug_log(strategy.id, "💰 POST-FILL STATE (BUY)", post_fill_data)
            
            # Debug sistemi ile trade execution logla
            if self.debug_enabled and self.detailed_debug:
                debugger = get_bol_grid_debugger(strategy.id)
                debugger.log_trade_execution(
                    trade_side=trade.side.value,
                    quantity=trade.quantity,
                    price=trade.price,
                    cycle_info=strategy_data.get('cycle_info', ''),
                    before_state=custom_data,
                    after_state={
                        'positions': positions,
                        'average_cost': average_cost,
                        'total_quantity': total_quantity,
                        'cycle_number': cycle_number,
                        'cycle_step': f'D{cycle_number}-{cycle_trades}',
                        'cycle_trades': cycle_trades,
                        'last_buy_price': last_buy_price
                    }
                )
            
            return {
                'positions': positions,
                'average_cost': average_cost,
                'total_quantity': total_quantity,
                'cycle_number': cycle_number,
                'cycle_step': f'D{cycle_number}-{cycle_trades}',
                'cycle_trades': cycle_trades,
                'last_buy_price': last_buy_price
            }
        
        elif trade.side == OrderSide.SELL:
            
            if cycle_action == 'cycle_close':
                # Döngü kapanışı - tüm pozisyonları temizle
                self._debug_log(strategy.id, f"🔄 Döngü {cycle_number} tamamlandı, yeni döngü bekleniyor")
                
                # Döngü kapanış detaylı logu
                cycle_close_data = {
                    "action": "cycle_close_fill_processed",
                    "cycle_number": cycle_number,
                    "sold_quantity": trade.quantity,
                    "sell_price": trade.price,
                    "new_state": {
                        "cycle_number": cycle_number,
                        "cycle_step": 'D0',
                        "cycle_trades": 0,
                        "positions_count": 0,
                        "total_quantity": 0.0,
                        "average_cost": 0.0,
                        "last_sell_price": trade.price
                    }
                }
                self._detailed_debug_log(strategy.id, "🔄 CYCLE CLOSE FILL PROCESSED", cycle_close_data)
                
                # Debug sistemi ile trade execution ve döngü geçişi logla
                if self.debug_enabled and self.detailed_debug:
                    debugger = get_bol_grid_debugger(strategy.id)
                    
                    # Trade execution logla
                    debugger.log_trade_execution(
                        trade_side=trade.side.value,
                        quantity=trade.quantity,
                        price=trade.price,
                        cycle_info=strategy_data.get('cycle_info', ''),
                        before_state=custom_data,
                        after_state={
                            'positions': [],
                            'average_cost': 0.0,
                            'total_quantity': 0.0,
                            'cycle_number': cycle_number,
                            'cycle_step': 'D0',
                            'cycle_trades': 0,
                            'last_buy_price': 0.0,
                            'last_sell_price': trade.price
                        }
                    )
                    
                    # Döngü geçişi logla
                    debugger.log_cycle_transition(
                        from_cycle=f'D{cycle_number}',
                        to_cycle='D0',
                        reason='Cycle completed - all positions sold',
                        cycle_data=cycle_close_data
                    )
                
                return {
                    'positions': [],
                    'average_cost': 0.0,
                    'total_quantity': 0.0,
                    'cycle_number': cycle_number,
                    'cycle_step': 'D0',
                    'cycle_trades': 0,
                    'last_buy_price': 0.0,
                    'last_sell_price': trade.price
                }
            
            else:
                # Kısmi satış - pozisyonlardan orantılı olarak düş
                remaining_quantity = sum(pos['quantity'] for pos in positions) - trade.quantity
                
                if remaining_quantity <= 0:
                    # Tüm pozisyon satıldı
                    positions = []
                    average_cost = 0.0
                    total_quantity = 0.0
                else:
                    # Pozisyonları orantılı olarak azalt
                    sell_ratio = trade.quantity / sum(pos['quantity'] for pos in positions)
                    
                    for pos in positions:
                        pos['quantity'] *= (1 - sell_ratio)
                    
                    # Çok küçük pozisyonları temizle
                    positions = [pos for pos in positions if pos['quantity'] > 0.000001]
                    
                    total_quantity = sum(pos['quantity'] for pos in positions)
                    average_cost = self._calculate_average_cost(positions)
                
                cycle_trades += 1
                
                self._debug_log(strategy.id, f"💰 Kısmi satış sonrası: Kalan miktar={total_quantity}, Ort maliyet={average_cost}")
                
                # Kısmi satış detaylı logu
                partial_sell_data = {
                    "action": "partial_sell_fill_processed",
                    "cycle_number": cycle_number,
                    "cycle_step": f'D{cycle_number}-{cycle_trades}',
                    "sold_quantity": trade.quantity,
                    "sell_price": trade.price,
                    "sell_ratio": sell_ratio if 'sell_ratio' in locals() else 0,
                    "new_state": {
                        "cycle_number": cycle_number,
                        "cycle_trades": cycle_trades,
                        "positions_count": len(positions),
                        "total_quantity": total_quantity,
                        "average_cost": average_cost,
                        "last_sell_price": trade.price
                    },
                    "calculation": {
                        "remaining_quantity": remaining_quantity,
                        "positions_after_sell": positions
                    }
                }
                self._detailed_debug_log(strategy.id, "💰 PARTIAL SELL FILL PROCESSED", partial_sell_data)
                
                # Debug sistemi ile trade execution logla
                if self.debug_enabled and self.detailed_debug:
                    debugger = get_bol_grid_debugger(strategy.id)
                    debugger.log_trade_execution(
                        trade_side=trade.side.value,
                        quantity=trade.quantity,
                        price=trade.price,
                        cycle_info=strategy_data.get('cycle_info', ''),
                        before_state=custom_data,
                        after_state={
                            'positions': positions,
                            'average_cost': average_cost,
                            'total_quantity': total_quantity,
                            'cycle_number': cycle_number,
                            'cycle_step': f'D{cycle_number}-{cycle_trades}',
                            'cycle_trades': cycle_trades,
                            'last_sell_price': trade.price
                        }
                    )
                
                return {
                    'positions': positions,
                    'average_cost': average_cost,
                    'total_quantity': total_quantity,
                    'cycle_number': cycle_number,
                    'cycle_step': f'D{cycle_number}-{cycle_trades}',
                    'cycle_trades': cycle_trades,
                    'last_sell_price': trade.price
                }
        
        # Değişiklik yok
        return {}
