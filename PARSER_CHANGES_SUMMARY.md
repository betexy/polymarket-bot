# Что нужно изменить в парсере

## Важно: Я НЕ менял файлы парсера!

Я **НЕ изменял** файлы парсера. Я только создал **инструкции** и **примеры кода**.

Вам нужно **самостоятельно** модифицировать файлы парсера на вашем сервере.

## Какие файлы нужно изменить

### 1. `bot/configparser.py`

**Что добавить:** Новое поле в класс Config

**Где:** В класс `Config`

**Что добавить:**
```python
class Config(BaseSettings):
    # ... существующие поля ...
    polymarket_bot_url: str = ""  # URL бота: http://YOUR_SERVER_IP:8000/bets
    polymarket_bot_secret_key: str = ""  # Секретный ключ (опционально)
```

### 2. `bot/tasks/alerts.py`

**Что добавить:** 
1. Функцию `send_to_polymarket_bot()`
2. Вызовы этой функции в `send_data()`

**Где добавить функцию:** В конце файла (можно перед функцией `send_data()` или после)

**Что добавить:**
```python
async def send_to_polymarket_bot(
    config,
    bet_data: dict,
) -> None:
    """Отправка ставки на бот Polymarket"""
    from aiohttp import ClientSession
    from datetime import datetime
    
    if not config.polymarket_bot_url or bet_data.get("bookmaker") != "POLYMARKET":
        return
    
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

**Где добавить вызовы:** В функции `send_data()`, после создания `first_row_bets_app_data` и `second_row_bets_app_data`

**Что добавить:**
```python
# В функции send_data(), после обработки first_row_bets_app_data и second_row_bets_app_data:

# Отправка на Polymarket бот
if first_row_bets_app_data:
    await send_to_polymarket_bot(config, first_row_bets_app_data)

if second_row_bets_app_data:
    await send_to_polymarket_bot(config, second_row_bets_app_data)
```

### 3. `.env` файл парсера

**Что добавить:**
```env
POLYMARKET_BOT_URL=http://YOUR_SERVER_IP:8000/bets
POLYMARKET_BOT_SECRET_KEY=your_secret_key_here
```

**Где:** `YOUR_SERVER_IP` - IP адрес сервера, где запущен бот

**Важно:** `POLYMARKET_BOT_SECRET_KEY` должен совпадать с `API_SECRET_KEY` в боте!

## Пошаговая инструкция

### Шаг 1: Добавить поля в configparser.py

Откройте файл `bot/configparser.py` и добавьте два новых поля в класс `Config`:

```python
class Config(BaseSettings):
    redis_dsn: str
    secret_key: str
    login: str
    password: str
    allowed_betexy_bk: list[str]
    betburger_login: str
    betburger_password: str
    mode: Literal["LIVE", "PREMATCH"]
    full_time_only: bool
    storage_expire_time: int
    
    # ДОБАВИТЬ ЭТИ ДВА ПОЛЯ:
    polymarket_bot_url: str = ""
    polymarket_bot_secret_key: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
```

### Шаг 2: Добавить функцию в alerts.py

Откройте файл `bot/tasks/alerts.py` и добавьте функцию (можно в конец файла):

```python
async def send_to_polymarket_bot(
    config,
    bet_data: dict,
) -> None:
    """Отправка ставки на бот Polymarket"""
    from aiohttp import ClientSession
    from datetime import datetime
    
    if not config.polymarket_bot_url or bet_data.get("bookmaker") != "POLYMARKET":
        return
    
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

### Шаг 3: Добавить вызовы функции в send_data()

В функции `send_data()` найдите место, где обрабатываются `first_row_bets_app_data` и `second_row_bets_app_data`, и добавьте вызовы:

```python
async def send_data(
    config: Config,
    betexy_data: dict | None,
    first_row_bets_app_data: dict | None = None,
    second_row_bets_app_data: dict | None = None,
) -> None:
    # ... существующий код ...
    
    # ДОБАВИТЬ ПОСЛЕ ОБРАБОТКИ first_row_bets_app_data и second_row_bets_app_data:
    
    # Отправка на Polymarket бот
    if first_row_bets_app_data:
        await send_to_polymarket_bot(config, first_row_bets_app_data)
    
    if second_row_bets_app_data:
        await send_to_polymarket_bot(config, second_row_bets_app_data)
```

### Шаг 4: Добавить настройки в .env

Добавьте в `.env` файл парсера:

```env
POLYMARKET_BOT_URL=http://YOUR_SERVER_IP:8000/bets
POLYMARKET_BOT_SECRET_KEY=your_secret_key_here
```

Где:
- `YOUR_SERVER_IP` - IP адрес сервера, где запущен бот
- `your_secret_key_here` - тот же ключ, что и `API_SECRET_KEY` в боте

## Резюме изменений

### Файлы для изменения:
1. ✅ `bot/configparser.py` - добавить 2 поля
2. ✅ `bot/tasks/alerts.py` - добавить функцию и вызовы
3. ✅ `.env` - добавить 2 переменные

### Ничего не удаляем, только добавляем!

Все изменения - это **добавление кода**, никакие существующие функции не изменяются.

## Проверка

После изменений:
1. Проверьте синтаксис: `python -m py_compile bot/configparser.py bot/tasks/alerts.py`
2. Запустите парсер
3. Проверьте логи - должны появляться сообщения о отправке на polymarket bot
4. Проверьте логи бота - должны приходить запросы от парсера

## Готовый пример кода

См. файл `parser_patch_example.py` в папке `polymarket_bot/` - там есть пример функции, которую нужно добавить.
