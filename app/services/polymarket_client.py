import logging
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
import aiohttp
from app.config.settings import Settings
from app.services.event_parser import EventParser

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Клиент для работы с Polymarket Gamma API"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.polymarket_gamma_api_url
        self.api_key = settings.polymarket_api_key
        self.api_secret = settings.polymarket_api_secret
        self.api_passphrase = settings.polymarket_api_passphrase
        
        # Инициализируем парсер событий для локального кэширования
        self.event_parser = EventParser(db_path="polymarket_events.db")
        
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        use_auth: bool = False
    ) -> Dict[str, Any]:
        """Базовый метод для выполнения HTTP запросов к Gamma API"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://polymarket.com/"
        }
        
        # Добавляем авторизацию если требуется
        if use_auth and self.api_key:
            # Polymarket API может использовать разные форматы авторизации
            # Попробуем наиболее распространенные варианты
            headers["X-API-Key"] = self.api_key
            # Альтернативные варианты (можно попробовать)
            # headers["Authorization"] = f"Bearer {self.api_key}"
            # headers["RF-Api-Key"] = self.api_key
        
        async with aiohttp.ClientSession() as session:
            try:
                import json as json_lib
                full_url = f"{url}?{urlencode(params)}" if params else url
                logger.info(f"Polymarket API Request: {method} {full_url}, use_auth={use_auth}")
                if data:
                    logger.info(f"Request body: {json_lib.dumps(data, indent=2, ensure_ascii=False)}")
                
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params
                ) as response:
                    response_text = await response.text()
                    
                    if response.status == 200:
                        try:
                            json_response = await response.json()
                            response_json_str = json_lib.dumps(json_response, indent=2, ensure_ascii=False)
                            logger.info(f"Polymarket API Response (status=200):\n{response_json_str[:2000]}")  # Первые 2000 символов
                            return json_response
                        except Exception as e:
                            logger.warning(f"Response is not JSON: {response_text[:500]}, error: {e}")
                            return {"data": response_text}
                    elif response.status == 401:
                        logger.warning(f"API authentication failed (401): {response_text[:500]}")
                        raise Exception(f"API authentication failed (401): {response_text[:500]}")
                    else:
                        logger.error(f"API error {response.status}: {response_text[:500]}")
                        raise Exception(f"API error {response.status}: {response_text[:500]}")
            except aiohttp.ClientError as e:
                logger.error(f"Request error: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise
    
    async def search_events_via_search_api(
        self, 
        query: str,
        search_type: str = "market"  # "market" или "event"
    ) -> List[Dict[str, Any]]:
        """
        Поиск событий через /search endpoint (требует авторизацию)
        API: GET /search?q=query&type=market
        
        Это более точный поиск, чем client-side filtering
        """
        if not self.api_key:
            logger.warning("API key not configured, cannot use /search endpoint")
            return []
        
        params = {
            "q": query,
            "type": search_type
        }
        
        try:
            logger.info(f"Searching via /search endpoint: query='{query}', type={search_type}")
            response = await self._make_request("GET", "/search", params=params, use_auth=True)
            
            # /search может возвращать данные в разных форматах
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                # Может быть обертка с полем 'data', 'results', 'markets', 'events'
                results = response.get("data", response.get("results", response.get("markets", response.get("events", []))))
                if isinstance(results, list):
                    return results
                return []
            else:
                return []
        except Exception as e:
            logger.error(f"Error searching via /search endpoint: {e}")
            return []
    
    async def search_events(
        self, 
        query: str,
        sport: Optional[str] = None,
        limit: int = 100,  # Лимит на одну страницу (100 как рекомендует ChatGPT)
        max_pages: int = 50  # Максимальное количество страниц для пагинации
    ) -> List[Dict[str, Any]]:
        """
        Поиск событий (events) по запросу
        
        Сначала ищет в локальной базе данных (быстро), затем fallback на API поиск.
        
        Args:
            query: Поисковый запрос (название команды/игрока)
            sport: Опциональный фильтр по спорту
            limit: Количество событий на страницу (рекомендуется 100)
            max_pages: Максимальное количество страниц для перебора
        """
        # Сначала пробуем поиск в локальной базе данных (быстрее)
        try:
            db_events = self.event_parser.search_events(query, limit=20)
            if db_events:
                logger.info(f"Found {len(db_events)} events in local database for query: '{query}'")
                
                # Логируем успешный поиск в БД
                try:
                    from app.services.logger_service import log_storage
                    log_storage.add_api_log(
                        f"Event search: Using local DB → found {len(db_events)} events for '{query}'",
                        "INFO",
                        {
                            "type": "event_search",
                            "source": "local_db",
                            "query": query,
                            "found_count": len(db_events)
                        }
                    )
                except Exception:
                    pass
                
                # Конвертируем формат для совместимости
                formatted_events = []
                for event in db_events:
                    formatted_event = {
                        'id': event.get('id'),
                        'slug': event.get('slug'),
                        'title': event.get('title'),
                        'description': event.get('description'),
                        'startDate': event.get('start_date'),
                        'endDate': event.get('end_date'),
                        'createdAt': event.get('created_at'),
                        'updatedAt': event.get('updated_at'),
                        'closed': event.get('closed', False),
                        'active': event.get('active', True),
                        'markets': event.get('markets', [])
                    }
                    formatted_events.append(formatted_event)
                return formatted_events
            else:
                # Логируем что в БД не найдено, переходим к API
                try:
                    from app.services.logger_service import log_storage
                    log_storage.add_api_log(
                        f"Event search: No results in local DB for '{query}', falling back to API",
                        "INFO",
                        {
                            "type": "event_search",
                            "source": "local_db",
                            "query": query,
                            "found_count": 0,
                            "fallback": True
                        }
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error searching in local database: {e}, falling back to API search")
            # Логируем ошибку
            try:
                from app.services.logger_service import log_storage
                log_storage.add_api_log(
                    f"Event search: DB error for '{query}': {str(e)}, falling back to API",
                    "WARNING",
                    {
                        "type": "event_search",
                        "source": "local_db",
                        "query": query,
                        "error": str(e),
                        "fallback": True
                    }
                )
            except Exception:
                pass
        
        # Fallback: Client-Side Filtering с пагинацией (если не нашли в БД)
        query_lower = query.lower()
        all_filtered_events = []
        max_events_per_page = 100  # Используем 100 для более точной пагинации (как рекомендует ChatGPT)
        
        import time
        start_time = time.time()
        
        try:
            for page in range(max_pages):
                offset = page * max_events_per_page
                params = {
                    "limit": max_events_per_page,
                    "offset": offset,
                    "closed": "false"  # Только активные события
                }
                
                if sport:
                    params["sport"] = sport
                
                logger.info(f"Fetching events page {page + 1} (offset={offset}, limit={max_events_per_page})")
                response = await self._make_request("GET", "/events", params=params)
                
                # Получаем список событий
                if isinstance(response, list):
                    events_list = response
                elif isinstance(response, dict):
                    events_list = response.get("data", response.get("events", []))
                else:
                    events_list = []
                
                if not events_list:
                    logger.info(f"No more events at offset {offset}, stopping pagination")
                    break
                
                # Client-Side Filtering: фильтруем события локально
                page_filtered = []
                for event in events_list:
                    title = (event.get('title', '') or '').lower()
                    slug = (event.get('slug', '') or '').lower()
                    description = (event.get('description', '') or '').lower()
                    
                    # Проверяем наличие query в title, slug или description
                    if (query_lower in title or 
                        query_lower in slug or 
                        query_lower in description):
                        page_filtered.append(event)
                        all_filtered_events.append(event)
                
                logger.info(f"Page {page + 1}: found {len(page_filtered)} matching events out of {len(events_list)} total")
                
                # Если получили меньше событий, чем запросили - это последняя страница
                if len(events_list) < max_events_per_page:
                    logger.info(f"Last page reached (got {len(events_list)} events, less than {max_events_per_page})")
                    break
            
            elapsed_time = time.time() - start_time
            logger.info(f"Client-side filtering with pagination: found {len(all_filtered_events)} events matching '{query}' in {elapsed_time:.2f} seconds ({page + 1} pages)")
            
            # Логируем API поиск
            try:
                from app.services.logger_service import log_storage
                log_storage.add_api_log(
                    f"Event search: Using API → found {len(all_filtered_events)} events for '{query}' ({elapsed_time:.2f}s, {page + 1} pages)",
                    "INFO",
                    {
                        "type": "event_search",
                        "source": "api",
                        "query": query,
                        "found_count": len(all_filtered_events),
                        "elapsed_seconds": round(elapsed_time, 2),
                        "pages_searched": page + 1
                    }
                )
            except Exception:
                pass
            
            # Проверяем, может markets уже включены в events
            if all_filtered_events and isinstance(all_filtered_events, list) and len(all_filtered_events) > 0:
                first_event = all_filtered_events[0]
                if "markets" in first_event:
                    logger.info(f"Events response includes markets field - markets are already in events data")
            
            return all_filtered_events
        except Exception as e:
            logger.error(f"Error searching events: {e}")
            return []
        
    async def get_event_markets(
        self, 
        event_id: str
    ) -> List[Dict[str, Any]]:
        """
        Получение markets для события
        
        API: GET /markets?event_id=<event_id>
        """
        params = {"event_id": event_id}
        try:
            response = await self._make_request("GET", "/markets", params=params)
            markets_count = len(response) if isinstance(response, list) else 'unknown'
            logger.info(f"Markets response: found {markets_count} markets")
            
            if isinstance(response, list) and response:
                first_market = response[0]
                logger.info(f"First market sample: {first_market.get('id')}, {first_market.get('question')}")
            
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(f"Error getting markets for event {event_id}: {e}")
            return []

    async def get_event_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """
        Получение события по slug
        API: GET /events/slug/{slug}
        """
        try:
            logger.info(f"Fetching event by slug: {slug}")
            response = await self._make_request("GET", f"/events/slug/{slug}")
            if isinstance(response, dict):
                return response.get("data", response)
            return response
        except Exception as e:
            logger.error(f"Error getting event by slug {slug}: {e}")
            return None
    
    async def get_market_by_id(self, market_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение market по ID
        API: GET /markets/{id}
        """
        try:
            logger.info(f"Fetching market by ID: {market_id}")
            response = await self._make_request("GET", f"/markets/{market_id}")
            
            if isinstance(response, dict):
                return response.get("data", response)
            return response
        except Exception as e:
            logger.error(f"Error getting market by ID {market_id}: {e}")
            return None
    
    def _filter_markets_by_type(
        self,
        markets: List[Dict[str, Any]],
        market_type: str,
        target: Optional[str] = None,
        pivot: Optional[str] = None,
        home_teams: Optional[List[str]] = None,
        away_teams: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Фильтрация markets по типу, target и pivot
        
        market_type может быть: ONE_TWO, TOTAL, HDP, T1_TOTAL, T2_TOTAL
        """
        one_two_markets = []  # Для отладки: собираем все ONE_TWO маркеты
        total_markets = []  # Для отладки: собираем все TOTAL маркеты
        
        for market in markets:
            market_title = market.get("title", "").upper()
            market_question = market.get("question", "").upper()
            market_text = f"{market_title} {market_question}"
            
            # Определяем тип market по тексту
            detected_type = self._detect_market_type(market_text)
            
            # Логируем для отладки, если тип не совпадает
            if market_type == "ONE_TWO" and detected_type != market_type:
                logger.debug(f"Market ID {market.get('id')}: detected_type={detected_type}, expected={market_type}, question='{market.get('question', '')[:60]}'")
            
            if detected_type != market_type:
                continue
            
            # Для отладки ONE_TWO маркетов
            if market_type == "ONE_TWO":
                one_two_markets.append({
                    "id": market.get("id"),
                    "title": market.get("title", ""),
                    "question": market.get("question", ""),
                    "market_text": market_text,
                    "market": market  # Сохраняем весь объект для детального логирования
                })
            
            # Для отладки TOTAL маркетов
            if market_type in ["TOTAL", "T1_TOTAL", "T2_TOTAL"]:
                total_markets.append({
                    "id": market.get("id"),
                    "title": market.get("title", ""),
                    "question": market.get("question", ""),
                    "market_text": market_text
                })
            
            # Для TOTAL и HDP проверяем pivot
            if market_type in ["TOTAL", "T1_TOTAL", "T2_TOTAL", "HDP"] and pivot:
                if not self._check_pivot_match(market_text, pivot):
                    continue
            
            # Для ONE_TWO и других проверяем target
            if target and not self._check_target_match(market_text, target, market_type, home_teams, away_teams):
                continue
            
            return market
        
        # Если не нашли и это ONE_TWO, логируем для отладки
        if market_type == "ONE_TWO" and one_two_markets and target:
            logger.warning(f"ONE_TWO markets found ({len(one_two_markets)}) but target '{target}' didn't match")
            # Детальное логирование для каждого маркета
            for m in one_two_markets[:3]:
                market_obj = m.get('market', {})
                market_text_for_check = f"{m.get('title', '')} {m.get('question', '')}".lower()
                match_result = self._check_target_match(market_text_for_check, target, market_type, home_teams, away_teams)
                logger.warning(f"  Market ID {m.get('id')}: title='{m.get('title', 'N/A')[:60]}', question='{m.get('question', 'N/A')[:60]}', target_match={match_result}")
                logger.warning(f"    Market text (lower): '{market_text_for_check[:150]}'")
                logger.warning(f"    Home teams: {home_teams}, Away teams: {away_teams}")
        
        # Если не нашли и это TOTAL, логируем для отладки
        if market_type in ["TOTAL", "T1_TOTAL", "T2_TOTAL"] and total_markets:
            logger.debug(f"TOTAL markets found ({len(total_markets)}) but filters didn't match. pivot={pivot}, target={target}. Sample markets: {[m['question'][:60] for m in total_markets[:3]]}")
        
        return None
    
    def _detect_market_type(self, market_text: str) -> Optional[str]:
        """Определение типа market по тексту"""
        market_text_upper = market_text.upper()
        market_text = market_text_upper
        
        # 1X2 (Match Winner / Match Result)
        if any(word in market_text for word in ["WINNER", "WIN", "RESULT", "1X2", "MATCH RESULT", "MONEYLINE"]):
            return "ONE_TWO"
        
        # Если формат "Team A vs. Team B" или "Team A vs Team B" без других ключевых слов
        # и это не TOTAL/HDP (нет OVER/UNDER/SPREAD/HANDICAP), то это скорее всего ONE_TWO
        if " VS. " in market_text or " VS " in market_text:
            # Проверяем, что это не TOTAL или HDP
            if not any(word in market_text for word in ["TOTAL", "OVER", "UNDER", "O/U", "SPREAD", "HANDICAP", "HDP", "POINTS", "SCORE"]):
                # Если это формат "Team A vs. Team B", то это скорее всего ONE_TWO (Match Winner)
                return "ONE_TWO"
        
        # TOTAL (Over/Under)
        # Проверяем различные варианты написания Total/Over/Under
        total_keywords = ["TOTAL", "OVER/UNDER", "O/U", "OVER UNDER", "O U", "OVER-UNDER", "POINTS", "SCORE"]
        if any(word in market_text for word in total_keywords):
            if "TEAM" in market_text or "TEAM 1" in market_text or "TEAM1" in market_text:
                return "T1_TOTAL"
            elif "TEAM 2" in market_text or "TEAM2" in market_text:
                return "T2_TOTAL"
            return "TOTAL"
        
        # Также проверяем, если в тексте есть "Over" и "Under" вместе (без явного "Total")
        if ("OVER" in market_text and "UNDER" in market_text) or ("OVER" in market_text and "/" in market_text):
            return "TOTAL"
        
        # HDP (Handicap / Spread)
        if any(word in market_text for word in ["HANDICAP", "SPREAD", "HDP", "ASIAN HANDICAP"]):
            return "HDP"
        
        return None
    
    def _check_pivot_match(self, market_text: str, pivot: str) -> bool:
        """Проверка соответствия pivot в тексте market"""
        try:
            bet_pivot_val = float(pivot)
            # Ищем все числа в тексте маркета (включая десятичные)
            numbers = re.findall(r"\d+\.?\d*", market_text)
            for num_str in numbers:
                try:
                    market_pivot_val = float(num_str)
                    # Сравниваем с точностью до 0.1 (на случай округления)
                    if abs(market_pivot_val - bet_pivot_val) < 0.1:
                        return True
                except ValueError:
                    continue
            return False
        except (ValueError, AttributeError):
            return False

    def _check_target_match(
        self, 
        market_text: str, 
        target: str, 
        market_type: str,
        home_teams: Optional[List[str]] = None,
        away_teams: Optional[List[str]] = None
    ) -> bool:
        """Проверка соответствия target в тексте market"""
        target_lower = target.lower()
        market_text_lower = market_text.lower()

        if market_type == "ONE_TWO":
            # Маппинг ONE -> HOME, TWO -> AWAY (согласно ONE_TWO_TARGET_MAP)
            original_target = target_lower
            if target_lower == "one":
                target_lower = "home"
            elif target_lower == "two":
                target_lower = "away"
            
            # Для 1X2 (Moneyline) target может быть "1", "X", "2", "HOME", "AWAY" или названия команд
            # Проверяем различные варианты обозначения HOME/TEAM 1
            if target_lower in ["1", "home"]:
                home_keywords = ["home", "team 1", "team1", "first team", "1st team"]
                if any(keyword in market_text_lower for keyword in home_keywords):
                    return True
                # Также проверяем, если в тексте есть "1" в контексте команды
                if " 1 " in market_text_lower or market_text_lower.startswith("1 ") or " (1)" in market_text_lower:
                    return True
                # Проверяем по названию первой команды (home_teams)
                # Важно: проверяем двустороннее совпадение (фамилия может быть в полном имени и наоборот)
                if home_teams:
                    for team in home_teams:
                        if team:
                            team_lower = team.lower()
                            # Проверяем двустороннее совпадение: team в market_text или market_text содержит часть team
                            if team_lower in market_text_lower:
                                return True
                            # Также проверяем, если отдельные слова из team есть в market_text
                            team_words = team_lower.split()
                            for word in team_words:
                                if len(word) > 3 and word in market_text_lower:  # Только слова длиннее 3 символов
                                    return True
            
            # Проверяем различные варианты обозначения AWAY/TEAM 2
            if target_lower in ["2", "away"]:
                away_keywords = ["away", "team 2", "team2", "second team", "2nd team"]
                if any(keyword in market_text_lower for keyword in away_keywords):
                    return True
                # Также проверяем, если в тексте есть "2" в контексте команды
                if " 2 " in market_text_lower or market_text_lower.startswith("2 ") or " (2)" in market_text_lower:
                    return True
                # Проверяем по названию второй команды (away_teams)
                # Важно: проверяем двустороннее совпадение (фамилия может быть в полном имени и наоборот)
                if away_teams:
                    for team in away_teams:
                        if team:
                            team_lower = team.lower()
                            # Проверяем двустороннее совпадение: team в market_text или market_text содержит часть team
                            if team_lower in market_text_lower:
                                return True
                            # Также проверяем, если отдельные слова из team есть в market_text
                            team_words = team_lower.split()
                            for word in team_words:
                                if len(word) > 3 and word in market_text_lower:  # Только слова длиннее 3 символов
                                    return True
            
            # Проверяем ничью
            if target_lower == "x" or original_target == "x":
                if any(keyword in market_text_lower for keyword in ["draw", "tie", "x"]):
                    return True
            
            # Проверяем по названию команды (если target - это название команды)
            if target_lower in market_text_lower:
                return True
        
        # Для TOTAL markets проверяем OVER/UNDER
        if market_type in ["TOTAL", "T1_TOTAL", "T2_TOTAL"]:
            if target_lower in ["over", "to"]:
                # Ищем "over" в тексте маркета
                over_keywords = ["over", "o/", "o "]
                if any(keyword in market_text_lower for keyword in over_keywords):
                    return True
                # Если в тексте есть только два варианта (Over/Under), первый обычно Over
                if "under" not in market_text_lower and len(market_text_lower.split()) > 0:
                    return True
            elif target_lower in ["under", "tu"]:
                # Ищем "under" в тексте маркета
                under_keywords = ["under", "u/", "u "]
                if any(keyword in market_text_lower for keyword in under_keywords):
                    return True
                # Если в тексте есть только два варианта (Over/Under), второй обычно Under
                if "over" in market_text_lower:
                    return True
        
        # Для HDP (Handicap / Spread) проверяем по названиям команд
        if market_type in ["HDP", "EURO_HDP"]:
            if target_lower in ["home", "ah1"]:
                # Проверяем по названию первой команды (home_teams)
                if home_teams:
                    for team in home_teams:
                        if team:
                            team_lower = team.lower()
                            if team_lower in market_text_lower:
                                return True
                            # Также проверяем, если отдельные слова из team есть в market_text
                            team_words = team_lower.split()
                            for word in team_words:
                                if len(word) > 3 and word in market_text_lower:
                                    return True
                # Проверяем ключевые слова
                if any(keyword in market_text_lower for keyword in ["home", "team 1", "team1", "+", "ah1"]):
                    return True
            elif target_lower in ["away", "ah2"]:
                # Проверяем по названию второй команды (away_teams)
                if away_teams:
                    for team in away_teams:
                        if team:
                            team_lower = team.lower()
                            if team_lower in market_text_lower:
                                return True
                            # Также проверяем, если отдельные слова из team есть в market_text
                            team_words = team_lower.split()
                            for word in team_words:
                                if len(word) > 3 and word in market_text_lower:
                                    return True
                # Проверяем ключевые слова
                if any(keyword in market_text_lower for keyword in ["away", "team 2", "team2", "-", "ah2"]):
                    return True
        
        # Для других типов, просто проверяем вхождение
        return target_lower in market_text_lower
