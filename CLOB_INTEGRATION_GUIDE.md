# Руководство по интеграции CLOB API

## Обзор

CLOB API интегрирован в бота для размещения ордеров на Polymarket. Интеграция использует официальную библиотеку `py-clob-client`.

## Установка зависимостей

```bash
pip install py-clob-client eth-account
```

Или установите все зависимости:

```bash
pip install -r requirements.txt
```

## Настройка

### 1. Приватный ключ кошелька

⚠️ **КРИТИЧЕСКИ ВАЖНО:**
- Используйте **отдельный кошелек** для бота
- **НЕ используйте** основной кошелек с большими средствами
- Храните приватный ключ в безопасности
- Используйте переменные окружения

Добавьте в `.env` файл:

```env
POLYMARKET_PRIVATE_KEY=your_private_key_here
```

**Формат ключа:** Может быть с префиксом `0x` или без него, библиотека обработает оба варианта.

### 2. API ключи (опционально)

Если у вас уже есть API ключи от Polymarket, их можно использовать:

```env
POLYMARKET_API_KEY=your_api_key
POLYMARKET_API_SECRET=your_api_secret
POLYMARKET_API_PASSPHRASE=your_passphrase
```

Если ключи не указаны, они будут созданы автоматически при первой инициализации.

### 3. Другие настройки

```env
POLYMARKET_CLOB_HOST=https://clob.polymarket.com
POLYMARKET_CHAIN_ID=137  # 137 для mainnet, 80001 для testnet
```

## Как это работает

### Процесс размещения ордера:

1. **Парсер отправляет ставку** → `POST /bets/`
2. **Бот получает ставку** и проверяет условия
3. **Поиск market** через Gamma API:
   - Поиск события по названиям команд
   - Получение markets для события
   - Фильтрация по типу market (1X2, TOTAL, HDP, etc.)
4. **Извлечение token_id** из market данных:
   - Находим нужный outcome (YES/NO)
   - Получаем token_id для этого outcome
5. **Размещение ордера** через CLOB API:
   - Используем token_id
   - Рассчитываем цену из коэффициента
   - Размещаем ордер

### Структура данных market

Market из Gamma API содержит информацию о токенах (outcomes):

```json
{
  "id": "market_id",
  "title": "Market Title",
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

Метод `get_token_id_from_market()` извлекает нужный token_id.

## Использование

### Автоматическое размещение

Бот автоматически размещает ордера при получении ставок от парсера, если:
- CLOB клиент инициализирован
- Найден соответствующий market
- Извлечен token_id

### Ручное размещение ордера (пример)

```python
from app.services.clob_client import PolymarketCLOBClient
from app.config.settings import Settings

settings = Settings()
clob = PolymarketCLOBClient(settings)

# Размещение ордера
response = clob.create_order(
    token_id="0x1234...",
    price=0.65,
    size=10,
    side="BUY"
)

print(f"Order ID: {response['orderID']}")
```

### Отмена ордера

```python
clob.cancel_order(order_id="ORDER_ID")
```

### Проверка статуса

```python
order = clob.get_order(order_id="ORDER_ID")
print(f"Status: {order['status']}")
```

### Получение баланса

```python
balance = clob.get_balance()
print(f"Balance: {balance}")
```

## Обработка ошибок

Бот обрабатывает следующие ошибки:

1. **CLOB клиент не инициализирован:**
   - Возвращает информацию о market, но не размещает ордер
   - Логирует предупреждение

2. **Token ID не найден:**
   - Возвращает ошибку "token_id_not_found"
   - Логирует предупреждение

3. **Ошибка размещения ордера:**
   - Логирует ошибку с деталями
   - Возвращает статус "error" с описанием

## Тестирование

### 1. Проверка инициализации

При запуске бота проверьте логи:
```
INFO - CLOB client initialized with API credentials
```

Если видите ошибки - проверьте настройки.

### 2. Тестовая ставка

Отправьте тестовую ставку и проверьте логи:
```bash
curl -X POST http://localhost:8000/bets/ \
  -H "Content-Type: application/json" \
  -H "X-Secret-Key: YOUR_SECRET" \
  -d '{
    "bookmaker": "POLYMARKET",
    "market": "ONE_TWO",
    "target": "ONE",
    "homeTeam": "Team 1",
    "awayTeam": "Team 2",
    "sport": "FOOTBALL",
    "coef": "2.50",
    "mode": "LIVE",
    "timeValue": "FULL_TIME"
  }'
```

### 3. Проверка ордеров

Используйте методы клиента для проверки:
```python
orders = clob.get_orders()
positions = clob.get_positions()
balance = clob.get_balance()
```

## Безопасность

⚠️ **ВАЖНО:**

1. **Приватный ключ:**
   - НЕ храните в коде
   - НЕ коммитьте в git
   - Используйте переменные окружения
   - Ограничьте права доступа к файлу .env

2. **Кошелек:**
   - Используйте отдельный кошелек
   - Ограничьте суммы на кошельке
   - Регулярно проверяйте баланс
   - Настройте уведомления о транзакциях

3. **API ключи:**
   - Храните в безопасности
   - Не передавайте третьим лицам
   - Регулярно обновляйте

## Troubleshooting

### Ошибка: "py-clob-client not available"

**Решение:** Установите библиотеку:
```bash
pip install py-clob-client
```

### Ошибка: "Private key not configured"

**Решение:** Добавьте `POLYMARKET_PRIVATE_KEY` в `.env` файл

### Ошибка: "CLOB client is not available"

**Проверьте:**
- Установлена ли библиотека
- Настроен ли приватный ключ
- Правильный ли формат ключа
- Проверьте логи для деталей

### Ошибка при размещении ордера

**Возможные причины:**
- Недостаточно средств на балансе
- Неправильный token_id
- Цена вне допустимого диапазона (0.01-0.99)
- Market закрыт или неактивен

**Решение:** Проверьте логи для детальной информации об ошибке

## Дополнительные ресурсы

- **Документация CLOB API:** https://docs.polymarket.com/developers/CLOB/introduction
- **Python клиент:** https://github.com/Polymarket/py-clob-client
- **CLOB API Study:** CLOB_API_STUDY.md
- **Статус интеграции:** API_INTEGRATION_STATUS.md
