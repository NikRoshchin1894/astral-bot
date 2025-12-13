#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для удаления данных о рождении у пользователя, чтобы он выглядел как новый
"""

import os
import sys
from urllib.parse import urlparse
import psycopg2
import sqlite3
from dotenv import load_dotenv
from datetime import datetime

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

def clear_birth_data(username_or_user_id):
    """Удаляет данные о рождении у пользователя"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    # Определяем, это user_id или username
    user_id = None
    username = None
    
    try:
        user_id = int(username_or_user_id)
    except ValueError:
        username = username_or_user_id.lstrip('@')
    
    # Ищем пользователя
    if user_id:
        if db_type == 'postgresql':
            cursor.execute('SELECT user_id, username, first_name FROM users WHERE user_id = %s', (user_id,))
        else:
            cursor.execute('SELECT user_id, username, first_name FROM users WHERE user_id = ?', (user_id,))
    else:
        if db_type == 'postgresql':
            cursor.execute('SELECT user_id, username, first_name FROM users WHERE username = %s OR username = %s', 
                         (username, f'@{username}'))
        else:
            cursor.execute('SELECT user_id, username, first_name FROM users WHERE username = ? OR username = ?', 
                         (username, f'@{username}'))
    
    user = cursor.fetchone()
    
    if not user:
        print(f"❌ Пользователь '{username_or_user_id}' не найден в базе данных")
        conn.close()
        return False
    
    found_user_id = user[0]
    found_username = user[1]
    found_name = user[2]
    
    print(f"Найден пользователь:")
    print(f"  User ID: {found_user_id}")
    print(f"  Username: {found_username}")
    print(f"  Имя: {found_name}")
    
    # Удаляем данные о рождении
    if db_type == 'postgresql':
        cursor.execute('''
            UPDATE users 
            SET birth_date = NULL,
                birth_time = NULL,
                birth_place = NULL,
                city = NULL,
                country = NULL,
                has_paid = 0,
                updated_at = NOW()
            WHERE user_id = %s
        ''', (found_user_id,))
    else:
        cursor.execute('''
            UPDATE users 
            SET birth_date = NULL,
                birth_time = NULL,
                birth_place = NULL,
                city = NULL,
                country = NULL,
                has_paid = 0,
                updated_at = ?
            WHERE user_id = ?
        ''', (datetime.now().isoformat(), found_user_id))
    
    conn.commit()
    
    print(f"\n✅ Данные о рождении удалены. Пользователь теперь как новый (без заполненного профиля).")
    
    conn.close()
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python clear_birth_data.py <username>     - удалить данные о рождении по username")
        print("  python clear_birth_data.py <user_id>     - удалить данные о рождении по user_id")
        print("\nПримеры:")
        print("  python clear_birth_data.py NikitaRoshchin")
        print("  python clear_birth_data.py 724281972")
        sys.exit(1)
    
    try:
        clear_birth_data(sys.argv[1])
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

