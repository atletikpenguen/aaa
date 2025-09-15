"""
DCA + OTT Strategy Implementation
Kullanıcının tarif ettiği strateji mantığı
"""

import os
from typing import Dict, Any, List
from datetime import datetime, timezone

from .base_strategy import BaseStrategy
from .models import (
    Strategy, State, TradingSignal, OrderSide, OTTMode, OTTResult, 
    MarketInfo, Trade, DCAPosition
)
from .utils import (
    logger, round_to_tick, calculate_quantity
)


class DCAOTTStrategy(BaseStrategy):
    """
    DCA + OTT strateji implementasyonu
    
    ALIM KURALLARI:
    1. OTT AL verdiğinde alım yapılır (SAT verdiğinde SHORT yok)
    2. İlk alım: base_usdt kadar USDT ile alım
    3. DCA alımları: Fiyat ilk alım fiyatının altında VE ortalama maliyetten min_drop_pct kadar düşükse
    4. DCA miktarı: base_usdt × (dca_multiplier ^ pozisyon_sayısı)
    
    SATIŞ KURALLARI:
    1. Kısmi satış: OTT SAT verdiğinde, fiyat son alım fiyatının %1 üzerindeyse → sadece son pozisyonu sat
    2. Tam satış: OTT SAT verdiğinde, fiyat ortalama maliyetin %1 üzerindeyse → tüm pozisyonu sat
    3. Tam satış sonrası: Yeni döngü başlar (state sıfırlanır)
    """
    
    def __init__(self):
        super().__init__("DCA+OTT")
        # Environment'dan debug modunu al
        self.debug_enabled = os.getenv('DCA_DEBUG_ENABLED', 'false').lower() == 'true'
    
    def _debug_log(self, strategy_id: str, message: str, level: str = "INFO"):
        """DCA+OTT özel debug log"""
        if self.debug_enabled:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_message = f"[DCA+OTT DEBUG] {strategy_id} | {timestamp} | {message}"
            
            if level == "ERROR":
                logger.error(log_message)
            elif level == "WARNING":
                logger.warning(log_message)
            elif level == "DEBUG":
                logger.debug(log_message)
            else:
                logger.info(log_message)
    
    def _debug_open_orders_check(self, strategy_id: str, state: State) -> bool:
        """Açık emir kontrolü ve debug log"""
        open_orders_count = len(state.open_orders)
        
        self._debug_log(strategy_id, f"🔍 Açık emir kontrolü: {open_orders_count} emir")
        
        if open_orders_count > 0:
            for i, order in enumerate(state.open_orders):
                age_minutes = (datetime.now(timezone.utc) - order.timestamp).total_seconds() / 60
                self._debug_log(strategy_id, f"  📋 Emir {i+1}: {order.side.value} {order.quantity} @ {order.price} (Yaş: {age_minutes:.1f}dk)")
            
            self._debug_log(strategy_id, f"❌ Yeni emir engellendi: {open_orders_count} açık emir var", "WARNING")
            return True  # Açık emir var
        
        self._debug_log(strategy_id, "✅ Açık emir yok - yeni emir gönderilebilir")
        return False  # Açık emir yok
    
    def _debug_position_analysis(self, strategy_id: str, position_analysis: Dict[str, Any]):
        """Pozisyon analizi debug log"""
        self._debug_log(strategy_id, "📊 Pozisyon Analizi:")
        self._debug_log(strategy_id, f"  💰 Pozisyon var: {position_analysis['has_positions']}")
        self._debug_log(strategy_id, f"  📈 Toplam miktar: {position_analysis['total_quantity']}")
        self._debug_log(strategy_id, f"  💵 Ortalama maliyet: ${position_analysis['avg_cost']:.4f}")
        self._debug_log(strategy_id, f"  🎯 İlk alım fiyatı: ${position_analysis['first_buy_price']:.4f}")
        self._debug_log(strategy_id, f"  📉 Son alım fiyatı: ${position_analysis['last_buy_price']:.4f}")
        self._debug_log(strategy_id, f"  💚 Kar/Zarar: ${position_analysis['unrealized_pnl']:.2f} ({position_analysis['unrealized_pnl_pct']:.2f}%)")
        self._debug_log(strategy_id, f"  ✅ Karlı: {position_analysis['is_profitable']}")
    
    def _debug_ott_analysis(self, strategy_id: str, ott_result: OTTResult, current_price: float):
        """OTT analizi debug log"""
        self._debug_log(strategy_id, "🎯 OTT Analizi:")
        self._debug_log(strategy_id, f"  🔄 OTT Modu: {ott_result.mode.value}")
        self._debug_log(strategy_id, f"  📊 Baseline: ${ott_result.baseline:.4f}")
        self._debug_log(strategy_id, f"  💰 Güncel Fiyat: ${current_price:.4f}")
        
        if ott_result.mode == OTTMode.AL:
            price_diff = current_price - ott_result.baseline
            self._debug_log(strategy_id, f"  📈 Fiyat farkı: ${price_diff:.4f} (AL modu)")
        else:
            price_diff = ott_result.baseline - current_price
            self._debug_log(strategy_id, f"  📉 Fiyat farkı: ${price_diff:.4f} (SAT modu)")
    
    def _debug_dca_parameters(self, strategy_id: str, base_usdt: float, dca_multiplier: float, min_drop_pct: float, use_market_orders: bool):
        """DCA parametreleri debug log"""
        self._debug_log(strategy_id, "⚙️ DCA Parametreleri:")
        self._debug_log(strategy_id, f"  💵 İlk alım tutarı: ${base_usdt}")
        self._debug_log(strategy_id, f"  📈 DCA çarpanı: {dca_multiplier}x")
        self._debug_log(strategy_id, f"  📉 Min düşüş %: {min_drop_pct}%")
        self._debug_log(strategy_id, f"  🚀 Market emir: {'✅ Aktif' if use_market_orders else '❌ Limit emir'}")
    
    def _debug_signal_decision(self, strategy_id: str, signal: TradingSignal, reason: str = ""):
        """Sinyal kararı debug log"""
        if signal.should_trade:
            price_info = f" @ ${signal.target_price}" if signal.target_price else " (Market)"
            self._debug_log(strategy_id, f"✅ SİNYAL ONAYLANDI: {signal.side.value} {signal.quantity}{price_info}")
            self._debug_log(strategy_id, f"  📝 Sebep: {signal.reason}")
            if signal.strategy_specific_data:
                self._debug_log(strategy_id, f"  🔧 Özel veri: {signal.strategy_specific_data}")
        else:
            self._debug_log(strategy_id, f"❌ SİNYAL ENGELLENDİ: {signal.reason}")
            if reason:
                self._debug_log(strategy_id, f"  📝 Ek sebep: {reason}")
    
    async def initialize_state(self, strategy: Strategy) -> Dict[str, Any]:
        """DCA+OTT için initial state"""
        self._debug_log(strategy.id, "🚀 DCA+OTT strateji başlatılıyor")
        return {
            "first_buy_executed": False,
            "last_ott_action": None,
            "profit_threshold": 0.0,  # Karlılık eşiği (%)
            "use_market_orders": True  # Market emir kullanımı (varsayılan: True)
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
        """DCA+OTT sinyal hesaplama"""
        
        self._debug_log(strategy.id, "=" * 60)
        self._debug_log(strategy.id, f"🔄 DCA+OTT Sinyal Hesaplama Başladı - Fiyat: ${current_price}")
        self._debug_log(strategy.id, "=" * 60)
        
        # 1️⃣ Açık emir kontrolü - EN ÖNEMLİ KONTROL
        if self._debug_open_orders_check(strategy.id, state):
            return TradingSignal(
                should_trade=False,
                reason=f"Açık emir beklemede: {len(state.open_orders)} emir"
            )
        
        # 2️⃣ Fiyat limitleri kontrolü
        price_valid, price_reason = self._check_price_limits(current_price, market_info)
        if not price_valid:
            self._debug_log(strategy.id, f"❌ Fiyat limitleri kontrolü başarısız: {price_reason}", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=price_reason
            )
        self._debug_log(strategy.id, "✅ Fiyat limitleri kontrolü geçti")
        
        # 3️⃣ DCA parametrelerini al
        base_usdt = self.get_parameter(strategy, 'base_usdt', 100.0)
        dca_multiplier = self.get_parameter(strategy, 'dca_multiplier', 1.5)
        min_drop_pct = self.get_parameter(strategy, 'min_drop_pct', 2.0)
        use_market_orders = state.custom_data.get('use_market_orders', True)
        self._debug_dca_parameters(strategy.id, base_usdt, dca_multiplier, min_drop_pct, use_market_orders)
        
        # 4️⃣ Mevcut pozisyon durumunu analiz et
        position_analysis = self._analyze_positions(state, current_price)
        self._debug_position_analysis(strategy.id, position_analysis)
        
        # 5️⃣ OTT analizi
        self._debug_ott_analysis(strategy.id, ott_result, current_price)
        
        # 6️⃣ OTT moduna göre karar ver
        if ott_result.mode == OTTMode.AL:
            signal = await self._handle_ott_buy_signal(
                strategy, state, current_price, market_info, 
                position_analysis, base_usdt, dca_multiplier, min_drop_pct, use_market_orders
            )
        else:  # SAT
            signal = await self._handle_ott_sell_signal(
                strategy, state, current_price, market_info,
                position_analysis, use_market_orders
            )
        
        # 7️⃣ Final sinyal kararı
        self._debug_signal_decision(strategy.id, signal)
        
        self._debug_log(strategy.id, "=" * 60)
        self._debug_log(strategy.id, "🏁 DCA+OTT Sinyal Hesaplama Tamamlandı")
        self._debug_log(strategy.id, "=" * 60)
        
        return signal
    
    def _check_price_limits(self, current_price: float, market_info: MarketInfo) -> tuple[bool, str]:
        """Fiyat limitleri kontrolü"""
        # Minimum fiyat kontrolü
        if current_price <= 0:
            return False, "Fiyat sıfır veya negatif"
        
        # Maksimum fiyat kontrolü (çok yüksek fiyatları engelle)
        if current_price > 1000000:  # 1M USDT üzeri
            return False, "Fiyat çok yüksek"
        
        return True, "Fiyat limitleri geçerli"
    
    def _analyze_positions(self, state: State, current_price: float) -> Dict[str, Any]:
        """Mevcut pozisyon durumunu analiz et"""
        
        if not state.dca_positions:
            return {
                "has_positions": False,
                "total_quantity": 0.0,
                "avg_cost": 0.0,
                "first_buy_price": 0.0,
                "last_buy_price": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "is_profitable": False,
                "position_count": 0
            }
        
        # Toplam miktar ve ortalama maliyet hesapla
        total_quantity = sum(pos.quantity for pos in state.dca_positions)
        total_cost = sum(pos.buy_price * pos.quantity for pos in state.dca_positions)
        avg_cost = total_cost / total_quantity if total_quantity > 0 else 0
        
        # İlk ve son alım fiyatları
        sorted_positions = sorted(state.dca_positions, key=lambda x: x.timestamp)
        first_buy_price = sorted_positions[0].buy_price
        last_buy_price = sorted_positions[-1].buy_price
        
        # Gerçekleşmemiş kar/zarar
        current_value = total_quantity * current_price
        total_invested = total_cost
        unrealized_pnl = current_value - total_invested
        unrealized_pnl_pct = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0
        
        return {
            "has_positions": True,
            "total_quantity": total_quantity,
            "avg_cost": avg_cost,
            "first_buy_price": first_buy_price,
            "last_buy_price": last_buy_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "is_profitable": unrealized_pnl > 0,
            "position_count": len(state.dca_positions)
        }
    
    async def _handle_ott_buy_signal(
        self,
        strategy: Strategy,
        state: State,
        current_price: float,
        market_info: MarketInfo,
        position_analysis: Dict[str, Any],
        base_usdt: float,
        dca_multiplier: float,
        min_drop_pct: float,
        use_market_orders: bool = True
    ) -> TradingSignal:
        """OTT AL sinyali işleme"""
        
        self._debug_log(strategy.id, f"🔍 DCA+OTT {strategy.id}: OTT AL sinyali analizi - Fiyat: ${current_price}")
        self._debug_log(strategy.id, f"   Pozisyon durumu: {position_analysis}")
        self._debug_log(strategy.id, f"   Parametreler: base_usdt=${base_usdt}, dca_multiplier={dca_multiplier}, min_drop_pct={min_drop_pct}%")
        
        # Kural 1: İlk alım (henüz pozisyon yok)
        if not position_analysis["has_positions"]:
            self._debug_log(strategy.id, f"   📈 İlk alım sinyali - Henüz pozisyon yok (Döngü: D{state.cycle_number})")
            
            # Minimum USDT tutarını kontrol et
            min_notional = market_info.min_notional
            if base_usdt < min_notional:
                self._debug_log(strategy.id, f"   ❌ İlk alım engellendi: USDT tutarı çok düşük (${base_usdt} < ${min_notional})", "WARNING")
                return TradingSignal(
                    should_trade=False,
                    reason=f"İlk alım: USDT tutarı çok düşük (${base_usdt} < ${min_notional})"
                )
            
            quantity, is_valid = calculate_quantity(
                base_usdt, current_price, market_info.step_size, market_info.min_qty
            )
            
            if not is_valid:
                self._debug_log(strategy.id, f"   ❌ İlk alım engellendi: Miktar geçersiz ({quantity} < {market_info.min_qty})", "WARNING")
                return TradingSignal(
                    should_trade=False,
                    reason=f"İlk alım: miktar geçersiz ({quantity} < {market_info.min_qty})"
                )
            
            order_type = "MARKET" if use_market_orders else "LIMIT"
            target_price = None if use_market_orders else round_to_tick(current_price, market_info.tick_size)
            
            # İlk alım için işlem sayacını 1 olarak ayarla
            trade_count = state.cycle_trade_count + 1
            
            self._debug_log(strategy.id, f"   ✅ İlk alım sinyali onaylandı: {quantity} @ ${current_price} ({order_type}) - D{state.cycle_number}-{trade_count}")
            return TradingSignal(
                should_trade=True,
                side=OrderSide.BUY,
                target_price=target_price,
                quantity=quantity,
                reason=f"İlk alım: OTT AL sinyali ({order_type}) - D{state.cycle_number}-{trade_count}",
                strategy_specific_data={
                    "dca_type": "first_buy",
                    "usdt_amount": base_usdt,
                    "order_type": order_type,
                    "cycle_number": state.cycle_number,
                    "cycle_trade_count": trade_count
                }
            )
        
        # Kural 4: Fiyat ilk maliyetin üstünde → alım yok
        if current_price >= position_analysis["first_buy_price"]:
            self._debug_log(strategy.id, f"   ❌ AL engellendi: Fiyat (${current_price}) ilk alım fiyatının (${position_analysis['first_buy_price']}) üstünde", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=f"AL engellendi: Fiyat ({current_price}) ilk alım fiyatının ({position_analysis['first_buy_price']}) üstünde"
            )
        
        # 🛡️ EK GÜVENLIK: Fiyat son alım fiyatının üstünde → alım yok (yanlış DCA engelle)
        if current_price > position_analysis["last_buy_price"]:
            self._debug_log(strategy.id, f"   🚨 AL engellendi: Fiyat (${current_price}) son alım fiyatının (${position_analysis['last_buy_price']}) üstünde - YANLIŞ DCA!", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=f"AL engellendi: Fiyat ({current_price}) son alım fiyatının ({position_analysis['last_buy_price']}) üstünde - DCA kuralı ihlali"
            )
        
        # Kural 5: Fiyat yeterince düşmedi mi? (Son alım fiyatından düşüş)
        drop_from_last = ((position_analysis["last_buy_price"] - current_price) / position_analysis["last_buy_price"]) * 100
        self._debug_log(strategy.id, f"   📊 Düşüş analizi: Son alım=${position_analysis['last_buy_price']}, Düşüş={drop_from_last:.2f}%, Min eşik={min_drop_pct}%")
        
        if drop_from_last < min_drop_pct:
            self._debug_log(strategy.id, f"   ❌ AL engellendi: Düşüş ({drop_from_last:.2f}%) minimum eşiğin ({min_drop_pct}%) altında", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=f"AL engellendi: Düşüş ({drop_from_last:.2f}%) minimum eşiğin ({min_drop_pct}%) altında"
            )
        
        # DCA alım miktarını hesapla
        position_count = position_analysis["position_count"]
        dca_usdt = base_usdt * (dca_multiplier ** position_count)
        
        self._debug_log(strategy.id, f"   📊 DCA hesaplama: Pozisyon sayısı={position_count}, DCA USDT=${dca_usdt}")
        
        # Minimum USDT tutarını kontrol et
        min_notional = market_info.min_notional
        if dca_usdt < min_notional:
            self._debug_log(strategy.id, f"   ❌ DCA alım engellendi: USDT tutarı çok düşük (${dca_usdt} < ${min_notional})", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=f"DCA alım: USDT tutarı çok düşük (${dca_usdt} < ${min_notional})"
            )
        
        quantity, is_valid = calculate_quantity(
            dca_usdt, current_price, market_info.step_size, market_info.min_qty
        )
        
        if not is_valid:
            self._debug_log(strategy.id, f"   ❌ DCA alım engellendi: Miktar geçersiz ({quantity} < {market_info.min_qty})", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=f"DCA alım: miktar geçersiz ({quantity} < {market_info.min_qty})"
            )
        
        order_type = "MARKET" if use_market_orders else "LIMIT"
        target_price = None if use_market_orders else round_to_tick(current_price, market_info.tick_size)
        
        # DCA alım için işlem sayacını artır
        trade_count = state.cycle_trade_count + 1
        
        self._debug_log(strategy.id, f"   ✅ DCA alım sinyali onaylandı: {quantity} @ ${current_price} ({position_count+1}. pozisyon, {order_type}) - D{state.cycle_number}-{trade_count}")
        return TradingSignal(
            should_trade=True,
            side=OrderSide.BUY,
            target_price=target_price,
            quantity=quantity,
            reason=f"DCA alım: {position_count+1}. pozisyon, {drop_from_last:.2f}% düşüş ({order_type}) - D{state.cycle_number}-{trade_count}",
            strategy_specific_data={
                "dca_type": "dca_buy",
                "position_count": position_count + 1,
                "usdt_amount": dca_usdt,
                "drop_pct": drop_from_last,
                "order_type": order_type,
                "cycle_number": state.cycle_number,
                "cycle_trade_count": trade_count
            }
        )
    
    async def _handle_ott_sell_signal(
        self,
        strategy: Strategy,
        state: State,
        current_price: float,
        market_info: MarketInfo,
        position_analysis: Dict[str, Any],
        use_market_orders: bool = True
    ) -> TradingSignal:
        """OTT SAT sinyali işleme - Yeni kurallar:
        1. Kısmi satış: Son alım fiyatının %1 üzerinde
        2. Tam satış: Ortalama maliyetin %1 üzerinde
        """
        
        self._debug_log(strategy.id, "🔍 OTT SAT sinyali analizi başladı")
        
        # Pozisyon yoksa satış yapılamaz
        if not position_analysis["has_positions"]:
            self._debug_log(strategy.id, "❌ SAT engellendi: Pozisyon yok", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason="SAT engellendi: Hiç pozisyon yok"
            )
        
        avg_cost = position_analysis["avg_cost"]
        last_buy_price = position_analysis["last_buy_price"]
        
        self._debug_log(strategy.id, f"📊 SAT Analizi: Ort. maliyet=${avg_cost:.4f}, Son alım=${last_buy_price:.4f}, Güncel fiyat=${current_price:.4f}")
        
        # Kural 1: Tam satış - Ortalama maliyetin %1 üzerinde
        profit_threshold = avg_cost * 1.01  # %1 kâr eşiği
        if current_price >= profit_threshold:
            total_quantity = position_analysis["total_quantity"]
            profit_pct = position_analysis["unrealized_pnl_pct"]
            order_type = "MARKET" if use_market_orders else "LIMIT"
            target_price = None if use_market_orders else round_to_tick(current_price, market_info.tick_size)
            
            self._debug_log(strategy.id, f"✅ TÜM POZİSYON SATIŞI: Fiyat (${current_price}) >= Kâr eşiği (${profit_threshold:.4f}) - Kar: {profit_pct:.2f}% ({order_type}) - D{state.cycle_number} (TAMAMLANDI)")
            
            return TradingSignal(
                should_trade=True,
                side=OrderSide.SELL,
                target_price=target_price,
                quantity=round_to_tick(total_quantity, market_info.step_size),
                reason=f"Tüm pozisyon satışı: Fiyat ({current_price}) >= Kâr eşiği ({profit_threshold:.4f}) - %1 kâr ({order_type}) - D{state.cycle_number} (TAMAMLANDI)",
                strategy_specific_data={
                    "sell_type": "full_exit",
                    "profit_pct": position_analysis["unrealized_pnl_pct"],
                    "profit_threshold": profit_threshold,
                    "order_type": order_type,
                    "cycle_number": state.cycle_number,
                    "cycle_trade_count": 0  # Tam satışta sayacı sıfırla
                }
            )
        
        # Kural 2: Kısmi satış - Son alım fiyatının %1 üzerinde
        partial_profit_threshold = last_buy_price * 1.01  # Son alımın %1 üzeri
        if current_price >= partial_profit_threshold:
            # Son alımı bul
            sorted_positions = sorted(state.dca_positions, key=lambda x: x.timestamp, reverse=True)
            last_position = sorted_positions[0]
            order_type = "MARKET" if use_market_orders else "LIMIT"
            target_price = None if use_market_orders else round_to_tick(current_price, market_info.tick_size)
            
            profit_vs_last = ((current_price - last_buy_price) / last_buy_price) * 100
            
            # Kısmi satış için işlem sayacını artır
            trade_count = state.cycle_trade_count + 1
            
            self._debug_log(strategy.id, f"✅ KISMI SATIŞ: Fiyat (${current_price}) >= Son alım kâr eşiği (${partial_profit_threshold:.4f}) - %{profit_vs_last:.2f} kâr ({order_type}) - D{state.cycle_number}-{trade_count}")
            
            return TradingSignal(
                should_trade=True,
                side=OrderSide.SELL,
                target_price=target_price,
                quantity=round_to_tick(last_position.quantity, market_info.step_size),
                reason=f"Son pozisyon satışı: Fiyat ({current_price}) >= Son alım kâr eşiği ({partial_profit_threshold:.4f}) - %{profit_vs_last:.2f} kâr ({order_type}) - D{state.cycle_number}-{trade_count}",
                strategy_specific_data={
                    "sell_type": "partial_exit",
                    "position_to_sell": last_position.order_id,
                    "profit_vs_last": profit_vs_last,
                    "partial_profit_threshold": partial_profit_threshold,
                    "order_type": order_type,
                    "cycle_number": state.cycle_number,
                    "cycle_trade_count": trade_count
                }
            )
        
        # Kural 3: Satış koşulları sağlanmıyor
        self._debug_log(strategy.id, f"❌ SAT engellendi: Fiyat (${current_price}) kâr eşiklerini karşılamıyor", "WARNING")
        self._debug_log(strategy.id, f"   📊 Gerekli eşikler: Tam satış >= ${profit_threshold:.4f}, Kısmi satış >= ${partial_profit_threshold:.4f}")
        return TradingSignal(
            should_trade=False,
            reason=f"SAT engellendi: Fiyat ({current_price}) kâr eşiklerini karşılamıyor (Tam: {profit_threshold:.4f}, Kısmi: {partial_profit_threshold:.4f})"
        )
    
    async def process_fill(
        self, 
        strategy: Strategy, 
        state: State, 
        trade: Trade
    ) -> Dict[str, Any]:
        """DCA+OTT fill işlemi - pozisyon güncelleme"""
        
        self._debug_log(strategy.id, f"🔄 FILL İşlemi: {trade.side.value} {trade.quantity} @ ${trade.price}")
        
        if trade.side == OrderSide.BUY:
            # İlk alım ise döngü sayısını artır ve işlem sayacını sıfırla
            if len(state.dca_positions) == 0:
                state.cycle_number += 1
                state.cycle_trade_count = 0
                self._debug_log(strategy.id, f"🔄 YENİ DÖNGÜ BAŞLADI: D{state.cycle_number}")
            
            # İşlem sayacını artır
            state.cycle_trade_count += 1
            
            # 🛡️ GÜVENLIK KONTROLÜ: Aynı order_id ile pozisyon var mı?
            existing_position = None
            for pos in state.dca_positions:
                if pos.order_id == trade.order_id:
                    existing_position = pos
                    break
            
            if existing_position:
                self._debug_log(strategy.id, f"⚠️ DUPLICATE FILL: Order {trade.order_id} zaten pozisyonlarda var, atlanıyor", "WARNING")
                return {
                    "action": "duplicate_fill_ignored",
                    "existing_position": existing_position.buy_price
                }
            
            # Yeni pozisyon ekle
            new_position = DCAPosition(
                buy_price=trade.price,
                quantity=trade.quantity,
                timestamp=trade.timestamp,
                order_id=trade.order_id
            )
            state.dca_positions.append(new_position)
            
            # 📊 DETAYLI LOG: Pozisyon listesi
            self._debug_log(strategy.id, f"📋 Pozisyon listesi ({len(state.dca_positions)} adet):")
            for i, pos in enumerate(state.dca_positions, 1):
                self._debug_log(strategy.id, f"   {i}. {pos.quantity} @ ${pos.buy_price} (Order: {pos.order_id})")
            
            # Pozisyon sayısı kontrolü
            if len(state.dca_positions) > 10:
                self._debug_log(strategy.id, f"🚨 UYARI: Çok fazla pozisyon ({len(state.dca_positions)}), state corruption olabilir!", "WARNING")
            
            # Ortalama maliyeti güncelle
            total_quantity = sum(pos.quantity for pos in state.dca_positions)
            total_cost = sum(pos.buy_price * pos.quantity for pos in state.dca_positions)
            state.avg_cost = total_cost / total_quantity if total_quantity > 0 else 0
            state.total_quantity = total_quantity
            
            self._debug_log(strategy.id, f"✅ ALIM FILL: Yeni pozisyon eklendi - {trade.quantity} @ ${trade.price} (D{state.cycle_number}-{state.cycle_trade_count})")
            self._debug_log(strategy.id, f"📊 Güncel durum: {len(state.dca_positions)} pozisyon, Ort. maliyet: ${state.avg_cost:.4f}")
            
            self.log_strategy_action(
                strategy.id,
                "DCA_BUY",
                f"Yeni pozisyon: {trade.quantity} @ {trade.price}, Ort. maliyet: {state.avg_cost:.6f} (D{state.cycle_number}-{state.cycle_trade_count})"
            )
            
            return {
                "action": "dca_buy",
                "new_avg_cost": state.avg_cost,
                "position_count": len(state.dca_positions),
                "cycle_number": state.cycle_number,
                "cycle_trade_count": state.cycle_trade_count
            }
        
        else:  # SELL
            sell_type = trade.strategy_specific_data.get('sell_type') if hasattr(trade, 'strategy_specific_data') else 'unknown'
            
            # Satış işlemlerinde de sayacı artır (tam satış hariç)
            if sell_type != "full_exit":
                state.cycle_trade_count += 1
            
            self._debug_log(strategy.id, f"📊 SAT FILL: Satış türü = {sell_type}")
            
            if sell_type == "full_exit":
                # Tüm pozisyonları temizle - YENİ DÖNGÜ BAŞLAT
                old_avg_cost = state.avg_cost
                old_positions_count = len(state.dca_positions)
                old_cycle_number = state.cycle_number
                state.dca_positions.clear()
                state.avg_cost = None
                state.total_quantity = 0.0
                
                # İşlem sayacını sıfırla (döngü sayısı korunur, bir sonraki alımda artırılacak)
                state.cycle_trade_count = 0
                
                # Yeni döngü için state'i sıfırla
                state.custom_data["first_buy_executed"] = False
                state.custom_data["last_ott_action"] = None
                
                self._debug_log(strategy.id, f"✅ TAM SATIŞ: {old_positions_count} pozisyon temizlendi - Döngü D{old_cycle_number} tamamlandı")
                self._debug_log(strategy.id, f"💰 Kar/Zarar: Eski ort. maliyet ${old_avg_cost:.4f} → Satış fiyatı ${trade.price:.4f}")
                self._debug_log(strategy.id, f"🔄 Pozisyonlar temizlendi - Yeni döngü için hazır (sonraki alım D{state.cycle_number + 1} olacak)")
                
                self.log_strategy_action(
                    strategy.id,
                    "FULL_EXIT_NEW_CYCLE",
                    f"Tüm pozisyon satıldı @ {trade.price}, Eski ort. maliyet: {old_avg_cost:.6f} - Döngü D{old_cycle_number} tamamlandı, sonraki döngü D{state.cycle_number + 1} olacak"
                )
                
                return {
                    "action": "full_exit_new_cycle",
                    "exit_price": trade.price,
                    "old_avg_cost": old_avg_cost,
                    "old_cycle_number": old_cycle_number,
                    "current_cycle_number": state.cycle_number,
                    "next_cycle_number": state.cycle_number + 1,
                    "positions_cleared": True
                }
            
            elif sell_type == "partial_exit":
                # Son pozisyonu kaldır (LIFO)
                if state.dca_positions:
                    removed_position = state.dca_positions.pop()  # Son pozisyonu çıkar
                    
                    # Ortalama maliyeti yeniden hesapla
                    if state.dca_positions:
                        total_quantity = sum(pos.quantity for pos in state.dca_positions)
                        total_cost = sum(pos.buy_price * pos.quantity for pos in state.dca_positions)
                        state.avg_cost = total_cost / total_quantity
                        state.total_quantity = total_quantity
                    else:
                        state.avg_cost = None
                        state.total_quantity = 0.0
                    
                    self._debug_log(strategy.id, f"✅ KISMI SATIŞ: Son pozisyon satıldı - {removed_position.quantity} @ ${removed_position.buy_price} (D{state.cycle_number}-{state.cycle_trade_count})")
                    self._debug_log(strategy.id, f"📊 Kalan pozisyonlar: {len(state.dca_positions)}, Yeni ort. maliyet: ${state.avg_cost:.4f}")
                    
                    self.log_strategy_action(
                        strategy.id,
                        "PARTIAL_EXIT",
                        f"Son pozisyon satıldı: {removed_position.quantity} @ {trade.price}, Yeni ort. maliyet: {state.avg_cost}"
                    )
                
                return {
                    "action": "partial_exit",
                    "exit_price": trade.price,
                    "remaining_positions": len(state.dca_positions)
                }
            
            else:
                # Bilinmeyen satış türü - Güvenli varsayılan davranış
                self._debug_log(strategy.id, f"⚠️ Bilinmeyen satış türü: {sell_type} - Tüm pozisyonları temizle", "WARNING")
                
                # Satılan miktarı pozisyonlardan çıkar
                remaining_quantity = trade.quantity
                removed_positions = []
                
                # LIFO sırasıyla pozisyonları çıkar
                while remaining_quantity > 0 and state.dca_positions:
                    last_position = state.dca_positions[-1]
                    if last_position.quantity <= remaining_quantity:
                        # Tüm pozisyonu çıkar
                        removed_positions.append(state.dca_positions.pop())
                        remaining_quantity -= last_position.quantity
                    else:
                        # Pozisyonun bir kısmını çıkar
                        removed_quantity = remaining_quantity
                        last_position.quantity -= removed_quantity
                        remaining_quantity = 0
                        
                        # Kısmi pozisyon için yeni kayıt oluştur
                        removed_positions.append(DCAPosition(
                            buy_price=last_position.buy_price,
                            quantity=removed_quantity,
                            timestamp=last_position.timestamp,
                            order_id=last_position.order_id
                        ))
                
                # Ortalama maliyeti yeniden hesapla
                if state.dca_positions:
                    total_quantity = sum(pos.quantity for pos in state.dca_positions)
                    total_cost = sum(pos.buy_price * pos.quantity for pos in state.dca_positions)
                    state.avg_cost = total_cost / total_quantity
                    state.total_quantity = total_quantity
                else:
                    state.avg_cost = None
                    state.total_quantity = 0.0
                    # Tüm pozisyonlar satıldıysa yeni döngü başlat
                    state.custom_data["first_buy_executed"] = False
                    state.custom_data["last_ott_action"] = None
                
                self._debug_log(strategy.id, f"✅ GÜVENLİ SATIŞ: {len(removed_positions)} pozisyon çıkarıldı")
                self._debug_log(strategy.id, f"📊 Kalan pozisyonlar: {len(state.dca_positions)}, Yeni ort. maliyet: ${state.avg_cost:.4f}")
                
                self.log_strategy_action(
                    strategy.id,
                    "SAFE_EXIT",
                    f"Güvenli satış: {trade.quantity} @ {trade.price}, Kalan pozisyonlar: {len(state.dca_positions)}"
                )
                
                return {
                    "action": "safe_exit",
                    "exit_price": trade.price,
                    "remaining_positions": len(state.dca_positions),
                    "removed_positions": len(removed_positions)
                }
        
        return {}
    
    async def validate_strategy_config(self, strategy: Strategy) -> tuple[bool, str]:
        """DCA+OTT konfigürasyon validasyonu"""
        
        base_usdt = self.get_parameter(strategy, 'base_usdt')
        if not base_usdt or base_usdt <= 0:
            return False, "DCA base_usdt parametresi gerekli ve pozitif olmalı"
        
        dca_multiplier = self.get_parameter(strategy, 'dca_multiplier', 1.5)
        if dca_multiplier < 1.0 or dca_multiplier > 5.0:
            return False, "DCA multiplier 1.0-5.0 arasında olmalı"
        
        min_drop_pct = self.get_parameter(strategy, 'min_drop_pct', 2.0)
        if min_drop_pct < 0.5 or min_drop_pct > 20.0:
            return False, "Min drop percentage 0.5-20.0 arasında olmalı"
        
        # OTT parametreleri validasyonu
        if strategy.ott.period < 1 or strategy.ott.period > 200:
            return False, "OTT period 1-200 arasında olmalı"
        
        if strategy.ott.opt < 0.1 or strategy.ott.opt > 10.0:
            return False, "OTT opt 0.1-10.0 arasında olmalı"
        
        return True, "DCA+OTT konfigürasyonu geçerli"
