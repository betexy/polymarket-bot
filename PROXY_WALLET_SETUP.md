# Настройка Proxy Wallet для Polymarket API

## Проблема
Ошибка "not enough balance / allowance" возникает потому, что:
- **UI Polymarket** торгует от лица Proxy-кошелька (где лежат USDC)
- **API по умолчанию** пытается торговать от лица EOA (личного кошелька), где баланс 0

## Решение

### 1. Найдите ваш Proxy адрес

1. Откройте https://polymarket.com
2. Зайдите в **Profile** (профиль)
3. Нажмите **"Copy Address"**
4. Это ваш Proxy адрес (отличается от адреса в MetaMask!)

**Или:**
- Посмотрите в Polygonscan транзакции вашего основного кошелька
- Найдите транзакцию deposit - куда уходили USDC
- Это и есть Proxy адрес

### 2. Добавьте настройки в .env

Откройте файл `/root/polymarket_bot/.env` и добавьте:

```bash
# Proxy Wallet адрес (где лежат USDC после deposit)
POLYMARKET_PROXY_ADDRESS=0x... (ваш Proxy адрес)

# Тип подписи: 1 = Magic Link/Email, 2 = MetaMask/Browser Wallet
POLYMARKET_SIGNATURE_TYPE=1
```

### 3. Перезапустите бота

После добавления настроек перезапустите бота:

```bash
pkill -f "python.*app.main"
cd /root/polymarket_bot && nohup python3 -m app.main > /tmp/polymarket_bot.log 2>&1 &
```

## Как это работает

- **EOA адрес** (из `POLYMARKET_PRIVATE_KEY`) - используется для подписи транзакций
- **Proxy адрес** (из `POLYMARKET_PROXY_ADDRESS`) - откуда списываются USDC
- **signature_type** - тип авторизации (1 для Email, 2 для MetaMask)

Указывая `funder=proxy_address`, вы говорите системе: "Я подписываю транзакцию своим ключом, но деньги списывай с моего Proxy-контракта".

## Проверка

После настройки попробуйте разместить ставку через API. Ошибка "not enough balance / allowance" должна исчезнуть.

## Примечание

Если вы хотите торговать с EOA (личного кошелька) вместо Proxy:
1. Переведите USDC с Proxy на EOA (Withdraw в UI)
2. Сделайте approve вручную (как мы обсуждали ранее)
3. Не указывайте `POLYMARKET_PROXY_ADDRESS` в .env

Но для ботов на Polymarket стандарт - торговля через Proxy (funder).
