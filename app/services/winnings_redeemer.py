"""
Сервис для автоматического вывода (redeem) выигрышных позиций.

После резолва маркета выигрышные conditional tokens конвертируются в USDC
через Builder Relayer (gasless) → ProxyFactory → CTF.redeemPositions.
"""
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

from app.config.settings import Settings

logger = logging.getLogger(__name__)

# Ленивый импорт poly_web3 (может быть не установлен)
_poly_web3_available = False
try:
    from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds
    from py_builder_signing_sdk.config import BuilderConfig
    from py_builder_relayer_client.client import RelayClient
    from poly_web3 import PolyWeb3Service
    from poly_web3.web3_service.base import BaseWeb3Service
    _poly_web3_available = True
except ImportError:
    logger.warning("poly-web3 not installed. Redeem will be disabled. pip install poly-web3")

RELAYER_URL = "https://relayer-v2.polymarket.com"
RPC_URL = "https://polygon-bor-rpc.publicnode.com"


class WinningsRedeemer:
    """Автоматический redeem выигрышных позиций через Builder Relayer"""

    def __init__(self, settings: Settings, db_path: str = "polymarket_bets.db"):
        self.settings = settings
        self.db_path = db_path
        self._web3_service: Optional[Any] = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Инициализирует poly_web3 сервис при первом вызове"""
        if self._initialized:
            return self._web3_service is not None

        self._initialized = True

        if not _poly_web3_available:
            logger.error("poly-web3 not available, cannot redeem")
            return False

        builder_key = self.settings.polymarket_builder_api_key
        builder_secret = self.settings.polymarket_builder_secret
        builder_passphrase = self.settings.polymarket_builder_passphrase

        if not all([builder_key, builder_secret, builder_passphrase]):
            logger.warning(
                "Builder API credentials not configured. "
                "Set POLYMARKET_BUILDER_API_KEY, POLYMARKET_BUILDER_SECRET, "
                "POLYMARKET_BUILDER_PASSPHRASE in .env. "
                "Get them at polymarket.com/settings?tab=builder"
            )
            return False

        if not self.settings.polymarket_private_key:
            logger.warning("Private key not configured, cannot redeem")
            return False

        try:
            from py_clob_client.client import ClobClient
            from py_clob_client import clob_types

            builder_creds = BuilderApiKeyCreds(
                key=builder_key,
                secret=builder_secret,
                passphrase=builder_passphrase,
            )
            builder_config = BuilderConfig(local_builder_creds=builder_creds)

            relay = RelayClient(
                relayer_url=RELAYER_URL,
                chain_id=self.settings.polymarket_chain_id,
                private_key=self.settings.polymarket_private_key,
                builder_config=builder_config,
            )

            proxy_address = self.settings.polymarket_proxy_address
            if proxy_address:
                proxy_address = proxy_address.strip('"')

            clob = ClobClient(
                host=self.settings.polymarket_clob_host,
                chain_id=self.settings.polymarket_chain_id,
                key=self.settings.polymarket_private_key,
                signature_type=self.settings.polymarket_signature_type,
                funder=proxy_address,
                builder_config=builder_config,
            )

            if (self.settings.polymarket_api_key and
                    self.settings.polymarket_api_secret and
                    self.settings.polymarket_api_passphrase):
                api_creds = clob_types.ApiCreds(
                    api_key=self.settings.polymarket_api_key,
                    api_secret=self.settings.polymarket_api_secret,
                    api_passphrase=self.settings.polymarket_api_passphrase,
                )
                clob.set_api_creds(api_creds)

            self._web3_service = PolyWeb3Service(clob, relay, rpc_url=RPC_URL)
            logger.info(f"WinningsRedeemer initialized: {type(self._web3_service).__name__}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize WinningsRedeemer: {e}", exc_info=True)
            return False

    def _get_proxy_address(self) -> Optional[str]:
        proxy = self.settings.polymarket_proxy_address
        if proxy:
            return proxy.strip('"')
        return None

    async def redeem_all_winning_bets(self) -> Dict[str, Any]:
        """
        Выводит все выигрышные позиции через Builder Relayer.

        1. Получает redeemable позиции через Polymarket Data API
        2. Для каждой вызывает CTF.redeemPositions через Proxy → Relayer
        3. Помечает redeemed ставки в БД

        Returns:
            Словарь с результатами: redeemed, errors, total
        """
        if not self._ensure_initialized():
            return {"redeemed": 0, "errors": 0, "total": 0, "skipped": "not_configured"}

        proxy_address = self._get_proxy_address()
        if not proxy_address:
            logger.warning("Proxy address not configured, cannot redeem")
            return {"redeemed": 0, "errors": 0, "total": 0, "skipped": "no_proxy_address"}

        try:
            # Получаем redeemable позиции через Polymarket Data API
            positions = BaseWeb3Service.fetch_positions(proxy_address)
            if not positions:
                return {"redeemed": 0, "errors": 0, "total": 0}

            logger.info(f"Found {len(positions)} redeemable positions")

            # Группируем condition_ids
            condition_ids = list({p.get("conditionId") for p in positions if p.get("conditionId")})
            if not condition_ids:
                return {"redeemed": 0, "errors": 0, "total": 0}

            # Выполняем redeem через poly_web3 (батчами)
            results = self._web3_service.redeem(condition_ids, batch_size=5)

            redeemed_count = len([r for r in results if r])
            error_count = len(condition_ids) - redeemed_count

            if redeemed_count > 0:
                logger.info(f"Redeemed {redeemed_count} positions successfully")
                # Помечаем в БД
                self._mark_redeemed_by_conditions(condition_ids)

            logger.info(f"Redeem complete: redeemed={redeemed_count}, errors={error_count}, total={len(condition_ids)}")
            return {"redeemed": redeemed_count, "errors": error_count, "total": len(condition_ids)}

        except Exception as e:
            logger.error(f"Error in redeem_all_winning_bets: {e}", exc_info=True)
            return {"redeemed": 0, "errors": 1, "total": 0, "error": str(e)}

    def _mark_redeemed_by_conditions(self, condition_ids: list) -> None:
        """
        Помечает redeemed ставки в БД по condition_id маркетов.
        Поскольку в БД хранится market_id (Gamma), а не condition_id,
        помечаем все WIN ставки без redeemed как выведенные.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                """UPDATE bets SET redeemed = 1, redeemed_at = ?
                   WHERE status = 'success'
                     AND settled_status = 'WIN'
                     AND (redeemed IS NULL OR redeemed = 0)""",
                (now,)
            )
            updated = cursor.rowcount
            conn.commit()
            conn.close()
            if updated > 0:
                logger.info(f"Marked {updated} bets as redeemed in DB")
        except Exception as e:
            logger.error(f"Error marking bets as redeemed: {e}", exc_info=True)
