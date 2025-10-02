# Excel Backtest Engine - YENİDEN YAZILDI (23 Eylül 2025)
# Bu dosyada Excel verisiyle backtest analizi yapabileceğimiz sistem oluşturduk
# ÖZELLİKLER:
# - Excel dosyası yükleme ve OHLCV verisi işleme
# - Strateji seçimi ve parametreleri (mevcut stratejilerden)
# - Gerçek zamanlı kar-zarar hesaplaması (bizim PnL sistemimiz)
# - OTT hesaplama ve değerlerini trade'lere aktarma
# - Grafik verileri oluşturma (fiyat, bakiye, işlemler)
# - Detaylı işlem tablosu
# 
# EXCEL FORMAT: Date, Time, Open, High, Low, Close, Volume, WClose
# İşlemler kapanış fiyatına göre, bir sonraki açılış fiyatında gerçekleşir
#
# DÜZELTME (23 Eylül 2025): OTT değerleri sorunu tamamen çözüldü
# - Sorun: OTT hesaplanıyor ama trade objesine aktarılmıyor
# - Çözüm: OTT değerleri doğru şekilde trade objesine aktarılıyor
# - Sonuç: İşlem detayları tablosunda OTT değerleri görünüyor

import pandas as pd
import numpy as np
import io
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict

from .models import Strategy, State, OrderSide, OTTMode, StrategyType
from .base_strategy import BaseStrategy
from .bol_grid_strategy import BollingerGridStrategy
from .dca_ott_strategy import DCAOTTStrategy
from .grid_ott_strategy import GridOTTStrategy
from .indicators import calculate_ott
from .pnl_calculator import pnl_calculator
from .utils import logger


@dataclass
class BacktestTrade:
    """Backtest işlemi"""
    timestamp: datetime
    side: str  # "BUY" veya "SELL"
    price: float
    quantity: float
    total_value: float
    balance_before: float
    balance_after: float
    position_quantity_before: float
    position_quantity_after: float
    position_avg_cost: float  # Ortalama maliyet
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    signal_reason: str
    cash_flow: float  # Kasa akışı (kümülatif)
    # OTT değerleri
    ott_mode: str = None
    ott_upper: float = None
    ott_lower: float = None
    ott_baseline: float = None


@dataclass
class BacktestResult:
    """Backtest sonuçları"""
    # Temel bilgiler
    symbol: str
    strategy_name: str
    strategy_type: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    duration_days: float
    
    # Finansal sonuçlar
    initial_balance: float
    final_balance: float
    final_position_value: float
    total_return: float
    total_return_pct: float
    realized_pnl: float
    unrealized_pnl: float
    
    # İşlem istatistikleri
    total_trades: int
    buy_trades: int
    sell_trades: int
    profitable_trades: int
    losing_trades: int
    win_rate: float
    avg_trade_return: float
    max_drawdown: float
    max_profit: float
    
    # Detaylar
    trades: List[BacktestTrade]
    balance_history: List[Dict[str, Any]]
    parameters: Dict[str, Any]


class ExcelBacktestEngine:
    """
    Excel dosyasından OHLCV verisi alarak backtest yapan motor
    """
    
    def __init__(self):
        self.strategies = {
            'bol_grid': BollingerGridStrategy(),
            'dca_ott': DCAOTTStrategy(),
            'grid_ott': GridOTTStrategy()
        }
    
    def process_excel_file(self, file_content: bytes) -> pd.DataFrame:
        """
        Excel dosyasını işleyip OHLCV DataFrame'i döndür
        
        Args:
            file_content: Excel dosyasının byte içeriği
            
        Returns:
            OHLCV DataFrame
        """
        try:
            logger.info(f"Excel dosyası işleniyor, boyut: {len(file_content)} bytes")
            
            # Excel dosyasını oku
            df = pd.read_excel(io.BytesIO(file_content))
            logger.info(f"Excel okundu, satır sayısı: {len(df)}")
            logger.info(f"Sütunlar: {list(df.columns)}")
            
            # Sütun isimlerini temizle
            df.columns = df.columns.str.strip()
            
            # Gerekli sütunları kontrol et
            required_columns = ['Date', 'Time', 'Open', 'High', 'Low', 'Close']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise Exception(f"Eksik sütunlar: {missing_columns}")
            
            # Tarih ve saat sütunlarını birleştir
            # Excel formatı: DD.MM.YYYY HH:MM (Türkçe format)
            if 'Time' in df.columns:
                # Format belirtilerek doğru parse et
                df['DateTime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str), format='%d.%m.%Y %H:%M', errors='coerce')
            else:
                # Sadece tarih varsa
                df['DateTime'] = pd.to_datetime(df['Date'], format='%d.%m.%Y', errors='coerce')
            
            # Sayısal sütunları dönüştür
            numeric_columns = ['Open', 'High', 'Low', 'Close']
            if 'Volume' in df.columns:
                numeric_columns.append('Volume')
            
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Boş değerleri temizle
            df = df.dropna(subset=['DateTime'] + numeric_columns)
            
            # Tarihe göre sırala
            df = df.sort_values('DateTime').reset_index(drop=True)
            
            logger.info(f"OHLCV verisi hazır: {len(df)} satır, tarih aralığı: {df['DateTime'].min()} - {df['DateTime'].max()}")
            
            return df
            
        except Exception as e:
            logger.error(f"Excel işleme hatası: {e}")
            raise Exception(f"Excel dosyası işlenemedi: {str(e)}")
    
    def run_backtest(
        self, 
        ohlcv_data: pd.DataFrame, 
        strategy_type: str,
        strategy_params: Dict[str, Any],
        symbol: str = "ETHUSDT",  # Excel verisi için varsayılan
        timeframe: str = "1h"
    ) -> BacktestResult:
        """
        OHLCV verisiyle backtest çalıştır
        
        Args:
            ohlcv_data: OHLCV DataFrame
            strategy_type: Strateji tipi ('bol_grid', 'dca_ott', 'grid_ott')
            strategy_params: Strateji parametreleri
            symbol: Sembol adı
            timeframe: Zaman dilimi
            
        Returns:
            BacktestResult
        """
        try:
            logger.info(f"Backtest başlatılıyor: {strategy_type} - {symbol} - {len(ohlcv_data)} mum")
            
            # Stratejiyi al
            if strategy_type not in self.strategies:
                raise Exception(f"Desteklenmeyen strateji: {strategy_type}")
            
            strategy_instance = self.strategies[strategy_type]
            
            # OTT parametrelerini ayır
            ott_params = strategy_params.pop('ott', {'period': 14, 'opt': 2.0})
            logger.info(f"OTT parametreleri: {ott_params}")
            
            # Strategy objesi oluştur
            from .models import OTTParams
            
            strategy_type_enum = StrategyType(strategy_type)
            
            ott_obj = OTTParams(
                period=ott_params.get('period', 14),
                opt=ott_params.get('opt', 2.0)
            )
            
            logger.info(f"OTTParams oluşturuldu: period={ott_obj.period}, opt={ott_obj.opt}")
            
            strategy = Strategy(
                id="backtest_001",
                name=f"backtest_{strategy_type}",
                symbol=symbol,
                timeframe=timeframe,
                strategy_type=strategy_type_enum,
                parameters=strategy_params,
                ott=ott_obj,
                active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # State başlat
            state = State(
                strategy_id="backtest_001",
                symbol=symbol,
                active=True,
                created_at=None,  # JSON serialization için None
                updated_at=None,  # JSON serialization için None
                open_orders=[],
                trades=[],
                custom_data={}
            )
            
            # Backtest için özel alanlar ekle
            state._last_buy_price = None
            state.dca_positions = []
            
            # PnL calculator'ı initialize et
            pnl_calculator.initialize_state_pnl(state)
            
            # Backtest değişkenleri
            trades = []
            balance_history = []
            
            # İlk bakiye kaydı
            initial_balance = state.cash_balance
            balance_history.append({
                'timestamp': ohlcv_data.iloc[0]['DateTime'],
                'price': ohlcv_data.iloc[0]['Close'],
                'cash_balance': state.cash_balance,
                'position_quantity': state.position_quantity,
                'position_value': 0.0,
                'unrealized_pnl': 0.0,
                'total_balance': state.cash_balance
            })
            
            # OTT hesaplama için minimum veri kontrolü (VIDYA için CMO(9) + period gerekli)
            ott_period = ott_obj.period
            start_processing_index = ott_period + 9  # VIDYA için ek 9 veri
            
            logger.info(f"Backtest başlangıcı: {len(ohlcv_data)} mum, OTT hesaplama için {start_processing_index} mumdan sonra başlanacak (OTT period: {ott_period} + CMO: 9)")
            
            # Her mum için işle (OTT hesaplama için yeterli veri olduktan sonra)
            for i in range(start_processing_index, len(ohlcv_data)):
                row = ohlcv_data.iloc[i]
                current_price = float(row['Close'])
                timestamp = row['DateTime']
                
                # OTT hesapla (son ott_period + 10 mum kullan)
                end_idx = i + 1
                start_idx = max(0, end_idx - (ott_period + 10))
                ohlcv_slice = ohlcv_data.iloc[start_idx:end_idx]
                
                # OTT hesaplama
                ott_result = self._calculate_ott(ohlcv_slice, ott_obj)
                
                # OTT hesaplanamadıysa bu mumu atla
                if ott_result is None:
                    logger.warning(f"OTT hesaplanamadı, mum atlanıyor: {timestamp}")
                    continue
                
                # Debug: OTT sonucu
                logger.info(f"OTT hesaplandı - Mode: {ott_result.mode}, Upper: {ott_result.upper:.2f}, Lower: {ott_result.lower:.2f}, Baseline: {ott_result.baseline:.2f}")
                
                # Sinyal hesapla
                signal = self._calculate_signal(strategy, state, current_price, ott_result)
                
                # Debug: Sinyal sonucu
                logger.info(f"Sinyal hesaplandı - Should trade: {signal.get('should_trade', False)}, Reason: {signal.get('reason', 'No reason')}")
                
                # Eğer sinyal varsa işlem yap
                if signal['should_trade']:
                    trade_price = self._get_execution_price(ohlcv_data, i, signal['side'])
                    
                    if trade_price > 0:
                        # İşlem oluştur
                        trade = self._create_trade(
                            timestamp=timestamp,
                            side=signal['side'],
                            price=trade_price,
                            quantity=signal['quantity'],
                            state=state,
                            signal_reason=signal['reason'],
                            ott_result=ott_result
                        )
                        
                        # Trade'i state'e uygula
                        pnl_result = pnl_calculator.process_trade_fill(state, trade)
                        
                        # Backtest için state güncellemeleri
                        if signal['side'] == OrderSide.BUY:
                            state._last_buy_price = trade_price
                            # DCA pozisyonu ekle
                            from .models import DCAPosition
                            dca_position = DCAPosition(
                                timestamp=timestamp,
                                buy_price=trade_price,
                                quantity=trade.quantity
                            )
                            state.dca_positions.append(dca_position)
                        elif signal['side'] == OrderSide.SELL:
                            # Satış türüne göre state güncelleme
                            if "Tam satış" in signal['reason']:
                                # Tam satış: Tüm pozisyonları temizle
                                state._last_buy_price = None
                                state.dca_positions = []
                            elif "Kısmi satış" in signal['reason']:
                                # Kısmi satış: Son pozisyonu DCA listesinden çıkar
                                if hasattr(state, 'dca_positions') and state.dca_positions:
                                    # En son pozisyonu çıkar
                                    state.dca_positions = state.dca_positions[:-1]
                                    # Son alım fiyatını güncelle
                                    if state.dca_positions:
                                        state._last_buy_price = max(state.dca_positions, key=lambda x: x.timestamp).buy_price
                                    else:
                                        state._last_buy_price = None
                        
                        # Trade'i kaydet
                        trades.append(trade)
                
                # Güncel durumu kaydet
                pnl_summary = pnl_calculator.get_pnl_summary(state, current_price)
                balance_history.append({
                    'timestamp': timestamp,
                    'price': current_price,
                    'cash_balance': state.cash_balance,
                    'position_quantity': state.position_quantity,
                    'position_value': pnl_summary['position_value'],
                    'position_avg_cost': state.position_avg_cost if state.position_avg_cost is not None else 0.0,
                    'unrealized_pnl': pnl_summary['unrealized_pnl'],
                    'total_balance': pnl_summary['total_balance']
                })
            
            # Sonuçları hesapla
            result = self._calculate_backtest_results(
                trades=trades,
                balance_history=balance_history,
                strategy=strategy,
                ohlcv_data=ohlcv_data,
                initial_balance=initial_balance
            )
            
            logger.info(f"Backtest tamamlandı: {len(trades)} işlem, final balance: ${result.final_balance:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Backtest hatası: {e}")
            raise Exception(f"Backtest çalıştırılamadı: {str(e)}")
    
    def _calculate_ott(self, ohlcv_data: pd.DataFrame, ott_params) -> Optional[Any]:
        """OTT hesapla"""
        try:
            # OHLC verilerini hazırla
            close_prices = [float(x) for x in ohlcv_data['Close'].tolist() if pd.notna(x)]
            
            if len(close_prices) < ott_params.period + 9:  # VIDYA için CMO(9) + period gerekli
                logger.warning(f"OTT hesaplama için yeterli veri yok. Gerekli: {ott_params.period + 9}, Mevcut: {len(close_prices)}")
                return None
            
            # OTT hesapla
            ott_result = calculate_ott(close_prices, period=ott_params.period, opt=ott_params.opt, strategy_name="backtest")
            
            if ott_result is None:
                logger.warning("OTT result is None after calculation")
                return None
            
            # Eksik alanları ekle
            current_price = float(close_prices[-1])
            if not hasattr(ott_result, 'upper') or ott_result.upper is None:
                ott_result.upper = current_price * 1.02
            if not hasattr(ott_result, 'lower') or ott_result.lower is None:
                ott_result.lower = current_price * 0.98
            if not hasattr(ott_result, 'current_price') or ott_result.current_price is None:
                ott_result.current_price = current_price
                
            return ott_result
            
        except Exception as e:
            logger.error(f"OTT hesaplama hatası: {e}")
            return None
    
    def _calculate_signal(self, strategy: Strategy, state: State, current_price: float, ott_result) -> Dict:
        """Basit sinyal hesaplama"""
        try:
            # OTT mode'a göre sinyal ver
            ott_mode = str(ott_result.mode)
            
            logger.info(f"Sinyal hesaplama - OTT Mode: {ott_mode}, Price: {current_price}, Last buy: {getattr(state, '_last_buy_price', None)}")
            
            if ott_mode == 'OTTMode.AL' or ott_mode == 'AL':
                # AL sinyali - alış yap
                if not hasattr(state, '_last_buy_price') or state._last_buy_price is None:
                    # İlk alış
                    quantity = self._calculate_quantity(strategy, current_price)
                    state._last_buy_price = current_price
                    logger.info(f"İlk alış sinyali - Quantity: {quantity}")
                    return {
                        'should_trade': True,
                        'side': OrderSide.BUY,
                        'quantity': quantity,
                        'reason': "OTT AL sinyali - İlk alış"
                    }
                else:
                    # DCA alışı - min düşüş kontrolü
                    min_drop_pct = float(strategy.parameters.get('min_drop_pct', 2.0))
                    reference_price = state._last_buy_price
                    drop_from_reference = ((reference_price - current_price) / reference_price) * 100
                    
                    logger.info(f"DCA kontrolü - Referans: {reference_price}, Current: {current_price}, Drop: {drop_from_reference:.2f}%, Min: {min_drop_pct}%")
                    
                    if drop_from_reference >= min_drop_pct:
                        # DCA alışı
                        dca_multiplier = float(strategy.parameters.get('dca_multiplier', 1.5))
                        position_count = len(state.dca_positions) if hasattr(state, 'dca_positions') else 0
                        base_usdt = float(strategy.parameters.get('base_usdt', 50.0))
                        dca_usdt = base_usdt * (dca_multiplier ** position_count)
                        quantity = dca_usdt / current_price
                        
                        logger.info(f"DCA alışı sinyali - Drop: {drop_from_reference:.2f}%, DCA USDT: {dca_usdt}, Quantity: {quantity}")
                        
                        return {
                            'should_trade': True,
                            'side': OrderSide.BUY,
                            'quantity': quantity,
                            'reason': f"OTT AL sinyali - DCA alışı (Düşüş: {drop_from_reference:.2f}%)"
                        }
                    else:
                        logger.info(f"DCA alışı engellendi - Drop: {drop_from_reference:.2f}% < Min: {min_drop_pct}%")
            
            elif ott_mode == 'OTTMode.SAT' or ott_mode == 'SAT':
                # SAT sinyali
                logger.info(f"SAT sinyali kontrolü - Position: {state.position_quantity}, Last buy: {getattr(state, '_last_buy_price', None)}")
                if hasattr(state, '_last_buy_price') and state._last_buy_price and state.position_quantity > 0:
                    profit_threshold_pct = float(strategy.parameters.get('profit_threshold_pct', 1.0))
                    avg_cost = state.position_avg_cost if state.position_avg_cost is not None else state._last_buy_price
                    
                    logger.info(f"SAT kontrolü - Current: {current_price}, Avg cost: {avg_cost}, Threshold: {profit_threshold_pct}%")
                    
                    # Tam satış kontrolü: Ortalama maliyetin profit_threshold_pct üzerinde
                    if current_price >= avg_cost * (1 + profit_threshold_pct / 100):
                        quantity = float(state.position_quantity)
                        logger.info(f"Tam satış sinyali - Quantity: {quantity}")
                        return {
                            'should_trade': True,
                            'side': OrderSide.SELL,
                            'quantity': quantity,
                            'reason': f"OTT SAT sinyali - Tam satış (Ort. maliyet %{profit_threshold_pct} üzeri)"
                        }
            
            # Sinyal yok
            logger.info(f"Sinyal yok - OTT Mode: {ott_mode}")
            return {'should_trade': False, 'reason': f'Sinyal yok - OTT Mode: {ott_mode}'}
            
        except Exception as e:
            logger.error(f"Sinyal hesaplama hatası: {e}")
            return {'should_trade': False, 'reason': f'Hata: {str(e)}'}
    
    def _calculate_quantity(self, strategy: Strategy, current_price: float) -> float:
        """İşlem miktarı hesapla"""
        try:
            strategy_type_value = str(strategy.strategy_type.value)
            
            if strategy_type_value == 'dca_ott':
                base_usdt = float(strategy.parameters.get('base_usdt', 50.0))
                quantity = base_usdt / current_price
            elif strategy_type_value == 'grid_ott':
                usdt_grid = float(strategy.parameters.get('usdt_grid', 30.0))
                quantity = usdt_grid / current_price
            elif strategy_type_value == 'bol_grid':
                initial_usdt = float(strategy.parameters.get('initial_usdt', 50.0))
                quantity = initial_usdt / current_price
            else:
                quantity = 50.0 / current_price  # Default
            
            return quantity
                
        except Exception as e:
            logger.error(f"Quantity hesaplama hatası: {e}")
            return 0.001  # Minimum güvenli miktar
    
    def _get_execution_price(self, ohlcv_data: pd.DataFrame, current_index: int, side) -> float:
        """İşlem gerçekleşme fiyatını hesapla"""
        try:
            current_close = float(ohlcv_data.iloc[current_index]['Close'])
            
            # Bir sonraki mumun açılış fiyatını al
            if current_index + 1 < len(ohlcv_data):
                next_open = float(ohlcv_data.iloc[current_index + 1]['Open'])
                return next_open
            else:
                # Son mum ise, mevcut kapanış fiyatını kullan
                return current_close
                
        except Exception as e:
            logger.error(f"Execution price hesaplama hatası: {e}")
            current_close = float(ohlcv_data.iloc[current_index]['Close'])
            return current_close
    
    def _create_trade(
        self, 
        timestamp: datetime, 
        side, 
        price: float, 
        quantity: float,
        state: State,
        signal_reason: str,
        ott_result=None
    ) -> BacktestTrade:
        """Backtest trade objesi oluştur"""
        
        # Önceki durumu kaydet
        balance_before = state.cash_balance
        position_before = state.position_quantity
        
        # Unrealized PnL hesapla (trade öncesi)
        pnl_before = pnl_calculator.calculate_unrealized_pnl(state, price)
        
        # Trade objesi oluştur (PnL hesaplaması için)
        from .models import Trade
        trade_obj = Trade(
            id=f"backtest_{timestamp.isoformat()}",
            timestamp=timestamp,
            strategy_id=state.strategy_id,
            side=side,
            price=price,
            quantity=quantity,
            z=0,  # Grid kademesi (backtest için 0)
            notional=price * quantity,  # USDT tutarı
            gf_before=state.position_avg_cost or price,  # İşlem öncesi ortalama fiyat
            gf_after=price,  # İşlem sonrası fiyat
            commission=0.0,  # Komisyon (backtest için 0)
            order_id=f"backtest_order_{timestamp.isoformat()}"
        )
        
        # PnL hesapla (geçici state kopyası ile)
        temp_state = State(**state.__dict__)
        pnl_result = pnl_calculator.process_trade_fill(temp_state, trade_obj)
        
        # Sonraki durumu al
        balance_after = temp_state.cash_balance
        position_after = temp_state.position_quantity
        
        # Unrealized PnL hesapla (trade sonrası)
        pnl_after = pnl_calculator.calculate_unrealized_pnl(temp_state, price)
        
        # Side değerini string'e çevir
        side_value = str(side.value) if hasattr(side, 'value') else str(side)
        
        # Kasa akışı hesapla
        if side_value.upper() == 'BUY':
            cash_flow = -(price * quantity)  # Para çıkışı (negatif)
        else:  # SELL
            cash_flow = price * quantity  # Para girişi (pozitif)
        
        # OTT değerlerini hazırla
        ott_mode = None
        ott_upper = None
        ott_lower = None
        ott_baseline = None
        
        if ott_result:
            try:
                ott_mode = str(ott_result.mode)
                ott_upper = float(ott_result.upper) if hasattr(ott_result, 'upper') and ott_result.upper is not None else None
                ott_lower = float(ott_result.lower) if hasattr(ott_result, 'lower') and ott_result.lower is not None else None
                ott_baseline = float(ott_result.baseline) if hasattr(ott_result, 'baseline') and ott_result.baseline is not None else None
                
                logger.info(f"Trade OTT değerleri - Mode: {ott_mode}, Upper: {ott_upper}, Lower: {ott_lower}, Baseline: {ott_baseline}")
                
            except Exception as e:
                logger.warning(f"OTT değerleri trade'e aktarılamadı: {e}")
        
        # BacktestTrade oluştur
        backtest_trade = BacktestTrade(
            timestamp=timestamp,
            side=side_value,
            price=price,
            quantity=quantity,
            total_value=price * quantity,
            balance_before=balance_before,
            balance_after=balance_after,
            position_quantity_before=position_before,
            position_quantity_after=position_after,
            position_avg_cost=temp_state.position_avg_cost if temp_state.position_avg_cost is not None else 0.0,
            realized_pnl=pnl_result['realized_pnl_change'],
            unrealized_pnl=pnl_after['unrealized_pnl'],
            total_pnl=pnl_result['realized_pnl_change'] + pnl_after['unrealized_pnl'],
            signal_reason=signal_reason,
            cash_flow=cash_flow,
            ott_mode=ott_mode,
            ott_upper=ott_upper,
            ott_lower=ott_lower,
            ott_baseline=ott_baseline
        )
        
        return backtest_trade
    
    def _calculate_backtest_results(
        self,
        trades: List[BacktestTrade],
        balance_history: List[Dict[str, Any]],
        strategy: Strategy,
        ohlcv_data: pd.DataFrame,
        initial_balance: float
    ) -> BacktestResult:
        """Backtest sonuçlarını hesapla"""
        
        # Temel bilgiler
        start_date = ohlcv_data.iloc[0]['DateTime']
        end_date = ohlcv_data.iloc[-1]['DateTime']
        duration_days = (end_date - start_date).total_seconds() / 86400
        
        # Final durumu
        final_balance_data = balance_history[-1]
        final_balance = final_balance_data['cash_balance']
        final_position_value = final_balance_data['position_value']
        final_unrealized_pnl = final_balance_data['unrealized_pnl']
        total_balance = final_balance_data['total_balance']
        
        # Return hesaplamaları
        total_return = total_balance - initial_balance
        total_return_pct = (total_return / initial_balance * 100) if initial_balance > 0 else 0.0
        
        # İşlem istatistikleri
        total_trades = len(trades)
        buy_trades = len([t for t in trades if t.side == "BUY"])
        sell_trades = len([t for t in trades if t.side == "SELL"])
        
        # Kar/zarar analizi
        profitable_trades = len([t for t in trades if t.realized_pnl > 0])
        losing_trades = len([t for t in trades if t.realized_pnl < 0])
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # Ortalama işlem getirisi
        trade_returns = [t.realized_pnl for t in trades if t.realized_pnl != 0]
        avg_trade_return = np.mean(trade_returns) if trade_returns else 0.0
        
        # Drawdown hesaplama
        balance_values = [b['total_balance'] for b in balance_history]
        peak_balance = initial_balance
        max_drawdown = 0.0
        max_profit = 0.0
        
        for balance in balance_values:
            if balance > peak_balance:
                peak_balance = balance
                profit = balance - initial_balance
                if profit > max_profit:
                    max_profit = profit
            else:
                drawdown = (peak_balance - balance) / peak_balance * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        # Realized PnL toplamı
        realized_pnl = sum([t.realized_pnl for t in trades])
        
        # Sonuç objesi oluştur
        result = BacktestResult(
            symbol=strategy.symbol,
            strategy_name=strategy.name,
            strategy_type=str(strategy.strategy_type.value),
            timeframe=strategy.timeframe,
            start_date=start_date,
            end_date=end_date,
            duration_days=duration_days,
            
            initial_balance=initial_balance,
            final_balance=final_balance,
            final_position_value=final_position_value,
            total_return=total_return,
            total_return_pct=total_return_pct,
            realized_pnl=realized_pnl,
            unrealized_pnl=final_unrealized_pnl,
            
            total_trades=total_trades,
            buy_trades=buy_trades,
            sell_trades=sell_trades,
            profitable_trades=profitable_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_trade_return=avg_trade_return,
            max_drawdown=max_drawdown,
            max_profit=max_profit,
            
            trades=trades,
            balance_history=balance_history,
            parameters=strategy.parameters
        )
        
        return result


# Global instance
excel_backtest_engine = ExcelBacktestEngine()