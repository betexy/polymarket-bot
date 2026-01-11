# Фильтрация по second_bookmaker

## Что изменилось?

Бот теперь размещает ставки на Polymarket **только если** `second_bookmaker` (вторая букмекерская контора в паре) является одним из разрешенных.

## Разрешенные second_bookmaker:

- ✅ **PINNACLE**
- ✅ **BETFAIR**
- ✅ **SMARKETS**
- ✅ **MATCHBOOK**

## Логика работы:

1. Парсер отправляет ставку с `bookmaker = "POLYMARKET"` и `second_bookmaker = "PINNACLE"` (например)
2. Бот проверяет:
   - ✅ `bookmaker == "POLYMARKET"` (должно быть)
   - ✅ `second_bookmaker` в списке разрешенных
3. Если `second_bookmaker` не в списке → ставка пропускается (skipped)

## Настройка:

Разрешенные букмекеры настраиваются в `.env` файле:

```env
ALLOWED_SECOND_BOOKMAKERS=["PINNACLE", "BETFAIR", "SMARKETS", "MATCHBOOK"]
```

Или оставьте по умолчанию (уже настроено в коде).

## Примеры:

### Разрешенные (ставка будет размещена):
```json
{
    "bookmaker": "POLYMARKET",
    "second_bookmaker": "PINNACLE",
    ...
}
```

```json
{
    "bookmaker": "POLYMARKET",
    "second_bookmaker": "BETFAIR",
    ...
}
```

### Запрещенные (ставка будет пропущена):
```json
{
    "bookmaker": "POLYMARKET",
    "second_bookmaker": "1XBET",  // Не в списке
    ...
}
```

```json
{
    "bookmaker": "POLYMARKET",
    "second_bookmaker": "FONBET",  // Не в списке
    ...
}
```

## Статус в логах:

Если ставка пропущена из-за `second_bookmaker`, в логах будет:
- Статус: `skipped`
- Причина: `second_bookmaker_not_allowed: NAME`
- Логируется в API логах

## Изменение списка:

Если нужно изменить список разрешенных букмекеров, отредактируйте `.env`:

```env
ALLOWED_SECOND_BOOKMAKERS=["PINNACLE", "BETFAIR", "SMARKETS", "MATCHBOOK", "ДРУГОЙ"]
```

Или измените в коде `app/config/settings.py` (поле `allowed_second_bookmakers`).
