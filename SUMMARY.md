# Резюме проекта Polymarket Bot

## Что было сделано

Создан полнофункциональный бот для приема ставок от парсера и размещения ордеров на Polymarket через API.

### Структура проекта

```
polymarket_bot/
├── app/
│   ├── api/
│   │   └── bets.py              # HTTP API endpoints для приема ставок
│   ├── config/
│   │   └── settings.py          # Конфигурация приложения
│   ├── models/
│   │   └── bet.py               # Модель данных ставки (Pydantic)
│   ├── services/
│   │   ├── polymarket_client.py # Клиент для работы с Polymarket API
│   │   ├── data_mapper.py       # Маппинг данных парсера → Polymarket
│   │   └── order_manager.py     # Управление ордерами
│   └── main.py                  # FastAPI приложение (точка входа)
├── .env.example                 # Пример конфигурации
├── requirements.txt             # Зависимости Python
├── README.md                    # Полная документация
├── PARSER_MODIFICATION_GUIDE.md # Инструкция по модификации парсера
├── QUICK_START.md              # Быстрый старт
└── parser_patch_example.py     # Пример кода для парсера
```

### Основные компоненты

#### 1. HTTP API Server (FastAPI)
- **Endpoint**: `POST /bets/` - прием одной ставки
- **Endpoint**: `POST /bets/batch` - прием нескольких ставок
- **Endpoint**: `GET /bets/health` - проверка работоспособности
- Защита через `X-Secret-Key` заголовок
- CORS настроен для работы с внешними серверами

#### 2. Polymarket Client
- Абстракция для работы с Polymarket API
- Методы для поиска markets, создания/отмены ордеров
- Готов к интеграции с реальным API (нужно только реализовать endpoints)

#### 3. Data Mapper
- Маппинг спортов (FOOTBALL → soccer, etc.)
- Конвертация коэффициентов в вероятности/цены
- Генерация поисковых запросов для markets
- Маппинг типов ставок (ONE_TWO, TOTAL, HDP, etc.)

#### 4. Order Manager
- Обработка ставок от парсера
- Поиск соответствующих markets на Polymarket
- Расчет параметров ордеров
- Размещение ордеров через API

### Интеграция с парсером

Парсер должен:
1. Отправлять POST запросы на `http://SERVER_IP:8000/bets/`
2. Передавать данные в формате JSON (соответствует модели `BetData`)
3. Опционально использовать `X-Secret-Key` заголовок для защиты

Инструкции по модификации парсера находятся в `PARSER_MODIFICATION_GUIDE.md`

## Что нужно доработать

### Критично (для работы в продакшене):

1. **Polymarket API Integration**
   - Изучить реальную документацию API: https://docs.polymarket.com/
   - Реализовать реальные endpoints в `app/services/polymarket_client.py`
   - Протестировать с реальными API ключами
   - Уточнить формат данных (markets, orders, prices)

2. **Поиск и сопоставление Markets**
   - Уточнить API для поиска markets
   - Реализовать точное сопоставление событий (команды, лиги)
   - Обработать различные типы markets (ONE_TWO, TOTAL, HDP, etc.)
   - Учесть pivot для HDP/TOTAL markets

3. **Обработка цен и размеров**
   - Уточнить формат цен в Polymarket (вероятности, центы, etc.)
   - Реализовать правильную конвертацию коэффициентов
   - Учесть комиссии и spread

### Рекомендуется (для улучшения):

4. **Обработка ошибок**
   - Добавить retry механизм для failed requests
   - Обработать rate limits API
   - Добавить очередь для ордеров при недоступности API

5. **Мониторинг и логирование**
   - Настроить структурированное логирование
   - Добавить метрики (количество ордеров, успешность, etc.)
   - Интеграция с системами мониторинга

6. **Безопасность**
   - Настроить HTTPS (через nginx)
   - Добавить rate limiting
   - Настроить firewall

7. **Тестирование**
   - Unit тесты для маппинга данных
   - Интеграционные тесты с mock API
   - End-to-end тесты

## Настройка

### На сервере с ботом:

1. Установить зависимости: `pip install -r requirements.txt`
2. Создать `.env` файл (см. `.env.example`)
3. Указать API ключи Polymarket
4. Запустить: `python -m app.main`

### На сервере с парсером:

1. Добавить в конфигурацию:
   - `POLYMARKET_BOT_URL=http://SERVER_IP:8000/bets`
   - `POLYMARKET_BOT_SECRET_KEY=your_secret_key`

2. Модифицировать `bot/tasks/alerts.py` (см. `PARSER_MODIFICATION_GUIDE.md`)

3. Добавить функцию отправки на бот

## Формат данных

### Ставка от парсера:

```json
{
    "bookmaker": "POLYMARKET",
    "market": "ONE_TWO",
    "target": "ONE",
    "homeTeam": "Team 1",
    "awayTeam": "Team 2",
    "league": "League Name",
    "sport": "FOOTBALL",
    "coef": "2.50",
    "surebet_profit": 5.2,
    "mode": "LIVE",
    "timeValue": "FULL_TIME",
    "pivot": null
}
```

### Ответ от бота:

```json
{
    "status": "received",
    "bet_processed": true,
    "result": {
        "status": "success",
        "order_id": "...",
        "market_id": "..."
    }
}
```

## Следующие шаги

1. Получить доступ к Polymarket API и изучить документацию
2. Реализовать реальные endpoints в `polymarket_client.py`
3. Протестировать с тестовыми данными
4. Настроить парсер для отправки данных
5. Провести интеграционное тестирование
6. Запустить в продакшене с мониторингом

## Документация

- `README.md` - полная документация проекта
- `PARSER_MODIFICATION_GUIDE.md` - инструкция по модификации парсера
- `QUICK_START.md` - быстрый старт
- `parser_patch_example.py` - пример кода для парсера
