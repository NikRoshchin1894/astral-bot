# Развертывание бота на Timeweb VPS 🚀

Подробная инструкция по развертыванию Astral Bot на VPS от Timeweb.

## 📋 Что вам понадобится

1. Аккаунт на Timeweb (https://timeweb.com)
2. VPS сервер (минимум 1 GB RAM, 1 ядро CPU, 5 GB диска)
3. Доступ к SSH
4. Токен бота от @BotFather

## 🎯 Шаг 1: Аренда VPS на Timeweb

### 1.1 Регистрация и вход

1. Зайдите на https://timeweb.com
2. Зарегистрируйтесь или войдите в личный кабинет
3. Перейдите в раздел **"Облачные серверы"** → **"Виртуальные серверы"**

### 1.2 Создание VPS

1. Нажмите **"Создать сервер"**
2. Выберите тариф:
   - **Минимальный**: 1 GB RAM, 1 ядро CPU, 10 GB SSD (от 199₽/мес)
   - **Рекомендуемый**: 2 GB RAM, 2 ядра CPU, 20 GB SSD (от 399₽/мес)
3. Выберите **операционную систему**: **Ubuntu 22.04 LTS** (рекомендуется)
4. Выберите регион (Москва или Санкт-Петербург)
5. Выберите способ оплаты и оплатите первый месяц
6. Дождитесь активации сервера (обычно 2-5 минут)

### 1.3 Получение данных для доступа

После создания сервера:

1. В панели управления Timeweb найдите ваш VPS
2. Скопируйте:
   - **IP-адрес сервера** (например: `185.71.76.XXX`)
   - **Пароль root** (будет показан один раз, сохраните его!)
   - Или создайте SSH-ключ для безопасного доступа

## 🔐 Шаг 2: Подключение к серверу

### Вариант A: Через терминал (Linux/Mac)

```bash
ssh root@ваш_ip_адрес
```

При первом подключении введите `yes` для подтверждения, затем введите пароль root.

### Вариант B: Через SSH-клиент (Windows)

Используйте **PuTTY** (https://www.putty.org) или **MobaXterm**:

1. Запустите PuTTY
2. В поле **Host Name** введите IP-адрес сервера
3. Порт: **22**
4. Тип подключения: **SSH**
5. Нажмите **Open**
6. Введите логин: `root`
7. Введите пароль (при вводе пароль не отображается - это нормально)

## 🚀 Шаг 3: Первоначальная настройка сервера

### 3.1 Обновление системы

```bash
apt update && apt upgrade -y
```

### 3.2 Установка необходимых пакетов

```bash
apt install -y python3.9 python3.9-venv python3-pip git build-essential python3-dev swig curl wget nano htop ufw
```

### 3.3 Настройка firewall (безопасность)

```bash
# Разрешаем SSH (ВАЖНО! Сделайте это первым)
ufw allow 22/tcp

# Разрешаем HTTP и HTTPS (для webhook, если будете использовать домен)
ufw allow 80/tcp
ufw allow 443/tcp

# Включаем firewall
ufw enable

# Проверяем статус
ufw status
```

## 👤 Шаг 4: Создание пользователя для бота

Для безопасности лучше запускать бота не от root:

```bash
# Создаем пользователя
adduser --disabled-password --gecos "" astralbot

# Добавляем в группу sudo (если понадобится)
usermod -aG sudo astralbot

# Переключаемся на пользователя
su - astralbot
```

## 📦 Шаг 5: Установка бота

### 5.1 Клонирование репозитория

```bash
cd ~
git clone https://github.com/NikRoshchin1894/astral-bot.git Astral_Bot
cd Astral_Bot
```

### 5.2 Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
```

### 5.3 Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Примечание**: Установка может занять несколько минут. Если возникнут ошибки с `pyswisseph`, выполните:

```bash
# Вернитесь в root временно
exit

# Установите дополнительные зависимости
apt install -y swig libswisseph-dev

# Вернитесь к пользователю бота
su - astralbot
cd ~/Astral_Bot
source venv/bin/activate
pip install pyswisseph
```

## ⚙️ Шаг 6: Настройка переменных окружения

```bash
cd ~/Astral_Bot
cp env.example .env
nano .env
```

Заполните все необходимые переменные:

```env
# Токен бота от @BotFather
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# OpenAI API ключ (для генерации натальных карт)
OPENAI_API_KEY=sk-...

# ЮKassa настройки
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_secret_key

# Username бота (без @)
TELEGRAM_BOT_USERNAME=ваш_bot_username

# URL для возврата после оплаты (замените на ваш username)
PAYMENT_SUCCESS_URL=https://t.me/ваш_bot_username?start=payment_success
PAYMENT_RETURN_URL=https://t.me/ваш_bot_username?start=payment_cancel

# База данных (оставьте пустым для SQLite или укажите PostgreSQL)
# DATABASE_PUBLIC_URL=postgresql://user:password@localhost:5432/database
```

**Сохраните файл**: `Ctrl+O` (Enter) → `Ctrl+X`

## 🗄️ Шаг 7: Настройка базы данных

### Вариант A: SQLite (проще, для начала)

Ничего дополнительного делать не нужно! SQLite будет использоваться автоматически, если `DATABASE_PUBLIC_URL` не указан.

### Вариант B: PostgreSQL (рекомендуется для продакшена)

```bash
# Вернитесь в root
exit

# Установка PostgreSQL
apt install -y postgresql postgresql-contrib

# Переход в PostgreSQL
sudo -u postgres psql
```

В консоли PostgreSQL выполните:

```sql
CREATE USER astralbot WITH PASSWORD 'ваш_надежный_пароль';
CREATE DATABASE astral_bot OWNER astralbot;
GRANT ALL PRIVILEGES ON DATABASE astral_bot TO astralbot;
\q
```

Обновите `.env` файл:

```bash
su - astralbot
cd ~/Astral_Bot
nano .env
```

Добавьте или измените строку:

```env
DATABASE_PUBLIC_URL=postgresql://astralbot:ваш_надежный_пароль@localhost:5432/astral_bot
```

## 📂 Шаг 8: Создание директории для логов

```bash
mkdir -p ~/Astral_Bot/logs
chmod 755 ~/Astral_Bot/logs
```

## 🔧 Шаг 9: Настройка systemd (автозапуск)

```bash
# Вернитесь в root
exit

# Создайте файл сервиса
nano /etc/systemd/system/astral-bot.service
```

Вставьте следующее содержимое (замените пути, если используете другого пользователя):

```ini
[Unit]
Description=Astral Bot Telegram Service
After=network.target postgresql.service

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

**Сохраните**: `Ctrl+O` (Enter) → `Ctrl+X`

```bash
# Перезагружаем systemd
systemctl daemon-reload

# Включаем автозапуск
systemctl enable astral-bot

# Запускаем бота
systemctl start astral-bot

# Проверяем статус
systemctl status astral-bot
```

Должно появиться сообщение **"active (running)"** в зеленом цвете.

## ✅ Шаг 10: Проверка работы

### Просмотр логов

```bash
# В реальном времени
journalctl -u astral-bot -f

# Последние 50 строк
journalctl -u astral-bot -n 50

# Или из файла
tail -f /home/astralbot/Astral_Bot/logs/bot.log
```

### Тест бота

1. Найдите вашего бота в Telegram
2. Отправьте команду `/start`
3. Бот должен ответить приветственным сообщением

## 🌐 Шаг 11: Настройка домена (опционально, для webhook)

Если вы хотите использовать webhook для мгновенных уведомлений от ЮKassa:

### 11.1 Получение домена в Timeweb

1. В панели Timeweb перейдите в **"Домены"**
2. Зарегистрируйте новый домен или добавьте существующий
3. Настройте DNS-записи:
   - **Тип**: A
   - **Имя**: @ (или поддомен, например `bot`)
   - **Значение**: IP-адрес вашего VPS

### 11.2 Установка Nginx

```bash
apt install -y nginx certbot python3-certbot-nginx
```

### 11.3 Настройка Nginx

```bash
nano /etc/nginx/sites-available/astral-bot
```

Добавьте:

```nginx
server {
    listen 80;
    server_name ваш_домен.ru;

    # Webhook для ЮKassa
    location /webhook/yookassa {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
```

```bash
# Включить конфигурацию
ln -s /etc/nginx/sites-available/astral-bot /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default  # Удалить дефолтную конфигурацию
nginx -t  # Проверка
systemctl restart nginx
```

### 11.4 Настройка SSL (Let's Encrypt)

```bash
certbot --nginx -d ваш_домен.ru
```

Следуйте инструкциям. Сертификат будет обновляться автоматически.

### 11.5 Обновление .env

```bash
su - astralbot
cd ~/Astral_Bot
nano .env
```

Добавьте:

```env
YOOKASSA_WEBHOOK_URL=https://ваш_домен.ru/webhook/yookassa
WEBHOOK_PORT=8080
```

Перезапустите бота:

```bash
systemctl restart astral-bot
```

### 11.6 Настройка в ЮKassa

1. Зайдите в личный кабинет ЮKassa: https://yookassa.ru/my
2. **Настройки** → **Уведомления**
3. Добавьте URL: `https://ваш_домен.ru/webhook/yookassa`
4. Сохраните

## 🔄 Управление ботом

### Полезные команды:

```bash
# Запуск
systemctl start astral-bot

# Остановка
systemctl stop astral-bot

# Перезапуск
systemctl restart astral-bot

# Статус
systemctl status astral-bot

# Просмотр логов
journalctl -u astral-bot -f
```

## 🔄 Обновление бота

```bash
# Переключитесь на пользователя бота
su - astralbot
cd ~/Astral_Bot

# Остановите бота (из другого терминала или SSH сессии)
# systemctl stop astral-bot

# Получите обновления
git pull

# Обновите зависимости
source venv/bin/activate
pip install -r requirements.txt

# Вернитесь в root и перезапустите
exit
systemctl restart astral-bot
```

## 🛡️ Дополнительная безопасность

### Настройка автоматических обновлений безопасности

```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

### Установка Fail2ban (защита от брутфорса)

```bash
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

### Отключение входа по паролю (только SSH-ключ)

1. Создайте SSH-ключ на локальном компьютере (если еще нет)
2. Скопируйте публичный ключ на сервер
3. В файле `/etc/ssh/sshd_config` установите:
   ```
   PasswordAuthentication no
   PubkeyAuthentication yes
   ```
4. Перезапустите SSH: `systemctl restart sshd`

## 📊 Мониторинг ресурсов

### Использование ресурсов

```bash
# CPU и память
htop

# Дисковое пространство
df -h

# Память
free -h

# Сетевая активность
iftop  # (установите: apt install -y iftop)
```

### Логи

```bash
# Все логи бота
journalctl -u astral-bot

# Логи за последний час
journalctl -u astral-bot --since "1 hour ago"

# Следить за логами в реальном времени
journalctl -u astral-bot -f
```

## 🐛 Решение проблем

### Бот не запускается

1. Проверьте логи:
   ```bash
   journalctl -u astral-bot -n 100
   ```

2. Проверьте переменные окружения:
   ```bash
   su - astralbot
   cd ~/Astral_Bot
   source venv/bin/activate
   python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Token:', bool(os.getenv('TELEGRAM_BOT_TOKEN')))"
   ```

3. Проверьте права доступа:
   ```bash
   ls -la /home/astralbot/Astral_Bot/
   ```

### Проблемы с базой данных

**SQLite**:
```bash
ls -la /home/astralbot/Astral_Bot/users.db
chmod 644 /home/astralbot/Astral_Bot/users.db
```

**PostgreSQL**:
```bash
sudo -u postgres psql -d astral_bot -c "SELECT 1;"
```

### Ошибки с зависимостями

```bash
su - astralbot
cd ~/Astral_Bot
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### Бот не отвечает в Telegram

1. Проверьте, что токен правильный
2. Убедитесь, что бот запущен: `systemctl status astral-bot`
3. Проверьте логи на ошибки: `journalctl -u astral-bot -n 50`

## 💰 Стоимость

Примерная стоимость на Timeweb:

- **VPS**: от 199₽/мес (1 GB RAM, 10 GB SSD)
- **Домен**: от 149₽/год (опционально)
- **Итого**: от 199₽/мес без домена

## 📞 Поддержка

- **Timeweb**: https://timeweb.com/ru/help (техническая поддержка 24/7)
- **Документация бота**: см. README.md в репозитории
- **Проблемы с ботом**: проверьте логи (`journalctl -u astral-bot`)

---

**Готово!** Ваш бот должен работать на Timeweb VPS! 🎉

Если возникли проблемы - проверьте логи и убедитесь, что все переменные окружения установлены корректно.

