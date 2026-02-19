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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    settled_status TEXT,
                    outcome TEXT,
                    bet_amount_usd REAL,
                    settled_at TEXT
                )
            """)
            
            # Добавляем новые колонки если их нет (для существующих БД)
            try:
                cursor.execute("ALTER TABLE bets ADD COLUMN settled_status TEXT")
            except sqlite3.OperationalError:
                pass  # Колонка уже существует
            
            try:
                cursor.execute("ALTER TABLE bets ADD COLUMN outcome TEXT")
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE bets ADD COLUMN bet_amount_usd REAL")
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE bets ADD COLUMN settled_at TEXT")
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute("ALTER TABLE bets ADD COLUMN redeemed INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute("ALTER TABLE bets ADD COLUMN redeemed_at TEXT")
            except sqlite3.OperationalError:
                pass

            # Индексы для быстрого поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON bets(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON bets(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_id ON bets(order_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_id ON bets(market_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status_market ON bets(status, market_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_id ON bets(token_id)")
            
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
                self._save_bet_to_db(timestamp, bet_data, result)
            elif status == "error":
                self.stats["failed_orders"] += 1
                self._save_bet_to_db(timestamp, bet_data, result)
            elif status == "skipped":
                self.stats["skipped_orders"] += 1
                # Save interesting skips (exclude trivial filter reasons)
                skip_reason = result.get("reason", "")
                trivial_skips = {"second_bookmaker_not_allowed", "not_polymarket"}
                if skip_reason not in trivial_skips:
                    self._save_bet_to_db(timestamp, bet_data, result)
    
    def _save_bet_to_db(self, timestamp: str, bet_data: Dict[str, Any], result: Dict[str, Any]):
        """Сохранение ставки в базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Вычисляем сумму ставки
            order_price = result.get("order_price")
            order_size = result.get("order_size")
            bet_amount_usd = None
            if order_price and order_size:
                bet_amount_usd = float(order_price) * float(order_size)
            
            cursor.execute("""
                INSERT INTO bets (
                    timestamp, status, order_id, market_id, token_id,
                    home_team, away_team, market_type, target, second_bookmaker,
                    order_price, order_size, coef, surebet_profit, profit, result_status,
                    bet_data_json, result_json, bet_amount_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(result),
                bet_amount_usd
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving bet to database: {e}", exc_info=True)
    
    def _update_order_info_in_db(self, order_id: str, order_price: float, order_size: float) -> bool:
        """Обновление информации об ордере (цена и размер) в БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE bets
                SET order_price = ?, order_size = ?, bet_amount_usd = ?
                WHERE order_id = ?
            """, (order_price, order_size, order_price * order_size, order_id))
            
            conn.commit()
            updated = cursor.rowcount > 0
            conn.close()
            
            if updated:
                logger.info(f"Updated order info in DB: order_id={order_id}, price={order_price}, size={order_size}")
            else:
                logger.warning(f"Order not found for update: order_id={order_id}")
            
            return updated
        except Exception as e:
            logger.error(f"Error updating order info in DB: {e}", exc_info=True)
            return False
    
    def _delete_bet_from_db(self, order_id: str) -> bool:
        """Удаление ставки из базы данных по order_id"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM bets WHERE order_id = ?", (order_id,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"Bet deleted from database: order_id={order_id}")
                return True
            else:
                logger.warning(f"Bet not found in database for deletion: order_id={order_id}")
                return False
        except Exception as e:
            logger.error(f"Error deleting bet from database: {e}", exc_info=True)
            return False
    
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
    
    def get_recent_bets(self, limit: int = 100, status_filter: str = None) -> List[Dict[str, Any]]:
        """Получение последних ставок из базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if status_filter:
                cursor.execute("""
                    SELECT timestamp, bet_data_json, result_json, market_type, target,
                           order_price, order_size, bet_amount_usd,
                           settled_status, outcome, profit
                    FROM bets
                    WHERE status = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (status_filter, limit))
            else:
                cursor.execute("""
                    SELECT timestamp, bet_data_json, result_json, market_type, target,
                           order_price, order_size, bet_amount_usd,
                           settled_status, outcome, profit
                    FROM bets
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            bets = []
            for row in rows:
                try:
                    bet_data = json.loads(row["bet_data_json"]) if row["bet_data_json"] else {}
                    result = json.loads(row["result_json"]) if row["result_json"] else {}
                    
                    # Формируем строку маркета для отображения
                    target = row["target"] if "target" in list(row.keys()) else bet_data.get("target", "")
                    pivot = bet_data.get("pivot", None)
                    market_display = target
                    if pivot:
                        market_display = f"{target} {pivot}"
                    
                    # Добавляем информацию о сумме ставки и результате
                    # sqlite3.Row поддерживает доступ через ключи
                    row_keys = list(row.keys())
                    bet_amount_usd = row["bet_amount_usd"] if "bet_amount_usd" in row_keys else None
                    if bet_amount_usd is None and row["order_price"] and row["order_size"]:
                        # Вычисляем сумму ставки если не сохранена
                        bet_amount_usd = float(row["order_price"]) * float(row["order_size"])
                    
                    # Рассчитываем ROI (Return on Investment)
                    roi = None
                    profit = row["profit"] if "profit" in row_keys else None
                    if profit is not None and bet_amount_usd and bet_amount_usd > 0:
                        # ROI = (Profit / Investment) * 100%
                        roi = (float(profit) / float(bet_amount_usd)) * 100
                    
                    bets.append({
                        "timestamp": row["timestamp"],
                        "bet_data": bet_data,
                        "result": result,
                        "market_display": market_display,
                        "bet_amount_usd": bet_amount_usd,
                        "settled_status": row["settled_status"] if "settled_status" in row_keys else None,
                        "outcome": row["outcome"] if "outcome" in row_keys else None,
                        "profit": profit,
                        "roi": roi,  # ROI в процентах
                        "source": bet_data.get("source")  # Источник парсера
                    })
                except Exception as e:
                    logger.error(f"Error parsing bet from database: {e}")
                    continue
            
            return bets
        except Exception as e:
            logger.error(f"Error getting bets from database: {e}", exc_info=True)
            # Fallback к памяти, если БД недоступна
            with self._lock:
                return list(self.bets)[:limit]
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение последних логов"""
        with self._lock:
            return list(self.api_logs)[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики из базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Подсчитываем статистику из БД
            cursor.execute("SELECT COUNT(*) FROM bets")
            total_bets = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM bets WHERE status = 'success'")
            successful_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM bets WHERE status = 'error'")
            failed_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM bets WHERE status = 'skipped'")
            skipped_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COALESCE(SUM(profit), 0) FROM bets WHERE profit IS NOT NULL")
            total_profit = cursor.fetchone()[0] or 0.0
            
            # Общий оборот = сумма всех успешных ставок в долларах
            cursor.execute("""
                SELECT COALESCE(SUM(bet_amount_usd), 0) 
                FROM bets 
                WHERE status = 'success' AND bet_amount_usd IS NOT NULL
            """)
            total_turnover = cursor.fetchone()[0] or 0.0
            
            # Если bet_amount_usd нет, используем order_size * order_price как fallback
            if total_turnover == 0:
                cursor.execute("""
                    SELECT COALESCE(SUM(order_size * order_price), 0) 
                    FROM bets 
                    WHERE status = 'success' AND order_size IS NOT NULL AND order_price IS NOT NULL
                """)
                total_turnover = cursor.fetchone()[0] or 0.0
            
            # Для совместимости сохраняем total_invested
            total_invested = total_turnover
            
            # Рассчитываем общий ROI (Return on Investment)
            # ROI = (Total Profit / Total Turnover) * 100%
            total_roi = None
            if total_turnover > 0:
                total_roi = (total_profit / total_turnover) * 100
            
            cursor.execute("SELECT MAX(timestamp) FROM bets")
            last_update = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "total_bets": total_bets,
                "successful_orders": successful_orders,
                "failed_orders": failed_orders,
                "skipped_orders": skipped_orders,
                "total_profit": float(total_profit),
                "total_invested": float(total_invested),
                "total_turnover": float(total_turnover),  # Общий оборот в долларах
                "total_roi": float(total_roi) if total_roi is not None else None,  # Общий ROI в процентах
                "last_update": last_update
            }
        except Exception as e:
            logger.error(f"Error getting stats from database: {e}", exc_info=True)
            # Fallback к памяти, если БД недоступна
            with self._lock:
                return self.stats.copy()
    
    def get_profit_data(self, days: int = 30) -> List[Dict[str, Any]]:
        """Получение данных профита по дням для графика из базы данных"""
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            today = datetime.now().date()
            cutoff_date = (today - timedelta(days=days)).isoformat()
            
            # Получаем ставки из БД за указанный период
            cursor.execute("""
                SELECT timestamp, order_size, order_price, profit, status
                FROM bets
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            """, (cutoff_date,))
            
            rows = cursor.fetchall()
            conn.close()
            
            profit_by_day: Dict[str, float] = defaultdict(float)
            invested_by_day: Dict[str, float] = defaultdict(float)
            
            for row in rows:
                try:
                    bet_date = datetime.fromisoformat(row[0].replace("Z", "+00:00")).date()
                    date_key = bet_date.isoformat()
                    
                    # Если ордер успешно размещен, учитываем размер ставки
                    if row[4] == "success" and row[1] and row[2]:
                        invested_by_day[date_key] += row[1] * row[2]
                    
                    # Если есть информация о профите
                    if row[3] is not None:
                        profit_by_day[date_key] += row[3]
                        
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
        except Exception as e:
            logger.error(f"Error getting profit data from database: {e}", exc_info=True)
            # Fallback к памяти, если БД недоступна
            with self._lock:
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
                        
                        if result.get("status") == "success":
                            order_size = result.get("order_size", 0)
                            if order_size:
                                invested_by_day[date_key] += order_size
                        
                        profit = result.get("profit")
                        if profit is not None:
                            profit_by_day[date_key] += profit
                    except Exception as e:
                        continue
                
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
