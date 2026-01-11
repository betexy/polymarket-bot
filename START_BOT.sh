#!/bin/bash
# Скрипт для запуска бота

cd /root/polymarket_bot

echo "Проверка настроек..."
python3 -c "from app.config.settings import Settings; s = Settings(); print(f'✓ Order size: {s.default_order_size} USD')"

echo ""
echo "Запуск бота..."
echo "API будет доступен на: http://0.0.0.0:8000"
echo ""
echo "Проверка: curl http://localhost:8000/bets/health"
echo ""

python3 -m app.main
