#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для диагностики и исправления конфликта Telegram (409 Conflict)
"""

import os
import sys
import requests
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

def print_header(title):
    """Печатает заголовок"""
    print()
    print("=" * 80)
    print(f"🔍 {title}")
    print("=" * 80)
    print()

def check_webhook_status():
    """Проверяет статус webhook"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return None
    
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                webhook_data = result.get('result', {})
                url = webhook_data.get('url', '')
                pending_updates = webhook_data.get('pending_update_count', 0)
                last_error_date = webhook_data.get('last_error_date')
                last_error_message = webhook_data.get('last_error_message', '')
                
                return {
                    'url': url,
                    'pending_updates': pending_updates,
                    'last_error_date': last_error_date,
                    'last_error_message': last_error_message
                }
    except Exception as e:
        print(f"❌ Ошибка при проверке webhook: {e}")
    
    return None

def check_conflict():
    """Проверяет наличие конфликта"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        return False
    
    try:
        # Пробуем получить обновления
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1&limit=1",
            timeout=10
        )
        
        if response.status_code == 409:
            return True
        elif response.status_code == 200:
            return False
    except Exception as e:
        print(f"⚠️  Ошибка при проверке конфликта: {e}")
    
    return None

async def delete_webhook_async():
    """Удаляет webhook асинхронно"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        return False
    
    try:
        bot = Bot(token=bot_token)
        result = await bot.delete_webhook(drop_pending_updates=True)
        return result
    except Exception as e:
        print(f"❌ Ошибка при удалении webhook: {e}")
        return False

def delete_webhook_sync():
    """Удаляет webhook синхронно"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        return False
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
            json={'drop_pending_updates': True},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('ok', False)
    except Exception as e:
        print(f"❌ Ошибка при удалении webhook: {e}")
    
    return False

def main():
    """Основная функция"""
    print()
    print("=" * 80)
    print("🔧 ИСПРАВЛЕНИЕ КОНФЛИКТА TELEGRAM (409 Conflict)")
    print("=" * 80)
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        print("   Установите токен в .env файле или переменных окружения")
        return 1
    
    # 1. Проверка статуса webhook
    print_header("1. ПРОВЕРКА СТАТУСА WEBHOOK")
    
    webhook_info = check_webhook_status()
    
    if webhook_info:
        if webhook_info['url']:
            print(f"⚠️  Webhook УСТАНОВЛЕН: {webhook_info['url']}")
            print(f"   Ожидающих обновлений: {webhook_info['pending_updates']}")
            
            if webhook_info['last_error_date']:
                print(f"   ❌ Последняя ошибка: {webhook_info['last_error_message']}")
            
            print()
            print("   💡 ПРОБЛЕМА: Webhook установлен, но бот пытается использовать polling!")
            print("   Решение: Удалить webhook или использовать webhook режим")
        else:
            print("✅ Webhook НЕ установлен (polling режим)")
    else:
        print("⚠️  Не удалось проверить статус webhook")
    
    # 2. Проверка конфликта
    print_header("2. ПРОВЕРКА КОНФЛИКТА")
    
    has_conflict = check_conflict()
    
    if has_conflict is True:
        print("❌ КОНФЛИКТ ОБНАРУЖЕН (409 Conflict)")
        print()
        print("   Возможные причины:")
        print("   1. Webhook установлен, но бот пытается использовать polling")
        print("   2. Запущено несколько экземпляров бота одновременно")
        print("   3. Предыдущая сессия polling не завершена")
    elif has_conflict is False:
        print("✅ Конфликта нет")
    else:
        print("⚠️  Не удалось проверить конфликт")
    
    # 3. Решение проблемы
    print_header("3. РЕШЕНИЕ ПРОБЛЕМЫ")
    
    if webhook_info and webhook_info['url']:
        print("🔧 Удаление webhook...")
        
        # Пробуем синхронный метод
        success = delete_webhook_sync()
        
        if success:
            print("✅ Webhook успешно удален")
            print()
            print("💡 Теперь бот может использовать polling (getUpdates)")
            print("   Перезапустите бота после удаления webhook")
        else:
            print("❌ Не удалось удалить webhook автоматически")
            print()
            print("💡 Попробуйте вручную:")
            print("   python remove_webhook.py")
    else:
        if has_conflict:
            print("⚠️  Конфликт обнаружен, но webhook не установлен")
            print()
            print("💡 Возможные решения:")
            print("   1. Остановите все экземпляры бота")
            print("   2. Подождите 1-2 минуты")
            print("   3. Перезапустите бота")
            print()
            print("   Или используйте webhook режим:")
            print("   1. Установите TELEGRAM_WEBHOOK_URL в .env")
            print("   2. Перезапустите бота")
    
    # 4. Рекомендации
    print_header("4. РЕКОМЕНДАЦИИ")
    
    telegram_webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
    
    if telegram_webhook_url:
        print("✅ TELEGRAM_WEBHOOK_URL установлен")
        print(f"   URL: {telegram_webhook_url}")
        print()
        print("💡 Бот должен работать в режиме WEBHOOK")
        print("   Убедитесь, что:")
        print("   1. Webhook сервер запущен")
        print("   2. URL доступен извне")
        print("   3. Webhook установлен в Telegram")
    else:
        print("⚠️  TELEGRAM_WEBHOOK_URL не установлен")
        print()
        print("💡 Бот будет работать в режиме POLLING")
        print("   Для этого:")
        print("   1. Удалите webhook (если установлен)")
        print("   2. Остановите все экземпляры бота")
        print("   3. Запустите один экземпляр бота")
    
    # Итоговый отчет
    print_header("ИТОГОВЫЙ ОТЧЕТ")
    
    if webhook_info and webhook_info['url']:
        if delete_webhook_sync():
            print("✅ WEBHOOK УДАЛЕН - можно использовать polling")
        else:
            print("⚠️  Webhook установлен - удалите его вручную или используйте webhook режим")
    else:
        if has_conflict:
            print("⚠️  Конфликт обнаружен - остановите все экземпляры бота")
        else:
            print("✅ Проблем не обнаружено")
    
    print()
    print("=" * 80)
    
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

