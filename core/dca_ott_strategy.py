"""
DCA + OTT Strategy Implementation
Kullanıcının tarif ettiği strateji mantığı

DÜZELTME (25 Eylül 2025): DCA alım referansı sorunu çözüldü
- Sorun: Tekrar alım için son alım fiyatı referansı kullanılıyordu
- Çözüm: Son satış fiyatı referansı kullanılacak şekilde düzeltildi
- Sonuç: DCA stratejisi artık doğru mantıkla çalışacak

DÜZELTME (25 Eylül 2025): drop_from_last değişken hatası düzeltildi
- Sorun: 395. ve 400. satırlarda tanımlanmamış drop_from_last değişkeni kullanılıyordu
- Çözüm: drop_from_last yerine drop_from_last_sell kullanılacak şekilde düzeltildi
- Sonuç: NameError hatası çözüldü, strateji düzgün çalışacak

DÜZELTME (30 Eylül 2025): Min düşüş kontrolü düzeltildi
- Sorun: Son satış fiyatından düşüş kontrolü yapılıyordu
- Çözüm: Son gerçekleşen işlem noktasından düşüş kontrolü yapılacak şekilde düzeltildi
- Sonuç: DCA stratejisi artık doğru min düşüş kontrolü yapacak

DÜZELTME (30 Eylül 2025): calculate_signal parametre uyumsuzluğu düzeltildi
- Sorun: BaseStrategy'deki signature ile uyumsuzluk
- Çözüm: ott_result parametresi eklendi
- Sonuç: DCA stratejisi artık doğru parametrelerle çalışacak
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
        # Environment'dan debug modunu al - Döngü debug için her zaman aktif
        self.debug_enabled = os.getenv('DCA_DEBUG_ENABLED', 'true').lower() == 'true'
    
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
    
    def _debug_cycle_calculation(self, strategy_id: str, state: State, trade_type: str, level: str = "WARNING"):
        """Döngü hesaplama debug - WARNING düzeyinde güvenli debug"""
        cycle_display = state.cycle_number  # Artık +1 yapmıyoruz
        expected_cycle = state.cycle_number
        
        # Pozisyon durumu analizi
        has_positions = len(state.dca_positions) > 0
        position_count = len(state.dca_positions)
        
        # Döngü mantığı kontrolü
        cycle_logic_ok = True
        if state.cycle_number < 1:
            cycle_logic_ok = False  # Döngü numarası 1'den küçük olamaz
        
        # Debug mesajı
        debug_msg = (
            f"[CYCLE DEBUG] {strategy_id} | {trade_type} | "
            f"State cycle_number={state.cycle_number} | "
            f"Display=D{cycle_display} | "
            f"Trade count={state.cycle_trade_count} | "
            f"Positions={position_count} | "
            f"Has positions={has_positions} | "
            f"Logic OK={cycle_logic_ok}"
        )
        
        # WARNING düzeyinde log - Her zaman çalışır
        logger.warning(debug_msg)
        
        # Kritik sorun tespiti
        if not cycle_logic_ok:
            logger.warning(f"[CYCLE CRITICAL] {strategy_id} | Döngü mantığı hatası tespit edildi!")
        
        return {
            "cycle_number": state.cycle_number,
            "cycle_display": cycle_display,
            "trade_count": state.cycle_trade_count,
            "position_count": position_count,
            "logic_ok": cycle_logic_ok
        }
    
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
    
    async def initialize_state(self, strategy: Strategy) -> Dict[str, Any]:
        """DCA+OTT stratejisi için initial state oluştur"""
        return {
            "first_buy_executed": False,
            "last_ott_action": None,
            "profit_threshold": 0.0,
            "use_market_orders": True,
            "last_sell_price": None,
            "last_trade_price": None
        }
    
    async def calculate_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        current_price: float, 
        ott_result: OTTResult,
        market_info: MarketInfo,
        ohlcv_data: List[Dict[str, Any]] = None
    ) -> TradingSignal:
        """DCA+OTT sinyal hesaplama"""
        
        # OTT hesapla (eğer ott_result None ise)
        if not ott_result:
            ott_result = self._calculate_ott(ohlcv_data, strategy.ott.period, strategy.ott.opt)
        
        if not ott_result:
            return TradingSignal(should_trade=False, reason="OTT hesaplama hatası")
        
        # Pozisyon analizi
        position_analysis = self._analyze_position(state)
        
        # Parametreleri al
        base_usdt = float(strategy.parameters.get('base_usdt', 100.0))
        dca_multiplier = float(strategy.parameters.get('dca_multiplier', 1.5))
        min_drop_pct = float(strategy.parameters.get('min_drop_pct', 2.0))
        profit_threshold_pct = float(strategy.parameters.get('profit_threshold_pct', 1.0))
        use_market_orders = strategy.parameters.get('use_market_orders', True)
        
        self._debug_log(strategy.id, f"🔍 DCA+OTT {strategy.id}: OTT={ott_result.mode}, Fiyat=${current_price}")
        self._debug_log(strategy.id, f"   Pozisyon: {position_analysis}")
        self._debug_log(strategy.id, f"   Parametreler: base_usdt=${base_usdt}, dca_multiplier={dca_multiplier}, min_drop_pct={min_drop_pct}%")
        
        # OTT AL sinyali
        if ott_result.mode == OTTMode.AL:
            return await self._handle_ott_buy_signal(
                strategy, state, current_price, market_info, position_analysis,
                base_usdt, dca_multiplier, min_drop_pct, use_market_orders
            )
        
        # OTT SAT sinyali
        elif ott_result.mode == OTTMode.SAT:
            return await self._handle_ott_sell_signal(
                strategy, state, current_price, market_info, position_analysis,
                profit_threshold_pct, use_market_orders
            )
        
        return TradingSignal(should_trade=False, reason="OTT sinyali yok")
    
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
        
        self._debug_log(strategy.id, f"🔍 DCA+OTT {strategy.id}: OTT AL sinyali analizi - Fiyat: ${current_price}")
        self._debug_log(strategy.id, f"   Pozisyon durumu: {position_analysis}")
        self._debug_log(strategy.id, f"   Parametreler: base_usdt=${base_usdt}, dca_multiplier={dca_multiplier}, min_drop_pct={min_drop_pct}%")
        
        # Kural 1: İlk alım (henüz pozisyon yok)
        if not position_analysis["has_positions"]:
            # 🔍 DÖNGÜ DEBUG: İlk alım sinyali
            cycle_debug = self._debug_cycle_calculation(strategy.id, state, "FIRST_BUY_SIGNAL")
            
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
        
        # Kural 2: Açık emir kontrolü
        if self._debug_open_orders_check(strategy.id, state):
            return TradingSignal(
                should_trade=False,
                reason="Açık emir var - yeni emir engellendi"
            )
        
        # Kural 3: Pozisyon sayısı kontrolü (çok fazla pozisyon)
        if position_analysis["position_count"] >= 10:
            self._debug_log(strategy.id, f"   ❌ AL engellendi: Çok fazla pozisyon ({position_analysis['position_count']})", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=f"Çok fazla pozisyon ({position_analysis['position_count']})"
            )
        
        # Kural 5: Fiyat yeterince düşmedi mi? (Son gerçekleşen işlem noktasından düşüş)
        # Son gerçekleşen işlem noktasını referans al (alım veya satış fark etmez)
        last_trade_price = state.custom_data.get('last_trade_price', position_analysis["last_buy_price"])
        
        drop_from_last_trade = ((last_trade_price - current_price) / last_trade_price) * 100
        self._debug_log(strategy.id, f"   📊 Düşüş analizi: Son işlem=${last_trade_price}, Düşüş={drop_from_last_trade:.2f}%, Min eşik={min_drop_pct}%")
        
        if drop_from_last_trade < min_drop_pct:
            self._debug_log(strategy.id, f"   ❌ AL engellendi: Düşüş ({drop_from_last_trade:.2f}%) minimum eşiğin ({min_drop_pct}%) altında", "WARNING")
            return TradingSignal(
                should_trade=False,
                reason=f"AL engellendi: Düşüş ({drop_from_last_trade:.2f}%) minimum eşiğin ({min_drop_pct}%) altında"
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
        
        # 🔍 DÖNGÜ DEBUG: DCA alım sinyali
        cycle_debug = self._debug_cycle_calculation(strategy.id, state, "DCA_BUY_SIGNAL")
        
        self._debug_log(strategy.id, f"   ✅ DCA alım sinyali onaylandı: {quantity} @ ${current_price} ({position_count+1}. pozisyon, {order_type}) - D{state.cycle_number}-{trade_count}")
        return TradingSignal(
            should_trade=True,
            side=OrderSide.BUY,
            target_price=target_price,
            quantity=quantity,
            reason=f"DCA alım: {position_count+1}. pozisyon, {drop_from_last_trade:.2f}% düşüş ({order_type}) - D{state.cycle_number}-{trade_count}",
            strategy_specific_data={
                "dca_type": "dca_buy",
                "position_count": position_count + 1,
                "usdt_amount": dca_usdt,
                "drop_pct": drop_from_last_trade,
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
        profit_threshold_pct: float,
        use_market_orders: bool = True
    ) -> TradingSignal:
        
        self._debug_log(strategy.id, f"🔍 DCA+OTT {strategy.id}: OTT SAT sinyali analizi - Fiyat: ${current_price}")
        self._debug_log(strategy.id, f"   Pozisyon durumu: {position_analysis}")
        
        # Pozisyon yoksa satış yapma
        if not position_analysis["has_positions"]:
            self._debug_log(strategy.id, f"   ❌ SAT engellendi: Pozisyon yok")
            return TradingSignal(
                should_trade=False,
                reason="SAT engellendi: Pozisyon yok"
            )
        
        # Açık emir kontrolü
        if self._debug_open_orders_check(strategy.id, state):
            return TradingSignal(
                should_trade=False,
                reason="Açık emir var - yeni emir engellendi"
            )
        
        # Tam satış kontrolü: Ortalama maliyetin üzerinde mi?
        avg_cost = position_analysis["avg_cost"]
        total_quantity = position_analysis["total_quantity"]
        profit_threshold = avg_cost * (1 + profit_threshold_pct / 100)
        profit_pct = position_analysis["unrealized_pnl_pct"]
        
        if current_price >= profit_threshold:
            # TÜM POZİSYON SATIŞI
            order_type = "MARKET" if use_market_orders else "LIMIT"
            target_price = None if use_market_orders else round_to_tick(current_price, market_info.tick_size)
            
            # 🔍 DÖNGÜ DEBUG: Tam satış sinyali
            cycle_debug = self._debug_cycle_calculation(strategy.id, state, "FULL_SELL_SIGNAL")
            
            self._debug_log(strategy.id, f"✅ TÜM POZİSYON SATIŞI: Fiyat (${current_price}) >= Kâr eşiği (${profit_threshold:.4f}) - Kar: {profit_pct:.2f}% ({order_type}) - D{state.cycle_number} (TAMAMLANDI)")
            
            return TradingSignal(
                should_trade=True,
                side=OrderSide.SELL,
                target_price=target_price,
                quantity=round_to_tick(total_quantity, market_info.step_size),
                reason=f"Tüm pozisyon satışı: Fiyat ({current_price}) >= Kâr eşiği ({profit_threshold:.4f}) - %{profit_threshold_pct} kâr ({order_type}) - D{state.cycle_number} (TAMAMLANDI)",
                strategy_specific_data={
                    "sell_type": "full_exit",
                    "profit_pct": position_analysis["unrealized_pnl_pct"],
                    "profit_threshold": profit_threshold,
                    "order_type": order_type,
                    "cycle_number": state.cycle_number,
                    "cycle_trade_count": 0  # Tam satışta sayacı sıfırla
                }
            )
        
        # Kısmi satış kontrolü: Son pozisyonun kârında mı?
        last_position = position_analysis["last_position"]
        if last_position:
            last_buy_price = last_position["buy_price"]
            partial_profit_threshold = last_buy_price * (1 + profit_threshold_pct / 100)
            
        if current_price >= partial_profit_threshold:
                # KISMI SATIŞ - Son pozisyonu sat
            order_type = "MARKET" if use_market_orders else "LIMIT"
            target_price = None if use_market_orders else round_to_tick(current_price, market_info.tick_size)
            
            profit_vs_last = ((current_price - last_buy_price) / last_buy_price) * 100
            
            # Kısmi satış için işlem sayacını artır
            trade_count = state.cycle_trade_count + 1
            
            # 🔍 DÖNGÜ DEBUG: Kısmi satış sinyali
            cycle_debug = self._debug_cycle_calculation(strategy.id, state, "PARTIAL_SELL_SIGNAL")
            
            self._debug_log(strategy.id, f"✅ KISMI SATIŞ: Fiyat (${current_price}) >= Son alım kâr eşiği (${partial_profit_threshold:.4f}) - %{profit_vs_last:.2f} kâr ({order_type}) - D{state.cycle_number}-{trade_count}")
            
            return TradingSignal(
                should_trade=True,
                side=OrderSide.SELL,
                target_price=target_price,
                quantity=round_to_tick(last_position["quantity"], market_info.step_size),
                    reason=f"Son pozisyon satışı: Fiyat ({current_price}) >= Son alım kâr eşiği (${partial_profit_threshold:.4f}) - %{profit_vs_last:.2f} kâr ({order_type}) - D{state.cycle_number}-{trade_count}",
                strategy_specific_data={
                    "sell_type": "partial_exit",
                    "position_to_sell": last_position["order_id"],
                    "profit_vs_last": profit_vs_last,
                    "partial_profit_threshold": partial_profit_threshold,
                    "order_type": order_type,
                    "cycle_number": state.cycle_number,
                    "cycle_trade_count": trade_count
                }
            )
        
        # Satış koşulu yok
        self._debug_log(strategy.id, f"   ❌ SAT engellendi: Kâr koşulu sağlanmadı")
        return TradingSignal(
            should_trade=False,
            reason="SAT engellendi: Kâr koşulu sağlanmadı"
        )
    
    async def process_fill(
        self, 
        strategy: Strategy, 
        state: State, 
        trade: Trade
    ) -> Dict[str, Any]:
        """DCA+OTT fill işlemi - pozisyon güncelleme"""
        
        self._debug_log(strategy.id, f"🔄 FILL İşlemi: {trade.side.value} {trade.quantity} @ ${trade.price}")
        
        # 🔍 DÖNGÜ DEBUG: Fill işlemi başlangıcı
        cycle_debug = self._debug_cycle_calculation(strategy.id, state, f"FILL_{trade.side.value}")
        
        if trade.side == OrderSide.BUY:
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
            
            # Son gerçekleşen işlem noktasını kaydet
            state.custom_data['last_trade_price'] = trade.price
            self._debug_log(strategy.id, f"💰 Son işlem fiyatı kaydedildi: ${trade.price}")
            
            self._debug_log(strategy.id, f"✅ ALIM FILL: Yeni pozisyon eklendi - {trade.quantity} @ ${trade.price} (D{state.cycle_number}-{state.cycle_trade_count})")
            avg_cost_str = f"${state.avg_cost:.4f}" if state.avg_cost is not None else "N/A"
            self._debug_log(strategy.id, f"📊 Güncel durum: {len(state.dca_positions)} pozisyon, Ort. maliyet: {avg_cost_str}")
            
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
            # ÖNEMLİ: Satış türünü mevcut pozisyon durumuna göre belirle
            # trade.strategy_specific_data her zaman None/boş olduğu için bu yaklaşım daha güvenilir
            if len(state.dca_positions) == 0:
                # Pozisyon yok ama satış yapılıyor - bu bir hata
                sell_type = "error_no_positions"
                self._debug_log(strategy.id, f"🚨 HATA: Pozisyon yok ama satış yapılıyor! Trade: {trade.quantity} @ ${trade.price}", "ERROR")
            elif trade.quantity >= state.total_quantity:
                # Satış miktarı toplam pozisyon miktarına eşit veya fazla - tam satış
                sell_type = "full_exit"
                self._debug_log(strategy.id, f"✅ TAM SATIŞ tespit edildi: Satış miktarı ({trade.quantity}) >= Toplam pozisyon ({state.total_quantity})")
            else:
                # Satış miktarı toplam pozisyon miktarından az - kısmi satış
                sell_type = "partial_exit"
                self._debug_log(strategy.id, f"✅ KISMI SATIŞ tespit edildi: Satış miktarı ({trade.quantity}) < Toplam pozisyon ({state.total_quantity})")
            
            # Satış işlemlerinde de sayacı artır (tam satış hariç)
            if sell_type != "full_exit":
                state.cycle_trade_count += 1
            
            # Son gerçekleşen işlem noktasını kaydet
            state.custom_data['last_trade_price'] = trade.price
            self._debug_log(strategy.id, f"💰 Son işlem fiyatı kaydedildi: ${trade.price}")
            
            self._debug_log(strategy.id, f"📊 SAT FILL: Satış türü = {sell_type}")
            
            # Hata durumu: Pozisyon yok ama satış yapılıyor
            if sell_type == "error_no_positions":
                self._debug_log(strategy.id, f"🚨 KRİTİK HATA: Pozisyon yok ama satış emri işlenmiş! Bu bir hayalet satış!", "ERROR")
                self._debug_log(strategy.id, f"   Trade bilgileri: {trade.quantity} @ ${trade.price} (Order: {trade.order_id})", "ERROR")
                self._debug_log(strategy.id, f"   State pozisyon sayısı: {len(state.dca_positions)}", "ERROR")
                return {
                    "action": "error_no_positions",
                    "error": "Pozisyon yok ama satış yapılıyor - hayalet satış",
                    "trade": {
                        "quantity": trade.quantity,
                        "price": trade.price,
                        "order_id": trade.order_id
                    }
                }
            
            if sell_type == "full_exit":
                # Tüm pozisyonları temizle - YENİ DÖNGÜ BAŞLAT
                old_avg_cost = state.avg_cost
                old_positions_count = len(state.dca_positions)
                old_cycle_number = state.cycle_number
                state.dca_positions.clear()
                state.avg_cost = None
                state.total_quantity = 0.0
                
                # YENİ DÖNGÜ İÇİN CYCLE NUMBER'I ARTIR
                state.cycle_number += 1

                # İşlem sayacını sıfırla (yeni döngü için)
                state.cycle_trade_count = 0
                
                # Yeni döngü için state'i sıfırla
                state.custom_data["first_buy_executed"] = False
                state.custom_data["last_ott_action"] = None
                
                # 🔍 DÖNGÜ DEBUG: Tam satış sonrası döngü geçişi
                cycle_debug_after = self._debug_cycle_calculation(strategy.id, state, "FULL_EXIT_CYCLE_TRANSITION")
                
                self._debug_log(strategy.id, f"✅ TAM SATIŞ: {old_positions_count} pozisyon temizlendi - Döngü D{old_cycle_number} tamamlandı")
                self._debug_log(strategy.id, f"💰 Kar/Zarar: Eski ort. maliyet ${old_avg_cost:.4f} → Satış fiyatı ${trade.price:.4f}")
                self._debug_log(strategy.id, f"🔄 Pozisyonlar temizlendi - Yeni döngü için hazır (sonraki alım D{state.cycle_number} olacak)")
                
                self.log_strategy_action(
                    strategy.id,
                    "FULL_EXIT_NEW_CYCLE",
                    f"Tüm pozisyon satıldı @ {trade.price}, Eski ort. maliyet: {old_avg_cost:.6f} - Döngü D{old_cycle_number} tamamlandı, sonraki döngü D{state.cycle_number} olacak"
                )
                
                return {
                    "action": "full_exit_new_cycle",
                    "exit_price": trade.price,
                    "old_avg_cost": old_avg_cost,
                    "old_cycle_number": old_cycle_number,
                    "current_cycle_number": state.cycle_number,
                    "next_cycle_number": state.cycle_number,
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
                        state.avg_cost = total_cost / total_quantity if total_quantity > 0 else 0
                        state.total_quantity = total_quantity
                    else:
                        state.avg_cost = None
                        state.total_quantity = 0.0
                    
                    self._debug_log(strategy.id, f"✅ KISMI SATIŞ: Son pozisyon kaldırıldı - {removed_position.quantity} @ ${removed_position.buy_price}")
                    avg_cost_str = f"${state.avg_cost:.4f}" if state.avg_cost is not None else "N/A"
                    self._debug_log(strategy.id, f"📊 Güncel durum: {len(state.dca_positions)} pozisyon, Ort. maliyet: {avg_cost_str}")
                    
                    self.log_strategy_action(
                        strategy.id,
                        "DCA_PARTIAL_SELL",
                        f"Son pozisyon satıldı: {removed_position.quantity} @ {removed_position.buy_price}, Yeni ort. maliyet: {state.avg_cost:.6f}"
                    )
                
                return {
                    "action": "partial_exit",
                        "removed_position": {
                            "quantity": removed_position.quantity,
                            "buy_price": removed_position.buy_price,
                            "order_id": removed_position.order_id
                        },
                        "new_avg_cost": state.avg_cost,
                        "position_count": len(state.dca_positions)
                    }
                
                return {
                "action": "sell_processed",
                "sell_type": sell_type,
                "price": trade.price
            }
    
    def _analyze_position(self, state: State) -> Dict[str, Any]:
        """Pozisyon analizi"""
        has_positions = len(state.dca_positions) > 0
        position_count = len(state.dca_positions)
        
        if not has_positions:
            return {
                "has_positions": False,
                "position_count": 0,
                "total_quantity": 0.0,
                "avg_cost": 0.0,
                "last_buy_price": 0.0,
                "last_position": None,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0
            }
        
        # Pozisyon bilgileri
        total_quantity = sum(pos.quantity for pos in state.dca_positions)
        total_cost = sum(pos.buy_price * pos.quantity for pos in state.dca_positions)
        avg_cost = total_cost / total_quantity if total_quantity > 0 else 0.0
        
        # Son pozisyon
        last_position = state.dca_positions[-1] if state.dca_positions else None
        
        return {
            "has_positions": True,
            "position_count": position_count,
            "total_quantity": total_quantity,
            "avg_cost": avg_cost,
            "last_buy_price": last_position["buy_price"] if last_position else 0.0,
            "last_position": {
                "quantity": last_position["quantity"],
                "buy_price": last_position["buy_price"],
                "order_id": last_position["order_id"]
            } if last_position else None,
            "unrealized_pnl": 0.0,  # Bu değer current_price ile hesaplanmalı
            "unrealized_pnl_pct": 0.0  # Bu değer current_price ile hesaplanmalı
        }
    
    def _calculate_ott(self, ohlcv_data: List[Dict[str, Any]], period: int, opt: float) -> OTTResult:
        """OTT hesaplama"""
        if len(ohlcv_data) < period:
            return None
        
        # Basit OTT hesaplama (gerçek implementasyon daha karmaşık olmalı)
        closes = [float(candle['close']) for candle in ohlcv_data[-period:]]
        current_price = closes[-1]
        
        # Basit trend analizi
        if current_price > sum(closes[:-1]) / (period - 1):
            return OTTResult(mode=OTTMode.AL, value=current_price)
        else:
            return OTTResult(mode=OTTMode.SAT, value=current_price)