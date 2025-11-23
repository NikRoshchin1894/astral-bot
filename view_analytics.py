#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для просмотра аналитики бота
Показывает воронку событий для анализа поведения пользователей
"""

import sqlite3
import json
from datetime import datetime
from collections import defaultdict, Counter

DATABASE = 'users.db'

def get_analytics():
    """Получает аналитику из базы данных"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    
    # Получаем все события
    events = conn.execute('''
        SELECT user_id, event_type, event_data, timestamp
        FROM events
        ORDER BY timestamp DESC
    ''').fetchall()
    
    # Получаем уникальных пользователей
    unique_users = conn.execute('SELECT COUNT(DISTINCT user_id) as count FROM events').fetchone()['count']
    
    # Подсчитываем события по типам
    event_counts = Counter(e['event_type'] for e in events)
    
    # Подсчитываем по дням
    daily_events = defaultdict(lambda: defaultdict(int))
    for event in events:
        date = event['timestamp'][:10]  # Берем только дату
        daily_events[date][event['event_type']] += 1
    
    conn.close()
    
    return {
        'unique_users': unique_users,
        'total_events': len(events),
        'event_counts': dict(event_counts),
        'daily_events': dict(daily_events),
        'recent_events': [dict(e) for e in events[:50]]  # Последние 50 событий
    }

def print_analytics():
    """Выводит аналитику в консоль"""
    analytics = get_analytics()
    
    print("=" * 60)
    print("📊 АНАЛИТИКА БОТА")
    print("=" * 60)
    print()
    
    print(f"👥 Уникальных пользователей: {analytics['unique_users']}")
    print(f"📈 Всего событий: {analytics['total_events']}")
    print()
    
    print("📋 События по типам:")
    print("-" * 60)
    event_names = {
        'start': '🚀 Старт бота',
        'button_click': '🔘 Нажатие кнопки',
        'profile_viewed': '👤 Просмотр профиля',
        'profile_saved': '💾 Сохранение профиля',
        'profile_complete': '✅ Профиль заполнен полностью',
        'payment_start': '💳 Начало оплаты',
        'payment_precheckout': '🔍 Проверка оплаты',
        'payment_success': '✅ Успешная оплата',
        'payment_error': '❌ Ошибка оплаты',
        'natal_chart_request_no_profile': '📜 Запрос без профиля',
        'natal_chart_request_no_payment': '📜 Запрос без оплаты',
        'natal_chart_generation_start': '⚙️ Начало генерации',
        'natal_chart_success': '✅ Успешная генерация',
        'natal_chart_error': '❌ Ошибка генерации',
        'support_contacted': '💬 Обращение в поддержку'
    }
    
    for event_type, count in sorted(analytics['event_counts'].items(), key=lambda x: x[1], reverse=True):
        name = event_names.get(event_type, event_type)
        print(f"  {name}: {count}")
    
    print()
    print("📅 События по дням (последние 7 дней):")
    print("-" * 60)
    daily = analytics['daily_events']
    sorted_dates = sorted(daily.keys(), reverse=True)[:7]
    for date in sorted_dates:
        print(f"\n{date}:")
        for event_type, count in sorted(daily[date].items(), key=lambda x: x[1], reverse=True):
            name = event_names.get(event_type, event_type)
            print(f"  {name}: {count}")
    
    print()
    print("🔄 Воронка:")
    print("-" * 60)
    start_count = analytics['event_counts'].get('start', 0)
    profile_complete = analytics['event_counts'].get('profile_complete', 0)
    payment_success = analytics['event_counts'].get('payment_success', 0)
    natal_success = analytics['event_counts'].get('natal_chart_success', 0)
    natal_errors = analytics['event_counts'].get('natal_chart_error', 0)
    generation_start = analytics['event_counts'].get('natal_chart_generation_start', 0)
    
    if start_count > 0:
        print(f"Старт бота: {start_count} (100%)")
        print(f"Профиль заполнен: {profile_complete} ({profile_complete*100/start_count:.1f}%)")
        print(f"Оплата: {payment_success} ({payment_success*100/start_count:.1f}%)")
        print(f"Начало генерации: {generation_start} ({generation_start*100/start_count:.1f}%)")
        print(f"✅ Натальная карта получена: {natal_success} ({natal_success*100/start_count:.1f}%)")
        print(f"❌ Ошибки при генерации: {natal_errors} ({natal_errors*100/start_count:.1f}%)")
        
        if generation_start > 0:
            success_rate = (natal_success / generation_start) * 100 if generation_start > 0 else 0
            error_rate = (natal_errors / generation_start) * 100 if generation_start > 0 else 0
            print()
            print(f"📊 Конверсия генерации (от начала генерации):")
            print(f"  Успешных: {natal_success} ({success_rate:.1f}%)")
            print(f"  Ошибок: {natal_errors} ({error_rate:.1f}%)")
    
    print()
    print("=" * 60)

if __name__ == '__main__':
    try:
        print_analytics()
    except Exception as e:
        print(f"Ошибка при получении аналитики: {e}")
        import traceback
        traceback.print_exc()

