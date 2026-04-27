#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки настройки webhook YooKassa
"""

import os
import sys
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def check_webhook_url():
    """Проверяет наличие и формат webhook URL"""
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    print("=" * 80)
    print("🔍 ПРОВЕРКА НАСТРОЙКИ WEBHOOK YOOKASSA")
    print("=" * 80)
    print()
    
    if not webhook_url:
        print("❌ YOOKASSA_WEBHOOK_URL не установлен")
        print()
        print("💡 Решение:")
        print("   1. Добавьте переменную YOOKASSA_WEBHOOK_URL в .env файл или переменные окружения")
        print("   2. Формат: https://ваш-домен.com/webhook/yookassa")
        print("   3. Пример: https://your-app.railway.app/webhook/yookassa")
        return False
    
    print(f"✅ YOOKASSA_WEBHOOK_URL установлен: {webhook_url}")
    
    # Проверяем формат URL
    parsed = urlparse(webhook_url)
    
    if not parsed.scheme:
        print("❌ URL не содержит схему (http/https)")
        return False
    
    if parsed.scheme != 'https':
        print(f"⚠️  ВНИМАНИЕ: URL использует {parsed.scheme} вместо https")
        print("   YooKassa требует HTTPS для webhook!")
        return False
    
    print(f"✅ URL использует HTTPS")
    
    if not parsed.hostname:
        print("❌ URL не содержит hostname")
        return False
    
    print(f"✅ Hostname: {parsed.hostname}")
    
    if not webhook_url.endswith('/webhook/yookassa'):
        print("⚠️  ВНИМАНИЕ: URL не заканчивается на /webhook/yookassa")
        print(f"   Текущий путь: {parsed.path}")
    
    print(f"✅ Путь: {parsed.path}")
    
    return True


def check_endpoint_availability(webhook_url):
    """Проверяет доступность webhook endpoint"""
    print()
    print("🌐 Проверка доступности endpoint...")
    
    try:
        # Пробуем отправить тестовый запрос
        response = requests.post(
            webhook_url,
            json={'test': 'data'},
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"✅ Endpoint доступен (HTTP {response.status_code})")
        
        if response.status_code == 200:
            print("   Endpoint отвечает корректно")
        else:
            print(f"   ⚠️  Endpoint вернул код {response.status_code}")
            print(f"   Ответ: {response.text[:200]}")
        
        return True
        
    except requests.exceptions.SSLError as e:
        print(f"❌ Ошибка SSL: {e}")
        print("   Проверьте SSL сертификат вашего домена")
        return False
        
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Не удалось подключиться: {e}")
        print("   Проверьте, что:")
        print("   - Сервер запущен и доступен")
        print("   - URL правильный")
        print("   - Нет проблем с сетью")
        return False
        
    except requests.exceptions.Timeout:
        print("❌ Таймаут при подключении")
        print("   Сервер не отвечает в течение 10 секунд")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def check_yookassa_credentials():
    """Проверяет наличие credentials YooKassa"""
    print()
    print("🔑 Проверка credentials YooKassa...")
    
    shop_id = os.getenv('YOOKASSA_SHOP_ID', '')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY', '')
    
    if not shop_id:
        print("❌ YOOKASSA_SHOP_ID не установлен")
        return False
    
    if not secret_key:
        print("❌ YOOKASSA_SECRET_KEY не установлен")
        return False
    
    print(f"✅ YOOKASSA_SHOP_ID: {shop_id[:10]}...")
    print(f"✅ YOOKASSA_SECRET_KEY: {secret_key[:10]}...")
    
    return True


def check_webhook_port():
    """Проверяет настройку порта webhook"""
    print()
    print("🔌 Проверка порта webhook...")
    
    port = os.getenv('WEBHOOK_PORT', '8080')
    print(f"✅ WEBHOOK_PORT: {port} (по умолчанию 8080)")
    
    return True


def main():
    """Основная функция проверки"""
    print()
    
    # Проверяем webhook URL
    if not check_webhook_url():
        print()
        print("=" * 80)
        print("❌ ПРОВЕРКА НЕ ПРОЙДЕНА")
        print("=" * 80)
        sys.exit(1)
    
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    # Проверяем доступность endpoint
    endpoint_available = check_endpoint_availability(webhook_url)
    
    # Проверяем credentials
    credentials_ok = check_yookassa_credentials()
    
    # Проверяем порт
    check_webhook_port()
    
    # Итоговый результат
    print()
    print("=" * 80)
    
    if endpoint_available and credentials_ok:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print()
        print("💡 Следующие шаги:")
        print("   1. Убедитесь, что webhook зарегистрирован в личном кабинете YooKassa")
        print("   2. Проверьте логи бота при запуске (должно быть: '🌐 Запуск webhook сервера')")
        print("   3. Создайте тестовый платеж и проверьте логи")
    else:
        print("⚠️  НЕКОТОРЫЕ ПРОВЕРКИ НЕ ПРОЙДЕНЫ")
        print()
        if not endpoint_available:
            print("   ❌ Endpoint недоступен")
        if not credentials_ok:
            print("   ❌ Credentials YooKassa не настроены")
    
    print("=" * 80)
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)






