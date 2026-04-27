#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка всех пользователей с проблемами генерации"""
import os
import sys
from dotenv import load_dotenv
import sqlite3

load_dotenv()
DATABASE = 'users.db'

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

print("🔍 Поиск пользователей с проблемами генерации натальной карты\n")
print("=" * 80)

# Находим пользователей с незавершенными генерациями
cursor.execute("""
    SELECT DISTINCT e1.user_id, 
           COUNT(*) as stuck_count,
           MAX(e1.timestamp) as last_start
    FROM events e1
    WHERE e1.event_type = 'natal_chart_generation_start'
    AND NOT EXISTS (
        SELECT 1 
        FROM events e2 
        WHERE e2.user_id = e1.user_id 
        AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
        AND e2.timestamp > e1.timestamp
    )
    GROUP BY e1.user_id
    ORDER BY last_start DESC
    LIMIT 20
""")

stuck_users = cursor.fetchall()

if stuck_users:
    print(f"⚠️ Найдено {len(stuck_users)} пользователей с незавершенными генерациями:\n")
    for user_id, stuck_count, last_start in stuck_users:
        # Получаем профиль
        cursor.execute("SELECT first_name, birth_date, birth_time, birth_place FROM users WHERE user_id = ?", (user_id,))
        profile = cursor.fetchone()
        
        # Получаем последнюю ошибку
        cursor.execute("""
            SELECT event_data, timestamp 
            FROM events 
            WHERE user_id = ? AND event_type = 'natal_chart_error'
            ORDER BY timestamp DESC 
            LIMIT 1
        """, (user_id,))
        error = cursor.fetchone()
        
        print(f"User ID: {user_id}")
        if profile:
            name, date, time, place = profile
            print(f"  Имя: {name or 'Не указано'}")
            print(f"  Дата: {date or 'Не указано'}")
            print(f"  Время: {time or 'Не указано'}")
            print(f"  Место: {place or 'Не указано'}")
            has_all = all([name, date, time, place])
            print(f"  Профиль: {'✅ Полный' if has_all else '❌ Неполный'}")
        print(f"  Незавершенных генераций: {stuck_count}")
        print(f"  Последний старт: {last_start}")
        if error:
            print(f"  Последняя ошибка: {error[0]}")
        print()
else:
    print("✅ Пользователей с незавершенными генерациями не найдено\n")

# Находим пользователей с ошибками
print("=" * 80)
print("❌ ПОЛЬЗОВАТЕЛИ С ОШИБКАМИ:\n")

cursor.execute("""
    SELECT DISTINCT user_id, 
           COUNT(*) as error_count,
           MAX(timestamp) as last_error
    FROM events
    WHERE event_type = 'natal_chart_error'
    GROUP BY user_id
    ORDER BY last_error DESC
    LIMIT 20
""")

error_users = cursor.fetchall()

if error_users:
    for user_id, error_count, last_error in error_users:
        print(f"User ID: {user_id}, Ошибок: {error_count}, Последняя: {last_error}")
        
        # Получаем последнюю ошибку
        cursor.execute("""
            SELECT event_data 
            FROM events 
            WHERE user_id = ? AND event_type = 'natal_chart_error'
            ORDER BY timestamp DESC 
            LIMIT 1
        """, (user_id,))
        error_data = cursor.fetchone()
        if error_data:
            print(f"  Детали: {error_data[0]}")
        print()
else:
    print("✅ Пользователей с ошибками не найдено\n")

conn.close()






