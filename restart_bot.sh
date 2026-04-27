#!/bin/bash
# Скрипт для перезапуска бота на сервере

echo "🔄 Перезапуск бота Astral Bot..."
echo ""

# Очищаем proxy-переменные, чтобы бот ходил в Telegram напрямую
PROXY_VARS=(
    HTTP_PROXY HTTPS_PROXY ALL_PROXY
    http_proxy https_proxy all_proxy
    SOCKS_PROXY SOCKS5_PROXY
    socks_proxy socks5_proxy
)

echo "🧹 Очищаю proxy-переменные окружения..."
for var in "${PROXY_VARS[@]}"; do
    unset "$var"
done
echo "✅ Proxy-переменные очищены в текущей сессии"
echo ""

# Проверяем, используется ли systemd
if systemctl is-active --quiet astral-bot 2>/dev/null; then
    echo "✅ Найден systemd сервис astral-bot"
    echo "🧹 Убираю proxy-переменные из systemd (если были заданы)..."
    sudo systemctl unset-environment "${PROXY_VARS[@]}" 2>/dev/null || true
    echo "🔄 Перезапускаю через systemd..."
    sudo systemctl restart astral-bot
    echo "✅ Бот перезапущен через systemd"
    echo ""
    echo "📋 Статус сервиса:"
    sudo systemctl status astral-bot --no-pager -l | head -15
elif systemctl is-active --quiet astral-bot.service 2>/dev/null; then
    echo "✅ Найден systemd сервис astral-bot.service"
    echo "🧹 Убираю proxy-переменные из systemd (если были заданы)..."
    sudo systemctl unset-environment "${PROXY_VARS[@]}" 2>/dev/null || true
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
    echo "   env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY python bot.py"
    echo ""
    echo "   Или запустите в screen/tmux:"
    echo "   screen -S bot env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY python bot.py"
fi

echo ""
echo "⏳ Подождите 10-30 секунд для установки webhook..."
echo ""
echo "📋 Для проверки статуса выполните:"
echo "   python check_bot_status.py"

