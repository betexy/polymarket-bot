from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager
import asyncio

from app.config.settings import Settings
from app.api import bets, dashboard
from app.dependencies import get_order_manager
from app.services.background_tasks import parse_events_periodically, check_bets_status_periodically, poll_bets_periodically, redeem_winnings_periodically
from app.services.bet_status_checker import BetStatusChecker
from app.services.bet_poller import BetPoller
from app.services.winnings_redeemer import WinningsRedeemer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройки
settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Polymarket Bot API Server...")
    logger.info(f"API will be available at http://{settings.api_host}:{settings.api_port}")
    
    # Получаем event_parser и clob_client из уже инициализированных клиентов
    from app.dependencies import _polymarket_client, _clob_client, get_order_manager
    
    # Запускаем периодический парсинг событий в фоне (раз в 3 часа)
    parsing_task = asyncio.create_task(
        parse_events_periodically(_polymarket_client.event_parser, interval_minutes=180)
    )
    
    # Первоначальный парсинг (не блокируем запуск сервера)
    # Парсим 30-40k событий (400 страниц), растягиваем на час
    asyncio.create_task(_polymarket_client.event_parser.parse_all_events(max_pages=400, target_duration_minutes=60))
    
    # Запускаем периодическую проверку статуса ставок (раз в час)
    bet_status_checker = None
    bet_status_task = None
    if _polymarket_client:
        bet_status_checker = BetStatusChecker(_polymarket_client)
        bet_status_task = asyncio.create_task(
            check_bets_status_periodically(bet_status_checker, interval_minutes=60)
        )
        logger.info("Bet status checking task started (every 1 hour)")
    else:
        logger.warning("Polymarket client not available, bet status checking will not run")
    
    # Запускаем автоматический redeem выигрышных позиций (раз в 5 минут)
    redeem_task = None
    winnings_redeemer = WinningsRedeemer(settings)
    redeem_task = asyncio.create_task(
        redeem_winnings_periodically(winnings_redeemer, interval_minutes=5)
    )
    logger.info("Winnings redeem task started (every 5 minutes)")

    # Запускаем получение ставок с парсера (раз в секунду)
    bet_poller_task = None
    try:
        from app.dependencies import _order_manager
        bet_poller = BetPoller(_order_manager, poll_url="http://bcp.bet/abb_pairs_pre_poly/")
        bet_poller_task = asyncio.create_task(
            poll_bets_periodically(bet_poller, interval_seconds=1.0)
        )
        logger.info("Bet polling task started (every 1 second)")
    except Exception as e:
        logger.warning(f"Could not start bet polling task: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Polymarket Bot API Server...")
    parsing_task.cancel()
    if bet_status_task:
        bet_status_task.cancel()
    if redeem_task:
        redeem_task.cancel()
    if bet_poller_task:
        bet_poller_task.cancel()
    try:
        await parsing_task
    except asyncio.CancelledError:
        pass
    if bet_status_task:
        try:
            await bet_status_task
        except asyncio.CancelledError:
            pass
    if redeem_task:
        try:
            await redeem_task
        except asyncio.CancelledError:
            pass
    if bet_poller_task:
        try:
            await bet_poller_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Polymarket Bot API",
    description="API для приема ставок от парсера и размещения ордеров на Polymarket",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (для разрешения запросов с других серверов)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency для передачи order_manager в роутеры импортируется из app.dependencies


# Подключение роутеров
app.include_router(bets.router)
app.include_router(dashboard.router)


@app.get("/")
async def root():
    return {
        "service": "Polymarket Bot API",
        "status": "running",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
