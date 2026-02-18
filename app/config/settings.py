from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Polymarket Gamma API настройки (для получения данных о markets)
    polymarket_api_key: Optional[str] = None
    polymarket_api_secret: Optional[str] = None
    polymarket_api_passphrase: Optional[str] = None
    polymarket_gamma_api_url: str = "https://gamma-api.polymarket.com"
    
    # Polymarket CLOB API настройки (для размещения ордеров)
    polymarket_clob_host: str = "https://clob.polymarket.com"
    polymarket_chain_id: int = 137  # Polygon mainnet (80001 для testnet)
    polymarket_private_key: Optional[str] = None  # Приватный ключ кошелька (БЕЗ 0x префикса или с ним)
    polymarket_proxy_address: Optional[str] = None  # Адрес Proxy кошелька (где лежат USDC). Найти в Polymarket UI -> Profile -> Copy Address
    polymarket_signature_type: int = 1  # 1 = Magic Link/Email, 2 = MetaMask/Browser Wallet

    # Builder API ключи (для Relayer — redeem, gasless транзакции)
    # Получить на polymarket.com/settings?tab=builder
    polymarket_builder_api_key: Optional[str] = None
    polymarket_builder_secret: Optional[str] = None
    polymarket_builder_passphrase: Optional[str] = None

    # Прокси для CLOB API (формат: username:password@host:port или http://username:password@host:port)
    polymarket_clob_proxy: Optional[str] = "af8bUp:et9yg5VYr5Ud@mproxy.site:14470"
    
    # API сервер для приема ставок
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: Optional[str] = None  # Для защиты endpoint от несанкционированного доступа
    
    # Логирование
    log_level: str = "INFO"
    
    # Настройки ордеров
    default_order_size: float = 2.0  # Размер ордера по умолчанию (в долларах)
    min_profit_percent: float = 0.0  # Минимальный процент прибыли для размещения
    allowed_second_bookmakers: list[str] = ["PINNACLE", "BETFAIR", "SMARKETS", "MATCHBOOK"]  # Разрешенные second_bookmaker для размещения
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
