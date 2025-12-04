#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки подключения к базе данных
Запуск: python check_db_connection.py
"""

import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Импортируем функции из bot.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot import get_db_connection, init_db

def check_database_connection():
    """Проверяет подключение к базе данных"""
    print("=" * 60)
    print("🔍 ПРОВЕРКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ")
    print("=" * 60)
    print()
    
    # Проверяем переменные окружения
    database_url = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
    
    if database_url:
        print(f"✅ Переменная DATABASE_PUBLIC_URL найдена")
        print(f"   Первые 50 символов: {database_url[:50]}...")
        print()
        
        # Пытаемся подключиться
        try:
            print("📡 Попытка подключения к базе данных...")
            conn, db_type = get_db_connection()
            
            if db_type == 'postgresql':
                print("✅ Успешное подключение к PostgreSQL!")
                print()
                
                # Проверяем версию PostgreSQL
                cursor = conn.cursor()
                cursor.execute('SELECT version();')
                version = cursor.fetchone()[0]
                print(f"📋 Версия PostgreSQL: {version[:50]}...")
                print()
                
                # Проверяем существующие таблицы
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name;
                """)
                tables = cursor.fetchall()
                print(f"📊 Найдено таблиц: {len(tables)}")
                if tables:
                    print("   Таблицы:")
                    for table in tables:
                        print(f"   - {table[0]}")
                print()
                
                # Проверяем количество пользователей
                try:
                    cursor.execute('SELECT COUNT(*) FROM users;')
                    user_count = cursor.fetchone()[0]
                    print(f"👥 Пользователей в базе: {user_count}")
                except Exception as e:
                    print(f"⚠️  Таблица users еще не создана: {e}")
                print()
                
            else:
                print("✅ Успешное подключение к SQLite!")
                print(f"   Файл базы данных: users.db")
                print()
                
                # Проверяем таблицы в SQLite
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                print(f"📊 Найдено таблиц: {len(tables)}")
                if tables:
                    print("   Таблицы:")
                    for table in tables:
                        print(f"   - {table[0]}")
                print()
            
            conn.close()
            print("=" * 60)
            print("✅ ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ РАБОТАЕТ")
            print("=" * 60)
            return True
            
        except Exception as e:
            print("=" * 60)
            print("❌ ОШИБКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ")
            print("=" * 60)
            print(f"   Тип ошибки: {type(e).__name__}")
            print(f"   Сообщение: {str(e)}")
            print()
            print("💡 Возможные причины:")
            print("   1. Неверная строка подключения DATABASE_PUBLIC_URL")
            print("   2. База данных не запущена в Timeweb Cloud")
            print("   3. Неверные учетные данные (пользователь, пароль)")
            print("   4. Проблемы с сетью или firewall")
            print("   5. Неверный хост или порт")
            print()
            return False
    else:
        print("⚠️  DATABASE_PUBLIC_URL или DATABASE_URL не найдены")
        print("   Будет использоваться SQLite (users.db)")
        print()
        
        # Проверяем SQLite
        try:
            conn, db_type = get_db_connection()
            print(f"✅ SQLite работает, тип: {db_type}")
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Ошибка SQLite: {e}")
            return False

def initialize_database():
    """Инициализирует базу данных (создает таблицы)"""
    print()
    print("=" * 60)
    print("🔧 ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
    print("=" * 60)
    print()
    
    try:
        init_db()
        print("✅ База данных успешно инициализирована!")
        print("   Все необходимые таблицы созданы")
        return True
    except Exception as e:
        print("❌ Ошибка при инициализации базы данных:")
        print(f"   {type(e).__name__}: {str(e)}")
        return False

if __name__ == '__main__':
    # Проверяем подключение
    connection_ok = check_database_connection()
    
    if connection_ok:
        # Инициализируем базу данных (если нужно)
        print()
        response = input("Инициализировать базу данных? (создать таблицы) [y/N]: ")
        if response.lower() in ['y', 'yes', 'да']:
            initialize_database()
    else:
        print()
        print("⚠️  Не удалось подключиться к базе данных.")
        print("   Проверьте настройки в переменных окружения.")
        sys.exit(1)

