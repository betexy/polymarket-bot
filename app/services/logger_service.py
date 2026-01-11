import logging
from datetime import datetime
from typing import List, Dict, Any
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class LogStorage:
    """Хранение логов и данных для веб-интерфейса"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._lock = Lock()
        
        # Хранилище ставок
        self.bets: deque = deque(maxlen=max_size)
        
        # Хранилище логов API
        self.api_logs: deque = deque(maxlen=max_size)
        
        # Статистика
        self.stats = {
            "total_bets": 0,
            "successful_orders": 0,
            "failed_orders": 0,
            "skipped_orders": 0,
            "last_update": None
        }
    
    def add_bet(self, bet_data: Dict[str, Any], result: Dict[str, Any]):
        """Добавление информации о ставке"""
        with self._lock:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "bet_data": bet_data,
                "result": result,
            }
            self.bets.appendleft(entry)  # Новые сначала
            self.stats["total_bets"] += 1
            self.stats["last_update"] = datetime.now().isoformat()
            
            if result.get("status") == "success":
                self.stats["successful_orders"] += 1
            elif result.get("status") == "error":
                self.stats["failed_orders"] += 1
            elif result.get("status") == "skipped":
                self.stats["skipped_orders"] += 1
    
    def add_api_log(self, message: str, level: str = "INFO", data: Dict[str, Any] = None):
        """Добавление лога API"""
        with self._lock:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "message": message,
                "level": level,
                "data": data or {}
            }
            self.api_logs.appendleft(entry)  # Новые сначала
    
    def get_recent_bets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение последних ставок"""
        with self._lock:
            return list(self.bets)[:limit]
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение последних логов"""
        with self._lock:
            return list(self.api_logs)[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        with self._lock:
            return self.stats.copy()


# Глобальный экземпляр
log_storage = LogStorage(max_size=1000)
