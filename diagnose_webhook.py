#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Детальная диагностика webhook YooKassa
"""

import os
import sys
import requests
import json
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def check_webhook_detailed():
    """Детальная проверка webhook"""
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    if not webhook_url:
        print("❌ YOOKASSA_WEBHOOK_URL не установлен")
        return
    
    print("=" * 80)
    print("🔍 ДЕТАЛЬНАЯ ДИАГНОСТИКА WEBHOOK")
    print("=" * 80)
    print()
    
    parsed = urlparse(webhook_url)
    print(f"📋 Информация о webhook URL:")
    print(f"   Полный URL: {webhook_url}")
    print(f"   Схема: {parsed.scheme}")
    print(f"   Hostname: {parsed.hostname}")
    print(f"   Порт: {parsed.port or (443 if parsed.scheme == 'https' else 80)}")
    print(f"   Путь: {parsed.path}")
    print()
    
    # Проверка 1: Доступность домена
    print("1️⃣ Проверка доступности домена...")
    try:
        response = requests.get(
            f"{parsed.scheme}://{parsed.hostname}",
            timeout=10,
            allow_redirects=True
        )
        print(f"   ✅ Домен доступен (HTTP {response.status_code})")
    except requests.exceptions.SSLError as e:
        print(f"   ❌ Ошибка SSL: {e}")
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ Не удалось подключиться: {e}")
    except Exception as e:
        print(f"   ⚠️  Ошибка: {e}")
    print()
    
    # Проверка 2: Health check endpoint (если есть)
    health_url = f"{parsed.scheme}://{parsed.hostname}/health"
    print("2️⃣ Проверка health endpoint...")
    try:
        response = requests.get(health_url, timeout=10)
        if response.status_code == 200:
            print(f"   ✅ Health endpoint работает: {response.text[:100]}")
        else:
            print(f"   ⚠️  Health endpoint вернул {response.status_code}")
    except Exception as e:
        print(f"   ⚠️  Health endpoint недоступен: {e}")
    print()
    
    # Проверка 3: Webhook endpoint с разными методами
    print("3️⃣ Проверка webhook endpoint...")
    
    # GET запрос (должен вернуть 405 Method Not Allowed или ошибку)
    try:
        response = requests.get(webhook_url, timeout=10)
        print(f"   GET запрос: HTTP {response.status_code}")
        if response.status_code == 405:
            print(f"   ✅ Endpoint существует, но GET не разрешен (это нормально)")
        elif response.status_code == 502:
            print(f"   ❌ 502 Bad Gateway - сервер webhook не запущен или недоступен")
        elif response.status_code == 404:
            print(f"   ❌ 404 Not Found - путь не найден")
        else:
            print(f"   Ответ: {response.text[:200]}")
    except Exception as e:
        print(f"   ❌ Ошибка при GET запросе: {e}")
    
    # POST запрос с тестовыми данными
    print()
    print("   POST запрос с тестовыми данными...")
    test_data = {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": "test-payment-123",
            "status": "succeeded"
        }
    }
    
    try:
        response = requests.post(
            webhook_url,
            json=test_data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        print(f"   POST запрос: HTTP {response.status_code}")
        print(f"   Ответ: {response.text[:300]}")
        
        if response.status_code == 200:
            print(f"   ✅ Webhook работает корректно!")
        elif response.status_code == 502:
            print(f"   ❌ 502 Bad Gateway")
            print(f"   💡 Возможные причины:")
            print(f"      - Бот не запущен")
            print(f"      - Webhook сервер не запустился")
            print(f"      - Проблема с прокси/маршрутизацией в Timeweb Cloud")
            print(f"      - Порт 8080 не доступен извне")
        elif response.status_code == 404:
            print(f"   ❌ 404 Not Found - путь /webhook/yookassa не найден")
        else:
            print(f"   ⚠️  Неожиданный код ответа")
    except requests.exceptions.SSLError as e:
        print(f"   ❌ Ошибка SSL: {e}")
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ Не удалось подключиться: {e}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    print()
    
    # Проверка 4: Информация о настройках
    print("4️⃣ Проверка настроек...")
    webhook_port = os.getenv('WEBHOOK_PORT', '8080')
    print(f"   WEBHOOK_PORT: {webhook_port}")
    
    shop_id = os.getenv('YOOKASSA_SHOP_ID', '')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY', '')
    print(f"   YOOKASSA_SHOP_ID: {'✅ Установлен' if shop_id else '❌ Не установлен'}")
    print(f"   YOOKASSA_SECRET_KEY: {'✅ Установлен' if secret_key else '❌ Не установлен'}")
    print()
    
    # Рекомендации
    print("=" * 80)
    print("💡 РЕКОМЕНДАЦИИ:")
    print("=" * 80)
    print()
    
    print("Если получили 502 Bad Gateway:")
    print("1. Проверьте, что бот запущен на сервере")
    print("2. Проверьте логи бота - должно быть:")
    print("   '🌐 Запуск webhook сервера на 0.0.0.0:8080'")
    print("3. Проверьте настройки прокси в Timeweb Cloud:")
    print("   - Запросы к /webhook/yookassa должны проксироваться на localhost:8080")
    print("4. Проверьте, что порт 8080 открыт и доступен")
    print()
    
    print("Если получили 404 Not Found:")
    print("1. Проверьте путь в YOOKASSA_WEBHOOK_URL")
    print("2. Убедитесь, что путь заканчивается на /webhook/yookassa")
    print()
    
    print("Если получили 200 OK:")
    print("✅ Webhook работает! Зарегистрируйте его в YooKassa:")
    print(f"   URL: {webhook_url}")
    print()
    print("=" * 80)


if __name__ == '__main__':
    try:
        check_webhook_detailed()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

