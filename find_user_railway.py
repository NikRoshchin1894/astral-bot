#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Поиск пользователя Александр в базе данных Railway (PostgreSQL)"""
import os
import sys
import json
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

# Используем DATABASE_PUBLIC_URL (Railway предоставляет публичный URL для базы данных)
DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')

# Проверяем аргументы: если первый аргумент - это DATABASE_URL (начинается с postgresql://), используем его
# Иначе это username для поиска
username_arg = None
if len(sys.argv) > 1:
    if sys.argv[1].startswith('postgresql://'):
        DATABASE_URL = sys.argv[1]
    else:
        username_arg = sys.argv[1].replace('@', '')

if not DATABASE_URL:
    print("❌ DATABASE_PUBLIC_URL или DATABASE_URL не найдена!")
    print("\nИспользование:")
    print("   python find_user_railway.py")
    print("   или")
    print("   python find_user_railway.py 'postgresql://user:pass@host:port/db'")
    print("\nТакже можно установить DATABASE_PUBLIC_URL в .env файле или как переменную окружения")
    sys.exit(1)

print("🔍 Подключение к базе данных Railway (PostgreSQL)...\n")
print("=" * 80)

try:
    result = urlparse(DATABASE_URL)
    print(f"Подключение к: {result.hostname}:{result.port}/{result.path[1:]}")
    
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    print("✅ Подключение успешно!\n")
    
    # Если передан username через аргумент, ищем по нему
    # Ищем пользователя по username или имени
    if username_arg:
        print(f"🔍 Поиск пользователя по username @{username_arg}...\n")
        cursor.execute("""
            SELECT user_id, first_name, birth_date, birth_time, birth_place, 
                   country, city, username, updated_at
            FROM users 
            WHERE username = %s
            ORDER BY updated_at DESC
            LIMIT 10
        """, (username_arg,))
    else:
        print("🔍 Поиск пользователя 'Александр'...\n")
        cursor.execute("""
            SELECT user_id, first_name, birth_date, birth_time, birth_place, 
                   country, city, username, updated_at
            FROM users 
            WHERE first_name ILIKE %s
            ORDER BY updated_at DESC
            LIMIT 10
        """, ('%Александр%',))
    
    users = cursor.fetchall()
    
    if not users:
        print("❌ Пользователь с именем 'Александр' не найден")
        # Ищем по дате рождения 12.04.2025
        print("\n🔍 Поиск по дате рождения 12.04.2025...\n")
        cursor.execute("""
            SELECT user_id, first_name, birth_date, birth_time, birth_place, 
                   country, city, username, updated_at
            FROM users 
            WHERE birth_date LIKE %s
            ORDER BY updated_at DESC
            LIMIT 10
        """, ('%12.04.2025%',))
        users = cursor.fetchall()
        
        if not users:
            # Пробуем без года
            print("🔍 Поиск по дате рождения 12.04...\n")
            cursor.execute("""
                SELECT user_id, first_name, birth_date, birth_time, birth_place, 
                       country, city, username, updated_at
                FROM users 
                WHERE birth_date LIKE %s
                ORDER BY updated_at DESC
                LIMIT 10
            """, ('%12.04%',))
            users = cursor.fetchall()
    
    if not users:
        print("❌ Пользователь не найден ни по имени, ни по дате")
        print("\n📋 Последние 10 пользователей в базе:\n")
        cursor.execute("""
            SELECT user_id, first_name, birth_date, birth_time, birth_place, 
                   country, city, username, updated_at
            FROM users 
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        recent_users = cursor.fetchall()
        for user in recent_users:
            print(f"   User ID: {user['user_id']}, Имя: {user['first_name']}, Дата: {user['birth_date']}, Username: {user['username']}")
    else:
        print(f"✅ Найдено {len(users)} пользователей:\n")
        
        for user in users:
            user_id = user['user_id']
            print(f"{'='*80}")
            print(f"👤 ПОЛЬЗОВАТЕЛЬ ID: {user_id}")
            print(f"{'='*80}")
            print(f"   Имя: {user['first_name']}")
            print(f"   Дата рождения: {user['birth_date']}")
            print(f"   Время рождения: {user['birth_time']}")
            print(f"   Место рождения: {user['birth_place']}")
            if user['city']:
                print(f"   Город: {user['city']}")
            if user['country']:
                print(f"   Страна: {user['country']}")
            if user['username']:
                print(f"   Username: @{user['username']}")
            print(f"   Обновлено: {user['updated_at']}")
            
            # Проверяем полноту профиля
            has_all = all([user['first_name'], user['birth_date'], user['birth_time'], user['birth_place']])
            print(f"\n   📋 Профиль: {'✅ ПОЛНЫЙ' if has_all else '❌ НЕПОЛНЫЙ'}")
            
            if not has_all:
                missing = []
                if not user['first_name']: missing.append("Имя")
                if not user['birth_date']: missing.append("Дата")
                if not user['birth_time']: missing.append("Время")
                if not user['birth_place']: missing.append("Место")
                print(f"   ⚠️ Отсутствуют: {', '.join(missing)}")
            
            # Проверяем события генерации
            print(f"\n   📊 СОБЫТИЯ ГЕНЕРАЦИИ НАТАЛЬНОЙ КАРТЫ:")
            cursor.execute("""
                SELECT event_type, event_data, timestamp 
                FROM events 
                WHERE user_id = %s 
                AND event_type IN ('natal_chart_generation_start', 'natal_chart_success', 
                                   'natal_chart_error', 'natal_chart_request_no_profile')
                ORDER BY timestamp DESC
                LIMIT 20
            """, (user_id,))
            
            events = cursor.fetchall()
            
            if not events:
                print("      ⚠️ События генерации не найдены")
            else:
                for event in events:
                    event_type = event['event_type']
                    icon = "✅" if event_type == "natal_chart_success" else \
                           "❌" if event_type == "natal_chart_error" else \
                           "⏳" if event_type == "natal_chart_generation_start" else "⚠️"
                    print(f"      {icon} {event_type}")
                    print(f"         Время: {event['timestamp']}")
                    if event['event_data']:
                        try:
                            event_data = json.loads(event['event_data']) if isinstance(event['event_data'], str) else event['event_data']
                            if isinstance(event_data, dict):
                                for key, value in event_data.items():
                                    if key in ['error_type', 'error_message', 'stage']:
                                        print(f"         {key}: {value}")
                            else:
                                print(f"         Данные: {str(event_data)[:200]}")
                        except:
                            print(f"         Данные: {str(event['event_data'])[:200]}")
                    print()
            
            # Проверяем последние ошибки подробно
            print(f"   ❌ ПОСЛЕДНИЕ ОШИБКИ:")
            cursor.execute("""
                SELECT event_data, timestamp 
                FROM events 
                WHERE user_id = %s AND event_type = 'natal_chart_error'
                ORDER BY timestamp DESC
                LIMIT 5
            """, (user_id,))
            
            errors = cursor.fetchall()
            
            if not errors:
                print("      ✅ Ошибок генерации не найдено")
            else:
                for i, error in enumerate(errors, 1):
                    print(f"\n      Ошибка #{i} ({error['timestamp']}):")
                    if error['event_data']:
                        try:
                            error_data = json.loads(error['event_data']) if isinstance(error['event_data'], str) else error['event_data']
                            if isinstance(error_data, dict):
                                for key, value in error_data.items():
                                    print(f"         {key}: {value}")
                            else:
                                print(f"         {str(error_data)[:300]}")
                        except Exception as e:
                            print(f"         {str(error['event_data'])[:300]}")
            
            # Проверяем незавершенные генерации
            print(f"\n   ⏳ НЕЗАВЕРШЕННЫЕ ГЕНЕРАЦИИ:")
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
            
            stuck = cursor.fetchall()
            
            if not stuck:
                print("      ✅ Незавершенных генераций нет")
            else:
                print(f"      ⚠️ Найдено {len(stuck)} незавершенных генераций:")
                for gen in stuck:
                    print(f"         Начата: {gen['timestamp']}")
                    if gen['event_data']:
                        try:
                            gen_data = json.loads(gen['event_data']) if isinstance(gen['event_data'], str) else gen['event_data']
                            print(f"         Данные: {json.dumps(gen_data, ensure_ascii=False, indent=2)}")
                        except:
                            print(f"         Данные: {str(gen['event_data'])[:200]}")
            
            print()
    
    conn.close()
    print("=" * 80)
    print("\n✅ Анализ завершен")

except psycopg2.Error as e:
    print(f"❌ Ошибка PostgreSQL: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

