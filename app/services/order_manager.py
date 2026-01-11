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
                    logger.info(f"Bet skipped: second_bookmaker {bet_data.second_bookmaker} not in allowed list {allowed_bookmakers}")
                    result = {"status": "skipped", "reason": f"second_bookmaker_not_allowed: {bet_data.second_bookmaker}"}
                    log_storage.add_bet(bet_data.dict(), result)
                    log_storage.add_api_log(
                        f"Bet skipped: second_bookmaker {bet_data.second_bookmaker} not allowed",
                        "INFO",
                        {"second_bookmaker": bet_data.second_bookmaker, "allowed": allowed_bookmakers}
                    )
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
                logger.warning(f"Market not found for: {order_data['search_query']}")
                result = {"status": "error", "reason": "market_not_found", "search_query": order_data.get('search_query')}
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
            
            # Рассчет параметров ордера
            order_params = self._calculate_order_params(bet_data, order_data, market_info)
            
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
                    
                    result = {
                        "status": "success",
                        "order_id": order_id,
                        "market_id": market_id,
                        "token_id": token_id,
                        "order_result": order_result
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
            
            for team in all_teams:
                if team:
                    team_events = await self.client.search_events(team, limit=20, max_pages=1)
                    if team_events:
                        # Добавляем только новые события (избегаем дубликатов)
                        new_events = [e for e in team_events if e.get('id') not in existing_ids]
                        for e in new_events:
                            existing_ids.add(e.get('id'))
                        events.extend(new_events)
                        logger.info(f"Found {len(new_events)} events searching by team: {team}")
            
            # Если все еще пусто, пробуем по полному запросу
            if not events and search_query:
                events_query = await self.client.search_events(search_query, limit=20, max_pages=1)
                if events_query:
                    new_events = [e for e in events_query if e.get('id') not in existing_ids]
                    events.extend(new_events)
                    logger.info(f"Found {len(new_events)} events searching by full query: {search_query}")
            
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
            teams_lower = [t.lower() for t in all_teams if t]
            
            for event in events:
                title = (event.get('title', '') + ' ' + (event.get('description', '') or '')).lower()
                slug = (event.get('slug', '') or '').lower()
                event_text = f"{title} {slug}"
                
                # Проверяем, что все команды присутствуют в событии (независимо от порядка)
                if len(teams_lower) > 0:
                    teams_found = sum(1 for team in teams_lower if team in event_text)
                    # Если найдены все команды - это наше событие
                    if teams_found == len(teams_lower):
                        matching_event = event
                        logger.info(f"Found matching event (all {len(teams_lower)} teams present): {event.get('id')}")
                        break
            
            if not matching_event:
                logger.warning(f"No matching event found for {home_team_raw} vs {away_team_raw}")
                log_storage.add_api_log(
                    f"Event search: no matching event for {home_team_raw} vs {away_team_raw}",
                    "WARNING",
                    {"home_team": home_team_raw, "away_team": away_team_raw, "events_found": len(events)}
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
            
            # 4. Фильтруем markets по типу, target и pivot
            market_type = bet_data.market
            target = bet_data.target
            pivot = bet_data.pivot
            
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
                logger.warning(f"No matching market found for type={market_type}, target={target}, pivot={pivot}")
                log_storage.add_api_log(
                    f"Market search: no matching market",
                    "WARNING",
                    {
                        "event_id": event_id,
                        "market_type": market_type,
                        "target": target,
                        "pivot": pivot,
                        "markets_count": len(markets)
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
        
        # Цена из коэффициента
        price = order_data["price"]
        
        # Извлекаем outcome из market данных
        outcome = self.mapper.extract_market_outcome(market_info, bet_data)
        
        # TODO: Добавить логику коррекции цены с учетом spread, комиссий и т.д.
        # TODO: Для размещения ордеров нужен CLOB API, не Gamma API
        
        return {
            "size": size,
            "price": price,
            "outcome": outcome
        }
