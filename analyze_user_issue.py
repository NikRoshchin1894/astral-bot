#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для анализа проблем с генерацией натальной карты для конкретного пользователя
"""
import os
import sys
from dotenv import load_dotenv
import psycopg2
import sqlite3
from urllib.parse import urlparse

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
DATABASE = 'users.db'

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
                port=result.port
            )
            return conn, 'postgresql'
        except Exception as e:
            print(f"Ошибка подключения к PostgreSQL: {e}, используем SQLite")
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        return sqlite3.connect(DATABASE), 'sqlite'

def analyze_user(username):
    """Анализирует проблемы для пользователя по username"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    print(f"🔍 Анализ пользователя: @{username}\n")
    print("=" * 60)
    
    # 1. Находим user_id по username
    # Сначала проверяем, есть ли колонка username
    if db_type == 'postgresql':
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='username'
        """)
        has_username_col = cursor.fetchone() is not None
    else:
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        has_username_col = 'username' in columns
    
    if has_username_col:
        if db_type == 'postgresql':
            cursor.execute("SELECT user_id, first_name, username FROM users WHERE username = %s", (username,))
        else:
            cursor.execute("SELECT user_id, first_name, username FROM users WHERE username = ?", (username,))
        
            user_row = cursor.fetchone()
            
            if not user_row:
                print(f"❌ Пользователь @{username} не найден в базе данных по username")
                conn.close()
                return
            else:
                user_id = user_row[0]
                first_name = user_row[1] if len(user_row) > 1 else None
                stored_username = user_row[2] if len(user_row) > 2 else None
                print(f"✅ Найден пользователь:")
                print(f"   User ID: {user_id}")
                if first_name:
                    print(f"   Имя: {first_name}")
                if stored_username:
                    print(f"   Username: @{stored_username}\n")
                else:
                    print(f"   Username: не указан\n")
    else:
        print(f"⚠️ Колонка username отсутствует в таблице users")
        print(f"   Введите user_id вручную или проверьте события для всех пользователей")
        conn.close()
        return
    
    print(f"✅ Найден пользователь:")
    print(f"   User ID: {user_id}")
    print(f"   Имя: {first_name}")
    print(f"   Username: @{stored_username}\n")
    
    # 2. Проверяем профиль пользователя
    print("=" * 60)
    print("📋 ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:")
    print("=" * 60)
    
    if db_type == 'postgresql':
        cursor.execute("SELECT first_name, birth_date, birth_time, birth_place, country, city FROM users WHERE user_id = %s", (user_id,))
    else:
        cursor.execute("SELECT first_name, birth_date, birth_time, birth_place FROM users WHERE user_id = ?", (user_id,))
    
    profile = cursor.fetchone()
    
    if db_type == 'postgresql':
        birth_name, birth_date, birth_time, birth_place, country, city = profile if profile else (None, None, None, None, None, None)
    else:
        birth_name, birth_date, birth_time, birth_place = profile if profile else (None, None, None, None)
        country, city = None, None
    
    print(f"   Имя: {birth_name or 'Не указано'}")
    print(f"   Дата рождения: {birth_date or 'Не указано'}")
    print(f"   Время рождения: {birth_time or 'Не указано'}")
    print(f"   Место рождения: {birth_place or 'Не указано'}")
    if country:
        print(f"   Страна: {country}")
    if city:
        print(f"   Город: {city}")
    
    # Проверяем полноту профиля
    has_profile = all([birth_name, birth_date, birth_time, birth_place])
    print(f"\n   ✅ Профиль {'полностью заполнен' if has_profile else 'НЕ полностью заполнен'}")
    if not has_profile:
        missing = []
        if not birth_name: missing.append("Имя")
        if not birth_date: missing.append("Дата рождения")
        if not birth_time: missing.append("Время рождения")
        if not birth_place: missing.append("Место рождения")
        print(f"   ⚠️ Отсутствуют: {', '.join(missing)}")
    
    # 3. Проверяем события генерации натальной карты
    print("\n" + "=" * 60)
    print("🔄 СОБЫТИЯ ГЕНЕРАЦИИ НАТАЛЬНОЙ КАРТЫ:")
    print("=" * 60)
    
    if db_type == 'postgresql':
        cursor.execute("""
            SELECT event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = %s 
            AND event_type IN ('natal_chart_generation_start', 'natal_chart_success', 'natal_chart_error', 'natal_chart_request_no_profile')
            ORDER BY timestamp DESC
            LIMIT 20
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = ? 
            AND event_type IN ('natal_chart_generation_start', 'natal_chart_success', 'natal_chart_error', 'natal_chart_request_no_profile')
            ORDER BY timestamp DESC
            LIMIT 20
        """, (user_id,))
    
    events = cursor.fetchall()
    
    if not events:
        print("   ⚠️ События генерации натальной карты не найдены")
    else:
        for event_type, event_data, timestamp in events:
            status_icon = "✅" if event_type == "natal_chart_success" else "❌" if event_type == "natal_chart_error" else "⏳" if event_type == "natal_chart_generation_start" else "⚠️"
            print(f"\n   {status_icon} {event_type}")
            print(f"      Время: {timestamp}")
            if event_data:
                print(f"      Данные: {event_data}")
    
    # 4. Проверяем последние ошибки
    print("\n" + "=" * 60)
    print("❌ ПОСЛЕДНИЕ ОШИБКИ:")
    print("=" * 60)
    
    if db_type == 'postgresql':
        cursor.execute("""
            SELECT event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = %s 
            AND event_type = 'natal_chart_error'
            ORDER BY timestamp DESC
            LIMIT 5
        """, (user_id,))
    else:
        cursor.execute("""
            SELECT event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = ? 
            AND event_type = 'natal_chart_error'
            ORDER BY timestamp DESC
            LIMIT 5
        """, (user_id,))
    
    errors = cursor.fetchall()
    
    if not errors:
        print("   ✅ Ошибок генерации не найдено")
    else:
        for i, (event_type, event_data, timestamp) in enumerate(errors, 1):
            print(f"\n   Ошибка #{i}:")
            print(f"      Время: {timestamp}")
            print(f"      Данные: {event_data}")
    
    # 5. Проверяем незавершенные генерации
    print("\n" + "=" * 60)
    print("⏳ НЕЗАВЕРШЕННЫЕ ГЕНЕРАЦИИ:")
    print("=" * 60)
    
    if db_type == 'postgresql':
        cursor.execute("""
            SELECT e1.timestamp, e1.event_data
            FROM events e1
            WHERE e1.user_id = %s 
            AND e1.event_type = 'natal_chart_generation_start'
            AND NOT EXISTS (
                SELECT 1 
                FROM events e2 
                WHERE e2.user_id = %s 
                AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                AND e2.timestamp > e1.timestamp
            )
            ORDER BY e1.timestamp DESC
        """, (user_id, user_id))
    else:
        cursor.execute("""
            SELECT e1.timestamp, e1.event_data
            FROM events e1
            WHERE e1.user_id = ? 
            AND e1.event_type = 'natal_chart_generation_start'
            AND NOT EXISTS (
                SELECT 1 
                FROM events e2 
                WHERE e2.user_id = ? 
                AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                AND e2.timestamp > e1.timestamp
            )
            ORDER BY e1.timestamp DESC
        """, (user_id, user_id))
    
    stuck_generations = cursor.fetchall()
    
    if not stuck_generations:
        print("   ✅ Незавершенных генераций не найдено")
    else:
        print(f"   ⚠️ Найдено {len(stuck_generations)} незавершенных генераций:")
        for timestamp, event_data in stuck_generations:
            print(f"      Начата: {timestamp}")
            if event_data:
                print(f"      Данные: {event_data}")
    
    # 6. Вывод рекомендаций
    print("\n" + "=" * 60)
    print("💡 РЕКОМЕНДАЦИИ:")
    print("=" * 60)
    
    if not has_profile:
        print("   1. ❌ Пользователь не заполнил профиль полностью")
        print("      → Нужно заполнить все поля: имя, дата, время, место рождения")
    
    if errors:
        print(f"   2. ❌ Обнаружено {len(errors)} ошибок генерации")
        print("      → Проверьте детали ошибок выше")
    
    if stuck_generations:
        print(f"   3. ⏳ Обнаружено {len(stuck_generations)} незавершенных генераций")
        print("      → Возможно, генерация зависла или была прервана")
    
    if has_profile and not errors and not stuck_generations:
        print("   ✅ Все данные в порядке, проблема может быть в другом месте")
        print("      → Проверьте логи бота для детальной информации")
    
    conn.close()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    username = "SberSBI"  # Без @
    if len(sys.argv) > 1:
        username = sys.argv[1].replace("@", "")
    analyze_user(username)

