"""
Grid + OTT Strategy Implementation
Mevcut grid.py'daki logic'i yeni mimariye uyarladık
"""

import math
from typing import Dict, Any
from datetime import datetime, timezone

from .base_strategy import BaseStrategy
from .models import (
    Strategy, State, TradingSignal, OrderSide, OTTMode, OTTResult, 
    MarketInfo, Trade, GridSignal
)
from .utils import (
    logger, round_to_tick, calculate_quantity
)


class GridOTTStrategy(BaseStrategy):
    """Grid + OTT strateji implementasyonu"""
    
    def __init__(self):
        super().__init__("Grid+OTT")
    
    async def initialize_state(self, strategy: Strategy) -> Dict[str, Any]:
        """Grid+OTT için initial state"""
        return {
            "gf_initialized": False,
            "last_grid_z": 0
        }
    
    async def calculate_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        current_price: float, 
        ott_result: OTTResult,
        market_info: MarketInfo,
        ohlcv_data: list = None
    ) -> TradingSignal:
        """Grid+OTT sinyal hesaplama"""
        
        # Fiyat limitleri kontrolü
        price_valid, price_reason = self._check_price_limits(strategy, current_price)
        if not price_valid:
            return TradingSignal(
                should_trade=False,
                reason=price_reason
            )
        
        # Grid parametrelerini al
        y = self.get_parameter(strategy, 'y')
        usdt_grid = self.get_parameter(strategy, 'usdt_grid')
        
        if not y or not usdt_grid:
            return TradingSignal(
                should_trade=False,
                reason="Grid parametreleri eksik: y ve usdt_grid gerekli"
            )
        
        # GF kontrolü - 0 ise ilk fiyatı GF yap
        gf = state.gf if state.gf is not None else 0
        if gf == 0:
            gf = current_price
            state.gf = gf
            self.set_custom_data(state, "gf_initialized", True)
            self.log_strategy_action(strategy.id, "GF_INIT", f"GF = {gf}")
        
        # Grid sinyali hesapla (mevcut algoritma)
        grid_signal = await self._calculate_grid_signal(
            strategy, state, current_price, gf, ott_result, market_info, y, usdt_grid
        )
        
        # GridSignal'i TradingSignal'e çevir
        if grid_signal.should_trade:
            return TradingSignal(
                should_trade=True,
                side=grid_signal.side,
                target_price=grid_signal.target_price,
                quantity=grid_signal.quantity,
                reason=grid_signal.reason,
                strategy_specific_data={
                    "z": grid_signal.z,
                    "delta": grid_signal.delta,
                    "gf": gf
                }
            )
        else:
            return TradingSignal(
                should_trade=False,
                reason=grid_signal.reason
            )
    
    async def _calculate_grid_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        current_price: float, 
        gf: float,
        ott_result: OTTResult,
        market_info: MarketInfo,
        y: float,
        usdt_grid: float
    ) -> GridSignal:
        """Grid sinyal hesaplama (mevcut algoritma)"""
        
        # OTT moduna göre işlem yönü
        if ott_result.mode == OTTMode.AL:
            return await self._calculate_buy_signal(
                strategy, state, current_price, gf, market_info, y, usdt_grid
            )
        else:  # SAT
            return await self._calculate_sell_signal(
                strategy, state, current_price, gf, market_info, y, usdt_grid
            )
    
    async def _calculate_buy_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        current_price: float, 
        gf: float,
        market_info: MarketInfo,
        y: float,
        usdt_grid: float
    ) -> GridSignal:
        """AL modu - Alım sinyali hesapla"""
        
        # AL kuralı: price < GF olmalı
        if current_price >= gf:
            return GridSignal(
                should_trade=False,
                reason=f"AL modu: price ({current_price}) >= GF ({gf})"
            )
        
        # Delta hesapla
        delta = gf - current_price
        
        # Eşik kontrolü: Δ > y (hassas karşılaştırma)
        if delta <= y:
            return GridSignal(
                should_trade=False,
                reason=f"AL modu: delta ({delta:.6f}) <= y ({y}) - grid aralığı yetersiz"
            )
        
        # z hesapla
        z = math.floor(delta / y)
        if z < 1:
            return GridSignal(
                should_trade=False,
                reason=f"AL modu: z ({z}) < 1 - grid seviyesi yetersiz"
            )
        
        # Debug log
        self.log_strategy_action(
            strategy.id,
            "GRID_CALC_AL",
            f"Delta: {delta:.6f}, y: {y}, z: {z}, target_price: {gf - (z * y):.6f}"
        )
        
        # Hedef fiyat: P_buy = GF - z*y
        target_price = gf - (z * y)
        target_price = round_to_tick(target_price, market_info.tick_size)
        
        # Hedef fiyat limit kontrolü
        price_valid, price_reason = self._check_price_limits(strategy, target_price)
        if not price_valid:
            return GridSignal(
                should_trade=False,
                reason=f"AL modu: {price_reason}"
            )
        
        # Miktar hesapla
        notional = z * usdt_grid
        quantity, is_valid = calculate_quantity(
            notional, target_price, market_info.step_size, market_info.min_qty
        )
        
        if not is_valid:
            return GridSignal(
                should_trade=False,
                reason=f"AL modu: miktar geçersiz ({quantity} < {market_info.min_qty})"
            )
        
        # Duplicate kontrol
        has_duplicate = await self._check_duplicate_order(
            state, OrderSide.BUY, target_price
        )
        
        if has_duplicate:
            return GridSignal(
                should_trade=False,
                reason=f"AL modu: duplicate emir mevcut (price: {target_price})"
            )
        
        return GridSignal(
            should_trade=True,
            side=OrderSide.BUY,
            z=z,
            target_price=target_price,
            quantity=quantity,
            delta=delta,
            reason=f"AL sinyali: z={z}, price={target_price}, qty={quantity}"
        )
    
    async def _calculate_sell_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        current_price: float, 
        gf: float,
        market_info: MarketInfo,
        y: float,
        usdt_grid: float
    ) -> GridSignal:
        """SAT modu - Satım sinyali hesapla"""
        
        # SAT kuralı: price > GF olmalı  
        if current_price <= gf:
            return GridSignal(
                should_trade=False,
                reason=f"SAT modu: price ({current_price}) <= GF ({gf})"
            )
        
        # Delta hesapla
        delta = current_price - gf
        
        # Eşik kontrolü: Δ > y (hassas karşılaştırma)
        if delta <= y:
            return GridSignal(
                should_trade=False,
                reason=f"SAT modu: delta ({delta:.6f}) <= y ({y}) - grid aralığı yetersiz"
            )
        
        # z hesapla
        z = math.floor(delta / y)
        if z < 1:
            return GridSignal(
                should_trade=False,
                reason=f"SAT modu: z ({z}) < 1 - grid seviyesi yetersiz"
            )
        
        # Debug log
        self.log_strategy_action(
            strategy.id,
            "GRID_CALC_SAT",
            f"Delta: {delta:.6f}, y: {y}, z: {z}, target_price: {gf + (z * y):.6f}"
        )
        
        # Hedef fiyat: P_sell = GF + z*y
        target_price = gf + (z * y)
        target_price = round_to_tick(target_price, market_info.tick_size)
        
        # Hedef fiyat limit kontrolü
        price_valid, price_reason = self._check_price_limits(strategy, target_price)
        if not price_valid:
            return GridSignal(
                should_trade=False,
                reason=f"SAT modu: {price_reason}"
            )
        
        # Miktar hesapla
        notional = z * usdt_grid
        quantity, is_valid = calculate_quantity(
            notional, target_price, market_info.step_size, market_info.min_qty
        )
        
        if not is_valid:
            return GridSignal(
                should_trade=False,
                reason=f"SAT modu: miktar geçersiz ({quantity} < {market_info.min_qty})"
            )
        
        # Duplicate kontrol
        has_duplicate = await self._check_duplicate_order(
            state, OrderSide.SELL, target_price
        )
        
        if has_duplicate:
            return GridSignal(
                should_trade=False,
                reason=f"SAT modu: duplicate emir mevcut (price: {target_price})"
            )
        
        return GridSignal(
            should_trade=True,
            side=OrderSide.SELL,
            z=z,
            target_price=target_price,
            quantity=quantity,
            delta=delta,
            reason=f"SAT sinyali: z={z}, price={target_price}, qty={quantity}"
        )
    
    async def _check_duplicate_order(
        self, 
        state: State, 
        side: OrderSide, 
        target_price: float
    ) -> bool:
        """Duplicate emir kontrolü"""
        for order in state.open_orders:
            if order.side == side and abs(order.price - target_price) < 0.0001:
                return True
        return False
    
    async def process_fill(
        self, 
        strategy: Strategy, 
        state: State, 
        trade: Trade
    ) -> Dict[str, Any]:
        """Grid+OTT fill işlemi - GF güncelleme"""
        
        y = self.get_parameter(strategy, 'y')
        if not y:
            logger.error(f"Grid parametresi y bulunamadı: {strategy.id}")
            return {}
        
        # Grid fill processing - GF güncelleme
        old_gf = state.gf if state.gf is not None else trade.price
        
        # Z değerini strategy_specific_data'dan al
        strategy_data = trade.strategy_specific_data or {}
        z = strategy_data.get('z', 0)
        
        # Eğer z değeri yoksa, trade fiyatından hesapla
        if z == 0:
            if trade.side == OrderSide.BUY:
                # AL: z = (GF - price) / y
                delta = old_gf - trade.price
                z = math.floor(delta / y) if delta > 0 else 0
            else:
                # SAT: z = (price - GF) / y  
                delta = trade.price - old_gf
                z = math.floor(delta / y) if delta > 0 else 0
        
        # Trade objesindeki z değerini güncelle
        trade.z = z
        
        # GF_new hesapla
        if trade.side == OrderSide.BUY:
            # AL fill: GF_new = GF_old - z*y
            new_gf = old_gf - (z * y)
        else:
            # SAT fill: GF_new = GF_old + z*y
            new_gf = old_gf + (z * y)
        
        state.gf = new_gf
        
        # GF değerlerini trade'e kaydet
        trade.gf_before = old_gf
        trade.gf_after = new_gf
        
        self.log_strategy_action(
            strategy.id, 
            "GF_UPDATE", 
            f"{trade.side.value} fill: {old_gf:.6f} -> {new_gf:.6f} (z={z})"
        )
        
        return {
            "last_fill_gf_change": new_gf - old_gf,
            "last_fill_z": z
        }
    
    async def validate_strategy_config(self, strategy: Strategy) -> tuple[bool, str]:
        """Grid+OTT konfigürasyon validasyonu"""
        
        # Grid parametreleri kontrolü
        y = self.get_parameter(strategy, 'y')
        usdt_grid = self.get_parameter(strategy, 'usdt_grid')
        
        if not y or y <= 0:
            return False, "Grid aralığı (y) parametresi gerekli ve pozitif olmalı"
        
        if not usdt_grid or usdt_grid <= 0:
            return False, "USDT/Grid parametresi gerekli ve pozitif olmalı"
        
        # OTT parametreleri validasyonu
        if strategy.ott.period < 1 or strategy.ott.period > 200:
            return False, "OTT period 1-200 arasında olmalı"
        
        if strategy.ott.opt < 0.1 or strategy.ott.opt > 10.0:
            return False, "OTT opt 0.1-10.0 arasında olmalı"
        
        return True, "Grid+OTT konfigürasyonu geçerli"
