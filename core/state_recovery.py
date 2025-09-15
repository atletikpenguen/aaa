"""
State Recovery System
Trade history'den state'leri yeniden inşa eden güvenlik sistemi
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from .models import Strategy, State, Trade, DCAPosition, StrategyType, OrderSide
from .storage import storage
from .utils import logger


class StateRecoveryManager:
    """
    State corruption durumlarında trade history'den state'leri yeniden inşa eden sistem
    """
    
    def __init__(self):
        self.recovery_log = []
    
    async def validate_and_recover_strategy_state(self, strategy: Strategy) -> Dict[str, any]:
        """
        Strateji state'ini validate et ve gerekirse recover et
        """
        strategy_id = strategy.id
        recovery_report = {
            'strategy_id': strategy_id,
            'strategy_name': strategy.name,
            'strategy_type': strategy.strategy_type.value,
            'validation_status': 'unknown',
            'recovery_needed': False,
            'recovery_performed': False,
            'issues_found': [],
            'recovery_details': {}
        }
        
        try:
            # Mevcut state'i yükle
            current_state = await storage.load_state(strategy_id)
            if not current_state:
                recovery_report['validation_status'] = 'state_not_found'
                return recovery_report
            
            # Trade history'yi yükle
            trades = await storage.load_trades(strategy_id, limit=50)
            if not trades:
                recovery_report['validation_status'] = 'no_trades'
                return recovery_report
            
            # Strateji tipine göre validation
            if strategy.strategy_type == StrategyType.DCA_OTT:
                return await self._validate_and_recover_dca_state(strategy, current_state, trades, recovery_report)
            elif strategy.strategy_type == StrategyType.GRID_OTT:
                return await self._validate_grid_state(strategy, current_state, trades, recovery_report)
            else:
                recovery_report['validation_status'] = 'unsupported_strategy_type'
                return recovery_report
                
        except Exception as e:
            recovery_report['validation_status'] = 'error'
            recovery_report['error'] = str(e)
            logger.error(f"State validation hatası {strategy_id}: {e}")
            return recovery_report
    
    async def _validate_and_recover_dca_state(
        self, 
        strategy: Strategy, 
        current_state: State, 
        trades: List[Trade],
        recovery_report: Dict
    ) -> Dict:
        """DCA state'ini validate et ve recover et"""
        
        try:
            # Trade'leri zaman sırasına göre sırala
            sorted_trades = sorted(trades, key=lambda x: x.timestamp)
            
            # Trade history'den beklenen pozisyonları hesapla
            expected_positions = []
            buy_trades = []
            sell_trades = []
            
            for trade in sorted_trades:
                if trade.side == OrderSide.BUY:
                    buy_trades.append(trade)
                    expected_positions.append({
                        'buy_price': trade.price,
                        'quantity': trade.quantity,
                        'timestamp': trade.timestamp,
                        'order_id': trade.order_id
                    })
                elif trade.side == OrderSide.SELL:
                    sell_trades.append(trade)
                    # Satış trade'lerinde hangi pozisyonların satıldığını belirlemek karmaşık
                    # Şimdilik basit mantık: LIFO (Last In First Out)
                    remaining_qty = trade.quantity
                    positions_to_remove = []
                    
                    # Sondan başlayarak pozisyonları sat
                    for j in range(len(expected_positions) - 1, -1, -1):
                        if remaining_qty <= 0:
                            break
                        
                        pos = expected_positions[j]
                        if pos['quantity'] <= remaining_qty:
                            # Tüm pozisyonu sat
                            remaining_qty -= pos['quantity']
                            positions_to_remove.append(j)
                        else:
                            # Kısmi satış
                            pos['quantity'] -= remaining_qty
                            remaining_qty = 0
                    
                    # Satılan pozisyonları kaldır
                    for idx in positions_to_remove:
                        expected_positions.pop(idx)
            
            # Mevcut state ile karşılaştır
            current_positions = current_state.dca_positions
            
            # Pozisyon sayısı kontrolü
            if len(current_positions) != len(expected_positions):
                recovery_report['issues_found'].append({
                    'type': 'position_count_mismatch',
                    'current_count': len(current_positions),
                    'expected_count': len(expected_positions)
                })
                recovery_report['recovery_needed'] = True
            
            # Pozisyon detayları kontrolü
            current_order_ids = {pos.order_id for pos in current_positions}
            expected_order_ids = {pos['order_id'] for pos in expected_positions}
            
            missing_positions = expected_order_ids - current_order_ids
            extra_positions = current_order_ids - expected_order_ids
            
            if missing_positions or extra_positions:
                recovery_report['issues_found'].append({
                    'type': 'position_order_id_mismatch',
                    'missing_in_state': list(missing_positions),
                    'extra_in_state': list(extra_positions)
                })
                recovery_report['recovery_needed'] = True
            
            # Recovery gerekiyorsa yap
            if recovery_report['recovery_needed']:
                logger.warning(f"🔧 State recovery gerekli: {strategy.id}")
                
                # Yeni pozisyonları oluştur
                new_dca_positions = []
                for pos_data in expected_positions:
                    new_pos = DCAPosition(
                        buy_price=pos_data['buy_price'],
                        quantity=pos_data['quantity'],
                        timestamp=pos_data['timestamp'],
                        order_id=pos_data['order_id']
                    )
                    new_dca_positions.append(new_pos)
                
                # State'i güncelle
                current_state.dca_positions = new_dca_positions
                
                # Ortalama maliyet ve toplam miktar hesapla
                if new_dca_positions:
                    total_quantity = sum(pos.quantity for pos in new_dca_positions)
                    total_cost = sum(pos.buy_price * pos.quantity for pos in new_dca_positions)
                    current_state.avg_cost = total_cost / total_quantity if total_quantity > 0 else 0
                    current_state.total_quantity = total_quantity
                else:
                    current_state.avg_cost = None
                    current_state.total_quantity = 0.0
                
                # State'i kaydet
                await storage.save_state(current_state)
                
                recovery_report['recovery_performed'] = True
                recovery_report['recovery_details'] = {
                    'old_positions_count': len(current_positions),
                    'new_positions_count': len(new_dca_positions),
                    'old_avg_cost': current_state.avg_cost,
                    'new_avg_cost': current_state.avg_cost,
                    'recovered_positions': [
                        f"{pos.quantity}@{pos.buy_price}" for pos in new_dca_positions
                    ]
                }
                
                logger.info(f"✅ State recovery tamamlandı: {strategy.id} - {len(new_dca_positions)} pozisyon recover edildi")
            
            recovery_report['validation_status'] = 'completed'
            return recovery_report
            
        except Exception as e:
            recovery_report['validation_status'] = 'error'
            recovery_report['error'] = str(e)
            logger.error(f"DCA state recovery hatası {strategy.id}: {e}")
            return recovery_report
    
    async def _validate_grid_state(
        self, 
        strategy: Strategy, 
        current_state: State, 
        trades: List[Trade],
        recovery_report: Dict
    ) -> Dict:
        """Grid state'ini validate et"""
        
        # Grid stratejileri için şimdilik basit validation
        recovery_report['validation_status'] = 'grid_validation_not_implemented'
        
        # Basit kontroller
        if current_state.gf is None or current_state.gf <= 0:
            recovery_report['issues_found'].append({
                'type': 'invalid_gf',
                'gf_value': current_state.gf
            })
        
        return recovery_report
    
    async def recover_all_strategies(self) -> Dict[str, any]:
        """
        Tüm stratejileri validate et ve gerekirse recover et
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            strategies = await storage.load_strategies()
            
            recovery_summary = {
                'start_time': start_time.isoformat(),
                'total_strategies': len(strategies),
                'strategies_checked': 0,
                'recoveries_needed': 0,
                'recoveries_performed': 0,
                'results': {}
            }
            
            for strategy in strategies:
                recovery_report = await self.validate_and_recover_strategy_state(strategy)
                recovery_summary['results'][strategy.id] = recovery_report
                recovery_summary['strategies_checked'] += 1
                
                if recovery_report.get('recovery_needed'):
                    recovery_summary['recoveries_needed'] += 1
                
                if recovery_report.get('recovery_performed'):
                    recovery_summary['recoveries_performed'] += 1
            
            end_time = datetime.now(timezone.utc)
            recovery_summary['duration_seconds'] = (end_time - start_time).total_seconds()
            
            logger.info(f"🔧 State recovery tamamlandı: {recovery_summary['strategies_checked']} strateji, {recovery_summary['recoveries_performed']} recovery")
            
            return recovery_summary
            
        except Exception as e:
            logger.error(f"Toplu state recovery hatası: {e}")
            return {
                'error': str(e),
                'start_time': start_time.isoformat()
            }


# Global state recovery manager
state_recovery_manager = StateRecoveryManager()
