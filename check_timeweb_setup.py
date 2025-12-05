#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Проверка настройки для Timeweb Cloud
Определяет, нужен ли прокси или можно обойтись без него
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

def check_timeweb_setup():
    """Проверяет настройку для Timeweb Cloud"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА НАСТРОЙКИ ДЛЯ TIMEWEB CLOUD")
    print("=" * 80)
    print()
    
    # Проверяем переменные
    telegram_webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
    yookassa_webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    webhook_port = os.getenv('WEBHOOK_PORT', '8080')
    port_env = os.getenv('PORT', '')
    
    print("📋 Текущие настройки:")
    print(f"   TELEGRAM_WEBHOOK_URL: {'✅ Установлен' if telegram_webhook_url else '❌ Не установлен'}")
    if telegram_webhook_url:
        print(f"      {telegram_webhook_url}")
    print(f"   YOOKASSA_WEBHOOK_URL: {'✅ Установлен' if yookassa_webhook_url else '❌ Не установлен'}")
    if yookassa_webhook_url:
        print(f"      {yookassa_webhook_url}")
    print(f"   WEBHOOK_PORT: {webhook_port}")
    print(f"   PORT (системная): {'✅ ' + port_env if port_env else '❌ Не установлена'}")
    print()
    
    # Анализ
    print("🔍 Анализ:")
    print()
    
    if port_env:
        print("   ✅ Обнаружена переменная PORT")
        print("      Это означает, что платформа может автоматически проксировать запросы")
        print("      💡 Flask должен слушать на этом порту")
    else:
        print("   ⚠️  Переменная PORT не установлена")
        print("      Используется WEBHOOK_PORT или 8080 по умолчанию")
    
    print()
    print("=" * 80)
    print("💡 РЕКОМЕНДАЦИИ:")
    print("=" * 80)
    print()
    
    if telegram_webhook_url or yookassa_webhook_url:
        print("1. Проверьте в панели Timeweb Cloud:")
        print("   - Есть ли раздел 'Домены' или 'Прокси'?")
        print("   - Нужно ли настраивать маршрутизацию вручную?")
        print()
        print("2. Если есть встроенный прокси:")
        print("   - Настройте маршрутизацию:")
        print("     /webhook/telegram → localhost:8080")
        print("     /webhook/yookassa → localhost:8080")
        print()
        print("3. Если прокси не нужен (прямой доступ):")
        print("   - Убедитесь, что порт 8080 открыт для внешних запросов")
        print("   - Проверьте, что домен указывает на контейнер")
        print()
        print("4. Проверьте документацию Timeweb Cloud:")
        print("   - Как работает маршрутизация запросов?")
        print("   - Нужно ли настраивать прокси вручную?")
    else:
        print("⚠️  Webhook URL не установлены")
        print("   Установите TELEGRAM_WEBHOOK_URL для работы через webhook")
    
    print()
    print("=" * 80)


if __name__ == '__main__':
    try:
        check_timeweb_setup()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

