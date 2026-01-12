#!/usr/bin/env python3
"""
Скрипт для проверки адреса и баланса кошелька Polymarket
"""
import sys
sys.path.insert(0, '/root/polymarket_bot')

from app.config.settings import Settings
from app.services.clob_client import PolymarketCLOBClient
from eth_account import Account

def main():
    settings = Settings()
    
    # Получаем приватный ключ
    private_key = settings.polymarket_private_key
    
    if not private_key:
        print("❌ Приватный ключ не найден в настройках")
        print("\nПроверьте .env файл на наличие POLYMARKET_PRIVATE_KEY")
        return
    
    # Получаем адрес из приватного ключа
    try:
        # Убираем 0x если есть
        if private_key.startswith('0x'):
            private_key = private_key[2:]
        
        account = Account.from_key(private_key)
        wallet_address = account.address
        
        print("=" * 60)
        print("📊 ИНФОРМАЦИЯ О КОШЕЛЬКЕ")
        print("=" * 60)
        print(f"\n✅ Адрес кошелька: {wallet_address}")
        print(f"\n📍 Где посмотреть баланс:")
        print(f"   1. Polygonscan (USDC баланс):")
        print(f"      https://polygonscan.com/address/{wallet_address}")
        print(f"\n   2. Polymarket (ваш профиль):")
        print(f"      https://polymarket.com/account/{wallet_address}")
        print(f"\n   3. В логах бота (при обработке ставок)")
        print("\n" + "=" * 60)
        
        # Пытаемся получить баланс через API
        print("\n🔍 Попытка получить баланс через CLOB API...\n")
        try:
            client = PolymarketCLOBClient(settings)
            if client.is_available():
                balance_info = client.check_balance_and_allowance(0)
                print("💰 Информация о балансе:")
                print(f"   Баланс: {balance_info.get('balance', 'N/A')} USDC")
                print(f"   Allowance: {balance_info.get('allowance', 'N/A')}")
                print(f"   Has balance: {balance_info.get('has_balance', 'N/A')}")
                print(f"   Has allowance: {balance_info.get('has_allowance', 'N/A')}")
            else:
                print("⚠️ CLOB клиент не доступен")
                print("   Используйте Polygonscan или Polymarket для проверки баланса")
        except Exception as e:
            print(f"⚠️ Не удалось получить баланс через API: {e}")
            print("   Используйте Polygonscan или Polymarket для проверки баланса")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"❌ Ошибка при получении адреса: {e}")
        print("Проверьте правильность POLYMARKET_PRIVATE_KEY в .env файле")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
