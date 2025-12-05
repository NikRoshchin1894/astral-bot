#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Быстрая проверка готовности системы оплаты и выдачи натальной карты
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

def check_mark(text, condition):
    """Выводит результат проверки"""
    mark = "✅" if condition else "❌"
    print(f"{mark} {text}")
    return condition

def print_header(title):
    """Печатает заголовок"""
    print()
    print("=" * 80)
    print(f"🔍 {title}")
    print("=" * 80)
    print()

def main():
    """Основная функция проверки"""
    print()
    print("=" * 80)
    print("💳 ПРОВЕРКА ГОТОВНОСТИ СИСТЕМЫ ОПЛАТЫ")
    print("=" * 80)
    
    results = []
    
    # 1. Проверка настроек YooKassa
    print_header("1. НАСТРОЙКИ YOOKASSA")
    
    shop_id = os.getenv('YOOKASSA_SHOP_ID', '')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY', '')
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    results.append(check_mark("YOOKASSA_SHOP_ID установлен", bool(shop_id)))
    results.append(check_mark("YOOKASSA_SECRET_KEY установлен", bool(secret_key)))
    results.append(check_mark("YOOKASSA_WEBHOOK_URL установлен", bool(webhook_url)))
    
    if webhook_url:
        if webhook_url.startswith('https://'):
            results.append(check_mark("Webhook URL использует HTTPS", True))
        else:
            results.append(check_mark("Webhook URL использует HTTPS", False))
            print("   ⚠️  YooKassa требует HTTPS!")
        
        if webhook_url.endswith('/webhook/yookassa'):
            results.append(check_mark("Webhook URL имеет правильный путь", True))
        else:
            results.append(check_mark("Webhook URL имеет правильный путь", False))
            print("   ⚠️  Должен заканчиваться на /webhook/yookassa")
    
    # 2. Проверка доступности webhook
    print_header("2. ДОСТУПНОСТЬ WEBHOOK")
    
    if webhook_url:
        try:
            response = requests.post(
                webhook_url,
                json={'test': 'data'},
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 502:
                results.append(check_mark("Webhook доступен", False))
                print("   ❌ 502 Bad Gateway - сервер не запущен или недоступен")
                print("   💡 Решение: Запустите бот на сервере")
            elif response.status_code == 404:
                results.append(check_mark("Webhook доступен", False))
                print("   ❌ 404 Not Found - путь не найден")
            elif response.status_code in [200, 405, 400]:
                results.append(check_mark("Webhook доступен", True))
                print(f"   ✅ Endpoint отвечает (HTTP {response.status_code})")
            else:
                results.append(check_mark("Webhook доступен", False))
                print(f"   ⚠️  Неожиданный код: {response.status_code}")
        except requests.exceptions.ConnectionError:
            results.append(check_mark("Webhook доступен", False))
            print("   ❌ Не удалось подключиться к webhook")
        except Exception as e:
            results.append(check_mark("Webhook доступен", False))
            print(f"   ❌ Ошибка: {e}")
    else:
        results.append(check_mark("Webhook доступен", False))
        print("   ⚠️  YOOKASSA_WEBHOOK_URL не установлен")
    
    # 3. Проверка других необходимых настроек
    print_header("3. ДРУГИЕ НАСТРОЙКИ")
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    openai_key = os.getenv('OPENAI_API_KEY', '')
    
    results.append(check_mark("TELEGRAM_BOT_TOKEN установлен", bool(bot_token)))
    results.append(check_mark("OPENAI_API_KEY установлен", bool(openai_key)))
    
    # Проверка бота через API
    if bot_token:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getMe",
                timeout=10
            )
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    bot_data = bot_info.get('result', {})
                    results.append(check_mark("Бот активен в Telegram", True))
                    print(f"   Бот: @{bot_data.get('username', 'N/A')}")
                else:
                    results.append(check_mark("Бот активен в Telegram", False))
            else:
                results.append(check_mark("Бот активен в Telegram", False))
        except Exception as e:
            results.append(check_mark("Бот активен в Telegram", False))
            print(f"   ❌ Ошибка: {e}")
    
    # 4. Проверка базы данных
    print_header("4. БАЗА ДАННЫХ")
    
    database_url = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL', '')
    
    if database_url:
        results.append(check_mark("База данных настроена", True))
        print(f"   Используется: PostgreSQL (Railway/Cloud)")
    else:
        results.append(check_mark("База данных настроена", True))
        print(f"   Используется: SQLite (локально)")
    
    # Итоговый отчет
    print_header("ИТОГОВЫЙ ОТЧЕТ")
    
    total_checks = len(results)
    passed_checks = sum(results)
    
    print(f"Пройдено проверок: {passed_checks} из {total_checks}")
    print()
    
    if all(results):
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print()
        print("💡 Следующие шаги:")
        print("   1. Зарегистрируйте webhook в личном кабинете YooKassa:")
        print(f"      URL: {webhook_url}")
        print("   2. Протестируйте оплату тестовой картой")
        print("   3. Проверьте, что натальная карта генерируется после оплаты")
    else:
        print("⚠️  ОБНАРУЖЕНЫ ПРОБЛЕМЫ")
        print()
        print("💡 Что нужно сделать:")
        
        if not shop_id or not secret_key:
            print("   ❌ Настройте YooKassa credentials (Shop ID и Secret Key)")
        
        if not webhook_url:
            print("   ❌ Установите YOOKASSA_WEBHOOK_URL")
        
        if webhook_url:
            try:
                response = requests.post(webhook_url, json={}, timeout=5)
                if response.status_code == 502:
                    print("   ❌ Запустите бот на сервере (webhook возвращает 502)")
            except:
                pass
        
        if not bot_token:
            print("   ❌ Установите TELEGRAM_BOT_TOKEN")
        
        if not openai_key:
            print("   ❌ Установите OPENAI_API_KEY (нужен для генерации натальной карты)")
        
        print()
        print("📖 Подробное руководство: PAYMENT_SETUP_GUIDE.md")
    
    print("=" * 80)
    print()
    
    return 0 if all(results) else 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

