import logging
import re
from typing import Optional, Dict, Any, List
from app.models.bet import BetData

logger = logging.getLogger(__name__)


class DataMapper:
    """Маппинг данных от парсера к формату Polymarket"""
    
    # Маппинг спортов
    SPORT_MAP = {
        "FOOTBALL": "soccer",
        "BASKETBALL": "basketball",
        "HOCKEY": "hockey",
        "TENNIS": "tennis",
        "VOLLEYBALL": "volleyball",
        "BASEBALL": "baseball",
        "CYBERSPORT": "esports",
    }
    
    # Маппинг рынков парсера на типы для поиска
    # Парсер использует: ONE_TWO, TOTAL, HDP, T1_TOTAL, T2_TOTAL
    # На Polymarket: ONE_TWO = Moneyline, HDP = Handicap/Spread
    MARKET_TYPE_MAP = {
        "ONE_TWO": "ONE_TWO",        # Moneyline на Polymarket (Match Winner)
        "TOTAL": "TOTAL",             # Over/Under
        "HDP": "HDP",                 # Handicap / Spread / Фора
        "EURO_HDP": "HDP",            # European Handicap (тоже Handicap)
        "T1_TOTAL": "T1_TOTAL",       # Individual Total Team 1
        "T2_TOTAL": "T2_TOTAL",       # Individual Total Team 2
    }
    
    # Маппинг target для ONE_TWO (1X2)
    ONE_TWO_TARGET_MAP = {
        "ONE": "HOME",      # Победа первой команды / домашней
        "TWO": "AWAY",      # Победа второй команды / гостевой
        "HOME": "HOME",
        "AWAY": "AWAY",
        "DRAW": "DRAW",     # Ничья (если поддерживается)
        "ONE_DRAW": "1X",   # Победа первой или ничья
        "TWO_DRAW": "X2",   # Победа второй или ничья
    }
    
    def map_sport(self, sport: str) -> Optional[str]:
        """Маппинг спорта из формата парсера в формат Polymarket"""
        return self.SPORT_MAP.get(sport.upper())
    
    def map_market_type(self, market: str) -> Optional[str]:
        """Маппинг типа рынка для поиска"""
        return self.MARKET_TYPE_MAP.get(market.upper())
    
    def coef_to_probability(self, coef: str) -> float:
        """Конвертация коэффициента в вероятность (0-1)"""
        try:
            coef_float = float(coef)
            if coef_float > 0:
                return 1.0 / coef_float
            return 0.5
        except (ValueError, TypeError):
            logger.warning(f"Invalid coef format: {coef}")
            return 0.5
    
    def coef_to_price(self, coef: str) -> float:
        """
        Конвертация коэффициента в цену для Polymarket
        
        Polymarket использует цены от 0.01 до 0.99 (или 1-99 центов)
        где 0.01 = 1% вероятность, 0.50 = 50% вероятность
        """
        probability = self.coef_to_probability(coef)
        # Ограничиваем диапазон 0.01 - 0.99
        price = max(0.01, min(0.99, probability))
        return round(price, 2)
    
    def extract_team_names(self, team_string: str) -> List[str]:
        """
        Извлекает названия команд из строки вида "Team1 ⇄ Team2" или просто "Team"
        Возвращает список названий команд
        
        Также очищает названия от указаний лиги типа "(NHL)", "(EPL)" и т.д.
        """
        if not team_string:
            return []
        
        # Разделяем по символу ⇄ (U+21C4 - двунаправленная стрелка) или ⇌ (U+21CC)
        # Также поддерживаем обычные варианты: ⇄, ⇌, vs, VS
        separators = ['⇄', '⇌', ' vs ', ' VS ']
        teams = [team_string]
        
        for sep in separators:
            if sep in team_string:
                teams = [t.strip() for t in team_string.split(sep)]
                break
        
        # Очищаем названия команд от указаний лиги: "Team (NHL)" -> "Team"
        import re
        cleaned_teams = []
        for team in teams:
            if team:
                # Убираем лигу в скобках в конце: "(NHL)", "(EPL)", "(NBA)" и т.д.
                cleaned = re.sub(r'\s*\([^)]+\)\s*$', '', team).strip()
                cleaned_teams.append(cleaned)
        
        # Убираем пустые строки
        return [t for t in cleaned_teams if t]
    
    def generate_search_query(self, bet_data: BetData) -> str:
        """
        Генерация поискового запроса для поиска event в Polymarket
        Используем точные названия команд
        """
        query_parts = []
        
        if bet_data.homeTeam and bet_data.awayTeam:
            # Основной формат: "Team1 vs Team2"
            query_parts.append(f"{bet_data.homeTeam} vs {bet_data.awayTeam}")
        elif bet_data.homeTeam:
            query_parts.append(bet_data.homeTeam)
        elif bet_data.awayTeam:
            query_parts.append(bet_data.awayTeam)
        
        # Лига может помочь в поиске, но сначала пробуем без неё
        # (так как названия команд должны быть достаточно уникальными)
        
        return " ".join(query_parts)
    
    def map_target_for_search(self, target: str, market: str) -> Optional[str]:
        """
        Маппинг target для поиска соответствующего market
        
        Returns:
            Строка для поиска в названии market или None
        """
        target_upper = target.upper()
        market_upper = market.upper()
        
        # Для 1X2 (ONE_TWO)
        if market_upper == "ONE_TWO":
            mapped = self.ONE_TWO_TARGET_MAP.get(target_upper)
            if mapped:
                return mapped
            return target_upper
        
        # Для TOTAL (Over/Under)
        if market_upper in ["TOTAL", "T1_TOTAL", "T2_TOTAL"]:
            if target_upper in ["OVER", "TO"]:
                return "OVER"
            elif target_upper in ["UNDER", "TU"]:
                return "UNDER"
            return target_upper
        
        # Для HDP (Handicap / Фора)
        if market_upper in ["HDP", "EURO_HDP"]:
            if target_upper in ["HOME", "AH1"]:
                return "HOME"
            elif target_upper in ["AWAY", "AH2"]:
                return "AWAY"
            return target_upper
        
        return target_upper
    
    def prepare_order_data(self, bet_data: BetData) -> Dict[str, Any]:
        """Подготовка данных для размещения ордера"""
        return {
            "home_team": bet_data.homeTeam,
            "away_team": bet_data.awayTeam,
            "league": bet_data.league,
            "sport": self.map_sport(bet_data.sport),
            "market_type": bet_data.market,  # ONE_TWO, TOTAL, HDP, etc.
            "target": bet_data.target,
            "target_for_search": self.map_target_for_search(bet_data.target, bet_data.market),
            "pivot": bet_data.pivot,
            "time_value": bet_data.timeValue,
            "mode": bet_data.mode,
            "coef": bet_data.coef,
            "price": self.coef_to_price(bet_data.coef),
        }
    
    def extract_market_outcome(self, market_data: Dict[str, Any], bet_data: BetData) -> Optional[str]:
        """
        Извлечение outcome (YES/NO/название/индекс) из market данных
        
        Для binary markets Polymarket использует outcomes типа "Yes" или "No"
        или может быть массив outcomes с индексами или названиями команд
        
        ВАЖНО: target="ONE" означает первую команду в данных парсера (homeTeam),
               target="TWO" означает вторую команду в данных парсера (awayTeam).
        
        Returns:
            "YES", "NO", название outcome или индекс outcome
        """
        # Получаем outcomes из market
        outcomes = market_data.get("outcomes", [])

        # Если outcomes - JSON строка, парсим её
        if isinstance(outcomes, str):
            try:
                import json as _json
                outcomes = _json.loads(outcomes)
            except (ValueError, TypeError):
                logger.warning(f"Could not parse outcomes as JSON: {outcomes}")
                outcomes = []

        if not outcomes:
            # Может быть другой формат
            outcomes = market_data.get("tokens", [])

        if not outcomes:
            logger.warning("No outcomes found in market data")
            return "YES"  # По умолчанию

        # Если outcomes - массив строк
        if isinstance(outcomes, list) and len(outcomes) > 0:
            # Пытаемся найти соответствующий outcome по target
            target_upper = bet_data.target.upper()
            market_upper = bet_data.market.upper()
            
            # ИСПРАВЛЕНИЕ: Извлекаем названия команд ПРАВИЛЬНО
            # homeTeam - это ПЕРВАЯ команда (для target=ONE)
            # awayTeam - это ВТОРАЯ команда (для target=TWO)
            # Если в homeTeam/awayTeam передаётся "Team1 ⇄ Team2", берём ПЕРВУЮ команду из homeTeam
            # и ПЕРВУЮ команду из awayTeam (которая должна быть второй командой матча)
            
            home_teams_raw = self.extract_team_names(bet_data.homeTeam or "")
            away_teams_raw = self.extract_team_names(bet_data.awayTeam or "")
            
            # Для target=ONE нужна ПЕРВАЯ команда (из homeTeam)
            # Для target=TWO нужна ВТОРАЯ команда (из awayTeam)
            # Берём только первый элемент из каждого списка, чтобы избежать дублирования
            home_teams = [home_teams_raw[0]] if home_teams_raw else []
            away_teams = [away_teams_raw[0]] if away_teams_raw else []
            
            logger.info(f"extract_market_outcome: target={target_upper}, market={market_upper}")
            logger.info(f"  homeTeam raw: '{bet_data.homeTeam}' -> home_teams: {home_teams}")
            logger.info(f"  awayTeam raw: '{bet_data.awayTeam}' -> away_teams: {away_teams}")
            logger.info(f"  outcomes from Polymarket: {outcomes}")
            
            # Для 1X2, ONE_DRAW, TWO_DRAW
            if market_upper in ["ONE_TWO", "ONE_DRAW", "TWO_DRAW"]:
                # Для ONE_DRAW (1X) - выбираем outcome для первой команды (ONE)
                if target_upper in ["ONE_DRAW", "1X", "1 X"] or (market_upper == "ONE_DRAW" and target_upper in ["ONE", "HOME"]):
                    # Ищем outcome для первой команды
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями homeTeam
                            for team in home_teams:
                                if team:
                                    team_lower = team.lower()
                                    # Проверяем: outcome входит в team или team входит в outcome
                                    if outcome_lower in team_lower or team_lower in outcome_lower:
                                        return outcome
                            # Проверяем ключевые слова
                            if "home" in outcome_lower or "team 1" in outcome_lower or "team1" in outcome_lower:
                                return outcome
                    # Если не нашли, возвращаем первый outcome
                    if len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "0"
                    return "YES"  # Fallback
                
                # Для TWO_DRAW (X2) - выбираем outcome для второй команды (TWO)
                elif target_upper in ["TWO_DRAW", "X2", "X 2"] or (market_upper == "TWO_DRAW" and target_upper in ["TWO", "AWAY"]):
                    # Ищем outcome для второй команды
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями awayTeam
                            for team in away_teams:
                                if team:
                                    team_lower = team.lower()
                                    # Проверяем: outcome входит в team или team входит в outcome
                                    if outcome_lower in team_lower or team_lower in outcome_lower:
                                        return outcome
                            # Проверяем ключевые слова
                            if "away" in outcome_lower or "team 2" in outcome_lower or "team2" in outcome_lower:
                                return outcome
                    # Если не нашли, возвращаем второй outcome (или первый, если только один)
                    if len(outcomes) > 1:
                        second_outcome = outcomes[1]
                        return second_outcome if isinstance(second_outcome, str) else "1"
                    elif len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "1"
                    return "NO"  # Fallback
                
                # Fallback: если market_upper == "TWO_DRAW" но target не TWO_DRAW/X2, выбираем второй outcome
                elif market_upper == "TWO_DRAW":
                    # Для TWO_DRAW всегда выбираем outcome для второй команды
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями awayTeam
                            for team in away_teams:
                                if team:
                                    team_lower = team.lower()
                                    if outcome_lower in team_lower or team_lower in outcome_lower:
                                        return outcome
                            # Проверяем ключевые слова
                            if "away" in outcome_lower or "team 2" in outcome_lower or "team2" in outcome_lower:
                                return outcome
                    # Если не нашли, возвращаем второй outcome (или первый, если только один)
                    if len(outcomes) > 1:
                        second_outcome = outcomes[1]
                        return second_outcome if isinstance(second_outcome, str) else "1"
                    elif len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "1"
                    return "NO"  # Fallback
                
                # Fallback: если market_upper == "ONE_DRAW" но target не ONE_DRAW/1X, выбираем первый outcome
                elif market_upper == "ONE_DRAW":
                    # Для ONE_DRAW всегда выбираем outcome для первой команды
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями homeTeam
                            for team in home_teams:
                                if team:
                                    team_lower = team.lower()
                                    if outcome_lower in team_lower or team_lower in outcome_lower:
                                        return outcome
                            # Проверяем ключевые слова
                            if "home" in outcome_lower or "team 1" in outcome_lower or "team1" in outcome_lower:
                                return outcome
                    # Если не нашли, возвращаем первый outcome
                    if len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "0"
                    return "YES"  # Fallback
                
                # Для обычных ONE_TWO маркетов
                elif market_upper == "ONE_TWO":
                    if target_upper in ["ONE", "HOME"]:
                        # Для target=ONE нужно найти outcome для ПЕРВОЙ команды (homeTeam)
                        logger.info(f"  Looking for outcome for target=ONE, home_teams={home_teams}")
                        
                        found_outcome = None
                        for i, outcome in enumerate(outcomes):
                            if isinstance(outcome, str):
                                outcome_lower = outcome.lower()
                                # Проверяем совпадение с названиями homeTeam
                                for team in home_teams:
                                    if team:
                                        team_lower = team.lower()
                                        # Проверяем: outcome входит в team или team входит в outcome
                                        if outcome_lower in team_lower or team_lower in outcome_lower:
                                            logger.info(f"  ✅ Found match: outcome='{outcome}' matches team='{team}'")
                                            found_outcome = outcome
                                            break
                                if found_outcome:
                                    break
                                # Проверяем ключевые слова
                                if "home" in outcome_lower or "team 1" in outcome_lower or "team1" in outcome_lower:
                                    logger.info(f"  ✅ Found match by keyword: outcome='{outcome}'")
                                    found_outcome = outcome
                                    break
                        
                        if found_outcome:
                            logger.info(f"  → Returning outcome: '{found_outcome}'")
                            return found_outcome
                        
                        # Если не нашли, возвращаем первый outcome (обычно это первая команда/homeTeam)
                        if len(outcomes) > 0:
                            first_outcome = outcomes[0]
                            logger.warning(f"  ⚠️ No match found, using fallback: first outcome='{first_outcome}'")
                            return first_outcome if isinstance(first_outcome, str) else "0"
                        return "YES"  # Fallback
                    
                    elif target_upper in ["DRAW", "X"]:
                        # Ищем outcome с "Draw", "Tie", "X" в названии
                        for i, outcome in enumerate(outcomes):
                            if isinstance(outcome, str):
                                outcome_lower = outcome.lower()
                                if any(keyword in outcome_lower for keyword in ["draw", "tie", "x"]):
                                    return outcome
                        # Если не нашли, возвращаем "X" или последний outcome
                        return "X" if "X" in str(outcomes) else (outcomes[-1] if len(outcomes) > 0 and isinstance(outcomes[-1], str) else "X")
                        
                    elif target_upper in ["TWO", "AWAY"]:
                        # Для target=TWO нужно найти outcome для ВТОРОЙ команды (awayTeam)
                        # ВАЖНО: away_teams содержит только первую команду из awayTeam (см. исправление выше)
                        logger.info(f"  Looking for outcome for target=TWO, away_teams={away_teams}")
                        
                        found_outcome = None
                        for i, outcome in enumerate(outcomes):
                            if isinstance(outcome, str):
                                outcome_lower = outcome.lower()
                                # Проверяем совпадение с названиями awayTeam
                                for team in away_teams:
                                    if team:
                                        team_lower = team.lower()
                                        # Проверяем: outcome входит в team или team входит в outcome
                                        if outcome_lower in team_lower or team_lower in outcome_lower:
                                            logger.info(f"  ✅ Found match: outcome='{outcome}' matches team='{team}'")
                                            found_outcome = outcome
                                            break
                                if found_outcome:
                                    break
                                # Проверяем ключевые слова
                                if "away" in outcome_lower or "team 2" in outcome_lower or "team2" in outcome_lower:
                                    logger.info(f"  ✅ Found match by keyword: outcome='{outcome}'")
                                    found_outcome = outcome
                                    break
                        
                        if found_outcome:
                            logger.info(f"  → Returning outcome: '{found_outcome}'")
                            return found_outcome
                        
                        # Если не нашли, возвращаем второй outcome (обычно это вторая команда/awayTeam)
                        if len(outcomes) > 1:
                            second_outcome = outcomes[1]
                            logger.warning(f"  ⚠️ No match found, using fallback: second outcome='{second_outcome}'")
                            return second_outcome if isinstance(second_outcome, str) else "1"
                        elif len(outcomes) > 0:
                            # Если только один outcome, но target=TWO, возможно команды перепутаны местами
                            first_outcome = outcomes[0]
                            logger.warning(f"  ⚠️ Only one outcome, using: '{first_outcome}'")
                            return first_outcome if isinstance(first_outcome, str) else "1"
                        return "NO"  # Fallback
            
            # Для TOTAL
            elif market_upper in ["TOTAL", "T1_TOTAL", "T2_TOTAL"]:
                if target_upper in ["OVER", "TO"]:
                    # Ищем outcome с "Over" в названии
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            if "over" in outcome_lower:
                                # Возвращаем название outcome, а не индекс или YES
                                return outcome
                    # Если не нашли "over", но есть outcomes, возвращаем первый (обычно это Over)
                    if len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "0"
                    return "YES"  # Fallback
                elif target_upper in ["UNDER", "TU"]:
                    # Ищем outcome с "Under" в названии
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            if "under" in outcome_lower:
                                # Возвращаем название outcome, а не индекс или NO
                                return outcome
                    # Если не нашли "under", но есть outcomes, возвращаем второй (обычно это Under)
                    if len(outcomes) > 1:
                        second_outcome = outcomes[1]
                        return second_outcome if isinstance(second_outcome, str) else "1"
                    elif len(outcomes) > 0:
                        # Если только один outcome, проверяем, это ли Under
                        first_outcome = outcomes[0]
                        if isinstance(first_outcome, str) and "under" in first_outcome.lower():
                            return first_outcome
                    return "NO"  # Fallback
            
            # Для HDP
            elif market_upper in ["HDP", "EURO_HDP"]:
                if target_upper in ["HOME", "AH1"]:
                    # Сначала пытаемся найти по названию команды (homeTeam)
                    # Улучшенная логика: проверяем более точные совпадения
                    best_match = None
                    best_match_score = 0
                    
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями homeTeam
                            for team in home_teams:
                                if team:
                                    team_lower = team.lower()
                                    # Извлекаем отдельные слова из названия команды (разделенные ⇄, vs, и т.д.)
                                    team_words = re.split(r'[⇄\s]+|vs\.?|v\.?', team_lower)
                                    team_words = [w.strip() for w in team_words if w.strip()]
                                    
                                    # Проверяем точное совпадение
                                    if outcome_lower == team_lower:
                                        return outcome  # Точное совпадение - возвращаем сразу
                                    
                                    # Проверяем, входит ли outcome в слова команды
                                    if outcome_lower in team_words or any(outcome_lower == word for word in team_words):
                                        # Оценка качества совпадения (точное слово важнее частичного)
                                        score = 2 if outcome_lower in team_words else 1
                                        if score > best_match_score:
                                            best_match = outcome
                                            best_match_score = score
                                    
                                    # Проверяем частичное совпадение (только если нет лучших совпадений)
                                    if best_match_score < 2:
                                        if outcome_lower in team_lower:
                                            # Но только если outcome не слишком короткий (минимум 4 символа)
                                            if len(outcome_lower) >= 4:
                                                score = 0.5
                                                if score > best_match_score:
                                                    best_match = outcome
                                                    best_match_score = score
                            
                            # Проверяем ключевые слова
                            if any(keyword in outcome_lower for keyword in ["home", "team 1", "team1", "+"]):
                                return outcome
                    
                    # Если нашли лучшее совпадение, возвращаем его
                    if best_match:
                        return best_match
                    
                    # Если не нашли, возвращаем первый outcome (обычно это первая команда/homeTeam)
                    if len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "0"
                    return "YES"  # Fallback
                elif target_upper in ["AWAY", "AH2"]:
                    # Сначала пытаемся найти по названию команды (awayTeam)
                    # Проверяем как точное вхождение, так и частичное (фамилия в полном имени)
                    # Улучшенная логика: проверяем более точные совпадения
                    best_match = None
                    best_match_score = 0
                    
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями awayTeam
                            for team in away_teams:
                                if team:
                                    team_lower = team.lower()
                                    # Извлекаем отдельные слова из названия команды (разделенные ⇄, vs, и т.д.)
                                    team_words = re.split(r'[⇄\s]+|vs\.?|v\.?', team_lower)
                                    team_words = [w.strip() for w in team_words if w.strip()]
                                    
                                    # Проверяем точное совпадение
                                    if outcome_lower == team_lower:
                                        return outcome  # Точное совпадение - возвращаем сразу
                                    
                                    # Проверяем, входит ли outcome в слова команды
                                    if outcome_lower in team_words:
                                        # Для AWAY: приоритет первому слову в away_team (обычно это AWAY команда)
                                        # Но также учитываем позицию в outcomes - для AWAY это обычно индекс 1
                                        if len(team_words) >= 2 and outcome_lower == team_words[0]:
                                            score = 3  # Первое слово в away_team - максимальный приоритет
                                        elif len(team_words) >= 2 and outcome_lower == team_words[-1]:
                                            score = 2  # Последнее слово - средний приоритет
                                        else:
                                            score = 2  # Обычное совпадение
                                        
                                        # Также приоритет индексу 1 (AWAY обычно второй)
                                        if score == best_match_score and i == 1:
                                            score = score + 0.1  # Небольшой бонус для индекса 1
                                        
                                        if score > best_match_score:
                                            best_match = outcome
                                            best_match_score = score
                                    elif any(outcome_lower == word for word in team_words):
                                        score = 1
                                        if score > best_match_score:
                                            best_match = outcome
                                            best_match_score = score
                                    
                                    # Проверяем частичное совпадение (только если нет лучших совпадений)
                                    if best_match_score < 2:
                                        if outcome_lower in team_lower:
                                            # Но только если outcome не слишком короткий (минимум 4 символа)
                                            if len(outcome_lower) >= 4:
                                                score = 0.5
                                                if score > best_match_score:
                                                    best_match = outcome
                                                    best_match_score = score
                            
                            # Проверяем ключевые слова
                            if any(keyword in outcome_lower for keyword in ["away", "team 2", "team2", "-"]):
                                return outcome
                    
                    # Если нашли лучшее совпадение, возвращаем его
                    if best_match:
                        return best_match
                    
                    # Если не нашли, возвращаем второй outcome (обычно это вторая команда/awayTeam)
                    if len(outcomes) > 1:
                        second_outcome = outcomes[1]
                        return second_outcome if isinstance(second_outcome, str) else "1"
                    elif len(outcomes) > 0:
                        # Если только один outcome, возможно команды перепутаны местами
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "1"
                    return "NO"  # Fallback
        
        # По умолчанию возвращаем первый outcome
        if isinstance(outcomes, list) and len(outcomes) > 0:
            first_outcome = outcomes[0]
            if isinstance(first_outcome, str):
                return first_outcome if not first_outcome.isdigit() else "0"
            return "0"
        return "YES"
