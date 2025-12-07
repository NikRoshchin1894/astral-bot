#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки компонентов бота без полного запуска
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

def test_imports():
    """Тест импорта всех модулей"""
    logger.info("📦 Тест импорта модулей...")
    try:
        import bot
        logger.info("✅ Модуль bot успешно импортирован")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при импорте модуля bot: {e}", exc_info=True)
        return False

def test_database():
    """Тест инициализации базы данных"""
    logger.info("🗄️ Тест инициализации базы данных...")
    try:
        import bot
        bot.init_db()
        logger.info("✅ База данных успешно инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации БД: {e}", exc_info=True)
        return False

def test_application_creation():
    """Тест создания Application"""
    logger.info("🤖 Тест создания Application...")
    try:
        import bot
        from telegram.ext import Application
        from telegram import Bot
        
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        if not token:
            logger.warning("⚠️ TELEGRAM_BOT_TOKEN не установлен, пропускаем тест Application")
            return True
        
        # Создаем Application
        application = Application.builder().token(token).build()
        logger.info("✅ Application успешно создан")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при создании Application: {e}", exc_info=True)
        return False

def test_webhook_app_creation():
    """Тест создания Flask приложения для webhook"""
    logger.info("🌐 Тест создания Flask приложения...")
    try:
        import bot
        from telegram.ext import Application
        from telegram import Bot
        
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        if not token:
            logger.warning("⚠️ TELEGRAM_BOT_TOKEN не установлен, пропускаем тест Flask app")
            return True
        
        # Создаем Application
        application = Application.builder().token(token).build()
        
        # Создаем Flask app
        flask_app = bot.create_webhook_app(application)
        logger.info("✅ Flask приложение успешно создано")
        
        # Проверяем наличие endpoints
        with flask_app.test_client() as client:
            # Тест health check
            response = client.get('/health')
            if response.status_code == 200:
                logger.info("✅ Health check endpoint работает")
            else:
                logger.warning(f"⚠️ Health check вернул статус {response.status_code}")
            
            # Тест root endpoint
            response = client.get('/')
            if response.status_code == 200:
                logger.info("✅ Root endpoint работает")
            else:
                logger.warning(f"⚠️ Root endpoint вернул статус {response.status_code}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при создании Flask приложения: {e}", exc_info=True)
        return False

def test_functions():
    """Тест основных функций"""
    logger.info("🔧 Тест основных функций...")
    try:
        import bot
        
        # Тест get_db_connection
        try:
            conn, db_type = bot.get_db_connection()
            logger.info(f"✅ get_db_connection работает, тип БД: {db_type}")
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка в get_db_connection: {e}", exc_info=True)
            return False
        
        # Тест load_user_profile
        try:
            profile = bot.load_user_profile(123456789)
            logger.info(f"✅ load_user_profile работает (вернул: {profile})")
        except Exception as e:
            logger.error(f"❌ Ошибка в load_user_profile: {e}", exc_info=True)
            return False
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании функций: {e}", exc_info=True)
        return False

def main():
    """Запуск всех тестов"""
    logger.info("🧪 Начало тестирования компонентов бота...")
    logger.info("=" * 60)
    
    results = []
    
    # Тест 1: Импорт модулей
    results.append(("Импорт модулей", test_imports()))
    
    # Тест 2: База данных
    results.append(("Инициализация БД", test_database()))
    
    # Тест 3: Создание Application
    results.append(("Создание Application", test_application_creation()))
    
    # Тест 4: Flask приложение
    results.append(("Flask приложение", test_webhook_app_creation()))
    
    # Тест 5: Основные функции
    results.append(("Основные функции", test_functions()))
    
    # Вывод результатов
    logger.info("=" * 60)
    logger.info("📊 Результаты тестирования:")
    
    all_passed = True
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        logger.info(f"   {test_name}: {status}")
        if not result:
            all_passed = False
    
    logger.info("=" * 60)
    if all_passed:
        logger.info("✅ Все тесты пройдены успешно!")
        return 0
    else:
        logger.error("❌ Некоторые тесты провалены!")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Тестирование прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при тестировании: {e}", exc_info=True)
        sys.exit(1)

