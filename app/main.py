from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager
import asyncio

from app.config.settings import Settings
from app.api import bets, dashboard
from app.dependencies import get_order_manager
from app.services.background_tasks import parse_events_periodically

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
    
    # Получаем event_parser из уже инициализированного клиента
    from app.dependencies import _polymarket_client
    
    # Запускаем периодический парсинг событий в фоне (раз в 3 часа)
    parsing_task = asyncio.create_task(
        parse_events_periodically(_polymarket_client.event_parser, interval_minutes=180)
    )
    
    # Первоначальный парсинг (не блокируем запуск сервера)
    # Парсим 30-40k событий (400 страниц), растягиваем на час
    asyncio.create_task(_polymarket_client.event_parser.parse_all_events(max_pages=400, target_duration_minutes=60))
    
    yield
    
    # Shutdown
    logger.info("Shutting down Polymarket Bot API Server...")
    parsing_task.cancel()
    try:
        await parsing_task
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
