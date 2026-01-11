"""
Сервис для управления настройками ставок
"""
import json
import os
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).parent.parent.parent / "bet_settings.json"


class BetSettingsService:
    """Сервис для управления настройками ставок"""
    
    DEFAULT_SETTINGS = {
        "bet_amount": 2.0,  # Сумма ставки по умолчанию (в долларах)
        "max_bets_per_market": 1,  # Максимальное количество ставок на один маркет
        "max_bets_per_match": 3,  # Максимальное количество ставок на один матч
    }
    
    def __init__(self):
        self.settings = self._load_settings()
    
    def _load_settings(self) -> Dict[str, Any]:
        """Загрузка настроек из файла"""
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # Объединяем с дефолтными настройками (на случай, если добавились новые)
                    merged = self.DEFAULT_SETTINGS.copy()
                    merged.update(settings)
                    return merged
            else:
                # Создаем файл с дефолтными настройками
                self._save_settings(self.DEFAULT_SETTINGS)
                return self.DEFAULT_SETTINGS.copy()
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            return self.DEFAULT_SETTINGS.copy()
    
    def _save_settings(self, settings: Dict[str, Any]) -> None:
        """Сохранение настроек в файл"""
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
    
    def get_settings(self) -> Dict[str, Any]:
        """Получение всех настроек"""
        return self.settings.copy()
    
    def update_settings(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Обновление настроек"""
        # Валидация
        if "bet_amount" in new_settings:
            try:
                bet_amount = float(new_settings["bet_amount"])
                if bet_amount <= 0:
                    raise ValueError("bet_amount must be positive")
                self.settings["bet_amount"] = bet_amount
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid bet_amount: {e}")
        
        if "max_bets_per_market" in new_settings:
            try:
                max_bets = int(new_settings["max_bets_per_market"])
                if max_bets < 1:
                    raise ValueError("max_bets_per_market must be at least 1")
                self.settings["max_bets_per_market"] = max_bets
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid max_bets_per_market: {e}")
        
        if "max_bets_per_match" in new_settings:
            try:
                max_bets = int(new_settings["max_bets_per_match"])
                if max_bets < 1:
                    raise ValueError("max_bets_per_match must be at least 1")
                self.settings["max_bets_per_match"] = max_bets
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid max_bets_per_match: {e}")
        
        # Сохраняем
        self._save_settings(self.settings)
        logger.info(f"Settings updated: {self.settings}")
        return self.settings.copy()
    
    def get_bet_amount(self) -> float:
        """Получение суммы ставки"""
        return self.settings.get("bet_amount", self.DEFAULT_SETTINGS["bet_amount"])
    
    def get_max_bets_per_market(self) -> int:
        """Получение максимального количества ставок на маркет"""
        return self.settings.get("max_bets_per_market", self.DEFAULT_SETTINGS["max_bets_per_market"])
    
    def get_max_bets_per_match(self) -> int:
        """Получение максимального количества ставок на матч"""
        return self.settings.get("max_bets_per_match", self.DEFAULT_SETTINGS["max_bets_per_match"])


# Глобальный экземпляр сервиса
_settings_service = None

def get_settings_service() -> BetSettingsService:
    """Получение глобального экземпляра сервиса настроек"""
    global _settings_service
    if _settings_service is None:
        _settings_service = BetSettingsService()
    return _settings_service
