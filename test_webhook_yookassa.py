#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования webhook YooKassa
Отправляет тестовое уведомление на webhook endpoint
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def send_test_webhook():
    """Отправляет тестовое webhook уведомление"""
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    if not webhook_url:
        print("❌ YOOKASSA_WEBHOOK_URL не установлен")
        print("   Установите переменную окружения YOOKASSA_WEBHOOK_URL")
        return False
    
    print(f"🔍 Отправка тестового webhook на: {webhook_url}")
    print()
    
    # Тестовое уведомление о успешном платеже
    test_notification = {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": "test-payment-id-12345",
            "status": "succeeded",
            "amount": {
                "value": "499.00",
                "currency": "RUB"
            },
            "created_at": "2025-12-04T20:00:00.000Z",
            "description": "Тестовый платеж",
            "metadata": {
                "user_id": "123456789",
                "payment_type": "natal_chart"
            },
            "payment_method": {
                "type": "bank_card",
                "card": {
                    "last4": "4242",
                    "card_type": "MasterCard"
                }
            }
        }
    }
    
    try:
        print("📤 Отправка запроса...")
        response = requests.post(
            webhook_url,
            json=test_notification,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        print(f"✅ Ответ получен: HTTP {response.status_code}")
        print(f"   Ответ: {response.text[:200]}")
        
        if response.status_code == 200:
            print()
            print("✅ Webhook endpoint работает корректно!")
            return True
        else:
            print()
            print(f"⚠️  Endpoint вернул код {response.status_code}")
            return False
            
    except requests.exceptions.SSLError as e:
        print(f"❌ Ошибка SSL: {e}")
        print("   Проверьте SSL сертификат")
        return False
        
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Не удалось подключиться: {e}")
        print("   Проверьте:")
        print("   - Сервер запущен")
        print("   - URL правильный")
        print("   - Нет проблем с сетью")
        return False
        
    except requests.exceptions.Timeout:
        print("❌ Таймаут при подключении")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_test_canceled_webhook():
    """Отправляет тестовое уведомление об отмене платежа"""
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    if not webhook_url:
        return False
    
    print()
    print("🔍 Отправка тестового webhook об отмене платежа...")
    
    test_notification = {
        "type": "notification",
        "event": "payment.canceled",
        "object": {
            "id": "test-payment-id-67890",
            "status": "canceled",
            "amount": {
                "value": "499.00",
                "currency": "RUB"
            },
            "created_at": "2025-12-04T20:00:00.000Z",
            "cancellation_details": {
                "party": "yoo_money",
                "reason": "expired_on_confirmation"
            },
            "metadata": {
                "user_id": "123456789",
                "payment_type": "natal_chart"
            }
        }
    }
    
    try:
        response = requests.post(
            webhook_url,
            json=test_notification,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        print(f"✅ Ответ получен: HTTP {response.status_code}")
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


if __name__ == '__main__':
    print("=" * 80)
    print("🧪 ТЕСТИРОВАНИЕ WEBHOOK YOOKASSA")
    print("=" * 80)
    print()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--canceled':
        success = send_test_canceled_webhook()
    else:
        success = send_test_webhook()
    
    print()
    print("=" * 80)
    if success:
        print("✅ ТЕСТ ПРОЙДЕН")
        print()
        print("💡 Примечание:")
        print("   Это тестовый запрос. В реальных условиях YooKassa будет")
        print("   отправлять уведомления автоматически при изменении статуса платежа.")
    else:
        print("❌ ТЕСТ НЕ ПРОЙДЕН")
        print()
        print("💡 Проверьте:")
        print("   1. Webhook URL правильный и доступен")
        print("   2. Сервер запущен")
        print("   3. Нет проблем с сетью/SSL")
    print("=" * 80)
    print()
    
    sys.exit(0 if success else 1)






