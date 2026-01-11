"""
Фоновые задачи для бота

Периодический парсинг событий Polymarket
"""
import logging
import asyncio
from app.services.event_parser import EventParser

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
