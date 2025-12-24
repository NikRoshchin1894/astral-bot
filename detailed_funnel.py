#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для детального поэтапного анализа воронки
"""

import os
import sys
from urllib.parse import urlparse
import psycopg2
import sqlite3
from dotenv import load_dotenv
from datetime import datetime
import pytz

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

def get_detailed_funnel(date_filter):
    """Получает детальную поэтапную воронку"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    print(f"🔌 Подключение к базе данных...")
    print(f"✅ Подключение к {'PostgreSQL' if db_type == 'postgresql' else 'SQLite'} установлено")
    print(f"📅 Фильтр по дате: {date_filter}\n")
    
    # Формируем условие фильтрации по дате
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
    
    # Этапы воронки
    stages = [
        ('start', 'Старт (start)', 'Пользователи, нажавшие /start'),
        ('profile_filling_start', 'Начали заполнять профиль', 'Пользователи, начавшие заполнение профиля'),
        ('profile_complete', 'Заполнили профиль', 'Пользователи, завершившие заполнение профиля'),
        ('natal_chart_request_no_payment', 'Увидели экран с предложением оплаты', 'Пользователи, увидевшие экран оплаты'),
        ('payment_start', 'Начали процесс оплаты', 'Пользователи, начавшие оплату'),
        ('payment_success', 'Успешная оплата', 'Пользователи, успешно оплатившие'),
        ('natal_chart_generation_start', 'Начало генерации карты', 'Пользователи, у которых началась генерация'),
        ('natal_chart_success', 'Успешная генерация карты', 'Пользователи, получившие карту'),
    ]
    
    print("=" * 80)
    print("📊 ПОЭТАПНАЯ ВОРОНКА КОНВЕРСИИ")
    print("=" * 80)
    print()
    
    previous_count = None
    total_start = None
    
    for i, (event_type, stage_name, stage_description) in enumerate(stages):
        # Получаем количество пользователей на этом этапе
        if db_type == 'postgresql':
            cursor.execute(f'''
                SELECT COUNT(DISTINCT user_id)
                FROM events
                WHERE event_type = %s {date_condition}
            ''', (event_type,) + date_params)
        else:
            cursor.execute(f'''
                SELECT COUNT(DISTINCT user_id)
                FROM events
                WHERE event_type = ? {date_condition}
            ''', (event_type,) + date_params)
        
        count = cursor.fetchone()[0] or 0
        
        if i == 0:
            total_start = count
        
        # Вычисляем метрики
        if total_start:
            conversion_from_start = (count / total_start) * 100
        else:
            conversion_from_start = 0
        
        if previous_count and previous_count > 0:
            conversion_from_previous = (count / previous_count) * 100
            drop_from_previous = previous_count - count
            drop_percentage = (drop_from_previous / previous_count) * 100
        else:
            conversion_from_previous = 100.0 if count > 0 else 0
            drop_from_previous = 0
            drop_percentage = 0
        
        # Визуализация прогресс-бара
        bar_length = 40
        filled = int((conversion_from_start / 100) * bar_length)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        # Выводим этап
        print(f"🔵 ЭТАП {i+1}: {stage_name}")
        print("-" * 80)
        print(f"📝 Описание: {stage_description}")
        print(f"👥 Пользователей на этапе: {count}")
        
        if i == 0:
            print(f"📊 Конверсия от старта: {conversion_from_start:.1f}%")
        else:
            print(f"📊 Конверсия от старта: {conversion_from_start:.1f}%")
            print(f"📉 Потеря от предыдущего этапа: {drop_from_previous} пользователей ({drop_percentage:.1f}%)")
            print(f"📈 Конверсия от предыдущего этапа: {conversion_from_previous:.1f}%")
        
        print(f"📊 Визуализация: {bar} {conversion_from_start:.1f}%")
        print()
        
        previous_count = count
    
    # Итоговая статистика
    print("=" * 80)
    print("📈 ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print()
    
    if total_start:
        final_count = count
        overall_conversion = (final_count / total_start) * 100
        total_drop = total_start - final_count
        total_drop_percentage = (total_drop / total_start) * 100
        
        print(f"🎯 Всего пользователей на старте: {total_start}")
        print(f"✅ Дошло до финала: {final_count}")
        print(f"📉 Общая потеря: {total_drop} пользователей ({total_drop_percentage:.1f}%)")
        print(f"📊 Общая конверсия: {overall_conversion:.1f}%")
        print()
        
        # Критические точки потери
        print("🔴 КРИТИЧЕСКИЕ ТОЧКИ ПОТЕРЬ:")
        print("-" * 80)
        
        previous_count = total_start
        for i, (event_type, stage_name, _) in enumerate(stages[1:], 1):
            if db_type == 'postgresql':
                cursor.execute(f'''
                    SELECT COUNT(DISTINCT user_id)
                    FROM events
                    WHERE event_type = %s {date_condition}
                ''', (event_type,) + date_params)
            else:
                cursor.execute(f'''
                    SELECT COUNT(DISTINCT user_id)
                    FROM events
                    WHERE event_type = ? {date_condition}
                ''', (event_type,) + date_params)
            
            current_count = cursor.fetchone()[0] or 0
            loss = previous_count - current_count
            loss_percentage = (loss / previous_count * 100) if previous_count > 0 else 0
            
            if loss > 0:
                print(f"  {i}. {stage_name}: потеря {loss} пользователей ({loss_percentage:.1f}%)")
            
            previous_count = current_count
    
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Если дата не указана, используем сегодня
        moscow_tz = pytz.timezone('Europe/Moscow')
        today = datetime.now(moscow_tz).date()
        date_filter = today.strftime('%Y-%m-%d')
        print(f"📅 Дата не указана, используем сегодня: {date_filter}\n")
    else:
        date_filter = sys.argv[1]
    
    get_detailed_funnel(date_filter)


