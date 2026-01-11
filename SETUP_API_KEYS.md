# Настройка API ключей Polymarket

## Полученные ключи

Согласно предоставленному скриншоту, у вас есть следующие ключи:

```
apiKey: 019ba95c-0f86-73f8-9f09-afae7e11c577
secret: NJLb8TXalIoKDOU1BHHDh1ee6iqOS-ErRagB7MPrfrU=
passphrase: 8f0fadd71c514aec4608a2ed1cbad422c1f92ea09ddaba754def58baaf98dce1
```

## Настройка .env файла

Создайте файл `.env` в корне проекта `polymarket_bot/`:

```bash
cd /root/polymarket_bot
cp .env.example .env
```

Отредактируйте `.env` файл и укажите ваши ключи:

```env
# Polymarket Gamma API настройки
POLYMARKET_API_KEY=019ba95c-0f86-73f8-9f09-afae7e11c577
POLYMARKET_API_SECRET=NJLb8TXalIoKDOU1BHHDh1ee6iqOS-ErRagB7MPrfrU=
POLYMARKET_API_PASSPHRASE=8f0fadd71c514aec4608a2ed1cbad422c1f92ea09ddaba754def58baaf98dce1
POLYMARKET_GAMMA_API_URL=https://gamma-api.polymarket.com

# API сервер настройки
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=your_secret_key_for_bot_protection

# Логирование
LOG_LEVEL=INFO

# Настройки ордеров
DEFAULT_ORDER_SIZE=10.0
MIN_PROFIT_PERCENT=0.0
```

## Важно

⚠️ **БЕЗОПАСНОСТЬ:**
- НЕ коммитьте `.env` файл в git
- `.env` уже должен быть в `.gitignore`
- Храните ключи в безопасности
- Не передавайте ключи третьим лицам

## Проверка подключения

После настройки ключей можно проверить подключение:

```bash
# Запустите бота
python -m app.main

# В другом терминале проверьте health endpoint
curl http://localhost:8000/bets/health

# Отправьте тестовую ставку (замените YOUR_SECRET_KEY на ваш API_SECRET_KEY)
curl -X POST http://localhost:8000/bets/ \
  -H "Content-Type: application/json" \
  -H "X-Secret-Key: YOUR_SECRET_KEY" \
  -d '{
    "bookmaker": "POLYMARKET",
    "market": "ONE_TWO",
    "target": "ONE",
    "homeTeam": "Team 1",
    "awayTeam": "Team 2",
    "league": "Test",
    "sport": "FOOTBALL",
    "coef": "2.50",
    "surebet_profit": 5.0,
    "mode": "LIVE",
    "timeValue": "FULL_TIME"
  }'
```

## Примечания

1. **Gamma API** - используется для получения данных о markets (read-only)
2. Эти ключи могут использоваться для аутентификации в Gamma API
3. Для размещения ордеров потребуется интеграция с CLOB API (см. CLOB_API_INFO.md)

## POLYMARKET_PRIVATE_KEY

⚠️ **ВАЖНО:** Для работы CLOB API нужен `POLYMARKET_PRIVATE_KEY` - это **приватный ключ от кошелька**.

**Где взять:**
- Создать новый кошелек (рекомендуется) - см. `PRIVATE_KEY_GUIDE.md`
- Или экспортировать из существующего кошелька (MetaMask, etc.)

**Подробная инструкция:** См. `PRIVATE_KEY_GUIDE.md`
