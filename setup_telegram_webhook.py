#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для установки webhook в Telegram
"""

import os
import sys
import requests
import asyncio
from dotenv import load_dotenv

load_dotenv()

def setup_telegram_webhook():
    """Устанавливает webhook в Telegram"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return False
    
    if not webhook_url:
        print("❌ TELEGRAM_WEBHOOK_URL не установлен")
        print()
        print("💡 Установите переменную TELEGRAM_WEBHOOK_URL в .env или переменных окружения")
        print("   Формат: https://ваш-домен.com/webhook/telegram")
        return False
    
    print("=" * 80)
    print("🔗 УСТАНОВКА WEBHOOK В TELEGRAM")
    print("=" * 80)
    print()
    print(f"Bot Token: {bot_token[:10]}...")
    print(f"Webhook URL: {webhook_url}")
    print()
    
    # Проверяем доступность webhook URL
    print("1️⃣ Проверка доступности webhook URL...")
    try:
        response = requests.get(webhook_url.replace('/webhook/telegram', '/health'), timeout=10)
        print(f"   ✅ Endpoint доступен (HTTP {response.status_code})")
    except Exception as e:
        print(f"   ⚠️  Не удалось проверить доступность: {e}")
        print(f"   💡 Убедитесь, что webhook сервер запущен")
    print()
    
    # Устанавливаем webhook
    print("2️⃣ Установка webhook в Telegram...")
    try:
        # Используем синхронный запрос для простоты
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={
                'url': webhook_url,
                'drop_pending_updates': True,
                'allowed_updates': ['message', 'callback_query', 'pre_checkout_query']
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print(f"   ✅ Webhook успешно установлен!")
                print(f"   URL: {result.get('result', {}).get('url', webhook_url)}")
                return True
            else:
                print(f"   ❌ Ошибка: {result.get('description', 'Unknown error')}")
                return False
        else:
            print(f"   ❌ HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_webhook_status():
    """Проверяет статус webhook"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        return
    
    print()
    print("3️⃣ Проверка статуса webhook...")
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                webhook_info = result.get('result', {})
                url = webhook_info.get('url', '')
                pending = webhook_info.get('pending_update_count', 0)
                last_error = webhook_info.get('last_error_message', '')
                
                if url:
                    print(f"   ✅ Webhook установлен: {url}")
                    print(f"   Ожидающих обновлений: {pending}")
                    if last_error:
                        print(f"   ⚠️  Последняя ошибка: {last_error}")
                else:
                    print(f"   ❌ Webhook не установлен")
    except Exception as e:
        print(f"   ⚠️  Ошибка при проверке: {e}")


if __name__ == '__main__':
    try:
        success = setup_telegram_webhook()
        check_webhook_status()
        
        print()
        print("=" * 80)
        if success:
            print("✅ WEBHOOK УСТАНОВЛЕН")
            print()
            print("💡 Теперь бот будет получать обновления через webhook")
            print("   Убедитесь, что webhook сервер запущен и доступен")
        else:
            print("❌ НЕ УДАЛОСЬ УСТАНОВИТЬ WEBHOOK")
            print()
            print("💡 Проверьте:")
            print("   1. TELEGRAM_BOT_TOKEN установлен")
            print("   2. TELEGRAM_WEBHOOK_URL установлен и доступен")
            print("   3. Webhook сервер запущен")
        print("=" * 80)
        
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)






