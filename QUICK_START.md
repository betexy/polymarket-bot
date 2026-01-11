# Быстрый старт

## Краткая инструкция по запуску

### 1. На сервере с ботом

```bash
# Установка зависимостей
cd /root/polymarket_bot
pip install -r requirements.txt

# Создание .env файла
cp .env.example .env
# Отредактируйте .env и укажите:
# - POLYMARKET_API_KEY
# - POLYMARKET_API_SECRET
# - API_SECRET_KEY (для защиты endpoint)

# Запуск бота
python -m app.main
```

Бот будет доступен по адресу: `http://YOUR_SERVER_IP:8000`

### 2. На сервере с парсером

#### 2.1 Добавить в конфигурацию парсера

В файл `bot/configparser.py` добавить:

```python
class Config(BaseSettings):
    # ... существующие поля ...
    polymarket_bot_url: str = ""  # URL бота: http://YOUR_SERVER_IP:8000/bets
    polymarket_bot_secret_key: str = ""  # Секретный ключ (опционально)
```

В `.env` файл парсера добавить:

```
POLYMARKET_BOT_URL=http://YOUR_SERVER_IP:8000/bets
POLYMARKET_BOT_SECRET_KEY=your_secret_key_here
```

#### 2.2 Модифицировать отправку данных

В файле `bot/tasks/alerts.py` в функцию `send_data()` добавить:

```python
# После создания first_row_bets_app_data и second_row_bets_app_data:

# Отправка на Polymarket бот
if first_row_bets_app_data and first_row_bets_app_data.get("bookmaker") == "POLYMARKET":
    await send_to_polymarket_bot(config, first_row_bets_app_data)

if second_row_bets_app_data and second_row_bets_app_data.get("bookmaker") == "POLYMARKET":
    await send_to_polymarket_bot(config, second_row_bets_app_data)
```

И добавить функцию (можно в конец файла):

```python
async def send_to_polymarket_bot(config, bet_data: dict) -> None:
    """Отправка ставки на бот Polymarket"""
    if not config.polymarket_bot_url or bet_data.get("bookmaker") != "POLYMARKET":
        return
    
    from aiohttp import ClientSession
    from datetime import datetime
    
    async with ClientSession() as session:
        try:
            headers = {"Content-Type": "application/json"}
            if config.polymarket_bot_secret_key:
                headers["X-Secret-Key"] = config.polymarket_bot_secret_key
            
            async with session.post(
                config.polymarket_bot_url,
                json=bet_data,
                headers=headers,
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    print(f"{datetime.now():%d.%m.%Y %H:%M:%S} > sent to polymarket bot > {response_data=}")
                else:
                    error_text = await response.text()
                    print(f"{datetime.now():%d.%m.%Y %H:%M:%S} > polymarket bot error {response.status}: {error_text}")
        except Exception as ex:
            print(f"{datetime.now():%d.%m.%Y %H:%M:%S} > send to polymarket bot error > {ex}")
```

### 3. Проверка работы

#### Проверка бота:

```bash
# Проверка health endpoint
curl http://YOUR_SERVER_IP:8000/bets/health

# Тестовая отправка ставки
curl -X POST http://YOUR_SERVER_IP:8000/bets/ \
  -H "Content-Type: application/json" \
  -H "X-Secret-Key: your_secret_key_here" \
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

#### Проверка парсера:

1. Запустите парсер
2. Проверьте логи - должны появляться сообщения о отправке на polymarket bot
3. Проверьте логи бота - должны приходить запросы от парсера

### 4. Важные замечания

⚠️ **ВНИМАНИЕ**: Перед запуском в продакшене:

1. **API Polymarket**: Реализовать реальные endpoints в `app/services/polymarket_client.py`
   - Изучить документацию: https://docs.polymarket.com/
   - Протестировать с реальными API ключами
   - Уточнить формат данных

2. **Маппинг markets**: Доразработать логику поиска и сопоставления markets
   - В `app/services/data_mapper.py`
   - В `app/services/order_manager.py`

3. **Безопасность**:
   - Использовать HTTPS (через nginx)
   - Настроить firewall
   - Использовать сильные секретные ключи

4. **Тестирование**:
   - Начните с тестовых ставок
   - Проверяйте логи
   - Мониторьте баланс

## Структура URL

- Бот API: `http://YOUR_SERVER_IP:8000/bets/`
- Health check: `http://YOUR_SERVER_IP:8000/bets/health`
- Batch endpoint: `http://YOUR_SERVER_IP:8000/bets/batch`

## Логи

Логи бота выводятся в stdout. Для продакшена рекомендуется:
- Настроить ротацию логов
- Использовать systemd journal
- Отправлять логи во внешний сервис (например, ELK)
