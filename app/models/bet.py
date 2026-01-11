from typing import Optional
from pydantic import BaseModel


class BetData(BaseModel):
    """Модель данных ставки от парсера"""
    bookmaker: str
    second_bookmaker: Optional[str] = None
    market: str
    target: str
    pivot: Optional[str] = None
    timeValue: str
    homeTeam: str
    awayTeam: str
    league: str
    sport: str
    coef: str
    surebet_profit: Optional[float] = None
    mode: str  # LIVE или PREMATCH
    stake: Optional[str] = None
    direct_link: Optional[str] = None
    bk_event_native_id: Optional[str] = None
    other_bookmakers: Optional[str] = None
    initiator_bookmaker: Optional[str] = None
