#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт миграции: добавление колонки username в таблицу users
"""

import os
import sys
from urllib.parse import urlparse
import psycopg2
import sqlite3
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
            print(f"Ошибка подключения к PostgreSQL: {e}, используем SQLite")
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        return sqlite3.connect(DATABASE), 'sqlite'

def migrate():
    """Добавляет колонку username если её нет"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if db_type == 'postgresql':
            # Проверяем, существует ли колонка
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='username'
            """)
            if not cursor.fetchone():
                print("Добавляем колонку username в PostgreSQL...")
                cursor.execute('ALTER TABLE users ADD COLUMN username TEXT')
                conn.commit()
                print("✅ Колонка username добавлена в PostgreSQL")
            else:
                print("✅ Колонка username уже существует в PostgreSQL")
        else:
            # SQLite
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN username TEXT')
                conn.commit()
                print("✅ Колонка username добавлена в SQLite")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print("✅ Колонка username уже существует в SQLite")
                else:
                    raise
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    print("🔄 Запуск миграции: добавление колонки username...")
    migrate()
    print("✅ Миграция завершена!")

