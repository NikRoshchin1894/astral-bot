#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки платежей конкретного пользователя
"""

import sqlite3
import json
import sys
import os
from datetime import datetime
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# База данных
DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
DATABASE = 'users.db'

def get_db_connection():
    """Получает соединение с базой данных (PostgreSQL или SQLite)"""
    if DATABASE_URL:
        try:
            result = urlparse(DATABASE_URL)
            print(f"🔌 Подключение к PostgreSQL: {result.hostname}:{result.port}/{result.path[1:]}")
            conn = psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port,
                connect_timeout=10
            )
            print("✅ Подключение к PostgreSQL установлено")
            return conn, 'postgresql'
        except Exception as e:
            print(f"❌ Ошибка подключения к PostgreSQL: {e}")
            print("Используем локальный SQLite...")
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        print("⚠️ DATABASE_URL не установлена, используем локальный SQLite")
        return sqlite3.connect(DATABASE), 'sqlite'


def find_user_by_username(username, db_type, cursor):
    """Находит пользователя по username"""
    if not username:
        return None
    
    # Убираем @ если есть
    username = username.lstrip('@')
    
    if db_type == 'postgresql':
        cursor.execute('SELECT * FROM users WHERE username = %s OR username = %s', (username, f'@{username}'))
    else:
        cursor.execute('SELECT * FROM users WHERE username = ? OR username = ?', (username, f'@{username}'))
    
    row = cursor.fetchone()
    if not row:
        return None
    
    if db_type == 'postgresql':
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    else:
        columns = ['user_id', 'first_name', 'last_name', 'country', 'city', 
                   'birth_date', 'birth_time', 'updated_at', 'has_paid', 'birth_place', 'username']
        return dict(zip(columns, row))


def get_user_payments(user_id, db_type, cursor):
    """Получает все платежи пользователя"""
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT id, yookassa_payment_id, internal_payment_id, amount, status, 
                   created_at, updated_at
            FROM payments 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT id, yookassa_payment_id, internal_payment_id, amount, status, 
                   created_at, updated_at
            FROM payments 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        ''', (user_id,))
    
    if db_type == 'postgresql':
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    else:
        columns = ['id', 'yookassa_payment_id', 'internal_payment_id', 'amount', 'status', 
                   'created_at', 'updated_at']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_payment_events(user_id, db_type, cursor):
    """Получает события, связанные с платежами"""
    if db_type == 'postgresql':
        cursor.execute('''
            SELECT id, event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = %s 
            AND event_type IN ('payment_start', 'payment_success', 'payment_error', 
                               'payment_canceled', 'payment_cancel_return')
            ORDER BY timestamp DESC
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT id, event_type, event_data, timestamp 
            FROM events 
            WHERE user_id = ? 
            AND event_type IN ('payment_start', 'payment_success', 'payment_error', 
                               'payment_canceled', 'payment_cancel_return')
            ORDER BY timestamp DESC
        ''', (user_id,))
    
    return cursor.fetchall()


def format_event_data(event_data_str):
    """Форматирует JSON данные события"""
    if not event_data_str:
        return "Нет данных"
    try:
        data = json.loads(event_data_str) if isinstance(event_data_str, str) else event_data_str
        return json.dumps(data, ensure_ascii=False, indent=2)
    except:
        return str(event_data_str)


def check_user_payment(username):
    """Проверяет платежи пользователя"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    # Находим пользователя
    user_data = find_user_by_username(username, db_type, cursor)
    
    if not user_data:
        print(f"\n❌ Пользователь '{username}' не найден в базе данных")
        conn.close()
        return
    
    user_id = user_data.get('user_id')
    print(f"\n{'='*80}")
    print(f"👤 ПОЛЬЗОВАТЕЛЬ: {user_data.get('first_name', 'N/A')} (@{username})")
    print(f"   ID: {user_id}")
    print(f"   Оплачено: {'✅ Да' if user_data.get('has_paid') else '❌ Нет'}")
    print(f"{'='*80}\n")
    
    # Получаем платежи
    payments = get_user_payments(user_id, db_type, cursor)
    
    print(f"💳 ПЛАТЕЖИ ({len(payments)}):")
    print("-" * 80)
    
    if not payments:
        print("   ❌ Платежей не найдено")
    else:
        for i, payment in enumerate(payments, 1):
            status = payment.get('status', 'unknown')
            status_icon = {
                'succeeded': '✅',
                'pending': '⏳',
                'canceled': '❌',
                'failed': '❌'
            }.get(status, '❓')
            
            print(f"\n   {i}. Платеж #{payment.get('id')}")
            print(f"      Статус: {status_icon} {status}")
            print(f"      Сумма: {payment.get('amount')} ₽")
            print(f"      YooKassa ID: {payment.get('yookassa_payment_id', 'N/A')}")
            print(f"      Внутренний ID: {payment.get('internal_payment_id', 'N/A')}")
            print(f"      Создан: {payment.get('created_at', 'N/A')}")
            print(f"      Обновлен: {payment.get('updated_at', 'N/A')}")
            
            # Если платеж отменен, пытаемся найти причину в событиях
            if status == 'canceled':
                print(f"      ⚠️ ПЛАТЕЖ ОТМЕНЕН - ищем причину...")
    
    # Получаем события платежей
    payment_events = get_payment_events(user_id, db_type, cursor)
    
    print(f"\n📋 СОБЫТИЯ ПЛАТЕЖЕЙ ({len(payment_events)}):")
    print("-" * 80)
    
    if not payment_events:
        print("   ❌ Событий платежей не найдено")
    else:
        for i, (event_id, event_type, event_data, timestamp) in enumerate(payment_events, 1):
            event_icon = {
                'payment_start': '🚀',
                'payment_success': '✅',
                'payment_error': '❌',
                'payment_canceled': '❌',
                'payment_cancel_return': '↩️'
            }.get(event_type, '📌')
            
            print(f"\n   {i}. {event_icon} {event_type}")
            print(f"      Время: {timestamp}")
            
            if event_data:
                try:
                    data = json.loads(event_data) if isinstance(event_data, str) else event_data
                    if isinstance(data, dict):
                        # Выводим важные поля
                        if 'cancel_reason' in data:
                            print(f"      ❌ Причина отмены: {data['cancel_reason']}")
                        if 'cancel_party' in data:
                            print(f"      👤 Инициатор отмены: {data['cancel_party']}")
                        if 'yookassa_payment_id' in data:
                            print(f"      💳 YooKassa ID: {data['yookassa_payment_id']}")
                        if 'error' in data:
                            print(f"      ⚠️ Ошибка: {data['error']}")
                        if 'amount' in data:
                            print(f"      💰 Сумма: {data['amount']} ₽")
                        
                        # Выводим все данные, если их немного
                        if len(str(data)) < 500:
                            print(f"      Данные:")
                            for key, value in data.items():
                                if key not in ['cancel_reason', 'cancel_party', 'yookassa_payment_id', 'error', 'amount']:
                                    print(f"         {key}: {value}")
                    else:
                        print(f"      Данные: {str(data)[:200]}")
                except Exception as e:
                    print(f"      Данные (не JSON): {str(event_data)[:200]}")
    
    # Анализ отмененных платежей
    canceled_payments = [p for p in payments if p.get('status') == 'canceled']
    if canceled_payments:
        print(f"\n🔍 АНАЛИЗ ОТМЕНЕННЫХ ПЛАТЕЖЕЙ:")
        print("-" * 80)
        for payment in canceled_payments:
            payment_id = payment.get('yookassa_payment_id')
            print(f"\n   Платеж {payment_id}:")
            
            # Ищем события отмены для этого платежа
            cancel_events = [e for e in payment_events 
                           if e[1] == 'payment_canceled' and 
                           (e[2] and payment_id in str(e[2]))]
            
            if cancel_events:
                for event_id, event_type, event_data, timestamp in cancel_events:
                    try:
                        data = json.loads(event_data) if isinstance(event_data, str) else event_data
                        if isinstance(data, dict):
                            cancel_reason = data.get('cancel_reason', 'unknown')
                            cancel_party = data.get('cancel_party', 'unknown')
                            
                            reason_messages = {
                                '3d_secure_failed': 'Ошибка 3D Secure аутентификации',
                                'call_issuer': 'Банк отклонил платеж',
                                'canceled_by_merchant': 'Платеж отменен магазином',
                                'expired_on_confirmation': 'Время на оплату истекло',
                                'expired_on_capture': 'Время на подтверждение платежа истекло',
                                'fraud_suspected': 'Подозрение в мошенничестве',
                                'insufficient_funds': 'Недостаточно средств на карте',
                                'invalid_csc': 'Неверный CVV/CVC код',
                                'invalid_card_number': 'Неверный номер карты',
                                'invalid_cardholder_name': 'Неверное имя держателя карты',
                                'issuer_unavailable': 'Банк-эмитент недоступен',
                                'payment_method_limit_exceeded': 'Превышен лимит по способу оплаты',
                                'payment_method_restricted': 'Способ оплаты недоступен',
                                'permission_revoked': 'Разрешение на платеж отозвано',
                                'unsupported_mobile_operator': 'Мобильный оператор не поддерживается'
                            }
                            
                            reason_text = reason_messages.get(cancel_reason, cancel_reason)
                            print(f"      ❌ Причина: {reason_text}")
                            print(f"      👤 Инициатор: {cancel_party}")
                            print(f"      ⏰ Время: {timestamp}")
                    except:
                        pass
            else:
                print(f"      ⚠️ События отмены не найдены в логах")
                print(f"      💡 Возможные причины:")
                print(f"         - Пользователь отменил платеж на странице YooKassa")
                print(f"         - Истекло время на оплату")
                print(f"         - Банк отклонил платеж")
    
    print(f"\n{'='*80}\n")
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python check_user_payment.py <username>")
        print("\nПримеры:")
        print("  python check_user_payment.py NikitaRoshchin")
        print("  python check_user_payment.py @NikitaRoshchin")
        sys.exit(1)
    
    username = sys.argv[1].lstrip('@')
    try:
        check_user_payment(username)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)






