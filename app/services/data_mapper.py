import logging
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
        
        # Убираем пустые строки
        return [t for t in teams if t]
    
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
        
        Returns:
            "YES", "NO", название outcome или индекс outcome
        """
        # Получаем outcomes из market
        outcomes = market_data.get("outcomes", [])
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
            
            # Извлекаем названия команд для сопоставления
            home_teams = self.extract_team_names(bet_data.homeTeam or "")
            away_teams = self.extract_team_names(bet_data.awayTeam or "")
            
            # Для 1X2
            if market_upper == "ONE_TWO":
                if target_upper in ["ONE", "HOME"]:
                    # Сначала пытаемся найти по названию команды (homeTeam)
                    # Проверяем как точное вхождение, так и частичное (фамилия в полном имени)
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями homeTeam
                            for team in home_teams:
                                if team:
                                    team_lower = team.lower()
                                    # Проверяем: outcome входит в team или team входит в outcome
                                    if outcome_lower in team_lower or team_lower in outcome_lower:
                                        # Всегда возвращаем название outcome, а не индекс
                                        return outcome
                            # Проверяем ключевые слова
                            if "home" in outcome_lower or "team 1" in outcome_lower or "team1" in outcome_lower:
                                return outcome
                    # Если не нашли, возвращаем первый outcome (обычно это первая команда/homeTeam)
                    if len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        # Всегда возвращаем название outcome, если это строка
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
                    # Сначала пытаемся найти по названию команды (awayTeam)
                    # Проверяем как точное вхождение, так и частичное (фамилия в полном имени)
                    for i, outcome in enumerate(outcomes):
                        if isinstance(outcome, str):
                            outcome_lower = outcome.lower()
                            # Проверяем совпадение с названиями awayTeam
                            for team in away_teams:
                                if team:
                                    team_lower = team.lower()
                                    # Проверяем: outcome входит в team или team входит в outcome
                                    if outcome_lower in team_lower or team_lower in outcome_lower:
                                        # Всегда возвращаем название outcome, а не индекс
                                        return outcome
                            # Проверяем ключевые слова
                            if "away" in outcome_lower or "team 2" in outcome_lower or "team2" in outcome_lower:
                                return outcome
                    # Если не нашли, возвращаем второй outcome (обычно это вторая команда/awayTeam)
                    if len(outcomes) > 1:
                        second_outcome = outcomes[1]
                        # Всегда возвращаем название outcome, если это строка
                        return second_outcome if isinstance(second_outcome, str) else "1"
                    elif len(outcomes) > 0:
                        # Если только один outcome, но target=TWO, возможно команды перепутаны местами
                        first_outcome = outcomes[0]
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
                    # Проверяем как точное вхождение, так и частичное (фамилия в полном имени)
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
                            if any(keyword in outcome_lower for keyword in ["home", "team 1", "team1", "+"]):
                                return outcome
                    # Если не нашли, возвращаем первый outcome (обычно это первая команда/homeTeam)
                    if len(outcomes) > 0:
                        first_outcome = outcomes[0]
                        return first_outcome if isinstance(first_outcome, str) else "0"
                    return "YES"  # Fallback
                elif target_upper in ["AWAY", "AH2"]:
                    # Сначала пытаемся найти по названию команды (awayTeam)
                    # Проверяем как точное вхождение, так и частичное (фамилия в полном имени)
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
                            if any(keyword in outcome_lower for keyword in ["away", "team 2", "team2", "-"]):
                                return outcome
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
