#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Локальный тест создания ссылки на оплату через ЮKassa API
Запуск: python test_yookassa_payment_link.py

Этот скрипт тестирует создание платежной ссылки через прямой запрос к API ЮKassa
"""

import os
import sys
import requests
import base64
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("🔍 ЛОКАЛЬНЫЙ ТЕСТ СОЗДАНИЯ ССЫЛКИ НА ОПЛАТУ ЧЕРЕЗ ЮKASSA API")
print("=" * 70)
print()

# Загружаем переменные окружения
shop_id = os.getenv('YOOKASSA_SHOP_ID', '').strip()
secret_key = os.getenv('YOOKASSA_SECRET_KEY', '').strip()
bot_username = os.getenv('TELEGRAM_BOT_USERNAME', '').strip()

if not shop_id or not secret_key:
    print("❌ Ошибка: YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не найдены в .env файле")
    print()
    print("Создайте файл .env в корне проекта со следующим содержимым:")
    print("YOOKASSA_SHOP_ID=ваш_shop_id")
    print("YOOKASSA_SECRET_KEY=ваш_secret_key")
    print("TELEGRAM_BOT_USERNAME=ваш_bot_username (опционально)")
    sys.exit(1)

print(f"✅ Переменные окружения найдены")
print(f"   Shop ID: {shop_id}")
print(f"   Secret Key: {'*' * (len(secret_key) - 4)}{secret_key[-4:]}")
if bot_username:
    print(f"   Bot Username: {bot_username}")
print()

# Обрабатываем return_url
return_url_env = os.getenv('PAYMENT_RETURN_URL', '').strip()
if return_url_env.startswith('PAYMENT_RETURN_URL='):
    return_url_env = return_url_env.replace('PAYMENT_RETURN_URL=', '', 1).strip()

if return_url_env:
    return_url = return_url_env
elif bot_username:
    return_url = f'https://t.me/{bot_username}?start=payment_cancel'
else:
    return_url = 'https://t.me/test_bot?start=payment_cancel'

print(f"🔗 Return URL: {return_url}")
print()

# Проверяем формат return_url
if not return_url.startswith('https://'):
    print(f"❌ Ошибка: return_url должен начинаться с https://, получен: {return_url}")
    sys.exit(1)

# Параметры платежа
user_id = 123456789  # Тестовый user_id
amount_rub = 499.00
description = "Натальная карта - детальный астрологический разбор"

# Формируем ID платежа
payment_id = f"natal_chart_{user_id}_{uuid.uuid4().hex[:8]}"

print(f"📦 Параметры платежа:")
print(f"   User ID: {user_id}")
print(f"   Amount: {amount_rub} RUB")
print(f"   Payment ID: {payment_id}")
print(f"   Description: {description}")
print()

# Подготовка данных для создания платежа
# Минимальный набор полей согласно документации ЮKassa API v3
amount_value_str = f"{amount_rub:.2f}"

payment_data = {
    "amount": {
        "value": amount_value_str,  # Строка с двумя знаками после запятой
        "currency": "RUB"
    },
    "confirmation": {
        "type": "redirect",
        "return_url": return_url  # Обязательное поле для redirect типа
    },
    "capture": True,  # Автоматическое подтверждение платежа
    "description": description,  # Описание платежа (максимум 128 символов)
    "metadata": {
        "user_id": str(user_id),
        "payment_type": "natal_chart"
    },
    "receipt": {
        "customer": {
            "email": f"user_{user_id}@telegram.bot"  # Минимальный email для фискализации
        },
        "items": [
            {
                "description": description[:128],  # Название товара (максимум 128 символов)
                "quantity": "1.00",
                "amount": {
                    "value": amount_value_str,
                    "currency": "RUB"
                },
                "vat_code": 1,  # НДС 20% (стандартная ставка для цифровых услуг в РФ)
                "payment_mode": "full_prepayment",  # Полная предоплата
                "payment_subject": "service"  # Цифровая услуга
            }
        ]
    }
}

# Проверяем длину description
if len(description) > 128:
    print(f"⚠️  Description слишком длинный ({len(description)} символов), обрезаем до 128")
    payment_data["description"] = description[:125] + "..."

print(f"📋 Тело запроса:")
print(json.dumps(payment_data, indent=2, ensure_ascii=False))
print()

# Авторизация через Basic Auth
auth_string = f"{shop_id}:{secret_key}"
auth_bytes = auth_string.encode('ascii')
auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
headers = {
    "Authorization": f"Basic {auth_b64}",
    "Content-Type": "application/json",
    "Idempotence-Key": payment_id
}

print(f"🔑 Заголовки запроса:")
print(f"   Authorization: Basic {auth_b64[:20]}...")
print(f"   Content-Type: application/json")
print(f"   Idempotence-Key: {payment_id}")
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
    print("✅ Прокси в окружении не обнаружено")
print()

# URL для запроса
payment_api_url = "https://api.yookassa.ru/v3/payments"
print(f"🌐 URL для запроса: {payment_api_url}")
print()

# Отправка запроса
start_time = datetime.now()
print("📤 Отправка POST запроса к ЮKassa API...")
print(f"⏱️  Timeout: (10 секунд на подключение, 60 секунд на чтение)")
print()

try:
    response = requests.post(
        payment_api_url,
        json=payment_data,
        headers=headers,
        timeout=(10, 60)  # 10 сек на подключение, 60 сек на чтение ответа
    )
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"✅ Ответ получен за {duration:.2f} секунд")
    print(f"📡 Status Code: {response.status_code}")
    print()
    
    if response.status_code == 200:
        payment_info = response.json()
        
        # Проверяем структуру ответа
        payment_yookassa_id = payment_info.get('id')
        payment_status = payment_info.get('status')
        confirmation = payment_info.get('confirmation', {})
        payment_url = confirmation.get('confirmation_url')
        
        print("=" * 70)
        print("✅ УСПЕХ! Ссылка на оплату создана")
        print("=" * 70)
        print()
        print(f"📋 Информация о платеже:")
        print(f"   Payment ID: {payment_yookassa_id}")
        print(f"   Status: {payment_status}")
        print(f"   Amount: {payment_info.get('amount', {}).get('value')} {payment_info.get('amount', {}).get('currency')}")
        print(f"   Description: {payment_info.get('description')}")
        print()
        
        if payment_url:
            print(f"🔗 Payment URL (ссылка на оплату):")
            print(f"   {payment_url}")
            print()
            print("💡 Эта ссылка откроет экран выбора способов оплаты:")
            print("   • SberPay")
            print("   • Банковская карта")
            print("   • ЮMoney")
            print("   • T-Pay")
            print("   • СБП")
            print()
        else:
            print("❌ В ответе отсутствует confirmation_url")
            print(f"   Полный ответ: {json.dumps(payment_info, indent=2, ensure_ascii=False)}")
        
    elif response.status_code == 401:
        print("=" * 70)
        print("❌ ОШИБКА АУТЕНТИФИКАЦИИ (401 Unauthorized)")
        print("=" * 70)
        print()
        print("💡 Проверьте:")
        print("   1. YOOKASSA_SHOP_ID правильный")
        print("   2. YOOKASSA_SECRET_KEY правильный")
        print("   3. Используете ключи из правильного окружения (тестовое/продакшн)")
        print()
        try:
            error_details = response.json()
            print(f"📋 Детали ошибки:")
            print(json.dumps(error_details, indent=2, ensure_ascii=False))
        except:
            print(f"📄 Ответ сервера: {response.text}")
    
    elif response.status_code == 400:
        print("=" * 70)
        print("❌ ОШИБКА В ЗАПРОСЕ (400 Bad Request)")
        print("=" * 70)
        print()
        print("💡 Проверьте формат данных в запросе")
        print()
        try:
            error_details = response.json()
            print(f"📋 Детали ошибки:")
            print(json.dumps(error_details, indent=2, ensure_ascii=False))
        except:
            print(f"📄 Ответ сервера: {response.text}")
    
    else:
        print(f"⚠️  Неожиданный статус код: {response.status_code}")
        print(f"📄 Ответ сервера: {response.text}")
        
except requests.exceptions.ConnectTimeout:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ ConnectTimeout после {duration:.2f} секунд")
    print()
    print("=" * 70)
    print("❌ НЕ УДАЛОСЬ УСТАНОВИТЬ TCP СОЕДИНЕНИЕ")
    print("=" * 70)
    print()
    print("💡 Возможные причины:")
    print("   • Блокировка на уровне сети/провайдера")
    print("   • Проблемы с DNS")
    print("   • Firewall блокирует подключение")
    print("   • Недоступность api.yookassa.ru")
    sys.exit(1)
    
except requests.exceptions.ReadTimeout:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ ReadTimeout после {duration:.2f} секунд")
    print()
    print("=" * 70)
    print("❌ СОЕДИНЕНИЕ УСТАНОВЛЕНО, НО ОТВЕТ НЕ ПОЛУЧЕН")
    print("=" * 70)
    print()
    print("💡 Возможные причины:")
    print("   • API ЮKassa перегружен или медленно отвечает")
    print("   • Медленное сетевое подключение")
    print("   • Проблемы с маршрутизацией к api.yookassa.ru")
    sys.exit(1)
    
except requests.exceptions.ConnectionError as conn_error:
    error_str = str(conn_error)
    print(f"❌ ConnectionError")
    print()
    print("=" * 70)
    print("❌ ОШИБКА ПОДКЛЮЧЕНИЯ К ЮKASSA API")
    print("=" * 70)
    print()
    print(f"📋 Детали: {error_str}")
    print()
    
    if "RemoteDisconnected" in error_str or "Remote end closed connection" in error_str:
        print("🔍 Сервер ЮKassa закрыл соединение без ответа")
        print()
        print("💡 Возможные причины:")
        print("   • Проблемы на стороне API ЮKassa (перегрузка, временная недоступность)")
        print("   • Блокировка соединений на уровне сети (firewall, rate limiting)")
        print("   • Проблемы с keep-alive соединениями")
    elif "NewConnectionError" in error_str or "Failed to establish" in error_str:
        print("🔍 Не удалось установить TCP соединение")
        print()
        print("💡 Возможные причины:")
        print("   • Недоступность api.yookassa.ru")
        print("   • Проблемы с DNS")
        print("   • Блокировка на уровне сети")
    else:
        print("🔍 Общая ошибка соединения")
    sys.exit(1)
    
except requests.exceptions.RequestException as req_error:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ RequestException после {duration:.2f} секунд")
    print(f"   Тип: {type(req_error).__name__}")
    print(f"   Ошибка: {req_error}")
    sys.exit(1)
    
except Exception as e:
    duration = (datetime.now() - start_time).total_seconds()
    print(f"❌ Неожиданная ошибка после {duration:.2f} секунд")
    print(f"   Тип: {type(e).__name__}")
    print(f"   Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

