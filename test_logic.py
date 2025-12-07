#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тест логики обработки обновлений
"""
import ast
import sys
import logging
import re

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def check_update_processing():
    """Проверка логики обработки обновлений"""
    logger.info("🔍 Проверка логики обработки обновлений...")
    
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            code = f.read()
        
        issues = []
        warnings = []
        
        # Проверка 1: telegram_webhook обрабатывает обновления
        if 'def telegram_webhook' in code:
            logger.info("   ✅ telegram_webhook функция найдена")
            
            # Проверяем, что используется process_update
            if 'application_instance.process_update' in code:
                logger.info("   ✅ Используется application_instance.process_update")
            else:
                issues.append("telegram_webhook не использует application_instance.process_update")
            
            # Проверяем, что обновления обрабатываются в отдельном потоке
            if 'threading.Thread' in code and 'process_update' in code:
                logger.info("   ✅ Обновления обрабатываются в отдельном потоке")
            else:
                warnings.append("Обновления могут не обрабатываться в отдельном потоке")
        else:
            issues.append("telegram_webhook функция не найдена")
        
        # Проверка 2: process_payment_async запускает генерацию
        if 'async def process_payment_async' in code:
            logger.info("   ✅ process_payment_async функция найдена")
            
            if 'handle_natal_chart_request_from_payment' in code:
                logger.info("   ✅ process_payment_async вызывает handle_natal_chart_request_from_payment")
            else:
                issues.append("process_payment_async не вызывает handle_natal_chart_request_from_payment")
        else:
            issues.append("process_payment_async функция не найдена")
        
        # Проверка 3: handle_natal_chart_request_from_payment запускает генерацию
        if 'async def handle_natal_chart_request_from_payment' in code:
            logger.info("   ✅ handle_natal_chart_request_from_payment функция найдена")
            
            # Проверяем, что генерация запускается в отдельном потоке
            if 'threading.Thread' in code and 'run_generation' in code:
                logger.info("   ✅ Генерация запускается в отдельном потоке")
            elif 'asyncio.create_task' in code and 'generate_natal_chart_background' in code:
                warnings.append("Генерация использует asyncio.create_task вместо отдельного потока")
            else:
                issues.append("handle_natal_chart_request_from_payment не запускает генерацию")
        else:
            issues.append("handle_natal_chart_request_from_payment функция не найдена")
        
        # Проверка 4: application_ready_event используется
        if 'application_ready_event' in code:
            logger.info("   ✅ application_ready_event используется")
            
            if 'application_ready_event.set()' in code:
                logger.info("   ✅ application_ready_event.set() вызывается")
            else:
                warnings.append("application_ready_event.set() не вызывается")
            
            if 'application_ready_event.wait' in code:
                logger.info("   ✅ application_ready_event.wait() используется")
            else:
                warnings.append("application_ready_event.wait() не используется")
        else:
            issues.append("application_ready_event не используется")
        
        # Проверка 5: Нет дублирования кода генерации
        gen_calls = len(re.findall(r'generate_natal_chart_background', code))
        if gen_calls > 0:
            logger.info(f"   ✅ generate_natal_chart_background вызывается {gen_calls} раз(а)")
            if gen_calls > 5:
                warnings.append(f"generate_natal_chart_background вызывается много раз ({gen_calls})")
        
        # Вывод результатов
        if issues:
            logger.error("   ❌ Найдены проблемы:")
            for issue in issues:
                logger.error(f"      - {issue}")
        
        if warnings:
            logger.warning("   ⚠️ Найдены предупреждения:")
            for warning in warnings:
                logger.warning(f"      - {warning}")
        
        if not issues and not warnings:
            logger.info("   ✅ Логика обработки обновлений корректна")
        
        return len(issues) == 0
        
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке логики: {e}", exc_info=True)
        return False

def check_event_loop_safety():
    """Проверка безопасности работы с event loop"""
    logger.info("🔄 Проверка безопасности event loop...")
    
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            code = f.read()
        
        issues = []
        
        # Проверяем, что все loop.close() в finally блоках
        # Это упрощенная проверка - ищем паттерн
        if 'loop.close()' in code:
            # Проверяем, что есть проверка на None
            if 'if loop is not None' in code or 'loop is not None' in code:
                logger.info("   ✅ Есть проверка loop is not None")
            else:
                warnings.append("Нет проверки loop is not None перед close()")
        
        # Проверяем, что loop инициализируется как None
        if 'loop = None' in code:
            logger.info("   ✅ loop инициализируется как None")
        else:
            issues.append("loop не инициализируется как None")
        
        return len(issues) == 0
        
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке event loop: {e}", exc_info=True)
        return False

def main():
    """Запуск всех тестов"""
    logger.info("🧪 Тестирование логики обработки обновлений...")
    logger.info("=" * 60)
    
    results = []
    
    # Тест 1: Логика обработки обновлений
    results.append(("Логика обработки обновлений", check_update_processing()))
    
    # Тест 2: Безопасность event loop
    results.append(("Безопасность event loop", check_event_loop_safety()))
    
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
        logger.info("✅ Все тесты логики пройдены!")
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

