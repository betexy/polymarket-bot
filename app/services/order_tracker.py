"""
Сервис для отслеживания результатов ордеров и расчета профита
"""
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.services.clob_client import PolymarketCLOBClient
from app.services.polymarket_client import PolymarketClient
from app.services.logger_service import log_storage
from app.config.settings import Settings

logger = logging.getLogger(__name__)


class OrderTracker:
    """Отслеживание результатов ордеров"""
    
    def __init__(
        self,
        clob_client: Optional[PolymarketCLOBClient],
        polymarket_client: PolymarketClient
    ):
        self.clob_client = clob_client
        self.polymarket_client = polymarket_client
        
    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Получение статуса ордера"""
        if not self.clob_client or not self.clob_client.is_available():
            return None
        
        try:
            order_info = self.clob_client.get_order(order_id)
            return order_info
        except Exception as e:
            logger.error(f"Error getting order status for {order_id}: {e}")
            return None
    
    async def get_all_orders(self) -> List[Dict[str, Any]]:
        """Получение списка всех ордеров"""
        if not self.clob_client or not self.clob_client.is_available():
            return []
        
        try:
            orders = self.clob_client.get_orders()
            return orders if isinstance(orders, list) else []
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
    
    async def update_order_result(self, order_id: str, market_id: str) -> Optional[Dict[str, Any]]:
        """Обновление результата ордера"""
        try:
            # Получаем статус ордера
            order_info = await self.get_order_status(order_id)
            if not order_info:
                return None
            
            # Получаем информацию о рынке
            market_info = await self.polymarket_client.get_market_by_id(market_id)
            if not market_info:
                return None
            
            # Проверяем, закрыт ли рынок
            is_closed = market_info.get("closed", False)
            is_active = market_info.get("active", True)
            
            result = {
                "order_id": order_id,
                "market_id": market_id,
                "updated_at": datetime.now().isoformat(),
                "order_status": order_info,
                "market_closed": is_closed,
                "market_active": is_active,
            }
            
            # Если рынок закрыт, пытаемся определить результат
            if is_closed:
                # Получаем результат рынка (какой исход выиграл)
                # Это требует дополнительной логики в зависимости от структуры данных
                result["market_result"] = "closed"
            
            return result
            
        except Exception as e:
            logger.error(f"Error updating order result for {order_id}: {e}")
            return None
    
    async def calculate_profit(self, order_id: str, initial_price: float, initial_size: float) -> Optional[float]:
        """Расчет профита для ордера"""
        try:
            order_info = await self.get_order_status(order_id)
            if not order_info:
                return None
            
            # Здесь должна быть логика расчета профита
            # Пока возвращаем None, т.к. нужно знать результат рынка
            return None
            
        except Exception as e:
            logger.error(f"Error calculating profit for {order_id}: {e}")
            return None
    
    async def update_all_orders(self) -> int:
        """Обновление результатов для всех ордеров из логов"""
        updated_count = 0
        
        try:
            # Получаем все ставки из логов
            bets = log_storage.get_recent_bets(limit=1000)
            
            for bet_entry in bets:
                result = bet_entry.get("result", {})
                order_id = result.get("order_id")
                
                if not order_id or result.get("status") != "success":
                    continue
                
                market_id = result.get("market_id")
                if not market_id:
                    continue
                
                # Обновляем результат
                order_result = await self.update_order_result(order_id, market_id)
                if order_result:
                    # Обновляем запись в логе
                    result["order_tracking"] = order_result
                    updated_count += 1
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating all orders: {e}")
            return 0
