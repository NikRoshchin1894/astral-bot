#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для просмотра данных и логов конкретного пользователя
"""

import sqlite3
import json
import sys
import os
from datetime import datetime
from urllib.parse import urlparse
import psycopg2
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# База данных
# Railway предоставляет два URL:
# - DATABASE_URL - для внутренних подключений (postgres.railway.internal)
# - DATABASE_PUBLIC_URL - для внешних подключений (с вашего компьютера)
DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
DATABASE = 'users.db'

def get_db_connection():
    """Получает соединение с базой данных (PostgreSQL или SQLite)"""
    if DATABASE_URL:
        try:
            result = urlparse(DATABASE_URL)
            print(f"🔌 Подключение к PostgreSQL: {result.hostname}:{result.port}/{result.path[1:]}")
            conn = psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port,
                connect_timeout=10
            )
            print("✅ Подключение к PostgreSQL установлено")
            return conn, 'postgresql'
        except Exception as e:
            print(f"❌ Ошибка подключения к PostgreSQL: {e}")
            print("💡 Подсказка: Убедитесь, что DATABASE_PUBLIC_URL установлен в .env")
            print("   Railway предоставляет DATABASE_PUBLIC_URL для внешних подключений")
            print("   Используем локальный SQLite...")
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        print("⚠️ DATABASE_URL не установлена, используем локальный SQLite")
        return sqlite3.connect(DATABASE), 'sqlite'


def get_user_data(user_id, db_type, cursor):
    """Получает данные пользователя"""
    if db_type == 'postgresql':
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
    else:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    
    row = cursor.fetchone()
    if not row:
        return None
    
    if db_type == 'postgresql':
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    else:
        columns = ['user_id', 'first_name', 'last_name', 'country', 'city', 
                   'birth_date', 'birth_time', 'updated_at', 'has_paid', 'birth_place']
        return dict(zip(columns, row))


def get_user_events(user_id, db_type, cursor):
    """Получает все события пользователя"""
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT id, event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = %s 
            ORDER BY timestamp DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT id, event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = ? 
            ORDER BY timestamp DESC
        ''', (user_id,))
    
    return cursor.fetchall()


def get_event_stats(user_id, db_type, cursor):
    """Получает статистику по событиям пользователя"""
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT event_type, COUNT(*) as count 
            FROM events 
            WHERE user_id = %s 
            GROUP BY event_type 
            ORDER BY count DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT event_type, COUNT(*) as count 
            FROM events 
            WHERE user_id = ? 
            GROUP BY event_type 
            ORDER BY count DESC
        ''', (user_id,))
    
    return cursor.fetchall()


def format_event_data(event_data_str):
    """Форматирует JSON данные события"""
    if not event_data_str:
        return "Нет данных"
    try:
        data = json.loads(event_data_str)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except:
        return event_data_str


def view_user(user_id):
    """Просмотр данных и логов пользователя"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    print(f"\n{'='*60}")
    print(f"📊 ДАННЫЕ ПОЛЬЗОВАТЕЛЯ: {user_id}")
    print(f"{'='*60}\n")
    
    # Получаем данные пользователя
    user_data = get_user_data(user_id, db_type, cursor)
    
    if not user_data:
        print(f"❌ Пользователь {user_id} не найден в базе данных")
        conn.close()
        return
    
    # Выводим данные пользователя
    print("👤 ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:")
    print("-" * 60)
    print(f"  ID: {user_data.get('user_id', 'N/A')}")
    print(f"  Имя: {user_data.get('first_name', 'Не указано')}")
    print(f"  Фамилия: {user_data.get('last_name', 'Не указано')}")
    print(f"  Страна: {user_data.get('country', 'Не указано')}")
    print(f"  Город: {user_data.get('city', 'Не указано')}")
    print(f"  Место рождения: {user_data.get('birth_place', user_data.get('city', 'Не указано'))}")
    print(f"  Дата рождения: {user_data.get('birth_date', 'Не указано')}")
    print(f"  Время рождения: {user_data.get('birth_time', 'Не указано')}")
    print(f"  Оплачено: {'✅ Да' if user_data.get('has_paid') else '❌ Нет'}")
    print(f"  Обновлено: {user_data.get('updated_at', 'N/A')}")
    print()
    
    # Получаем статистику событий
    event_stats = get_event_stats(user_id, db_type, cursor)
    
    print("📈 СТАТИСТИКА СОБЫТИЙ:")
    print("-" * 60)
    if event_stats:
        for event_type, count in event_stats:
            print(f"  {event_type}: {count}")
    else:
        print("  Нет событий")
    print()
    
    # Получаем все события
    events = get_user_events(user_id, db_type, cursor)
    
    print(f"📋 ВСЕ СОБЫТИЯ ({len(events)}):")
    print("-" * 60)
    
    if events:
        for i, (event_id, event_type, event_data, timestamp) in enumerate(events, 1):
            print(f"\n{i}. {event_type}")
            print(f"   Время: {timestamp}")
            if event_data:
                print(f"   Данные:")
                formatted_data = format_event_data(event_data)
                for line in formatted_data.split('\n'):
                    print(f"     {line}")
    else:
        print("  Нет событий")
    
    print(f"\n{'='*60}\n")
    
    conn.close()


def list_users():
    """Список всех пользователей"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT user_id, first_name, birth_date, has_paid, updated_at 
            FROM users 
            ORDER BY updated_at DESC 
            LIMIT 50
        ''')
    else:
        cursor.execute('''
            SELECT user_id, first_name, birth_date, has_paid, updated_at 
            FROM users 
            ORDER BY updated_at DESC 
            LIMIT 50
        ''')
    
    users = cursor.fetchall()
    
    print(f"\n{'='*60}")
    print(f"👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ (последние 50):")
    print(f"{'='*60}\n")
    
    if users:
        print(f"{'ID':<12} {'Имя':<20} {'Дата рождения':<15} {'Оплата':<8} {'Обновлено':<20}")
        print("-" * 80)
        for user_id, first_name, birth_date, has_paid, updated_at in users:
            paid = "✅" if has_paid else "❌"
            name = first_name or "N/A"
            date = birth_date or "N/A"
            updated = updated_at or "N/A"
            print(f"{user_id:<12} {name:<20} {date:<15} {paid:<8} {updated:<20}")
    else:
        print("  Нет пользователей")
    
    print(f"\n{'='*60}\n")
    
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python view_user_data.py <user_id>  - просмотр данных пользователя")
        print("  python view_user_data.py --list     - список всех пользователей")
        print("\nПример:")
        print("  python view_user_data.py 123456789")
        sys.exit(1)
    
    if sys.argv[1] == '--list':
        list_users()
    else:
        try:
            user_id = int(sys.argv[1])
            view_user(user_id)
        except ValueError:
            print(f"❌ Ошибка: {sys.argv[1]} не является числом")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            sys.exit(1)

