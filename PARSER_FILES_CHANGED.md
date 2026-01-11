# Измененные файлы парсера

## Файлы для замены на сервере

Я изменил следующие файлы в папке `bot_betburger_pre/bot_betburger_pre/`:

### 1. `bot/configparser.py`

**Изменение:** Добавлены два новых поля в класс Config:
- `polymarket_bot_url: str = ""`
- `polymarket_bot_secret_key: str = ""`

### 2. `bot/tasks/alerts.py`

**Изменение:** Добавлена отправка на Polymarket бот в функции `send_data()`:
- Проверка, что bookmaker == "POLYMARKET"
- Проверка, что config.polymarket_bot_url не пустой
- Отправка POST запроса на URL бота
- Поддержка X-Secret-Key заголовка
- Обработка ошибок в том же стиле, что и остальные отправки

## Что было добавлено

### В configparser.py:
```python
polymarket_bot_url: str = ""
polymarket_bot_secret_key: str = ""
```

### В alerts.py:
Добавлены два блока кода в конце функции `send_data()` (после всех существующих отправок):
- Один для `first_row_bets_app_data`
- Один для `second_row_bets_app_data`

Код следует тому же стилю, что и существующие отправки на другие API.

## Настройка .env

Добавьте в `.env` файл парсера:

```env
POLYMARKET_BOT_URL=http://YOUR_SERVER_IP:8000/bets
POLYMARKET_BOT_SECRET_KEY=your_secret_key_here
```

Где `YOUR_SERVER_IP` - IP адрес сервера, где запущен бот.

## Проверка

После замены файлов:
1. Проверьте синтаксис: `python -m py_compile bot/configparser.py bot/tasks/alerts.py`
2. Добавьте настройки в `.env`
3. Запустите парсер
4. Проверьте логи - должны появляться сообщения о отправке на polymarket bot
