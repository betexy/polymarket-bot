# Инструкция по модификации парсера для отправки ставок

## Обзор

Парсер (`bot_betburger_pre`) должен быть модифицирован для отправки ставок на API бота Polymarket.

## Способ интеграции

Парсер уже отправляет данные на различные endpoints в функции `send_data()` в файле `bot/tasks/alerts.py`.

Нужно добавить отправку данных на endpoint бота Polymarket.

## Модификация парсера

### Шаг 1: Добавить URL бота в конфигурацию

В файле `bot/configparser.py` добавить новое поле:

```python
class Config(BaseSettings):
    # ... существующие поля ...
    polymarket_bot_url: str  # URL бота, например: http://YOUR_SERVER_IP:8000/bets
```

И в `.env` файле парсера добавить:

```
POLYMARKET_BOT_URL=http://YOUR_SERVER_IP:8000/bets
# Опционально, для защиты endpoint:
POLYMARKET_BOT_SECRET_KEY=your_secret_key_here
```

### Шаг 2: Модифицировать функцию send_data()

В файле `bot/tasks/alerts.py` в функции `send_data()` добавить отправку на бот Polymarket:

```python
async def send_data(
    config: Config,
    betexy_data: dict | None,
    first_row_bets_app_data: dict | None = None,
    second_row_bets_app_data: dict | None = None,
) -> None:
    url = f"https://bsa.betexy.com/bet?secret={config.secret_key}"
    bets_app_url = f"http://91.184.243.131/api/bets"
    new_bets_app_url = "http://77.110.98.233/api/bets"
    new_bets_app_url2 = "http://89.110.95.139/api/bets"
    
    # Добавить URL бота Polymarket
    polymarket_bot_url = config.polymarket_bot_url

    async with ClientSession(
        auth=BasicAuth(login=config.login, password=config.password)
    ) as session:
        # ... существующий код для betexy_data ...
        
        # Отправка на бот Polymarket (только для ставок на Polymarket)
        if first_row_bets_app_data:
            # ... существующий код ...
            
            # Добавить отправку на Polymarket бот
            if first_row_bets_app_data.get("bookmaker") == "POLYMARKET":
                try:
                    headers = {}
                    if hasattr(config, 'polymarket_bot_secret_key') and config.polymarket_bot_secret_key:
                        headers["X-Secret-Key"] = config.polymarket_bot_secret_key
                    
                    async with session.post(
                        polymarket_bot_url, 
                        json=first_row_bets_app_data, 
                        headers=headers,
                        ssl=False
                    ) as response:
                        response_data = await response.json()
                except Exception as ex:
                    print(
                        f"{datetime.now():%d.%m.%Y %H:%M:%S} > send request to polymarket bot error > {first_row_bets_app_data=} {ex}"
                    )
                else:
                    print(
                        f"{datetime.now():%d.%m.%Y %H:%M:%S} > send request to polymarket bot > {first_row_bets_app_data=} {response_data=}"
                    )

        if second_row_bets_app_data:
            # ... существующий код ...
            
            # Добавить отправку на Polymarket бот
            if second_row_bets_app_data.get("bookmaker") == "POLYMARKET":
                try:
                    headers = {}
                    if hasattr(config, 'polymarket_bot_secret_key') and config.polymarket_bot_secret_key:
                        headers["X-Secret-Key"] = config.polymarket_bot_secret_key
                    
                    async with session.post(
                        polymarket_bot_url, 
                        json=second_row_bets_app_data, 
                        headers=headers,
                        ssl=False
                    ) as response:
                        response_data = await response.json()
                except Exception as ex:
                    print(
                        f"{datetime.now():%d.%m.%Y %H:%M:%S} > send request to polymarket bot error > {second_row_bets_app_data=} {ex}"
                    )
                else:
                    print(
                        f"{datetime.now():%d.%m.%Y %H:%M:%S} > send request to polymarket bot > {second_row_bets_app_data=} {response_data=}"
                    )
```

### Альтернативный вариант: отдельная функция

Можно создать отдельную функцию для отправки на Polymarket бот:

```python
async def send_to_polymarket_bot(
    config: Config,
    bet_data: dict,
) -> None:
    """Отправка ставки на бот Polymarket"""
    if bet_data.get("bookmaker") != "POLYMARKET":
        return
    
    polymarket_bot_url = config.polymarket_bot_url
    
    async with ClientSession() as session:
        try:
            headers = {"Content-Type": "application/json"}
            if hasattr(config, 'polymarket_bot_secret_key') and config.polymarket_bot_secret_key:
                headers["X-Secret-Key"] = config.polymarket_bot_secret_key
            
            async with session.post(
                polymarket_bot_url,
                json=bet_data,
                headers=headers,
                ssl=False
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    print(
                        f"{datetime.now():%d.%m.%Y %H:%M:%S} > sent to polymarket bot > {response_data=}"
                    )
                else:
                    error_text = await response.text()
                    print(
                        f"{datetime.now():%d.%m.%Y %H:%M:%S} > polymarket bot error {response.status}: {error_text}"
                    )
        except Exception as ex:
            print(
                f"{datetime.now():%d.%m.%Y %H:%M:%S} > send to polymarket bot error > {bet_data=} {ex}"
            )
```

И затем вызвать её в `send_data()`:

```python
# В send_data() после обработки first_row_bets_app_data и second_row_bets_app_data:
await send_to_polymarket_bot(config, first_row_bets_app_data)
await send_to_polymarket_bot(config, second_row_bets_app_data)
```

## Формат данных

Парсер уже отправляет данные в правильном формате, который соответствует модели `BetData` бота:

```python
{
    "bookmaker": "POLYMARKET",
    "second_bookmaker": "...",
    "market": "ONE_TWO",
    "target": "ONE",
    "pivot": None,
    "timeValue": "FULL_TIME",
    "homeTeam": "Team 1",
    "awayTeam": "Team 2",
    "league": "League Name",
    "sport": "FOOTBALL",
    "coef": "2.50",
    "surebet_profit": 5.2,
    "mode": "LIVE",
    "stake": "100",
    "direct_link": "",
    "bk_event_native_id": "",
}
```

## Тестирование

После модификации парсера:

1. Убедитесь, что бот Polymarket запущен и доступен
2. Проверьте подключение: `curl http://YOUR_SERVER_IP:8000/bets/health`
3. Запустите парсер и проверьте логи на наличие ошибок
4. Проверьте логи бота на получение ставок

## Безопасность

Рекомендуется:
1. Использовать `X-Secret-Key` заголовок для защиты endpoint
2. Настроить firewall для ограничения доступа только с IP парсера
3. Использовать HTTPS в продакшене (через nginx reverse proxy)
