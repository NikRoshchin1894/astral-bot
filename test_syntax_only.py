#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тест синтаксиса и структуры кода без импорта зависимостей
"""
import ast
import sys
import logging

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def test_syntax():
    """Проверка синтаксиса Python"""
    logger.info("📝 Проверка синтаксиса bot.py...")
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Парсим AST
        ast.parse(code)
        logger.info("✅ Синтаксис корректен")
        return True
    except SyntaxError as e:
        logger.error(f"❌ Синтаксическая ошибка: {e}")
        logger.error(f"   Строка {e.lineno}: {e.text}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке синтаксиса: {e}")
        return False

def test_structure():
    """Проверка структуры кода"""
    logger.info("🏗️ Проверка структуры кода...")
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code)
        
        # Проверяем наличие основных функций (включая async)
        functions = []
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
        
        required_functions = [
            'main',
            'start',
            'button_handler',
            'handle_natal_chart_request',
            'generate_natal_chart_background',
            'create_webhook_app',
            'process_payment_async',
            'handle_natal_chart_request_from_payment'
        ]
        
        missing = []
        for func in required_functions:
            if func not in functions:
                missing.append(func)
        
        if missing:
            logger.warning(f"⚠️ Не найдены функции: {', '.join(missing)}")
        else:
            logger.info("✅ Все необходимые функции найдены")
        
        logger.info(f"   Найдено функций: {len(functions)}")
        logger.info(f"   Найдено классов: {len(classes)}")
        
        return len(missing) == 0
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке структуры: {e}", exc_info=True)
        return False

def test_webhook_handler():
    """Проверка наличия webhook handler"""
    logger.info("🔍 Проверка webhook handlers...")
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Проверяем наличие ключевых элементов
        checks = {
            'telegram_webhook': '@app.route(\'/webhook/telegram' in code or 'def telegram_webhook' in code,
            'yookassa_webhook': '@app.route(\'/webhook/yookassa' in code or 'def yookassa_webhook' in code,
            'process_update': 'process_update' in code,
            'application_ready_event': 'application_ready_event' in code,
            'process_payment_async': 'async def process_payment_async' in code,
            'handle_natal_chart_request_from_payment': 'async def handle_natal_chart_request_from_payment' in code
        }
        
        all_ok = True
        for check_name, result in checks.items():
            if result:
                logger.info(f"   ✅ {check_name}: найдено")
            else:
                logger.warning(f"   ⚠️ {check_name}: не найдено")
                all_ok = False
        
        return all_ok
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке webhook handlers: {e}", exc_info=True)
        return False

def test_event_loop_handling():
    """Проверка правильности обработки event loop"""
    logger.info("🔄 Проверка обработки event loop...")
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Проверяем, что везде правильно закрываются event loops
        issues = []
        
        # Проверяем наличие finally блоков для закрытия loop
        if 'loop.close()' in code:
            logger.info("   ✅ Найдены вызовы loop.close()")
        else:
            issues.append("Не найдены вызовы loop.close()")
        
        # Проверяем, что loop инициализируется как None
        if 'loop = None' in code:
            logger.info("   ✅ loop инициализируется как None")
        else:
            issues.append("loop не инициализируется как None")
        
        if issues:
            for issue in issues:
                logger.warning(f"   ⚠️ {issue}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке event loop: {e}", exc_info=True)
        return False

def main():
    """Запуск всех тестов"""
    logger.info("🧪 Тестирование синтаксиса и структуры bot.py...")
    logger.info("=" * 60)
    
    results = []
    
    # Тест 1: Синтаксис
    results.append(("Синтаксис", test_syntax()))
    
    # Тест 2: Структура
    results.append(("Структура кода", test_structure()))
    
    # Тест 3: Webhook handlers
    results.append(("Webhook handlers", test_webhook_handler()))
    
    # Тест 4: Event loop handling
    results.append(("Обработка event loop", test_event_loop_handling()))
    
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
        logger.info("💡 Для полного тестирования установите зависимости: pip install -r requirements.txt")
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

