# Решение проблемы с балансом/allowance

## Проблема
Ошибка: `not enough balance / allowance` при попытке разместить ставку через CLOB API.

## Анализ

### 1. Ошибка в библиотеке py-clob-client
Метод `update_balance_allowance()` в библиотеке py-clob-client требует параметр `BalanceAllowanceParams`, но мы вызываем его без параметров. Библиотека пытается обратиться к `params.signature_type`, но `params = None`, что вызывает ошибку:
```
'NoneType' object has no attribute 'signature_type'
```

Это баг/ограничение в библиотеке - метод требует специальных параметров для работы.

### 2. Как работает баланс в Polymarket

В Polymarket есть два типа баланса:
1. **Баланс кошелька** (wallet balance) - средства на вашем кошельке в блокчейне
2. **Внутренний баланс** (internal balance) - средства на счету в Polymarket (после deposit)

CLOB API работает с **внутренним балансом Polymarket**, а не напрямую с кошельком!

### 3. Решение

#### Вариант 1: DEPOSIT через UI Polymarket (РЕКОМЕНДУЕТСЯ)

1. Откройте https://polymarket.com
2. Подключите кошелек (адрес: `0x841F88aEF3e5B7d2e0a080Bb5ff0a52441Bc88b9`)
3. Найдите опцию **"Deposit"** или **"Перевести на баланс аккаунта"**
4. Переведите нужное количество USDC с кошелька на внутренний баланс Polymarket
5. После deposit баланс появится в CLOB API автоматически
6. Бот сможет размещать ставки

#### Вариант 2: Approve через контракт USDC (если deposit не помогает)

Если deposit не работает, можно сделать approve напрямую через контракт:

1. Адрес контракта USDC (Polygon): `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
2. Адрес контракта CLOB: `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E`
3. Вызовите функцию `approve(spender, amount)` контракта USDC:
   - `spender`: `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` (CLOB контракт)
   - `amount`: максимальное значение (например, `2^256-1`) или конкретная сумма

Это можно сделать через:
- MetaMask (Interact with Contract)
- Polygonscan (Write Contract)
- Другие кошельки с поддержкой взаимодействия с контрактами

## Проверка

После deposit/approve:
1. Проверьте баланс через скрипт: `python3 check_wallet.py`
2. Попробуйте разместить ставку снова
3. Ошибка "not enough balance / allowance" должна исчезнуть

## Текущий статус

- ✅ Баланс на кошельке: 12.39 USDC
- ❌ Внутренний баланс Polymarket: неизвестен (проверить после deposit)
- ❌ Allowance: не установлен
