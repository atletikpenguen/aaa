# Backtest Debug Sistemi - Hata Tespiti (23 Eylül 2025)
# Bu dosyada backtest sırasında oluşan hataları detaylı olarak loglayabiliriz
# Özellikle 'str' object has no attribute 'value' hatasını tespit etmek için

import traceback
import sys
from typing import Any, Dict, List
from .utils import logger

class BacktestDebugger:
    """Backtest debug sistemi"""
    
    def __init__(self):
        self.debug_logs = []
        self.error_count = 0
    
    def log_debug(self, message: str, data: Any = None):
        """Debug mesajı logla"""
        debug_msg = f"[BACKTEST DEBUG] {message}"
        if data is not None:
            debug_msg += f" | Data: {data}"
        
        logger.info(debug_msg)
        self.debug_logs.append(debug_msg)
    
    def log_error(self, error: Exception, context: str = ""):
        """Hata logla"""
        self.error_count += 1
        error_msg = f"[BACKTEST ERROR] {context}: {str(error)}"
        logger.error(error_msg)
        
        # Stack trace'i al
        stack_trace = traceback.format_exc()
        logger.error(f"[BACKTEST ERROR] Stack trace:\n{stack_trace}")
        
        self.debug_logs.append(error_msg)
        self.debug_logs.append(f"Stack trace: {stack_trace}")
    
    def safe_get_value(self, obj, attr_name: str, default=None):
        """Güvenli .value erişimi"""
        try:
            if hasattr(obj, attr_name):
                attr = getattr(obj, attr_name)
                if hasattr(attr, 'value'):
                    return attr.value
                else:
                    return str(attr)
            else:
                return default
        except Exception as e:
            self.log_error(e, f"safe_get_value error for {attr_name}")
            return default
    
    def safe_enum_access(self, obj, default=None):
        """Güvenli enum erişimi"""
        try:
            if hasattr(obj, 'value'):
                return obj.value
            else:
                return str(obj)
        except Exception as e:
            self.log_error(e, f"safe_enum_access error")
            return default
    
    def debug_object_type(self, obj, obj_name: str):
        """Obje tipini debug et"""
        try:
            obj_type = type(obj).__name__
            obj_str = str(obj)
            has_value = hasattr(obj, 'value')
            
            self.log_debug(f"Object {obj_name}: type={obj_type}, str={obj_str}, has_value={has_value}")
            
            if has_value:
                try:
                    value = obj.value
                    self.log_debug(f"Object {obj_name}.value: {value} (type: {type(value).__name__})")
                except Exception as e:
                    self.log_error(e, f"Error accessing {obj_name}.value")
            
        except Exception as e:
            self.log_error(e, f"Error debugging object {obj_name}")
    
    def get_debug_summary(self) -> Dict[str, Any]:
        """Debug özeti al"""
        return {
            "error_count": self.error_count,
            "debug_logs": self.debug_logs,
            "total_logs": len(self.debug_logs)
        }

# Global debug instance
backtest_debugger = BacktestDebugger()
