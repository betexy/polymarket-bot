import logging
from typing import Optional, Dict, Any
from app.config.settings import Settings

logger = logging.getLogger(__name__)

try:
    from py_clob_client.client import ClobClient
    from py_clob_client import clob_types
    import py_clob_client.http_helpers.helpers as http_helpers
    import httpx
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False
    logger.warning("py-clob-client not installed. CLOB functionality will be disabled.")

try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    logger.warning("web3 not installed. Direct balance check will be disabled.")

# USDC contract on Polygon
USDC_CONTRACT_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
USDC_ABI = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]


class PolymarketCLOBClient:
    """
    Клиент для работы с Polymarket CLOB API
    
    Использует официальную библиотеку py-clob-client для размещения ордеров
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Optional[ClobClient] = None
        self._initialized = False
        
        if not CLOB_AVAILABLE:
            logger.error("py-clob-client not available. Install with: pip install py-clob-client")
            return
        
        if not settings.polymarket_private_key:
            logger.warning("Private key not configured. CLOB client will not be initialized.")
            return
        
        # Настраиваем прокси для HTTP клиента py-clob-client
        self._setup_proxy()
        
        self._initialize_client()
    
    def _setup_proxy(self) -> None:
        """Настройка прокси для py-clob-client HTTP клиента"""
        if not CLOB_AVAILABLE:
            return
            
        if not self.settings.polymarket_clob_proxy:
            logger.info("No proxy configured for CLOB API")
            return
        
        try:
            # Форматируем прокси URL
            proxy_url = self.settings.polymarket_clob_proxy
            if not proxy_url.startswith('http://') and not proxy_url.startswith('https://'):
                # Если формат username:password@host:port, добавляем http://
                if '@' in proxy_url:
                    proxy_url = f"http://{proxy_url}"
                else:
                    proxy_url = f"http://{proxy_url}"
            
            logger.info(f"Setting up proxy for CLOB API: {proxy_url.split('@')[1] if '@' in proxy_url else proxy_url}")
            
            # Патчим глобальный httpx клиент в py-clob-client
            # py-clob-client использует глобальный _http_client = httpx.Client(http2=True)
            # Пересоздаем его с прокси
            old_client = http_helpers._http_client
            http_helpers._http_client = httpx.Client(
                http2=True,
                proxy=proxy_url,  # httpx использует proxy (единственное число)
                timeout=30.0
            )
            
            # Закрываем старый клиент
            try:
                old_client.close()
            except:
                pass
            
            logger.info("Proxy configured successfully for CLOB API")
            
        except Exception as e:
            logger.error(f"Failed to setup proxy: {e}", exc_info=True)
    
    def _initialize_client(self) -> None:
        """Инициализация CLOB клиента"""
        try:
            # Параметры для инициализации
            client_kwargs = {
                "host": self.settings.polymarket_clob_host,
                "chain_id": self.settings.polymarket_chain_id,
                "key": self.settings.polymarket_private_key
            }
            
            # Добавляем signature_type (1 = Magic Link/Email, 2 = MetaMask)
            if hasattr(self.settings, 'polymarket_signature_type') and self.settings.polymarket_signature_type:
                client_kwargs["signature_type"] = self.settings.polymarket_signature_type
            else:
                client_kwargs["signature_type"] = 1  # По умолчанию Magic Link/Email
            
            # Добавляем funder (Proxy адрес) - КРИТИЧЕСКИ ВАЖНО!
            if hasattr(self.settings, 'polymarket_proxy_address') and self.settings.polymarket_proxy_address:
                client_kwargs["funder"] = self.settings.polymarket_proxy_address
                logger.info(f"Using Proxy Wallet (funder): {self.settings.polymarket_proxy_address}")
            else:
                logger.warning("⚠️ POLYMARKET_PROXY_ADDRESS not set! Trading will use EOA address (may fail if balance is on Proxy)")
                logger.warning("   Set POLYMARKET_PROXY_ADDRESS in .env file (find it in Polymarket UI -> Profile -> Copy Address)")
            
            # Создаем клиент с приватным ключом и настройками
            self._client = ClobClient(**client_kwargs)
            
            # Если есть API ключи, используем их
            if (self.settings.polymarket_api_key and 
                self.settings.polymarket_api_secret and 
                self.settings.polymarket_api_passphrase):
                try:
                    # Создаем ApiCreds объект напрямую
                    api_creds = clob_types.ApiCreds(
                        api_key=self.settings.polymarket_api_key,
                        api_secret=self.settings.polymarket_api_secret,
                        api_passphrase=self.settings.polymarket_api_passphrase
                    )
                    self._client.set_api_creds(api_creds)
                    logger.info("CLOB client initialized with existing API credentials")
                except Exception as e:
                    logger.warning(f"Failed to set API credentials: {e}. Will create/derive new ones.")
                    try:
                        # Создаем или получаем API ключи
                        api_creds = self._client.create_or_derive_api_creds()
                        self._client.set_api_creds(api_creds)
                        logger.info("CLOB client initialized with new API credentials")
                    except Exception as e2:
                        logger.error(f"Failed to create/derive API credentials: {e2}")
                        # Продолжаем без API ключей (клиент может работать без них для некоторых операций)
                        logger.warning("CLOB client initialized without API credentials")
            else:
                # Создаем или получаем API ключи
                api_creds = self._client.create_or_derive_api_creds()
                self._client.set_api_creds(api_creds)
                logger.info("CLOB client initialized with derived API credentials")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}", exc_info=True)
            self._client = None
            self._initialized = False
    
    def is_available(self) -> bool:
        """Проверка доступности CLOB клиента"""
        return CLOB_AVAILABLE and self._initialized and self._client is not None
    
    def get_best_price(self, token_id: str, side: str = "BUY") -> Optional[float]:
        """
        Получение лучшей цены из CLOB order book.
        Для BUY возвращает best ask (минимальная цена продавца) из order book.
        """
        if not self.is_available():
            return None
        try:
            # Используем order book для получения реальной best ask/bid
            order_book = self._client.get_order_book(token_id)
            if side.upper() == "BUY" and order_book.asks:
                # Best ask = минимальная цена среди asks (asks обычно отсортированы по возрастанию)
                best_ask = min(float(a.price) for a in order_book.asks if a.price)
                if 0 < best_ask < 1:
                    logger.info(f"CLOB best ask from order book: {best_ask} (token_id=...{token_id[-10:]})")
                    return best_ask
            elif side.upper() == "SELL" and order_book.bids:
                # Best bid = максимальная цена среди bids
                best_bid = max(float(b.price) for b in order_book.bids if b.price)
                if 0 < best_bid < 1:
                    logger.info(f"CLOB best bid from order book: {best_bid} (token_id=...{token_id[-10:]})")
                    return best_bid
            logger.warning(f"No {'asks' if side.upper() == 'BUY' else 'bids'} in order book for token_id=...{token_id[-10:]}")
            return None
        except Exception as e:
            logger.warning(f"Could not get CLOB price from order book: {e}")
            return None

    def create_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str = "BUY"  # "BUY" or "SELL"
    ) -> Dict[str, Any]:
        """
        Размещение ордера на Polymarket
        
        Args:
            token_id: ID токена (outcome token) из market
            price: Цена от 0.01 до 0.99 (0.50 = 50% вероятность)
            size: Размер ордера (в токенах)
            side: "BUY" или "SELL"
        
        Returns:
            Ответ от API с информацией об ордере (включая orderID)
        
        Raises:
            Exception: Если клиент не инициализирован или произошла ошибка
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            logger.info(f"Creating order: token_id={token_id}, price={price}, size={size}, side={side}")
            
            # Создаем OrderArgs объект
            order_args = clob_types.OrderArgs(
                token_id=token_id,
                price=float(price),  # Цена как float
                size=float(size),    # Размер как float
                side=side.upper()    # "BUY" или "SELL"
            )
            
            # Используем create_and_post_order для создания и отправки ордера за один раз
            try:
                response = self._client.create_and_post_order(order_args)
            except Exception as e:
                error_msg = str(e)
                # Если ошибка 401 (Unauthorized), пытаемся создать новые ключи
                if "401" in error_msg or "Unauthorized" in error_msg or "Invalid api key" in error_msg:
                    logger.warning(f"API key authentication failed: {e}. Attempting to create new API credentials...")
                    try:
                        # Создаем новые API ключи
                        new_api_creds = self._client.create_or_derive_api_creds()
                        self._client.set_api_creds(new_api_creds)
                        logger.info("New API credentials created and set. Retrying order...")
                        # Повторная попытка
                        response = self._client.create_and_post_order(order_args)
                    except Exception as e2:
                        logger.error(f"Failed to create new API credentials: {e2}")
                        raise e  # Пробрасываем оригинальную ошибку
                # Если ошибка "not enough balance / allowance", не пытаемся обновить allowance
                # При использовании Proxy Wallet update_balance_allowance() не работает
                # Allowance должен быть установлен вручную через веб-интерфейс или через скрипт
                elif "not enough balance" in error_msg.lower() or "not enough allowance" in error_msg.lower() or "allowance" in error_msg.lower():
                    logger.warning(f"Insufficient balance/allowance: {e}")
                    if hasattr(self.settings, 'polymarket_proxy_address') and self.settings.polymarket_proxy_address:
                        logger.warning(f"Proxy Wallet mode: allowance must be set manually. Check balance on: {self.settings.polymarket_proxy_address}")
                    raise e  # Пробрасываем ошибку без попытки обновить allowance
                else:
                    raise  # Пробрасываем другие ошибки
            
            # response может быть dict или другой тип
            if isinstance(response, dict):
                order_id = response.get('orderID') or response.get('order_id') or response.get('id')
            elif hasattr(response, 'orderID'):
                order_id = response.orderID
            elif hasattr(response, 'dict'):
                # Если это объект с методом dict()
                order_dict = response.dict()
                order_id = order_dict.get('orderID') or order_dict.get('order_id') or order_dict.get('id')
            else:
                order_id = str(response)
            
            logger.info(f"Order created and posted successfully: {order_id}")
            # Преобразуем response в словарь для удобства
            if isinstance(response, dict):
                return response
            elif hasattr(response, 'dict'):
                return response.dict()
            else:
                return {"orderID": order_id, "response": str(response)} if order_id else {"response": str(response)}
            
        except Exception as e:
            logger.error(f"Error creating order: {e}", exc_info=True)
            raise
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Отмена ордера
        
        Args:
            order_id: ID ордера для отмены
        
        Returns:
            Ответ от API
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            logger.info(f"Canceling order: {order_id}")
            response = self._client.cancel(order_id)
            logger.info(f"Order canceled: {order_id}")
            return response
        except Exception as e:
            logger.error(f"Error canceling order: {e}", exc_info=True)
            raise
    
    def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Получение информации об ордере
        
        Args:
            order_id: ID ордера
        
        Returns:
            Информация об ордере
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            return self._client.get_order(order_id=order_id)
        except Exception as e:
            logger.error(f"Error getting order: {e}", exc_info=True)
            raise
    
    def get_orders(self) -> list[Dict[str, Any]]:
        """
        Получение списка всех открытых ордеров
        
        Returns:
            Список ордеров
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            return self._client.get_orders()
        except Exception as e:
            logger.error(f"Error getting orders: {e}", exc_info=True)
            raise
    
    def get_positions(self) -> list[Dict[str, Any]]:
        """
        Получение позиций
        
        Returns:
            Список позиций
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            return self._client.get_positions()
        except Exception as e:
            logger.error(f"Error getting positions: {e}", exc_info=True)
            raise
    
    def get_balance(self) -> Dict[str, Any]:
        """
        Получение баланса
        
        Returns:
            Информация о балансе
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            # Используем get_balance_allowance для получения баланса
            balance_allowance = self._client.get_balance_allowance()
            if isinstance(balance_allowance, dict):
                return balance_allowance
            else:
                # Если возвращается не dict, оборачиваем
                return {"balance": balance_allowance}
        except Exception as e:
            logger.error(f"Error getting balance: {e}", exc_info=True)
            raise
    
    def get_address(self) -> Optional[str]:
        """
        Получение адреса кошелька
        
        Returns:
            Адрес кошелька или None
        """
        if not self.is_available():
            return None
        
        try:
            return self._client.get_address()
        except Exception as e:
            logger.error(f"Error getting address: {e}", exc_info=True)
            return None
    
    def get_balance_allowance(self) -> Dict[str, Any]:
        """
        Получение баланса и allowance
        
        Returns:
            Словарь с балансом и allowance
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            return self._client.get_balance_allowance()
        except Exception as e:
            logger.error(f"Error getting balance/allowance: {e}", exc_info=True)
            raise
    
    def update_balance_allowance(self, amount: Optional[float] = None) -> Dict[str, Any]:
        """
        Обновление allowance для CLOB контракта
        
        Args:
            amount: Сумма для allowance (если None, устанавливается максимальное значение)
        
        Returns:
            Результат обновления
        """
        if not self.is_available():
            raise Exception("CLOB client is not available or not initialized")
        
        try:
            if amount is not None:
                return self._client.update_balance_allowance(amount=amount)
            else:
                # Устанавливаем максимальное allowance
                return self._client.update_balance_allowance()
        except Exception as e:
            logger.error(f"Error updating balance allowance: {e}", exc_info=True)
            raise
    
    def get_usdc_balance_direct(self, address: str) -> Optional[float]:
        """
        Прямая проверка баланса USDC через Web3 (не через py-clob-client)
        Работает для любого адреса, включая Proxy Wallet
        
        Args:
            address: Адрес кошелька для проверки
            
        Returns:
            Баланс в USDC или None при ошибке
        """
        if not WEB3_AVAILABLE:
            logger.warning("Web3 not available for direct balance check")
            return None
        
        try:
            w3 = Web3(Web3.HTTPProvider('https://polygon-bor-rpc.publicnode.com'))
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(USDC_CONTRACT_ADDRESS),
                abi=USDC_ABI
            )
            balance_wei = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()
            balance_usdc = balance_wei / 1e6  # USDC has 6 decimals
            logger.info(f"Direct USDC balance check: {address} = ${balance_usdc:.2f}")
            return balance_usdc
        except Exception as e:
            logger.error(f"Error getting USDC balance directly: {e}")
            return None
    
    def check_balance_and_allowance(self, required_amount: float) -> Dict[str, Any]:
        """
        Проверка баланса и allowance перед размещением ордера
        
        Args:
            required_amount: Требуемая сумма для ордера
        
        Returns:
            Словарь с результатами проверки:
            {
                "has_balance": bool,
                "has_allowance": bool,
                "balance": float,
                "allowance": float,
                "address": str,
                "needs_allowance_update": bool
            }
        """
        if not self.is_available():
            return {
                "has_balance": False,
                "has_allowance": False,
                "error": "CLOB client not available"
            }
        
        try:
            # Получаем адрес кошелька (для Proxy Wallet это будет EOA)
            address = self.get_address()
            balance = None
            allowance = None
            needs_allowance_update = True
            
            # Определяем адрес для проверки баланса
            # Для Proxy Wallet проверяем баланс на Proxy адресе, а не EOA
            balance_check_address = address
            if hasattr(self.settings, 'polymarket_proxy_address') and self.settings.polymarket_proxy_address:
                balance_check_address = self.settings.polymarket_proxy_address
                logger.info(f"Using Proxy Wallet address for balance check: {balance_check_address}")
            
            # ВАЖНО: Прямая проверка баланса USDC через Web3
            # Это работает для любого адреса, включая Proxy Wallet
            balance = self.get_usdc_balance_direct(balance_check_address)
            
            if balance is None:
                # Fallback: пытаемся через py-clob-client (работает только для EOA)
                try:
                    balance_allowance_info = self._client.get_balance_allowance()
                    
                    if isinstance(balance_allowance_info, dict):
                        balance = float(balance_allowance_info.get("balance", 
                            balance_allowance_info.get("available", 
                            balance_allowance_info.get("usdc", 
                            balance_allowance_info.get("usdcBalance", 0)))))
                        
                        allowance = float(balance_allowance_info.get("allowance",
                            balance_allowance_info.get("usdc_allowance",
                            balance_allowance_info.get("usdcAllowance", 0))))
                        
                        needs_allowance_update = allowance < required_amount if allowance is not None else True
                    elif isinstance(balance_allowance_info, (int, float)):
                        balance = float(balance_allowance_info)
                except Exception as e:
                    logger.warning(f"Fallback balance check failed: {e}")
            
            # Результат проверки
            has_balance = balance >= required_amount if balance is not None else None
            
            result = {
                "has_balance": has_balance,
                "has_allowance": allowance >= required_amount if allowance is not None else None,
                "balance": balance,
                "allowance": allowance,
                "address": balance_check_address,
                "eoa_address": address,
                "needs_allowance_update": needs_allowance_update,
                "required_amount": required_amount
            }
            
            balance_str = f"${balance:.2f}" if balance is not None else "N/A"
            logger.info(f"Balance check: address={balance_check_address}, balance={balance_str}, required=${required_amount:.2f}, has_balance={has_balance}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking balance and allowance: {e}", exc_info=True)
            return {
                "has_balance": None,
                "has_allowance": None,
                "error": str(e)
            }
    
    def get_token_id_from_market(
        self,
        market_data: Dict[str, Any],
        outcome: str = "YES"  # "YES", "NO", или индекс/название outcome
    ) -> Optional[str]:
        """
        Извлечение token_id из market данных
        
        Args:
            market_data: Данные market из Gamma API
            outcome: Название или индекс outcome ("YES", "NO", "0", "1", etc.)
        
        Returns:
            token_id или None если не найден
        """
        # Ищем tokens в разных форматах
        # В Polymarket API tokens могут быть в разных полях:
        # - tokens (массив объектов с token_id)
        # - outcomeTokens (массив объектов)
        # - clobTokenIds (массив строк с token_id для CLOB)
        # - outcomes (массив строк или JSON строка)
        tokens = market_data.get("tokens") or market_data.get("outcomeTokens")
        clob_token_ids = market_data.get("clobTokenIds")
        outcomes = market_data.get("outcomes", [])
        
        # Если есть clobTokenIds (это token_id для CLOB), используем их
        if clob_token_ids:
            if isinstance(clob_token_ids, str):
                try:
                    import json
                    clob_token_ids = json.loads(clob_token_ids)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"Could not parse clobTokenIds as JSON: {clob_token_ids}")
                    clob_token_ids = []
            
            if isinstance(clob_token_ids, list) and len(clob_token_ids) > 0:
                logger.warning(f"   [TOKEN_SEARCH] Found clobTokenIds: {clob_token_ids}")
                # Создаем структуру tokens из clobTokenIds для совместимости
                if not tokens or not isinstance(tokens, list):
                    tokens = [{"token_id": tid, "id": tid} for tid in clob_token_ids]
                    logger.warning(f"   [TOKEN_SEARCH] Created tokens structure from clobTokenIds")
        
        # НЕ используем outcomes как fallback для tokens, т.к. outcomes - это названия, а не token_id
        # Если tokens все еще нет после обработки clobTokenIds, значит их нет в данных
        
        # Если outcomes - строка JSON, парсим её
        if isinstance(outcomes, str):
            try:
                import json
                outcomes = json.loads(outcomes)
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"Could not parse outcomes as JSON: {outcomes}")
                outcomes = []
        
        if not tokens or not isinstance(tokens, list):
            logger.error(f"❌ [TOKEN_SEARCH] No tokens found in market data!")
            logger.error(f"   [TOKEN_SEARCH] Market data keys: {list(market_data.keys())[:20]}")
            logger.error(f"   [TOKEN_SEARCH] tokens value: {tokens} (type: {type(tokens).__name__})")
            logger.error(f"   [TOKEN_SEARCH] outcomes value: {outcomes} (type: {type(outcomes).__name__})")
            return None
        
        outcome_upper = str(outcome).upper()
        logger.warning(f"🔍 [TOKEN_SEARCH] Searching token_id for outcome='{outcome}' (upper: '{outcome_upper}')")
        logger.warning(f"   [TOKEN_SEARCH] Available outcomes: {outcomes} (type: {type(outcomes).__name__})")
        logger.warning(f"   [TOKEN_SEARCH] Tokens found: {len(tokens) if isinstance(tokens, list) else 0} tokens (type: {type(tokens).__name__})")
        if isinstance(tokens, list) and len(tokens) > 0:
            logger.warning(f"   [TOKEN_SEARCH] First token sample: {str(tokens[0])[:200]}")
        else:
            logger.error(f"   [TOKEN_SEARCH] ⚠️ NO TOKENS IN LIST! tokens={tokens}")
        
        # Если outcome - индекс
        if outcome_upper.isdigit():
            idx = int(outcome_upper)
            if 0 <= idx < len(tokens):
                token = tokens[idx]
                if isinstance(token, dict):
                    token_id = token.get("token_id") or token.get("tokenId") or token.get("id")
                    if token_id:
                        logger.debug(f"Found token_id by index {idx}: {token_id}")
                        return token_id
                elif isinstance(token, str):
                    logger.debug(f"Found token_id by index {idx}: {token}")
                    return token
        
        # Если outcome - название (YES, NO, Home, Away, Over, Under, или название команды)
        # Сначала проверяем, если outcomes - это массив строк (названия), а tokens - объекты с token_id
        if outcomes and isinstance(outcomes, list) and len(outcomes) > 0:
            logger.warning(f"   [TOKEN_SEARCH] Checking outcomes list (length: {len(outcomes)})")
            for i, outcome_name in enumerate(outcomes):
                if isinstance(outcome_name, str):
                    outcome_name_upper = outcome_name.upper()
                    # Проверяем совпадение названия outcome
                    match = outcome_upper == outcome_name_upper or outcome_upper in outcome_name_upper or outcome_name_upper in outcome_upper
                    logger.warning(f"   [TOKEN_SEARCH] Outcome[{i}]: '{outcome_name}' (upper: '{outcome_name_upper}') - Match: {match}")
                    if match:
                        # Находим соответствующий token по индексу
                        if i < len(tokens):
                            token = tokens[i]
                            logger.warning(f"   [TOKEN_SEARCH] Token[{i}]: type={type(token).__name__}, value={str(token)[:200]}")
                            if isinstance(token, dict):
                                token_id = token.get("token_id") or token.get("tokenId") or token.get("id")
                                if token_id:
                                    logger.warning(f"✅ [TOKEN_SEARCH] Found token_id by outcome name match (index {i}, outcome '{outcome_name}'): {token_id}")
                                    return token_id
                                else:
                                    logger.error(f"⚠️ [TOKEN_SEARCH] Token at index {i} found but no token_id field. Keys: {list(token.keys())[:10]}")
                                    logger.error(f"   [TOKEN_SEARCH] Full token: {token}")
                            elif isinstance(token, str):
                                logger.warning(f"✅ [TOKEN_SEARCH] Found token_id by outcome name match (index {i}, outcome '{outcome_name}'): {token}")
                                return token
                        else:
                            logger.error(f"⚠️ [TOKEN_SEARCH] Outcome '{outcome_name}' found at index {i}, but tokens list has only {len(tokens)} elements")
        
        # Проверяем tokens напрямую
        logger.info(f"   Checking tokens directly (count: {len(tokens)})")
        for idx, token in enumerate(tokens):
            if isinstance(token, dict):
                token_outcome = token.get("outcome") or token.get("name") or token.get("label")
                if token_outcome:
                    token_outcome_upper = str(token_outcome).upper()
                    match = outcome_upper == token_outcome_upper or outcome_upper in token_outcome_upper or token_outcome_upper in outcome_upper
                    logger.info(f"   Token[{idx}]: outcome='{token_outcome}' (upper: '{token_outcome_upper}') - Match: {match}")
                    if match:
                        token_id = token.get("token_id") or token.get("tokenId") or token.get("id")
                        if token_id:
                            logger.info(f"✅ Found token_id by direct token match: {token_id}")
                            return token_id
                        else:
                            logger.warning(f"⚠️ Token match found but no token_id field. Keys: {token.keys()}")
            elif isinstance(token, str):
                # Если token - строка (название outcome)
                token_upper = token.upper()
                match = outcome_upper == token_upper or outcome_upper in token_upper or token_upper in outcome_upper
                logger.info(f"   Token[{idx}] (string): '{token}' (upper: '{token_upper}') - Match: {match}")
                if match:
                    # Если token - это строка, нужно найти соответствующий token_id
                    # Проверяем, есть ли в market_data структура с token_id
                    # Пытаемся найти token_id по индексу в другой структуре
                    tokens_dict = market_data.get("tokens") or market_data.get("outcomeTokens")
                    if tokens_dict and isinstance(tokens_dict, list) and idx < len(tokens_dict):
                        token_obj = tokens_dict[idx]
                        if isinstance(token_obj, dict):
                            token_id = token_obj.get("token_id") or token_obj.get("tokenId") or token_obj.get("id")
                            if token_id:
                                logger.info(f"✅ Found token_id by string token match: {token_id}")
                                return token_id
        
        # Если не нашли, возвращаем первый токен (fallback)
        logger.error(f"❌ [TOKEN_SEARCH] Token ID not found for outcome '{outcome}' after all checks")
        logger.error(f"   [TOKEN_SEARCH] Market data keys: {list(market_data.keys())[:20]}")
        logger.error(f"   [TOKEN_SEARCH] Outcomes: {outcomes}")
        logger.error(f"   [TOKEN_SEARCH] Tokens type: {type(tokens).__name__}, count: {len(tokens) if isinstance(tokens, list) else 'N/A'}")
        if isinstance(tokens, list):
            logger.error(f"   [TOKEN_SEARCH] All tokens: {[str(t)[:100] for t in tokens[:5]]}")
        
        if tokens:
            first_token = tokens[0]
            logger.warning(f"   [TOKEN_SEARCH] Using first token as fallback: {str(first_token)[:200]}")
            if isinstance(first_token, dict):
                token_id = first_token.get("token_id") or first_token.get("tokenId") or first_token.get("id")
                if token_id:
                    logger.warning(f"   [TOKEN_SEARCH] Fallback token_id: {token_id}")
                    return token_id
                else:
                    logger.error(f"   [TOKEN_SEARCH] First token has no token_id! Keys: {list(first_token.keys())[:10]}")
            elif isinstance(first_token, str):
                logger.warning(f"   [TOKEN_SEARCH] Fallback token (string): {first_token}")
                return first_token
        
        logger.error(f"❌ [TOKEN_SEARCH] Token ID not found for outcome '{outcome}'. No fallback available.")
        return None
