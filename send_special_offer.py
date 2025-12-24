#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для отправки специального предложения пользователям с заполненным профилем
Отправляет сообщение о скидке на натальную карту (299 руб вместо 499 руб)
"""

import os
import sys
from urllib.parse import urlparse
import psycopg2
import sqlite3
from dotenv import load_dotenv
from datetime import datetime
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
DATABASE = 'users.db'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

def get_db_connection():
    """Получает соединение с базой данных"""
    if DATABASE_URL:
        try:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port,
                connect_timeout=10
            )
            return conn, 'postgresql'
        except Exception as e:
            print(f"Ошибка подключения к PostgreSQL: {e}")
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        return sqlite3.connect(DATABASE), 'sqlite'

def get_users_with_complete_profile():
    """Получает список пользователей с заполненным профилем"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    # В базе данных имя хранится в поле first_name, но в логике используется как birth_name
    # Проверяем наличие всех необходимых полей для заполненного профиля
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT user_id, first_name, birth_date, birth_time, birth_place, has_paid
            FROM users
            WHERE first_name IS NOT NULL 
              AND first_name != ''
              AND birth_date IS NOT NULL 
              AND birth_date != ''
              AND birth_time IS NOT NULL 
              AND birth_time != ''
              AND birth_place IS NOT NULL 
              AND birth_place != ''
        ''')
    else:
        cursor.execute('''
            SELECT user_id, first_name, birth_date, birth_time, birth_place, has_paid
            FROM users
            WHERE first_name IS NOT NULL 
              AND first_name != ''
              AND birth_date IS NOT NULL 
              AND birth_date != ''
              AND birth_time IS NOT NULL 
              AND birth_time != ''
              AND birth_place IS NOT NULL 
              AND birth_place != ''
        ''')
    
    users = []
    for row in cursor.fetchall():
        user_id, first_name, birth_date, birth_time, birth_place, has_paid = row
        users.append({
            'user_id': user_id,
            'first_name': first_name,
            'birth_name': first_name,  # birth_name в логике = first_name в БД
            'birth_date': birth_date,
            'birth_time': birth_time,
            'birth_place': birth_place,
            'has_paid': has_paid
        })
    
    conn.close()
    return users

def mark_user_has_special_price(user_id, db_type, cursor):
    """Помечает пользователя как имеющего право на специальную цену 299 руб"""
    try:
        if db_type == 'postgresql':
            # Проверяем, есть ли колонка special_price_299
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='special_price_299'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE users ADD COLUMN special_price_299 BOOLEAN DEFAULT FALSE')
            
            cursor.execute('''
                UPDATE users
                SET special_price_299 = TRUE
                WHERE user_id = %s
            ''', (user_id,))
        else:
            # Проверяем, есть ли колонка special_price_299
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'special_price_299' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN special_price_299 INTEGER DEFAULT 0')
            
            cursor.execute('''
                UPDATE users
                SET special_price_299 = 1
                WHERE user_id = ?
            ''', (user_id,))
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении special_price_299 для пользователя {user_id}: {e}")

async def send_special_offer(user_id, bot):
    """Отправляет специальное предложение пользователю"""
    message_text = (
        "🎁 *Специальное предложение только для вас!*\n\n"
        "Только для вас натальная карта доступна за *299 ₽* вместо стандартных 499 ₽\n\n"
        "Не упустите возможность получить детальный астрологический разбор по выгодной цене!"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Оплатить 299 ₽", callback_data='payment_299')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')]
    ])
    
    try:
        await bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        return True
    except TelegramError as e:
        print(f"❌ Ошибка при отправке сообщения пользователю {user_id}: {e}")
        return False

async def main():
    """Основная функция"""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
        return
    
    print("🔌 Подключение к базе данных...")
    users = get_users_with_complete_profile()
    print(f"✅ Найдено {len(users)} пользователей с заполненным профилем")
    
    # Фильтруем только тех, кто еще не оплатил
    users_to_send = [u for u in users if not u.get('has_paid')]
    print(f"📊 Пользователей без оплаты: {len(users_to_send)}")
    
    if len(users_to_send) == 0:
        print("ℹ️ Нет пользователей для отправки сообщений")
        return
    
    # Подтверждение
    print(f"\n⚠️ Будет отправлено сообщений: {len(users_to_send)}")
    response = input("Продолжить? (yes/no): ")
    if response.lower() not in ['yes', 'y', 'да', 'д']:
        print("❌ Отменено пользователем")
        return
    
    # Подключаемся к базе для обновления флагов
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    # Создаем бота
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    success_count = 0
    error_count = 0
    
    print(f"\n📤 Начинаем отправку сообщений...\n")
    
    for i, user in enumerate(users_to_send, 1):
        user_id = user['user_id']
        first_name = user.get('first_name', 'Пользователь')
        
        print(f"[{i}/{len(users_to_send)}] Отправка пользователю {user_id} ({first_name})...", end=' ')
        
        # Отправляем сообщение
        success = await send_special_offer(user_id, bot)
        
        if success:
            # Помечаем пользователя как имеющего право на специальную цену
            mark_user_has_special_price(user_id, db_type, cursor)
            conn.commit()
            print("✅")
            success_count += 1
        else:
            print("❌")
            error_count += 1
        
        # Небольшая задержка, чтобы не перегружать API
        await asyncio.sleep(0.5)
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"📊 ИТОГИ:")
    print(f"✅ Успешно отправлено: {success_count}")
    print(f"❌ Ошибок: {error_count}")
    print(f"{'='*60}")

if __name__ == '__main__':
    asyncio.run(main())

