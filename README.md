# Polymarket Bot

Бот для автоматического размещения ордеров на Polymarket на основе ставок от парсера BetBurger.

## Описание

Этот бот:
- Принимает ставки от парсера через HTTP API
- Обрабатывает данные ставок
- Ищет соответствующие markets на Polymarket
- Размещает ордера на Polymarket через API

## Структура проекта

```
polymarket_bot/
├── app/
│   ├── api/              # API endpoints
│   │   └── bets.py       # Endpoint для приема ставок
│   ├── config/           # Конфигурация
│   │   └── settings.py   # Настройки приложения
│   ├── models/           # Модели данных
│   │   └── bet.py        # Модель ставки
│   ├── services/         # Бизнес-логика
│   │   ├── polymarket_client.py  # Клиент Polymarket API
│   │   ├── data_mapper.py        # Маппинг данных
│   │   └── order_manager.py      # Управление ордерами
│   └── main.py           # Точка входа и FastAPI приложение
├── .env.example          # Пример файла конфигурации
├── requirements.txt      # Зависимости Python
└── README.md            # Этот файл
```

## Установка

### 1. Клонирование и установка зависимостей

```bash
cd polymarket_bot
pip install -r requirements.txt
```

### 2. Настройка конфигурации

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```env
# Polymarket API настройки
POLYMARKET_API_KEY=your_api_key_here
POLYMARKET_API_SECRET=your_api_secret_here
POLYMARKET_API_URL=https://api.polymarket.com

# API сервер настройки
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=your_secret_key_here

# Логирование
LOG_LEVEL=INFO

# Настройки ордеров
DEFAULT_ORDER_SIZE=10.0
MIN_PROFIT_PERCENT=0.0
```

### 3. Получение API ключей Polymarket

1. Зарегистрируйтесь на Polymarket
2. Создайте API ключ в настройках аккаунта
3. Укажите ключи в `.env` файле

**ВАЖНО**: На момент разработки точная документация API Polymarket может отличаться. Необходимо:
- Изучить официальную документацию: https://docs.polymarket.com/
- Уточнить endpoints и формат данных
- Адаптировать код в `app/services/polymarket_client.py`

## Запуск

### Разработка

```bash
python -m app.main
```

или

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Продакшен

Рекомендуется использовать systemd или supervisor для управления процессом.

Пример systemd service (`/etc/systemd/system/polymarket-bot.service`):

```ini
[Unit]
Description=Polymarket Bot API
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/polymarket_bot
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## API Endpoints

### POST /bets/
Прием ставки от парсера

**Заголовки:**
- `X-Secret-Key` (опционально): Секретный ключ для защиты

**Тело запроса:**
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
    "timeValue": "FULL_TIME"
}
```

**Ответ:**
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

### POST /bets/batch
Прием нескольких ставок одновременно

### GET /bets/health
Проверка работоспособности API

### GET /
Информация о сервисе

## Интеграция с парсером

См. файл `PARSER_MODIFICATION_GUIDE.md` для инструкций по модификации парсера.

## Настройка Nginx (опционально)

Для продакшена рекомендуется использовать nginx как reverse proxy:

```nginx
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Важные замечания

1. **API Polymarket**: Код содержит заглушки для API вызовов. Необходимо:
   - Изучить реальную документацию API
   - Реализовать реальные endpoints
   - Протестировать с реальными credentials

2. **Маппинг данных**: Логика маппинга ставок на markets Polymarket требует доработки:
   - Уточнить формат поиска markets
   - Реализовать точное сопоставление событий
   - Обработать различные типы markets

3. **Безопасность**:
   - Используйте секретный ключ для защиты API
   - Настройте firewall
   - Используйте HTTPS в продакшене

4. **Тестирование**:
   - Тестируйте с небольшими суммами
   - Проверяйте логи
   - Мониторьте баланс

## Разработка

### Добавление новых типов markets

Отредактируйте `app/services/data_mapper.py`:
- Добавьте новые типы в `MARKET_KEYWORDS`
- Реализуйте логику маппинга в `map_target_to_outcome()`

### Расширение функционала

- Добавьте новые endpoints в `app/api/`
- Реализуйте дополнительную логику в `app/services/`
- Обновите модели в `app/models/`

## Логирование

Логи выводятся в stdout с уровнем, указанным в `LOG_LEVEL`.

Для продакшена рекомендуется настроить ротацию логов или отправку в внешний сервис.

## Поддержка

При возникновении проблем:
1. Проверьте логи
2. Убедитесь, что API ключи корректны
3. Проверьте подключение к Polymarket API
4. Проверьте формат данных от парсера
