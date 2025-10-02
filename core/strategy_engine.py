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
from .order_manager import OrderManager  # YENİ


class StrategyEngine:
    """
    Unified Strategy Engine - Tüm strateji türlerini yönetir
    Factory pattern ile farklı stratejileri destekler
    """
    
    def __init__(self):
        self.active_strategies: Dict[str, bool] = {}
        self.strategy_locks: Dict[str, asyncio.Lock] = {}
        self.error_counts: Dict[str, int] = {}  # strategy_id -> error_count
        self.max_errors = 5 # Maksimum hata sayısı
        
        # YENİ: Her strateji için OrderManager tutacak
        self.order_managers: Dict[str, OrderManager] = {}
        
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
    
    # YENİ: Strateji için OrderManager al/oluştur
    def get_order_manager(self, strategy_id: str) -> OrderManager:
        if strategy_id not in self.order_managers:
            self.order_managers[strategy_id] = OrderManager(
                storage=storage, 
                binance=binance_client, 
                strategy_id=strategy_id
            )
        return self.order_managers[strategy_id]
    
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
                # YENİ: OrderManager'ı al
                order_manager = self.get_order_manager(strategy.id)

                # Strateji parametrelerini kontrol et ve eksik parametreleri ekle
                strategy = self._ensure_strategy_parameters(strategy)
                
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
                
                # 🛡️ YENİ KONTROL: OrderManager'da bekleyen emir var mı?
                order_placed = False  # Değişkeni başta tanımla
                if order_manager.has_pending_orders():
                    logger.debug(f"⏳ {strategy.id}: {order_manager.get_pending_order_count()} bekleyen emir var, yeni sinyal işlenmiyor.")
                    signal = TradingSignal(should_trade=False, reason="Bekleyen emir var.")
                else:
                    # Strateji özel sinyal hesaplama
                    signal = await handler.calculate_signal(
                        strategy, state, current_price, ott_result, market_info, ohlcv_data
                    )
                    
                    # Sinyal varsa pozisyon riski kontrol et
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
                        
                    # YENİ: Emir gönderme mantığı OrderManager'a devredildi
                    order_result = await self.execute_trading_signal(strategy, signal)
                    order_placed = order_result is not None
                
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
        signal: TradingSignal
    ) -> Optional[Dict[str, Any]]:
        """Trading sinyalini OrderManager aracılığıyla uygula"""
        
        if not signal.should_trade:
            return None
        
        try:
            order_manager = self.get_order_manager(strategy.id)
            
            # OrderManager aracılığıyla emir oluştur
            # Market emirleri için price=None, Limit emirleri için target_price kullan
            order_data = await order_manager.create_order(
                side=signal.side,
                quantity=signal.quantity,
                price=signal.target_price if signal.target_price else None,
                order_type="MARKET" if not signal.target_price else "LIMIT"
            )
            
            if order_data:
                price_info = f" @ {signal.target_price}" if signal.target_price else " (Market)"
                log_trading_action(
                    f"[{strategy.strategy_type.value}] Emir oluşturma isteği gönderildi: {strategy.id} - {signal.side.value} {signal.quantity}{price_info}",
                    action_type="ORDER_CREATE"
                )
                
                # Telegram bildirimi burada GÖNDERİLMEMELİ. 
                # Bildirim, emir 'SUBMITTED' (borsa tarafından onaylandı) olduğunda OrderManager tarafından gönderilmeli.
                
                return order_data
            else:
                logger.error(f"OrderManager aracılığıyla emir oluşturulamadı: {strategy.id}")
                return None
                
        except Exception as e:
            logger.error(f"Trading sinyal uygulama hatası {strategy.id}: {e}")
            return None
    
    async def check_order_fills(self, strategy: Strategy, state: State) -> list[Trade]:
        """
        DEPRECATED: Bu fonksiyon artık kullanılmıyor.
        Emir takibi OrderManager.reconcile_orders tarafından yapılıyor.
        """
        logger.warning(f"DEPRECATED: check_order_fills fonksiyonu kullanıldı. OrderManager sistemi aktif.")
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
            symbol=strategy.symbol,  # ✅ Eksik olan satır eklendi
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

    def _ensure_strategy_parameters(self, strategy: Strategy) -> Strategy:
        """
        Strateji parametrelerini kontrol et ve eksik parametreleri varsayılan değerlerle ekle
        """
        try:
            # DCA+OTT stratejisi için eksik parametreleri kontrol et
            if strategy.strategy_type == StrategyType.DCA_OTT:
                # Eksik parametreleri varsayılan değerlerle ekle
                if 'profit_threshold_pct' not in strategy.parameters:
                    strategy.parameters['profit_threshold_pct'] = 1.0
                    logger.info(f"Strateji {strategy.id} için profit_threshold_pct parametresi eklendi (varsayılan: 1.0)")
                
                if 'base_usdt' not in strategy.parameters:
                    strategy.parameters['base_usdt'] = 100.0
                    logger.info(f"Strateji {strategy.id} için base_usdt parametresi eklendi (varsayılan: 100.0)")
                
                if 'dca_multiplier' not in strategy.parameters:
                    strategy.parameters['dca_multiplier'] = 1.5
                    logger.info(f"Strateji {strategy.id} için dca_multiplier parametresi eklendi (varsayılan: 1.5)")
                
                if 'min_drop_pct' not in strategy.parameters:
                    strategy.parameters['min_drop_pct'] = 2.0
                    logger.info(f"Strateji {strategy.id} için min_drop_pct parametresi eklendi (varsayılan: 2.0)")
            
            return strategy
            
        except Exception as e:
            logger.error(f"Strateji parametre kontrolü hatası {strategy.id}: {e}")
            return strategy


# Global strategy engine instance
strategy_engine = StrategyEngine()
