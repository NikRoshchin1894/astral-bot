#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для локального тестирования бота
"""
import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Настраиваем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Проверяем наличие обязательных переменных
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не установлен в .env файле")
    sys.exit(1)

# Устанавливаем временный webhook URL для тестирования (можно использовать ngrok)
TELEGRAM_WEBHOOK_URL = os.getenv('TELEGRAM_WEBHOOK_URL', '')
YOOKASSA_WEBHOOK_URL = os.getenv('YOOKASSA_WEBHOOK_URL', '')

logger.info("🧪 Локальное тестирование бота")
logger.info(f"   TELEGRAM_BOT_TOKEN: {'✅ установлен' if TELEGRAM_BOT_TOKEN else '❌ не установлен'}")
logger.info(f"   TELEGRAM_WEBHOOK_URL: {'✅ ' + TELEGRAM_WEBHOOK_URL if TELEGRAM_WEBHOOK_URL else '❌ не установлен'}")
logger.info(f"   YOOKASSA_WEBHOOK_URL: {'✅ ' + YOOKASSA_WEBHOOK_URL if YOOKASSA_WEBHOOK_URL else '❌ не установлен'}")

# Импортируем bot
try:
    logger.info("📦 Импорт модуля bot...")
    import bot
    logger.info("✅ Модуль bot успешно импортирован")
except Exception as e:
    logger.error(f"❌ Ошибка при импорте модуля bot: {e}", exc_info=True)
    sys.exit(1)

if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    try:
        bot.main()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота по запросу пользователя")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

