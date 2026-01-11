# Управление сервисом Polymarket Bot

## Статус сервиса

Сервис `polymarket-bot.service` настроен и работает как systemd service.

## Основные команды

### Проверка статуса
```bash
systemctl status polymarket-bot.service
```

### Запуск сервиса
```bash
systemctl start polymarket-bot.service
```

### Остановка сервиса
```bash
systemctl stop polymarket-bot.service
```

### Перезапуск сервиса
```bash
systemctl restart polymarket-bot.service
```

### Просмотр логов
```bash
# Последние логи
journalctl -u polymarket-bot.service -n 50

# Логи в реальном времени
journalctl -u polymarket-bot.service -f

# Логи за последний час
journalctl -u polymarket-bot.service --since "1 hour ago"

# Также логи пишутся в файл
tail -f /tmp/polymarket_bot.log
```

### Включить автозапуск при загрузке системы
```bash
systemctl enable polymarket-bot.service
```

### Отключить автозапуск
```bash
systemctl disable polymarket-bot.service
```

## Проверка работы

```bash
# Проверка health endpoint
curl http://localhost:8000/bets/health

# Проверка дашборда
curl http://localhost:8000/
```

## Автоматический перезапуск

Сервис настроен на автоматический перезапуск:
- При падении процесса (Restart=always)
- С задержкой 10 секунд (RestartSec=10)
- При загрузке системы (WantedBy=multi-user.target)

## Файл сервиса

Расположение: `/etc/systemd/system/polymarket-bot.service`

## Логи

- Systemd логи: `journalctl -u polymarket-bot.service`
- Файл логов: `/tmp/polymarket_bot.log`
