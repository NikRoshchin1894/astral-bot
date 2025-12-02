#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка активных (генерирующихся) натальных карт"""
import os
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
    exit(1)

print("🔍 Проверка активных генераций натальных карт\n")
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
    
    now = datetime.now(timezone.utc)
    
    # Находим все активные генерации (начаты, но еще не завершены)
    print("🔍 Поиск активных генераций...\n")
    
    cursor.execute("""
        SELECT 
            e1.user_id, 
            e1.timestamp as start_time,
            e1.event_data as start_data,
            u.first_name,
            u.username
        FROM events e1
        LEFT JOIN users u ON u.user_id = e1.user_id
        WHERE e1.event_type = 'natal_chart_generation_start'
        AND NOT EXISTS (
            SELECT 1 
            FROM events e2 
            WHERE e2.user_id = e1.user_id 
            AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
            AND e2.timestamp > e1.timestamp
        )
        ORDER BY e1.timestamp DESC
    """)
    
    active_generations = cursor.fetchall()
    
    if not active_generations:
        print("✅ Активных генераций не найдено\n")
    else:
        print(f"⚠️ Найдено {len(active_generations)} активных генераций:\n")
        
        for gen in active_generations:
            user_id = gen['user_id']
            start_time_str = str(gen['start_time'])
            
            # Парсим время начала
            try:
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
            except:
                start_time = None
            
            # Вычисляем длительность
            if start_time:
                duration_seconds = (now - start_time).total_seconds()
                duration_minutes = duration_seconds / 60
                duration_hours = duration_minutes / 60
                
                if duration_minutes < 10:
                    status = "✅ В процессе (нормально)"
                    status_icon = "⏳"
                elif duration_minutes < 60:
                    status = "⚠️ Затянулось"
                    status_icon = "⚠️"
                else:
                    status = "❌ Зависло"
                    status_icon = "❌"
            else:
                duration_minutes = None
                status = "❓ Неизвестно"
                status_icon = "❓"
            
            print(f"{status_icon} User ID: {user_id}")
            if gen['username']:
                print(f"   Username: @{gen['username']}")
            if gen['first_name']:
                print(f"   Имя: {gen['first_name']}")
            print(f"   Начато: {start_time_str}")
            if duration_minutes is not None:
                if duration_hours >= 1:
                    print(f"   Длительность: {duration_hours:.1f} часов ({duration_minutes:.1f} минут)")
                else:
                    print(f"   Длительность: {duration_minutes:.1f} минут")
                print(f"   Статус: {status}")
            if gen['start_data']:
                try:
                    start_data = json.loads(gen['start_data']) if isinstance(gen['start_data'], str) else gen['start_data']
                    if isinstance(start_data, dict):
                        if 'birth_date' in start_data:
                            print(f"   Дата рождения: {start_data.get('birth_date', 'N/A')}")
                        if 'birth_time' in start_data:
                            print(f"   Время рождения: {start_data.get('birth_time', 'N/A')}")
                        if 'birth_place' in start_data:
                            print(f"   Место рождения: {start_data.get('birth_place', 'N/A')}")
                except:
                    pass
            print()
        
        # Статистика
        print("=" * 80)
        if start_time:
            normal_count = sum(1 for g in active_generations if g.get('duration_minutes', 999) < 10)
            stuck_count = sum(1 for g in active_generations if g.get('duration_minutes', 0) >= 10)
            print(f"📊 Статистика:")
            print(f"   В процессе (менее 10 минут): {normal_count}")
            print(f"   Зависшие (10+ минут): {stuck_count}")
    
    conn.close()
    print("=" * 80)
    print("\n✅ Проверка завершена")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

