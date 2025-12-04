#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для просмотра пользователей в базе данных
Работает с PostgreSQL на Timeweb Cloud и SQLite локально
Запуск: python view_users_timeweb.py
"""

import os
import sys
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

def get_db_connection():
    """Получает соединение с базой данных PostgreSQL из Timeweb Cloud"""
    database_url = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ ОШИБКА: DATABASE_PUBLIC_URL не найден в переменных окружения!")
        print()
        print("💡 Решение:")
        print("   1. Создайте файл .env в текущей директории")
        print("   2. Добавьте строку:")
        print("      DATABASE_PUBLIC_URL=postgresql://пользователь:пароль@хост:порт/имя_базы")
        print()
        print("   Или укажите строку подключения как аргумент:")
        print("   python view_users_timeweb.py 'postgresql://...'")
        sys.exit(1)
    
    try:
        result = urlparse(database_url)
        print(f"📡 Подключение к PostgreSQL: {result.hostname}:{result.port}/{result.path[1:]}")
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        print("✅ Подключение к PostgreSQL установлено")
        return conn, 'postgresql'
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        print()
        print("💡 Проверьте:")
        print("   1. Правильность строки подключения DATABASE_PUBLIC_URL")
        print("   2. Что база данных запущена в Timeweb Cloud")
        print("   3. Что хост, порт, пользователь и пароль правильные")
        sys.exit(1)

def view_all_users():
    """Просмотр всех пользователей в базе данных"""
    print("=" * 80)
    print("👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ В БАЗЕ ДАННЫХ")
    print("=" * 80)
    print()
    
    try:
        conn, db_type = get_db_connection()
        
        if db_type == 'postgresql':
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Получаем всех пользователей
            cursor.execute('''
                SELECT 
                    user_id,
                    first_name,
                    username,
                    birth_date,
                    birth_time,
                    birth_place,
                    city,
                    country,
                    has_paid,
                    updated_at
                FROM users
                ORDER BY updated_at DESC
            ''')
            users = cursor.fetchall()
            
            # Получаем статистику по событиям
            cursor.execute('''
                SELECT 
                    user_id,
                    COUNT(*) as event_count,
                    MAX(timestamp) as last_event
                FROM events
                GROUP BY user_id
            ''')
            event_stats = {row['user_id']: row for row in cursor.fetchall()}
            
            # Получаем статистику по платежам
            cursor.execute('''
                SELECT 
                    user_id,
                    COUNT(*) as payment_count,
                    SUM(amount) as total_amount,
                    MAX(created_at) as last_payment
                FROM payments
                GROUP BY user_id
            ''')
            payment_stats = {row['user_id']: row for row in cursor.fetchall()}
            
        else:
            # SQLite
            cursor = conn.cursor()
            
            # Проверяем, какие колонки есть в таблице users
            cursor.execute("PRAGMA table_info(users)")
            columns_info = cursor.fetchall()
            column_names = [col[1] for col in columns_info]
            
            # Формируем список колонок, которые есть в таблице
            select_columns = ['user_id', 'first_name']
            if 'username' in column_names:
                select_columns.append('username')
            if 'birth_date' in column_names:
                select_columns.append('birth_date')
            if 'birth_time' in column_names:
                select_columns.append('birth_time')
            if 'birth_place' in column_names:
                select_columns.append('birth_place')
            if 'city' in column_names:
                select_columns.append('city')
            if 'country' in column_names:
                select_columns.append('country')
            if 'has_paid' in column_names:
                select_columns.append('has_paid')
            if 'updated_at' in column_names:
                select_columns.append('updated_at')
            
            query = f'''
                SELECT {', '.join(select_columns)}
                FROM users
                ORDER BY updated_at DESC
            '''
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Преобразуем в словари
            users = []
            for row in rows:
                user_dict = {}
                for i, col_name in enumerate(select_columns):
                    user_dict[col_name] = row[i]
                users.append(user_dict)
            
            # Статистика по событиям (если таблица существует)
            event_stats = {}
            try:
                cursor.execute('''
                    SELECT 
                        user_id,
                        COUNT(*) as event_count,
                        MAX(timestamp) as last_event
                    FROM events
                    GROUP BY user_id
                ''')
                for row in cursor.fetchall():
                    event_stats[row[0]] = {
                        'user_id': row[0],
                        'event_count': row[1],
                        'last_event': row[2]
                    }
            except sqlite3.OperationalError:
                print("⚠️  Таблица events не найдена")
            
            # Статистика по платежам (если таблица существует)
            payment_stats = {}
            try:
                cursor.execute('''
                    SELECT 
                        user_id,
                        COUNT(*) as payment_count,
                        SUM(amount) as total_amount,
                        MAX(created_at) as last_payment
                    FROM payments
                    GROUP BY user_id
                ''')
                for row in cursor.fetchall():
                    payment_stats[row[0]] = {
                        'user_id': row[0],
                        'payment_count': row[1] if row[1] else 0,
                        'total_amount': row[2] if row[2] else 0,
                        'last_payment': row[3]
                    }
            except sqlite3.OperationalError:
                print("⚠️  Таблица payments не найдена")
        
        print(f"📊 Всего пользователей в базе: {len(users)}")
        print()
        
        if not users:
            print("⚠️  В базе данных пока нет пользователей")
            conn.close()
            return
        
        # Выводим информацию о каждом пользователе
        for i, user in enumerate(users, 1):
            print(f"{'=' * 80}")
            print(f"👤 Пользователь #{i}")
            print(f"{'=' * 80}")
            print(f"🆔 User ID: {user.get('user_id')}")
            print(f"📛 Имя: {user.get('first_name') or 'Не указано'}")
            
            username = user.get('username')
            if username:
                print(f"📱 Username: @{username}")
            else:
                print(f"📱 Username: Не указан")
            
            print(f"📅 Дата рождения: {user.get('birth_date') or 'Не указана'}")
            print(f"🕐 Время рождения: {user.get('birth_time') or 'Не указано'}")
            print(f"📍 Место рождения: {user.get('birth_place') or user.get('city') or 'Не указано'}")
            
            if user.get('city'):
                print(f"🏙️  Город: {user.get('city')}")
            if user.get('country'):
                print(f"🌍 Страна: {user.get('country')}")
            
            has_paid = user.get('has_paid', 0)
            if has_paid:
                print(f"💰 Оплата: ✅ Оплачено")
            else:
                print(f"💰 Оплата: ❌ Не оплачено")
            
            updated_at = user.get('updated_at')
            if updated_at:
                print(f"🕒 Последнее обновление: {updated_at}")
            
            # Статистика по событиям
            user_id = user.get('user_id')
            if user_id in event_stats:
                stats = event_stats[user_id]
                print(f"📊 Событий: {stats['event_count']}")
                if stats.get('last_event'):
                    print(f"   Последнее событие: {stats['last_event']}")
            
            # Статистика по платежам
            if user_id in payment_stats:
                stats = payment_stats[user_id]
                print(f"💳 Платежей: {stats['payment_count']}")
                if stats.get('total_amount'):
                    print(f"   Сумма: {stats['total_amount']} ₽")
                if stats.get('last_payment'):
                    print(f"   Последний платеж: {stats['last_payment']}")
            
            print()
        
        # Общая статистика
        print("=" * 80)
        print("📈 ОБЩАЯ СТАТИСТИКА")
        print("=" * 80)
        
        paid_count = sum(1 for u in users if u.get('has_paid'))
        profile_complete = sum(1 for u in users if u.get('birth_date') and u.get('birth_time') and u.get('birth_place'))
        
        print(f"👥 Всего пользователей: {len(users)}")
        print(f"💰 Оплатили: {paid_count}")
        print(f"📋 Заполнили профиль: {profile_complete}")
        print(f"📊 Всего событий: {sum(s['event_count'] for s in event_stats.values())}")
        print(f"💳 Всего платежей: {sum(s['payment_count'] for s in payment_stats.values())}")
        print()
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка при получении данных: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    # Если передан аргумент - используем его как DATABASE_PUBLIC_URL
    if len(sys.argv) > 1:
        os.environ['DATABASE_PUBLIC_URL'] = sys.argv[1]
        print(f"📝 Используется строка подключения из аргумента")
        print()
    
    view_all_users()

