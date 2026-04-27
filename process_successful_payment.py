#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для обработки успешного платежа вручную
Помечает пользователя как оплатившего и логирует событие
"""

import os
import sys
import json
from datetime import datetime
from urllib.parse import urlparse
import psycopg2
from dotenv import load_dotenv

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
            print(f"❌ Ошибка подключения к PostgreSQL: {e}")
            import sqlite3
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        import sqlite3
        return sqlite3.connect(DATABASE), 'sqlite'


def mark_user_paid(user_id, db_type, cursor, conn):
    """Помечает пользователя как оплатившего"""
    now = datetime.now().isoformat()
    
    try:
        if db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO users (user_id, has_paid, updated_at)
                VALUES (%s, 1, %s)
                ON CONFLICT(user_id) DO UPDATE SET
                    has_paid = 1,
                    updated_at = EXCLUDED.updated_at
            ''', (user_id, now))
        else:
            cursor.execute('''
                INSERT INTO users (user_id, has_paid, updated_at)
                VALUES (?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    has_paid = 1,
                    updated_at = excluded.updated_at
            ''', (user_id, now))
        conn.commit()
        return True
    except Exception as e:
        print(f"   ❌ Ошибка при пометке пользователя: {e}")
        conn.rollback()
        return False


def log_event(user_id, event_type, event_data, db_type, cursor, conn):
    """Логирует событие"""
    try:
        event_data_str = json.dumps(event_data, ensure_ascii=False) if event_data else None
        timestamp = datetime.now().isoformat()
        
        if db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO events (user_id, event_type, event_data, timestamp)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, event_type, event_data_str, timestamp))
        else:
            cursor.execute('''
                INSERT INTO events (user_id, event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, event_type, event_data_str, timestamp))
        conn.commit()
        return True
    except Exception as e:
        print(f"   ⚠️ Ошибка при логировании события: {e}")
        conn.rollback()
        return False


def process_successful_payment(yookassa_payment_id, user_id=None):
    """Обрабатывает успешный платеж"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    # Если user_id не передан, получаем из платежа
    if not user_id:
        if db_type == 'postgresql':
            cursor.execute('''
                SELECT user_id, amount FROM payments
                WHERE yookassa_payment_id = %s
            ''', (yookassa_payment_id,))
        else:
            cursor.execute('''
                SELECT user_id, amount FROM payments
                WHERE yookassa_payment_id = ?
            ''', (yookassa_payment_id,))
        
        result = cursor.fetchone()
        if not result:
            print(f"❌ Платеж {yookassa_payment_id} не найден в базе данных")
            conn.close()
            return False
        
        user_id = result[0]
        amount = result[1]
    else:
        if db_type == 'postgresql':
            cursor.execute('''
                SELECT amount FROM payments
                WHERE yookassa_payment_id = %s
            ''', (yookassa_payment_id,))
        else:
            cursor.execute('''
                SELECT amount FROM payments
                WHERE yookassa_payment_id = ?
            ''', (yookassa_payment_id,))
        
        result = cursor.fetchone()
        amount = result[0] if result else 0
    
    print(f"🔍 Обработка успешного платежа:")
    print(f"   Платеж: {yookassa_payment_id}")
    print(f"   Пользователь: {user_id}")
    print(f"   Сумма: {amount} ₽\n")
    
    # Помечаем пользователя как оплатившего
    print("   📝 Помечаем пользователя как оплатившего...")
    if mark_user_paid(user_id, db_type, cursor, conn):
        print("      ✅ Пользователь помечен как оплативший")
    else:
        print("      ❌ Ошибка при пометке пользователя")
        conn.close()
        return False
    
    # Логируем событие успешной оплаты
    print("   📝 Логируем событие payment_success...")
    event_data = {
        'yookassa_payment_id': yookassa_payment_id,
        'amount': amount,
        'source': 'manual_processing'
    }
    if log_event(user_id, 'payment_success', event_data, db_type, cursor, conn):
        print("      ✅ Событие залогировано")
    else:
        print("      ⚠️ Не удалось залогировать событие")
    
    # Проверяем, заполнен ли профиль
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT first_name, birth_date, birth_time, birth_place
            FROM users WHERE user_id = %s
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT first_name, birth_date, birth_time, birth_place
            FROM users WHERE user_id = ?
        ''', (user_id,))
    
    profile = cursor.fetchone()
    if profile:
        has_profile = all([profile[0], profile[1], profile[2], profile[3]])
        if has_profile:
            print(f"\n   ✅ Профиль пользователя заполнен")
            print(f"      💡 Можно запустить генерацию натальной карты")
        else:
            print(f"\n   ⚠️ Профиль пользователя не заполнен полностью")
            print(f"      💡 Пользователю нужно заполнить профиль перед генерацией")
    
    print(f"\n✅ Обработка платежа завершена")
    conn.close()
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python process_successful_payment.py <yookassa_payment_id> [user_id]")
        print("\nПримеры:")
        print("  python process_successful_payment.py 30c3d6d8-000f-5000-8000-1316cc5dc8e1")
        print("  python process_successful_payment.py 30c3d6d8-000f-5000-8000-1316cc5dc8e1 724281972")
        sys.exit(1)
    
    payment_id = sys.argv[1]
    user_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    try:
        process_successful_payment(payment_id, user_id)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)






