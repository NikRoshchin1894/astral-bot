#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки статуса бота и webhook в Telegram
"""

import os
import sys
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def check_bot_status():
    """Проверяет статус бота и webhook в Telegram"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return
    
    print("=" * 80)
    print("🔍 ПРОВЕРКА СТАТУСА БОТА В TELEGRAM")
    print("=" * 80)
    print()
    
    # Проверка информации о боте
    print("1️⃣ Информация о боте...")
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getMe",
            timeout=10
        )
        if response.status_code == 200:
            bot_info = response.json()
            if bot_info.get('ok'):
                bot_data = bot_info.get('result', {})
                print(f"   ✅ Бот активен")
                print(f"   Имя: {bot_data.get('first_name', 'N/A')}")
                print(f"   Username: @{bot_data.get('username', 'N/A')}")
                print(f"   ID: {bot_data.get('id', 'N/A')}")
            else:
                print(f"   ❌ Ошибка: {bot_info.get('description', 'Unknown error')}")
        else:
            print(f"   ❌ HTTP {response.status_code}: {response.text}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    print()
    
    # Проверка webhook
    print("2️⃣ Статус webhook...")
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
            timeout=10
        )
        if response.status_code == 200:
            webhook_info = response.json()
            if webhook_info.get('ok'):
                webhook_data = webhook_info.get('result', {})
                url = webhook_data.get('url', '')
                pending_updates = webhook_data.get('pending_update_count', 0)
                last_error_date = webhook_data.get('last_error_date')
                last_error_message = webhook_data.get('last_error_message', '')
                
                if url:
                    print(f"   ⚠️  Webhook УСТАНОВЛЕН")
                    print(f"   URL: {url}")
                    print(f"   Ожидающих обновлений: {pending_updates}")
                    
                    if last_error_date:
                        print(f"   ⚠️  Последняя ошибка: {last_error_message}")
                        print(f"   Дата ошибки: {last_error_date}")
                    
                    print()
                    print("   💡 ВНИМАНИЕ: Если бот использует polling, webhook нужно удалить!")
                    print("   💡 Удалить webhook: python remove_webhook.py")
                else:
                    print(f"   ✅ Webhook НЕ установлен (используется polling)")
            else:
                print(f"   ❌ Ошибка: {webhook_info.get('description', 'Unknown error')}")
        else:
            print(f"   ❌ HTTP {response.status_code}: {response.text}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    print()
    
    # Проверка обновлений
    print("3️⃣ Проверка получения обновлений...")
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1&limit=1",
            timeout=10
        )
        if response.status_code == 200:
            updates_info = response.json()
            if updates_info.get('ok'):
                updates = updates_info.get('result', [])
                print(f"   ✅ API доступен")
                print(f"   Последних обновлений: {len(updates)}")
                
                if response.status_code == 409:
                    print(f"   ❌ КОНФЛИКТ: Другой экземпляр бота уже получает обновления!")
                    print(f"   💡 Остановите все другие экземпляры бота")
            else:
                error_desc = updates_info.get('description', '')
                if 'Conflict' in error_desc or '409' in str(response.status_code):
                    print(f"   ❌ КОНФЛИКТ: {error_desc}")
                    print(f"   💡 Другой экземпляр бота уже запущен!")
                else:
                    print(f"   ⚠️  Ошибка: {error_desc}")
        elif response.status_code == 409:
            print(f"   ❌ КОНФЛИКТ: HTTP 409")
            print(f"   💡 Другой экземпляр бота уже получает обновления!")
        else:
            print(f"   ⚠️  HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    print()
    print("=" * 80)
    print("💡 РЕКОМЕНДАЦИИ:")
    print("=" * 80)
    print()
    print("Если webhook установлен, но бот использует polling:")
    print("  python remove_webhook.py")
    print()
    print("Если есть конфликт (409):")
    print("  1. Остановите все экземпляры бота")
    print("  2. Убедитесь, что запущен только один процесс")
    print("  3. Перезапустите бота")
    print()
    print("=" * 80)


if __name__ == '__main__':
    try:
        check_bot_status()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)






