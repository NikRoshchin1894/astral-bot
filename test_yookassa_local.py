#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Локальный тест подключения к API ЮKassa
Запуск: python test_yookassa_local.py

Этот скрипт помогает определить, является ли проблема сетевой (Railway) 
или связана с кодом/конфигурацией.
"""

import os
import sys
import requests
import base64
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("🔍 ЛОКАЛЬНЫЙ ТЕСТ ПОДКЛЮЧЕНИЯ К ЮKASSA API")
print("=" * 70)
print()

# Загружаем переменные окружения
shop_id = os.getenv('YOOKASSA_SHOP_ID')
secret_key = os.getenv('YOOKASSA_SECRET_KEY')

if not shop_id or not secret_key:
    print("❌ Ошибка: YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не найдены в .env файле")
    print()
    print("Создайте файл .env в корне проекта со следующим содержимым:")
    print("YOOKASSA_SHOP_ID=ваш_shop_id")
    print("YOOKASSA_SECRET_KEY=ваш_secret_key")
    sys.exit(1)

print(f"✅ Переменные окружения найдены")
print(f"   Shop ID: {shop_id}")
print(f"   Secret Key: {'*' * (len(secret_key) - 4)}{secret_key[-4:]}")
print()

# Проверяем прокси
proxy_env_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
proxy_found = False
for proxy_var in proxy_env_vars:
    proxy_value = os.getenv(proxy_var)
    if proxy_value:
        print(f"⚠️  Найден прокси: {proxy_var}={proxy_value}")
        proxy_found = True

if not proxy_found:
    print("✅ Прокси не обнаружен")
print()

# Подготовка авторизации
auth_string = f"{shop_id}:{secret_key}"
auth_bytes = auth_string.encode('ascii')
auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
headers = {
    "Authorization": f"Basic {auth_b64}",
    "Content-Type": "application/json",
    "Idempotence-Key": f"test-local-{datetime.now().timestamp()}"
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
    "description": "Тестовый платеж для локальной проверки подключения"
}

url = "https://api.yookassa.ru/v3/payments"

print(f"🌐 URL: {url}")
print(f"📤 Отправка POST запроса...")
print()

# Измеряем время выполнения
start_time = datetime.now()

# Сначала делаем простую проверку доступности API
print("🔍 Шаг 1: Проверка доступности API (HEAD запрос)...")
try:
    head_response = requests.head(
        "https://api.yookassa.ru",
        timeout=5,
        allow_redirects=True
    )
    print(f"   ✅ API доступен (статус: {head_response.status_code})")
    print()
except Exception as e:
    print(f"   ⚠️  Не удалось проверить доступность: {e}")
    print()

try:
    print("⏱️  Таймаут: 60 секунд (увеличен для диагностики)")
    print("📡 Отправка POST запроса...")
    print()
    
    # Используем tuple для timeout: (connect_timeout, read_timeout)
    response = requests.post(
        url,
        json=payment_data,
        headers=headers,
        timeout=(10, 30)  # 10 секунд на подключение, 30 секунд на чтение
    )
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"✅ Ответ получен за {duration:.2f} секунд")
    print(f"📡 Status Code: {response.status_code}")
    print(f"📄 Response Headers:")
    for key, value in response.headers.items():
        if key.lower() in ['content-type', 'x-request-id', 'content-length']:
            print(f"   {key}: {value}")
    print()
    
    if response.status_code == 200:
        payment_info = response.json()
        print(f"✅ УСПЕХ! Платеж создан:")
        print(f"   Payment ID: {payment_info.get('id')}")
        print(f"   Status: {payment_info.get('status')}")
        print(f"   Amount: {payment_info.get('amount', {}).get('value')} {payment_info.get('amount', {}).get('currency')}")
        confirmation_url = payment_info.get('confirmation', {}).get('confirmation_url')
        if confirmation_url:
            print(f"   Payment URL: {confirmation_url[:60]}...")
        print()
        print("=" * 70)
        print("✅ ЛОКАЛЬНОЕ ПОДКЛЮЧЕНИЕ РАБОТАЕТ")
        print("=" * 70)
        print()
        print("💡 Вывод: Если локально работает, а на Railway нет -")
        print("   проблема в сетевом подключении Railway → ЮKassa")
        
    elif response.status_code == 401:
        print(f"❌ Ошибка 401 - Неверные credentials")
        print(f"   Проверьте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")
        try:
            error_details = response.json()
            print(f"   Детали: {json.dumps(error_details, ensure_ascii=False, indent=2)}")
        except:
            print(f"   Ответ сервера: {response.text}")
        
    else:
        print(f"⚠️  Неожиданный статус: {response.status_code}")
        print(f"   Ответ сервера: {response.text[:200]}")
        
except requests.exceptions.ConnectTimeout:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ ConnectTimeout после {duration:.2f} секунд")
    print()
    print("=" * 70)
    print("❌ НЕ УДАЛОСЬ УСТАНОВИТЬ TCP СОЕДИНЕНИЕ")
    print("=" * 70)
    print()
    print("💡 Это указывает на проблему сети/доступа к api.yookassa.ru")
    print("   Возможные причины:")
    print("   • Блокировка на уровне сети/провайдера")
    print("   • Проблемы с DNS")
    print("   • Firewall блокирует подключение")
    print()
    print("🔍 Проверьте доступность API:")
    print("   curl -v https://api.yookassa.ru/v3/payments")
    sys.exit(1)
    
except requests.exceptions.ReadTimeout:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ ReadTimeout после {duration:.2f} секунд")
    print()
    print("=" * 70)
    print("❌ СОЕДИНЕНИЕ УСТАНОВЛЕНО, НО ОТВЕТ НЕ ПОЛУЧЕН")
    print("=" * 70)
    print()
    print("💡 Это указывает, что:")
    print("   • TCP соединение установлено успешно")
    print("   • Но API ЮKassa медленно отвечает или перегружен")
    print()
    print("🔍 Возможные причины:")
    print("   • Проблемы на стороне API ЮKassa")
    print("   • Медленное сетевое подключение к ЮKassa")
    print("   • Проблемы с маршрутизацией к api.yookassa.ru")
    print()
    print("📊 Сравнение с Railway:")
    print("   • Если локально таймаут → проблема может быть не только в Railway")
    print("   • Если на Railway таймаут, а локально работает → проблема в Railway")
    print("   • Если везде таймаут → проблема в API ЮKassa или сети")
    print()
    print("🔍 Попробуйте:")
    print("   1. Повторить запрос через несколько минут")
    print("   2. Проверить статус API ЮKassa на их сайте")
    print("   3. Проверить с другого интернет-соединения")
    sys.exit(1)
    
except requests.exceptions.ConnectionError as e:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ ConnectionError после {duration:.2f} секунд")
    print(f"   Ошибка: {e}")
    print()
    print("=" * 70)
    print("❌ ОШИБКА ПОДКЛЮЧЕНИЯ")
    print("=" * 70)
    print()
    print("💡 Не удалось установить соединение с api.yookassa.ru")
    print("   Проверьте интернет-соединение и доступность API")
    sys.exit(1)
    
except requests.exceptions.RequestException as e:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ RequestException после {duration:.2f} секунд")
    print(f"   Тип: {type(e).__name__}")
    print(f"   Ошибка: {e}")
    sys.exit(1)
    
except Exception as e:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ Неожиданная ошибка после {duration:.2f} секунд")
    print(f"   Тип: {type(e).__name__}")
    print(f"   Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

