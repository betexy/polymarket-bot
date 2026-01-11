"""
Пример кода для модификации парсера
Добавить в файл bot/tasks/alerts.py
"""

async def send_to_polymarket_bot(
    config,
    bet_data: dict,
) -> None:
    """Отправка ставки на бот Polymarket"""
    from datetime import datetime
    from aiohttp import ClientSession
    
    # Отправляем только ставки на Polymarket
    if bet_data.get("bookmaker") != "POLYMARKET":
        return
    
    # URL бота из конфигурации
    polymarket_bot_url = getattr(config, 'polymarket_bot_url', None)
    if not polymarket_bot_url:
        return
    
    async with ClientSession() as session:
        try:
            headers = {"Content-Type": "application/json"}
            
            # Добавляем секретный ключ если настроен
            polymarket_bot_secret = getattr(config, 'polymarket_bot_secret_key', None)
            if polymarket_bot_secret:
                headers["X-Secret-Key"] = polymarket_bot_secret
            
            async with session.post(
                polymarket_bot_url,
                json=bet_data,
                headers=headers,
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=10)
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
                f"{datetime.now():%d.%m.%Y %H:%M:%S} > send to polymarket bot error > bookmaker={bet_data.get('bookmaker')} homeTeam={bet_data.get('homeTeam')} {ex}"
            )


# В функции send_data() добавить вызовы:
# await send_to_polymarket_bot(config, first_row_bets_app_data)
# await send_to_polymarket_bot(config, second_row_bets_app_data)
