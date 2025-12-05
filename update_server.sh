#!/bin/bash
# Скрипт для обновления кода бота на сервере

set -e  # Остановка при ошибке

echo "🚀 Обновление бота Astral Bot на сервере..."
echo ""

# Определяем путь к директории бота
# Проверяем несколько возможных путей
BOT_DIR=""
POSSIBLE_PATHS=(
    "$HOME/Astral_Bot"
    "/home/astralbot/Astral_Bot"
    "/home/telegrambot/Astral_Bot"
    "$(pwd)"
)

for path in "${POSSIBLE_PATHS[@]}"; do
    if [ -d "$path" ] && [ -f "$path/bot.py" ]; then
        BOT_DIR="$path"
        break
    fi
done

if [ -z "$BOT_DIR" ]; then
    echo "❌ Не найдена директория бота!"
    echo "💡 Перейдите в директорию бота и запустите скрипт оттуда, или укажите путь:"
    echo "   cd /path/to/Astral_Bot"
    echo "   ./update_server.sh"
    exit 1
fi

echo "✅ Найдена директория бота: $BOT_DIR"
cd "$BOT_DIR"

# Проверяем, что это git репозиторий
if [ ! -d ".git" ]; then
    echo "❌ Это не git репозиторий!"
    echo "💡 Инициализируйте git репозиторий или клонируйте его заново"
    exit 1
fi

echo ""
echo "📋 Текущий статус git:"
git status --short || true

# Проверяем, есть ли незакоммиченные изменения
if [ -n "$(git status --porcelain)" ]; then
    echo ""
    echo "⚠️  Обнаружены незакоммиченные изменения!"
    echo "💡 Сохранить изменения перед обновлением? (y/n)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "💾 Создаю stash с локальными изменениями..."
        git stash save "Локальные изменения перед обновлением $(date +%Y-%m-%d_%H-%M-%S)"
    else
        echo "⚠️  Продолжаю без сохранения изменений..."
    fi
fi

echo ""
echo "🔄 Получаю обновления из репозитория..."

# Определяем ветку
CURRENT_BRANCH=$(git branch --show-current)
if [ -z "$CURRENT_BRANCH" ]; then
    CURRENT_BRANCH="main"
fi

echo "📌 Текущая ветка: $CURRENT_BRANCH"

# Получаем обновления
if git pull origin "$CURRENT_BRANCH"; then
    echo "✅ Код успешно обновлен!"
else
    echo "❌ Ошибка при получении обновлений!"
    echo "💡 Попробуйте вручную: git pull origin $CURRENT_BRANCH"
    exit 1
fi

# Проверяем, обновились ли requirements.txt
if git diff HEAD@{1} HEAD --name-only | grep -q "requirements.txt"; then
    echo ""
    echo "📦 Обнаружены изменения в requirements.txt"
    echo "🔄 Обновляю зависимости..."
    
    # Проверяем наличие виртуального окружения
    if [ -d "venv" ]; then
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        echo "✅ Зависимости обновлены!"
    else
        echo "⚠️  Виртуальное окружение не найдено!"
        echo "💡 Установите зависимости вручную:"
        echo "   source venv/bin/activate"
        echo "   pip install -r requirements.txt"
    fi
fi

echo ""
echo "🔄 Перезапускаю бота..."

# Проверяем, используется ли systemd
if systemctl is-active --quiet astral-bot 2>/dev/null; then
    echo "✅ Найден systemd сервис astral-bot"
    sudo systemctl restart astral-bot
    echo "✅ Бот перезапущен!"
    
    echo ""
    echo "📋 Статус сервиса:"
    sleep 2
    sudo systemctl status astral-bot --no-pager -l | head -20
elif systemctl is-active --quiet astral-bot.service 2>/dev/null; then
    echo "✅ Найден systemd сервис astral-bot.service"
    sudo systemctl restart astral-bot.service
    echo "✅ Бот перезапущен!"
    
    echo ""
    echo "📋 Статус сервиса:"
    sleep 2
    sudo systemctl status astral-bot.service --no-pager -l | head -20
else
    echo "⚠️  Systemd сервис не найден"
    echo "💡 Остановите бота вручную и запустите заново:"
    echo "   pkill -f bot.py"
    echo "   cd $BOT_DIR"
    echo "   source venv/bin/activate"
    echo "   python bot.py"
fi

echo ""
echo "✅ Обновление завершено!"
echo ""
echo "📋 Полезные команды:"
echo "   Просмотр логов: sudo journalctl -u astral-bot -f"
echo "   Статус бота: sudo systemctl status astral-bot"
echo "   Проверка webhook: python check_bot_status.py"

