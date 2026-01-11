# Маппинг маркетов и поиск markets

## Где находится маппинг маркетов?

### 1. Маппинг типов маркетов (`MARKET_TYPE_MAP`)
**Файл:** `app/services/data_mapper.py`

Определяет, как тип маркета от парсера преобразуется для поиска на Polymarket:

```python
MARKET_TYPE_MAP = {
    "ONE_TWO": "1X2",           # Ставка 1X2
    "TOTAL": "TOTAL",            # Тотал
    "HDP": "HANDICAP",          # Фора (Handicap)
    "INDIVIDUAL_TOTAL": "INDIVIDUAL_TOTAL",  # Индивидуальный тотал
}
```

### 2. Маппинг целей (`MARKET_TARGET_MAP`)
**Файл:** `app/services/data_mapper.py`

Определяет, как цель ставки (HOME, AWAY, OVER, UNDER и т.д.) преобразуется:

```python
MARKET_TARGET_MAP = {
    "HOME": "HOME",
    "AWAY": "AWAY",
    "OVER": "OVER",
    "UNDER": "UNDER",
    # и т.д.
}
```

### 3. Логика фильтрации markets
**Файл:** `app/services/polymarket_client.py`, метод `_filter_markets_by_type`

Этот метод фильтрует найденные markets по типу, target и pivot.

## Как работает поиск markets?

1. **Поиск событий (events)** по названиям команд
   - Запросы к `/events` endpoint
   - Используются разные варианты запросов:
     - `"Granada CF vs CD Castellón"`
     - `"Granada CF CD Castellón"`
     - `"Granada CF"`
     - `"CD Castellón"`

2. **Получение markets для каждого события**
   - Запрос к `/markets?event_id=XXX`
   - Получаем все markets для события

3. **Фильтрация markets**
   - По типу market (1X2, TOTAL, HANDICAP, etc.)
   - По target (HOME, AWAY, OVER, UNDER, etc.)
   - По pivot (для тоталов и фор)

## Какой запрос отправляется к API?

### Запрос поиска событий:
```
GET /events?q={query}&limit=10
```

Где `{query}` - это один из вариантов названий команд.

### Запрос получения markets:
```
GET /markets?event_id={event_id}
```

## Почему может не найтись market?

1. **Неправильные названия команд**
   - На Polymarket команды могут называться по-другому
   - Например: "Granada" вместо "Granada CF"

2. **Неправильный маппинг типа маркета**
   - Тип маркета от парсера не соответствует тому, что есть на Polymarket
   - Нужно проверить `MARKET_TYPE_MAP`

3. **Market такого типа не существует для этого события**
   - На Polymarket может не быть market типа HANDICAP для этого матча
   - Или market еще не создан

4. **Неправильная фильтрация**
   - Метод `_filter_markets_by_type` не находит подходящий market
   - Нужно проверить логику фильтрации

## Как посмотреть текущий маппинг?

Запустите:
```bash
cd /root/polymarket_bot
python3 -c "from app.services.data_mapper import DataMapper; m = DataMapper(); print('MARKET_TYPE_MAP:', m.MARKET_TYPE_MAP); print('MARKET_TARGET_MAP:', m.MARKET_TARGET_MAP)"
```

## Добавлено детальное логирование

Теперь в логах будет видно:
- Какие запросы отправляются к API
- Какие события найдены
- Сколько markets у каждого события
- Какие типы markets доступны
- Почему market не был найден
