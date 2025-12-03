# Развертывание бота на российском VPS 🚀

Эта инструкция поможет развернуть бота на российском VPS сервере (Timeweb, Selectel, Beget, REG.RU, FirstVDS и других).

## 🎯 Выбор VPS провайдера

### Рекомендуемые российские провайдеры:

1. **Timeweb** (https://timeweb.com) - от 199₽/мес
   - Хорошая поддержка, панель управления
   - Подходит для начинающих

2. **Selectel** (https://selectel.ru) - от 300₽/мес
   - Надежный, быстрый, хорошая документация
   - Рекомендуется для продакшена

3. **Beget** (https://beget.com) - от 200₽/мес
   - Простое управление, хорошая поддержка

4. **REG.RU** (https://www.reg.ru) - от 250₽/мес
   - Популярный, много дополнительных услуг

5. **FirstVDS** (https://firstvds.ru) - от 179₽/мес
   - Дешевый, но надежный вариант

## 📋 Требования к VPS

- **ОС**: Ubuntu 20.04 LTS или 22.04 LTS (рекомендуется)
- **RAM**: минимум 512 MB (рекомендуется 1 GB)
- **Диск**: минимум 5 GB свободного места
- **CPU**: 1 ядро (достаточно для бота)
- **Сеть**: исходящие подключения к интернету (для Telegram API и ЮKassa API)

## 🚀 Быстрая установка

### Шаг 1: Подключение к серверу

```bash
ssh root@ваш_сервер_ip
```

Или, если используется пользователь:
```bash
ssh username@ваш_сервер_ip
```

### Шаг 2: Обновление системы

```bash
apt update && apt upgrade -y
```

### Шаг 3: Установка Python 3.9+ и зависимостей

```bash
# Установка Python 3.9 и pip
apt install -y python3.9 python3.9-venv python3-pip git

# Проверка версии Python
python3 --version  # Должно быть 3.9 или выше
```

### Шаг 4: Создание пользователя для бота (рекомендуется)

```bash
# Создаем пользователя
adduser --disabled-password --gecos "" astralbot

# Переключаемся на пользователя
su - astralbot
```

### Шаг 5: Клонирование репозитория

```bash
cd ~
git clone https://github.com/NikRoshchin1894/astral-bot.git Astral_Bot
cd Astral_Bot
```

### Шаг 6: Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
```

### Шаг 7: Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Примечание**: Если возникают проблемы с установкой `pyswisseph`, может потребоваться:
```bash
apt install -y swig build-essential python3-dev
pip install pyswisseph
```

### Шаг 8: Настройка переменных окружения

```bash
cp env.example .env
nano .env
```

Заполните все необходимые переменные:
- `TELEGRAM_BOT_TOKEN` - токен от @BotFather
- `OPENAI_API_KEY` - ключ OpenAI API
- `YOOKASSA_SHOP_ID` - ID магазина ЮKassa
- `YOOKASSA_SECRET_KEY` - секретный ключ ЮKassa
- `TELEGRAM_BOT_USERNAME` - username бота (без @)
- `DATABASE_PUBLIC_URL` - строка подключения к PostgreSQL (если используется) или оставьте пустым для SQLite

### Шаг 9: Настройка базы данных

#### Вариант A: SQLite (проще, для начала)

Ничего делать не нужно - SQLite будет использоваться автоматически, если `DATABASE_PUBLIC_URL` не установлен.

#### Вариант B: PostgreSQL (рекомендуется для продакшена)

```bash
# Установка PostgreSQL
apt install -y postgresql postgresql-contrib

# Создание пользователя и базы данных
sudo -u postgres psql

# В консоли PostgreSQL:
CREATE USER astralbot WITH PASSWORD 'ваш_пароль';
CREATE DATABASE astral_bot OWNER astralbot;
GRANT ALL PRIVILEGES ON DATABASE astral_bot TO astralbot;
\q

# В .env файле укажите:
# DATABASE_PUBLIC_URL=postgresql://astralbot:ваш_пароль@localhost:5432/astral_bot
```

### Шаг 10: Создание директории для логов

```bash
mkdir -p logs
chmod 755 logs
```

### Шаг 11: Настройка systemd сервиса

```bash
# Вернитесь в root (если используете отдельного пользователя)
exit

# Создайте systemd service файл
nano /etc/systemd/system/astral-bot.service
```

Скопируйте содержимое из файла `astral-bot.service.example` (или используйте файл ниже, заменив пути на ваши):

```ini
[Unit]
Description=Astral Bot Telegram Service
After=network.target

[Service]
Type=simple
User=astralbot
WorkingDirectory=/home/astralbot/Astral_Bot
Environment="PATH=/home/astralbot/Astral_Bot/venv/bin"
ExecStart=/home/astralbot/Astral_Bot/venv/bin/python3 /home/astralbot/Astral_Bot/bot.py
Restart=always
RestartSec=10
StandardOutput=append:/home/astralbot/Astral_Bot/logs/bot.log
StandardError=append:/home/astralbot/Astral_Bot/logs/bot_error.log

[Install]
WantedBy=multi-user.target
```

**Важно**: Измените пути `/home/astralbot/Astral_Bot` на ваши реальные пути!

```bash
# Перезагружаем systemd
systemctl daemon-reload

# Включаем автозапуск
systemctl enable astral-bot

# Запускаем сервис
systemctl start astral-bot

# Проверяем статус
systemctl status astral-bot
```

### Шаг 12: Проверка работы

```bash
# Просмотр логов в реальном времени
tail -f /home/astralbot/Astral_Bot/logs/bot.log

# Или если запущено под root
journalctl -u astral-bot -f
```

## 🔧 Управление ботом

### Полезные команды:

```bash
# Запуск бота
systemctl start astral-bot

# Остановка бота
systemctl stop astral-bot

# Перезапуск бота
systemctl restart astral-bot

# Статус бота
systemctl status astral-bot

# Просмотр логов
journalctl -u astral-bot -n 100 -f

# Или из файла
tail -f /home/astralbot/Astral_Bot/logs/bot.log
```

## 🔄 Обновление бота

```bash
# Переключитесь на пользователя бота
su - astralbot

# Перейдите в директорию проекта
cd ~/Astral_Bot

# Остановите бота (или сделайте это через systemctl от root)
# exit  # вернуться в root
# systemctl stop astral-bot

# Получите последние изменения
git pull

# Обновите зависимости (если изменились)
source venv/bin/activate
pip install -r requirements.txt

# Вернитесь в root и перезапустите бота
# exit
# systemctl start astral-bot
```

## 🛡️ Безопасность

1. **Firewall (ufw)**:
```bash
# Установка ufw
apt install -y ufw

# Разрешаем SSH (важно сделать сначала!)
ufw allow 22/tcp

# Включаем firewall
ufw enable

# Проверяем статус
ufw status
```

2. **Обновление системы**:
```bash
# Настройка автоматических обновлений безопасности
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

3. **Fail2ban** (защита от брутфорса):
```bash
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

## 📊 Мониторинг

### Проверка использования ресурсов:

```bash
# Использование CPU и памяти
htop

# Или
top

# Дисковое пространство
df -h

# Использование памяти
free -h
```

### Логи:

```bash
# Все логи systemd
journalctl -u astral-bot

# Последние 100 строк
journalctl -u astral-bot -n 100

# Логи за последний час
journalctl -u astral-bot --since "1 hour ago"

# Следить за логами в реальном времени
journalctl -u astral-bot -f
```

## 🐛 Решение проблем

### Бот не запускается:

1. Проверьте логи:
```bash
journalctl -u astral-bot -n 50
```

2. Проверьте, что все переменные окружения установлены:
```bash
su - astralbot
cd ~/Astral_Bot
source venv/bin/activate
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('TELEGRAM_BOT_TOKEN:', bool(os.getenv('TELEGRAM_BOT_TOKEN')))"
```

3. Проверьте права доступа:
```bash
ls -la /home/astralbot/Astral_Bot/
chmod +x /home/astralbot/Astral_Bot/bot.py
```

### Ошибки с базой данных:

1. Для PostgreSQL - проверьте подключение:
```bash
sudo -u postgres psql -d astral_bot -c "SELECT 1;"
```

2. Для SQLite - проверьте права на файл:
```bash
ls -la /home/astralbot/Astral_Bot/users.db
chmod 644 /home/astralbot/Astral_Bot/users.db
```

### Ошибки с зависимостями:

```bash
# Переустановите зависимости
su - astralbot
cd ~/Astral_Bot
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

## 🌐 Настройка домена и webhook для ЮKassa (опционально)

Если вам нужен webhook для ЮKassa (для мгновенных уведомлений о платежах):

### Шаг 1: Установка Nginx

```bash
apt install -y nginx
```

### Шаг 2: Настройка проксирования для webhook

```bash
nano /etc/nginx/sites-available/astral-bot
```

Добавьте следующую конфигурацию:

```nginx
server {
    listen 80;
    server_name ваш_домен.ru;

    # Webhook endpoint для ЮKassa
    location /webhook/yookassa {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Другие endpoints (если нужны)
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Шаг 3: Включение конфигурации

```bash
ln -s /etc/nginx/sites-available/astral-bot /etc/nginx/sites-enabled/
nginx -t  # Проверка конфигурации
systemctl restart nginx
```

### Шаг 4: Настройка SSL (Let's Encrypt)

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d ваш_домен.ru
```

Сертификат будет обновляться автоматически.

### Шаг 5: Настройка переменной окружения для webhook

В файле `.env` добавьте:

```bash
YOOKASSA_WEBHOOK_URL=https://ваш_домен.ru/webhook/yookassa
WEBHOOK_PORT=8080
```

После этого перезапустите бота:

```bash
systemctl restart astral-bot
```

### Шаг 6: Настройка webhook в личном кабинете ЮKassa

1. Зайдите в личный кабинет ЮKassa: https://yookassa.ru/my
2. Перейдите в раздел "Настройки" → "Уведомления"
3. Добавьте URL webhook: `https://ваш_домен.ru/webhook/yookassa`
4. Сохраните изменения

**Примечание**: Если webhook не настроен, бот все равно будет проверять статусы платежей периодически (каждые 2 минуты), но уведомления от ЮKassa будут мгновенными с webhook.

## 📞 Поддержка

Если возникли проблемы:
1. Проверьте логи: `journalctl -u astral-bot -n 100`
2. Убедитесь, что все переменные окружения установлены
3. Проверьте, что бот запущен: `systemctl status astral-bot`

---

**Готово!** Ваш бот должен работать на российском VPS! 🎉

