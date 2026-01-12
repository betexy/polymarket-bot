#!/usr/bin/env python3
"""
Скрипт для проверки адреса кошелька и баланса
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.config.settings import Settings
from app.services.clob_client import PolymarketCLOBClient

def main():
    settings = Settings()
    
    if not settings.polymarket_private_key:
        print("❌ Ошибка: POLYMARKET_PRIVATE_KEY не установлен в .env")
        return
    
    print("🔍 Проверка кошелька...")
    print(f"Chain ID: {settings.polymarket_chain_id}")
    print(f"CLOB Host: {settings.polymarket_clob_host}")
    print()
    
    try:
        clob_client = PolymarketCLOBClient(settings)
        
        if not clob_client.is_available():
            print("❌ CLOB клиент не доступен")
            return
        
        # Получаем адрес кошелька
        address = clob_client.get_address()
        print(f"✅ Адрес кошелька: {address}")
        print()
        
        # Проверяем баланс
        print("💰 Проверка баланса...")
        try:
            balance_info = clob_client.get_balance()
            print(f"Баланс (raw): {balance_info}")
            
            # Пытаемся извлечь баланс
            if isinstance(balance_info, dict):
                balance = balance_info.get("balance") or balance_info.get("available") or balance_info.get("usdc", 0)
                print(f"✅ Баланс USDC: {balance}")
            else:
                print(f"✅ Баланс: {balance_info}")
        except Exception as e:
            print(f"❌ Ошибка при получении баланса: {e}")
        
        # Проверяем allowance
        print()
        print("🔐 Проверка allowance...")
        try:
            balance_check = clob_client.check_balance_and_allowance(1.0)  # Проверка для суммы 1 USD
            print(f"Результат проверки: {balance_check}")
            
            if balance_check.get("has_balance"):
                print(f"✅ Баланс достаточен: {balance_check.get('balance')} USDC")
            else:
                print(f"❌ Недостаточно баланса: {balance_check.get('balance')} USDC")
            
            if balance_check.get("needs_allowance_update"):
                print("⚠️  Требуется обновление allowance")
                print("Попытка обновления...")
                try:
                    result = clob_client.update_balance_allowance()
                    print(f"✅ Allowance обновлен: {result}")
                except Exception as e:
                    print(f"❌ Ошибка при обновлении allowance: {e}")
            else:
                print("✅ Allowance достаточен")
        except Exception as e:
            print(f"❌ Ошибка при проверке allowance: {e}")
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
