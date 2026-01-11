"""
Парсер событий Polymarket

Парсит события и сохраняет их в локальную базу данных для быстрого поиска.
Сохраняет только события, которые начнутся максимум через 48 часов.
"""
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import json
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class EventParser:
    """Парсер событий Polymarket с сохранением в SQLite"""
    
    def __init__(self, db_path: str = "polymarket_events.db"):
        self.db_path = db_path
        self.base_url = "https://gamma-api.polymarket.com"
        self._init_database()
    
    def _init_database(self):
        """Инициализация базы данных SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица событий
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                slug TEXT UNIQUE,
                title TEXT,
                description TEXT,
                start_date TEXT,
                end_date TEXT,
                created_at TEXT,
                updated_at TEXT,
                closed BOOLEAN,
                active BOOLEAN,
                markets_json TEXT,
                indexed_at TEXT,
                expires_at TEXT
            )
        """)
        
        # Индекс для быстрого поиска по title и slug
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_title ON events(title)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_slug ON events(slug)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_start_date ON events(start_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON events(expires_at)
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")
    
    def _should_save_event(self, event: Dict[str, Any]) -> bool:
        """
        Проверяет, нужно ли сохранять событие
        
        Сохраняем все активные события (без фильтрации по дате)
        """
        # Сохраняем все события, которые не закрыты
        # Фильтрацию по дате не используем - сохраняем все
        return True
    
    async def parse_events_page(
        self, 
        offset: int = 0, 
        limit: int = 100,
        max_pages: int = 100
    ) -> int:
        """
        Парсит страницу событий и сохраняет в базу
        
        Returns:
            Количество сохраненных событий
        """
        url = f"{self.base_url}/events"
        params = {
            "limit": limit,
            "offset": offset,
            "closed": "false"
        }
        
        saved_count = 0
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://polymarket.com/"
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    events = await response.json()
                    
                    if not isinstance(events, list):
                        events = events.get("data", events.get("events", []))
                    
                    if not events:
                        return 0
                    
                    # Сохраняем события в базу
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    
                    now = datetime.now(timezone.utc).isoformat()
                    expires_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
                    
                    for event in events:
                        if not self._should_save_event(event):
                            continue
                        
                        try:
                            event_id = str(event.get('id', ''))
                            slug = event.get('slug', '')
                            title = event.get('title', '')
                            description = event.get('description', '')
                            start_date = event.get('startDate') or event.get('start_date', '')
                            end_date = event.get('endDate') or event.get('end_date', '')
                            created_at = event.get('createdAt') or event.get('created_at', '')
                            updated_at = event.get('updatedAt') or event.get('updated_at', '')
                            closed = event.get('closed', False)
                            active = event.get('active', True)
                            
                            # Сохраняем markets как JSON
                            markets = event.get('markets', [])
                            markets_json = json.dumps(markets) if markets else '[]'
                            
                            cursor.execute("""
                                INSERT OR REPLACE INTO events 
                                (id, slug, title, description, start_date, end_date, 
                                 created_at, updated_at, closed, active, markets_json, 
                                 indexed_at, expires_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                event_id, slug, title, description, start_date, end_date,
                                created_at, updated_at, closed, active, markets_json,
                                now, expires_at
                            ))
                            
                            saved_count += 1
                            
                        except Exception as e:
                            logger.warning(f"Error saving event: {e}, event_id={event.get('id')}")
                            continue
                    
                    conn.commit()
                    conn.close()
                    
                    logger.info(f"Page {offset//limit + 1}: saved {saved_count} events out of {len(events)}")
                    
                    # Если получили меньше событий, чем запросили - это последняя страница
                    if len(events) < limit:
                        return saved_count
                    
                    return saved_count
                else:
                    text = await response.text()
                    logger.error(f"Error fetching events: {response.status}, {text[:200]}")
                    return 0
        
        return saved_count
    
    async def parse_all_events(self, max_pages: int = 400, target_duration_minutes: int = 60) -> Dict[str, Any]:
        """
        Парсит все события (с пагинацией)
        
        Args:
            max_pages: Максимальное количество страниц (400 = ~40k событий)
            target_duration_minutes: Целевая длительность парсинга в минутах (распределяем запросы)
        
        Returns:
            Словарь со статистикой
        """
        logger.info(f"Starting event parsing (max_pages={max_pages}, target_duration={target_duration_minutes} min)")
        start_time = datetime.now()
        
        total_saved = 0
        page = 0
        limit = 100
        
        # Сначала очищаем закрытые события
        self._cleanup_old_events()
        
        # Рассчитываем задержку между запросами, чтобы растянуть на target_duration_minutes
        # Приблизительная оценка: max_pages запросов за target_duration_minutes
        target_duration_seconds = target_duration_minutes * 60
        delay_between_requests = max(0.2, target_duration_seconds / max_pages)  # Минимум 0.2 сек
        
        logger.info(f"Delay between requests: {delay_between_requests:.2f} seconds")
        
        while page < max_pages:
            offset = page * limit
            saved = await self.parse_events_page(offset=offset, limit=limit, max_pages=max_pages)
            
            if saved == 0:
                logger.info(f"No more events to save, stopping at page {page + 1}")
                break
            
            total_saved += saved
            page += 1
            
            # Задержка между запросами (растягиваем парсинг на час)
            await asyncio.sleep(delay_between_requests)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Получаем статистику
        stats = self.get_stats()
        
        result = {
            "total_saved": total_saved,
            "pages_parsed": page,
            "elapsed_seconds": elapsed,
            "total_events_in_db": stats.get("total_events", 0),
            "events_in_next_48h": stats.get("events_in_next_48h", 0)
        }
        
        logger.info(f"Parsing completed: {total_saved} events saved in {elapsed:.2f} seconds")
        return result
    
    def _cleanup_old_events(self):
        """Удаляет старые события (закончившиеся)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Удаляем события, которые уже закончились (end_date < now)
        cursor.execute("""
            DELETE FROM events 
            WHERE expires_at < ? OR end_date < ?
        """, (now, now))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old events")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получает статистику по базе данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Всего событий
        cursor.execute("SELECT COUNT(*) FROM events")
        total_events = cursor.fetchone()[0]
        
        # События, которые закончатся в ближайшие 48 часов (используем end_date)
        now = datetime.now(timezone.utc).isoformat()
        max_time = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        
        cursor.execute("""
            SELECT COUNT(*) FROM events 
            WHERE end_date >= ? AND end_date <= ?
        """, (now, max_time))
        events_in_next_48h = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_events": total_events,
            "events_in_next_48h": events_in_next_48h
        }
    
    def search_events(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Поиск событий в локальной базе данных
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
        
        Returns:
            Список событий
        """
        import time
        start_time = time.time()
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query_lower = query.lower()
        
        # Ищем в title и slug
        cursor.execute("""
            SELECT * FROM events 
            WHERE LOWER(title) LIKE ? OR LOWER(slug) LIKE ?
            ORDER BY start_date ASC
            LIMIT ?
        """, (f"%{query_lower}%", f"%{query_lower}%", limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        events = []
        for row in rows:
            event = dict(row)
            # Парсим markets из JSON
            try:
                event['markets'] = json.loads(event.get('markets_json', '[]'))
            except:
                event['markets'] = []
            # Удаляем внутренние поля
            event.pop('markets_json', None)
            event.pop('indexed_at', None)
            event.pop('expires_at', None)
            events.append(event)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Логируем результат поиска
        logger.info(f"DB Search: query='{query}', found={len(events)}, time={elapsed_ms:.2f}ms")
        
        # Добавляем лог в logger_service для дашборда
        try:
            from app.services.logger_service import log_storage
            log_storage.add_api_log(
                f"DB Search: query='{query}' → found {len(events)} events ({elapsed_ms:.2f}ms)",
                "INFO",
                {
                    "type": "db_search",
                    "query": query,
                    "found_count": len(events),
                    "elapsed_ms": round(elapsed_ms, 2),
                    "events": [
                        {
                            "id": e.get('id'),
                            "title": e.get('title', '')[:100],
                            "start_date": e.get('start_date')
                        } for e in events[:5]  # Первые 5 для лога
                    ]
                }
            )
        except Exception as e:
            logger.warning(f"Failed to log DB search to logger_service: {e}")
        
        return events
