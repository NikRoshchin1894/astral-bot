#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для запуска генерации натальной карты после исправления статуса оплаты
Использует Telegram Bot API для отправки сообщения пользователю
"""

import os
import sys
import asyncio
from dotenv import load_dotenv
from telegram import Bot
from telegram.ext import Application, ContextTypes

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN не установлен")
    sys.exit(1)


async def trigger_generation_for_user(user_id: int):
    """Запускает генерацию натальной карты для пользователя"""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    try:
        # Отправляем сообщение пользователю с кнопкой для запуска генерации
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        message = (
            "✅ *Оплата обработана!*\n\n"
            "Ваш платеж был успешно обработан. "
            "Теперь вы можете получить вашу натальную карту.\n\n"
            "Нажмите кнопку ниже, чтобы начать генерацию:"
        )
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📜 Получить натальную карту", callback_data='natal_chart'),
            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
        ]])
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        print(f"✅ Сообщение отправлено пользователю {user_id}")
        print(f"   Пользователь может нажать кнопку для запуска генерации")
        
    except Exception as e:
        print(f"❌ Ошибка при отправке сообщения: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python trigger_natal_chart_generation.py <user_id>")
        print("  python trigger_natal_chart_generation.py <username>")
        print("\nПримеры:")
        print("  python trigger_natal_chart_generation.py 724281972")
        print("  python trigger_natal_chart_generation.py NikitaRoshchin")
        sys.exit(1)
    
    user_input = sys.argv[1]
    
    # Определяем, это user_id или username
    try:
        user_id = int(user_input)
    except ValueError:
        # Это username, нужно найти user_id
        from urllib.parse import urlparse
        import psycopg2
        
        DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            print("❌ DATABASE_URL не установлен")
            sys.exit(1)
        
        result = urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        cursor = conn.cursor()
        
        username = user_input.lstrip('@')
        cursor.execute('SELECT user_id FROM users WHERE username = %s OR username = %s', 
                     (username, f'@{username}'))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            print(f"❌ Пользователь '{user_input}' не найден")
            sys.exit(1)
        
        user_id = result[0]
    
    try:
        asyncio.run(trigger_generation_for_user(user_id))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

