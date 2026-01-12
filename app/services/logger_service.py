import logging
from datetime import datetime
from typing import List, Dict, Any
from collections import deque
from threading import Lock
import sqlite3
import json
import os

logger = logging.getLogger(__name__)


class LogStorage:
    """Хранение логов и данных для веб-интерфейса"""
    
    def __init__(self, max_size: int = 1000, db_path: str = "polymarket_bets.db"):
        self.max_size = max_size
        self._lock = Lock()
        self.db_path = db_path
        
        # Хранилище ставок (в памяти для быстрого доступа)
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
        
        # Инициализируем базу данных
        self._init_database()
    
    def _init_database(self):
        """Инициализация базы данных SQLite для ставок"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    order_id TEXT,
                    market_id TEXT,
                    token_id TEXT,
                    home_team TEXT,
                    away_team TEXT,
                    market_type TEXT,
                    target TEXT,
                    second_bookmaker TEXT,
                    order_price REAL,
                    order_size REAL,
                    coef TEXT,
                    surebet_profit REAL,
                    profit REAL,
                    result_status TEXT,
                    bet_data_json TEXT,
                    result_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Индексы для быстрого поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON bets(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON bets(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_id ON bets(order_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_id ON bets(market_id)")
            
            conn.commit()
            conn.close()
            logger.info(f"Bets database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Error initializing bets database: {e}", exc_info=True)
    
    def add_bet(self, bet_data: Dict[str, Any], result: Dict[str, Any]):
        """Добавление информации о ставке"""
        with self._lock:
            timestamp = datetime.now().isoformat()
            entry = {
                "timestamp": timestamp,
                "bet_data": bet_data,
                "result": result,
            }
            self.bets.appendleft(entry)  # Новые сначала
            self.stats["total_bets"] += 1
            self.stats["last_update"] = timestamp
            
            status = result.get("status")
            if status == "success":
                self.stats["successful_orders"] += 1
                # Сохраняем успешные ставки в базу данных
                self._save_bet_to_db(timestamp, bet_data, result)
            elif status == "error":
                self.stats["failed_orders"] += 1
            elif status == "skipped":
                self.stats["skipped_orders"] += 1
    
    def _save_bet_to_db(self, timestamp: str, bet_data: Dict[str, Any], result: Dict[str, Any]):
        """Сохранение ставки в базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO bets (
                    timestamp, status, order_id, market_id, token_id,
                    home_team, away_team, market_type, target, second_bookmaker,
                    order_price, order_size, coef, surebet_profit, profit, result_status,
                    bet_data_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                result.get("status"),
                result.get("order_id"),
                result.get("market_id"),
                result.get("token_id"),
                bet_data.get("homeTeam"),
                bet_data.get("awayTeam"),
                bet_data.get("market"),
                bet_data.get("target"),
                bet_data.get("second_bookmaker"),
                result.get("order_price"),
                result.get("order_size"),
                bet_data.get("coef"),
                bet_data.get("surebet_profit"),
                result.get("profit"),
                result.get("result_status"),
                json.dumps(bet_data),
                json.dumps(result)
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving bet to database: {e}", exc_info=True)
    
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
