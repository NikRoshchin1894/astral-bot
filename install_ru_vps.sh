#!/bin/bash

# Скрипт автоматической установки Astral Bot на российский VPS
# Использование: sudo bash install_ru_vps.sh

set -e  # Остановка при ошибках

echo "=================================="
echo "  Установка Astral Bot на VPS"
echo "=================================="
echo ""

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Ошибка: Запустите скрипт с правами root (sudo)"
    exit 1
fi

# Переменные
BOT_USER="astralbot"
BOT_DIR="/home/$BOT_USER/Astral_Bot"
PYTHON_VERSION="3.9"

echo "📦 Шаг 1: Обновление системы..."
apt update && apt upgrade -y

echo ""
echo "🐍 Шаг 2: Установка Python $PYTHON_VERSION и зависимостей..."
apt install -y python3.9 python3.9-venv python3-pip git build-essential python3-dev swig

echo ""
echo "👤 Шаг 3: Создание пользователя $BOT_USER..."
if id "$BOT_USER" &>/dev/null; then
    echo "   Пользователь $BOT_USER уже существует"
else
    adduser --disabled-password --gecos "" $BOT_USER
    echo "   ✅ Пользователь создан"
fi

echo ""
echo "📁 Шаг 4: Клонирование репозитория..."
if [ -d "$BOT_DIR" ]; then
    echo "   Директория $BOT_DIR уже существует, обновляем..."
    su - $BOT_USER -c "cd $BOT_DIR && git pull"
else
    su - $BOT_USER -c "cd ~ && git clone https://github.com/NikRoshchin1894/astral-bot.git Astral_Bot"
fi

echo ""
echo "🔧 Шаг 5: Создание виртуального окружения..."
su - $BOT_USER -c "cd $BOT_DIR && python3 -m venv venv"

echo ""
echo "📚 Шаг 6: Установка зависимостей Python..."
su - $BOT_USER -c "cd $BOT_DIR && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

echo ""
echo "📝 Шаг 7: Создание .env файла..."
if [ ! -f "$BOT_DIR/.env" ]; then
    su - $BOT_USER -c "cd $BOT_DIR && cp env.example .env"
    echo "   ⚠️  ВАЖНО: Отредактируйте файл $BOT_DIR/.env и заполните все переменные окружения!"
    echo "   Команда: nano $BOT_DIR/.env"
else
    echo "   Файл .env уже существует"
fi

echo ""
echo "📂 Шаг 8: Создание директории для логов..."
su - $BOT_USER -c "mkdir -p $BOT_DIR/logs && chmod 755 $BOT_DIR/logs"

echo ""
echo "⚙️  Шаг 9: Настройка systemd сервиса..."
cat > /etc/systemd/system/astral-bot.service <<EOF
[Unit]
Description=Astral Bot Telegram Service
After=network.target

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$BOT_DIR
Environment="PATH=$BOT_DIR/venv/bin"
ExecStart=$BOT_DIR/venv/bin/python3 $BOT_DIR/bot.py
Restart=always
RestartSec=10
StandardOutput=append:$BOT_DIR/logs/bot.log
StandardError=append:$BOT_DIR/logs/bot_error.log

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "🔄 Шаг 10: Перезагрузка systemd..."
systemctl daemon-reload

echo ""
echo "=================================="
echo "  ✅ Установка завершена!"
echo "=================================="
echo ""
echo "📋 Следующие шаги:"
echo ""
echo "1. Отредактируйте файл .env и заполните все переменные:"
echo "   nano $BOT_DIR/.env"
echo ""
echo "2. Включите автозапуск бота:"
echo "   systemctl enable astral-bot"
echo ""
echo "3. Запустите бота:"
echo "   systemctl start astral-bot"
echo ""
echo "4. Проверьте статус:"
echo "   systemctl status astral-bot"
echo ""
echo "5. Просмотр логов:"
echo "   journalctl -u astral-bot -f"
echo ""
echo "=================================="

