#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Комплексная проверка всех webhook (Telegram и YooKassa)
"""

import os
import sys
import requests
import json
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def print_header(title):
    """Печатает заголовок секции"""
    print()
    print("=" * 80)
    print(f"🔍 {title}")
    print("=" * 80)
    print()

def check_telegram_webhook():
    """Проверяет Telegram webhook"""
    print_header("ПРОВЕРКА TELEGRAM WEBHOOK")
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
    
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return False
    
    print(f"✅ TELEGRAM_BOT_TOKEN установлен: {bot_token[:10]}...")
    
    if not webhook_url:
        print("❌ TELEGRAM_WEBHOOK_URL не установлен")
        print()
        print("💡 Решение:")
        print("   Бот будет работать в режиме polling вместо webhook")
        return False
    
    print(f"✅ TELEGRAM_WEBHOOK_URL установлен: {webhook_url}")
    
    # Проверяем формат URL
    parsed = urlparse(webhook_url)
    if parsed.scheme != 'https':
        print(f"❌ URL должен использовать HTTPS, текущая схема: {parsed.scheme}")
        return False
    
    print(f"✅ URL использует HTTPS")
    print(f"✅ Hostname: {parsed.hostname}")
    print(f"✅ Путь: {parsed.path}")
    print()
    
    # Проверяем статус webhook через Telegram API
    print("📡 Проверка статуса webhook через Telegram API...")
    try:
        api_url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Не удалось получить информацию о webhook (HTTP {response.status_code})")
            print(f"   Ответ: {response.text[:200]}")
            return False
        
        webhook_info = response.json()
        
        if not webhook_info.get('ok'):
            print(f"❌ Ошибка API: {webhook_info.get('description', 'Неизвестная ошибка')}")
            return False
        
        result = webhook_info.get('result', {})
        current_url = result.get('url', '')
        pending_updates = result.get('pending_update_count', 0)
        last_error_date = result.get('last_error_date')
        last_error_message = result.get('last_error_message', '')
        max_connections = result.get('max_connections', 40)
        allowed_updates = result.get('allowed_updates', [])
        
        print(f"   Текущий URL: {current_url if current_url else '(не установлен)'}")
        print(f"   Ожидающих обновлений: {pending_updates}")
        print(f"   Макс. соединений: {max_connections}")
        
        if last_error_date:
            from datetime import datetime
            error_time = datetime.fromtimestamp(last_error_date)
            print(f"   ❌ Последняя ошибка: {error_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Сообщение: {last_error_message[:200]}")
        
        if not current_url:
            print()
            print("⚠️  Webhook не установлен в Telegram")
            print(f"   Требуемый URL: {webhook_url}")
            return False
        
        if current_url != webhook_url:
            print()
            print(f"⚠️  Webhook URL не совпадает!")
            print(f"   Текущий в Telegram: {current_url}")
            print(f"   Ожидаемый: {webhook_url}")
            return False
        
        if last_error_date:
            print()
            print("❌ Webhook установлен, но есть ошибки")
            return False
        
        print()
        print("✅ Telegram webhook настроен правильно!")
        
        # Проверяем доступность endpoint
        print()
        print("🌐 Проверка доступности endpoint /webhook/telegram...")
        try:
            response = requests.post(
                webhook_url,
                json={'message': {'text': 'test'}},
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            print(f"   Endpoint доступен (HTTP {response.status_code})")
            if response.status_code == 502:
                print("   ❌ 502 Bad Gateway - сервер webhook не запущен или недоступен")
                return False
            elif response.status_code in [200, 404, 405]:
                print("   ✅ Endpoint отвечает (это нормально для тестового запроса)")
        except requests.exceptions.ConnectionError:
            print("   ❌ Не удалось подключиться к endpoint")
            return False
        except Exception as e:
            print(f"   ⚠️  Ошибка: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при проверке Telegram webhook: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_yookassa_webhook():
    """Проверяет YooKassa webhook"""
    print_header("ПРОВЕРКА YOOKASSA WEBHOOK")
    
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    if not webhook_url:
        print("❌ YOOKASSA_WEBHOOK_URL не установлен")
        print()
        print("💡 Решение:")
        print("   Добавьте переменную YOOKASSA_WEBHOOK_URL в .env файл")
        print("   Формат: https://ваш-домен.com/webhook/yookassa")
        return False
    
    print(f"✅ YOOKASSA_WEBHOOK_URL установлен: {webhook_url}")
    
    # Проверяем формат URL
    parsed = urlparse(webhook_url)
    
    if parsed.scheme != 'https':
        print(f"❌ URL должен использовать HTTPS, текущая схема: {parsed.scheme}")
        return False
    
    print(f"✅ URL использует HTTPS")
    print(f"✅ Hostname: {parsed.hostname}")
    print(f"✅ Путь: {parsed.path}")
    
    if not webhook_url.endswith('/webhook/yookassa'):
        print("⚠️  ВНИМАНИЕ: URL не заканчивается на /webhook/yookassa")
    
    # Проверяем credentials
    shop_id = os.getenv('YOOKASSA_SHOP_ID', '')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY', '')
    
    print()
    print("🔑 Проверка credentials YooKassa...")
    if not shop_id:
        print("❌ YOOKASSA_SHOP_ID не установлен")
        return False
    
    if not secret_key:
        print("❌ YOOKASSA_SECRET_KEY не установлен")
        return False
    
    print(f"✅ YOOKASSA_SHOP_ID: {shop_id[:10]}...")
    print(f"✅ YOOKASSA_SECRET_KEY: {secret_key[:10]}...")
    
    # Проверяем доступность endpoint
    print()
    print("🌐 Проверка доступности endpoint /webhook/yookassa...")
    try:
        test_data = {
            "type": "notification",
            "event": "payment.succeeded",
            "object": {
                "id": "test-payment-123",
                "status": "succeeded"
            }
        }
        
        response = requests.post(
            webhook_url,
            json=test_data,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"   Endpoint доступен (HTTP {response.status_code})")
        
        if response.status_code == 502:
            print("   ❌ 502 Bad Gateway - сервер webhook не запущен или недоступен")
            print()
            print("💡 Возможные причины:")
            print("   1. Бот не запущен на сервере")
            print("   2. Webhook сервер не запустился (проверьте логи)")
            print("   3. Проблема с прокси/маршрутизацией")
            print("   4. Порт 8080 не доступен извне")
            return False
        elif response.status_code == 404:
            print("   ❌ 404 Not Found - путь /webhook/yookassa не найден")
            return False
        elif response.status_code == 200:
            print("   ✅ Endpoint отвечает корректно!")
            return True
        else:
            print(f"   ⚠️  Неожиданный код ответа: {response.status_code}")
            print(f"   Ответ: {response.text[:200]}")
            return True  # Возможно, endpoint работает, но возвращает ошибку валидации
            
    except requests.exceptions.SSLError as e:
        print(f"   ❌ Ошибка SSL: {e}")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ Не удалось подключиться: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False


def check_webhook_server_config():
    """Проверяет конфигурацию webhook сервера"""
    print_header("ПРОВЕРКА КОНФИГУРАЦИИ WEBHOOK СЕРВЕРА")
    
    webhook_port = os.getenv('WEBHOOK_PORT', '8080')
    port = os.getenv('PORT', webhook_port)
    
    print(f"✅ PORT: {port}")
    print(f"✅ WEBHOOK_PORT: {webhook_port}")
    
    telegram_webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
    yookassa_webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    print()
    if telegram_webhook_url or yookassa_webhook_url:
        print("✅ Webhook URLs настроены:")
        if telegram_webhook_url:
            print(f"   Telegram: {telegram_webhook_url}")
        if yookassa_webhook_url:
            print(f"   YooKassa: {yookassa_webhook_url}")
        
        print()
        print("💡 Ожидаемое поведение:")
        print(f"   - Webhook сервер должен запуститься на порту {port}")
        print("   - В логах должно быть: '🌐 Запуск webhook сервера на 0.0.0.0:{port}'")
        if telegram_webhook_url:
            print("   - Telegram webhook: /webhook/telegram")
        if yookassa_webhook_url:
            print("   - YooKassa webhook: /webhook/yookassa")
    else:
        print("⚠️  TELEGRAM_WEBHOOK_URL и YOOKASSA_WEBHOOK_URL не установлены")
        print("   Бот будет работать в режиме polling")
    
    return True


def main():
    """Основная функция проверки"""
    print()
    print("=" * 80)
    print("🔍 КОМПЛЕКСНАЯ ПРОВЕРКА WEBHOOK")
    print("=" * 80)
    
    results = {}
    
    # Проверяем конфигурацию сервера
    check_webhook_server_config()
    
    # Проверяем Telegram webhook
    results['telegram'] = check_telegram_webhook()
    
    # Проверяем YooKassa webhook
    results['yookassa'] = check_yookassa_webhook()
    
    # Итоговый отчет
    print_header("ИТОГОВЫЙ ОТЧЕТ")
    
    if results.get('telegram'):
        print("✅ Telegram webhook: Работает корректно")
    elif os.getenv('TELEGRAM_WEBHOOK_URL'):
        print("❌ Telegram webhook: Проблемы обнаружены")
    else:
        print("⚪ Telegram webhook: Не настроен (будет использован polling)")
    
    if results.get('yookassa'):
        print("✅ YooKassa webhook: Работает корректно")
    elif os.getenv('YOOKASSA_WEBHOOK_URL'):
        print("❌ YooKassa webhook: Проблемы обнаружены")
    else:
        print("⚪ YooKassa webhook: Не настроен")
    
    print()
    print("=" * 80)
    
    if all(results.values()) or (not os.getenv('TELEGRAM_WEBHOOK_URL') and not os.getenv('YOOKASSA_WEBHOOK_URL')):
        print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
        if os.getenv('TELEGRAM_WEBHOOK_URL') or os.getenv('YOOKASSA_WEBHOOK_URL'):
            print()
            print("💡 Следующие шаги:")
            if os.getenv('YOOKASSA_WEBHOOK_URL'):
                print("   1. Зарегистрируйте webhook в личном кабинете YooKassa")
                print(f"      URL: {os.getenv('YOOKASSA_WEBHOOK_URL')}")
            print("   2. Проверьте логи бота при запуске")
            print("   3. Создайте тестовый платеж и проверьте логи")
    else:
        print("⚠️  ОБНАРУЖЕНЫ ПРОБЛЕМЫ")
        print()
        print("💡 Рекомендации:")
        if os.getenv('YOOKASSA_WEBHOOK_URL') and not results.get('yookassa'):
            print("   - Проверьте, что бот запущен на сервере")
            print("   - Проверьте логи бота на наличие ошибок")
            print("   - Убедитесь, что порт 8080 доступен")
        if os.getenv('TELEGRAM_WEBHOOK_URL') and not results.get('telegram'):
            print("   - Проверьте статус бота через /start в Telegram")
            print("   - Убедитесь, что webhook URL правильный")
    
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

