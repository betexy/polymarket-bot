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
        # Счетчики ставок для контроля лимитов (загружаются из БД при старте)
        self._bets_per_market: Dict[str, int] = defaultdict(int)  # market_id -> count
        self._bets_per_match: Dict[str, int] = defaultdict(int)  # event_id -> count
        self._load_bet_counters_from_db()
    
    def _load_bet_counters_from_db(self):
        """Load bet counters from the bets DB so limits survive restarts."""
        try:
            import sqlite3
            db_path = "polymarket_bets.db"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Count successful bets per market_id
            cursor.execute(
                "SELECT market_id, COUNT(*) FROM bets WHERE status = 'success' AND market_id IS NOT NULL GROUP BY market_id"
            )
            for market_id, cnt in cursor.fetchall():
                self._bets_per_market[market_id] = cnt

            # Count successful bets per event_id (stored in result_json)
            cursor.execute(
                "SELECT result_json FROM bets WHERE status = 'success' AND result_json IS NOT NULL"
            )
            import json as _json
            for (result_json,) in cursor.fetchall():
                try:
                    result = _json.loads(result_json)
                    event_id = result.get("event_id")
                    if event_id:
                        self._bets_per_match[event_id] += 1
                except Exception:
                    pass

            conn.close()
            total_market = sum(self._bets_per_market.values())
            total_match = sum(self._bets_per_match.values())
            logger.info(f"Loaded bet counters from DB: {total_market} market entries, {total_match} match entries")
        except Exception as e:
            logger.warning(f"Could not load bet counters from DB: {e}")

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
                    # Пропускаем без логирования и без сохранения в историю
                    return {"status": "skipped", "reason": f"second_bookmaker_not_allowed: {bet_data.second_bookmaker}"}
            
            # Обработка знака ⇄ - команды нужно поменять местами
            # Формат: "Team1 ⇄ Team2" означает что реальный home = Team2, away = Team1
            if bet_data.homeTeam and '⇄' in bet_data.homeTeam:
                parts = bet_data.homeTeam.split('⇄')
                if len(parts) == 2:
                    original_home = bet_data.homeTeam
                    # Первая часть становится away, вторая - home
                    bet_data.homeTeam = parts[1].strip()
                    bet_data.awayTeam = parts[0].strip()
                    logger.info(f"⇄ Teams swapped: '{original_home}' -> home='{bet_data.homeTeam}', away='{bet_data.awayTeam}'")
            elif bet_data.awayTeam and '⇄' in bet_data.awayTeam:
                parts = bet_data.awayTeam.split('⇄')
                if len(parts) == 2:
                    original_away = bet_data.awayTeam
                    # Первая часть становится away, вторая - home
                    bet_data.homeTeam = parts[1].strip()
                    bet_data.awayTeam = parts[0].strip()
                    logger.info(f"⇄ Teams swapped: '{original_away}' -> home='{bet_data.homeTeam}', away='{bet_data.awayTeam}'")
            
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
                        "sport": bet_data.sport,
                        "search_query": order_data.get('search_query'),
                        "api_response": "No matching market found (checked main event and '- More Markets' event)"
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

            # Проверка на закрытый/неактивный маркет
            is_closed = market_info.get("closed", False)
            is_active = market_info.get("active", True)
            accepting_orders = market_info.get("acceptingOrders", True)

            if is_closed:
                logger.warning(f"Market {market_id} is closed (resolved), skipping bet")
                return {"status": "skipped", "reason": "market_closed"}

            if not is_active:
                logger.warning(f"Market {market_id} is not active, skipping bet")
                return {"status": "skipped", "reason": "market_not_active"}

            if not accepting_orders:
                logger.warning(f"Market {market_id} is not accepting orders, skipping bet")
                return {"status": "skipped", "reason": "market_not_accepting_orders"}

            # Проверка на существующую ставку в БД (защита от дубликатов)
            if market_id:
                existing_bet = self._check_existing_bet_in_db(market_id)
                if existing_bet:
                    logger.info(f"Skipping duplicate bet: already have bet on market {market_id}")
                    return {
                        "status": "skipped",
                        "reason": "duplicate_market",
                        "market_id": market_id,
                        "existing_bet_id": existing_bet
                    }
            
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
                if any(x in error_msg for x in ["profit_too_low", "price_dropped_too_much", "market_resolved", "no_liquidity"]):
                    logger.warning(f"Bet skipped: {error_msg}")
                    result = {"status": "skipped", "reason": error_msg}
                    log_storage.add_bet(bet_data.dict(), result)
                    
                    # Собираем детальную информацию для лога
                    log_data = {
                        "market_id": market_info.get('id'),
                        "original_profit": bet_data.surebet_profit,
                        "reason": error_msg
                    }
                    
                    # Добавляем детали расчета, если они доступны
                    try:
                        parser_price = order_data.get("price")
                        if parser_price:
                            parser_coef = 1.0 / parser_price if parser_price > 0 else None
                            log_data["parser_price"] = parser_price
                            log_data["parser_coef"] = parser_coef
                        
                        current_price = self._get_current_price_from_market(market_info, self.mapper.extract_market_outcome(market_info, bet_data))
                        if current_price:
                            current_coef = 1.0 / current_price if current_price > 0 else None
                            log_data["current_price"] = current_price
                            log_data["current_coef"] = current_coef
                            
                            # Рассчитываем recalculated_profit для логирования (правильная формула для вилки)
                            if bet_data.surebet_profit is not None and parser_coef and current_coef:
                                coef_second_bk = parser_coef * (bet_data.surebet_profit / 100.0 + 1.0)
                                total_price = 1.0 / coef_second_bk + 1.0 / current_coef
                                recalculated_profit = (1.0 / total_price - 1.0) * 100.0
                                log_data["coef_second_bk"] = coef_second_bk
                                log_data["recalculated_profit"] = round(recalculated_profit, 2)
                    except Exception as e:
                        logger.debug(f"Could not extract detailed price info for log: {e}")
                    
                    log_storage.add_api_log(
                        f"Bet skipped: {error_msg}",
                        "WARNING",
                        log_data
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
            
            # Функция для проверки совпадения outcome (без учёта регистра и с нормализацией)
            def outcome_matches(outcome_to_check, outcomes_list):
                if not outcome_to_check or not outcomes_list:
                    return False
                outcome_lower = outcome_to_check.lower().strip()
                for o in outcomes_list:
                    if isinstance(o, str) and o.lower().strip() == outcome_lower:
                        return True
                return False
            
            # Функция для получения правильного outcome из списка (с учётом регистра оригинала)
            def get_matching_outcome(outcome_to_check, outcomes_list):
                if not outcome_to_check or not outcomes_list:
                    return None
                outcome_lower = outcome_to_check.lower().strip()
                for o in outcomes_list:
                    if isinstance(o, str) and o.lower().strip() == outcome_lower:
                        return o  # Возвращаем оригинальное написание
                return None
            
            # Проверяем, правильно ли определен outcome
            # Если outcome = "YES" или "NO" (старые значения), или его нет в доступных outcomes, переизвлекаем
            if not outcome or outcome in ["YES", "NO"] or (available_outcomes and not outcome_matches(outcome, available_outcomes)):
                # Если outcome не был правильно определен, пробуем извлечь заново
                logger.info(f"Outcome '{outcome}' not valid, re-extracting from market. Available: {available_outcomes}")
                outcome = self.mapper.extract_market_outcome(market_info, bet_data)
                logger.info(f"Re-extracted outcome: {outcome}")
                
                # Находим точное написание outcome из списка
                if outcome and available_outcomes:
                    matched = get_matching_outcome(outcome, available_outcomes)
                    if matched:
                        outcome = matched
                        logger.info(f"Matched outcome to available: {outcome}")
                
                # Если outcome все еще не определен, логируем ошибку и ищем по названию команды
                if not outcome or (available_outcomes and not outcome_matches(outcome, available_outcomes)):
                    logger.error(f"❌ Could not determine correct outcome! outcome='{outcome}', available={available_outcomes}")
                    logger.error(f"   Target: {bet_data.target}, homeTeam: {bet_data.homeTeam}, awayTeam: {bet_data.awayTeam}")
                    
                    # Для ONE_TWO маркетов - ищем outcome по названию команды, НЕ по индексу!
                    # Порядок outcomes на Polymarket может не совпадать с порядком команд от парсера
                    if bet_data.market and bet_data.market.upper() == "ONE_TWO":
                        target_upper = bet_data.target.upper() if bet_data.target else ""
                        
                        # Определяем, какую команду нужно найти
                        if target_upper in ["ONE", "HOME"]:
                            team_to_find = bet_data.homeTeam
                        elif target_upper in ["TWO", "AWAY"]:
                            team_to_find = bet_data.awayTeam
                        else:
                            team_to_find = None
                        
                        if team_to_find and available_outcomes:
                            team_lower = team_to_find.lower().strip()
                            found_by_name = None

                            # Ищем outcome по названию команды — scoring-based подход
                            # Сначала проверяем точное подстрочное совпадение
                            for available_outcome in available_outcomes:
                                if isinstance(available_outcome, str):
                                    outcome_lower = available_outcome.lower().strip()
                                    if outcome_lower == team_lower:
                                        found_by_name = available_outcome
                                        break
                                    if outcome_lower in team_lower or team_lower in outcome_lower:
                                        found_by_name = available_outcome
                                        break

                            # Если подстрочное совпадение не найдено, используем scoring по словам
                            # Выбираем outcome с наибольшим количеством совпавших слов
                            if not found_by_name:
                                team_words = [w.strip() for w in team_lower.split() if len(w.strip()) > 2]
                                best_score = 0
                                best_outcome = None
                                for available_outcome in available_outcomes:
                                    if isinstance(available_outcome, str):
                                        outcome_lower = available_outcome.lower().strip()
                                        score = sum(1 for w in team_words if w in outcome_lower)
                                        if score > best_score:
                                            best_score = score
                                            best_outcome = available_outcome
                                # Требуем совпадение хотя бы 50% слов
                                if best_outcome and best_score >= max(1, len(team_words) // 2):
                                    found_by_name = best_outcome
                                    logger.warning(f"Found outcome by word scoring: '{found_by_name}' (score={best_score}/{len(team_words)}) for team '{team_to_find}'")

                            if found_by_name:
                                outcome = found_by_name
                                logger.warning(f"Found outcome by team name search: '{outcome}' for team '{team_to_find}'")
                            else:
                                logger.error(f"Cannot find outcome for team '{team_to_find}' in {available_outcomes}")
                                # Последний fallback - но с предупреждением
                                outcome = None
                        else:
                            logger.error(f"Cannot determine team for target={target_upper}")
                    else:
                        # Для других типов маркетов (TOTAL, HDP) - определяем outcome по target
                        target_upper = bet_data.target.upper() if bet_data.target else ""
                        market_upper = bet_data.market.upper() if bet_data.market else ""
                        
                        if market_upper in ["TOTAL", "T1_TOTAL", "T2_TOTAL"]:
                            # Для TOTAL маркетов: OVER = первый outcome, UNDER = второй outcome
                            if target_upper in ["UNDER", "TU"] and available_outcomes and len(available_outcomes) > 1:
                                outcome = available_outcomes[1] if isinstance(available_outcomes[1], str) else "Under"
                                logger.warning(f"Using second outcome for UNDER: {outcome}")
                            elif target_upper in ["OVER", "TO"] and available_outcomes and len(available_outcomes) > 0:
                                outcome = available_outcomes[0] if isinstance(available_outcomes[0], str) else "Over"
                                logger.warning(f"Using first outcome for OVER: {outcome}")
                            else:
                                # Fallback - ищем по ключевому слову
                                for o in available_outcomes:
                                    if isinstance(o, str):
                                        if target_upper in ["UNDER", "TU"] and "under" in o.lower():
                                            outcome = o
                                            break
                                        elif target_upper in ["OVER", "TO"] and "over" in o.lower():
                                            outcome = o
                                            break
                                if not outcome:
                                    logger.error(f"Cannot find outcome for TOTAL target={target_upper}")
                        elif market_upper in ["HDP", "EURO_HDP"]:
                            # Для HDP маркетов: HOME = первый outcome, AWAY = второй outcome
                            if target_upper in ["AWAY", "AH2"] and available_outcomes and len(available_outcomes) > 1:
                                outcome = available_outcomes[1] if isinstance(available_outcomes[1], str) else None
                                logger.warning(f"Using second outcome for HDP AWAY: {outcome}")
                            elif target_upper in ["HOME", "AH1"] and available_outcomes and len(available_outcomes) > 0:
                                outcome = available_outcomes[0] if isinstance(available_outcomes[0], str) else None
                                logger.warning(f"Using first outcome for HDP HOME: {outcome}")
                            else:
                                logger.error(f"Cannot find outcome for HDP target={target_upper}")
                        else:
                            # Для других маркетов - первый outcome
                            if available_outcomes and len(available_outcomes) > 0:
                                outcome = available_outcomes[0] if isinstance(available_outcomes[0], str) else "YES"
                                logger.warning(f"Using first available outcome as fallback: {outcome}")
                            else:
                                outcome = "YES"
                                logger.warning(f"No outcomes available, using 'YES' as fallback")
            
            logger.info(f"Final outcome: {outcome} for market {market_id}, available outcomes: {available_outcomes}")
            
            # КРИТИЧЕСКАЯ ПРОВЕРКА: если outcome не определён, не размещаем ставку!
            if not outcome:
                logger.error(f"❌ Cannot place bet: outcome is None/empty for market {market_id}")
                result = {
                    "status": "error",
                    "reason": "outcome_not_determined",
                    "market_id": market_id,
                    "available_outcomes": available_outcomes,
                    "target": bet_data.target,
                    "homeTeam": bet_data.homeTeam,
                    "awayTeam": bet_data.awayTeam
                }
                log_storage.add_bet(bet_data.dict(), result)
                log_storage.add_api_log(
                    f"Bet skipped: could not determine outcome for {bet_data.homeTeam} vs {bet_data.awayTeam}",
                    "ERROR",
                    result
                )
                return result
            
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
                    },
                    # Детали маркета Polymarket для отображения на дашборде
                    "polymarket_event": market_info.get("event_title") or market_info.get("title") or "N/A",
                    "polymarket_market": market_info.get("question") or market_info.get("title") or "N/A",
                    "selected_outcome": outcome,
                    "available_outcomes": available_outcomes
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
                
                # При использовании Proxy Wallet автоматическое обновление allowance не работает
                # Allowance должен быть установлен вручную через веб-интерфейс или скрипт
                if balance_check.get("needs_allowance_update", True) and not (hasattr(self.settings, 'polymarket_proxy_address') and self.settings.polymarket_proxy_address):
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
                
                # Проверяем Open orders на Polymarket — не ставим дубликат, если уже есть ордер по этому outcome (token_id)
                try:
                    open_orders = self.clob_client.get_orders()
                    if open_orders:
                        token_id_str = str(token_id)
                        for o in open_orders:
                            o_asset = str(o.get("asset_id") or o.get("token_id") or "")
                            if o_asset == token_id_str:
                                logger.info(f"Skipping: already have open order for this market/outcome (order_id={o.get('id', '')[:20]}...)")
                                return {
                                    "status": "skipped",
                                    "reason": "open_order_exists",
                                    "market_id": market_id,
                                    "existing_order_id": o.get("id"),
                                }
                except Exception as open_orders_err:
                    logger.warning(f"Could not check open orders (continuing): {open_orders_err}")
                
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
                    order_status_from_api = (order_result.get("status") or "").lower()
                    
                    logger.info(f"CLOB API Response: order_id={order_id}, status={order_status_from_api}, market_id={market_id}")
                    
                    # Если ордер не исполнен (live) — сразу отменяем и не сохраняем. Важна цена в моменте, не потом.
                    if order_status_from_api == "live":
                        logger.info(f"Order not filled (status=live), cancelling immediately: {order_id}")
                        try:
                            self.clob_client.cancel_order(order_id)
                            logger.info(f"Order cancelled: {order_id}")
                        except Exception as cancel_err:
                            logger.warning(f"Failed to cancel order {order_id}: {cancel_err}")
                        return {
                            "status": "skipped",
                            "reason": "order_not_filled_immediately",
                            "order_id": order_id,
                            "market_id": market_id,
                            "message": "Order was live (0 filled), cancelled — only placing at parser price in the moment.",
                        }
                    
                    # Только matched — сохраняем в БД и продолжаем
                    logger.info(f"Order placed successfully (matched): order_id={order_id}, market_id={market_id}")
                    
                    # Логируем сравнение цен для диагностики
                    parser_coef = float(bet_data.coef) if bet_data.coef else None
                    parser_price = 1.0 / parser_coef if parser_coef and parser_coef > 0 else None
                    used_price = order_params.get("price")
                    if parser_coef and parser_price:
                        logger.info(f"Price comparison: parser_coef={parser_coef:.4f}, parser_price={parser_price:.4f}, used_price={used_price:.4f}, diff={abs(parser_price - used_price):.4f}")
                    
                    logger.info(f"Order params used: price={order_params.get('price')}, size={order_params.get('size')}")
                    
                    # Изначально используем значения из order_params, но потом обновим реальными из API
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
                        "result_status": "pending",  # pending, win, loss, closed
                        # Детали маркета Polymarket для отображения на дашборде
                        "polymarket_event": market_info.get("event_title") or market_info.get("title") or "N/A",
                        "polymarket_market": market_info.get("question") or market_info.get("title") or "N/A",
                        "selected_outcome": outcome,
                        "available_outcomes": available_outcomes
                    }
                    # Сохраняем в хранилище только исполненные (matched) ордера
                    log_storage.add_bet(bet_data.dict(), result)
                    
                    # Проверяем статус заказа после создания
                    try:
                        import asyncio as _asyncio
                        # Задержка, чтобы заказ успел обработаться на блокчейне
                        await _asyncio.sleep(2.0)  # 2 секунды для обработки транзакции
                        order_info = self.clob_client.get_order(order_id)
                        order_status = order_info.get("status")
                        
                        logger.info(f"Order status check: status={order_status}")
                        logger.info(f"Order info from API: {order_info}")
                        
                        # Пытаемся получить реальные значения из order_info
                        # В Polymarket CLOB API могут быть поля: price, size, filled, avgFillPrice, etc.
                        real_price = order_info.get("avgFillPrice") or order_info.get("price") or order_info.get("avg_fill_price")
                        real_size = order_info.get("filled") or order_info.get("size_filled") or order_info.get("size")
                        
                        if real_price and real_size:
                            logger.info(f"Real order values from API: price={real_price}, size={real_size}")
                            # Обновляем значения для расчета профита
                            order_price = float(real_price)
                            order_size = float(real_size)
                            # Обновляем result с реальными значениями
                            result["order_price"] = order_price
                            result["order_size"] = order_size
                            # Обновляем в БД
                            log_storage._update_order_info_in_db(order_id, order_price, order_size)
                        else:
                            logger.warning(f"Could not extract real price/size from order_info. Using order_params values.")
                            logger.debug(f"Available order_info keys: {list(order_info.keys()) if isinstance(order_info, dict) else 'not a dict'}")
                        
                        # Если заказ недействителен (INVALID), удаляем из БД
                        if order_status == "INVALID":
                            logger.warning(f"Order {order_id} has INVALID status, removing from database")
                            log_storage._delete_bet_from_db(order_id)
                            # Обновляем статистику
                            with log_storage._lock:
                                log_storage.stats["successful_orders"] = max(0, log_storage.stats["successful_orders"] - 1)
                                log_storage.stats["total_bets"] = max(0, log_storage.stats["total_bets"] - 1)
                            
                            log_storage.add_api_log(
                                f"Order removed from database: status={order_status}",
                                "WARNING",
                                {
                                    "order_id": order_id,
                                    "status": order_status,
                                    "reason": "invalid_order_status"
                                }
                            )
                        else:
                            # Заказ валиден, увеличиваем счетчики
                            if market_id:
                                self._bets_per_market[market_id] = self._bets_per_market.get(market_id, 0) + 1
                                logger.info(f"Market {market_id} bets count: {self._bets_per_market[market_id]}")
                            if event_id:
                                self._bets_per_match[event_id] = self._bets_per_match.get(event_id, 0) + 1
                                logger.info(f"Event {event_id} bets count: {self._bets_per_match[event_id]}")
                    except Exception as status_check_error:
                        logger.warning(f"Could not check order status (non-critical): {status_check_error}")
                        # Не критичная ошибка, продолжаем
                        # Если не удалось проверить, считаем заказ валидным и увеличиваем счетчики
                        if market_id:
                            self._bets_per_market[market_id] = self._bets_per_market.get(market_id, 0) + 1
                        if event_id:
                            self._bets_per_match[event_id] = self._bets_per_match.get(event_id, 0) + 1
                    
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
    
    def _check_existing_bet_in_db(self, market_id: str) -> Optional[int]:
        """
        Проверяет есть ли уже успешная ставка на данный market в БД

        Args:
            market_id: ID маркета

        Returns:
            ID существующей ставки или None
        """
        try:
            import sqlite3

            db_path = "polymarket_bets.db"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id FROM bets WHERE status = 'success' AND market_id = ? LIMIT 1",
                (str(market_id),)
            )
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None

        except Exception as e:
            logger.warning(f"Error checking existing bet in DB: {e}")
            return None
    
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
            
            # ВАЖНО: ONE_DRAW (1X) и TWO_DRAW (X2) можно реализовать через Handicap +0.5
            # ONE_DRAW = HDP HOME +0.5, TWO_DRAW = HDP AWAY +0.5
            target_upper = target.upper() if target else ""
            is_double_chance = target_upper in ["ONE_DRAW", "TWO_DRAW", "1X", "X2"]
            
            logger.info(f"Filtering markets: market_type={market_type}, target={target}, pivot={pivot}, home_teams={home_teams}, away_teams={away_teams}")
            
            matching_market = self.client._filter_markets_by_type(
                markets=markets,
                market_type=market_type,
                target=target,
                pivot=pivot,
                home_teams=home_teams,
                away_teams=away_teams
            )
            
            # Если это ONE_DRAW/TWO_DRAW и маркет Double Chance не найден,
            # пробуем найти Handicap +0.5 (эквивалент Double Chance)
            if not matching_market and is_double_chance:
                logger.info(f"Double Chance market not found, trying Handicap +0.5 as alternative...")
                
                # ONE_DRAW (1X) = Handicap HOME +0.5
                # TWO_DRAW (X2) = Handicap AWAY +0.5
                if target_upper in ["ONE_DRAW", "1X"]:
                    hdp_target = "HOME"  # Ставим на домашнюю команду с гандикапом +0.5
                else:  # TWO_DRAW, X2
                    hdp_target = "AWAY"  # Ставим на гостевую команду с гандикапом +0.5
                
                matching_market = self.client._filter_markets_by_type(
                    markets=markets,
                    market_type="HDP",
                    target=hdp_target,
                    pivot="0.5",  # Именно +0.5, без минуса
                    home_teams=home_teams,
                    away_teams=away_teams
                )
                
                if matching_market:
                    logger.info(f"✅ Found Handicap +0.5 market as alternative for {target}")
                else:
                    # Также проверим в More Markets событии
                    logger.info(f"Handicap +0.5 not found in main event, will check More Markets...")
            
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
                
                # Добавляем event_id и event_title в market_info для использования в проверке лимитов и отображения
                matching_market["event_id"] = event_id
                matching_market["event_title"] = matching_event.get('title', '')  # Название события для дашборда
                
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
                # Маркет не найден в основном событии
                # Ищем в событии "- More Markets" (для всех типов маркетов)
                if True:  # Всегда пробуем искать в "- More Markets"
                    logger.info(f"Market not found in main event, searching for '- More Markets' event...")
                    
                    # Ищем событие с суффиксом "- More Markets"
                    more_markets_event = None
                    event_title = matching_event.get('title', '')
                    
                    for event in events:
                        e_title = event.get('title', '')
                        # Проверяем, что это событие "- More Markets" для того же матча
                        if "more markets" in e_title.lower() and event.get('id') != event_id:
                            # Проверяем, что все команды присутствуют
                            e_title_lower = e_title.lower()
                            teams_in_event = sum(1 for team in teams_lower if team in e_title_lower)
                            if teams_in_event >= len(teams_lower) // 2 or teams_in_event >= 1:
                                more_markets_event = event
                                logger.info(f"✅ Found '- More Markets' event: {event.get('id')}, title: {e_title[:80]}")
                                break
                    
                    # Если не нашли в уже полученных событиях, ищем отдельно
                    if not more_markets_event:
                        logger.info(f"Searching for 'More Markets' event separately...")
                        more_query = f"{event_title} More Markets"
                        more_events = await self.client.search_events(more_query, limit=10, max_pages=1)
                        
                        if more_events:
                            for event in more_events:
                                e_title = event.get('title', '')
                                if "more markets" in e_title.lower():
                                    e_title_lower = e_title.lower()
                                    teams_in_event = sum(1 for team in teams_lower if team in e_title_lower)
                                    if teams_in_event >= 1:
                                        more_markets_event = event
                                        logger.info(f"✅ Found '- More Markets' event via search: {event.get('id')}, title: {e_title[:80]}")
                                        break
                    
                    if more_markets_event:
                        more_event_id = more_markets_event.get('id')
                        more_markets = more_markets_event.get('markets', [])
                        
                        if not more_markets:
                            logger.info(f"Fetching markets for '- More Markets' event: {more_event_id}")
                            more_markets = await self.client.get_event_markets(more_event_id)
                        
                        if more_markets:
                            logger.info(f"Found {len(more_markets)} markets in '- More Markets' event")
                            for m in more_markets[:5]:
                                logger.info(f"  Market: {m.get('question', m.get('title', 'N/A'))[:70]}")
                            
                            # Фильтруем маркеты
                            matching_market = self.client._filter_markets_by_type(
                                markets=more_markets,
                                market_type=market_type,
                                target=target,
                                pivot=pivot,
                                home_teams=home_teams,
                                away_teams=away_teams
                            )
                            
                            # Если это ONE_DRAW/TWO_DRAW и не нашли, пробуем HDP +0.5
                            if not matching_market and is_double_chance:
                                logger.info(f"Double Chance not found in More Markets, trying HDP +0.5...")
                                if target_upper in ["ONE_DRAW", "1X"]:
                                    hdp_target = "HOME"
                                else:
                                    hdp_target = "AWAY"
                                
                                matching_market = self.client._filter_markets_by_type(
                                    markets=more_markets,
                                    market_type="HDP",
                                    target=hdp_target,
                                    pivot="0.5",
                                    home_teams=home_teams,
                                    away_teams=away_teams
                                )
                                if matching_market:
                                    logger.info(f"✅ Found HDP +0.5 in More Markets as alternative for {target}")
                            
                            if matching_market:
                                market_id = matching_market.get('id')
                                logger.info(f"✅ Found matching market in '- More Markets' event: id={market_id}")
                                
                                # Получаем полные данные market
                                try:
                                    full_market_data = await self.client.get_market_by_id(market_id)
                                    if full_market_data:
                                        matching_market = full_market_data
                                except Exception as e:
                                    logger.warning(f"Could not get full market data: {e}")
                                
                                matching_market["event_id"] = more_event_id
                                matching_market["event_title"] = more_markets_event.get('title', '')  # Название события для дашборда
                                
                                log_storage.add_api_log(
                                    f"Market found in '- More Markets': {market_id}",
                                    "SUCCESS",
                                    {
                                        "event_id": more_event_id,
                                        "market_id": market_id,
                                        "market_question": matching_market.get("question"),
                                        "market_type": market_type,
                                        "target": target,
                                        "pivot": pivot,
                                        "source": "More Markets event"
                                    }
                                )
                                return matching_market
                            else:
                                logger.warning(f"No matching market in '- More Markets' event either")
                
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
                        "sample_markets": [{"id": m.get('id'), "question": m.get('question', m.get('title', ''))[:60]} for m in markets[:5]] if markets else [],
                        "note": "Also checked '- More Markets' event"
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
        # Извлекаем outcome из market данных
        outcome = self.mapper.extract_market_outcome(market_info, bet_data)
        
        # Получаем текущую цену на Polymarket и сравниваем с ценой из парсера
        current_price = self._get_current_price_from_market(market_info, outcome)
        parser_price = order_data["price"]  # Цена из коэффициента парсера

        # Проверка на "невозможную" цену (маркет уже разрешён или без ликвидности)
        if current_price is not None:
            if current_price >= 0.99:
                logger.warning(f"Current price {current_price} >= 0.99 - market likely resolved or no liquidity")
                raise ValueError(f"market_resolved_or_no_liquidity: current_price={current_price:.4f} (price=1.0 means outcome already determined)")
            if current_price <= 0.01:
                logger.warning(f"Current price {current_price} <= 0.01 - market likely resolved (this outcome lost)")
                raise ValueError(f"market_resolved_outcome_lost: current_price={current_price:.4f} (price=0.0 means this outcome lost)")

        # Проверка: нельзя ставить ставку, если текущий кэф меньше парсеровского более чем на 0.03
        # Размещаем если current_coef >= parser_coef - 0.03
        # Не размещаем если current_coef < parser_coef - 0.03
        if current_price is not None and parser_price is not None and parser_price > 0:
            parser_coef = 1.0 / parser_price
            current_coef = 1.0 / current_price if current_price > 0 else 0
            
            if current_coef > 0:
                # Размещаем только если текущий кэф не меньше чем парсеровский минус 0.03
                min_allowed_coef = parser_coef - 0.03
                if current_coef < min_allowed_coef:
                    logger.warning(
                        f"Current coefficient too low: parser_coef={parser_coef:.4f} (price={parser_price:.4f}), "
                        f"current_coef={current_coef:.4f} (price={current_price:.4f}), "
                        f"min_allowed_coef={min_allowed_coef:.4f}, diff={parser_coef - current_coef:.4f} (>0.03)"
                    )
                    raise ValueError(
                        f"price_dropped_too_much: parser_coef={parser_coef:.4f}, "
                        f"current_coef={current_coef:.4f}, min_allowed={min_allowed_coef:.4f} "
                        f"(current_coef is {parser_coef - current_coef:.4f} less than parser_coef, >0.03)"
                    )
        
        # Проверяем, не изменился ли коэффициент (цена) на Polymarket
        if current_price is not None and parser_price is not None and bet_data.surebet_profit is not None:
            # Вычисляем коэффициент второй БК из surebet_profit
            # Для вилки: profit = (1 / (1/coef_second + 1/coef_polymarket) - 1) * 100
            # Откуда: 1/coef_second = (1 + profit/100) * 1/coef_polymarket - 1/coef_polymarket
            # Но проще: из исходной вилки знаем coef_second относительно parser_coef
            parser_coef = 1.0 / parser_price if parser_price > 0 else 0
            coef_second_bk = parser_coef * (bet_data.surebet_profit / 100.0 + 1.0)
            
            # Получаем текущий коэффициент на Polymarket
            current_coef = 1.0 / current_price if current_price > 0 else 0
            
            # Пересчитываем profit с текущим коэффициентом
            # Правильная формула для вилки (ставки на противоположные исходы):
            # profit = (1 / (1/coef_second + 1/coef_polymarket) - 1) * 100%
            if current_coef > 0 and coef_second_bk > 0:
                total_price = 1.0 / coef_second_bk + 1.0 / current_coef
                recalculated_profit = (1.0 / total_price - 1.0) * 100.0
                
                logger.info(f"Profit recalculation: parser_coef={parser_coef:.4f} (price={parser_price:.4f}), "
                          f"current_coef={current_coef:.4f} (price={current_price:.4f}), "
                          f"coef_second_bk={coef_second_bk:.4f}, "
                          f"original_profit={bet_data.surebet_profit:.2f}%, "
                          f"recalculated_profit={recalculated_profit:.2f}%")
                
                # Стандартная проверка прибыли
                if recalculated_profit < -5.0:
                    logger.warning(f"Recalculated profit {recalculated_profit:.2f}% < -5%, skipping bet (price changed too much)")
                    raise ValueError(f"profit_too_low: recalculated_profit={recalculated_profit:.2f}% (price changed significantly)")
                elif recalculated_profit < -0.5:
                    logger.warning(f"Recalculated profit {recalculated_profit:.2f}% < -0.5%, skipping bet")
                    raise ValueError(f"profit_too_low: recalculated_profit={recalculated_profit:.2f}%")
                else:
                    logger.info(f"Recalculated profit {recalculated_profit:.2f}% >= -0.5%, placing bet with current price")
            
            # Используем текущую цену для размещения ордера
            price = current_price
        else:
            # Если не удалось получить текущую цену или нет surebet_profit, используем цену из парсера
            price = parser_price
        
        # Рассчитываем size (количество токенов) из фиксированной суммы в USD
        # Настройка "Сумма ставки" - это сумма в USD, которую мы хотим поставить
        # size = сумма_в_USD / цена_токена
        settings_service = get_settings_service()
        bet_amount_usd = settings_service.get_bet_amount()  # Сумма ставки в USD из настроек
        
        MIN_SIZE_TOKENS = 5.0  # Минимальный размер ордера в токенах (требование Polymarket)
        
        if price and price > 0:
            # Рассчитываем количество токенов: size = bet_amount_usd / price
            size = bet_amount_usd / price
            
            # Проверяем минимальный размер ордера (Polymarket требует минимум 5 токенов)
            # Если size меньше минимума, используем минимальный размер
            if size < MIN_SIZE_TOKENS:
                min_required_usd = MIN_SIZE_TOKENS * price
                logger.info(f"Calculated size ({size:.2f}) is less than minimum ({MIN_SIZE_TOKENS}). Using minimum size: {MIN_SIZE_TOKENS} tokens (≈{min_required_usd:.2f} USD)")
                size = MIN_SIZE_TOKENS
        else:
            # Если цена не определена, используем bet_amount как fallback
            logger.warning(f"Price not available, using bet_amount as size: {bet_amount_usd}")
            size = bet_amount_usd
        
        # TODO: Добавить логику коррекции цены с учетом spread, комиссий и т.д.
        # TODO: Для размещения ордеров нужен CLOB API, не Gamma API
        
        return {
            "size": size,
            "price": price,
            "outcome": outcome
        }
    
    def _get_opposite_price_from_market(self, market_info: Dict[str, Any], current_outcome: Optional[str]) -> Optional[float]:
        """
        Получение противоположной цены из market_info
        
        Args:
            market_info: Данные маркета
            current_outcome: Текущий outcome, для которого нужно найти противоположный
            
        Returns:
            Противоположная цена (0.01-0.99) или None
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
            
            # Для binary markets (2 исхода) противоположный - это другой outcome
            if current_outcome and outcomes and outcome_prices and len(outcomes) == len(outcome_prices) == 2:
                try:
                    current_index = outcomes.index(current_outcome)
                    opposite_index = 1 - current_index  # Если current=0, то opposite=1, и наоборот
                    opposite_price_str = outcome_prices[opposite_index]
                    opposite_price = float(opposite_price_str)
                    logger.debug(f"Found opposite price for outcome '{current_outcome}': {opposite_price} (outcome: {outcomes[opposite_index]})")
                    return opposite_price
                except (ValueError, IndexError, TypeError):
                    pass
            
            # Альтернативный способ: если есть текущая цена, противоположная = 1 - current_price
            current_price = self._get_current_price_from_market(market_info, current_outcome)
            if current_price is not None and 0 < current_price < 1:
                opposite_price = 1.0 - current_price
                logger.debug(f"Calculated opposite price from current: {current_price} -> {opposite_price}")
                return opposite_price
            
            logger.debug("Could not find opposite price in market_info")
            return None
            
        except Exception as e:
            logger.warning(f"Error getting opposite price from market: {e}")
            return None
    
    def _get_opposite_outcome(self, market_info: Dict[str, Any], current_outcome: Optional[str]) -> Optional[str]:
        """
        Получение противоположного outcome из market_info
        
        Args:
            market_info: Данные маркета
            current_outcome: Текущий outcome, для которого нужно найти противоположный
            
        Returns:
            Противоположный outcome или None
        """
        try:
            outcomes = market_info.get('outcomes', [])
            
            # Если outcomes - строка JSON, парсим её
            if isinstance(outcomes, str):
                import json
                try:
                    outcomes = json.loads(outcomes)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"Could not parse outcomes as JSON: {outcomes}")
                    outcomes = []
            
            # Для binary markets (2 исхода) противоположный - это другой outcome
            if current_outcome and outcomes and len(outcomes) == 2:
                try:
                    current_index = outcomes.index(current_outcome)
                    opposite_index = 1 - current_index  # Если current=0, то opposite=1, и наоборот
                    opposite_outcome = outcomes[opposite_index]
                    logger.debug(f"Found opposite outcome for '{current_outcome}': '{opposite_outcome}'")
                    return opposite_outcome if isinstance(opposite_outcome, str) else str(opposite_outcome)
                except (ValueError, IndexError):
                    pass
            
            # Альтернативный способ: если текущий "YES", противоположный "NO" и наоборот
            if current_outcome:
                current_upper = str(current_outcome).upper()
                if current_upper == "YES":
                    return "NO"
                elif current_upper == "NO":
                    return "YES"
                # Если outcomes есть, но текущий не найден, возвращаем другой outcome
                if outcomes and len(outcomes) >= 2:
                    # Пробуем найти outcome, который не равен текущему
                    for outcome in outcomes:
                        if str(outcome).upper() != current_upper:
                            return outcome if isinstance(outcome, str) else str(outcome)
            
            logger.debug("Could not find opposite outcome in market_info")
            return None
            
        except Exception as e:
            logger.warning(f"Error getting opposite outcome from market: {e}")
            return None
    
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
