# Изучение CLOB API Polymarket

## Обзор

**CLOB (Central Limit Order Book) API** - это API для размещения и управления ордерами на Polymarket.

**Важно:** CLOB API отличается от Gamma API:
- **Gamma API** - только чтение данных о markets (read-only)
- **CLOB API** - размещение ордеров, управление позициями (read-write)

## Основные компоненты

### 1. Аутентификация

CLOB API использует два уровня аутентификации:

#### Уровень L1 (Private Key Authentication)
- Использует **приватный ключ кошелька** для подписания сообщений EIP-712
- Доказывает владение и контроль над приватным ключом
- Требуется для создания/получения API-ключей
- Используется для локального подписания ордеров

#### Уровень L2 (API Key Authentication)
- Использует **API-ключи** (apiKey, secret, passphrase)
- Используется для аутентификации запросов к CLOB
- Создаются через L1 аутентификацию

### 2. Официальный Python клиент

Polymarket предоставляет официальную библиотеку: **`py-clob-client`**

**GitHub:** https://github.com/Polymarket/py-clob-client

**Установка:**
```bash
pip install py-clob-client
```

**Зависимости:**
- eth-account (для работы с кошельками)
- eth-keys
- другие зависимости для работы с блокчейном

## Инициализация клиента

### Базовый пример

```python
from py_clob_client.client import ClobClient

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet
PRIVATE_KEY = "ваш_приватный_ключ"  # БЕЗ 0x префикса или с ним

# Создание клиента с приватным ключом
client = ClobClient(
    host=HOST,
    chain_id=CHAIN_ID,
    key=PRIVATE_KEY
)

# Создание или получение API-ключей (L2)
api_creds = client.create_or_derive_api_key()

# Установка API-ключей для клиента
client.set_api_creds(api_creds)
```

### Использование существующих API ключей

Если у вас уже есть API ключи (apiKey, secret, passphrase):

```python
from py_clob_client.client import ClobClient
from py_clob_client.utilities import create_api_key_credential_object

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

# Создание объекта с API ключами
api_creds = create_api_key_credential_object(
    api_key="your_api_key",
    api_secret="your_api_secret",
    api_passphrase="your_api_passphrase"
)

# Создание клиента (приватный ключ всё равно нужен для некоторых операций)
client = ClobClient(
    host=HOST,
    chain_id=CHAIN_ID,
    key=PRIVATE_KEY,
    api_creds=api_creds
)
```

## Основные операции

### 1. Размещение ордера

```python
response = client.create_order(
    token_id="YOUR_TOKEN_ID",  # ID токена из market
    price=0.65,                # Цена (0.01 - 0.99)
    size=10,                   # Размер ордера
    side="BUY"                 # или "SELL"
)

print(f"Order placed! ID: {response['orderID']}")
```

**Параметры:**
- `token_id` - ID токена (outcome token) из market
- `price` - Цена (от 0.01 до 0.99, где 0.50 = 50% вероятность)
- `size` - Размер ордера (в токенах)
- `side` - "BUY" или "SELL"

### 2. Отмена ордера

```python
client.cancel_order(order_id="ORDER_ID")
```

### 3. Получение информации об ордерах

```python
# Получить все открытые ордера
orders = client.get_orders()

# Получить конкретный ордер
order = client.get_order(order_id="ORDER_ID")
```

### 4. Получение позиций

```python
positions = client.get_positions()
```

### 5. Получение баланса

```python
balance = client.get_balance()
```

## Получение Token ID из Market

Для размещения ордера нужен `token_id`. Его можно получить из market данных:

1. Через Gamma API получить market
2. В market есть поле `tokens` или `outcomes`
3. Каждый outcome/token имеет свой ID

Пример структуры market:
```json
{
  "id": "market_id",
  "tokens": [
    {
      "token_id": "0x1234...",
      "outcome": "Yes"
    },
    {
      "token_id": "0x5678...",
      "outcome": "No"
    }
  ]
}
```

## Важные моменты

### 1. Приватный ключ
- ⚠️ **НЕ храните приватный ключ в коде!**
- Используйте переменные окружения
- Используйте отдельный кошелек для бота
- Ограничьте суммы на кошельке

### 2. Цены
- Формат: от 0.01 до 0.99
- 0.01 = 1% вероятность
- 0.50 = 50% вероятность
- 0.99 = 99% вероятность

### 3. Размер ордера
- В токенах (shares)
- Минимальный размер зависит от market
- Максимальный - ограничен балансом

### 4. Chain ID
- **137** - Polygon mainnet (продакшен)
- **80001** - Mumbai testnet (тестирование)

### 5. Host
- **https://clob.polymarket.com** - продакшен
- **https://clob-staging.polymarket.com** - staging (если доступен)

## Процесс работы

1. **Инициализация клиента** с приватным ключом
2. **Создание/получение API ключей** (L2)
3. **Поиск market** через Gamma API
4. **Получение token_id** из market данных
5. **Размещение ордера** через CLOB API
6. **Мониторинг ордера** (статус, исполнение)
7. **Отмена ордера** (если нужно)

## Пример полного цикла

```python
from py_clob_client.client import ClobClient
import os

# 1. Инициализация
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=os.getenv("PRIVATE_KEY")
)

# 2. Получение API ключей
api_creds = client.create_or_derive_api_key()
client.set_api_creds(api_creds)

# 3. Получение token_id (из Gamma API или другого источника)
token_id = "0x1234..."  # ID токена "Yes" из market

# 4. Размещение ордера
response = client.create_order(
    token_id=token_id,
    price=0.65,
    size=10,
    side="BUY"
)

print(f"Order ID: {response['orderID']}")

# 5. Проверка статуса
order = client.get_order(order_id=response['orderID'])
print(f"Status: {order['status']}")
```

## Ресурсы

- **Документация CLOB API:** https://docs.polymarket.com/developers/CLOB/introduction
- **Аутентификация:** https://docs.polymarket.com/developers/CLOB/authentication
- **Быстрый старт:** https://docs.polymarket.com/developers/CLOB/quickstart
- **Python клиент:** https://github.com/Polymarket/py-clob-client
- **TypeScript клиент:** https://github.com/Polymarket/clob-client

## Следующие шаги

1. Изучить структуру market данных (tokens/outcomes)
2. Реализовать интеграцию с py-clob-client
3. Добавить обработку ошибок
4. Реализовать логику получения token_id из market
5. Протестировать на тестовой сети
