#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для исправления статуса оплаты и запуска генерации натальной карты
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


def fix_user_payment_status(user_id, db_type, cursor, conn):
    """Исправляет статус оплаты пользователя"""
    try:
        if db_type == 'postgresql':
            # Используем CURRENT_TIMESTAMP для PostgreSQL
            cursor.execute('''
                UPDATE users
                SET has_paid = 1, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            ''', (user_id,))
        else:
            cursor.execute('''
                UPDATE users
                SET has_paid = 1, updated_at = ?
                WHERE user_id = ?
            ''', (datetime.now().isoformat(), user_id))
        
        conn.commit()
        
        # Проверяем результат
        if db_type == 'postgresql':
            cursor.execute('SELECT has_paid FROM users WHERE user_id = %s', (user_id,))
        else:
            cursor.execute('SELECT has_paid FROM users WHERE user_id = ?', (user_id,))
        
        result = cursor.fetchone()
        has_paid = result[0] if result else 0
        
        return has_paid == 1
    except Exception as e:
        print(f"   ❌ Ошибка при обновлении статуса оплаты: {e}")
        conn.rollback()
        return False


def get_user_profile(user_id, db_type, cursor):
    """Получает профиль пользователя"""
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
    if not profile:
        return None
    
    return {
        'birth_name': profile[0] or '',
        'birth_date': profile[1] or '',
        'birth_time': profile[2] or '',
        'birth_place': profile[3] or ''
    }


def check_and_fix_payment(user_id):
    """Проверяет и исправляет статус оплаты, запускает генерацию если нужно"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    print(f"🔍 Проверка пользователя {user_id}\n")
    
    # Проверяем текущий статус
    if db_type == 'postgresql':
        cursor.execute('SELECT has_paid FROM users WHERE user_id = %s', (user_id,))
    else:
        cursor.execute('SELECT has_paid FROM users WHERE user_id = ?', (user_id,))
    
    result = cursor.fetchone()
    current_has_paid = result[0] if result else 0
    
    print(f"   Текущий статус оплаты: {'✅ Да' if current_has_paid else '❌ Нет'}")
    
    # Проверяем успешные платежи
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT COUNT(*) FROM payments
            WHERE user_id = %s AND status = 'succeeded'
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT COUNT(*) FROM payments
            WHERE user_id = ? AND status = 'succeeded'
        ''', (user_id,))
    
    succeeded_payments = cursor.fetchone()[0]
    print(f"   Успешных платежей: {succeeded_payments}")
    
    # Если есть успешные платежи, но has_paid = 0, исправляем
    if succeeded_payments > 0 and not current_has_paid:
        print(f"\n   🔧 Исправляем статус оплаты...")
        if fix_user_payment_status(user_id, db_type, cursor, conn):
            print(f"      ✅ Статус оплаты обновлен")
        else:
            print(f"      ❌ Не удалось обновить статус")
            conn.close()
            return False
    
    # Проверяем профиль
    profile = get_user_profile(user_id, db_type, cursor)
    if profile:
        has_profile = all([profile['birth_name'], profile['birth_date'], 
                         profile['birth_time'], profile['birth_place']])
        
        if has_profile:
            print(f"\n   ✅ Профиль заполнен:")
            print(f"      Имя: {profile['birth_name']}")
            print(f"      Дата: {profile['birth_date']}")
            print(f"      Время: {profile['birth_time']}")
            print(f"      Место: {profile['birth_place']}")
            
            # Проверяем, была ли уже успешная генерация после последнего платежа
            if db_type == 'postgresql':
                cursor.execute('''
                    SELECT MAX(p.created_at) as last_payment
                    FROM payments p
                    WHERE p.user_id = %s AND p.status = 'succeeded'
                ''', (user_id,))
                last_payment_result = cursor.fetchone()
                last_payment = last_payment_result[0] if last_payment_result else None
                
                if last_payment:
                    cursor.execute('''
                        SELECT COUNT(*) FROM events
                        WHERE user_id = %s 
                        AND event_type = 'natal_chart_success'
                        AND timestamp > %s
                    ''', (user_id, last_payment.isoformat() if hasattr(last_payment, 'isoformat') else str(last_payment)))
                else:
                    cursor.execute('''
                        SELECT COUNT(*) FROM events
                        WHERE user_id = %s 
                        AND event_type = 'natal_chart_success'
                    ''', (user_id,))
            else:
                cursor.execute('''
                    SELECT MAX(created_at) as last_payment
                    FROM payments
                    WHERE user_id = ? AND status = 'succeeded'
                ''', (user_id,))
                last_payment_result = cursor.fetchone()
                last_payment = last_payment_result[0] if last_payment_result else None
                
                if last_payment:
                    cursor.execute('''
                        SELECT COUNT(*) FROM events
                        WHERE user_id = ? 
                        AND event_type = 'natal_chart_success'
                        AND timestamp > ?
                    ''', (user_id, last_payment))
                else:
                    cursor.execute('''
                        SELECT COUNT(*) FROM events
                        WHERE user_id = ? 
                        AND event_type = 'natal_chart_success'
                    ''', (user_id,))
            
            success_count = cursor.fetchone()[0]
            
            if success_count == 0:
                print(f"\n   ⚠️ Генерация натальной карты не была запущена после оплаты")
                print(f"      💡 Пользователю нужно запросить генерацию вручную через бота")
                print(f"      💡 Или можно запустить генерацию через API бота")
            else:
                print(f"\n   ✅ Генерация натальной карты уже была выполнена")
        else:
            print(f"\n   ⚠️ Профиль не заполнен полностью")
            missing = []
            if not profile['birth_name']: missing.append('Имя')
            if not profile['birth_date']: missing.append('Дата')
            if not profile['birth_time']: missing.append('Время')
            if not profile['birth_place']: missing.append('Место')
            print(f"      Отсутствуют: {', '.join(missing)}")
    
    print(f"\n✅ Проверка завершена")
    conn.close()
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python fix_user_payment_and_generate.py <user_id>")
        print("  python fix_user_payment_and_generate.py <username>")
        print("\nПримеры:")
        print("  python fix_user_payment_and_generate.py 724281972")
        print("  python fix_user_payment_and_generate.py NikitaRoshchin")
        sys.exit(1)
    
    user_input = sys.argv[1]
    
    # Определяем, это user_id или username
    try:
        user_id = int(user_input)
    except ValueError:
        # Это username, нужно найти user_id
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        username = user_input.lstrip('@')
        
        if db_type == 'postgresql':
            cursor.execute('SELECT user_id FROM users WHERE username = %s OR username = %s', 
                         (username, f'@{username}'))
        else:
            cursor.execute('SELECT user_id FROM users WHERE username = ? OR username = ?', 
                         (username, f'@{username}'))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            print(f"❌ Пользователь '{user_input}' не найден")
            sys.exit(1)
        
        user_id = result[0]
    
    try:
        check_and_fix_payment(user_id)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)






