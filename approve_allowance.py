#!/usr/bin/env python3
"""
Скрипт для установки allowance (разрешения) для контракта Polymarket CLOB
"""
import sys
sys.path.insert(0, '/root/polymarket_bot')

from app.config.settings import Settings
from app.services.clob_client import PolymarketCLOBClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    settings = Settings()
    
    print("=" * 60)
    print("🔐 УСТАНОВКА ALLOWANCE ДЛЯ POLYMARKET CLOB")
    print("=" * 60)
    
    try:
        client = PolymarketCLOBClient(settings)
        if not client.is_available():
            print("\n❌ CLOB клиент не доступен")
            print("Проверьте настройки POLYMARKET_PRIVATE_KEY в .env файле")
            return
        
        address = client.get_address()
        print(f"\n✅ Адрес кошелька: {address}")
        print(f"💰 Баланс: 12.39 USDC (из Polygonscan)")
        
        print("\n⚠️ Проблема: Нет allowance (разрешения для контракта)")
        print("\n🔧 Попытка установить allowance...\n")
        
        try:
            # Пытаемся установить максимальное allowance
            result = client.update_balance_allowance()
            print("✅ Allowance успешно установлен!")
            print(f"Результат: {result}")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Ошибка при установке allowance через код: {error_msg}")
            
            if "signature_type" in error_msg:
                print("\n" + "=" * 60)
                print("💡 РЕШЕНИЕ: Установите allowance через Polymarket UI")
                print("=" * 60)
                print("\nИнструкция:")
                print("1. Откройте Polymarket: https://polymarket.com")
                print("2. Подключите кошелек (MetaMask или другой)")
                print("3. Перейдите в настройки аккаунта")
                print("4. Найдите опцию 'Approve USDC' или 'Enable Trading'")
                print("5. Подтвердите транзакцию в кошельке")
                print("\nИли используйте прямую ссылку (если доступна):")
                print(f"   https://polymarket.com/account/{address}")
                print("\nПосле установки allowance, попробуйте снова разместить ставку.")
            else:
                print(f"\nНеизвестная ошибка: {e}")
                import traceback
                traceback.print_exc()
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
