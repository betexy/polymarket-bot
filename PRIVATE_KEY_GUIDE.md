# Где взять POLYMARKET_PRIVATE_KEY?

## Что это?

`POLYMARKET_PRIVATE_KEY` - это **приватный ключ от кошелька Ethereum/Polygon**, который используется для:
- Аутентификации в CLOB API
- Размещения ордеров на Polymarket
- Управления позициями

⚠️ **ВАЖНО:** Это ключ от вашего кошелька с реальными деньгами! Будьте осторожны!

## Где взять приватный ключ?

### Вариант 1: Создать новый кошелек (РЕКОМЕНДУЕТСЯ)

**Для бота рекомендуется создать отдельный кошелек!**

#### Способ 1: Python (eth-account)

```python
from eth_account import Account

# Создание нового кошелька
account = Account.create()
private_key = account.key.hex()  # Приватный ключ (с 0x префиксом)
address = account.address  # Адрес кошелька

print(f"Адрес кошелька: {address}")
print(f"Приватный ключ: {private_key}")
```

**Или через скрипт:**

```bash
python3 -c "from eth_account import Account; acc = Account.create(); print(f'Address: {acc.address}'); print(f'Private Key: {acc.key.hex()}')"
```

#### Способ 2: Использовать MetaMask (через браузер)

1. Установите MetaMask расширение
2. Создайте новый кошелек
3. Нажмите на три точки (⋮) → Account details
4. Нажмите "Export Private Key"
5. Введите пароль MetaMask
6. Скопируйте приватный ключ

⚠️ **БЕЗОПАСНОСТЬ:** Никогда не делитесь приватным ключом!

#### Способ 3: Использовать готовые инструменты

- MyEtherWallet (https://www.myetherwallet.com/)
- Trust Wallet
- Другие кошельки с функцией экспорта приватного ключа

### Вариант 2: Получить из существующего кошелька

⚠️ **НЕ РЕКОМЕНДУЕТСЯ использовать основной кошелек!**

Если у вас уже есть кошелек (например, MetaMask):

1. Откройте MetaMask
2. Нажмите на три точки (⋮) рядом с названием аккаунта
3. Выберите "Account details"
4. Нажмите "Export Private Key"
5. Введите пароль MetaMask
6. Скопируйте приватный ключ

**Формат ключа:** Обычно начинается с `0x` и содержит 64 символа (например: `0x1234567890abcdef...`)

## Формат ключа

Приватный ключ может быть:
- С префиксом `0x`: `0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`
- Без префикса `0x`: `1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`

Библиотека `py-clob-client` принимает оба формата.

## Что нужно сделать после получения ключа?

### 1. Пополнить кошелек

Для торговли на Polymarket нужен баланс USDC на Polygon network:

1. **Пополните кошелек USDC на Polygon:**
   - Через биржу (Binance, Coinbase, etc.)
   - Через мост (Polygon Bridge)
   - Через обменники

2. **Убедитесь, что это Polygon network:**
   - Адрес кошелька начинается с `0x`
   - Network: Polygon (Chain ID: 137)

### 2. Добавить в .env файл

```env
POLYMARKET_PRIVATE_KEY=0xваш_приватный_ключ_здесь
```

**Или без префикса:**
```env
POLYMARKET_PRIVATE_KEY=ваш_приватный_ключ_здесь_без_0x
```

### 3. Проверить баланс

После настройки можно проверить баланс через бота (если реализовано) или через:
- MetaMask
- Polygon Explorer: https://polygonscan.com/
- Polymarket веб-сайт

## Безопасность

⚠️ **КРИТИЧЕСКИ ВАЖНО:**

1. **НЕ используйте основной кошелек:**
   - Создайте отдельный кошелек для бота
   - Ограничьте сумму на этом кошельке

2. **Храните приватный ключ в безопасности:**
   - НЕ коммитьте в git
   - НЕ отправляйте по email/мессенджерам
   - Используйте переменные окружения (.env файл)
   - Ограничьте доступ к файлу .env (chmod 600)

3. **Регулярно проверяйте:**
   - Баланс кошелька
   - Активность транзакций
   - Настройте уведомления (если возможно)

4. **Тестирование:**
   - Сначала тестируйте на testnet (Mumbai, Chain ID: 80001)
   - Используйте небольшие суммы для начала

## Тестовый кошелек (Mumbai Testnet)

Для тестирования можно использовать testnet:

```env
POLYMARKET_CHAIN_ID=80001  # Mumbai testnet
POLYMARKET_CLOB_HOST=https://clob-staging.polymarket.com  # Если доступен
```

Получить тестовые токены можно через:
- Polygon Faucet: https://faucet.polygon.technology/
- Alchemy Faucet: https://www.alchemy.com/faucets/polygon-mumbai

## Пример полного процесса

### 1. Создать кошелек (Python)

```python
from eth_account import Account

account = Account.create()
print(f"Адрес: {account.address}")
print(f"Приватный ключ: {account.key.hex()}")
```

### 2. Сохранить приватный ключ в .env

```env
POLYMARKET_PRIVATE_KEY=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
```

### 3. Пополнить кошелек USDC

- Переведите USDC на адрес кошелька
- Убедитесь, что это Polygon network

### 4. Проверить работу

Запустите бота и проверьте логи - должен инициализироваться CLOB клиент.

## Резюме

1. ✅ **Создайте отдельный кошелек** для бота (рекомендуется)
2. ✅ **Получите приватный ключ** (через MetaMask или Python)
3. ✅ **Пополните кошелек USDC** на Polygon
4. ✅ **Добавьте ключ в .env** файл
5. ✅ **Проверьте безопасность** (ограниченный доступ к .env)
6. ✅ **Начните с тестирования** на testnet или с небольших сумм

## Дополнительные ресурсы

- MetaMask: https://metamask.io/
- Polygon Explorer: https://polygonscan.com/
- Polygon Bridge: https://wallet.polygon.technology/polygon/bridge
- Eth Account Python: https://eth-account.readthedocs.io/
