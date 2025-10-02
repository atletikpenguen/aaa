# PnL Calculator - Düzeltilmiş kar-zarar hesaplama sistemi (22 Eylül 2025)
# Bu dosyada profesyonel PnL takip sistemini implement ettik
# DÜZELTİLEN ÖZELLIKLER:
# - 1000 USD sabit başlangıç bakiyesi (realized PnL ile güncellenir)
# - Pozisyon artırımında bakiye değişmez, pozisyon azaltımında değişir
# - Pozisyon artırımında ortalama maliyet güncellenir
# - Pozisyon azaltımında ortalama maliyet DEĞİŞMEZ
# - Gerçek zamanlı unrealized PnL hesaplaması
# - Short/Long pozisyonlar için farklı formüller
#
# DÜZELTME (22 Eylül 2025 - Akşam): Short Pozisyon Unrealized PnL Bug Düzeltmesi
# SORUN: Short pozisyonda fiyat artarken kar gözüküyordu (yanlış!)
# ÇÖZÜM: Short pozisyon formülünde abs() kullanarak doğru işaret elde ettik
# Short pozisyonda: fiyat artarsa zarar (-), fiyat düşerse kar (+)

from typing import Dict, Optional, Tuple
from .models import State, Trade, OrderSide
# from .utils import logger
import logging
logger = logging.getLogger(__name__)


class PnLCalculator:
    """
    Düzeltilmiş kar-zarar hesaplama sistemi
    
    Her strateji 1000 USD ile başlar ve şu mantıkla çalışır:
    
    TEMEL KURAL:
    - Pozisyon ARTIRIMI: Bakiye değişmez, ortalama maliyet güncellenir
    - Pozisyon AZALTIMI: Realized PnL bakiyeye eklenir, ortalama maliyet değişmez
    
    TAKIP EDİLEN DEĞERLER:
    - cash_balance: Başlangıç bakiyesi + gerçekleşen kar/zarar
    - position_quantity: Net pozisyon miktarı (+long, -short)  
    - position_avg_cost: Pozisyon ortalama maliyeti (sadece artırımda değişir)
    - realized_pnl: Gerçekleşen kar/zarar toplamı
    """
    
    def __init__(self):
        pass
    
    def initialize_state_pnl(self, state: State) -> None:
        """
        State'in PnL alanlarını initialize et
        Mevcut state'ler için migration yapılır
        """
        # Yeni alanları initialize et
        if not hasattr(state, 'initial_balance'):
            state.initial_balance = 1000.0
        if not hasattr(state, 'cash_balance'):
            state.cash_balance = 1000.0
        if not hasattr(state, 'realized_pnl'):
            state.realized_pnl = 0.0
        if not hasattr(state, 'position_quantity'):
            state.position_quantity = 0.0
        if not hasattr(state, 'position_avg_cost'):
            state.position_avg_cost = None
        if not hasattr(state, 'position_side'):
            state.position_side = None
            
        # Legacy alanlardan migration yap
        if hasattr(state, 'total_quantity') and state.total_quantity > 0:
            state.position_quantity = state.total_quantity
            if hasattr(state, 'avg_cost') and state.avg_cost:
                state.position_avg_cost = state.avg_cost
                state.position_side = "long"  # DCA genelde long pozisyon
    
    def process_trade_fill(self, state: State, trade: Trade) -> Dict[str, float]:
        """
        Trade gerçekleştiğinde PnL hesaplamalarını güncelle
        
        YENİ MANTIK:
        - Pozisyon artırımında: Bakiye değişmez, ortalama maliyet güncellenir
        - Pozisyon azaltımında: Realized PnL bakiyeye eklenir, ortalama maliyet değişmez
        
        Returns:
            Dict with 'realized_pnl_change', 'cash_balance_change', 'new_avg_cost'
        """
        old_position_quantity = state.position_quantity
        old_position_avg_cost = state.position_avg_cost
        
        # Trade miktarını belirle (BUY = +, SELL = -)
        trade_quantity = trade.quantity if trade.side == OrderSide.BUY else -trade.quantity
        
        realized_pnl_change = 0.0
        cash_balance_change = 0.0  # YENİ MANTIK: Sadece realized PnL'de değişir
        
        # Pozisyon durumuna göre işlem yap
        if old_position_quantity == 0:
            # Yeni pozisyon açılıyor
            state.position_quantity = trade_quantity
            state.position_avg_cost = trade.price
            state.position_side = "long" if trade_quantity > 0 else "short"
            
            # YENİ MANTIK: Pozisyon açarken bakiye değişmez
            cash_balance_change = 0.0
            
        elif (old_position_quantity > 0 and trade_quantity > 0) or (old_position_quantity < 0 and trade_quantity < 0):
            # Pozisyon büyütülüyor (aynı yön) - POZISYON ARTIRIMI
            new_total_quantity = old_position_quantity + trade_quantity
            
            if old_position_avg_cost:
                # Ağırlıklı ortalama maliyet hesapla
                old_total_cost = abs(old_position_quantity) * old_position_avg_cost
                new_trade_cost = abs(trade_quantity) * trade.price
                new_total_cost = old_total_cost + new_trade_cost
                state.position_avg_cost = new_total_cost / abs(new_total_quantity)
            else:
                state.position_avg_cost = trade.price
            
            state.position_quantity = new_total_quantity
            
            # YENİ MANTIK: Pozisyon artırımında bakiye değişmez
            cash_balance_change = 0.0
            
        else:
            # Pozisyon kapatılıyor (ters yön) - POZISYON AZALTIMI - PnL gerçekleşiyor
            close_quantity = min(abs(trade_quantity), abs(old_position_quantity))
            
            if old_position_avg_cost:
                # Gerçekleşen kar/zarar hesapla
                if old_position_quantity > 0:  # Long pozisyon kapatılıyor
                    realized_pnl_change = (trade.price - old_position_avg_cost) * close_quantity
                else:  # Short pozisyon kapatılıyor
                    realized_pnl_change = (old_position_avg_cost - trade.price) * close_quantity
            
            # Pozisyon miktarını güncelle
            remaining_old_position = abs(old_position_quantity) - close_quantity
            remaining_new_position = abs(trade_quantity) - close_quantity
            
            if remaining_old_position > 0:
                # Kısmi kapatma - eski pozisyon devam ediyor
                state.position_quantity = remaining_old_position if old_position_quantity > 0 else -remaining_old_position
                # YENİ MANTIK: Ortalama maliyet DEĞİŞMEZ (aynı kalır)
            elif remaining_new_position > 0:
                # Pozisyon tersine döndü - bu durumda yeni pozisyon açılıyor
                state.position_quantity = remaining_new_position if trade_quantity > 0 else -remaining_new_position
                state.position_avg_cost = trade.price  # Yeni pozisyon için yeni ortalama maliyet
                state.position_side = "long" if state.position_quantity > 0 else "short"
            else:
                # Pozisyon tamamen kapandı
                state.position_quantity = 0.0
                state.position_avg_cost = None
                state.position_side = None
            
            # YENİ MANTIK: Realized PnL bakiyeye eklenir
            cash_balance_change = realized_pnl_change
        
        # State'i güncelle
        state.realized_pnl += realized_pnl_change
        state.cash_balance += cash_balance_change
        
        # Güvenli side değeri al
        side_value = trade.side.value if hasattr(trade.side, 'value') else str(trade.side)
        
        # Güvenli position_avg_cost değeri al
        avg_cost_value = state.position_avg_cost if state.position_avg_cost is not None else 0.0
        
        logger.info(f"PnL güncellendi - Strategy: {state.strategy_id}, "
                   f"Trade: {side_value} {trade.quantity:.6f} @ ${trade.price:.6f}, "
                   f"Realized PnL change: ${realized_pnl_change:.2f}, "
                   f"New balance: ${state.cash_balance:.2f}, "
                   f"New position: {state.position_quantity:.6f} @ ${avg_cost_value:.6f}")
        
        return {
            'realized_pnl_change': realized_pnl_change,
            'cash_balance_change': cash_balance_change,
            'new_avg_cost': state.position_avg_cost
        }
    
    def calculate_unrealized_pnl(self, state: State, current_price: float) -> Dict[str, float]:
        """
        Gerçekleşmemiş kar/zarar hesapla - OVERFLOW KORUMALI VERSİYON
        
        FORMÜL:
        - Long pozisyon: (şimdiki_fiyat - ortalama_maliyet) * pozisyon_miktarı
        - Short pozisyon: (ortalama_maliyet - şimdiki_fiyat) * pozisyon_miktarı
        
        Returns:
            Dict with 'unrealized_pnl', 'unrealized_pnl_pct', 'position_value', 'total_balance'
        """
        try:
            # Güvenlik kontrolleri - overflow önleme
            if state.position_quantity == 0 or not state.position_avg_cost:
                return {
                    'unrealized_pnl': 0.0,
                    'unrealized_pnl_pct': 0.0,
                    'position_value': 0.0,
                    'total_balance': state.cash_balance
                }
            
            # Değerleri güvenli aralıklarda kontrol et
            max_safe_value = 1e15  # 1 katrilyon - çok büyük değerler için limit
            min_safe_value = 1e-15  # Çok küçük değerler için limit
            
            # Pozisyon miktarı ve fiyat kontrolleri
            position_qty = float(state.position_quantity)
            avg_cost = float(state.position_avg_cost)
            current_price_float = float(current_price)
            
            # Overflow kontrolü
            if (abs(position_qty) > max_safe_value or 
                abs(avg_cost) > max_safe_value or 
                abs(current_price_float) > max_safe_value):
                logger.warning(f"Overflow riski: position_qty={position_qty}, avg_cost={avg_cost}, current_price={current_price_float}")
                return {
                    'unrealized_pnl': 0.0,
                    'unrealized_pnl_pct': 0.0,
                    'position_value': 0.0,
                    'total_balance': state.cash_balance
                }
            
            # Pozisyon değeri (her zaman pozitif) - overflow korumalı
            try:
                position_value = abs(position_qty) * current_price_float
                if position_value > max_safe_value:
                    position_value = max_safe_value
                    logger.warning(f"Position value overflow korundu: {position_value}")
            except (OverflowError, ValueError):
                position_value = 0.0
                logger.error("Position value hesaplama hatası")
            
            # Gerçekleşmemiş kar/zarar - overflow korumalı
            try:
                if position_qty > 0:  # Long pozisyon
                    unrealized_pnl = (current_price_float - avg_cost) * position_qty
                elif position_qty < 0:  # Short pozisyon (negatif quantity)
                    # Short için: (ortalama_maliyet - şimdiki_fiyat) * mutlak_pozisyon_miktarı
                    unrealized_pnl = (avg_cost - current_price_float) * abs(position_qty)
                else:
                    unrealized_pnl = 0.0
                
                # Overflow kontrolü
                if abs(unrealized_pnl) > max_safe_value:
                    unrealized_pnl = max_safe_value if unrealized_pnl > 0 else -max_safe_value
                    logger.warning(f"Unrealized PnL overflow korundu: {unrealized_pnl}")
                    
            except (OverflowError, ValueError):
                unrealized_pnl = 0.0
                logger.error("Unrealized PnL hesaplama hatası")
            
            # Yüzdelik hesaplama (yatırım tutarına göre) - overflow korumalı
            try:
                invested_amount = abs(position_qty) * avg_cost
                if invested_amount > min_safe_value:  # Sıfıra bölme önleme
                    unrealized_pnl_pct = (unrealized_pnl / invested_amount * 100)
                    # Yüzde değeri makul aralıkta tut
                    if abs(unrealized_pnl_pct) > 10000:  # %10000'den fazla mantıksız
                        unrealized_pnl_pct = 10000 if unrealized_pnl_pct > 0 else -10000
                        logger.warning(f"Unrealized PnL % overflow korundu: {unrealized_pnl_pct}")
                else:
                    unrealized_pnl_pct = 0.0
            except (OverflowError, ValueError, ZeroDivisionError):
                unrealized_pnl_pct = 0.0
                logger.error("Unrealized PnL % hesaplama hatası")
            
            # Toplam bakiye = Nakit bakiye + Gerçekleşmemiş kar/zarar - overflow korumalı
            try:
                total_balance = state.cash_balance + unrealized_pnl
                if abs(total_balance) > max_safe_value:
                    total_balance = max_safe_value if total_balance > 0 else -max_safe_value
                    logger.warning(f"Total balance overflow korundu: {total_balance}")
            except (OverflowError, ValueError):
                total_balance = state.cash_balance
                logger.error("Total balance hesaplama hatası")
            
            return {
                'unrealized_pnl': unrealized_pnl,
                'unrealized_pnl_pct': unrealized_pnl_pct,
                'position_value': position_value,
                'total_balance': total_balance
            }
            
        except Exception as e:
            logger.error(f"PnL hesaplama genel hatası: {e}")
            return {
                'unrealized_pnl': 0.0,
                'unrealized_pnl_pct': 0.0,
                'position_value': 0.0,
                'total_balance': state.cash_balance
            }
    
    def get_pnl_summary(self, state: State, current_price: float) -> Dict[str, any]:
        """
        Tam PnL özeti al
        
        Returns:
            Complete PnL summary with all metrics
        """
        unrealized_data = self.calculate_unrealized_pnl(state, current_price)
        
        # Toplam kar/zarar (gerçekleşen + gerçekleşmeyen)
        total_pnl = state.realized_pnl + unrealized_data['unrealized_pnl']
        
        # Toplam getiri yüzdesi (başlangıç sermayesine göre)
        total_return_pct = (total_pnl / state.initial_balance * 100) if state.initial_balance > 0 else 0.0
        
        return {
            # Temel bilgiler
            'initial_balance': state.initial_balance,
            'cash_balance': state.cash_balance,
            'realized_pnl': state.realized_pnl,
            
            # Pozisyon bilgileri
            'position_quantity': state.position_quantity,
            'position_avg_cost': state.position_avg_cost,
            'position_side': state.position_side,
            'position_value': unrealized_data['position_value'],
            
            # Gerçekleşmemiş kar/zarar
            'unrealized_pnl': unrealized_data['unrealized_pnl'],
            'unrealized_pnl_pct': unrealized_data['unrealized_pnl_pct'],
            
            # Toplam değerler
            'total_balance': unrealized_data['total_balance'],
            'total_pnl': total_pnl,
            'total_return_pct': total_return_pct,
            
            # Ekstra metrikler
            'current_price': current_price,
            'is_profitable': total_pnl > 0,
            'has_position': state.position_quantity != 0
        }


# Global instance
pnl_calculator = PnLCalculator()
