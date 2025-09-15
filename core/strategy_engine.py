"""
Unified Strategy Engine - Factory Pattern ile çoklu strateji desteği

DEĞİŞİKLİK NOTLARI:
- Risk kontrolü mesajları için cooldown mekanizması eklendi
- 10 dakika cooldown süresi ile aynı strateji için tekrarlayan risk mesajları engellendi
- Mesaj gönderme sıklığı azaltıldı, kullanıcı deneyimi iyileştirildi
"""

import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timezone, timedelta

from .base_strategy import BaseStrategy
from .grid_ott_strategy import GridOTTStrategy
from .dca_ott_strategy import DCAOTTStrategy
from .bol_grid_strategy import BollingerGridStrategy
from .models import (
    Strategy, State, TradingSignal, OrderSide, StrategyType,
    OpenOrder, Trade, MarketInfo, OTTResult
)
from .indicators import calculate_ott
from .binance import binance_client
from .storage import storage
from .utils import (
    logger, get_last_closed_bar_data, is_bar_closed, log_trading_action
)
from .telegram import telegram_notifier
from .debug_monitor import universal_debug_monitor, AlertLevel


class StrategyEngine:
    """
    Unified Strategy Engine - Tüm strateji türlerini yönetir
    Factory pattern ile farklı stratejileri destekler
    """
    
    def __init__(self):
        self.active_strategies: Dict[str, bool] = {}
        self.strategy_locks: Dict[str, asyncio.Lock] = {}
        self.error_counts: Dict[str, int] = {}  # strategy_id -> error_count
        self.max_errors = 3  # Maksimum hata sayısı
        
        # Risk kontrolü mesajları için cooldown sistemi
        self.risk_message_cooldowns: Dict[str, datetime] = {}  # strategy_id -> last_message_time
        self.risk_cooldown_minutes = 20  # 10 dakika cooldown
        
        # Strategy factory - yeni stratejiler buraya eklenir
        self.strategy_handlers: Dict[StrategyType, BaseStrategy] = {
            StrategyType.GRID_OTT: GridOTTStrategy(),
            StrategyType.DCA_OTT: DCAOTTStrategy(),
            StrategyType.BOL_GRID: BollingerGridStrategy(),
            # Gelecekteki stratejiler buraya eklenecek
            # StrategyType.BOLLINGER_BANDS: BollingerBandsStrategy(),
            # StrategyType.RSI_SCALPING: RSIScalpingStrategy(),
        }
        
        logger.info(f"Strategy Engine başlatıldı. Desteklenen stratejiler: {list(self.strategy_handlers.keys())}")
    
    def _can_send_risk_message(self, strategy_id: str) -> bool:
        """
        Risk kontrolü mesajı gönderilebilir mi kontrol et (cooldown)
        """
        if strategy_id not in self.risk_message_cooldowns:
            return True
        
        last_message_time = self.risk_message_cooldowns[strategy_id]
        current_time = datetime.now(timezone.utc)
        time_diff = current_time - last_message_time
        
        return time_diff.total_seconds() >= (self.risk_cooldown_minutes * 60)
    
    def _update_risk_message_cooldown(self, strategy_id: str):
        """
        Risk kontrolü mesajı cooldown'unu güncelle
        """
        self.risk_message_cooldowns[strategy_id] = datetime.now(timezone.utc)
    
    def get_strategy_lock(self, strategy_id: str) -> asyncio.Lock:
        """Strateji için lock al"""
        if strategy_id not in self.strategy_locks:
            self.strategy_locks[strategy_id] = asyncio.Lock()
        return self.strategy_locks[strategy_id]
    
    def get_strategy_handler(self, strategy_type: StrategyType) -> Optional[BaseStrategy]:
        """Strateji türü için handler al"""
        return self.strategy_handlers.get(strategy_type)
    
    def increment_error_count(self, strategy_id: str) -> bool:
        """Hata sayacını artır ve gerekirse stratejiyi durdur"""
        if strategy_id not in self.error_counts:
            self.error_counts[strategy_id] = 0
        
        self.error_counts[strategy_id] += 1
        logger.warning(f"Strateji {strategy_id} hata sayısı: {self.error_counts[strategy_id]}/{self.max_errors}")
        
        if self.error_counts[strategy_id] >= self.max_errors:
            logger.error(f"🚨 Strateji {strategy_id} maksimum hata sayısına ulaştı! Strateji durduruluyor.")
            self.active_strategies[strategy_id] = False
            return True  # Strateji durduruldu
        
        return False  # Strateji hala aktif
    
    def reset_error_count(self, strategy_id: str):
        """Hata sayacını sıfırla (başarılı işlem sonrası)"""
        if strategy_id in self.error_counts:
            self.error_counts[strategy_id] = 0
            logger.info(f"Strateji {strategy_id} hata sayacı sıfırlandı")
    
    def get_error_count(self, strategy_id: str) -> int:
        """Strateji hata sayısını al"""
        return self.error_counts.get(strategy_id, 0)
    
    async def process_strategy_tick(self, strategy: Strategy) -> Dict:
        """
        Unified strateji tick işleme - tüm strateji türleri için
        """
        strategy_lock = self.get_strategy_lock(strategy.id)
        
        async with strategy_lock:
            try:
                # Strateji handler'ını al
                handler = self.get_strategy_handler(strategy.strategy_type)
                if not handler:
                    logger.error(f"Desteklenmeyen strateji türü: {strategy.strategy_type}")
                    return {'error': f'Desteklenmeyen strateji türü: {strategy.strategy_type}'}
                
                # State yükle
                state = await storage.load_state(strategy.id)
                if not state:
                    logger.error(f"State yüklenemedi: {strategy.id}")
                    return {'error': 'State yüklenemedi'}
                
                # State'in strateji türünü güncelle (migration için)
                if not hasattr(state, 'strategy_type') or state.strategy_type != strategy.strategy_type:
                    state.strategy_type = strategy.strategy_type
                    await storage.save_state(state)
                
                # Market info al
                market_info = await binance_client.get_market_info(strategy.symbol.value)
                if not market_info:
                    logger.error(f"Market info alınamadı: {strategy.symbol.value}")
                    return {'error': 'Market info alınamadı'}
                
                # OHLCV verisi al
                if strategy.strategy_type == StrategyType.BOL_GRID:
                    # BOL-Grid için Bollinger period kullan
                    bollinger_period = strategy.parameters.get('bollinger_period', 250)
                    ohlcv_limit = max(100, bollinger_period + 10)
                else:
                    # Diğer stratejiler için OTT period kullan
                    ohlcv_limit = max(100, strategy.ott.period + 10)
                
                ohlcv_data = await binance_client.fetch_ohlcv(
                    strategy.symbol.value, 
                    strategy.timeframe.value, 
                    limit=ohlcv_limit
                )
                
                if not ohlcv_data:
                    logger.warning(f"OHLCV verisi alınamadı: {strategy.id}")
                    return {'error': 'OHLCV verisi alınamadı'}
                
                # Son kapalı bar'ı al
                last_bar = get_last_closed_bar_data(ohlcv_data)
                if not last_bar:
                    logger.warning(f"Son kapalı bar bulunamadı: {strategy.id}")
                    return {'error': 'Son kapalı bar bulunamadı'}
                
                # Bar kapanışı kontrolü
                if state.last_bar_timestamp and not is_bar_closed(
                    last_bar['timestamp'], strategy.timeframe.value, state.last_bar_timestamp
                ):
                    # Henüz yeni bar kapanmamış
                    return {'status': 'waiting_for_new_bar'}
                
                # Close price'ları al
                close_prices = [float(bar[4]) for bar in ohlcv_data[:-1]]  # Son bar hariç (açık olabilir)
                current_price = last_bar['close']
                
                # OTT hesapla (BOL-Grid için atla)
                if strategy.strategy_type == StrategyType.BOL_GRID:
                    # BOL-Grid OTT kullanmaz, None gönder
                    ott_result = None
                else:
                    ott_result = calculate_ott(close_prices, strategy.ott.period, strategy.ott.opt, strategy.name)
                    if not ott_result:
                        logger.warning(f"OTT hesaplanamadı: {strategy.id}")
                        return {'error': 'OTT hesaplanamadı'}
                
                # 🛡️ Açık emir varken yeni emir engelle
                if state.open_orders:
                    logger.debug(f"⏳ {strategy.id}: {len(state.open_orders)} açık emir var, yeni emir bekliyor...")
                    signal = TradingSignal(
                        should_trade=False,
                        reason=f"Açık emir beklemede: {len(state.open_orders)} emir"
                    )
                    order_placed = False
                else:
                    # Strateji özel sinyal hesaplama
                    signal = await handler.calculate_signal(
                        strategy, state, current_price, ott_result, market_info, ohlcv_data
                    )
                    
                    # Sinyal varsa pozisyon riski kontrol et
                    order_placed = False
                    if signal.should_trade:
                        # Risk kontrolü
                        risk_check = await self._check_position_risk(signal, strategy)
                        if not risk_check['allowed']:
                            logger.warning(f"🚨 RISK KONTROLÜ: {strategy.id} - {risk_check['reason']}")
                            
                            # 📱 TELEGRAM BİLDİRİMİ - Risk kontrolü iptali (cooldown ile)
                            if self._can_send_risk_message(strategy.id):
                                try:
                                    side_emoji = "🟢" if signal.side == OrderSide.BUY else "🔴"
                                    side_text = "ALIM" if signal.side == OrderSide.BUY else "SATIM"
                                    order_usd = signal.quantity * (signal.target_price or 0)
                                    
                                    telegram_message = f"🚨 RİSK KONTROLÜ İPTALİ\n"
                                    telegram_message += f"📊 Strateji: {strategy.name}\n"
                                    telegram_message += f"💱 Sembol: {strategy.symbol.value}\n"
                                    telegram_message += f"📈 İşlem: {side_emoji} {side_text}\n"
                                    telegram_message += f"🔢 Miktar: {signal.quantity}\n"
                                    telegram_message += f"💰 Tutar: ${order_usd:.2f}\n"
                                    telegram_message += f"⚠️ Sebep: {risk_check['reason']}\n"
                                    telegram_message += f"⏰ Sonraki mesaj: {self.risk_cooldown_minutes} dk sonra"
                                    
                                    await telegram_notifier.send_message(telegram_message)
                                    
                                    # Cooldown'u güncelle
                                    self._update_risk_message_cooldown(strategy.id)
                                    
                                except Exception as e:
                                    logger.warning(f"Risk kontrolü Telegram bildirimi hatası: {e}")
                            else:
                                # Cooldown aktif, sadece log
                                logger.debug(f"Risk kontrolü mesajı cooldown'da: {strategy.id}")
                            
                            return {
                                'status': 'risk_blocked',
                                'message': f"Risk kontrolü: {risk_check['reason']}"
                            }
                        
                        order_placed = await self.execute_trading_signal(strategy, state, signal)
                
                # Bar timestamp güncelle
                state.last_bar_timestamp = last_bar['timestamp']
                state.last_ott_mode = ott_result.mode if ott_result else None
                state.last_update = datetime.now(timezone.utc)
                
                # State kaydet
                await storage.save_state(state)
                
                # Başarılı işlem sonrası hata sayacını sıfırla
                self.reset_error_count(strategy.id)
                
                # 🔍 DEBUG MONITORING: TÜM STRATEJİLER için health check
                if strategy.active and universal_debug_monitor.is_check_needed(strategy.id):
                    asyncio.create_task(self._background_health_check(strategy))
                
                # Sonuç döndür
                return {
                    'status': 'processed',
                    'strategy_type': strategy.strategy_type.value,
                    'current_price': current_price,
                    'ott_mode': ott_result.mode.value if ott_result else 'none',
                    'signal': signal.dict() if signal.should_trade else None,
                    'order_placed': order_placed,
                    'open_orders': len(state.open_orders),
                    'bar_timestamp': last_bar['timestamp'].isoformat(),
                    'handler': handler.strategy_name
                }
                
            except Exception as e:
                logger.error(f"Strategy tick işlem hatası {strategy.id}: {e}")
                # Hata sayacını artır ve gerekirse stratejiyi durdur
                strategy_stopped = self.increment_error_count(strategy.id)
                if strategy_stopped:
                    # Strateji durduruldu, storage'da da pasif yap
                    try:
                        strategy.active = False
                        await storage.save_strategy(strategy)
                        logger.error(f"🚨 Strateji {strategy.id} storage'da da pasif yapıldı")
                    except Exception as storage_error:
                        logger.error(f"Storage güncelleme hatası {strategy.id}: {storage_error}")
                
                return {'error': str(e), 'strategy_stopped': strategy_stopped}
    
    async def execute_trading_signal(
        self, 
        strategy: Strategy, 
        state: State, 
        signal: TradingSignal
    ) -> bool:
        """Unified trading sinyal uygulama"""
        
        if not signal.should_trade:
            return False
        
        try:
            # Emir türünü belirle (market veya limit)
            order_type = signal.strategy_specific_data.get('order_type', 'LIMIT') if signal.strategy_specific_data else 'LIMIT'
            
            if order_type == "MARKET":
                # Market emir oluştur
                order_result = await binance_client.create_market_order(
                    symbol=strategy.symbol.value,
                    side=signal.side,
                    quantity=signal.quantity,
                    strategy_id=strategy.id,
                    strategy_type=strategy.strategy_type.value,
                    grid_level=signal.strategy_specific_data.get('z', None) if signal.strategy_specific_data else None
                )
            else:
                # Limit emir oluştur
                order_result = await binance_client.create_limit_order(
                    symbol=strategy.symbol.value,
                    side=signal.side,
                    quantity=signal.quantity,
                    price=signal.target_price,
                    strategy_id=strategy.id,
                    strategy_type=strategy.strategy_type.value,
                    grid_level=signal.strategy_specific_data.get('z', None) if signal.strategy_specific_data else None
                )
            
            if order_result:
                # Emir türüne göre price alanını ayarla
                order_type = signal.strategy_specific_data.get('order_type', 'LIMIT') if signal.strategy_specific_data else 'LIMIT'
                order_price = signal.target_price if order_type == "LIMIT" else None
                
                # Açık emirlere ekle
                new_order = OpenOrder(
                    order_id=str(order_result['id']),
                    side=signal.side,
                    price=order_price,  # Market emirlerde None
                    quantity=signal.quantity,
                    z=signal.strategy_specific_data.get('z', 0) if signal.strategy_specific_data else 0,
                    timestamp=datetime.now(timezone.utc),
                    strategy_specific_data=signal.strategy_specific_data if signal.strategy_specific_data else {}
                )
                
                state.open_orders.append(new_order)
                state.last_update = datetime.now(timezone.utc)
                
                # State'i kaydet
                await storage.save_state(state)
                
                price_info = f" @ {signal.target_price}" if signal.target_price else " (Market)"
                
                log_trading_action(
                    f"[{strategy.strategy_type.value}] {order_type} emir oluşturuldu: {strategy.id} - {signal.side.value} {signal.quantity}{price_info}",
                    action_type="ORDER"
                )
                
                # Telegram bildirimi gönder - başarısız olursa stratejiyi durdur
                try:
                    telegram_success = await telegram_notifier.send_trade_notification(
                        strategy_name=f"{strategy.name} ({strategy.strategy_type.value})",
                        symbol=strategy.symbol.value,
                        side=signal.side.value,
                        quantity=signal.quantity,
                        price=signal.target_price,
                        order_id=str(order_result['id']),
                        order_type=order_type
                    )
                    
                    # Telegram mesajı başarısız olduysa stratejiyi durdur
                    if not telegram_success:
                        logger.error(f"🚨 TELEGRAM MESAJI BAŞARISIZ - Strateji durduruluyor: {strategy.id}")
                        self.active_strategies[strategy.id] = False
                        strategy.active = False
                        await storage.save_strategy(strategy)
                        
                        # Strateji durdurma bildirimi gönder (bu da başarısız olabilir ama deneyelim)
                        try:
                            await telegram_notifier.send_strategy_notification(
                                strategy_name=strategy.name,
                                symbol=strategy.symbol.value,
                                message_type="error",
                                details="Telegram mesajı gönderilemediği için strateji durduruldu"
                            )
                        except:
                            pass  # Bu da başarısız olursa sessizce geç
                        
                        return False
                        
                except Exception as e:
                    logger.error(f"Telegram bildirimi kritik hatası: {e}")
                    # Telegram hatası da stratejiyi durdursun
                    logger.error(f"🚨 TELEGRAM HATASI - Strateji durduruluyor: {strategy.id}")
                    self.active_strategies[strategy.id] = False
                    strategy.active = False
                    await storage.save_strategy(strategy)
                    return False
                
                return True
            else:
                logger.error(f"Emir oluşturulamadı: {strategy.id}")
                return False
                
        except Exception as e:
            logger.error(f"Trading sinyal uygulama hatası {strategy.id}: {e}")
            return False
    
    async def check_order_fills(self, strategy: Strategy, state: State) -> list[Trade]:
        """
        Unified order fill kontrolü - tüm strateji türleri için
        """
        if not strategy:
            logger.error("check_order_fills: strategy parametresi None")
            return []
            
        if not state or not state.open_orders:
            return []
        
        filled_trades = []
        order_ids = [order.order_id for order in state.open_orders]
        
        logger.debug(f"🔍 {strategy.id}: {len(order_ids)} adet açık emir kontrol ediliyor")
        
        try:
            # Binance'den emir durumlarını kontrol et
            fills = await binance_client.check_order_fills(
                strategy.symbol.value, 
                order_ids, 
                strategy_id=strategy.id,
                strategy_type=strategy.strategy_type.value
            )
            
            if fills:
                log_trading_action(
                    f"✅ [{strategy.strategy_type.value}] {strategy.id}: {len(fills)} adet emir gerçekleşmiş!",
                    action_type="TRADE"
                )
            
            # Strateji handler'ını al
            handler = self.get_strategy_handler(strategy.strategy_type)
            if not handler:
                logger.error(f"Desteklenmeyen strateji türü: {strategy.strategy_type}")
                return []
            
            for fill in fills:
                # İlgili order'ı bul
                filled_order = None
                for order in state.open_orders:
                    if order.order_id == fill['order_id']:
                        filled_order = order
                        break
                
                if not filled_order:
                    continue
                
                # Döngü bilgisini hazırla (DCA+OTT için)
                cycle_info = None
                if strategy.strategy_type == StrategyType.DCA_OTT:
                    # DCA+OTT için döngü bilgisini oluştur
                    cycle_number = filled_order.strategy_specific_data.get('cycle_number', state.cycle_number)
                    cycle_trade_count = filled_order.strategy_specific_data.get('cycle_trade_count', state.cycle_trade_count)
                    
                    # Döngü bilgisini oluştur
                    if cycle_number > 0 and cycle_trade_count > 0:
                        # Normal durum: hem döngü hem işlem sayısı var
                        cycle_info = f"D{cycle_number}-{cycle_trade_count}"
                    elif cycle_number > 0 and cycle_trade_count == 0:
                        # Full exit sonrası: döngü var ama işlem sayısı sıfır
                        # Bu durumda state'den mevcut değerleri kullan
                        cycle_info = f"D{state.cycle_number}-{state.cycle_trade_count + 1}"
                    else:
                        # Fallback: State'den mevcut döngü bilgisini kullan
                        if state.cycle_number > 0:
                            cycle_info = f"D{state.cycle_number}-{state.cycle_trade_count + 1}"
                        else:
                            # İlk alım durumu
                            cycle_info = "D1-1"
                
                # 🛡️ DUPLICATE FILL KONTROLÜ: Aynı order_id ile daha önce trade kaydedilmiş mi?
                if strategy.strategy_type == StrategyType.DCA_OTT:
                    # DCA stratejileri için duplicate kontrol
                    existing_trades = await storage.load_trades(strategy.id, limit=100)
                    for existing_trade in existing_trades:
                        if existing_trade.order_id == fill['order_id']:
                            logger.warning(f"⚠️ DUPLICATE FILL: Order {fill['order_id']} zaten trades.csv'de kayıtlı, atlanıyor")
                            continue  # Bu fill'i atla
                
                # Trade kaydı oluştur
                trade = Trade(
                    timestamp=fill['timestamp'],
                    strategy_id=strategy.id,
                    side=filled_order.side,
                    price=fill['price'],  # Gerçekleşen ortalama fiyat
                    quantity=fill['filled_qty'],
                    z=filled_order.z,  # Grid için, DCA için 0
                    notional=fill['price'] * fill['filled_qty'],
                    gf_before=state.gf if state.gf is not None else fill['price'],
                    gf_after=0,  # Handler tarafından güncellenecek
                    order_id=fill['order_id'],
                    limit_price=fill.get('limit_price'),
                    strategy_specific_data=filled_order.strategy_specific_data,  # OpenOrder'dan strategy_specific_data al
                    cycle_info=cycle_info  # DCA döngü bilgisi
                )
                
                # Komisyon bilgisini ekle
                if fill.get('fee') and fill['fee'].get('cost'):
                    trade.commission = float(fill['fee']['cost'])
                
                # Strateji özel fill işlemi
                custom_updates = await handler.process_fill(strategy, state, trade)
                
                # Trade'in gf_after ve limit_price'ını güncelle (Grid için)
                if strategy.strategy_type == StrategyType.GRID_OTT:
                    trade.gf_after = state.gf if state.gf is not None else trade.price
                    # Grid stratejilerinde limit_price = yeni GF olmalı
                    trade.limit_price = state.gf if state.gf is not None else trade.price
                else:
                    trade.gf_after = trade.gf_before  # DCA için GF kullanmıyor
                
                filled_trades.append(trade)
                
                # Strateji istatistiklerini güncelle
                await self._update_strategy_stats(strategy, trade)
                
                logger.info(f"[{strategy.strategy_type.value}] Emir doldu: {strategy.id} - {trade.side.value} {trade.quantity} @ {trade.price}")
            
            # Doldurulan emirleri open_orders'dan çıkar
            filled_order_ids = [fill['order_id'] for fill in fills]
            state.open_orders = [o for o in state.open_orders if o.order_id not in filled_order_ids]
            
            # Trade'leri kaydet
            for trade in filled_trades:
                await storage.save_trade(trade)
            
            # State'i kaydet
            if filled_trades:
                state.last_update = datetime.now(timezone.utc)
                await storage.save_state(state)
            
            return filled_trades
            
        except Exception as e:
            strategy_id = strategy.id if strategy else "UNKNOWN"
            logger.error(f"Order fill kontrol hatası {strategy_id}: {e}")
            return []
    
    async def _update_strategy_stats(self, strategy: Strategy, trade: Trade):
        """Strateji istatistiklerini güncelle"""
        try:
            strategy.total_trades += 1
            strategy.updated_at = datetime.now(timezone.utc)
            await storage.save_strategy(strategy)
        except Exception as e:
            logger.error(f"Strateji stats güncelleme hatası: {e}")
    
    async def initialize_strategy_state(self, strategy: Strategy) -> State:
        """
        Yeni strateji için initial state oluştur
        """
        handler = self.get_strategy_handler(strategy.strategy_type)
        if not handler:
            raise ValueError(f"Desteklenmeyen strateji türü: {strategy.strategy_type}")
        
        # Handler'dan initial custom data al
        custom_data = await handler.initialize_state(strategy)
        
        # Grid+OTT için legacy uyumluluk
        gf = strategy.gf if strategy.strategy_type == StrategyType.GRID_OTT else None
        
        state = State(
            strategy_id=strategy.id,
            strategy_type=strategy.strategy_type,
            gf=gf,
            custom_data=custom_data
        )
        
        return state
    
    async def validate_strategy(self, strategy: Strategy) -> tuple[bool, str]:
        """
        Strateji konfigürasyonunu validate et
        """
        handler = self.get_strategy_handler(strategy.strategy_type)
        if not handler:
            return False, f"Desteklenmeyen strateji türü: {strategy.strategy_type}"
        
        return await handler.validate_strategy_config(strategy)
    
    async def start_strategy(self, strategy_id: str):
        """Stratejiyi aktif yap"""
        self.active_strategies[strategy_id] = True
        logger.info(f"Strateji başlatıldı: {strategy_id}")
    
    async def stop_strategy(self, strategy_id: str):
        """Stratejiyi durdur"""
        self.active_strategies[strategy_id] = False
        logger.info(f"Strateji durduruldu: {strategy_id}")
    
    def is_strategy_active(self, strategy_id: str) -> bool:
        """Strateji aktif mi?"""
        return self.active_strategies.get(strategy_id, False)
    
    async def cleanup_strategy(self, strategy_id: str):
        """Strateji temizliği - tüm açık emirleri iptal et"""
        try:
            strategy = await storage.get_strategy(strategy_id)
            if strategy:
                # Tüm açık emirleri iptal et
                cancelled = await binance_client.cancel_all_orders(strategy.symbol.value)
                logger.info(f"Strateji temizlendi: {strategy_id} - {cancelled} emir iptal edildi")
                
                # State'den açık emirleri temizle
                state = await storage.load_state(strategy_id)
                if state:
                    state.open_orders.clear()
                    state.last_update = datetime.now(timezone.utc)
                    await storage.save_state(state)
        except Exception as e:
            logger.error(f"Strateji temizlik hatası {strategy_id}: {e}")
    
    async def manage_order_lifecycle(self, strategy: Strategy, state: State):
        """
        Açık emirlerin yaşam döngüsünü yönet
        
        🎯 Kullanıcı Stratejisi:
        - 3 dakika timeout
        - Kısmi fill = iptal (sanki hiç gönderilmemiş gibi)
        - Partial fill monitoring
        """
        if not state.open_orders:
            return
            
        from .models import PartialFillRecord  # Import burada
        current_time = datetime.now(timezone.utc)
        timeout_minutes = 3
        
        # Detaylı order durumlarını kontrol et
        order_ids = [order.order_id for order in state.open_orders]
        order_details = await binance_client.check_order_status_detailed(
            strategy.symbol.value, order_ids
        )
        
        orders_to_cancel = []
        orders_to_remove = []
        
        for order_detail in order_details:
            # State'deki matching order'ı bul
            state_order = None
            for order in state.open_orders:
                if order.order_id == order_detail['order_id']:
                    state_order = order
                    break
            
            if not state_order:
                continue
            
            # 1️⃣ Timeout kontrolü (3 dakika)
            age_minutes = (current_time - state_order.timestamp).total_seconds() / 60
            if age_minutes >= timeout_minutes:
                orders_to_cancel.append((state_order, order_detail, f"timeout_{age_minutes:.1f}dk"))
                continue
            
            # 2️⃣ Partial fill kontrolü
            if order_detail['is_partial']:
                # Kısmi gerçekleşmiş - kullanıcı stratejisi: iptal et!
                partial_record = PartialFillRecord(
                    timestamp=current_time,
                    strategy_id=strategy.id,
                    order_id=order_detail['order_id'],
                    side=OrderSide(order_detail['side'].lower()),
                    original_qty=order_detail['original_qty'],
                    filled_qty=order_detail['filled_qty'],
                    remaining_qty=order_detail['remaining_qty'],
                    price=order_detail['price'],
                    reason="partial_fill"
                )
                
                orders_to_cancel.append((state_order, order_detail, "partial_fill"))
                
                # Kısmi fill kaydını tut (optional)
                if not hasattr(state, 'partial_fills'):
                    state.partial_fills = []
                state.partial_fills.append(partial_record)
                
                logger.warning(f"🟡 Kısmi gerçekleşme: {strategy.id} - {order_detail['order_id']} "
                             f"({order_detail['filled_qty']}/{order_detail['original_qty']}) iptal ediliyor")
                continue
        
        # 3️⃣ Toplu iptal işlemi
        if orders_to_cancel:
            cancel_order_ids = [item[0].order_id for item in orders_to_cancel]
            cancelled_count = await binance_client.cancel_orders_batch(
                strategy.symbol.value, cancel_order_ids
            )
            
            # State'den temizle
            cancelled_order_ids = [item[0].order_id for item in orders_to_cancel]
            state.open_orders = [o for o in state.open_orders if o.order_id not in cancelled_order_ids]
            
            # Detaylı log
            for state_order, order_detail, reason in orders_to_cancel:
                logger.info(f"❌ Emir iptal: {strategy.id} - {state_order.order_id} ({reason})")
            
            logger.info(f"🗑️ Toplu iptal: {strategy.id} - {cancelled_count}/{len(orders_to_cancel)} emir iptal edildi")
            
            # State kaydet
            state.last_update = current_time
            await storage.save_state(state)

    def get_supported_strategies(self) -> list[str]:
        """Desteklenen strateji türlerini döndür"""
        return [strategy_type.value for strategy_type in self.strategy_handlers.keys()]
    
    async def _check_position_risk(self, signal: TradingSignal, strategy: Strategy) -> Dict:
        """
        Pozisyon risk kontrolü - Net pozisyon limitlerini kontrol et
        """
        try:
            # Pozisyon limitlerini yükle
            limits = await storage.load_position_limits()
            max_position_usd = limits['max_position_usd']
            min_position_usd = limits['min_position_usd']
            
            # Mevcut tüm pozisyonları al
            positions_data = await binance_client.get_all_positions()
            current_net_position = positions_data.get('net_position_usd', 0.0)
            
            # Emir tutarını hesapla
            if signal.target_price is None or signal.target_price <= 0:
                # Market emir için güncel fiyatı kullan
                try:
                    current_price = await binance_client.get_current_price(strategy.symbol.value)
                    if current_price and current_price > 0:
                        order_usd = signal.quantity * current_price
                        logger.info(f"Risk kontrolü: Market emir için güncel fiyat kullanıldı: ${current_price:.6f}")
                    else:
                        logger.warning(f"Risk kontrolü: Güncel fiyat alınamadı - risk kontrolü atlanıyor")
                        return {
                            'allowed': True,
                            'reason': 'Market emir - güncel fiyat alınamadı'
                        }
                except Exception as e:
                    logger.warning(f"Risk kontrolü: Güncel fiyat alma hatası ({e}) - risk kontrolü atlanıyor")
                    return {
                        'allowed': True,
                        'reason': 'Market emir - fiyat hatası'
                    }
            else:
                order_usd = signal.quantity * signal.target_price
            
            # Risk hesaplaması
            if signal.side == OrderSide.BUY:
                # Alış emri - net pozisyona eklenir
                projected_position = current_net_position + order_usd
                
                if projected_position > max_position_usd:
                    return {
                        'allowed': False,
                        'reason': f"Maksimum pozisyon aşılacak: Mevcut={current_net_position:.2f}$, Emir={order_usd:.2f}$, Toplam={projected_position:.2f}$, Max={max_position_usd:.2f}$"
                    }
            
            elif signal.side == OrderSide.SELL:
                # Satış emri - net pozisyondan çıkarılır
                projected_position = current_net_position - order_usd
                
                if projected_position < min_position_usd:
                    return {
                        'allowed': False,
                        'reason': f"Minimum pozisyon aşılacak: Mevcut={current_net_position:.2f}$, Emir={order_usd:.2f}$, Toplam={projected_position:.2f}$, Min={min_position_usd:.2f}$"
                    }
            
            # Risk kontrolü geçti
            return {
                'allowed': True,
                'current_position': current_net_position,
                'projected_position': current_net_position + (order_usd if signal.side == OrderSide.BUY else -order_usd),
                'order_usd': order_usd
            }
            
        except Exception as e:
            logger.error(f"Risk kontrolü hatası: {e}")
            # Hata durumunda güvenli tarafta kal - işleme izin verme
            return {
                'allowed': False,
                'reason': f"Risk kontrolü hatası: {e}"
            }
    
    async def _background_health_check(self, strategy: Strategy):
        """
        Background'da çalışan health check (performance için async)
        """
        try:
            health_report = await universal_debug_monitor.check_strategy_health(strategy)
            
            # Kritik sorunları logla
            critical_issues = [i for i in health_report.get('issues', []) if i.get('severity') == 'critical']
            if critical_issues:
                logger.error(f"🚨 KRITIK SORUN: {strategy.id} - {len(critical_issues)} kritik sorun tespit edildi")
                for issue in critical_issues:
                    logger.error(f"   ❌ {issue.get('type', 'unknown')}: {issue.get('message', str(issue))}")
            
            # Error sorunları logla
            error_issues = [i for i in health_report.get('issues', []) if i.get('severity') == 'error']
            if error_issues:
                logger.warning(f"⚠️ HATA: {strategy.id} - {len(error_issues)} hata tespit edildi")
                for issue in error_issues:
                    logger.warning(f"   ❌ {issue.get('type', 'unknown')}: {issue.get('message', str(issue))}")
            
            # 🛡️ OTOMATIK DURDURMA DEĞERLENDİRMESİ
            if critical_issues or error_issues:
                auto_stopped = await universal_debug_monitor.evaluate_auto_stop(strategy, health_report)
                if auto_stopped:
                    logger.error(f"🛑 STRATEJI OTOMATIK DURDURULDU: {strategy.name} ({strategy.id})")
                    
                    # Strategy engine'de de pasif yap
                    self.active_strategies[strategy.id] = False
                    
                    # Açık emirleri temizle
                    await self.cleanup_strategy(strategy.id)
        
        except Exception as e:
            logger.error(f"Background health check hatası {strategy.id}: {e}")


# Global strategy engine instance
strategy_engine = StrategyEngine()
