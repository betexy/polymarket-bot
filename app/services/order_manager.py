import logging
from typing import Optional, Dict, Any
from collections import defaultdict
from app.models.bet import BetData
from app.services.polymarket_client import PolymarketClient
from app.services.data_mapper import DataMapper
from app.services.clob_client import PolymarketCLOBClient
from app.services.logger_service import log_storage
from app.services.settings_service import get_settings_service
from app.config.settings import Settings

logger = logging.getLogger(__name__)


class OrderManager:
    """Управление ордерами на Polymarket"""
    
    def __init__(
        self, 
        polymarket_client: PolymarketClient, 
        clob_client: Optional[PolymarketCLOBClient],
        settings: Settings
    ):
        self.client = polymarket_client  # Gamma API client
        self.clob_client = clob_client  # CLOB API client
        self.settings = settings
        self.mapper = DataMapper()
        # Счетчики ставок для контроля лимитов (в памяти, сбрасываются при перезапуске)
        self._bets_per_market: Dict[str, int] = defaultdict(int)  # market_id -> count
        self._bets_per_match: Dict[str, int] = defaultdict(int)  # event_id -> count
    
    async def process_bet(self, bet_data: BetData) -> Dict[str, Any]:
        """Обработка ставки от парсера и размещение ордера"""
        try:
            # Проверка минимальной прибыли
            if bet_data.surebet_profit is not None:
                if bet_data.surebet_profit < self.settings.min_profit_percent:
                    logger.info(f"Bet skipped: profit {bet_data.surebet_profit}% < min {self.settings.min_profit_percent}%")
                    result = {"status": "skipped", "reason": "low_profit"}
                    log_storage.add_bet(bet_data.dict(), result)
                    log_storage.add_api_log(f"Bet skipped: low profit {bet_data.surebet_profit}%", "INFO")
                    return result
            
            # Проверка, что это ставка на Polymarket
            if bet_data.bookmaker != "POLYMARKET":
                logger.info(f"Bet skipped: bookmaker {bet_data.bookmaker} is not POLYMARKET")
                result = {"status": "skipped", "reason": "not_polymarket"}
                log_storage.add_bet(bet_data.dict(), result)
                return result
            
            # Проверка second_bookmaker - ставим только для определенных букмекеров
            if bet_data.second_bookmaker:
                allowed_bookmakers = self.settings.allowed_second_bookmakers
                if bet_data.second_bookmaker not in allowed_bookmakers:
                    # Пропускаем без логирования (чтобы не засорять логи)
                    result = {"status": "skipped", "reason": f"second_bookmaker_not_allowed: {bet_data.second_bookmaker}"}
                    log_storage.add_bet(bet_data.dict(), result)
                    return result
            
            # Логируем, что ставка прошла проверку и будет обрабатываться
            logger.info(f"Bet approved for processing: {bet_data.homeTeam} vs {bet_data.awayTeam}, second_bookmaker: {bet_data.second_bookmaker}")
            log_storage.add_api_log(
                f"Bet approved: {bet_data.homeTeam} vs {bet_data.awayTeam}",
                "INFO",
                {
                    "bookmaker": bet_data.bookmaker,
                    "second_bookmaker": bet_data.second_bookmaker,
                    "market": bet_data.market,
                    "target": bet_data.target,
                    "coef": bet_data.coef,
                    "homeTeam": bet_data.homeTeam,
                    "awayTeam": bet_data.awayTeam
                }
            )
            
            # Подготовка данных
            order_data = self.mapper.prepare_order_data(bet_data)
            
            # Поиск соответствующего market
            logger.info(f"Searching market for: {bet_data.homeTeam} vs {bet_data.awayTeam}, market_type: {bet_data.market}")
            log_storage.add_api_log(
                f"Searching market: {bet_data.homeTeam} vs {bet_data.awayTeam}",
                "INFO",
                {"market_type": bet_data.market, "target": bet_data.target, "second_bookmaker": bet_data.second_bookmaker}
            )
            
            market_info = await self._find_market(bet_data, order_data)
            if not market_info:
                search_query = order_data.get('search_query', 'N/A')
                logger.warning(f"Market not found for: {search_query}")
                result = {"status": "error", "reason": "market_not_found", "search_query": search_query}
                log_storage.add_bet(bet_data.dict(), result)
                log_storage.add_api_log(
                    f"Market not found: {bet_data.homeTeam} vs {bet_data.awayTeam}",
                    "WARNING",
                    {
                        "second_bookmaker": bet_data.second_bookmaker,
                        "market_type": bet_data.market,
                        "search_query": order_data.get('search_query'),
                        "api_response": "No matching market found"
                    }
                )
                return result
            
            logger.info(f"Market found: {market_info.get('id')}, title: {market_info.get('title', 'N/A')}")
            log_storage.add_api_log(
                f"Market found: {market_info.get('id')}",
                "SUCCESS",
                {
                    "market_id": market_info.get("id"),
                    "title": market_info.get("title"),
                    "second_bookmaker": bet_data.second_bookmaker,
                    "api_response": {
                        "id": market_info.get("id"),
                        "title": market_info.get("title"),
                        "question": market_info.get("question"),
                        "outcomes": market_info.get("outcomes", [])[:3]  # Первые 3 исхода
                    }
                }
            )
            
            market_id = market_info.get("id")
            event_id = market_info.get("event_id") or market_info.get("conditionId", "").split("_")[0] if market_info.get("conditionId") else ""
            
            # Проверка лимитов ставок
            settings_service = get_settings_service()
            max_bets_per_market = settings_service.get_max_bets_per_market()
            max_bets_per_match = settings_service.get_max_bets_per_match()
            
            # Проверяем лимит на маркет
            if market_id:
                current_market_bets = self._bets_per_market.get(market_id, 0)
                if current_market_bets >= max_bets_per_market:
                    logger.warning(f"Max bets per market limit reached: {current_market_bets}/{max_bets_per_market} for market {market_id}")
                    result = {
                        "status": "skipped",
                        "reason": "max_bets_per_market_limit",
                        "market_id": market_id,
                        "current_bets": current_market_bets,
                        "max_bets": max_bets_per_market
                    }
                    log_storage.add_bet(bet_data.dict(), result)
                    return result
            
            # Проверяем лимит на матч
            if event_id:
                current_match_bets = self._bets_per_match.get(event_id, 0)
                if current_match_bets >= max_bets_per_match:
                    logger.warning(f"Max bets per match limit reached: {current_match_bets}/{max_bets_per_match} for event {event_id}")
                    result = {
                        "status": "skipped",
                        "reason": "max_bets_per_match_limit",
                        "event_id": event_id,
                        "current_bets": current_match_bets,
                        "max_bets": max_bets_per_match
                    }
                    log_storage.add_bet(bet_data.dict(), result)
                    return result
            if not market_id:
                logger.error("Market ID not found in market_info")
                return {"status": "error", "reason": "invalid_market_info"}
            
            # Рассчет параметров ордера (с проверкой текущей цены)
            try:
                order_params = self._calculate_order_params(bet_data, order_data, market_info)
            except ValueError as e:
                error_msg = str(e)
                if "profit_too_low" in error_msg:
                    logger.warning(f"Bet skipped: {error_msg}")
                    result = {"status": "skipped", "reason": error_msg}
                    log_storage.add_bet(bet_data.dict(), result)
                    log_storage.add_api_log(
                        f"Bet skipped: {error_msg}",
                        "WARNING",
                        {
                            "market_id": market_info.get('id'),
                            "original_profit": bet_data.surebet_profit,
                            "reason": error_msg
                        }
                    )
                    return result
                else:
                    raise
            
            # Получение token_id из market данных
            outcome = order_params.get("outcome", "YES")
            
            # Получаем доступные outcomes (может быть список или строка JSON)
            available_outcomes = market_info.get('outcomes', [])
            if isinstance(available_outcomes, str):
                # Если это строка JSON, парсим её
                try:
                    import json
                    available_outcomes = json.loads(available_outcomes)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"Could not parse outcomes as JSON: {available_outcomes}")
                    available_outcomes = []
            
            logger.info(f"Outcome from order_params: {outcome}, available outcomes: {available_outcomes}")
            
            # Проверяем, правильно ли определен outcome
            # Если outcome = "YES" или "NO" (старые значения), или его нет в доступных outcomes, переизвлекаем
            if not outcome or outcome in ["YES", "NO"] or (available_outcomes and outcome not in available_outcomes):
                # Если outcome не был правильно определен, пробуем извлечь заново
                logger.info(f"Outcome '{outcome}' not valid, re-extracting from market. Available: {available_outcomes}")
                outcome = self.mapper.extract_market_outcome(market_info, bet_data)
                logger.info(f"Re-extracted outcome: {outcome}")
                
                # Если outcome все еще не определен или не найден в списке, используем fallback
                if not outcome or (available_outcomes and outcome not in available_outcomes):
                    # Если все еще не определен, берем первый outcome из доступных
                    if available_outcomes and len(available_outcomes) > 0:
                        outcome = available_outcomes[0] if isinstance(available_outcomes[0], str) else "YES"
                        logger.warning(f"Using first available outcome as fallback: {outcome}")
                    else:
                        outcome = "YES"  # Последний fallback
                        logger.warning(f"No outcomes available, using 'YES' as fallback")
            
            logger.info(f"Final outcome: {outcome} for market {market_id}, available outcomes: {available_outcomes}")
            logger.info(f"Market info before get_token_id_from_market: has clobTokenIds={bool(market_info.get('clobTokenIds'))}, has tokens={bool(market_info.get('tokens'))}, has outcomeTokens={bool(market_info.get('outcomeTokens'))}")
            if market_info.get('clobTokenIds'):
                logger.info(f"clobTokenIds value: {str(market_info.get('clobTokenIds'))[:200]}")
            token_id = None
            # get_token_id_from_market не требует инициализированного CLOB клиента
            # Она просто извлекает token_id из данных market
            if self.clob_client:
                logger.info(f"Calling get_token_id_from_market for outcome='{outcome}'")
                token_id = self.clob_client.get_token_id_from_market(market_info, outcome)
                logger.info(f"get_token_id_from_market returned: {token_id}")
            else:
                logger.warning(f"CLOB client is None, skipping token_id search")
            
            if not token_id:
                # Детальное логирование для отладки
                logger.error(f"❌ Token ID not found for market {market_id}, outcome: {outcome}")
                logger.error(f"   Market info keys: {list(market_info.keys())[:15]}")
                logger.error(f"   Available outcomes: {market_info.get('outcomes', [])}")
                logger.error(f"   Tokens in market_info: {market_info.get('tokens', 'NOT FOUND')}")
                logger.error(f"   OutcomeTokens in market_info: {market_info.get('outcomeTokens', 'NOT FOUND')}")
                
                # Пытаемся найти tokens в разных местах
                tokens_found = market_info.get("tokens") or market_info.get("outcomes") or market_info.get("outcomeTokens")
                if tokens_found:
                    logger.error(f"   Tokens found (type: {type(tokens_found).__name__}, count: {len(tokens_found) if isinstance(tokens_found, list) else 'N/A'})")
                    if isinstance(tokens_found, list) and len(tokens_found) > 0:
                        logger.error(f"   First token: {str(tokens_found[0])[:200]}")
                else:
                    logger.error(f"   ⚠️ NO TOKENS FOUND IN MARKET_INFO!")
                
                result = {
                    "status": "error",
                    "reason": "token_id_not_found",
                    "market_id": market_id,
                    "market_info": {
                        "title": market_info.get("title"),
                        "question": market_info.get("question"),
                    }
                }
                log_storage.add_bet(bet_data.dict(), result)
                log_storage.add_api_log(
                    f"Token ID not found for market {market_id}, outcome: {outcome}",
                    "WARNING",
                    {
                        "market_id": market_id,
                        "outcome": outcome,
                        "available_outcomes": market_info.get("outcomes", []),
                        "market_structure": list(market_info.keys())[:10],
                        "tokens_found": bool(tokens_found),
                        "tokens_type": type(tokens_found).__name__ if tokens_found else None,
                        "tokens_count": len(tokens_found) if isinstance(tokens_found, list) else None
                    }
                )
                return result
            
            # Размещение ордера через CLOB API
            if self.clob_client and self.clob_client.is_available():
                # Проверяем баланс и allowance перед размещением ордера
                required_amount = float(order_params["size"]) * float(order_params["price"])
                balance_check = self.clob_client.check_balance_and_allowance(required_amount)
                
                # Логируем информацию о балансе
                logger.info(f"Balance check: balance={balance_check.get('balance', 0)}, allowance={balance_check.get('allowance', 'unknown')}, required={required_amount}, address={balance_check.get('address', 'unknown')}")
                log_storage.add_api_log(
                    f"Balance check before order: balance={balance_check.get('balance', 0)}, required={required_amount}",
                    "INFO",
                    {
                        "address": balance_check.get("address"),
                        "balance": balance_check.get("balance"),
                        "allowance": balance_check.get("allowance"),
                        "required_amount": required_amount,
                        "has_balance": balance_check.get("has_balance"),
                        "has_allowance": balance_check.get("has_allowance")
                    }
                )
                
                # Проверяем баланс (если проверка прошла успешно)
                if balance_check.get("has_balance") is False:
                    error_msg = f"Insufficient balance: {balance_check.get('balance', 0)} < {required_amount}"
                    logger.error(error_msg)
                    result = {
                        "status": "error",
                        "reason": "insufficient_balance",
                        "balance": balance_check.get("balance", 0),
                        "required": required_amount,
                        "address": balance_check.get("address")
                    }
                    log_storage.add_bet(bet_data.dict(), result)
                    log_storage.add_api_log(
                        f"Order skipped: insufficient balance",
                        "ERROR",
                        {
                            "balance": balance_check.get("balance", 0),
                            "required": required_amount,
                            "address": balance_check.get("address")
                        }
                    )
                    return result
                
                # Проверяем и обновляем allowance, если нужно
                if balance_check.get("needs_allowance_update", True):
                    logger.info("Updating balance allowance for CLOB contract...")
                    try:
                        self.clob_client.update_balance_allowance()
                        logger.info("Balance allowance updated successfully")
                        log_storage.add_api_log(
                            "Balance allowance updated",
                            "INFO",
                            {"address": balance_check.get("address")}
                        )
                    except Exception as allowance_error:
                        logger.warning(f"Failed to update allowance (may not be critical): {allowance_error}")
                        # Продолжаем попытку размещения ордера, т.к. ошибка может быть не критичной
                
                # Логируем отправку в CLOB API
                logger.info(f"Sending order to CLOB API: market_id={market_id}, price={order_params['price']}, size={order_params['size']}")
                log_storage.add_api_log(
                    f"Sending to CLOB API: {bet_data.homeTeam} vs {bet_data.awayTeam}",
                    "INFO",
                    {
                        "market_id": market_id,
                        "token_id": token_id,
                        "price": order_params["price"],
                        "size": order_params["size"],
                        "second_bookmaker": bet_data.second_bookmaker
                    }
                )
                
                try:
                    order_result = self.clob_client.create_order(
                        token_id=token_id,
                        price=order_params["price"],
                        size=order_params["size"],
                        side="BUY"  # По умолчанию покупка
                    )
                    
                    order_id = order_result.get("orderID") or order_result.get("order_id") or order_result.get("id")
                    
                    logger.info(f"Order placed successfully via CLOB API: order_id={order_id}, market_id={market_id}")
                    logger.info(f"CLOB API Response: {order_result}")
                    
                    # Увеличиваем счетчики ставок после успешного размещения
                    if market_id:
                        self._bets_per_market[market_id] = self._bets_per_market.get(market_id, 0) + 1
                        logger.info(f"Market {market_id} bets count: {self._bets_per_market[market_id]}")
                    if event_id:
                        self._bets_per_match[event_id] = self._bets_per_match.get(event_id, 0) + 1
                        logger.info(f"Event {event_id} bets count: {self._bets_per_match[event_id]}")
                    
                    # Сохраняем информацию для расчета профита
                    order_price = order_params.get("price", 0)
                    order_size = order_params.get("size", 0)
                    
                    result = {
                        "status": "success",
                        "order_id": order_id,
                        "market_id": market_id,
                        "token_id": token_id,
                        "order_price": order_price,  # Цена покупки
                        "order_size": order_size,    # Размер ставки
                        "order_result": order_result,
                        "profit": None,  # Будет рассчитан позже
                        "result_status": "pending"  # pending, win, loss, closed
                    }
                    # Сохраняем в хранилище
                    log_storage.add_bet(bet_data.dict(), result)
                    log_storage.add_api_log(
                        f"Order placed successfully via CLOB API: order_id={order_id}",
                        "SUCCESS",
                        {
                            "order_id": order_id,
                            "market_id": market_id,
                            "second_bookmaker": bet_data.second_bookmaker,
                            "price": order_params["price"],
                            "size": order_params["size"],
                            "clob_api_response": order_result
                        }
                    )
                    return result
                    
                except Exception as e:
                    error_details = str(e)
                    logger.error(f"Error placing order via CLOB API: {e}", exc_info=True)
                    result = {
                        "status": "error",
                        "reason": f"order_placement_failed: {error_details}",
                        "market_id": market_id,
                        "token_id": token_id,
                        "error_type": type(e).__name__
                    }
                    log_storage.add_bet(bet_data.dict(), result)
                    log_storage.add_api_log(
                        f"Order placement failed via CLOB API: {error_details}",
                        "ERROR",
                        {
                            "market_id": market_id,
                            "token_id": token_id,
                            "error": error_details,
                            "error_type": type(e).__name__,
                            "second_bookmaker": bet_data.second_bookmaker
                        }
                    )
                    return result
            else:
                # CLOB клиент не доступен - только информация о market
                logger.warning("CLOB client not available. Order not placed.")
                result = {
                    "status": "skipped",
                    "reason": "clob_client_not_available",
                    "market_id": market_id,
                    "token_id": token_id,
                    "market_info": {
                        "title": market_info.get("title"),
                        "question": market_info.get("question"),
                    },
                    "order_params": order_params,
                    "note": "Market found and token_id extracted, but CLOB client not available for order placement. Install py-clob-client and configure private key to place orders."
                }
                log_storage.add_bet(bet_data.dict(), result)
                log_storage.add_api_log(
                    f"Order skipped: CLOB client not available",
                    "WARNING",
                    {
                        "market_id": market_id,
                        "token_id": token_id,
                        "reason": "CLOB client not installed or not configured",
                        "note": "Install py-clob-client and configure private key"
                    }
                )
                return result
            
        except Exception as e:
            logger.error(f"Error processing bet: {e}", exc_info=True)
            return {"status": "error", "reason": str(e)}
    
    async def _find_market(self, bet_data: BetData, order_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Поиск соответствующего market в Polymarket по названиям команд"""
        try:
            import json as json_lib
            from app.services.logger_service import log_storage
            
            # Генерируем поисковый запрос для события
            search_query = self.mapper.generate_search_query(bet_data)
            home_team_raw = bet_data.homeTeam or ""
            away_team_raw = bet_data.awayTeam or ""
            
            # Извлекаем отдельные команды из строк (могут быть формата "Team1 ⇄ Team2")
            home_teams = self.mapper.extract_team_names(home_team_raw)
            away_teams = self.mapper.extract_team_names(away_team_raw)
            
            # Объединяем все уникальные команды в один список
            all_teams = list(set(home_teams + away_teams))
            
            logger.info(f"Searching for event: home='{home_team_raw}', away='{away_team_raw}'")
            logger.info(f"Extracted teams: {all_teams}")
            
            # 1. Ищем события по каждой команде отдельно
            # Команды могут быть поменяны местами в Polymarket, поэтому ищем по каждой
            events = []
            existing_ids = set()
            
            # Сначала пробуем поиск по полному запросу (более точный)
            if search_query:
                logger.info(f"Trying full search query first: '{search_query}'")
                events_query = await self.client.search_events(search_query, limit=30, max_pages=2)
                if events_query:
                    new_events = [e for e in events_query if e.get('id') not in existing_ids]
                    for e in new_events:
                        existing_ids.add(e.get('id'))
                    events.extend(new_events)
                    logger.info(f"Found {len(new_events)} events searching by full query: '{search_query}'")
            
            # Затем ищем по каждой команде отдельно (для случаев, когда полный запрос не сработал)
            for team in all_teams:
                if team and len(team) > 2:  # Пропускаем слишком короткие строки
                    logger.info(f"Searching by team: '{team}'")
                    team_events = await self.client.search_events(team, limit=30, max_pages=2)
                    if team_events:
                        # Добавляем только новые события (избегаем дубликатов)
                        new_events = [e for e in team_events if e.get('id') not in existing_ids]
                        for e in new_events:
                            existing_ids.add(e.get('id'))
                        events.extend(new_events)
                        logger.info(f"Found {len(new_events)} events searching by team: '{team}' (total unique: {len(events)})")
            
            # Если все еще пусто, пробуем поиск по отдельным словам из команд
            if not events and all_teams:
                logger.info("No events found, trying search by individual words from team names...")
                for team in all_teams:
                    if team:
                        # Разбиваем команду на слова и ищем по каждому значимому слову
                        words = [w.strip() for w in team.split() if len(w.strip()) > 3]  # Только слова длиннее 3 символов
                        for word in words[:3]:  # Максимум 3 слова на команду
                            logger.info(f"Trying search by word: '{word}'")
                            word_events = await self.client.search_events(word, limit=20, max_pages=1)
                            if word_events:
                                new_events = [e for e in word_events if e.get('id') not in existing_ids]
                                for e in new_events:
                                    existing_ids.add(e.get('id'))
                                events.extend(new_events)
                                logger.info(f"Found {len(new_events)} events searching by word: '{word}'")
                                if len(events) >= 10:  # Если нашли достаточно, прекращаем поиск
                                    break
                        if len(events) >= 10:
                            break
            
            if not events:
                logger.warning(f"No events found for teams: {all_teams}")
                log_storage.add_api_log(
                    f"Event search: no events found",
                    "WARNING",
                    {"search_query": search_query, "home_team": home_team_raw, "away_team": away_team_raw, "extracted_teams": all_teams}
                )
                return None
            
            logger.info(f"Found {len(events)} total events, filtering by teams...")
            
            # 2. Фильтруем события по всем командам (независимо от порядка)
            # Это важно, т.к. команды могут быть поменяны местами в Polymarket
            matching_event = None
            teams_lower = [t.lower().strip() for t in all_teams if t and len(t.strip()) > 0]
            
            logger.info(f"Filtering {len(events)} events by teams: {teams_lower}")
            
            # Сначала ищем точное совпадение всех команд
            for event in events:
                title = (event.get('title', '') or '').lower()
                description = (event.get('description', '') or '').lower()
                slug = (event.get('slug', '') or '').lower()
                event_text = f"{title} {description} {slug}"
                
                # Проверяем, что все команды присутствуют в событии (независимо от порядка)
                if len(teams_lower) > 0:
                    teams_found = sum(1 for team in teams_lower if team in event_text)
                    # Если найдены все команды - это наше событие
                    if teams_found == len(teams_lower):
                        matching_event = event
                        logger.info(f"✅ Found exact matching event (all {len(teams_lower)} teams present): {event.get('id')}, title: {event.get('title', '')[:60]}")
                        break
            
            # Если точного совпадения нет, пробуем частичное (хотя бы 50% команд)
            if not matching_event and len(teams_lower) > 1:
                logger.info("No exact match found, trying partial match (at least 50% of teams)...")
                min_teams_required = max(1, len(teams_lower) // 2)  # Хотя бы половина команд
                
                for event in events:
                    title = (event.get('title', '') or '').lower()
                    description = (event.get('description', '') or '').lower()
                    slug = (event.get('slug', '') or '').lower()
                    event_text = f"{title} {description} {slug}"
                    
                    teams_found = sum(1 for team in teams_lower if team in event_text)
                    if teams_found >= min_teams_required:
                        matching_event = event
                        logger.info(f"✅ Found partial matching event ({teams_found}/{len(teams_lower)} teams): {event.get('id')}, title: {event.get('title', '')[:60]}")
                        break
            
            if not matching_event:
                logger.warning(f"❌ No matching event found for {home_team_raw} vs {away_team_raw}")
                logger.warning(f"   Searched {len(events)} events, teams: {all_teams}")
                if events:
                    logger.warning(f"   Sample event titles: {[e.get('title', 'N/A')[:50] for e in events[:5]]}")
                log_storage.add_api_log(
                    f"Event search: no matching event for {home_team_raw} vs {away_team_raw}",
                    "WARNING",
                    {
                        "home_team": home_team_raw, 
                        "away_team": away_team_raw, 
                        "extracted_teams": all_teams,
                        "events_found": len(events),
                        "sample_events": [{"id": e.get('id'), "title": e.get('title', '')[:60]} for e in events[:5]] if events else []
                    }
                )
                return None
            
            event_id = matching_event.get('id')
            logger.info(f"Found matching event: {event_id}, title: {matching_event.get('title', '')[:60]}")
            
            # 3. Получаем markets для события
            # Сначала проверяем, есть ли markets уже в событии
            markets = matching_event.get('markets', [])
            
            if not markets:
                # Если markets нет в событии, запрашиваем отдельно
                logger.info(f"Markets not in event, fetching markets for event_id: {event_id}")
                markets = await self.client.get_event_markets(event_id)
            
            if not markets:
                logger.warning(f"No markets found for event {event_id}")
                log_storage.add_api_log(
                    f"Market search: no markets for event {event_id}",
                    "WARNING",
                    {"event_id": event_id, "event_title": matching_event.get('title', '')[:60]}
                )
                return None
            
            logger.info(f"Found {len(markets)} markets for event {event_id}")
            
            # Логируем примеры маркетов для отладки
            if markets:
                logger.info(f"Sample markets for event {event_id}:")
                for m in markets[:3]:
                    logger.info(f"  Market ID {m.get('id')}: title='{m.get('title', 'N/A')[:60]}', question='{m.get('question', 'N/A')[:60]}'")
            
            # 4. Фильтруем markets по типу, target и pivot
            market_type = bet_data.market
            target = bet_data.target
            pivot = bet_data.pivot
            
            logger.info(f"Filtering markets: market_type={market_type}, target={target}, pivot={pivot}, home_teams={home_teams}, away_teams={away_teams}")
            
            matching_market = self.client._filter_markets_by_type(
                markets=markets,
                market_type=market_type,
                target=target,
                pivot=pivot,
                home_teams=home_teams,
                away_teams=away_teams
            )
            
            if matching_market:
                market_id = matching_market.get('id')
                logger.info(f"Found matching market: id={market_id}, title={matching_market.get('title', 'N/A')}")
                logger.info(f"Market data before get_market_by_id: has clobTokenIds={bool(matching_market.get('clobTokenIds'))}, keys={list(matching_market.keys())[:10]}")
                
                # Получаем полные данные market через get_market_by_id, чтобы получить clobTokenIds
                # Markets из get_event_markets могут не содержать все поля
                try:
                    full_market_data = await self.client.get_market_by_id(market_id)
                    if full_market_data:
                        has_clob = bool(full_market_data.get('clobTokenIds'))
                        logger.info(f"✅ Retrieved full market data for {market_id}, includes clobTokenIds: {has_clob}")
                        logger.info(f"   Full market data keys count: {len(full_market_data.keys())}")
                        logger.info(f"   First 20 keys: {list(full_market_data.keys())[:20]}")
                        if has_clob:
                            clob_val = full_market_data.get('clobTokenIds')
                            logger.info(f"   clobTokenIds type: {type(clob_val).__name__}, value preview: {str(clob_val)[:200]}")
                        else:
                            logger.warning(f"   ⚠️ clobTokenIds NOT FOUND in full_market_data! All keys: {sorted(list(full_market_data.keys()))}")
                        matching_market = full_market_data
                    else:
                        logger.warning(f"⚠️ Could not retrieve full market data for {market_id}, using partial data")
                except Exception as e:
                    logger.error(f"❌ Error retrieving full market data for {market_id}: {e}", exc_info=True)
                    logger.warning(f"Using partial market data")
                
                # Добавляем event_id в market_info для использования в проверке лимитов
                matching_market["event_id"] = event_id
                
                log_storage.add_api_log(
                    f"Market found: {market_id}",
                    "SUCCESS",
                    {
                        "event_id": event_id,
                        "market_id": market_id,
                        "market_title": matching_market.get("title"),
                        "market_question": matching_market.get("question"),
                        "market_type": market_type,
                        "target": target,
                        "pivot": pivot
                    }
                )
                return matching_market
            else:
                logger.warning(f"❌ No matching market found for type={market_type}, target={target}, pivot={pivot}")
                logger.warning(f"   Event ID: {event_id}, Markets available: {len(markets)}")
                if markets:
                    logger.warning(f"   Sample market questions: {[m.get('question', m.get('title', 'N/A'))[:60] for m in markets[:5]]}")
                log_storage.add_api_log(
                    f"Market search: no matching market",
                    "WARNING",
                    {
                        "event_id": event_id,
                        "event_title": matching_event.get('title', '')[:60] if matching_event else None,
                        "market_type": market_type,
                        "target": target,
                        "pivot": pivot,
                        "markets_count": len(markets),
                        "sample_markets": [{"id": m.get('id'), "question": m.get('question', m.get('title', ''))[:60]} for m in markets[:5]] if markets else []
                    }
                )
                return None
            
        except Exception as e:
            logger.error(f"Error finding market: {e}", exc_info=True)
            from app.services.logger_service import log_storage
            log_storage.add_api_log(
                f"Market search error: {str(e)}",
                "ERROR",
                {
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None
    
    def _calculate_order_params(
        self, 
        bet_data: BetData, 
        order_data: Dict[str, Any],
        market_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Расчет параметров ордера"""
        # Размер ордера - используем настройки из settings_service
        settings_service = get_settings_service()
        size = settings_service.get_bet_amount()
        if bet_data.stake:
            try:
                size = float(bet_data.stake)
            except (ValueError, TypeError):
                pass
        
        # Извлекаем outcome из market данных
        outcome = self.mapper.extract_market_outcome(market_info, bet_data)
        
        # Получаем текущую цену на Polymarket и сравниваем с ценой из парсера
        current_price = self._get_current_price_from_market(market_info, outcome)
        parser_price = order_data["price"]  # Цена из коэффициента парсера
        
        # Проверяем, не изменился ли коэффициент (цена) на Polymarket
        if current_price is not None and parser_price is not None and bet_data.surebet_profit is not None:
            # Вычисляем коэффициент второй БК из surebet_profit
            # profit = (coef_second / coef_polymarket - 1) * 100
            # coef_second = coef_polymarket * (profit/100 + 1)
            parser_coef = 1.0 / parser_price if parser_price > 0 else 0
            coef_second_bk = parser_coef * (bet_data.surebet_profit / 100.0 + 1.0)
            
            # Получаем текущий коэффициент на Polymarket
            current_coef = 1.0 / current_price if current_price > 0 else 0
            
            # Пересчитываем profit с текущим коэффициентом
            if current_coef > 0:
                recalculated_profit = (coef_second_bk / current_coef - 1.0) * 100.0
                
                logger.info(f"Profit recalculation: parser_coef={parser_coef:.4f} (price={parser_price:.4f}), "
                          f"current_coef={current_coef:.4f} (price={current_price:.4f}), "
                          f"coef_second_bk={coef_second_bk:.4f}, "
                          f"original_profit={bet_data.surebet_profit:.2f}%, "
                          f"recalculated_profit={recalculated_profit:.2f}%")
                
                # Проверяем, что пересчитанный profit >= -0.5%
                if recalculated_profit < -0.5:
                    logger.warning(f"Recalculated profit {recalculated_profit:.2f}% < -0.5%, skipping bet")
                    raise ValueError(f"profit_too_low: recalculated_profit={recalculated_profit:.2f}%")
                else:
                    logger.info(f"Recalculated profit {recalculated_profit:.2f}% >= -0.5%, placing bet with current price")
            
            # Используем текущую цену для размещения ордера
            price = current_price
        else:
            # Если не удалось получить текущую цену или нет surebet_profit, используем цену из парсера
            price = parser_price
        
        # TODO: Добавить логику коррекции цены с учетом spread, комиссий и т.д.
        # TODO: Для размещения ордеров нужен CLOB API, не Gamma API
        
        return {
            "size": size,
            "price": price,
            "outcome": outcome
        }
    
    def _get_current_price_from_market(self, market_info: Dict[str, Any], outcome: Optional[str]) -> Optional[float]:
        """
        Получение текущей цены из market_info
        
        Args:
            market_info: Данные маркета
            outcome: Название outcome для которого нужно получить цену
            
        Returns:
            Текущая цена (0.01-0.99) или None
        """
        try:
            # Пытаемся получить outcomePrices
            outcome_prices = market_info.get('outcomePrices', [])
            outcomes = market_info.get('outcomes', [])
            
            # Если outcomePrices - строка JSON, парсим её
            if isinstance(outcome_prices, str):
                import json
                try:
                    outcome_prices = json.loads(outcome_prices)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"Could not parse outcomePrices as JSON: {outcome_prices}")
                    outcome_prices = []
            
            # Если outcomes - строка JSON, парсим её
            if isinstance(outcomes, str):
                import json
                try:
                    outcomes = json.loads(outcomes)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"Could not parse outcomes as JSON: {outcomes}")
                    outcomes = []
            
            # Ищем цену для нужного outcome
            if outcome and outcomes and outcome_prices:
                if len(outcomes) == len(outcome_prices):
                    try:
                        outcome_index = outcomes.index(outcome)
                        price_str = outcome_prices[outcome_index]
                        price = float(price_str)
                        logger.debug(f"Found current price for outcome '{outcome}': {price}")
                        return price
                    except (ValueError, IndexError, TypeError) as e:
                        logger.debug(f"Could not find price for outcome '{outcome}': {e}")
            
            # Если не нашли по outcome, берем первую доступную цену
            if outcome_prices and len(outcome_prices) > 0:
                try:
                    price_str = outcome_prices[0]
                    price = float(price_str)
                    logger.debug(f"Using first available price: {price}")
                    return price
                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse price: {e}")
            
            # Пытаемся найти цену в других полях
            price_fields = ['price', 'lastPrice', 'bestPrice', 'markPrice']
            for field in price_fields:
                if field in market_info:
                    try:
                        price = float(market_info[field])
                        logger.debug(f"Found price in field '{field}': {price}")
                        return price
                    except (ValueError, TypeError):
                        continue
            
            logger.debug("Could not find current price in market_info")
            return None
            
        except Exception as e:
            logger.warning(f"Error getting current price from market: {e}")
            return None
