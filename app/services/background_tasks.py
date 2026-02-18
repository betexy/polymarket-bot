"""
Фоновые задачи для бота

Периодический парсинг событий Polymarket
Периодическая проверка статуса ставок
Получение ставок с парсера через HTTP
"""
import logging
import asyncio
from app.services.event_parser import EventParser
from app.services.bet_status_checker import BetStatusChecker
from app.services.bet_poller import BetPoller
from app.services.winnings_redeemer import WinningsRedeemer

logger = logging.getLogger(__name__)


async def parse_events_periodically(event_parser: EventParser, interval_minutes: int = 180):
    """
    Периодически парсит события Polymarket
    
    Args:
        event_parser: Экземпляр EventParser
        interval_minutes: Интервал между парсингами (в минутах, по умолчанию 180 = 3 часа)
    """
    logger.info(f"Starting periodic event parsing (interval: {interval_minutes} minutes = {interval_minutes/60:.1f} hours)")
    
    while True:
        try:
            logger.info("Starting event parsing cycle...")
            # Парсим 30-40k событий (400 страниц), растягиваем на час
            result = await event_parser.parse_all_events(max_pages=400, target_duration_minutes=60)
            
            logger.info(
                f"Event parsing completed: {result['total_saved']} events saved, "
                f"total in DB: {result['total_events_in_db']}, "
                f"elapsed: {result['elapsed_seconds']:.1f}s"
            )
            
            # Ждем перед следующим циклом (3 часа)
            await asyncio.sleep(interval_minutes * 60)
            
        except Exception as e:
            logger.error(f"Error in periodic event parsing: {e}", exc_info=True)
            # В случае ошибки ждем 5 минут перед повтором
            await asyncio.sleep(5 * 60)


async def check_bets_status_periodically(bet_status_checker: BetStatusChecker, interval_minutes: int = 60):
    """
    Периодически проверяет статус ставок и рассчитывает профит
    
    Args:
        bet_status_checker: Экземпляр BetStatusChecker
        interval_minutes: Интервал между проверками (в минутах, по умолчанию 60 = 1 час)
    """
    logger.info(f"Starting periodic bet status checking (interval: {interval_minutes} minutes = {interval_minutes/60:.1f} hours)")
    
    while True:
        try:
            logger.info("Starting bet status check cycle...")
            result = await bet_status_checker.check_all_pending_bets_async()
            
            logger.info(
                f"Bet status check completed: checked={result.get('checked', 0)}, "
                f"updated={result.get('updated', 0)}, errors={result.get('errors', 0)}"
            )
            
            # Ждем перед следующим циклом (1 час)
            await asyncio.sleep(interval_minutes * 60)
            
        except Exception as e:
            logger.error(f"Error in periodic bet status checking: {e}", exc_info=True)
            # В случае ошибки ждем 5 минут перед повтором
            await asyncio.sleep(5 * 60)


async def redeem_winnings_periodically(winnings_redeemer: WinningsRedeemer, interval_minutes: int = 5):
    """
    Периодически выводит выигрышные позиции через Builder Relayer

    Args:
        winnings_redeemer: Экземпляр WinningsRedeemer
        interval_minutes: Интервал между проверками (в минутах, по умолчанию 5)
    """
    logger.info(f"Starting periodic winnings redeem (interval: {interval_minutes} minutes)")

    while True:
        try:
            result = await winnings_redeemer.redeem_all_winning_bets()

            if result.get("redeemed", 0) > 0 or result.get("errors", 0) > 0:
                logger.info(
                    f"Winnings redeem completed: redeemed={result.get('redeemed', 0)}, "
                    f"errors={result.get('errors', 0)}, total={result.get('total', 0)}"
                )

            await asyncio.sleep(interval_minutes * 60)

        except Exception as e:
            logger.error(f"Error in periodic winnings redeem: {e}", exc_info=True)
            await asyncio.sleep(5 * 60)


async def poll_bets_periodically(bet_poller: BetPoller, interval_seconds: float = 1.0):
    """
    Периодическое получение ставок с парсера
    
    Args:
        bet_poller: Экземпляр BetPoller
        interval_seconds: Интервал между запросами (в секундах, по умолчанию 1.0)
    """
    logger.info(f"Starting periodic bet polling from {bet_poller.poll_url} (interval: {interval_seconds} seconds)")
    
    while True:
        try:
            result = await bet_poller.poll_bets()
            
            if result.get("fetched", 0) > 0:
                logger.debug(
                    f"Bet polling completed: fetched={result.get('fetched', 0)}, "
                    f"processed={result.get('processed', 0)}, errors={result.get('errors', 0)}"
                )
            
            # Ждем перед следующим запросом (1 секунда)
            await asyncio.sleep(interval_seconds)
            
        except Exception as e:
            logger.error(f"Error in periodic bet polling: {e}", exc_info=True)
            # В случае ошибки ждем 1 секунду перед повтором
            await asyncio.sleep(1.0)
