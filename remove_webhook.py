#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для удаления webhook из Telegram
Используйте этот скрипт, если бот использует polling вместо webhook
"""

import os
import sys
import requests
import asyncio
from dotenv import load_dotenv

load_dotenv()

def remove_webhook():
    """Удаляет webhook из Telegram"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return False
    
    print("=" * 80)
    print("🗑️  УДАЛЕНИЕ WEBHOOK ИЗ TELEGRAM")
    print("=" * 80)
    print()
    
    # Проверяем текущий статус webhook
    print("1️⃣ Проверка текущего статуса webhook...")
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
                
                if url:
                    print(f"   ⚠️  Webhook установлен: {url}")
                else:
                    print(f"   ✅ Webhook не установлен (уже удален)")
                    return True
        else:
            print(f"   ⚠️  Не удалось проверить статус: HTTP {response.status_code}")
    except Exception as e:
        print(f"   ⚠️  Ошибка при проверке: {e}")
    
    print()
    
    # Удаляем webhook
    print("2️⃣ Удаление webhook...")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
            json={'drop_pending_updates': True},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print(f"   ✅ Webhook успешно удален")
                print(f"   Старые обновления пропущены: {result.get('result', {}).get('drop_pending_updates', False)}")
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


if __name__ == '__main__':
    try:
        success = remove_webhook()
        print()
        print("=" * 80)
        if success:
            print("✅ WEBHOOK УДАЛЕН")
            print()
            print("Теперь бот может использовать polling (getUpdates)")
        else:
            print("❌ НЕ УДАЛОСЬ УДАЛИТЬ WEBHOOK")
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






