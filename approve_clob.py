#!/usr/bin/env python3
"""
Скрипт для установки allowance через web3
"""
from web3 import Web3

# Настройки
RPC_URL = "https://polygon-rpc.com"
PRIVATE_KEY = "0x61faf91b1cf51466853826d9841dd7b6f956696815f1c69a6029c0a2deae9a2f"
MY_ADDRESS = "0x841F88aEF3e5B7d2e0a080Bb5ff0a52441Bc88b9"

# Адреса (проверьте актуальность!)
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174" # USDC.e on Polygon
EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E" # Polymarket Exchange Proxy

print("🔧 Настройка подключения к Polygon...")
w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print("❌ Не удалось подключиться к Polygon RPC")
    exit(1)

print(f"✅ Подключено к Polygon (chain_id: {w3.eth.chain_id})")

# ABI для метода approve (минимум)
erc20_abi = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

print(f"\n📝 Создание транзакции approve...")
print(f"   Контракт USDC: {USDC_ADDRESS}")
print(f"   Spender (CLOB): {EXCHANGE_ADDRESS}")
print(f"   Amount: Max Uint256")

contract = w3.eth.contract(address=USDC_ADDRESS, abi=erc20_abi)

# Получаем nonce
nonce = w3.eth.get_transaction_count(MY_ADDRESS)
print(f"   Nonce: {nonce}")

# Получаем актуальную цену газа
try:
    gas_price = w3.eth.gas_price
    print(f"   Gas price: {gas_price / 1e9:.2f} Gwei")
except:
    gas_price = w3.to_wei('50', 'gwei')
    print(f"   Gas price: 50 Gwei (по умолчанию)")

# Создаем транзакцию
tx = contract.functions.approve(
    EXCHANGE_ADDRESS,
    115792089237316195423570985008687907853269984665640564039457584007913129639935 # Max Uint256
).build_transaction({
    'chainId': 137,
    'gas': 100000,
    'gasPrice': gas_price,
    'nonce': nonce,
})

print(f"\n💰 Ориентировочная стоимость газа: {tx['gas'] * tx['gasPrice'] / 1e18:.6f} MATIC")

# Подписываем и отправляем
print(f"\n📤 Отправка транзакции...")
signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

print(f"\n✅ Транзакция отправлена!")
print(f"   Hash: {tx_hash.hex()}")
print(f"   Polygonscan: https://polygonscan.com/tx/{tx_hash.hex()}")
print(f"\n⏳ Ожидание подтверждения...")

# Ждем подтверждения
receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

if receipt.status == 1:
    print(f"\n✅ Транзакция успешно подтверждена!")
    print(f"   Block: {receipt.blockNumber}")
    print(f"   Gas used: {receipt.gasUsed}")
else:
    print(f"\n❌ Транзакция не удалась")
