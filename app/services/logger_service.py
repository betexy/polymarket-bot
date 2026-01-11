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
            "total_profit": 0.0,  # Общий профит в USD
            "total_invested": 0.0,  # Общая сумма инвестиций
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
    
    def get_profit_data(self, days: int = 30) -> List[Dict[str, Any]]:
        """Получение данных профита по дням для графика"""
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        with self._lock:
            # Группируем ставки по дням
            profit_by_day: Dict[str, float] = defaultdict(float)
            invested_by_day: Dict[str, float] = defaultdict(float)
            
            today = datetime.now().date()
            cutoff_date = today - timedelta(days=days)
            
            for bet_entry in self.bets:
                try:
                    bet_date = datetime.fromisoformat(bet_entry["timestamp"].replace("Z", "+00:00")).date()
                    if bet_date < cutoff_date:
                        continue
                    
                    date_key = bet_date.isoformat()
                    result = bet_entry.get("result", {})
                    
                    # Если ордер успешно размещен, учитываем размер ставки
                    if result.get("status") == "success":
                        order_size = result.get("order_size", 0)
                        if order_size:
                            invested_by_day[date_key] += order_size
                    
                    # Если есть информация о профите
                    profit = result.get("profit")
                    if profit is not None:
                        profit_by_day[date_key] += profit
                        
                except Exception as e:
                    logger.error(f"Error processing bet entry for profit data: {e}")
                    continue
            
            # Создаем список данных для всех дней в диапазоне
            profit_data = []
            for i in range(days, -1, -1):
                date = (today - timedelta(days=i)).isoformat()
                profit_data.append({
                    "date": date,
                    "profit": profit_by_day.get(date, 0.0),
                    "invested": invested_by_day.get(date, 0.0)
                })
            
            return profit_data


# Глобальный экземпляр
log_storage = LogStorage(max_size=1000)
