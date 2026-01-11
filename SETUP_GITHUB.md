# Настройка GitHub репозитория

## SSH ключ создан

Публичный SSH ключ для GitHub:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM2HTaZl29A05FbXc+KN53CN634V8glJHSkI2bslyuk0 polymarket-bot
```

## Инструкция по добавлению ключа на GitHub

1. Скопируйте публичный ключ выше
2. Перейдите на GitHub: https://github.com/settings/keys
3. Нажмите "New SSH key"
4. Вставьте ключ в поле "Key"
5. Дайте название (например, "polymarket-bot-server")
6. Нажмите "Add SSH key"

## Создание репозитория на GitHub

1. Перейдите на https://github.com/new
2. Название репозитория: `polymarket-bot` (или любое другое)
3. Выберите Private или Public
4. НЕ инициализируйте с README, .gitignore или лицензией (у нас уже есть .gitignore)
5. Нажмите "Create repository"

## Подключение локального репозитория к GitHub

После создания репозитория на GitHub выполните:

```bash
cd /root/polymarket_bot
git remote add origin git@github.com:ВАШ_USERNAME/polymarket-bot.git
git branch -M main
git push -u origin main
```

Замените `ВАШ_USERNAME` на ваш GitHub username.

## Первый коммит

```bash
cd /root/polymarket_bot
git add .
git commit -m "Initial commit: Polymarket betting bot"
git push -u origin main
```

## Важно

- Не коммитьте файл `.env` с секретными ключами (уже в .gitignore)
- Не коммитьте базу данных `polymarket_events.db` (уже в .gitignore)
- Не коммитьте `bet_settings.json` (уже в .gitignore)
