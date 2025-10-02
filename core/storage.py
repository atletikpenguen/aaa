"""
JSON/CSV Storage sistemi - Kalıcı veri saklama
"""

import json
import csv
import os
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from pathlib import Path

try:
    import aiofiles
    import aiofiles.os
except ImportError:
    print("aiofiles not installed. Install with: pip install aiofiles")
    aiofiles = None

from .models import Strategy, State, Trade, OpenOrder, OrderSide, PartialFillRecord
from .utils import logger
from .pnl_calculator import pnl_calculator


class StorageManager:
    """Storage işlemlerini yöneten sınıf"""
    
    def __init__(self, base_path: str = None):
        # VPS deployment için paths helper kullan
        if base_path is None:
            from .paths import get_data_dir
            self.base_path = Path(get_data_dir())
        else:
            self.base_path = Path(base_path)
            
        self.strategies_file = self.base_path / "strategies.json"
        self.position_limits_file = self.base_path / "position_limits.json"
        self.lock = asyncio.Lock()
        
        # Dizinleri sync olarak oluştur
        try:
            self.base_path.mkdir(exist_ok=True)
        except Exception as e:
            print(f"Storage dizini oluşturma hatası: {e}")
    
    async def _safe_write_file(self, file_path: str, content: str, max_retries: int = 5):
        """Windows permission sorunları için güvenli dosya yazma"""
        for attempt in range(max_retries):
            try:
                temp_file = f"{file_path}.tmp_{attempt}"
                
                # Geçici dosyaya yaz
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(content)
                
                # Windows için daha uzun bekleme
                await asyncio.sleep(0.05)
                
                # Hedef dosya varsa önce sil (Windows için gerekli)
                if await aiofiles.os.path.exists(file_path):
                    try:
                        await aiofiles.os.remove(file_path)
                        await asyncio.sleep(0.02)  # Silme sonrası kısa bekleme
                    except PermissionError:
                        # Dosya hala kullanımda, daha uzun bekle
                        await asyncio.sleep(0.2)
                        await aiofiles.os.remove(file_path)
                
                # Dosyayı taşı
                await aiofiles.os.rename(temp_file, file_path)
                return True
                
            except PermissionError as e:
                logger.warning(f"Dosya yazma izin hatası (deneme {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Daha uzun exponential backoff
                else:
                    raise
            except Exception as e:
                logger.error(f"Dosya yazma hatası: {e}")
                # Geçici dosyayı temizle
                try:
                    temp_file = f"{file_path}.tmp"
                    if await aiofiles.os.path.exists(temp_file):
                        await aiofiles.os.remove(temp_file)
                except:
                    pass
                raise
        return False
    
    async def _ensure_directories(self):
        """Gerekli dizinleri oluştur"""
        try:
            await aiofiles.os.makedirs(self.base_path, exist_ok=True)
            logger.info(f"Storage dizini hazır: {self.base_path}")
        except Exception as e:
            logger.error(f"Storage dizini oluşturma hatası: {e}")
    
    async def _ensure_strategy_directory(self, strategy_id: str):
        """Strateji dizinini oluştur"""
        strategy_dir = self.base_path / strategy_id
        try:
            await aiofiles.os.makedirs(strategy_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Strateji dizini oluşturma hatası {strategy_id}: {e}")
    
    # ============= STRATEGIES =============
    
    async def load_strategies(self) -> List[Strategy]:
        """Tüm stratejileri yükle"""
        async with self.lock:
            try:
                if not await aiofiles.os.path.exists(self.strategies_file):
                    logger.info("strategies.json bulunamadı, boş liste döndürülüyor")
                    return []
                
                async with aiofiles.open(self.strategies_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                    
                    strategies = []
                    for strategy_data in data.get('strategies', []):
                        try:
                            strategy = Strategy(**strategy_data)
                            strategies.append(strategy)
                        except Exception as e:
                            logger.error(f"Strateji parse hatası: {e}, data: {strategy_data}")
                    
                    logger.debug(f"{len(strategies)} strateji yüklendi")
                    return strategies
                    
            except Exception as e:
                logger.error(f"Stratejiler yükleme hatası: {e}")
                return []
    
    async def save_strategies(self, strategies: List[Strategy]):
        """Tüm stratejileri kaydet"""
        async with self.lock:
            try:
                # Strategy objelerini dict'e çevir
                strategies_data = []
                for strategy in strategies:
                    strategy_dict = strategy.dict()
                    # Datetime objelerini ISO string'e çevir
                    strategy_dict['created_at'] = strategy.created_at.isoformat()
                    strategy_dict['updated_at'] = strategy.updated_at.isoformat()
                    strategies_data.append(strategy_dict)
                
                data = {
                    'strategies': strategies_data,
                    'last_update': datetime.now().isoformat()
                }
                
                # Güvenli dosya yazma kullan
                json_content = json.dumps(data, indent=2, ensure_ascii=False)
                await self._safe_write_file(str(self.strategies_file), json_content)
                logger.info(f"{len(strategies)} strateji kaydedildi")
                
            except Exception as e:
                logger.error(f"Stratejiler kaydetme hatası: {e}")
    
    async def get_strategy(self, strategy_id: str) -> Optional[Strategy]:
        """Tek strateji al"""
        strategies = await self.load_strategies()
        for strategy in strategies:
            if strategy.id == strategy_id:
                return strategy
        return None
    
    async def save_strategy(self, strategy: Strategy):
        """Tek strateji kaydet/güncelle"""
        strategies = await self.load_strategies()
        
        # Mevcut stratejiyi bul ve güncelle
        found = False
        for i, existing in enumerate(strategies):
            if existing.id == strategy.id:
                strategy.updated_at = datetime.now()
                strategies[i] = strategy
                found = True
                break
        
        # Yoksa ekle
        if not found:
            strategies.append(strategy)
            await self._ensure_strategy_directory(strategy.id)
        
        await self.save_strategies(strategies)
    
    async def delete_strategy(self, strategy_id: str) -> bool:
        """Strateji sil"""
        strategies = await self.load_strategies()
        
        # Stratejiyi listeden çıkar
        strategies = [s for s in strategies if s.id != strategy_id]
        await self.save_strategies(strategies)
        
        # Strateji dizinini sil
        try:
            strategy_dir = self.base_path / strategy_id
            if await aiofiles.os.path.exists(strategy_dir):
                import shutil
                shutil.rmtree(strategy_dir)
                logger.info(f"Strateji dizini silindi: {strategy_id}")
        except Exception as e:
            logger.error(f"Strateji dizini silme hatası {strategy_id}: {e}")
        
        return True
    
    # ============= STATE =============
    
    def _get_state_file(self, strategy_id: str) -> Path:
        """State dosya yolunu al"""
        return self.base_path / strategy_id / "state.json"
    
    async def load_state(self, strategy_id: str) -> Optional[State]:
        """Strateji durumunu yükle"""
        state_file = self._get_state_file(strategy_id)
        
        try:
            if not await aiofiles.os.path.exists(state_file):
                # Yeni state oluştur
                logger.info(f"State dosyası bulunamadı, yeni oluşturuluyor: {strategy_id}")
                return State(strategy_id=strategy_id, gf=0.0)
            
            async with aiofiles.open(state_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                
                # OpenOrder objelerini düzelt
                if 'open_orders' in data:
                    open_orders = []
                    for order_data in data['open_orders']:
                        try:
                            # Datetime string'i parse et
                            if isinstance(order_data.get('timestamp'), str):
                                order_data['timestamp'] = datetime.fromisoformat(order_data['timestamp'])
                            
                            order = OpenOrder(**order_data)
                            open_orders.append(order)
                        except Exception as e:
                            logger.warning(f"OpenOrder parse hatası: {e}")
                    
                    data['open_orders'] = open_orders
                
                # Datetime string'lerini parse et ve naive ise UTC olarak ayarla
                if isinstance(data.get('last_bar_timestamp'), str):
                    dt = datetime.fromisoformat(data['last_bar_timestamp'])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    data['last_bar_timestamp'] = dt
                
                if isinstance(data.get('last_update'), str):
                    dt = datetime.fromisoformat(data['last_update'])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    data['last_update'] = dt
                
                state = State(**data)
                return state
                
        except FileNotFoundError:
            logger.warning(f"State dosyası bulunamadı {strategy_id}, yeni state oluşturuluyor")
            # Yeni state oluştur ve kaydet
            new_state = State(strategy_id=strategy_id, gf=0.0)
            await self.save_state(new_state)
            return new_state
        except Exception as e:
            logger.error(f"State yükleme hatası {strategy_id}: {e}")
            # Hata durumunda yeni state döndür
            return State(strategy_id=strategy_id, gf=0.0)
    
    async def save_state(self, state: State):
        """Strateji durumunu kaydet"""
        await self._ensure_strategy_directory(state.strategy_id)
        state_file = self._get_state_file(state.strategy_id)
        
        try:
            # State'i dict'e çevir
            state_dict = state.dict()
            
            # Datetime objelerini ISO string'e çevir
            if state_dict.get('last_bar_timestamp'):
                state_dict['last_bar_timestamp'] = state.last_bar_timestamp.isoformat()
            if state_dict.get('last_update'):
                state_dict['last_update'] = state.last_update.isoformat()
            
            # OpenOrder objelerini dict'e çevir
            if state_dict.get('open_orders'):
                orders_data = []
                for order in state.open_orders:
                    order_dict = order.dict()
                    order_dict['timestamp'] = order.timestamp.isoformat()
                    orders_data.append(order_dict)
                state_dict['open_orders'] = orders_data
            
            # Custom data içindeki datetime objelerini kontrol et
            if state_dict.get('custom_data'):
                custom_data = state_dict['custom_data']
                if isinstance(custom_data, dict):
                    for key, value in custom_data.items():
                        if isinstance(value, datetime):
                            custom_data[key] = value.isoformat()
            
            # DCA pozisyonlarındaki datetime objelerini kontrol et
            if state_dict.get('dca_positions'):
                positions_data = []
                for position in state.dca_positions:
                    position_dict = position.dict()
                    if position_dict.get('timestamp'):
                        position_dict['timestamp'] = position.timestamp.isoformat()
                    positions_data.append(position_dict)
                state_dict['dca_positions'] = positions_data
            
            # Güvenli dosya yazma kullan
            json_content = json.dumps(state_dict, indent=2, ensure_ascii=False)
            await self._safe_write_file(str(state_file), json_content)
            
        except Exception as e:
            logger.error(f"State kaydetme hatası {state.strategy_id}: {e}")
    
    # ============= PENDING ORDERS (YENİ) =============
    
    def _get_pending_orders_file(self, strategy_id: str) -> Path:
        """Bekleyen emirler dosyasının yolunu döndürür."""
        return self.base_path / strategy_id / "pending_orders.json"

    async def load_pending_orders(self, strategy_id: str) -> Dict[str, Any]:
        """Bekleyen emirleri dosyadan yükler."""
        pending_orders_file = self._get_pending_orders_file(strategy_id)
        if not await aiofiles.os.path.exists(pending_orders_file):
            return {}
        try:
            async with aiofiles.open(pending_orders_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"[{strategy_id}] Bekleyen emirler yüklenemedi: {e}")
            return {}

    async def save_pending_orders(self, strategy_id: str, pending_orders: Dict[str, Any]):
        """Bekleyen emirleri dosyaya kaydeder."""
        await self._ensure_strategy_directory(strategy_id)
        pending_orders_file = self._get_pending_orders_file(strategy_id)
        try:
            json_content = json.dumps(pending_orders, indent=2, ensure_ascii=False)
            await self._safe_write_file(str(pending_orders_file), json_content)
        except Exception as e:
            logger.error(f"[{strategy_id}] Bekleyen emirler kaydedilemedi: {e}")

    # ============= TRADES =============
    
    def _get_trades_file(self, strategy_id: str) -> Path:
        """Trades dosya yolunu al"""
        return self.base_path / strategy_id / "trades.csv"
    
    async def _ensure_trades_csv_header(self, strategy_id: str):
        """CSV header'ını kontrol et ve yoksa ekle"""
        trades_file = self._get_trades_file(strategy_id)
        
        if not await aiofiles.os.path.exists(trades_file):
            await self._ensure_strategy_directory(strategy_id)
            # CSV header'ı yaz
            header = "timestamp,strategy_id,side,price,quantity,z,notional,gf_before,gf_after,commission,order_id,limit_price,cycle_info\n"
            async with aiofiles.open(trades_file, 'w', encoding='utf-8') as f:
                await f.write(header)
    
    async def save_trade(self, trade: Trade):
        """Tek trade kaydı ekle ve PnL güncelle"""
        await self._ensure_trades_csv_header(trade.strategy_id)
        trades_file = self._get_trades_file(trade.strategy_id)
        
        try:
            # Strateji tipini al
            strategy = await self.get_strategy(trade.strategy_id)
            strategy_type = strategy.strategy_type if strategy else "grid_ott"
            
            # Strateji tipine göre doğru alanları kullan
            if strategy_type == "grid_ott":
                # Grid+OTT için z değeri kullan, cycle_info boş bırak
                csv_line = f"{trade.timestamp.isoformat()},{trade.strategy_id},{trade.side.value},{trade.price},{trade.quantity},{trade.z},{trade.notional},{trade.gf_before},{trade.gf_after},{trade.commission or ''},{trade.order_id or ''},{trade.limit_price or ''},\n"
            elif strategy_type == "dca_ott":
                # DCA+OTT için cycle_info kullan, z değeri 0
                csv_line = f"{trade.timestamp.isoformat()},{trade.strategy_id},{trade.side.value},{trade.price},{trade.quantity},0,{trade.notional},{trade.gf_before},{trade.gf_after},{trade.commission or ''},{trade.order_id or ''},{trade.limit_price or ''},{trade.cycle_info or ''}\n"
            else:
                # Diğer stratejiler için varsayılan
                csv_line = f"{trade.timestamp.isoformat()},{trade.strategy_id},{trade.side.value},{trade.price},{trade.quantity},{trade.z},{trade.notional},{trade.gf_before},{trade.gf_after},{trade.commission or ''},{trade.order_id or ''},{trade.limit_price or ''},{trade.cycle_info or ''}\n"
            
            # Dosyaya append et
            async with aiofiles.open(trades_file, 'a', encoding='utf-8') as f:
                await f.write(csv_line)
            
            # YENİ PnL SİSTEMİ: Trade gerçekleştiğinde state'i güncelle
            await self._update_pnl_on_trade(trade)
            
            logger.info(f"Trade kaydedildi ve PnL güncellendi: {trade.strategy_id} - {trade.side.value} {trade.quantity} @ {trade.price}")
            
        except Exception as e:
            logger.error(f"Trade kaydetme hatası {trade.strategy_id}: {e}")
    
    async def _update_pnl_on_trade(self, trade: Trade):
        """Trade gerçekleştiğinde PnL hesaplamalarını güncelle"""
        try:
            # State'i yükle
            state = await self.load_state(trade.strategy_id)
            if not state:
                logger.warning(f"PnL güncellemesi için state bulunamadı: {trade.strategy_id}")
                return
            
            # PnL alanlarını initialize et (migration için)
            pnl_calculator.initialize_state_pnl(state)
            
            # Trade'i işle ve PnL'i güncelle
            pnl_changes = pnl_calculator.process_trade_fill(state, trade)
            
            # State'i kaydet
            await self.save_state(state)
            
            # PnL GEÇMİŞİ KAYDET: Trade sonrası PnL durumunu kaydet
            try:
                pnl_record = await self.create_pnl_history_record(
                    strategy_id=trade.strategy_id,
                    current_price=trade.price,  # Trade fiyatını güncel fiyat olarak kullan
                    trade=trade
                )
                await self.save_pnl_history(pnl_record)
            except Exception as pnl_hist_error:
                logger.error(f"PnL geçmiş kaydetme hatası {trade.strategy_id}: {pnl_hist_error}")
            
            logger.info(f"PnL güncellendi - {trade.strategy_id}: "
                       f"Realized: ${pnl_changes['realized_pnl_change']:.2f}, "
                       f"Cash: ${pnl_changes['cash_balance_change']:.2f}")
            
        except Exception as e:
            logger.error(f"PnL güncelleme hatası {trade.strategy_id}: {e}")
    
    async def load_trades(self, strategy_id: str, limit: Optional[int] = None) -> List[Trade]:
        """Strateji trade'lerini yükle"""
        trades_file = self._get_trades_file(strategy_id)
        
        if not await aiofiles.os.path.exists(trades_file):
            return []
        
        trades = []
        try:
            async with aiofiles.open(trades_file, 'r', encoding='utf-8') as f:
                # İlk satırı atla (header)
                await f.readline()
                
                lines = []
                async for line in f:
                    lines.append(line.strip())
                
                # Limit varsa son N satırı al
                if limit and len(lines) > limit:
                    lines = lines[-limit:]
                
                # Her satırı parse et
                for line in lines:
                    if not line:
                        continue
                    
                    try:
                        parts = line.split(',')
                        if len(parts) >= 9:
                            # Cycle info alanını kontrol et (yeni alan)
                            cycle_info = parts[12] if len(parts) > 12 and parts[12] else None
                            
                            trade = Trade(
                                timestamp=datetime.fromisoformat(parts[0]),
                                strategy_id=parts[1],
                                side=OrderSide(parts[2].lower()),  # Küçük harfe çevir
                                price=float(parts[3]),
                                quantity=float(parts[4]),
                                z=int(parts[5]),
                                notional=float(parts[6]),
                                gf_before=float(parts[7]),
                                gf_after=float(parts[8]),
                                commission=float(parts[9]) if parts[9] else None,
                                order_id=parts[10] if len(parts) > 10 and parts[10] else None,
                                limit_price=float(parts[11]) if len(parts) > 11 and parts[11] else None,
                                cycle_info=cycle_info
                            )
                            trades.append(trade)
                    except Exception as e:
                        logger.warning(f"Trade parse hatası: {e}, line: {line}")
            
            logger.debug(f"{len(trades)} trade yüklendi: {strategy_id}")
            return trades
            
        except Exception as e:
            logger.error(f"Trades yükleme hatası {strategy_id}: {e}")
            return []
    
    async def get_trades_csv_content(self, strategy_id: str) -> Optional[str]:
        """Raw CSV içeriğini al"""
        trades_file = self._get_trades_file(strategy_id)
        
        try:
            if not await aiofiles.os.path.exists(trades_file):
                return None
            
            async with aiofiles.open(trades_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return content
                
        except Exception as e:
            logger.error(f"CSV içerik okuma hatası {strategy_id}: {e}")
            return None
    
    # ============= STATISTICS =============
    
    async def get_trade_statistics(self, strategy_id: str) -> Dict:
        """Trade istatistiklerini hesapla"""
        trades = await self.load_trades(strategy_id)
        
        if not trades:
            return {
                'total_trades': 0,
                'buy_trades': 0,
                'sell_trades': 0,
                'total_volume': 0.0,
                'total_notional': 0.0,
                'avg_price': 0.0,
                'first_trade': None,
                'last_trade': None,
                'realized_pnl': 0.0,
                'total_profit': 0.0,
                'total_loss': 0.0,
                'win_rate': 0.0,
                'profit_trades': 0,
                'loss_trades': 0,
                'open_buy_value': 0.0
            }
        
        buy_trades = [t for t in trades if t.side == OrderSide.BUY]
        sell_trades = [t for t in trades if t.side == OrderSide.SELL]
        
        total_volume = sum(t.quantity for t in trades)
        total_notional = sum(t.notional for t in trades)
        avg_price = total_notional / total_volume if total_volume > 0 else 0.0
        
        # Kar-zarar hesaplama
        pnl_data = await self.calculate_realized_pnl(strategy_id)
        
        # DCA+OTT için ortalama maliyet hesaplama
        open_buy_value = 0.0
        if buy_trades and not sell_trades:  # Sadece alım işlemleri varsa
            # Tüm alım işlemlerinin ağırlıklı ortalaması
            total_buy_cost = sum(t.price * t.quantity for t in buy_trades)
            total_buy_quantity = sum(t.quantity for t in buy_trades)
            if total_buy_quantity > 0:
                avg_cost = total_buy_cost / total_buy_quantity
                open_buy_value = avg_cost * total_buy_quantity
        
        return {
            'total_trades': len(trades),
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'total_volume': total_volume,
            'total_notional': total_notional,
            'avg_price': avg_price,
            'first_trade': trades[0].timestamp.isoformat() if trades else None,
            'last_trade': trades[-1].timestamp.isoformat() if trades else None,
            'realized_pnl': pnl_data['realized_pnl'],
            'total_profit': pnl_data['total_profit'],
            'total_loss': pnl_data['total_loss'],
            'win_rate': pnl_data['win_rate'],
            'profit_trades': pnl_data['profit_trades'],
            'loss_trades': pnl_data['loss_trades'],
            'open_buy_value': open_buy_value
        }
    
    async def calculate_realized_pnl(self, strategy_id: str) -> Dict:
        """
        Grid trading için gerçekleşen kar-zarar hesapla
        Sadece tamamlanan alış-satış çiftleri (realized PnL)
        Açık pozisyonlar dahil edilmez
        """
        trades = await self.load_trades(strategy_id)
        
        if not trades:
            return {
                'realized_pnl': 0.0,
                'total_profit': 0.0,
                'total_loss': 0.0,
                'win_rate': 0.0,
                'profit_trades': 0,
                'loss_trades': 0,
                'total_buy_value': 0.0,
                'total_sell_value': 0.0,
                'trade_pairs': [],
                'open_buy_value': 0.0,
                'open_sell_value': 0.0
            }
        
        # Tarihe göre sırala (FIFO için)
        trades.sort(key=lambda x: x.timestamp)
        
        # Tüm işlemleri kronolojik olarak eşleştir (FIFO)
        buy_stack = []  # Açık alım pozisyonları
        trade_pairs = []
        
        for trade in trades:
            if trade.side == OrderSide.BUY:
                # Alım işlemi - stack'e ekle
                buy_stack.append({
                    'price': trade.price,
                    'quantity': trade.quantity,
                    'timestamp': trade.timestamp,
                    'z': trade.z,
                    'notional': trade.notional
                })
            else:  # SELL
                # Satım işlemi - FIFO ile eşleştir
                sell_qty = trade.quantity
                sell_price = trade.price
                
                while sell_qty > 0 and buy_stack:
                    buy = buy_stack[0]
                    
                    # Eşleştirilebilecek miktar
                    match_qty = min(sell_qty, buy['quantity'])
                    
                    # Kar-zarar hesapla
                    buy_cost = buy['price'] * match_qty
                    sell_revenue = sell_price * match_qty
                    pair_pnl = sell_revenue - buy_cost
                    
                    trade_pairs.append({
                        'buy_price': buy['price'],
                        'sell_price': sell_price,
                        'quantity': match_qty,
                        'pnl': pair_pnl,
                        'buy_time': buy['timestamp'],
                        'sell_time': trade.timestamp,
                        'buy_z': buy['z'],
                        'sell_z': trade.z
                    })
                    
                    # Miktarları güncelle
                    buy['quantity'] -= match_qty
                    sell_qty -= match_qty
                    
                    # Alım tamamen eşleştiyse stack'ten çıkar
                    if buy['quantity'] <= 0:
                        buy_stack.pop(0)
        
        # İstatistikleri hesapla
        profitable_pairs = sum(1 for pair in trade_pairs if pair['pnl'] > 0)
        losing_pairs = sum(1 for pair in trade_pairs if pair['pnl'] <= 0)
        total_profit = sum(pair['pnl'] for pair in trade_pairs if pair['pnl'] > 0)
        total_loss = sum(abs(pair['pnl']) for pair in trade_pairs if pair['pnl'] <= 0)
        
        # Gerçekleşen kar-zarar (sadece tamamlanan işlemler)
        realized_pnl = sum(pair['pnl'] for pair in trade_pairs)
        
        # Win rate
        total_pairs = len(trade_pairs)
        win_rate = (profitable_pairs / total_pairs * 100) if total_pairs > 0 else 0.0
        
        # Açık pozisyon değerleri
        open_buy_value = sum(buy['notional'] for buy in buy_stack)
        
        # Toplam alım/satım tutarları
        total_buy_value = sum(t.notional for t in trades if t.side == OrderSide.BUY)
        total_sell_value = sum(t.notional for t in trades if t.side == OrderSide.SELL)
        
        return {
            'realized_pnl': realized_pnl,
            'total_profit': total_profit,
            'total_loss': total_loss,
            'win_rate': win_rate,
            'profit_trades': profitable_pairs,
            'loss_trades': losing_pairs,
            'total_buy_value': total_buy_value,
            'total_sell_value': total_sell_value,
            'trade_pairs': trade_pairs,
            'open_buy_value': open_buy_value,
            'open_sell_value': 0.0  # Satım stack'i yok, hep eşleştiriliyor
        }
    
    async def calculate_new_pnl(self, strategy_id: str, current_price: float) -> Dict:
        """
        YENİ PnL HESAPLAMA SİSTEMİ
        
        1000 USD başlangıç sermayesi ile:
        - Nakit bakiye (cash_balance)
        - Gerçekleşen kar/zarar (realized_pnl) 
        - Gerçekleşmeyen kar/zarar (unrealized_pnl)
        - Toplam bakiye (total_balance)
        """
        state = await self.load_state(strategy_id)
        if not state:
            return {
                'error': 'State bulunamadı',
                'initial_balance': 1000.0,
                'cash_balance': 1000.0,
                'realized_pnl': 0.0,
                'unrealized_pnl': 0.0,
                'total_balance': 1000.0,
                'position_quantity': 0.0,
                'position_avg_cost': None,
                'position_side': None
            }
        
        # State'in PnL alanlarını initialize et (migration için)
        pnl_calculator.initialize_state_pnl(state)
        
        # Güncel PnL özetini al
        pnl_summary = pnl_calculator.get_pnl_summary(state, current_price)
        
        return pnl_summary
    
    # ============= PnL GEÇMİŞİ SİSTEMİ =============
    
    def _get_pnl_history_file(self, strategy_id: str) -> Path:
        """PnL geçmiş dosyası yolunu al"""
        return self.base_path / strategy_id / "pnl_history.csv"
    
    async def _ensure_pnl_history_header(self, strategy_id: str):
        """PnL geçmiş dosyası header'ını oluştur"""
        await self._ensure_strategy_directory(strategy_id)
        pnl_file = self._get_pnl_history_file(strategy_id)
        
        if not await aiofiles.os.path.exists(pnl_file):
            header = "timestamp,strategy_id,current_price,total_balance,cash_balance,position_value,realized_pnl,unrealized_pnl,total_pnl,total_return_pct,position_quantity,position_avg_cost,position_side,trigger_trade_id,trigger_side,trigger_price,trigger_quantity\n"
            async with aiofiles.open(pnl_file, 'w', encoding='utf-8') as f:
                await f.write(header)
    
    async def save_pnl_history(self, pnl_record: 'PnLHistory'):
        """PnL geçmiş kaydı ekle"""
        await self._ensure_pnl_history_header(pnl_record.strategy_id)
        pnl_file = self._get_pnl_history_file(pnl_record.strategy_id)
        
        try:
            # CSV satırı oluştur
            csv_line = f"{pnl_record.timestamp.isoformat()},{pnl_record.strategy_id},{pnl_record.current_price},{pnl_record.total_balance},{pnl_record.cash_balance},{pnl_record.position_value},{pnl_record.realized_pnl},{pnl_record.unrealized_pnl},{pnl_record.total_pnl},{pnl_record.total_return_pct},{pnl_record.position_quantity},{pnl_record.position_avg_cost or ''},{pnl_record.position_side or ''},{pnl_record.trigger_trade_id or ''},{pnl_record.trigger_side.value if pnl_record.trigger_side else ''},{pnl_record.trigger_price or ''},{pnl_record.trigger_quantity or ''}\n"
            
            # Dosyaya append et
            async with aiofiles.open(pnl_file, 'a', encoding='utf-8') as f:
                await f.write(csv_line)
            
            logger.info(f"PnL geçmişi kaydedildi: {pnl_record.strategy_id} - Balance: ${pnl_record.total_balance:.2f}, PnL: ${pnl_record.total_pnl:.2f}")
            
        except Exception as e:
            logger.error(f"PnL geçmiş kaydetme hatası {pnl_record.strategy_id}: {e}")
    
    async def create_pnl_history_record(self, strategy_id: str, current_price: float, trade: Optional['Trade'] = None) -> 'PnLHistory':
        """Trade sonrası PnL geçmiş kaydı oluştur"""
        from .pnl_calculator import pnl_calculator
        from .models import PnLHistory
        
        # State'i yükle
        state = await self.load_state(strategy_id)
        if not state:
            raise ValueError(f"State bulunamadı: {strategy_id}")
        
        # PnL özetini al
        pnl_summary = pnl_calculator.get_pnl_summary(state, current_price)
        
        # PnL geçmiş kaydını oluştur
        pnl_record = PnLHistory(
            timestamp=datetime.now(),
            strategy_id=strategy_id,
            current_price=current_price,
            total_balance=pnl_summary['total_balance'],
            cash_balance=pnl_summary['cash_balance'],
            position_value=pnl_summary['position_value'],
            realized_pnl=pnl_summary['realized_pnl'],
            unrealized_pnl=pnl_summary['unrealized_pnl'],
            total_pnl=pnl_summary['total_pnl'],
            total_return_pct=pnl_summary['total_return_pct'],
            position_quantity=pnl_summary['position_quantity'],
            position_avg_cost=pnl_summary['position_avg_cost'],
            position_side=pnl_summary['position_side'],
            # Trade bilgileri (eğer varsa)
            trigger_trade_id=trade.order_id if trade else None,
            trigger_side=trade.side if trade else None,
            trigger_price=trade.price if trade else None,
            trigger_quantity=trade.quantity if trade else None
        )
        
        return pnl_record
    
    # ============= BACKUP & MAINTENANCE =============
    
    async def backup_strategy_data(self, strategy_id: str, backup_path: str):
        """Strateji verilerini yedekle"""
        try:
            import shutil
            source_dir = self.base_path / strategy_id
            if await aiofiles.os.path.exists(source_dir):
                shutil.copytree(source_dir, backup_path)
                logger.info(f"Strateji yedeklendi: {strategy_id} -> {backup_path}")
                return True
        except Exception as e:
            logger.error(f"Yedekleme hatası {strategy_id}: {e}")
        return False
    
    async def cleanup_old_data(self, days: int = 30):
        """Eski verileri temizle"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            # Bu fonksiyon ileriye dönük geliştirilebilir
            logger.info(f"Veri temizleme tamamlandı (>{days} gün)")
        except Exception as e:
            logger.error(f"Veri temizleme hatası: {e}")
    
    # ============= POSITION LIMITS MANAGEMENT =============
    
    async def save_position_limits(self, max_position_usd: float, min_position_usd: float):
        """Pozisyon limitlerini kaydet"""
        try:
            limits_data = {
                'max_position_usd': max_position_usd,
                'min_position_usd': min_position_usd,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            async with self.lock:
                content = json.dumps(limits_data, indent=2, ensure_ascii=False)
                await self._safe_write_file(str(self.position_limits_file), content)
            
            logger.info(f"Pozisyon limitleri kaydedildi: Max={max_position_usd}, Min={min_position_usd}")
            
        except Exception as e:
            logger.error(f"Pozisyon limitleri kaydetme hatası: {e}")
            raise
    
    async def load_position_limits(self) -> Dict:
        """Pozisyon limitlerini yükle"""
        try:
            if not await aiofiles.os.path.exists(self.position_limits_file):
                # Varsayılan değerler
                default_limits = {
                    'max_position_usd': 2000.0,
                    'min_position_usd': -1200.0,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
                await self.save_position_limits(
                    default_limits['max_position_usd'], 
                    default_limits['min_position_usd']
                )
                return default_limits
            
            async with aiofiles.open(self.position_limits_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
                
        except Exception as e:
            logger.error(f"Pozisyon limitleri yükleme hatası: {e}")
            # Hata durumunda varsayılan değerler
            return {
                'max_position_usd': 2000.0,
                'min_position_usd': -1200.0,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
    
    async def load_all_trades(self, limit: Optional[int] = 50) -> List[Trade]:
        """Tüm stratejilerden son işlemleri getir (en yeni en üstte)"""
        all_trades = []
        seen_trades = set()  # Duplicate kontrolü için
        
        try:
            # Tüm strateji klasörlerini tara
            if not await aiofiles.os.path.exists(self.base_path):
                return []
            
            import glob
            pattern = str(self.base_path / "*" / "trades.csv")
            trade_files = glob.glob(pattern)
            
            for trade_file in trade_files:
                try:
                    if not os.path.exists(trade_file):
                        continue
                    
                    # Strateji ID'sini çıkar
                    strategy_id = os.path.basename(os.path.dirname(trade_file))
                    
                    async with aiofiles.open(trade_file, 'r', encoding='utf-8') as f:
                        # İlk satırı atla (header)
                        await f.readline()
                        
                        lines = []
                        async for line in f:
                            lines.append(line.strip())
                        
                        # Her satırı parse et
                        for line in lines:
                            if not line:
                                continue
                            
                            try:
                                parts = line.split(',')
                                if len(parts) >= 9:
                                    # OrderSide enum değerini kontrol et
                                    side_value = parts[2].lower()  # CSV'den gelen değeri küçük harfe çevir
                                    
                                    # Duplicate kontrolü için unique key oluştur
                                    order_id = parts[10] if len(parts) > 10 and parts[10] else None
                                    timestamp = parts[0]
                                    strategy_id_from_csv = parts[1]
                                    side = side_value
                                    price = parts[3]
                                    quantity = parts[4]
                                    
                                    # Unique key: timestamp + strategy_id + side + price + quantity + order_id
                                    unique_key = f"{timestamp}_{strategy_id_from_csv}_{side}_{price}_{quantity}_{order_id}"
                                    
                                    # Eğer bu trade daha önce eklenmişse atla
                                    if unique_key in seen_trades:
                                        logger.debug(f"Duplicate trade atlandı: {unique_key}")
                                        continue
                                    
                                    # Cycle info alanını kontrol et (yeni alan)
                                    cycle_info = parts[12] if len(parts) > 12 and parts[12] else None
                                    
                                    trade = Trade(
                                        timestamp=datetime.fromisoformat(parts[0]),
                                        strategy_id=parts[1],
                                        side=OrderSide(side_value),
                                        price=float(parts[3]),
                                        quantity=float(parts[4]),
                                        z=int(parts[5]),
                                        notional=float(parts[6]),
                                        gf_before=float(parts[7]),
                                        gf_after=float(parts[8]),
                                        commission=float(parts[9]) if parts[9] else None,
                                        order_id=order_id,
                                        cycle_info=cycle_info
                                    )
                                    
                                    all_trades.append(trade)
                                    seen_trades.add(unique_key)
                                    
                            except Exception as e:
                                logger.warning(f"Trade parse hatası: {e}, line: {line}")
                                
                except Exception as e:
                    logger.warning(f"Trade dosyası okuma hatası {trade_file}: {e}")
            
            # Tarih sırasına göre tersten sırala (en yeni en üstte)
            all_trades.sort(key=lambda t: t.timestamp, reverse=True)
            
            # Limit uygula
            if limit and len(all_trades) > limit:
                all_trades = all_trades[:limit]
            
            logger.debug(f"{len(all_trades)} toplam trade yüklendi (duplicate kontrolü ile)")
            return all_trades
            
        except Exception as e:
            logger.error(f"Tüm trade'ler yükleme hatası: {e}")
            return []
    
    async def get_daily_volume_stats(self, days: int = 3) -> List[Dict]:
        """Son N günün günlük long/short hacim istatistiklerini getir"""
        try:
            from collections import defaultdict
            from datetime import timedelta
            
            # Tüm trade'leri yükle (limit olmadan)
            all_trades = await self.load_all_trades(limit=None)
            
            # Bugünden geriye doğru N gün
            today = datetime.now(timezone.utc).date()
            target_dates = []
            for i in range(days):
                target_date = today - timedelta(days=i)
                target_dates.append(target_date)
            
            # Günlere göre trade'leri grupla
            daily_stats = defaultdict(lambda: {
                'date': None,
                'long_volume': 0.0,
                'short_volume': 0.0,
                'long_count': 0,
                'short_count': 0,
                'total_volume': 0.0,
                'total_count': 0,
                'realized_pnl': 0.0  # Günlük kapanmış kar
            })
            
            for trade in all_trades:
                trade_date = trade.timestamp.date()
                
                # Sadece hedef tarihler içinde olan trade'leri işle
                if trade_date not in target_dates:
                    continue
                
                date_key = trade_date.isoformat()
                daily_stats[date_key]['date'] = trade_date
                
                # Notional (USD) değeri kullan
                volume = trade.notional
                
                if trade.side == OrderSide.BUY:
                    # Long pozisyon (alım)
                    daily_stats[date_key]['long_volume'] += volume
                    daily_stats[date_key]['long_count'] += 1
                else:
                    # Short pozisyon (satım)
                    daily_stats[date_key]['short_volume'] += volume
                    daily_stats[date_key]['short_count'] += 1
                
                daily_stats[date_key]['total_volume'] += volume
                daily_stats[date_key]['total_count'] += 1
                
                # Kar/zarar hesaplama kaldırıldı - pnl_history dosyalarından alınacak
            
            # PnL history dosyalarından gerçek kar/zarar bilgilerini al
            await self._add_realized_pnl_from_history(daily_stats, target_dates)
            
            # Sonuçları tarih sırasına göre düzenle (en yeni en üstte)
            result = []
            for date in target_dates:
                date_key = date.isoformat()
                stats = daily_stats[date_key]
                
                # Tarih formatını düzenle
                stats['date'] = date.strftime('%d.%m.%Y')
                stats['date_iso'] = date.isoformat()
                
                # Net pozisyon hesapla (long - short)
                stats['net_volume'] = stats['long_volume'] - stats['short_volume']
                
                result.append(stats)
            
            logger.debug(f"{days} günlük hacim istatistikleri hesaplandı")
            return result
            
        except Exception as e:
            logger.error(f"Günlük hacim istatistikleri hesaplama hatası: {e}")
            return []
    
    async def _add_realized_pnl_from_history(self, daily_stats: dict, target_dates: list):
        """Kar durumu takibi ile aynı yöntemi kullanarak gerçek kar/zarar bilgilerini al"""
        try:
            # Tüm stratejileri al
            strategies = await self.load_strategies()
            
            for strategy in strategies:
                try:
                    # Kar durumu takibi ile aynı yöntemi kullan
                    # Güncel fiyat bilgisini al
                    current_price = 0.0
                    try:
                        from .binance import binance_client
                        ticker = await binance_client.get_symbol_ticker(strategy.symbol.value)
                        if ticker:
                            current_price = float(ticker['price'])
                        else:
                            current_price = 0.0
                    except Exception as price_error:
                        logger.warning(f"Fiyat alma hatası {strategy.symbol}: {price_error}")
                        current_price = 0.0
                    
                    # Strateji için PnL hesapla (kar durumu takibi ile aynı yöntem)
                    pnl_data = await self.calculate_new_pnl(strategy.id, current_price)
                    
                    if 'error' not in pnl_data:
                        strategy_realized = pnl_data.get('realized_pnl', 0.0)
                        
                        # Toplam realized_pnl'i sadece bugün için göster
                        # (Son 3 günün toplam kar/zarar bilgisi)
                        today = datetime.now(timezone.utc).date()
                        today_key = today.isoformat()
                        if today_key in daily_stats:
                            daily_stats[today_key]['realized_pnl'] += strategy_realized
                                
                except Exception as e:
                    logger.warning(f"Strateji kar hesaplama hatası {strategy.id}: {e}")
                    continue
            
            logger.debug("Kar durumu takibi ile aynı yöntemle kar/zarar bilgileri alındı")
            
        except Exception as e:
            logger.error(f"Kar/zarar hesaplama hatası: {e}")
    
    async def enrich_trades_with_grid_data(self, trades: List[Trade]) -> List[Dict]:
        """
        Trade'leri grid referans fiyatı ve kar/zarar bilgileriyle zenginleştir
        """
        enriched_trades = []
        
        # Stratejileri yükle (grid parametreleri için)
        strategies = await self.load_strategies()
        strategy_map = {s.id: s for s in strategies}
        
        for trade in trades:
            strategy = strategy_map.get(trade.strategy_id)
            if not strategy:
                continue
            
            # Grid referans fiyatı = gf_before (işlem öncesi seviye = maliyetimiz)
            grid_reference = trade.gf_before
            
            # Kar/zarar hesapla
            # AL için: daha düşük fiyattan aldıysak kar (gf_before > price)
            # SAT için: daha yüksek fiyattan sattıysak kar (price > gf_before)  
            price_diff = trade.price - grid_reference
            
            if trade.side == OrderSide.BUY:
                # AL işlemi: düşük fiyattan aldıysak kar
                trade_pnl = -price_diff * trade.quantity  # Negatif fark = kar
            else:
                # SAT işlemi: yüksek fiyattan sattıysak kar
                trade_pnl = price_diff * trade.quantity   # Pozitif fark = kar
            
            enriched_trades.append({
                'trade': trade,
                'grid_reference': grid_reference,
                'trade_pnl': trade_pnl,
                'strategy_name': strategy.name if strategy else 'Unknown',
                'strategy_type': strategy.strategy_type.value if strategy else 'unknown'
            })
        
        return enriched_trades
    
    # ============= PARTIAL FILL MONITORING =============
    
    def _get_partial_fills_file(self) -> Path:
        """Partial fills dosya yolunu al"""
        return self.base_path / "partial_fills.json"
    
    async def log_partial_fill(self, partial_fill: "PartialFillRecord"):
        """Kısmi gerçekleşen emri kaydet"""
        from .models import PartialFillRecord  # Import burada
        
        try:
            partial_fills_file = self._get_partial_fills_file()
            
            # Mevcut kayıtları yükle
            existing_records = []
            if await aiofiles.os.path.exists(partial_fills_file):
                try:
                    async with aiofiles.open(partial_fills_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        existing_records = data.get('partial_fills', [])
                except:
                    pass
            
            # Yeni kaydı ekle
            new_record = {
                'timestamp': partial_fill.timestamp.isoformat(),
                'strategy_id': partial_fill.strategy_id,
                'order_id': partial_fill.order_id,
                'side': partial_fill.side.value,
                'original_quantity': partial_fill.original_quantity,
                'filled_quantity': partial_fill.filled_quantity,
                'remaining_quantity': partial_fill.remaining_quantity,
                'price': partial_fill.price,
                'cancel_reason': partial_fill.cancel_reason
            }
            
            existing_records.append(new_record)
            
            # Son 100 kaydı tut (eski olanları sil)
            if len(existing_records) > 100:
                existing_records = existing_records[-100:]
            
            # Kaydet
            data = {
                'partial_fills': existing_records,
                'last_update': datetime.now().isoformat(),
                'total_count': len(existing_records)
            }
            
            json_content = json.dumps(data, indent=2, ensure_ascii=False)
            await self._safe_write_file(str(partial_fills_file), json_content)
            
            logger.warning(f"PARTIAL FILL: {partial_fill.strategy_id} - {partial_fill.side.value} {partial_fill.filled_quantity}/{partial_fill.original_quantity} @ {partial_fill.price}")
            
        except Exception as e:
            logger.error(f"Partial fill kaydetme hatası: {e}")
    
    async def get_partial_fills_stats(self) -> Dict:
        """Kısmi gerçekleşme istatistikleri"""
        try:
            partial_fills_file = self._get_partial_fills_file()
            
            if not await aiofiles.os.path.exists(partial_fills_file):
                return {
                    'total_count': 0,
                    'today_count': 0,
                    'by_strategy': {},
                    'by_side': {'buy': 0, 'sell': 0}
                }
            
            async with aiofiles.open(partial_fills_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                records = data.get('partial_fills', [])
            
            # İstatistikleri hesapla
            today = datetime.now().date()
            today_count = 0
            by_strategy = {}
            by_side = {'buy': 0, 'sell': 0}
            
            for record in records:
                # Bugünkü kayıtlar
                record_date = datetime.fromisoformat(record['timestamp']).date()
                if record_date == today:
                    today_count += 1
                
                # Strateji bazında
                strategy_id = record['strategy_id']
                by_strategy[strategy_id] = by_strategy.get(strategy_id, 0) + 1
                
                # Side bazında
                side = record['side'].lower()
                if side in by_side:
                    by_side[side] += 1
            
            return {
                'total_count': len(records),
                'today_count': today_count,
                'by_strategy': by_strategy,
                'by_side': by_side
            }
            
        except Exception as e:
            logger.error(f"Partial fill stats hatası: {e}")
            return {
                'total_count': 0,
                'today_count': 0,
                'by_strategy': {},
                'by_side': {'buy': 0, 'sell': 0}
            }


# Global storage instance
storage = StorageManager()
