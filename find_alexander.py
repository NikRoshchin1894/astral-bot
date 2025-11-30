#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Поиск пользователя Александр и диагностика проблемы"""
import os
import sys
from dotenv import load_dotenv
import sqlite3

load_dotenv()
DATABASE = 'users.db'

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

print("🔍 Поиск пользователя Александр\n")
print("=" * 80)

# Проверяем структуру таблицы
cursor.execute("PRAGMA table_info(users)")
columns = [row[1] for row in cursor.fetchall()]
has_birth_place = 'birth_place' in columns

if has_birth_place:
    select_fields = "user_id, first_name, birth_date, birth_time, birth_place"
else:
    select_fields = "user_id, first_name, birth_date, birth_time, city, country"

# Ищем по имени
cursor.execute(f"SELECT {select_fields} FROM users WHERE first_name LIKE ?", ('%Александр%',))
users = cursor.fetchall()

if not users:
    print("❌ Пользователь с именем 'Александр' не найден")
    # Попробуем найти по дате 12.04.2025
    cursor.execute(f"SELECT {select_fields} FROM users WHERE birth_date LIKE ?", ('%12.04.2025%',))
    users = cursor.fetchall()
    if not users:
        # Попробуем найти по дате 12.04
        cursor.execute(f"SELECT {select_fields} FROM users WHERE birth_date LIKE ?", ('%12.04%',))
        users = cursor.fetchall()
        if not users:
            print("❌ Пользователь с датой рождения 12.04 также не найден")
        else:
            print(f"✅ Найдено {len(users)} пользователей с датой рождения 12.04:")
    else:
        print(f"✅ Найдено {len(users)} пользователей с датой 12.04.2025:")
else:
    print(f"✅ Найдено {len(users)} пользователей с именем 'Александр':")

for row in users:
    user_id = row[0]
    first_name = row[1]
    birth_date = row[2]
    birth_time = row[3]
    
    if has_birth_place:
        birth_place = row[4]
    else:
        city = row[4] if len(row) > 4 else None
        country = row[5] if len(row) > 5 else None
        if city and country:
            birth_place = f"{city}, {country}"
        elif city:
            birth_place = city
        elif country:
            birth_place = country
        else:
            birth_place = None
    print(f"\n👤 User ID: {user_id}")
    print(f"   Имя: {first_name}")
    print(f"   Дата рождения: {birth_date}")
    print(f"   Время рождения: {birth_time}")
    print(f"   Место рождения: {birth_place}")
    
    # Проверяем полноту профиля (для старой схемы без birth_place учитываем city/country)
    if has_birth_place:
        has_all = all([first_name, birth_date, birth_time, birth_place])
    else:
        has_all = all([first_name, birth_date, birth_time, (city or country)])
    print(f"   Профиль: {'✅ Полный' if has_all else '❌ Неполный'}")
    
    if not has_all:
        missing = []
        if not first_name: missing.append("Имя")
        if not birth_date: missing.append("Дата")
        if not birth_time: missing.append("Время")
        if not birth_place: missing.append("Место")
        print(f"   ⚠️ Отсутствуют: {', '.join(missing)}")
    
    # Проверяем события генерации
    print(f"\n   📊 СОБЫТИЯ ГЕНЕРАЦИИ:")
    cursor.execute("""
        SELECT event_type, event_data, timestamp 
        FROM events 
        WHERE user_id = ? 
        AND event_type IN ('natal_chart_generation_start', 'natal_chart_success', 'natal_chart_error', 'natal_chart_request_no_profile')
        ORDER BY timestamp DESC
        LIMIT 10
    """, (user_id,))
    
    events = cursor.fetchall()
    
    if not events:
        print("      ⚠️ События генерации не найдены")
    else:
        for event_type, event_data, timestamp in events:
            icon = "✅" if event_type == "natal_chart_success" else "❌" if event_type == "natal_chart_error" else "⏳" if event_type == "natal_chart_generation_start" else "⚠️"
            print(f"      {icon} {event_type} - {timestamp}")
            if event_data and len(event_data) > 0:
                print(f"         Данные: {event_data[:200]}...")
    
    # Проверяем последние ошибки
    print(f"\n   ❌ ПОСЛЕДНИЕ ОШИБКИ:")
    cursor.execute("""
        SELECT event_data, timestamp 
        FROM events 
        WHERE user_id = ? AND event_type = 'natal_chart_error'
        ORDER BY timestamp DESC
        LIMIT 3
    """, (user_id,))
    
    errors = cursor.fetchall()
    
    if not errors:
        print("      ✅ Ошибок не найдено")
    else:
        for i, (event_data, timestamp) in enumerate(errors, 1):
            print(f"      Ошибка #{i} ({timestamp}):")
            print(f"         {event_data}")
    
    # Проверяем незавершенные генерации
    print(f"\n   ⏳ НЕЗАВЕРШЕННЫЕ ГЕНЕРАЦИИ:")
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
    
    stuck = cursor.fetchall()
    
    if not stuck:
        print("      ✅ Незавершенных генераций нет")
    else:
        print(f"      ⚠️ Найдено {len(stuck)} незавершенных генераций:")
        for timestamp, event_data in stuck:
            print(f"         Начата: {timestamp}")
            if event_data:
                print(f"         Данные: {event_data[:200]}...")

conn.close()
print("\n" + "=" * 80)

