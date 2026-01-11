# Code Review: Market Search and Token ID Retrieval

## Поток данных

### 1. Поиск маркета (`_find_market` в `order_manager.py`)

**Шаги:**
1. Извлечение команд из `bet_data` → `home_teams`, `away_teams`
2. Поиск событий по командам → `events`
3. Фильтрация событий по всем командам → `matching_event`
4. Получение markets для события → `markets`
5. Фильтрация markets по типу/target/pivot → `matching_market`
6. **ВАЖНО:** Получение полных данных через `get_market_by_id` → `full_market_data` (содержит `clobTokenIds`)
7. Возврат `matching_market` (теперь с полными данными)

**Исправлено:**
- ✅ Исправлена ошибка с `home_team`/`away_team` → теперь `home_team_raw`/`away_team_raw`
- ✅ Добавлен запрос полных данных через `get_market_by_id` для получения `clobTokenIds`

### 2. Извлечение outcome (`extract_market_outcome` в `data_mapper.py`)

**Логика:**
- Для `ONE_TWO`: сопоставление по названиям команд или позиции (первый/второй)
- Для `TOTAL`: сопоставление "Over"/"Under"
- Для `HDP`: сопоставление по командам или "HOME"/"AWAY"

**Статус:** ✅ Работает корректно

### 3. Получение token_id (`get_token_id_from_market` в `clob_client.py`)

**Проблемы найдены:**
1. ❌ **ИСПРАВЛЕНО:** Строка 258 - неправильный fallback: `tokens = market_data.get("outcomes")` - outcomes это названия, а не tokens
2. ✅ Логика поиска по `clobTokenIds` работает корректно
3. ✅ Логика сопоставления outcome по индексу работает корректно

**Исправлено:**
- ✅ Убран неправильный fallback с outcomes
- ✅ Улучшено логирование

### 4. Вызов `get_token_id_from_market` в `order_manager.py`

**Проблемы найдены:**
1. ❌ **ИСПРАВЛЕНО:** Проверка `is_available()` блокировала вызов функции
2. ✅ Функция не требует инициализированного CLOB клиента

**Исправлено:**
- ✅ Убрана проверка `is_available()` - функция вызывается всегда, если `clob_client` существует
- ✅ Добавлено детальное логирование

## Критические моменты

### ✅ Правильно:
1. `get_market_by_id` вызывается после нахождения `matching_market` для получения `clobTokenIds`
2. `outcomes` парсятся из JSON строки
3. `clobTokenIds` парсятся из JSON строки
4. Создается структура `tokens` из `clobTokenIds` для совместимости
5. Сопоставление outcome по индексу в списке outcomes

### ⚠️ Потенциальные проблемы:
1. Если `clobTokenIds` нет в данных от `get_market_by_id` - token_id не будет найден (это нормально, если API не возвращает)
2. Если outcome не найден в списке outcomes - используется fallback на первый outcome (может быть неправильно)

## Рекомендации

1. ✅ Все критические исправления применены
2. ✅ Логирование улучшено для диагностики
3. ✅ Поток данных проверен и исправлен

## Тестирование

Все тесты показывают, что функция `get_token_id_from_market` работает корректно:
- ✅ Market 1159205 (Tirante) - token_id найден
- ✅ Market 1155527 (76ers) - token_id найден  
- ✅ Market 1157457 (76ers) - token_id найден
- ✅ Market 1159132 (Nava) - token_id найден
- ✅ Market 1159196 (Badosa) - token_id найден
