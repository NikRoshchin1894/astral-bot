# Инструкция по развертыванию бота на облачном сервере

## Варианты облачных серверов

### Рекомендуемые провайдеры:
- **DigitalOcean** (международный, от $4/месяц)
- **Hetzner** (международный, от €4/месяц)
- **Timeweb** (российский, от 200₽/месяц)
- **Selectel** (российский, от 200₽/месяц)
- **AWS EC2** (международный, free tier доступен)
- **Yandex Cloud** (российский)

## Шаг 1: Создание и настройка сервера

### 1.1 Создание VPS
1. Зарегистрируйтесь на выбранном провайдере
2. Создайте новый VPS сервер:
   - **ОС**: Ubuntu 22.04 LTS (рекомендуется)
   - **RAM**: минимум 512MB (1GB рекомендуется)
   - **Диск**: минимум 10GB
   - **Регион**: выбирайте ближайший к вашей аудитории

### 1.2 Подключение к серверу
После создания сервера вы получите IP-адрес и пароль/SSH ключ.

**Подключение через SSH:**
```bash
ssh root@YOUR_SERVER_IP
# или
ssh username@YOUR_SERVER_IP
```

## Шаг 2: Настройка сервера

### 2.1 Обновление системы
```bash
apt update && apt upgrade -y
```

### 2.2 Установка необходимых пакетов
```bash
apt install -y python3 python3-pip python3-venv git nginx supervisor curl
```

### 2.3 Настройка файрвола (опционально, но рекомендуется)
```bash
# Установка UFW (если еще не установлен)
apt install -y ufw

# Разрешаем SSH
ufw allow 22/tcp

# Включаем файрвол
ufw enable

# Проверяем статус
ufw status
```

## Шаг 3: Подготовка директории для бота

### 3.1 Создание пользователя для бота (рекомендуется)
```bash
# Создаем пользователя
adduser astralbot
# Установите пароль и заполните информацию (можно оставить пустым)

# Добавляем в группу sudo (если нужно)
usermod -aG sudo astralbot

# Переключаемся на пользователя
su - astralbot
```

### 3.2 Создание директории проекта
```bash
mkdir -p ~/Astral_Bot
cd ~/Astral_Bot
```

## Шаг 4: Загрузка файлов бота на сервер

### Вариант A: Через Git (рекомендуется)

#### 4.1 Инициализация Git репозитория
На вашем локальном компьютере:
```bash
cd /Users/nsroschin/Documents/Astral_Bot
git init
git add .
git commit -m "Initial commit"
```

Создайте репозиторий на GitHub/GitLab/Bitbucket и запушьте:
```bash
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

#### 4.2 Клонирование на сервере
На сервере:
```bash
cd ~/Astral_Bot
git clone YOUR_REPOSITORY_URL .
```

### Вариант B: Через SCP (прямая загрузка)

На вашем локальном компьютере:
```bash
# Создайте архив проекта (исключая venv и __pycache__)
cd /Users/nsroschin/Documents/Astral_Bot
tar --exclude='venv' --exclude='__pycache__' --exclude='.git' \
    --exclude='*.pyc' --exclude='bot_run.log' --exclude='bot.pid' \
    -czf astral_bot.tar.gz .

# Загрузите на сервер
scp astral_bot.tar.gz astralbot@YOUR_SERVER_IP:~/

# На сервере распакуйте
ssh astralbot@YOUR_SERVER_IP
cd ~/Astral_Bot
tar -xzf ~/astral_bot.tar.gz
```

### Вариант C: Через rsync (синхронизация)

На вашем локальном компьютере:
```bash
rsync -avz --exclude 'venv' --exclude '__pycache__' \
    --exclude '*.pyc' --exclude 'bot_run.log' \
    /Users/nsroschin/Documents/Astral_Bot/ \
    astralbot@YOUR_SERVER_IP:~/Astral_Bot/
```

## Шаг 5: Настройка окружения

### 5.1 Создание виртуального окружения
```bash
cd ~/Astral_Bot
python3 -m venv venv
source venv/bin/activate
```

### 5.2 Установка зависимостей
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.3 Создание файла .env
```bash
nano .env
```

Добавьте в файл:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
```

Сохраните файл (Ctrl+O, Enter, Ctrl+X)

### 5.4 Создание директории для логов
```bash
mkdir -p ~/Astral_Bot/logs
```

## Шаг 6: Тестирование запуска

### 6.1 Запуск бота вручную (для проверки)
```bash
cd ~/Astral_Bot
source venv/bin/activate
python3 bot.py
```

Если бот запустился успешно, остановите его (Ctrl+C).

## Шаг 7: Настройка автозапуска через systemd

### 7.1 Создание systemd сервиса
```bash
sudo nano /etc/systemd/system/astral-bot.service
```

Добавьте следующее содержимое (замените `astralbot` на ваше имя пользователя и путь на актуальный):
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

Сохраните файл (Ctrl+O, Enter, Ctrl+X).

### 7.2 Загрузка и запуск сервиса
```bash
# Перезагружаем systemd для чтения нового сервиса
sudo systemctl daemon-reload

# Включаем автозапуск при старте системы
sudo systemctl enable astral-bot

# Запускаем сервис
sudo systemctl start astral-bot

# Проверяем статус
sudo systemctl status astral-bot
```

### 7.3 Полезные команды для управления ботом

```bash
# Просмотр статуса
sudo systemctl status astral-bot

# Просмотр логов (в реальном времени)
sudo journalctl -u astral-bot -f

# Остановка бота
sudo systemctl stop astral-bot

# Перезапуск бота
sudo systemctl restart astral-bot

# Просмотр последних логов
sudo journalctl -u astral-bot -n 50

# Просмотр логов за сегодня
sudo journalctl -u astral-bot --since today
```

## Шаг 8: Настройка ротации логов (опционально)

### 8.1 Создание конфигурации logrotate
```bash
sudo nano /etc/logrotate.d/astral-bot
```

Добавьте:
```
/home/astralbot/Astral_Bot/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 astralbot astralbot
    sharedscripts
}
```

## Шаг 9: Мониторинг и обслуживание

### 9.1 Проверка работы бота
```bash
# Проверка процессов
ps aux | grep bot.py

# Проверка использования ресурсов
htop
# или
top
```

### 9.2 Обновление бота

#### Если используете Git:
```bash
cd ~/Astral_Bot
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart astral-bot
```

#### Если загружаете файлы вручную:
```bash
# Остановите бота
sudo systemctl stop astral-bot

# Загрузите новые файлы (через SCP или rsync)

# Установите зависимости, если нужно
cd ~/Astral_Bot
source venv/bin/activate
pip install -r requirements.txt

# Запустите бота
sudo systemctl start astral-bot
```

## Шаг 10: Безопасность

### 10.1 Настройка прав доступа
```bash
# Ограничиваем доступ к .env файлу
chmod 600 ~/Astral_Bot/.env

# Устанавливаем правильные права на файлы
chmod 755 ~/Astral_Bot
chmod 644 ~/Astral_Bot/*.py
```

### 10.2 Настройка SSH (рекомендуется)
```bash
# Отключение входа по паролю (используйте только SSH ключи)
sudo nano /etc/ssh/sshd_config
# Найдите и измените:
# PasswordAuthentication no

# Перезапустите SSH
sudo systemctl restart sshd
```

## Шаг 11: Резервное копирование

### 11.1 Автоматическое резервное копирование
Создайте скрипт для резервного копирования:
```bash
nano ~/backup_bot.sh
```

Добавьте:
```bash
#!/bin/bash
BACKUP_DIR="/home/astralbot/backups"
SOURCE_DIR="/home/astralbot/Astral_Bot"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/astral_bot_$DATE.tar.gz \
    -C $SOURCE_DIR \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='logs' \
    .

# Удаляем старые backup'ы (старше 7 дней)
find $BACKUP_DIR -name "astral_bot_*.tar.gz" -mtime +7 -delete
```

Сделайте скрипт исполняемым:
```bash
chmod +x ~/backup_bot.sh
```

Добавьте в crontab (ежедневное резервное копирование в 3:00):
```bash
crontab -e
```

Добавьте строку:
```
0 3 * * * /home/astralbot/backup_bot.sh
```

## Решение проблем

### Бот не запускается
1. Проверьте логи: `sudo journalctl -u astral-bot -n 50`
2. Проверьте права доступа к файлам
3. Убедитесь, что .env файл содержит правильные токены
4. Проверьте, что виртуальное окружение активировано в systemd сервисе

### Бот запускается, но не отвечает
1. Проверьте токен Telegram бота в .env
2. Проверьте логи на ошибки: `sudo journalctl -u astral-bot -f`
3. Убедитесь, что сервер имеет доступ к интернету

### Высокое использование памяти
1. Проверьте процессы: `ps aux | grep python`
2. Перезапустите бота: `sudo systemctl restart astral-bot`
3. Рассмотрите возможность увеличения RAM сервера

## Полезные ссылки

- [DigitalOcean Tutorial](https://www.digitalocean.com/community/tutorials)
- [Systemd Service Guide](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [Ubuntu Server Guide](https://ubuntu.com/server/docs)

## Контакты для поддержки

При возникновении проблем проверьте:
1. Логи бота: `sudo journalctl -u astral-bot -f`
2. Статус сервиса: `sudo systemctl status astral-bot`
3. Соединение с Telegram API

