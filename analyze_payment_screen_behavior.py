#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для анализа поведения пользователей после просмотра экрана оплаты
"""

import os
import sys
from urllib.parse import urlparse
import psycopg2
import sqlite3
from dotenv import load_dotenv
from datetime import datetime
import pytz
from collections import defaultdict, Counter
import json

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
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
                port=result.port,
                connect_timeout=10
            )
            return conn, 'postgresql'
        except Exception as e:
            print(f"Ошибка подключения к PostgreSQL: {e}")
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        return sqlite3.connect(DATABASE), 'sqlite'

def analyze_payment_screen_behavior(date_filter):
    """Анализирует поведение пользователей после просмотра экрана оплаты"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    print(f"🔌 Подключение к базе данных...")
    print(f"✅ Подключение к {'PostgreSQL' if db_type == 'postgresql' else 'SQLite'} установлено")
    print(f"📅 Фильтр по дате: {date_filter}\n")
    
    # Формируем условие фильтрации по дате (по московскому времени)
    if db_type == 'postgresql':
        date_condition = """AND (
            (timestamp::timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date = %s::date
        )"""
        date_params = (date_filter,)
    else:
        moscow_tz = pytz.timezone('Europe/Moscow')
        date_start_msk = moscow_tz.localize(datetime.strptime(f"{date_filter} 00:00:00", "%Y-%m-%d %H:%M:%S"))
        date_end_msk = moscow_tz.localize(datetime.strptime(f"{date_filter} 23:59:59.999999", "%Y-%m-%d %H:%M:%S.%f"))
        date_start_utc = date_start_msk.astimezone(pytz.UTC).isoformat()
        date_end_utc = date_end_msk.astimezone(pytz.UTC).isoformat()
        date_condition = "AND timestamp >= ? AND timestamp <= ?"
        date_params = (date_start_utc, date_end_utc)
    
    # Находим всех пользователей, которые увидели экран оплаты за указанную дату
    if db_type == 'postgresql':
        cursor.execute(f'''
            SELECT DISTINCT user_id, timestamp
            FROM events
            WHERE event_type = 'natal_chart_request_no_payment' {date_condition}
            ORDER BY timestamp
        ''', date_params)
    else:
        cursor.execute(f'''
            SELECT DISTINCT user_id, timestamp
            FROM events
            WHERE event_type = 'natal_chart_request_no_payment' {date_condition}
            ORDER BY timestamp
        ''', date_params)
    
    users_with_payment_screen = cursor.fetchall()
    
    print(f"👥 Найдено пользователей, увидевших экран оплаты: {len(users_with_payment_screen)}\n")
    
    if not users_with_payment_screen:
        print("❌ Пользователи не найдены")
        conn.close()
        return
    
    # Для каждого пользователя находим все события после просмотра экрана оплаты
    user_behaviors = []
    all_subsequent_events = Counter()
    users_by_action = defaultdict(list)
    
    for user_id, payment_screen_time in users_with_payment_screen:
        # Получаем все события пользователя после просмотра экрана оплаты
        if db_type == 'postgresql':
            cursor.execute('''
                SELECT event_type, event_data, timestamp
                FROM events
                WHERE user_id = %s AND timestamp > %s
                ORDER BY timestamp
            ''', (user_id, payment_screen_time))
        else:
            cursor.execute('''
                SELECT event_type, event_data, timestamp
                FROM events
                WHERE user_id = ? AND timestamp > ?
                ORDER BY timestamp
            ''', (user_id, payment_screen_time))
        
        subsequent_events = cursor.fetchall()
        
        # Получаем информацию о пользователе
        if db_type == 'postgresql':
            cursor.execute('SELECT username, first_name FROM users WHERE user_id = %s', (user_id,))
        else:
            cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
        user_info = cursor.fetchone()
        username = user_info[0] if user_info and user_info[0] else None
        first_name = user_info[1] if user_info and user_info[1] else None
        
        user_display = f"@{username}" if username else (first_name if first_name else f"ID:{user_id}")
        
        events_list = []
        for event_type, event_data, event_time in subsequent_events:
            events_list.append({
                'type': event_type,
                'data': event_data,
                'time': event_time
            })
            all_subsequent_events[event_type] += 1
            
            # Группируем пользователей по действиям
            if event_type not in ['button_click']:  # Исключаем общие button_click для более детального анализа
                users_by_action[event_type].append(user_display)
        
        user_behaviors.append({
            'user_id': user_id,
            'user_display': user_display,
            'payment_screen_time': payment_screen_time,
            'events': events_list,
            'events_count': len(events_list)
        })
    
    # Выводим статистику
    print("=" * 80)
    print("📊 АНАЛИЗ ПОВЕДЕНИЯ ПОСЛЕ ПРОСМОТРА ЭКРАНА ОПЛАТЫ")
    print("=" * 80)
    print()
    
    # Статистика по действиям
    print("🔵 СТАТИСТИКА ПО ДЕЙСТВИЯМ:")
    print("-" * 80)
    if all_subsequent_events:
        for event_type, count in all_subsequent_events.most_common():
            percentage = (count / len(users_with_payment_screen)) * 100
            print(f"{event_type:50} │ {count:3} раз │ {percentage:5.1f}% пользователей")
    else:
        print("❌ Нет последующих действий")
    print()
    
    # Группировка пользователей по действиям
    print("👥 ПОЛЬЗОВАТЕЛИ ПО ДЕЙСТВИЯМ:")
    print("-" * 80)
    for action, users in sorted(users_by_action.items(), key=lambda x: len(x[1]), reverse=True):
        unique_users = list(set(users))
        print(f"\n{action}:")
        print(f"  Всего пользователей: {len(unique_users)}")
        if len(unique_users) <= 10:
            for user in unique_users:
                print(f"    - {user}")
        else:
            for user in unique_users[:10]:
                print(f"    - {user}")
            print(f"    ... и еще {len(unique_users) - 10} пользователей")
    print()
    
    # Детальная информация по каждому пользователю
    print("=" * 80)
    print("📋 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ ПО ПОЛЬЗОВАТЕЛЯМ:")
    print("=" * 80)
    print()
    
    # Сортируем по количеству событий (сначала тех, у кого больше действий)
    user_behaviors.sort(key=lambda x: x['events_count'], reverse=True)
    
    for i, user_behavior in enumerate(user_behaviors, 1):
        print(f"{i}. {user_behavior['user_display']} (ID: {user_behavior['user_id']})")
        print(f"   Время просмотра экрана оплаты: {user_behavior['payment_screen_time']}")
        print(f"   Количество последующих действий: {user_behavior['events_count']}")
        
        if user_behavior['events']:
            print("   Последующие действия:")
            for event in user_behavior['events'][:10]:  # Показываем первые 10 событий
                event_data_str = ""
                if event['data']:
                    try:
                        data = json.loads(event['data']) if isinstance(event['data'], str) else event['data']
                        if data and isinstance(data, dict):
                            event_data_str = f" ({', '.join([f'{k}:{v}' for k, v in data.items() if k != 'button'])}))"
                    except:
                        pass
                print(f"     - {event['type']}{event_data_str} в {event['time']}")
            if len(user_behavior['events']) > 10:
                print(f"     ... и еще {len(user_behavior['events']) - 10} событий")
        else:
            print("   ❌ Нет последующих действий (пользователь ушел)")
        print()
    
    # Сводка
    print("=" * 80)
    print("📈 СВОДКА:")
    print("=" * 80)
    users_with_actions = sum(1 for ub in user_behaviors if ub['events_count'] > 0)
    users_without_actions = len(user_behaviors) - users_with_actions
    
    print(f"Всего пользователей, увидевших экран оплаты: {len(user_behaviors)}")
    print(f"Пользователей с последующими действиями: {users_with_actions} ({users_with_actions/len(user_behaviors)*100:.1f}%)")
    print(f"Пользователей без последующих действий: {users_without_actions} ({users_without_actions/len(user_behaviors)*100:.1f}%)")
    print()
    
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование: python3 analyze_payment_screen_behavior.py YYYY-MM-DD")
        print("Пример: python3 analyze_payment_screen_behavior.py 2025-12-21")
        sys.exit(1)
    
    date_filter = sys.argv[1]
    analyze_payment_screen_behavior(date_filter)


