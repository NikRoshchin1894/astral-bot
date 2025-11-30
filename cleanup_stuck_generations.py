#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Очистка зависших генераций натальной карты в базе данных Railway"""
import os
import sys
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta
import json

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_PUBLIC_URL или DATABASE_URL не найдена!")
    sys.exit(1)

print("🔧 Очистка зависших генераций натальной карты\n")
print("=" * 80)

try:
    result = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    print("✅ Подключение к базе данных успешно!\n")
    
    # Находим все незавершенные генерации старше 10 минут
    now = datetime.now(timezone.utc)
    ten_minutes_ago = now - timedelta(minutes=10)
    
    print(f"🔍 Поиск зависших генераций (старше 10 минут, до {ten_minutes_ago.isoformat()})...\n")
    
    cursor.execute("""
        SELECT e1.user_id, e1.timestamp, e1.event_data
        FROM events e1
        WHERE e1.event_type = 'natal_chart_generation_start'
        AND e1.timestamp < %s
        AND NOT EXISTS (
            SELECT 1 
            FROM events e2 
            WHERE e2.user_id = e1.user_id 
            AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
            AND e2.timestamp > e1.timestamp
        )
        ORDER BY e1.timestamp DESC
    """, (ten_minutes_ago.isoformat(),))
    
    stuck_generations = cursor.fetchall()
    
    if not stuck_generations:
        print("✅ Зависших генераций не найдено\n")
    else:
        print(f"⚠️ Найдено {len(stuck_generations)} зависших генераций:\n")
        
        for gen in stuck_generations:
            user_id = gen['user_id']
            # Парсим timestamp (может быть строкой или datetime объектом)
            if isinstance(gen['timestamp'], str):
                start_time_str = gen['timestamp'].replace('Z', '+00:00')
                start_time = datetime.fromisoformat(start_time_str)
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
            else:
                start_time = gen['timestamp']
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
            
            duration_minutes = (now - start_time).total_seconds() / 60
            
            # Получаем имя пользователя
            cursor.execute("SELECT first_name, username FROM users WHERE user_id = %s", (user_id,))
            user_info = cursor.fetchone()
            user_name = user_info['first_name'] if user_info else 'Неизвестно'
            username = user_info['username'] if user_info else None
            
            print(f"   User ID: {user_id}")
            if username:
                print(f"   Username: @{username}")
            print(f"   Имя: {user_name}")
            print(f"   Начата: {gen['timestamp']}")
            print(f"   Длительность: {duration_minutes:.1f} минут")
            
            # Проверяем, есть ли уже ошибка StuckGeneration
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM events
                WHERE user_id = %s
                AND event_type = 'natal_chart_error'
                AND event_data::text LIKE %s
            """, (user_id, '%StuckGeneration%'))
            
            has_stuck_error = cursor.fetchone()['count'] > 0
            
            if not has_stuck_error:
                # Логируем зависшую генерацию как ошибку
                error_data = {
                    'error_type': 'StuckGeneration',
                    'error_message': f'Генерация зависла и не завершилась за {duration_minutes:.1f} минут',
                    'stage': 'generation',
                    'stuck_duration_minutes': duration_minutes,
                    'generation_start': gen['timestamp']
                }
                
                cursor.execute("""
                    INSERT INTO events (user_id, event_type, event_data, timestamp)
                    VALUES (%s, 'natal_chart_error', %s, %s)
                """, (user_id, json.dumps(error_data, ensure_ascii=False), now.isoformat()))
                
                print(f"   ✅ Залогирована ошибка StuckGeneration")
            else:
                print(f"   ℹ️ Ошибка StuckGeneration уже залогирована ранее")
            
            print()
        
        # Подтверждаем изменения
        if not has_stuck_error:
            response = input(f"\n💾 Сохранить изменения в базе данных? (y/n): ")
            if response.lower() == 'y':
                conn.commit()
                print(f"✅ Изменения сохранены! Очищено {len(stuck_generations)} зависших генераций")
            else:
                conn.rollback()
                print("❌ Изменения отменены")
        else:
            print("\nℹ️ Все зависшие генерации уже обработаны")
    
    conn.close()
    print("\n" + "=" * 80)
    print("✅ Анализ завершен")

except psycopg2.Error as e:
    print(f"❌ Ошибка PostgreSQL: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

