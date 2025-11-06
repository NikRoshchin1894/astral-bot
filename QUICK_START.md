# Быстрый старт: Развертывание бота на сервере

## Краткая инструкция (5 минут)

### 1. Создайте VPS сервер
- Рекомендуется: Ubuntu 22.04 LTS
- Минимум: 512MB RAM, 10GB диск

### 2. Подключитесь к серверу
```bash
ssh root@YOUR_SERVER_IP
```

### 3. Установите необходимое ПО
```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git
```

### 4. Создайте пользователя для бота
```bash
adduser astralbot
# Задайте пароль
su - astralbot
```

### 5. Загрузите файлы бота

**Вариант A: Через Git (рекомендуется)**
```bash
cd ~
git clone YOUR_REPOSITORY_URL Astral_Bot
cd Astral_Bot
```

**Вариант B: Через SCP с локального компьютера**
```bash
# На вашем компьютере:
cd /Users/nsroschin/Documents/Astral_Bot
scp -r . astralbot@YOUR_SERVER_IP:~/Astral_Bot/
```

### 6. Запустите скрипт развертывания
```bash
cd ~/Astral_Bot
chmod +x deploy.sh
./deploy.sh
```

### 7. Создайте .env файл с токенами
```bash
nano .env
```

Добавьте:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
```

Сохраните (Ctrl+O, Enter, Ctrl+X)

### 8. Настройте systemd для автозапуска
```bash
# Выйдите из пользователя astralbot
exit

# От имени root создайте сервис
sudo nano /etc/systemd/system/astral-bot.service
```

Скопируйте содержимое из `astral-bot.service.example` и измените пути, если нужно.

Затем:
```bash
sudo systemctl daemon-reload
sudo systemctl enable astral-bot
sudo systemctl start astral-bot
sudo systemctl status astral-bot
```

### 9. Готово! 🎉

Бот должен работать. Проверьте логи:
```bash
sudo journalctl -u astral-bot -f
```

## Полезные команды

```bash
# Статус бота
sudo systemctl status astral-bot

# Перезапуск бота
sudo systemctl restart astral-bot

# Остановка бота
sudo systemctl stop astral-bot

# Просмотр логов
sudo journalctl -u astral-bot -f

# Просмотр последних 50 строк логов
sudo journalctl -u astral-bot -n 50
```

## Решение проблем

### Бот не запускается
```bash
# Проверьте логи
sudo journalctl -u astral-bot -n 50

# Проверьте .env файл
cat ~/Astral_Bot/.env

# Запустите бота вручную для диагностики
cd ~/Astral_Bot
source venv/bin/activate
python3 bot.py
```

### Обновление бота
```bash
cd ~/Astral_Bot
git pull  # если используете Git
# или загрузите новые файлы через SCP

source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart astral-bot
```

---

📖 **Подробная инструкция**: См. файл `DEPLOYMENT.md`

