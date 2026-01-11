#!/usr/bin/env python3
"""
Скрипт для тестирования методов API Polymarket
Проверяет оба метода: GET /events?q=... и GET /events/slug/...
"""
import asyncio
import aiohttp
import json
from app.config.settings import Settings

settings = Settings()

async def test_list_events(query: str):
    """Тест метода List events с параметром q"""
    url = f"{settings.polymarket_gamma_api_url}/events"
    params = {"q": query, "limit": 10}
    
    print(f"\n=== ТЕСТ: GET /events?q={query} ===")
    print(f"URL: {url}")
    print(f"Params: {params}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            print(f"Status: {response.status}")
            if response.status == 200:
                data = await response.json()
                print(f"Response type: {type(data)}")
                if isinstance(data, list):
                    print(f"Found {len(data)} events")
                    if data:
                        print(f"First event keys: {list(data[0].keys())}")
                        print(f"First event sample: {json.dumps(data[0], indent=2, ensure_ascii=False)[:500]}")
                elif isinstance(data, dict):
                    print(f"Response keys: {list(data.keys())}")
                    print(f"Response sample: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
                else:
                    print(f"Response: {data}")
            else:
                text = await response.text()
                print(f"Error: {text[:200]}")

async def test_event_by_slug(slug: str):
    """Тест метода Get event by slug"""
    url = f"{settings.polymarket_gamma_api_url}/events/slug/{slug}"
    
    print(f"\n=== ТЕСТ: GET /events/slug/{slug} ===")
    print(f"URL: {url}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print(f"Status: {response.status}")
            if response.status == 200:
                data = await response.json()
                print(f"Response type: {type(data)}")
                if isinstance(data, dict):
                    print(f"Event keys: {list(data.keys())}")
                    print(f"Event sample: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
                else:
                    print(f"Response: {data}")
            else:
                text = await response.text()
                print(f"Error: {text[:200]}")

async def main():
    # Примеры из реальных ставок
    test_cases = [
        "Granada CF vs CD Castellón",
        "Augsburger Panther vs Koelner Haie",
        "Victoria Mboko vs Beatriz Haddad Maia",
    ]
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ МЕТОДОВ API POLYMARKET")
    print("=" * 60)
    
    for query in test_cases:
        await test_list_events(query)
        await asyncio.sleep(1)  # Задержка между запросами
    
    # Тест по slug (если есть пример slug)
    # await test_event_by_slug("example-slug")
    
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
