#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для синхронизации статусов платежей с YooKassa API
Обновляет статусы платежей в базе данных на основе реальных данных из YooKassa
"""

import os
import sys
import requests
import base64
import json
from datetime import datetime
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor
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
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        import sqlite3
        return sqlite3.connect(DATABASE), 'sqlite'


def check_payment_status_yookassa(yookassa_payment_id):
    """Проверяет статус платежа через API YooKassa"""
    shop_id = os.getenv('YOOKASSA_SHOP_ID')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY')
    
    if not shop_id or not secret_key:
        return None
    
    auth_string = f"{shop_id}:{secret_key}"
    auth_bytes = auth_string.encode('ascii')
    auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"https://api.yookassa.ru/v3/payments/{yookassa_payment_id}",
            headers=headers,
            timeout=(10, 60)
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"   ⚠️ Ошибка API для {yookassa_payment_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"   ⚠️ Ошибка при запросе для {yookassa_payment_id}: {e}")
        return None


def update_payment_status_in_db(yookassa_payment_id, status, db_type, cursor, conn):
    """Обновляет статус платежа в базе данных"""
    try:
        if db_type == 'postgresql':
            cursor.execute('''
                UPDATE payments
                SET status = %s, updated_at = %s
                WHERE yookassa_payment_id = %s
                RETURNING user_id, amount
            ''', (status, datetime.now(), yookassa_payment_id))
            result = cursor.fetchone()
            conn.commit()
            return result
        else:
            cursor.execute('''
                UPDATE payments
                SET status = ?, updated_at = ?
                WHERE yookassa_payment_id = ?
            ''', (status, datetime.now().isoformat(), yookassa_payment_id))
            conn.commit()
            cursor.execute('''
                SELECT user_id, amount FROM payments
                WHERE yookassa_payment_id = ?
            ''', (yookassa_payment_id,))
            return cursor.fetchone()
    except Exception as e:
        print(f"   ❌ Ошибка при обновлении статуса: {e}")
        conn.rollback()
        return None


def sync_payments_for_user(username=None, user_id=None):
    """Синхронизирует статусы платежей для пользователя"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем платежи
    if username:
        # Находим пользователя по username
        username = username.lstrip('@')
        if db_type == 'postgresql':
            cursor.execute('SELECT user_id FROM users WHERE username = %s OR username = %s', 
                         (username, f'@{username}'))
        else:
            cursor.execute('SELECT user_id FROM users WHERE username = ? OR username = ?', 
                         (username, f'@{username}'))
        result = cursor.fetchone()
        if not result:
            print(f"❌ Пользователь '{username}' не найден")
            conn.close()
            return
        user_id = result[0] if db_type == 'postgresql' else result[0]
    
    # Получаем все pending платежи пользователя
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT id, yookassa_payment_id, status
            FROM payments 
            WHERE user_id = %s AND status = 'pending'
            ORDER BY created_at DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT id, yookassa_payment_id, status
            FROM payments 
            WHERE user_id = ? AND status = 'pending'
            ORDER BY created_at DESC
        ''', (user_id,))
    
    pending_payments = cursor.fetchall()
    
    if not pending_payments:
        print(f"✅ Нет pending платежей для синхронизации")
        conn.close()
        return
    
    print(f"🔍 Найдено {len(pending_payments)} pending платежей для синхронизации\n")
    
    updated_count = 0
    for payment_row in pending_payments:
        payment_id = payment_row[1] if db_type == 'postgresql' else payment_row[1]
        current_status = payment_row[2] if db_type == 'postgresql' else payment_row[2]
        
        print(f"   Проверка платежа: {payment_id}")
        
        # Проверяем статус через API
        payment_info = check_payment_status_yookassa(payment_id)
        
        if not payment_info:
            print(f"      ⚠️ Не удалось получить информацию")
            continue
        
        real_status = payment_info.get('status')
        
        if real_status != current_status:
            print(f"      📝 Обновление: {current_status} → {real_status}")
            
            # Обновляем в базе
            update_result = update_payment_status_in_db(payment_id, real_status, db_type, cursor, conn)
            
            if update_result:
                updated_count += 1
                
                if real_status == 'canceled':
                    cancellation_details = payment_info.get('cancellation_details', {})
                    reason = cancellation_details.get('reason', 'unknown')
                    party = cancellation_details.get('party', 'unknown')
                    print(f"      ❌ Отменен: {reason} (инициатор: {party})")
                elif real_status == 'succeeded':
                    print(f"      ✅ Успешно оплачен!")
                    # Можно добавить логику для обработки успешного платежа
        else:
            print(f"      ✅ Статус актуален: {real_status}")
    
    print(f"\n✅ Синхронизация завершена. Обновлено платежей: {updated_count}")
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python sync_payment_statuses.py <username>")
        print("  python sync_payment_statuses.py --user-id <user_id>")
        print("\nПримеры:")
        print("  python sync_payment_statuses.py NikitaRoshchin")
        print("  python sync_payment_statuses.py --user-id 724281972")
        sys.exit(1)
    
    if sys.argv[1] == '--user-id' and len(sys.argv) > 2:
        user_id = int(sys.argv[2])
        sync_payments_for_user(user_id=user_id)
    else:
        username = sys.argv[1]
        sync_payments_for_user(username=username)






