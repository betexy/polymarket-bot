from app.services.order_manager import OrderManager
from app.services.polymarket_client import PolymarketClient
from app.services.clob_client import PolymarketCLOBClient
from app.config.settings import Settings

# Глобальные объекты
_settings = Settings()
_polymarket_client = PolymarketClient(_settings)
_clob_client = PolymarketCLOBClient(_settings)
_order_manager = OrderManager(_polymarket_client, _clob_client, _settings)


def get_order_manager() -> OrderManager:
    return _order_manager
