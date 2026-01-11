from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional
import logging
from app.models.bet import BetData
from app.services.order_manager import OrderManager
from app.dependencies import get_order_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bets", tags=["bets"])


@router.post("/", status_code=200)
async def receive_bet(
    bet_data: BetData,
    x_secret_key: Optional[str] = Header(None, alias="X-Secret-Key"),
    order_manager: OrderManager = Depends(get_order_manager)
):
    """
    Endpoint для приема ставок от парсера
    
    Парсер должен отправлять POST запрос на этот endpoint с данными ставки.
    Для защиты можно использовать X-Secret-Key заголовок.
    """
    try:
        logger.info(f"=== INCOMING BET REQUEST ===")
        logger.info(f"Bet data received: bookmaker={bet_data.bookmaker}, second_bookmaker={bet_data.second_bookmaker}")
        logger.info(f"Teams: {bet_data.homeTeam} vs {bet_data.awayTeam}")
        
        # Проверка secret key если настроен
        if order_manager.settings.api_secret_key:
            if x_secret_key != order_manager.settings.api_secret_key:
                logger.warning(f"Invalid secret key provided. Expected: {order_manager.settings.api_secret_key[:10]}..., Got: {x_secret_key[:10] if x_secret_key else 'None'}...")
                raise HTTPException(status_code=401, detail="Invalid secret key")
        
        logger.info(f"Secret key check passed. Processing bet...")
        
        # Логируем получение ставки
        from app.services.logger_service import log_storage
        log_storage.add_api_log(
            f"Received bet from parser: {bet_data.bookmaker} - {bet_data.homeTeam} vs {bet_data.awayTeam}",
            "INFO",
            {
                "bookmaker": bet_data.bookmaker,
                "second_bookmaker": bet_data.second_bookmaker,
                "homeTeam": bet_data.homeTeam,
                "awayTeam": bet_data.awayTeam,
                "market": bet_data.market,
                "coef": bet_data.coef
            }
        )
        
        # Обработка ставки
        result = await order_manager.process_bet(bet_data)
        
        return {
            "status": "received",
            "bet_processed": result.get("status") == "success",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error receiving bet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", status_code=200)
async def receive_bets_batch(
    bets_data: list[BetData],
    x_secret_key: Optional[str] = Header(None, alias="X-Secret-Key"),
    order_manager: OrderManager = Depends(get_order_manager)
):
    """
    Endpoint для приема нескольких ставок одновременно
    """
    try:
        # Проверка secret key если настроен
        if order_manager.settings.api_secret_key:
            if x_secret_key != order_manager.settings.api_secret_key:
                raise HTTPException(status_code=401, detail="Invalid secret key")
        
        logger.info(f"Received batch of {len(bets_data)} bets")
        
        results = []
        for bet_data in bets_data:
            try:
                result = await order_manager.process_bet(bet_data)
                results.append({
                    "bet": {
                        "bookmaker": bet_data.bookmaker,
                        "homeTeam": bet_data.homeTeam,
                        "awayTeam": bet_data.awayTeam,
                    },
                    "result": result
                })
            except Exception as e:
                logger.error(f"Error processing bet in batch: {e}")
                results.append({
                    "bet": {
                        "bookmaker": bet_data.bookmaker,
                        "homeTeam": bet_data.homeTeam,
                        "awayTeam": bet_data.awayTeam,
                    },
                    "result": {"status": "error", "reason": str(e)}
                })
        
        return {
            "status": "received",
            "total": len(bets_data),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error receiving bets batch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", status_code=200)
async def health_check():
    """Проверка работоспособности API"""
    return {"status": "ok", "service": "polymarket_bot"}
