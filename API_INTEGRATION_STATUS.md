# Статус интеграции с Polymarket API

## Реализовано

### 1. Gamma API Integration ✅
- Клиент для работы с Gamma API
- Поиск событий (events) по названиям команд
- Получение markets для событий
- Получение информации о market

**Endpoints используемые:**
- `GET /events` - поиск событий
- `GET /markets?event_id=<id>` - получение markets события
- `GET /markets/<market_id>` - информация о market

### 2. Data Mapping ✅
- Маппинг спортов (FOOTBALL → soccer, etc.)
- Маппинг рынков:
  - **1X2** (ONE_TWO) - Match Winner / Match Result
  - **Тотал** (TOTAL) - Over/Under
  - **Фора** (HDP) - Handicap / Spread
  - **Индивидуальный тотал** (T1_TOTAL, T2_TOTAL) - Individual Team Total
- Конвертация коэффициентов в вероятности/цены
- Поиск по точным названиям команд

### 3. Market Search ✅
- Поиск событий по названиям команд (homeTeam vs awayTeam)
- Фильтрация markets по типу
- Проверка pivot для TOTAL и HDP markets
- Проверка target для соответствия исходу

### 4. HTTP API Server ✅
- Endpoint для приема ставок от парсера
- Защита через X-Secret-Key
- Обработка ошибок
- Логирование

## Требует доработки

### 1. CLOB API Integration ❌
Для размещения ордеров требуется интеграция с CLOB API:
- Аутентификация через Web3 кошелек
- Подпись транзакций
- Размещение buy/sell ордеров
- Отмена ордеров
- Управление позициями

**Документация:** https://docs.polymarket.com/developers/central-limit-order-book/

### 2. Outcome Mapping ❌
Требуется уточнить:
- Формат outcomes в Polymarket markets
- Маппинг YES/NO на конкретные outcomes
- Работа с множественными outcomes (например, для 1X2 с Draw)

### 3. Price Format ❌
Требуется уточнить:
- Формат цен в CLOB API (центы, вероятности, другие)
- Минимальные/максимальные значения
- Комиссии и spread

## Тестирование

Для тестирования текущей реализации:

```bash
# 1. Настроить .env файл
cp .env.example .env
# Указать API ключи

# 2. Запустить бота
python -m app.main

# 3. Отправить тестовую ставку
curl -X POST http://localhost:8000/bets/ \
  -H "Content-Type: application/json" \
  -d '{
    "bookmaker": "POLYMARKET",
    "market": "ONE_TWO",
    "target": "ONE",
    "homeTeam": "Team 1",
    "awayTeam": "Team 2",
    "league": "Test League",
    "sport": "FOOTBALL",
    "coef": "2.50",
    "surebet_profit": 5.0,
    "mode": "LIVE",
    "timeValue": "FULL_TIME"
  }'
```

## Следующие шаги

1. Изучить CLOB API документацию
2. Реализовать CLOB клиент
3. Интегрировать размещение ордеров
4. Протестировать на тестовой сети
5. Запустить в продакшене
