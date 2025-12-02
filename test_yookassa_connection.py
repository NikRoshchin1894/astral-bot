#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования подключения к API ЮKassa
Использование: python test_yookassa_connection.py
"""

import os
import sys
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

shop_id = os.getenv('YOOKASSA_SHOP_ID')
secret_key = os.getenv('YOOKASSA_SECRET_KEY')

if not shop_id or not secret_key:
    print("❌ YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены")
    sys.exit(1)

print(f"🔑 Shop ID: {shop_id}")
print(f"🔑 Secret Key: {'*' * (len(secret_key) - 4)}{secret_key[-4:]}")
print()

# Подготовка авторизации
auth_string = f"{shop_id}:{secret_key}"
auth_bytes = auth_string.encode('ascii')
auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
headers = {
    "Authorization": f"Basic {auth_b64}",
    "Content-Type": "application/json",
    "Idempotence-Key": "test-connection-123"
}

# Тестовые данные
payment_data = {
    "amount": {
        "value": "100.00",
        "currency": "RUB"
    },
    "confirmation": {
        "type": "redirect",
        "return_url": "https://t.me/test_bot?start=test"
    },
    "capture": True,
    "description": "Тестовый платеж для проверки подключения"
}

url = "https://api.yookassa.ru/v3/payments"

print(f"🌐 URL: {url}")
print(f"📤 Отправка POST запроса...")
print()

try:
    response = requests.post(
        url,
        json=payment_data,
        headers=headers,
        timeout=10  # Короткий timeout для быстрой диагностики
    )
    
    print(f"✅ Ответ получен!")
    print(f"📡 Status Code: {response.status_code}")
    print(f"📄 Response Headers: {dict(response.headers)}")
    print()
    
    if response.status_code == 200:
        payment_info = response.json()
        print(f"✅ Успешно! Платеж создан:")
        print(f"   Payment ID: {payment_info.get('id')}")
        print(f"   Status: {payment_info.get('status')}")
        print(f"   URL: {payment_info.get('confirmation', {}).get('confirmation_url')}")
    else:
        print(f"❌ Ошибка от API:")
        print(f"   {response.text}")
        
except requests.exceptions.ConnectTimeout:
    print("❌ ConnectTimeout - не удалось установить TCP соединение")
    print("   Это указывает на проблему сети/доступа к api.yookassa.ru")
    print("   Попробуйте проверить из контейнера Railway:")
    print(f'   curl -v {url} -u "{shop_id}:{secret_key}" -H "Content-Type: application/json" -d \'{{"amount":{{"value":"100.00","currency":"RUB"}}}}\'')
    
except requests.exceptions.ReadTimeout:
    print("❌ ReadTimeout - соединение установлено, но ответ не получен")
    print("   API ЮKassa медленно отвечает или перегружен")
    
except requests.exceptions.ConnectionError as e:
    print(f"❌ ConnectionError - не удалось подключиться")
    print(f"   {e}")
    
except requests.exceptions.RequestException as e:
    print(f"❌ RequestException: {type(e).__name__}")
    print(f"   {e}")
    
except Exception as e:
    print(f"❌ Неожиданная ошибка: {type(e).__name__}")
    print(f"   {e}")

