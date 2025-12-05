#!/bin/bash
# Скрипт для перезапуска бота на сервере

echo "🔄 Перезапуск бота Astral Bot..."
echo ""

# Проверяем, используется ли systemd
if systemctl is-active --quiet astral-bot 2>/dev/null; then
    echo "✅ Найден systemd сервис astral-bot"
    echo "🔄 Перезапускаю через systemd..."
    sudo systemctl restart astral-bot
    echo "✅ Бот перезапущен через systemd"
    echo ""
    echo "📋 Статус сервиса:"
    sudo systemctl status astral-bot --no-pager -l | head -15
elif systemctl is-active --quiet astral-bot.service 2>/dev/null; then
    echo "✅ Найден systemd сервис astral-bot.service"
    echo "🔄 Перезапускаю через systemd..."
    sudo systemctl restart astral-bot.service
    echo "✅ Бот перезапущен через systemd"
    echo ""
    echo "📋 Статус сервиса:"
    sudo systemctl status astral-bot.service --no-pager -l | head -15
else
    echo "⚠️  Systemd сервис не найден"
    echo "🔄 Останавливаю все процессы бота..."
    pkill -f "bot.py" 2>/dev/null || true
    pkill -f "python.*bot" 2>/dev/null || true
    sleep 2
    
    echo "✅ Процессы остановлены"
    echo ""
    echo "💡 Для запуска бота вручную выполните:"
    echo "   cd /path/to/Astral_Bot"
    echo "   python bot.py"
    echo ""
    echo "   Или запустите в screen/tmux:"
    echo "   screen -S bot python bot.py"
fi

echo ""
echo "⏳ Подождите 10-30 секунд для установки webhook..."
echo ""
echo "📋 Для проверки статуса выполните:"
echo "   python check_bot_status.py"

