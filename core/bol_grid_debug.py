"""
BOL-Grid Debug Sistemi
BOL-Grid stratejisi için özel debug ve monitoring sistemi
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from .utils import logger


class BollingerGridDebugger:
    """
    BOL-Grid stratejisi için özel debug sistemi
    Detaylı loglar, analiz ve monitoring
    """
    
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self.debug_file = f"logs/bol_grid_debug_{strategy_id}.log"
        self.analysis_file = f"logs/bol_grid_analysis_{strategy_id}.json"
        
        # Debug dosyasını oluştur
        self._ensure_debug_file()
    
    def _ensure_debug_file(self):
        """Debug dosyasını oluştur"""
        os.makedirs("logs", exist_ok=True)
        
        if not os.path.exists(self.debug_file):
            with open(self.debug_file, 'w', encoding='utf-8') as f:
                f.write(f"=== BOL-Grid Debug Log - {self.strategy_id} ===\n")
                f.write(f"Başlangıç: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
    
    def log_signal_analysis(self, 
                           current_price: float,
                           bands: Dict[str, float],
                           cross_signal: str,
                           positions: List[Dict],
                           average_cost: float,
                           decision: Dict[str, Any]):
        """Sinyal analizini detaylı logla"""
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Bollinger Bands analizi
        price_vs_upper = ((current_price - bands['upper']) / bands['upper']) * 100
        price_vs_middle = ((current_price - bands['middle']) / bands['middle']) * 100
        price_vs_lower = ((current_price - bands['lower']) / bands['lower']) * 100
        band_width = ((bands['upper'] - bands['lower']) / bands['middle']) * 100
        
        # Pozisyon analizi
        total_quantity = sum(pos.get('quantity', 0) for pos in positions)
        total_value = total_quantity * current_price
        profit_loss = (current_price - average_cost) * total_quantity if average_cost > 0 else 0
        profit_pct = ((current_price - average_cost) / average_cost) * 100 if average_cost > 0 else 0
        
        log_entry = {
            "timestamp": timestamp,
            "price_analysis": {
                "current_price": current_price,
                "price_vs_upper_pct": price_vs_upper,
                "price_vs_middle_pct": price_vs_middle,
                "price_vs_lower_pct": price_vs_lower,
                "band_width_pct": band_width
            },
            "bollinger_bands": bands,
            "cross_signal": cross_signal,
            "position_analysis": {
                "positions_count": len(positions),
                "total_quantity": total_quantity,
                "total_value": total_value,
                "average_cost": average_cost,
                "profit_loss": profit_loss,
                "profit_pct": profit_pct
            },
            "decision": decision
        }
        
        # JSON dosyasına yaz
        self._append_analysis(log_entry)
        
        # Debug dosyasına yaz
        self._write_debug_entry(log_entry)
    
    def log_trade_execution(self, 
                           trade_side: str,
                           quantity: float,
                           price: float,
                           cycle_info: str,
                           before_state: Dict[str, Any],
                           after_state: Dict[str, Any]):
        """Trade execution'ını detaylı logla"""
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        log_entry = {
            "timestamp": timestamp,
            "type": "trade_execution",
            "trade": {
                "side": trade_side,
                "quantity": quantity,
                "price": price,
                "cycle_info": cycle_info
            },
            "state_change": {
                "before": before_state,
                "after": after_state
            }
        }
        
        self._append_analysis(log_entry)
        self._write_debug_entry(log_entry)
    
    def log_cycle_transition(self, 
                           from_cycle: str,
                           to_cycle: str,
                           reason: str,
                           cycle_data: Dict[str, Any]):
        """Döngü geçişini logla"""
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        log_entry = {
            "timestamp": timestamp,
            "type": "cycle_transition",
            "transition": {
                "from": from_cycle,
                "to": to_cycle,
                "reason": reason
            },
            "cycle_data": cycle_data
        }
        
        self._append_analysis(log_entry)
        self._write_debug_entry(log_entry)
    
    def _append_analysis(self, log_entry: Dict[str, Any]):
        """Analiz dosyasına ekle"""
        try:
            # Mevcut analizi oku
            if os.path.exists(self.analysis_file):
                with open(self.analysis_file, 'r', encoding='utf-8') as f:
                    analysis_data = json.load(f)
            else:
                analysis_data = {
                    "strategy_id": self.strategy_id,
                    "start_time": datetime.now().isoformat(),
                    "entries": []
                }
            
            # Yeni entry ekle
            analysis_data["entries"].append(log_entry)
            analysis_data["last_update"] = datetime.now().isoformat()
            
            # Son 1000 entry'yi tut
            if len(analysis_data["entries"]) > 1000:
                analysis_data["entries"] = analysis_data["entries"][-1000:]
            
            # Dosyaya yaz
            with open(self.analysis_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"BOL-Grid analiz dosyası yazma hatası: {e}")
    
    def _write_debug_entry(self, log_entry: Dict[str, Any]):
        """Debug dosyasına yaz"""
        try:
            with open(self.debug_file, 'a', encoding='utf-8') as f:
                f.write(f"\n[{log_entry['timestamp']}] {log_entry.get('type', 'analysis')}\n")
                
                if log_entry.get('type') == 'trade_execution':
                    trade = log_entry['trade']
                    f.write(f"  🔄 TRADE: {trade['side']} {trade['quantity']} @ {trade['price']} ({trade['cycle_info']})\n")
                    
                    before = log_entry['state_change']['before']
                    after = log_entry['state_change']['after']
                    f.write(f"  📊 BEFORE: Cycle={before.get('cycle_step', 'D0')}, Qty={before.get('total_quantity', 0):.6f}, Avg={before.get('average_cost', 0):.6f}\n")
                    f.write(f"  📊 AFTER:  Cycle={after.get('cycle_step', 'D0')}, Qty={after.get('total_quantity', 0):.6f}, Avg={after.get('average_cost', 0):.6f}\n")
                
                elif log_entry.get('type') == 'cycle_transition':
                    transition = log_entry['transition']
                    f.write(f"  🔄 CYCLE: {transition['from']} → {transition['to']} ({transition['reason']})\n")
                
                else:
                    # Sinyal analizi
                    price_analysis = log_entry.get('price_analysis', {})
                    position_analysis = log_entry.get('position_analysis', {})
                    decision = log_entry.get('decision', {})
                    
                    f.write(f"  💰 PRICE: {price_analysis.get('current_price', 0):.6f} (vs bands: U:{price_analysis.get('price_vs_upper_pct', 0):+.2f}%, M:{price_analysis.get('price_vs_middle_pct', 0):+.2f}%, L:{price_analysis.get('price_vs_lower_pct', 0):+.2f}%)\n")
                    f.write(f"  📊 POSITION: Qty={position_analysis.get('total_quantity', 0):.6f}, Avg={position_analysis.get('average_cost', 0):.6f}, P&L={position_analysis.get('profit_pct', 0):+.2f}%\n")
                    f.write(f"  🎯 SIGNAL: {log_entry.get('cross_signal', 'none')}\n")
                    f.write(f"  ⚡ DECISION: {decision.get('action', 'none')} - {decision.get('reason', 'no reason')}\n")
                
                f.write("-" * 50 + "\n")
                
        except Exception as e:
            logger.error(f"BOL-Grid debug dosyası yazma hatası: {e}")
    
    def get_recent_analysis(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Son analizleri getir"""
        try:
            if not os.path.exists(self.analysis_file):
                return []
            
            with open(self.analysis_file, 'r', encoding='utf-8') as f:
                analysis_data = json.load(f)
            
            entries = analysis_data.get('entries', [])
            return entries[-limit:] if entries else []
            
        except Exception as e:
            logger.error(f"BOL-Grid analiz okuma hatası: {e}")
            return []
    
    def get_cycle_summary(self) -> Dict[str, Any]:
        """Döngü özetini getir"""
        try:
            recent_entries = self.get_recent_analysis(100)
            
            if not recent_entries:
                return {"status": "no_data"}
            
            # Son trade execution'ı bul
            last_trade = None
            for entry in reversed(recent_entries):
                if entry.get('type') == 'trade_execution':
                    last_trade = entry
                    break
            
            # Son sinyal analizi
            last_analysis = recent_entries[-1] if recent_entries else None
            
            return {
                "status": "active",
                "last_trade": last_trade,
                "last_analysis": last_analysis,
                "total_entries": len(recent_entries)
            }
            
        except Exception as e:
            logger.error(f"BOL-Grid döngü özeti hatası: {e}")
            return {"status": "error", "error": str(e)}


# Global debugger instance'ları
_bol_grid_debuggers: Dict[str, BollingerGridDebugger] = {}


def get_bol_grid_debugger(strategy_id: str) -> BollingerGridDebugger:
    """BOL-Grid debugger instance'ı al"""
    if strategy_id not in _bol_grid_debuggers:
        _bol_grid_debuggers[strategy_id] = BollingerGridDebugger(strategy_id)
    return _bol_grid_debuggers[strategy_id]
