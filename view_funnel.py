#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для анализа воронки конверсии по всем пользователям
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

def get_funnel_stats(db_type, cursor, date_filter=None):
    """Получает статистику воронки
    
    Args:
        db_type: Тип БД ('postgresql' или 'sqlite')
        cursor: Курсор БД
        date_filter: Дата для фильтрации в формате 'YYYY-MM-DD' (опционально)
                     Фильтрация происходит по московскому времени (UTC+3)
    """
    stats = {}
    
    # Формируем условие фильтрации по дате (по московскому времени)
    if date_filter:
        # timestamp хранится в формате ISO без часового пояса (предположительно в UTC или MSK)
        # Для фильтрации по московскому времени используем диапазон дат с учетом смещения
        if db_type == 'postgresql':
            # PostgreSQL: конвертируем timestamp в московское время
            # Если timestamp без TZ, считаем что это UTC и конвертируем в MSK
            # MSK = UTC+3, поэтому начало дня в MSK = начало дня UTC - 3 часа
            date_condition = """AND (
                (timestamp::timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')::date = %s::date
            )"""
            date_params = (date_filter,)
        else:
            # SQLite: timestamp хранится как ISO строка
            # Создаем временные метки начала и конца дня по московскому времени
            moscow_tz = pytz.timezone('Europe/Moscow')
            date_start_msk = moscow_tz.localize(datetime.strptime(f"{date_filter} 00:00:00", "%Y-%m-%d %H:%M:%S"))
            date_end_msk = moscow_tz.localize(datetime.strptime(f"{date_filter} 23:59:59.999", "%Y-%m-%d %H:%M:%S.%f"))
            # Конвертируем в UTC для сравнения (если timestamp в UTC)
            date_start_utc = date_start_msk.astimezone(pytz.UTC).isoformat()
            date_end_utc = date_end_msk.astimezone(pytz.UTC).isoformat()
            date_condition = "AND timestamp >= ? AND timestamp <= ?"
            date_params = (date_start_utc, date_end_utc)
    else:
        date_condition = ""
        date_params = ()
    
    # Уникальные пользователи на каждом этапе
    if db_type == 'postgresql':
        # Старт
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('start',) + date_params if date_filter else ('start',))
        stats['start'] = cursor.fetchone()[0]
        
        # Заполнение профиля
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('profile_complete',) + date_params if date_filter else ('profile_complete',))
        stats['profile_complete'] = cursor.fetchone()[0]
        
        # Начало оплаты
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('payment_start',) + date_params if date_filter else ('payment_start',))
        stats['payment_start'] = cursor.fetchone()[0]
        
        # Успешная оплата
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('payment_success',) + date_params if date_filter else ('payment_success',))
        stats['payment_success'] = cursor.fetchone()[0]
        
        # Начало генерации
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('natal_chart_generation_start',) + date_params if date_filter else ('natal_chart_generation_start',))
        stats['natal_chart_generation_start'] = cursor.fetchone()[0]
        
        # Успешная генерация
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('natal_chart_success',) + date_params if date_filter else ('natal_chart_success',))
        stats['natal_chart_success'] = cursor.fetchone()[0]
        
        # Ошибки генерации
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('natal_chart_error',) + date_params if date_filter else ('natal_chart_error',))
        stats['natal_chart_error'] = cursor.fetchone()[0]
        
        # Просмотр "Положение планет"
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('planets_info_viewed',) + date_params if date_filter else ('planets_info_viewed',))
        stats['planets_info_viewed'] = cursor.fetchone()[0]
        
        # Запрос данных о планетах
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('planets_data_requested',) + date_params if date_filter else ('planets_data_requested',))
        stats['planets_data_requested'] = cursor.fetchone()[0]
        
        # Обращения в поддержку
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = %s {date_condition}', 
                      ('support_contacted',) + date_params if date_filter else ('support_contacted',))
        stats['support_contacted'] = cursor.fetchone()[0]
        
        # Всего уникальных пользователей
        if date_filter:
            cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE 1=1 {date_condition}', date_params)
        else:
            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM events')
        stats['total_users'] = cursor.fetchone()[0]
        
        # Всего уникальных пользователей с профилем (без фильтра по дате, т.к. это состояние, а не событие)
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM users WHERE birth_date IS NOT NULL')
        stats['users_with_profile'] = cursor.fetchone()[0]
        
        # Всего платежей (количество)
        cursor.execute(f'SELECT COUNT(*) FROM events WHERE event_type = %s {date_condition}', 
                      ('payment_success',) + date_params if date_filter else ('payment_success',))
        stats['total_payments'] = cursor.fetchone()[0]
        
        # Сумма всех платежей
        if date_filter:
            cursor.execute(f'''
                SELECT SUM((event_data::json->>'total_amount')::int) 
                FROM events 
                WHERE event_type = %s AND event_data IS NOT NULL {date_condition}
            ''', ('payment_success',) + date_params)
        else:
            cursor.execute('''
                SELECT SUM((event_data::json->>'total_amount')::int) 
                FROM events 
                WHERE event_type = %s AND event_data IS NOT NULL
            ''', ('payment_success',))
        result = cursor.fetchone()[0]
        stats['total_revenue'] = (result or 0) / 100  # Конвертируем из копеек в рубли
        
    else:
        # SQLite версия
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('start',) + date_params if date_filter else ('start',))
        stats['start'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('profile_complete',) + date_params if date_filter else ('profile_complete',))
        stats['profile_complete'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('payment_start',) + date_params if date_filter else ('payment_start',))
        stats['payment_start'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('payment_success',) + date_params if date_filter else ('payment_success',))
        stats['payment_success'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('natal_chart_generation_start',) + date_params if date_filter else ('natal_chart_generation_start',))
        stats['natal_chart_generation_start'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('natal_chart_success',) + date_params if date_filter else ('natal_chart_success',))
        stats['natal_chart_success'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('natal_chart_error',) + date_params if date_filter else ('natal_chart_error',))
        stats['natal_chart_error'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('planets_info_viewed',) + date_params if date_filter else ('planets_info_viewed',))
        stats['planets_info_viewed'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('planets_data_requested',) + date_params if date_filter else ('planets_data_requested',))
        stats['planets_data_requested'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? {date_condition}', 
                      ('support_contacted',) + date_params if date_filter else ('support_contacted',))
        stats['support_contacted'] = cursor.fetchone()[0]
        
        if date_filter:
            cursor.execute(f'SELECT COUNT(DISTINCT user_id) FROM events WHERE 1=1 {date_condition}', date_params)
        else:
            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM events')
        stats['total_users'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM users WHERE birth_date IS NOT NULL')
        stats['users_with_profile'] = cursor.fetchone()[0]
        
        cursor.execute(f'SELECT COUNT(*) FROM events WHERE event_type = ? {date_condition}', 
                      ('payment_success',) + date_params if date_filter else ('payment_success',))
        stats['total_payments'] = cursor.fetchone()[0]
        
        stats['total_revenue'] = 0  # SQLite сложнее парсить JSON
    
    return stats

def print_funnel(stats, date_filter=None):
    """Выводит воронку конверсии"""
    print("\n" + "="*80)
    if date_filter:
        print(f"📊 ВОРОНКА КОНВЕРСИИ ЗА {date_filter}")
    else:
        print("📊 ВОРОНКА КОНВЕРСИИ ПО ВСЕМ ПОЛЬЗОВАТЕЛЯМ")
    print("="*80)
    
    # Основная воронка
    print("\n🔵 ОСНОВНАЯ ВОРОНКА:")
    print("-"*80)
    
    steps = [
        ('Старт (start)', 'start'),
        ('Заполнение профиля', 'profile_complete'),
        ('Переход на экран получения карты', 'payment_start'),
        ('Успешная оплата', 'payment_success'),
        ('Начало генерации карты', 'natal_chart_generation_start'),
        ('Успешная генерация карты', 'natal_chart_success'),
    ]
    
    prev_count = None
    for step_name, step_key in steps:
        count = stats.get(step_key, 0)
        
        if prev_count is None:
            prev_count = count
            conversion = 100.0
        else:
            if prev_count > 0:
                conversion = (count / prev_count) * 100
            else:
                conversion = 0.0
        
        bar_length = int((count / stats['start']) * 40) if stats['start'] > 0 else 0
        bar = "█" * bar_length + "░" * (40 - bar_length)
        
        print(f"{step_name:35} │ {count:4} пользователей │ {conversion:5.1f}% │ {bar}")
        prev_count = count
    
    # Дополнительная статистика
    print("\n📈 ДОПОЛНИТЕЛЬНАЯ СТАТИСТИКА:")
    print("-"*80)
    
    # Пользователи с профилем
    users_with_profile = stats.get('users_with_profile', 0)
    profile_conversion = (users_with_profile / stats['start'] * 100) if stats['start'] > 0 else 0
    print(f"{'Пользователи с заполненным профилем':35} │ {users_with_profile:4} │ {profile_conversion:5.1f}%")
    
    # Ошибки генерации
    errors = stats.get('natal_chart_error', 0)
    if stats.get('natal_chart_generation_start', 0) > 0:
        error_rate = (errors / stats['natal_chart_generation_start']) * 100
        print(f"{'Ошибки генерации карты':35} │ {errors:4} │ {error_rate:5.1f}%")
    
    # Просмотр "Положение планет"
    planets_viewed = stats.get('planets_info_viewed', 0)
    planets_conversion = (planets_viewed / stats['start'] * 100) if stats['start'] > 0 else 0
    planets_label = 'Просмотр "Положение планет"'
    print(f"{planets_label:35} │ {planets_viewed:4} │ {planets_conversion:5.1f}%")
    
    # Запрос данных о планетах
    planets_requested = stats.get('planets_data_requested', 0)
    if planets_viewed > 0:
        planets_data_conversion = (planets_requested / planets_viewed) * 100
        print(f"{'Запрос данных о планетах':35} │ {planets_requested:4} │ {planets_data_conversion:5.1f}%")
    
    # Обращения в поддержку
    support = stats.get('support_contacted', 0)
    support_conversion = (support / stats['start'] * 100) if stats['start'] > 0 else 0
    print(f"{'Обращения в поддержку':35} │ {support:4} │ {support_conversion:5.1f}%")
    
    # Финансовая статистика
    print("\n💰 ФИНАНСОВАЯ СТАТИСТИКА:")
    print("-"*80)
    total_payments = stats.get('total_payments', 0)
    total_revenue = stats.get('total_revenue', 0)
    avg_revenue_per_payment = total_revenue / total_payments if total_payments > 0 else 0
    avg_revenue_per_user = total_revenue / stats['start'] if stats['start'] > 0 else 0
    
    print(f"{'Всего платежей':35} │ {total_payments:4}")
    print(f"{'Общая выручка':35} │ {total_revenue:10.2f} ₽")
    print(f"{'Средний чек':35} │ {avg_revenue_per_payment:10.2f} ₽")
    print(f"{'Выручка на пользователя':35} │ {avg_revenue_per_user:10.2f} ₽")
    
    # Итоговые метрики
    print("\n🎯 КЛЮЧЕВЫЕ МЕТРИКИ:")
    print("-"*80)
    print(f"{'Всего уникальных пользователей':35} │ {stats.get('total_users', 0):4}")
    
    # Конверсия в оплату
    payment_conversion = (stats['payment_success'] / stats['start'] * 100) if stats['start'] > 0 else 0
    print(f"{'Конверсия в оплату':35} │ {payment_conversion:5.1f}%")
    
    # Конверсия в генерацию
    chart_conversion = (stats['natal_chart_success'] / stats['start'] * 100) if stats['start'] > 0 else 0
    print(f"{'Конверсия в генерацию карты':35} │ {chart_conversion:5.1f}%")
    
    print("\n" + "="*80)

def main():
    import sys
    
    # Получаем дату из аргументов командной строки или используем по умолчанию
    date_filter = None
    if len(sys.argv) > 1:
        date_filter = sys.argv[1]
        # Проверяем формат даты
        try:
            datetime.strptime(date_filter, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Неверный формат даты: {date_filter}")
            print("Используйте формат: YYYY-MM-DD (например: 2025-12-08)")
            return
    
    print("🔌 Подключение к базе данных...")
    conn, db_type = get_db_connection()
    
    if db_type == 'postgresql':
        print("✅ Подключение к PostgreSQL установлено")
    else:
        print("✅ Используется локальный SQLite")
    
    if date_filter:
        print(f"📅 Фильтр по дате: {date_filter}")
    
    cursor = conn.cursor()
    
    try:
        stats = get_funnel_stats(db_type, cursor, date_filter)
        print_funnel(stats, date_filter)
    except Exception as e:
        print(f"❌ Ошибка при получении статистики: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == '__main__':
    main()

