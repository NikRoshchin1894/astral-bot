#!/bin/bash
# Скрипт для помощи с загрузкой на GitHub

echo "🚀 Следующие шаги для развертывания:"
echo ""
echo "📋 ШАГ 1: Создайте репозиторий на GitHub"
echo "   1. Зайдите на https://github.com/new"
echo "   2. Назовите репозиторий: astral-bot"
echo "   3. НЕ добавляйте README, .gitignore или лицензию"
echo "   4. Нажмите 'Create repository'"
echo ""
echo "📋 ШАГ 2: Загрузите код на GitHub"
echo ""
echo "Выполните следующие команды (замените YOUR_USERNAME на ваш GitHub username):"
echo ""
echo "   git remote add origin https://github.com/YOUR_USERNAME/astral-bot.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "📋 ШАГ 3: Развертывание на Railway (рекомендуется)"
echo "   1. Зайдите на https://railway.app"
echo "   2. Нажмите 'Start a New Project'"
echo "   3. Выберите 'Deploy from GitHub repo'"
echo "   4. Выберите репозиторий 'astral-bot'"
echo "   5. В разделе 'Variables' добавьте:"
echo "      - TELEGRAM_BOT_TOKEN = ваш токен"
echo "      - OPENAI_API_KEY = ваш ключ"
echo ""
echo "📋 ШАГ 4: Развертывание на Render (альтернатива)"
echo "   1. Зайдите на https://render.com"
echo "   2. Нажмите 'New +' → 'Background Worker'"
echo "   3. Подключите репозиторий 'astral-bot'"
echo "   4. Настройте:"
echo "      - Build Command: pip install -r requirements.txt"
echo "      - Start Command: python3 bot.py"
echo "   5. В разделе 'Environment' добавьте переменные:"
echo "      - TELEGRAM_BOT_TOKEN"
echo "      - OPENAI_API_KEY"
echo ""
echo "📖 Подробные инструкции:"
echo "   - Быстрый старт: QUICK_DEPLOY.md"
echo "   - Полная инструкция: DEPLOY_RENDER_RAILWAY.md"
echo ""

# Проверяем, есть ли GitHub CLI
if command -v gh &> /dev/null; then
    echo "✅ GitHub CLI установлен"
    echo ""
    read -p "Хотите создать репозиторий на GitHub через CLI? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Создание репозитория на GitHub..."
        gh repo create astral-bot --public --source=. --remote=origin --push
        echo "✅ Репозиторий создан и код загружен!"
    fi
else
    echo "💡 Установите GitHub CLI для автоматического создания репозитория:"
    echo "   brew install gh  # macOS"
    echo "   или посетите: https://cli.github.com/"
fi

