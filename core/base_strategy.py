"""
Base Strategy abstract class - Tüm strateji türleri için ortak interface
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from datetime import datetime, timezone

from .models import Strategy, State, TradingSignal, MarketInfo, OTTResult, Trade
from .utils import logger


class BaseStrategy(ABC):
    """
    Tüm strateji türleri için abstract base class
    Her yeni strateji bu sınıftan inherit edecek
    """
    
    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        logger.info(f"Strateji oluşturuldu: {strategy_name}")
    
    @abstractmethod
    async def calculate_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        current_price: float, 
        ott_result: OTTResult,
        market_info: MarketInfo,
        ohlcv_data: list = None
    ) -> TradingSignal:
        """
        Ana sinyal hesaplama metodu - her strateji implement etmeli
        
        Args:
            strategy: Strateji konfigürasyonu
            state: Mevcut durum
            current_price: Güncel fiyat
            ott_result: OTT hesaplama sonucu
            market_info: Market metadata
            ohlcv_data: OHLCV verisi (opsiyonel, bazı stratejiler için)
            
        Returns:
            TradingSignal: İşlem sinyali
        """
        pass
    
    @abstractmethod
    async def initialize_state(self, strategy: Strategy) -> Dict[str, Any]:
        """
        Strateji için initial state oluştur
        
        Args:
            strategy: Strateji konfigürasyonu
            
        Returns:
            Dict: Custom_data için initial değerler
        """
        pass
    
    @abstractmethod
    async def process_fill(
        self, 
        strategy: Strategy, 
        state: State, 
        trade: Trade
    ) -> Dict[str, Any]:
        """
        Fill işlemi sonrası state güncelleme
        
        Args:
            strategy: Strateji konfigürasyonu
            state: Mevcut durum
            trade: Gerçekleşen işlem
            
        Returns:
            Dict: State için custom_data güncellemeleri
        """
        pass
    
    def _check_price_limits(self, strategy: Strategy, current_price: float) -> tuple[bool, str]:
        """
        Ortak fiyat limitleri kontrolü
        """
        # Min fiyat kontrolü
        if strategy.price_min is not None and strategy.price_min > 0:
            if current_price < strategy.price_min:
                return False, f"Fiyat minimum limit altında: {current_price} < {strategy.price_min}"
        
        # Max fiyat kontrolü  
        if strategy.price_max is not None and strategy.price_max > 0:
            if current_price > strategy.price_max:
                return False, f"Fiyat maksimum limit üstünde: {current_price} > {strategy.price_max}"
        
        # Limit geçerliliği kontrolü
        if (strategy.price_min is not None and strategy.price_min > 0 and 
            strategy.price_max is not None and strategy.price_max > 0):
            if strategy.price_min >= strategy.price_max:
                return False, f"Geçersiz limit aralığı: min ({strategy.price_min}) >= max ({strategy.price_max})"
        
        return True, "Fiyat limitleri içinde"
    
    def get_parameter(self, strategy: Strategy, key: str, default=None):
        """
        Strateji parametresi al - legacy alanları da kontrol et
        """
        # Önce parameters dict'ten al
        if key in strategy.parameters:
            return strategy.parameters[key]
        
        # Legacy alanları kontrol et
        if hasattr(strategy, key) and getattr(strategy, key) is not None:
            return getattr(strategy, key)
        
        return default
    
    async def validate_strategy_config(self, strategy: Strategy) -> tuple[bool, str]:
        """
        Strateji konfigürasyonunu validate et - override edilebilir
        """
        return True, "Konfigürasyon geçerli"
    
    def get_custom_data(self, state: State, key: str, default=None):
        """
        State'den custom data al
        """
        return state.custom_data.get(key, default)
    
    def set_custom_data(self, state: State, key: str, value: Any):
        """
        State'e custom data kaydet
        """
        if not hasattr(state, 'custom_data') or state.custom_data is None:
            state.custom_data = {}
        state.custom_data[key] = value
    
    def log_strategy_action(self, strategy_id: str, action: str, details: str = ""):
        """
        Strateji özel log yazma
        """
        logger.info(f"[{self.strategy_name}] {strategy_id}: {action} {details}")
    
    def log_signal(self, strategy_id: str, signal: TradingSignal):
        """
        Sinyal log yazma
        """
        if signal.should_trade:
            action = f"{signal.side.value.upper()} @ {signal.target_price} qty: {signal.quantity}"
            self.log_strategy_action(strategy_id, "SIGNAL", action)
        else:
            self.log_strategy_action(strategy_id, "NO_SIGNAL", signal.reason)
