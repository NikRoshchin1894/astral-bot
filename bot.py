#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Astral Bot - Astrology Telegram Bot
Астрологический бот для консультаций и получения информации о знаках зодиака
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import time
import uuid
import threading
import queue
import signal
import atexit
from datetime import datetime
from typing import Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Bot
from telegram.error import Conflict, BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    PreCheckoutQueryHandler,
    TypeHandler
)
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from aiohttp import web
import hmac
import hashlib
from openai import OpenAI
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, PageTemplate, BaseDocTemplate, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, Color, black, white
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
import random
import sqlite3
import sys
import swisseph as swe
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from datetime import datetime, timezone, timedelta
import pytz

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования (должно быть до использования logger)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# База данных
# Используем PostgreSQL на Railway, SQLite локально
# Приоритет: сначала DATABASE_PUBLIC_URL, потом DATABASE_URL (для обратной совместимости)
DATABASE_URL = os.getenv('DATABASE_PUBLIC_URL') or os.getenv('DATABASE_URL')
DATABASE = 'users.db'  # Для SQLite локально

# Логируем состояние DATABASE_URL при запуске
if DATABASE_URL:
    logger.info(f"✅ База данных найдена (первые 20 символов: {DATABASE_URL[:20]}...)")
    if os.getenv('DATABASE_PUBLIC_URL'):
        logger.info("Используется DATABASE_PUBLIC_URL")
    elif os.getenv('DATABASE_URL'):
        logger.info("Используется DATABASE_URL")
else:
    logger.warning("⚠️ DATABASE_PUBLIC_URL и DATABASE_URL не найдены в переменных окружения! Используется SQLite.")

def get_db_connection():
    """Получает соединение с базой данных (PostgreSQL или SQLite)"""
    if DATABASE_URL:
        # Используем PostgreSQL на Railway
        # Railway предоставляет DATABASE_URL в формате: postgresql://user:password@host:port/dbname
        try:
            result = urlparse(DATABASE_URL)
            logger.info(f"Подключение к PostgreSQL: {result.hostname}:{result.port}/{result.path[1:]}")
            conn = psycopg2.connect(
                database=result.path[1:],  # Убираем первый слэш
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port
            )
            logger.info("✅ Подключение к PostgreSQL установлено")
            return conn, 'postgresql'
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}, используем SQLite", exc_info=True)
            return sqlite3.connect(DATABASE), 'sqlite'
    else:
        # Используем SQLite локально
        logger.info("DATABASE_URL не установлена, используем SQLite")
        return sqlite3.connect(DATABASE), 'sqlite'

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Словарь для хранения активных генераций натальных карт
# Формат: {user_id: {'chat_id': int, 'message_id': int, 'birth_data': dict}}
active_generations = {}

PROMPT_EXAMPLE_PATH = os.getenv('PROMPT_EXAMPLE_PATH', os.path.join('prompt_examples', 'ideal_example.md'))

def load_prompt_example() -> str:
    """Загружает внешний пример идеального ответа, если файл существует."""
    try:
        candidates = []
        # 1) Явно заданный путь через переменную окружения или дефолт в папке проекта
        if PROMPT_EXAMPLE_PATH:
            candidates.append(PROMPT_EXAMPLE_PATH)
        # 2) Файл txt_example, который пользователь указал (внутри проекта)
        project_txt_example = os.path.join(os.path.dirname(__file__), 'venv', 'share', 'man', 'man1', 'txt_example')
        candidates.append(project_txt_example)
        # 3) Абсолютный путь к txt_example (на случай запуска из другого cwd)
        candidates.append('/Users/nsroschin/Documents/Astral_Bot/venv/share/man/man1/txt_example')

        for path in candidates:
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return "\n\nПример идеального ответа (ориентир по стилю; не копировать дословно):\n\n" + content
    except Exception as err:
        logger.warning(f"Не удалось загрузить пример промпта: {err}")
    return ""

def _split_example_by_sections(example_text: str) -> dict:
    """
    Делит пример на блоки по разделам. Возвращает словарь с ключами:
      '1', '2', ..., '7' и агрегированные '1-3', '4-5', '6-7'.
    Если структура не найдена, возвращает пустой словарь.
    """
    if not example_text:
        return {}
    import re
    lines = example_text.splitlines()
    section_re = re.compile(r'^\s*Раздел\s+(\d+)\b', re.IGNORECASE)
    current = None
    buckets = {str(i): [] for i in range(1, 8)}
    for raw in lines:
        m = section_re.match(raw.strip())
        if m:
            num = m.group(1)
            if num in buckets:
                current = num
            else:
                current = None
            # Всегда добавляем заголовок раздела в соответствующий бакет
            if current:
                buckets[current].append(raw)
            continue
        if current:
            buckets[current].append(raw)
    # Сформируем агрегаты
    def join_bucket(keys):
        parts = []
        for k in keys:
            chunk = "\n".join(buckets.get(k, [])).strip()
            if chunk:
                parts.append(chunk)
        return "\n\n".join(parts).strip()
    agg = {}
    # Индивидуальные
    for i in range(1, 8):
        joined = join_bucket([str(i)])
        if joined:
            agg[str(i)] = joined
    # Группы
    j13 = join_bucket(["1", "2", "3"])
    j45 = join_bucket(["4", "5"])
    j67 = join_bucket(["6", "7"])
    if j13:
        agg["1-3"] = j13
    if j45:
        agg["4-5"] = j45
    if j67:
        agg["6-7"] = j67
    return agg

def init_db():
    """Инициализация базы данных"""
    try:
        conn, db_type = get_db_connection()
        logger.info(f"Подключение к БД установлено: {db_type}")
        cursor = conn.cursor()
        
        if db_type == 'postgresql':
            # PostgreSQL схемы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    country TEXT,
                    city TEXT,
                    birth_date TEXT,
                    birth_time TEXT,
                    updated_at TEXT,
                    has_paid INTEGER DEFAULT 0,
                    birth_place TEXT
                )
            ''')
            
            # Проверяем и добавляем birth_place если его нет
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='birth_place'")
                if not cursor.fetchone():
                    cursor.execute('ALTER TABLE users ADD COLUMN birth_place TEXT')
            except Exception as e:
                logger.warning(f"Ошибка при проверке столбца birth_place: {e}")
            
            # Проверяем и добавляем has_paid если его нет
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='has_paid'")
                if not cursor.fetchone():
                    cursor.execute('ALTER TABLE users ADD COLUMN has_paid INTEGER DEFAULT 0')
            except Exception as e:
                logger.warning(f"Ошибка при проверке столбца has_paid: {e}")
            
            # Проверяем и добавляем username если его нет
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='username'")
                if not cursor.fetchone():
                    cursor.execute('ALTER TABLE users ADD COLUMN username TEXT')
            except Exception as e:
                logger.warning(f"Ошибка при проверке столбца username: {e}")
            
            # Таблица для аналитики событий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица для платежей (ЮKassa)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    yookassa_payment_id TEXT UNIQUE,
                    internal_payment_id TEXT UNIQUE,
                    amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
        else:
            # SQLite схемы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    country TEXT,
                    city TEXT,
                    birth_date TEXT,
                    birth_time TEXT,
                    updated_at TEXT,
                    has_paid INTEGER DEFAULT 0
                )
            ''')
            
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN has_paid INTEGER DEFAULT 0')
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN birth_place TEXT')
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN username TEXT')
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Таблица для аналитики событий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица для платежей (ЮKassa)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    yookassa_payment_id TEXT UNIQUE,
                    internal_payment_id TEXT UNIQUE,
                    amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
        
        # Индексы (одинаковые для обеих БД)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
        
        conn.commit()
        logger.info(f"Таблицы созданы успешно для БД типа: {db_type}")
        
        # Проверяем, что таблицы действительно созданы
        if db_type == 'postgresql':
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            tables = cursor.fetchall()
            logger.info(f"Существующие таблицы в PostgreSQL: {[t[0] for t in tables]}")
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            logger.info(f"Существующие таблицы в SQLite: {[t[0] for t in tables]}")
        
        conn.close()
        logger.info(f"✅ База данных инициализирована ({db_type})")
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации базы данных: {e}", exc_info=True)
        raise


def save_user_profile(user_id, user_data):
    """Сохранение профиля пользователя в базу данных"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()

    # Сначала загружаем текущие данные пользователя, чтобы не потерять существующие поля
    if db_type == 'postgresql':
        cursor.execute('SELECT first_name, birth_date, birth_time, birth_place, has_paid FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        if row:
            current_data = {
                'first_name': row[0] or '',
                'birth_date': row[1] or '',
                'birth_time': row[2] or '',
                'birth_place': row[3] or '',
                'has_paid': row[4] or 0
            }
        else:
            current_data = {}
    else:
        # Для SQLite используем явный список колонок
        cursor.execute('SELECT first_name, birth_date, birth_time, birth_place, has_paid FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            current_data = {
                'first_name': row[0] or '',
                'birth_date': row[1] or '',
                'birth_time': row[2] or '',
                'birth_place': row[3] or '',
                'has_paid': row[4] or 0
            }
        else:
            current_data = {}

    # Объединяем текущие данные с новыми (новые данные имеют приоритет)
    # Обновляем только те поля, которые переданы в user_data
    merged_data = {
        'first_name': user_data.get('birth_name') if 'birth_name' in user_data else current_data.get('first_name', ''),
        'birth_date': user_data.get('birth_date') if 'birth_date' in user_data else current_data.get('birth_date', ''),
        'birth_time': user_data.get('birth_time') if 'birth_time' in user_data else current_data.get('birth_time', ''),
        'birth_place': user_data.get('birth_place') if 'birth_place' in user_data else current_data.get('birth_place', ''),
        'has_paid': current_data.get('has_paid', 0)
    }

    # Обрабатываем место рождения (разделяем на city и country)
    birth_place = merged_data.get('birth_place', '')
    if ',' in birth_place:
        parts = birth_place.split(',')
        city = parts[0].strip()
        country = ','.join(parts[1:]).strip() if len(parts) > 1 else ''
    else:
        city = birth_place
        country = ''

    # Сохраняем профиль (не трогаем username, он обновляется отдельно через save_user_username)
    if db_type == 'postgresql':
        cursor.execute('''
            INSERT INTO users 
            (user_id, first_name, country, city, birth_date, birth_time, birth_place, has_paid, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                country = EXCLUDED.country,
                city = EXCLUDED.city,
                birth_date = EXCLUDED.birth_date,
                birth_time = EXCLUDED.birth_time,
                birth_place = EXCLUDED.birth_place,
                updated_at = EXCLUDED.updated_at
        ''', (
            user_id,
            merged_data['first_name'],
            country,
            city,
            merged_data['birth_date'],
            merged_data['birth_time'],
            birth_place,
            merged_data['has_paid'],
            datetime.now().isoformat()
        ))
    else:
        cursor.execute('''
            INSERT INTO users 
            (user_id, first_name, country, city, birth_date, birth_time, birth_place, has_paid, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                country = excluded.country,
                city = excluded.city,
                birth_date = excluded.birth_date,
                birth_time = excluded.birth_time,
                birth_place = excluded.birth_place,
                updated_at = excluded.updated_at
        ''', (
            user_id,
            merged_data['first_name'],
            country,
            city,
            merged_data['birth_date'],
            merged_data['birth_time'],
            birth_place,
            merged_data['has_paid'],
            datetime.now().isoformat()
        ))
    conn.commit()
    conn.close()
    
    # Логируем сохранение профиля
    log_event(user_id, 'profile_saved', {
        'has_birth_name': bool(user_data.get('birth_name')),
        'has_birth_date': bool(user_data.get('birth_date')),
        'has_birth_time': bool(user_data.get('birth_time')),
        'has_birth_place': bool(user_data.get('birth_place')),
        'is_complete': all(key in user_data for key in ['birth_name', 'birth_date', 'birth_time', 'birth_place'])
    })


def is_profile_complete(user_data_or_profile):
    """
    Проверяет, заполнен ли профиль пользователя полностью.
    
    Args:
        user_data_or_profile: dict с данными профиля (может быть user_data или результат load_user_profile)
    
    Returns:
        bool: True если все необходимые поля заполнены и не пустые
    """
    if not user_data_or_profile:
        return False
    
    required_fields = ['birth_name', 'birth_date', 'birth_time', 'birth_place']
    for field in required_fields:
        value = user_data_or_profile.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            return False
    return True


def load_user_profile(user_id):
    """Загрузка профиля пользователя из базы данных"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    if db_type == 'postgresql':
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
        else:
            result = None
    else:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            columns = ['user_id', 'first_name', 'last_name', 'country', 'city', 
                       'birth_date', 'birth_time', 'updated_at', 'has_paid', 'birth_place']
            result = dict(zip(columns, row))
        else:
            result = None
    
    conn.close()
    
    if result:
        user_data = {}
        if result.get('first_name'):
            user_data['birth_name'] = result['first_name']
        if result.get('birth_date'):
            user_data['birth_date'] = result['birth_date']
        if result.get('birth_time'):
            user_data['birth_time'] = result['birth_time']
        
        # Используем birth_place если есть, иначе собираем из city и country
        if result.get('birth_place'):
            user_data['birth_place'] = result['birth_place']
        elif result.get('city') and result.get('country'):
            user_data['birth_place'] = f"{result['city']}, {result['country']}"
        elif result.get('city'):
            user_data['birth_place'] = result['city']
        
        if result.get('has_paid'):
            user_data['has_paid'] = bool(result['has_paid'])
        return user_data
    return {}


def log_event(user_id: int, event_type: str, event_data: Optional[dict] = None):
    """
    Логирует событие в базу данных для аналитики.
    
    Args:
        user_id: ID пользователя Telegram
        event_type: Тип события (например: 'start', 'button_click', 'payment', 'natal_chart_request')
        event_data: Дополнительные данные события в формате словаря (будут сохранены как JSON)
    """
    # Проверяем валидность входных данных
    if not user_id:
        logger.warning(f"⚠️ Попытка залогировать событие {event_type} без user_id")
        return
    
    if not event_type:
        logger.warning(f"⚠️ Попытка залогировать событие без типа для user_id {user_id}")
        return
    
    try:
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        
        # Сериализуем event_data в JSON
        try:
            data_json = json.dumps(event_data, ensure_ascii=False) if event_data else None
        except (TypeError, ValueError) as json_error:
            logger.warning(f"⚠️ Не удалось сериализовать event_data для события {event_type}: {json_error}")
            data_json = json.dumps({'error': 'serialization_failed', 'original_error': str(json_error)})
        
        timestamp = datetime.now().isoformat()
        
        if db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO events (user_id, event_type, event_data, timestamp)
                VALUES (%s, %s, %s, %s)
            ''', (
                user_id,
                event_type,
                data_json,
                timestamp
            ))
        else:
            cursor.execute('''
                INSERT INTO events (user_id, event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (
                user_id,
                event_type,
                data_json,
                timestamp
            ))
        conn.commit()
        conn.close()
        logger.debug(f"📊 Event logged: {event_type} for user {user_id}")
    except Exception as e:
        # Детальное логирование ошибки для отладки
        logger.error(f"❌ Failed to log event {event_type} for user {user_id}: {e}", exc_info=True)
        # Не прерываем выполнение - логирование событий не критично для работы бота


# Никнеймы с бесплатной генерацией (не списываем плату)
FREE_GENERATION_USERNAMES = {'nina_swan'}


def user_has_paid(user_id: int) -> bool:
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    if db_type == 'postgresql':
        cursor.execute('SELECT has_paid, username FROM users WHERE user_id = %s', (user_id,))
    else:
        cursor.execute('SELECT has_paid, username FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False
    has_paid, username = row[0], (row[1] or '').strip()
    if username and username.lstrip('@').lower() in FREE_GENERATION_USERNAMES:
        return True
    return bool(has_paid)


def mark_user_paid(user_id: int):
    """Помечает пользователя как оплатившего"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if db_type == 'postgresql':
            # Используем CURRENT_TIMESTAMP для PostgreSQL
            cursor.execute('''
                UPDATE users
                SET has_paid = 1, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            ''', (user_id,))
            # Если пользователя нет, создаем запись
            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO users (user_id, has_paid, updated_at)
                    VALUES (%s, 1, CURRENT_TIMESTAMP)
                ''', (user_id,))
        else:
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE users
                SET has_paid = 1, updated_at = ?
                WHERE user_id = ?
            ''', (now, user_id))
            # Если пользователя нет, создаем запись
            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO users (user_id, has_paid, updated_at)
                    VALUES (?, 1, ?)
                ''', (user_id, now))
        
        conn.commit()
        logger.info(f"✅ Пользователь {user_id} помечен как оплативший")
    except Exception as e:
        logger.error(f"❌ Ошибка при пометке пользователя как оплатившего: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()


def save_user_username(user_id: int, username: Optional[str], first_name: Optional[str]):
    """Сохраняет username и first_name пользователя в базу данных.
    ВАЖНО: Не перезаписывает first_name, если оно уже заполнено пользователем (birth_name)"""
    try:
        if not username and not first_name:
            return  # Нет данных для сохранения
        
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        # Проверяем, есть ли уже заполненный профиль
        # Если first_name уже заполнено пользователем (birth_name), не перезаписываем его
        if db_type == 'postgresql':
            cursor.execute('SELECT first_name FROM users WHERE user_id = %s', (user_id,))
        else:
            cursor.execute('SELECT first_name FROM users WHERE user_id = ?', (user_id,))
        
        existing_row = cursor.fetchone()
        existing_first_name = existing_row[0] if existing_row and existing_row[0] else None
        
        # Если first_name уже заполнено (пользователь ввел birth_name), не перезаписываем его
        # Сохраняем только username и обновляем updated_at
        if existing_first_name and existing_first_name.strip():
            # Пользователь уже заполнил имя, сохраняем только username
            if db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO users (user_id, username, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = COALESCE(EXCLUDED.username, users.username),
                        updated_at = EXCLUDED.updated_at
                ''', (user_id, username, now))
            else:
                cursor.execute('''
                    INSERT INTO users (user_id, username, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = COALESCE(excluded.username, users.username),
                        updated_at = excluded.updated_at
                ''', (user_id, username, now))
        else:
            # Имени еще нет, можем сохранить first_name из Telegram (как начальное значение)
            if db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = COALESCE(EXCLUDED.username, users.username),
                        first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                        updated_at = EXCLUDED.updated_at
                ''', (user_id, username, first_name, now))
            else:
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = COALESCE(excluded.username, users.username),
                        first_name = COALESCE(excluded.first_name, users.first_name),
                        updated_at = excluded.updated_at
                ''', (user_id, username, first_name, now))
        
        conn.commit()
        conn.close()
    except Exception as e:
        # Логируем ошибку, но не прерываем выполнение команды /start
        logger.warning(f"Не удалось сохранить username для пользователя {user_id}: {e}")


def reset_user_payment(user_id: int):
    """Сбрасывает статус оплаты после выдачи натальной карты."""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    if db_type == 'postgresql':
        cursor.execute('''
            INSERT INTO users (user_id, has_paid, updated_at)
            VALUES (%s, 0, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                has_paid = 0,
                updated_at = EXCLUDED.updated_at
        ''', (user_id, now))
    else:
        cursor.execute('''
            INSERT INTO users (user_id, has_paid, updated_at)
            VALUES (?, 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                has_paid = 0,
                updated_at = excluded.updated_at
        ''', (user_id, now))
    conn.commit()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    logger.info("🔵 ФУНКЦИЯ start() ВЫЗВАНА!")
    user = update.effective_user
    user_id = user.id
    logger.info(f"🔵 Обработка команды /start для пользователя {user_id} (username: {user.username})")
    
    # Сохраняем username в базу данных
    save_user_username(user_id, user.username, user.first_name)
    
    # Проверяем параметры команды /start (например, /start payment_success)
    start_param = None
    if context.args and len(context.args) > 0:
        start_param = context.args[0]
    
    # ПРИМЕЧАНИЕ: return_url теперь открывает бота без параметров.
    # Генерация натальной карты запускается автоматически через webhook YooKassa.
    # Эта логика оставлена для совместимости, если пользователь перейдет по ссылке с параметрами вручную.
    if start_param in ['payment_success', 'payment_cancel']:
        logger.info(f"🔍 Пользователь {user_id} вернулся после оплаты (start_param={start_param}), проверяем статус платежа")
        
        # Проверяем статус последнего платежа в базе и обрабатываем его
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Получаем информацию о последнем платеже
            if db_type == 'postgresql':
                cursor.execute('''
                    SELECT yookassa_payment_id, status, created_at
                    FROM payments
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (user_id,))
            else:
                cursor.execute('''
                    SELECT yookassa_payment_id, status, created_at
                    FROM payments
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (user_id,))
            
            payment_info = cursor.fetchone()
            
            if payment_info:
                payment_id = payment_info[0]
                payment_status = payment_info[1]
                logger.info(f"🔍 Найден платеж {payment_id} со статусом '{payment_status}' для пользователя {user_id}")
                
                # Если платеж успешен, обрабатываем его
                if payment_status == 'succeeded':
                    logger.info(f"✅ Платеж {payment_id} успешен в базе, запускаем генерацию натальной карты")
                    conn.close()
                    
                    # Проверяем, есть ли профиль пользователя
                    user_data = context.user_data
                    if not user_data.get('birth_name'):
                        loaded_data = load_user_profile(user_id)
                        if loaded_data:
                            user_data.update(loaded_data)
                    
                    has_profile = is_profile_complete(user_data)
                    
                    if has_profile:
                        # Профиль заполнен - запускаем генерацию сразу
                        logger.info(f"✅ Профиль пользователя {user_id} заполнен, запускаем генерацию натальной карты")
                        await handle_natal_chart_request_from_payment(user_id, context)
                        return
                    else:
                        # Профиль не заполнен - показываем сообщение с кнопкой для заполнения
                        await update.message.reply_text(
                            "✅ *Оплата получена!*\n\n"
                            "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
                            "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта.",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                            ]]),
                            parse_mode='Markdown'
                        )
                        return
                
                # Если платеж pending или canceled, проверяем через API
                elif payment_status in ['pending', 'canceled']:
                    logger.info(f"🔍 Платеж {payment_id} в статусе {payment_status}, проверяем через API")
                    conn.close()
                    try:
                        payment_info_api = await check_yookassa_payment_status(payment_id)
                        if payment_info_api:
                            api_status = payment_info_api.get('status', payment_status)
                            logger.info(f"🔍 Статус платежа через API: {api_status}")
                            
                            if api_status == 'succeeded':
                                logger.info(f"✅ Платеж {payment_id} успешен при проверке через API, запускаем генерацию натальной карты")
                                update_payment_status(payment_id, 'succeeded', payment_info_api)
                                mark_user_paid(user_id)
                                
                                # Проверяем, есть ли профиль пользователя
                                user_data = context.user_data
                                if not user_data.get('birth_name'):
                                    loaded_data = load_user_profile(user_id)
                                    if loaded_data:
                                        user_data.update(loaded_data)
                                
                                has_profile = is_profile_complete(user_data)
                                
                                if has_profile:
                                    # Профиль заполнен - запускаем генерацию сразу
                                    logger.info(f"✅ Профиль пользователя {user_id} заполнен, запускаем генерацию натальной карты")
                                    await handle_natal_chart_request_from_payment(user_id, context)
                                    return
                                else:
                                    # Профиль не заполнен - показываем сообщение с кнопкой для заполнения
                                    await update.message.reply_text(
                                        "✅ *Оплата получена!*\n\n"
                                        "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
                                        "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта.",
                                        reply_markup=InlineKeyboardMarkup([[
                                            InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                                        ]]),
                                        parse_mode='Markdown'
                                    )
                                    return
                            elif api_status == 'canceled':
                                # Платеж был отменен
                                cancellation_details = payment_info_api.get('cancellation_details', {})
                                cancel_reason = cancellation_details.get('reason', '')
                                
                                reason_messages = {
                                    '3d_secure_failed': 'Ошибка 3D Secure аутентификации',
                                    'call_issuer': 'Банк отклонил платеж. Обратитесь в банк для уточнения причины.',
                                    'canceled_by_merchant': 'Платеж отменен магазином',
                                    'expired_on_confirmation': 'Время на оплату истекло',
                                    'expired_on_capture': 'Время на подтверждение платежа истекло',
                                    'fraud_suspected': 'Платеж отклонен из-за подозрения в мошенничестве',
                                    'insufficient_funds': 'Недостаточно средств на карте',
                                    'invalid_csc': 'Неверный CVV/CVC код',
                                    'invalid_card_number': 'Неверный номер карты',
                                    'invalid_cardholder_name': 'Неверное имя держателя карты',
                                    'issuer_unavailable': 'Банк-эмитент недоступен. Попробуйте позже.',
                                    'payment_method_limit_exceeded': 'Превышен лимит по способу оплаты',
                                    'payment_method_restricted': 'Способ оплаты недоступен',
                                    'permission_revoked': 'Разрешение на платеж отозвано',
                                    'unsupported_mobile_operator': 'Мобильный оператор не поддерживается',
                                    'not_found': 'Платеж не был создан или был удален. Попробуйте создать новый платеж.'
                                }
                                
                                if cancel_reason and cancel_reason in reason_messages:
                                    cancel_message = f"❌ *Оплата отменена*\n\n*Причина:* {reason_messages[cancel_reason]}\n\n"
                                else:
                                    cancel_message = "❌ *Оплата отменена*\n\n*Причина:* Платеж не был создан или был отменен до начала оплаты.\n\n"
                                
                                cancel_message += "Вы можете попробовать оплатить позже или обратиться в поддержку, если проблема повторяется."
                                
                                await update.message.reply_text(
                                    cancel_message,
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("💳 Попробовать оплатить снова", callback_data='buy_natal_chart'),
                                        InlineKeyboardButton("💬 Поддержка", callback_data='support'),
                                        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                                    ]]),
                                    parse_mode='Markdown'
                                )
                                log_event(user_id, 'payment_cancel_return', {'start_param': start_param, 'cancel_reason': cancel_reason})
                                return
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось проверить статус платежа через API: {e}")
            
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при проверке статуса платежа: {e}")
            if 'conn' in locals():
                conn.close()
        
        # Если платеж не найден или не успешен, показываем соответствующее сообщение
        if start_param == 'payment_success':
            # Ожидался успешный платеж, но его нет
            await update.message.reply_text(
                "✅ *Оплата получена!*\n\n"
                "Обрабатываю платеж... Пожалуйста, подождите немного. "
                "Если натальная карта не начнет генерироваться автоматически, нажмите кнопку ниже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
                    InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                ]]),
                parse_mode='Markdown'
            )
            return
        elif start_param == 'payment_cancel':
            # Показываем сообщение об отмене только если платеж действительно отменен
            cancel_message = "❌ *Оплата отменена*\n\n"
            cancel_message += "Вы можете попробовать оплатить позже или обратиться в поддержку, если проблема повторяется."
            
            await update.message.reply_text(
                cancel_message,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Попробовать оплатить снова", callback_data='buy_natal_chart'),
                    InlineKeyboardButton("💬 Поддержка", callback_data='support'),
                    InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                ]]),
                parse_mode='Markdown'
            )
            log_event(user_id, 'payment_cancel_return', {'start_param': start_param})
            return
    
    
    # Логируем событие старта
    log_event(user_id, 'start', {
        'username': user.username,
        'first_name': user.first_name,
        'language_code': user.language_code,
        'start_param': start_param
    })
    
    # Приветственное сообщение для главного меню (после /start)
    welcome_message = '''*Я могу сделать для тебя расклад натальной карты* 🌙✨

*Натальная карта — это персональный астрологический код, который формируется в момент твоего рождения.*

Это не гадание и не общее описание знака зодиака — это точная система координат, показывающая твои врождённые качества, сильные стороны, таланты, задачи и закономерности судьбы.

*Почему это важно?*

Потому что натальная карта помогает разобраться в себе глубже, чем любые тесты личности.

*Хочешь узнать себя лучше?*

Продолжая пользоваться, ты принимаешь [Условия оферты и Политику обработки персональных данных.](https://bot-astral.website.yandexcloud.net/index.html)'''

    buttons = [
        InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
        InlineKeyboardButton("🪐 Астрологические данные", callback_data='planets_info'),
        InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
        InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support'),
    ]
    
    keyboard = InlineKeyboardMarkup([[b] for b in buttons])
    
    # Отправляем фото, если оно есть (для описания бота используйте /setdescription в BotFather)
    welcome_image_path = os.path.join(os.path.dirname(__file__), 'images', 'welcome.png')
    if os.path.exists(welcome_image_path):
        try:
            from telegram import InputFile
            with open(welcome_image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=welcome_message,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            return
        except Exception as e:
            logger.warning(f"Не удалось отправить фото приветствия: {e}")
    
    # Если фото нет или произошла ошибка, отправляем только текст
    await update.message.reply_text(
        welcome_message,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    help_text = '''*📚 Помощь по боту:*

*Основные команды:*
/start - Запустить бота
/help - Показать эту справку

*Возможности бота:*
📜 Персональная натальная карта
👤 Управление профилем

Просто используйте кнопки меню для навигации!'''
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
        [InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support')]
    ])
    
    await update.message.reply_text(help_text, reply_markup=keyboard, parse_mode='Markdown')


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /about - описание бота"""
    about_text = '''Привет! Я — Айла, создаю персональные астрологические разборы по дате рождения: натальные карты. Точные, глубокие и созданные для тех, кто хочет лучше понять себя.

Поддержка: @Astrolog_support'''
    
    await update.message.reply_text(about_text, parse_mode=None)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    # Проверяем, что есть callback_query
    if not update.callback_query:
        logger.error("❌ button_handler вызван без callback_query")
        return
    
    query = update.callback_query
    
    # Проверяем, что есть данные
    if not query.data:
        logger.error(f"❌ callback_query без data для пользователя {query.from_user.id if query.from_user else 'unknown'}")
        try:
            await query.answer("Ошибка: нет данных в запросе")
        except:
            pass
        return
    
    user_id = query.from_user.id if query.from_user else None
    data = query.data
    
    logger.info(f"🔘 Обработка нажатия кнопки: {data} от пользователя {user_id}")
    
    # Отвечаем на callback query как можно раньше
    # Обрабатываем ошибку, если query уже истек (старые запросы)
    try:
        await query.answer()
    except BadRequest as bad_request_error:
        # Игнорируем ошибку BadRequest для старых queries - это не критично для работы бота
        # Пользователь уже получил ответ или query был слишком старым
        if "Query is too old" in str(bad_request_error) or "query id is invalid" in str(bad_request_error):
            logger.debug(f"Callback query истек или недействителен (не критично): {bad_request_error}")
        else:
            logger.warning(f"BadRequest при ответе на callback query: {bad_request_error}")
    except Exception as answer_error:
        # Обрабатываем другие ошибки
        logger.warning(f"Не удалось ответить на callback query: {answer_error}")
    
    # Логируем событие нажатия кнопки
    # log_event уже обрабатывает ошибки внутри, дополнительный try-except не нужен
    if user_id:
        log_event(user_id, 'button_click', {
            'button': data
        })
    
    # Обрабатываем различные callback_data
    try:
        logger.info(f"🔘 Начинаем обработку callback_data: {data}")
        if data == 'my_profile':
            logger.info(f"🔘 Вызов my_profile для пользователя {user_id}")
            await my_profile(query, context)
        elif data == 'select_edit_field':
            await select_edit_field(query, context)
        elif data == 'edit_profile':
            await natal_chart_start(query, context)
        elif data == 'edit_name':
            await start_edit_field(query, context, 'name')
        elif data == 'edit_date':
            await start_edit_field(query, context, 'date')
        elif data == 'edit_time':
            await start_edit_field(query, context, 'time')
        elif data == 'edit_place':
            await start_edit_field(query, context, 'place')
        elif data == 'natal_chart':
            await handle_natal_chart_request(query, context)
        elif data == 'natal_chart_start':
            await natal_chart_start(query, context)
        elif data == 'back_menu':
            await back_to_menu(query)
        elif data == 'buy_natal_chart':
            await start_payment_process(query, context)
        elif data == 'payment_299':
            await start_payment_process(query, context, custom_price_rub=299)
        elif data == 'support':
            await show_support(query, context)
        elif data == 'planets_info':
            await show_planets_info(query, context)
        elif data == 'get_planets_data':
            await handle_planets_request(query, context)
        else:
            logger.warning(f"⚠️ Неизвестный callback_data: {data} от пользователя {user_id}")
            try:
                await query.answer(f"Неизвестная команда: {data}", show_alert=False)
            except:
                pass
    except Exception as handler_error:
        logger.error(f"❌ Ошибка при обработке callback_data '{data}' для пользователя {user_id}: {handler_error}", exc_info=True)
        try:
            await query.answer("Произошла ошибка при обработке запроса", show_alert=True)
        except:
            pass


async def back_to_menu(query):
    """Вернуться в главное меню"""
    buttons = [
        InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
        InlineKeyboardButton("🪐 Астрологические данные", callback_data='planets_info'),
        InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
        InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support'),
    ]
    
    keyboard = InlineKeyboardMarkup([[b] for b in buttons])
    await query.edit_message_text(
        "*Я могу сделать для тебя расклад натальной карты* 🌙✨\n\n"
        "*Натальная карта — это персональный астрологический код, который формируется в момент твоего рождения.*\n\n"
        "Это не гадание и не общее описание знака зодиака — это точная система координат, показывающая твои врождённые качества, сильные стороны, таланты, задачи и закономерности судьбы.\n\n"
        "*Почему это важно?*\n\n"
        "Потому что натальная карта помогает разобраться в себе глубже, чем любые тесты личности.\n\n"
        "*Хочешь узнать себя лучше?*",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


async def show_support(query, context):
    """Показывает информацию о поддержке"""
    user_id = query.from_user.id
    
    # Логируем обращение к поддержке
    log_event(user_id, 'support_contacted', {})
    
    support_message = '''💬 <b>Поддержка и обратная связь</b>

Если у вас возникли вопросы, проблемы или есть предложения по улучшению бота, напишите нам:

📧 @Astrolog_support

Мы постараемся ответить как можно скорее! ✨'''
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
    ]])
    
    # Используем HTML parse mode, чтобы нижнее подчеркивание в username не интерпретировалось как форматирование
    await query.edit_message_text(
        support_message,
        reply_markup=keyboard,
        parse_mode='HTML'
    )


async def show_planets_info(query, context):
    """Показывает информацию о бесплатной опции 'Положение планет'"""
    user_id = query.from_user.id
    
    # Логируем просмотр информации о планетах
    log_event(user_id, 'planets_info_viewed', {})
    
    info_message = f'''🪐 Астрологические данные

Здесь вы можете получить данные, на основе которых строится ваша натальная карта:

• Положение планет (Солнце, Луна, Меркурий, Венера, Марс, Юпитер, Сатурн, Уран, Нептун, Плутон)

• Ваши дома (куспиды домов)

• Асцендент, MC, IC, Десцендент

• Лунные узлы

• Аспекты между планетами

Чтобы получить интерпретацию этих данных, перейдите в пункт "📜 Натальная карта".'''
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Получить астрологические данные", callback_data='get_planets_data')],
        [InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')]
    ])
    
    await query.edit_message_text(
        info_message,
        reply_markup=keyboard,
        parse_mode=None
    )


def format_planets_data_for_user(chart_data: dict) -> str:
    """
    Форматирование данных натальной карты для отображения пользователю.
    Более читабельный формат, чем для промпта.
    """
    lines = []
    
    lines.append("🪐 <b>ПОЛОЖЕНИЕ ПЛАНЕТ И АСТРОЛОГИЧЕСКИЕ ДАННЫЕ</b>\n")
    
    planet_ru = {
        'Sun': 'Солнце',
        'Moon': 'Луна',
        'Mercury': 'Меркурий',
        'Venus': 'Венера',
        'Mars': 'Марс',
        'Jupiter': 'Юпитер',
        'Saturn': 'Сатурн',
        'Uranus': 'Уран',
        'Neptune': 'Нептун',
        'Pluto': 'Плутон',
    }
    
    # Личные планеты
    lines.append("<b>📌 Личные планеты:</b>")
    personal_planets = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars']
    for planet_name in personal_planets:
        if planet_name in chart_data['planets']:
            planet_info = chart_data['planets'][planet_name]
            planet_name_ru = planet_ru.get(planet_name, planet_name)
            retrograde = " (R)" if planet_info['is_retrograde'] else ""
            lines.append(
                f"  • {planet_name_ru}: {planet_info['sign']} {planet_info['sign_degrees']:.1f}°{retrograde}"
            )
    
    # Социальные планеты
    lines.append("\n<b>🌍 Социальные планеты:</b>")
    social_planets = ['Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto']
    for planet_name in social_planets:
        if planet_name in chart_data['planets']:
            planet_info = chart_data['planets'][planet_name]
            planet_name_ru = planet_ru.get(planet_name, planet_name)
            retrograde = " (R)" if planet_info['is_retrograde'] else ""
            lines.append(
                f"  • {planet_name_ru}: {planet_info['sign']} {planet_info['sign_degrees']:.1f}°{retrograde}"
            )
    
    # Ретроградные планеты
    if chart_data['retrograde_planets']:
        lines.append("\n<b>🔄 Ретроградные планеты на момент рождения:</b>")
        for retro_planet in chart_data['retrograde_planets']:
            lines.append(f"  • {planet_ru.get(retro_planet, retro_planet)}")
    else:
        lines.append("\n<b>🔄 Ретроградные планеты:</b> нет")
    
    # Угловые точки
    lines.append("\n<b>📍 Угловые точки карты:</b>")
    lines.append(f"  • Асцендент (ASC): {chart_data['ascendant']['sign']} "
                 f"{chart_data['ascendant']['sign_degrees']:.1f}°")
    lines.append(f"  • MC (Середина неба): {chart_data['mc']['sign']} "
                 f"{chart_data['mc']['sign_degrees']:.1f}°")
    lines.append(f"  • IC (Глубина неба): {chart_data['ic']['sign']} "
                 f"{chart_data['ic']['sign_degrees']:.1f}°")
    dsc_degrees = (chart_data['ascendant']['sign_degrees'] + 180) % 360
    lines.append(f"  • DSC (Десцендент): {chart_data['ascendant']['sign']} {dsc_degrees:.1f}°")
    
    # Куспиды домов
    lines.append("\n<b>🏠 Куспиды домов (система Placidus):</b>")
    for house_num in range(1, 13):
        house_key = f'House{house_num}'
        if house_key in chart_data['houses']:
            house_info = chart_data['houses'][house_key]
            lines.append(
                f"  • Дом {house_num}: {house_info['sign']} {house_info['sign_degrees']:.1f}°"
            )
    
    # Планеты в домах
    lines.append("\n<b>⭐ Планеты в домах:</b>")
    for planet_name in ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto']:
        if planet_name in chart_data['planets_in_houses']:
            house_num = chart_data['planets_in_houses'][planet_name]
            lines.append(f"  • {planet_ru.get(planet_name, planet_name)}: Дом {house_num}")
    
    # Лунные узлы
    lines.append("\n<b>🌙 Лунные узлы:</b>")
    lines.append(f"  • Северный узел (Раху): {chart_data['north_node']['sign']} "
                 f"{chart_data['north_node']['sign_degrees']:.1f}°")
    lines.append(f"  • Южный узел (Кету): {chart_data['south_node']['sign']} "
                 f"{chart_data['south_node']['sign_degrees']:.1f}°")
    
    # Аспекты
    lines.append("\n<b>🔗 Главные аспекты между планетами:</b>")
    if chart_data['aspects']:
        for aspect in chart_data['aspects']:
            p1_ru = planet_ru.get(aspect['planet1'], aspect['planet1'])
            p2_ru = planet_ru.get(aspect['planet2'], aspect['planet2'])
            lines.append(
                f"  • {p1_ru} {aspect['aspect']} {p2_ru} (орбис {aspect['orb']:.1f}°)"
            )
    else:
        lines.append("  Нет значимых аспектов в указанных орбисах")
    
    lines.append("\n💡 <i>Для получения интерпретации этих данных перейдите в раздел '📜 Получить интерпретацию'</i>")
    
    return "\n".join(lines)


async def handle_planets_request(query, context):
    """Обработка запроса на получение данных о планетах"""
    user_id = query.from_user.id
    
    # Логируем запрос данных о планетах
    log_event(user_id, 'planets_data_requested', {})
    
    # Загружаем профиль пользователя
    profile = load_user_profile(user_id)
    
    # Проверяем наличие всех необходимых данных
    has_profile = is_profile_complete(profile)
    
    if not has_profile:
        # Логируем попытку запроса без профиля
        log_event(user_id, 'planets_data_request_no_profile', {})
        await query.edit_message_text(
            "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
            "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта, а также сделает ответы Звёздного Чата более персональными.🔮\n\n"
            "Нажмите кнопку ниже, чтобы заполнить данные:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Заполнить данные", callback_data='edit_profile'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    try:
        # Показываем сообщение о загрузке
        await query.answer("⏳ Рассчитываю данные...")
        
        # Преобразуем профиль в формат, который ожидает calculate_natal_chart
        birth_data = {
            'name': profile.get('birth_name', ''),
            'date': profile.get('birth_date', ''),
            'time': profile.get('birth_time', ''),
            'place': profile.get('birth_place', '')
        }
        
        # Расчет натальной карты через Swiss Ephemeris
        chart_data = calculate_natal_chart(birth_data)
        
        # Форматирование данных для пользователя
        planets_text = format_planets_data_for_user(chart_data)
        
        # Логируем успешное получение данных
        log_event(user_id, 'planets_data_success', {})
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Получить интерпретацию", callback_data='natal_chart')],
            [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')]
        ])
        
        # Отправляем данные (Telegram имеет лимит 4096 символов на сообщение)
        if len(planets_text) > 4000:
            # Разбиваем на части
            parts = []
            current_part = ""
            for line in planets_text.split('\n'):
                if len(current_part) + len(line) + 1 > 4000:
                    parts.append(current_part)
                    current_part = line + "\n"
                else:
                    current_part += line + "\n"
            if current_part:
                parts.append(current_part)
            
            # Отправляем первую часть с клавиатурой
            await query.edit_message_text(
                parts[0],
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            
            # Отправляем остальные части
            for part in parts[1:]:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=part,
                    parse_mode='HTML'
                )
        else:
            await query.edit_message_text(
                planets_text,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Ошибка при расчете данных о планетах для пользователя {user_id}: {e}", exc_info=True)
        
        # Логируем ошибку
        log_event(user_id, 'planets_data_error', {'error': str(e)})
        
        await query.answer("❌ Произошла ошибка при расчете данных. Попробуйте позже.", show_alert=True)


def get_profile_message_and_buttons(user_id, user_data):
    """Формирует текст и кнопки для сообщения профиля"""
    # Загружаем данные из базы только если они не переданы
    # Переданные user_data имеют приоритет, так как могут содержать свежесохраненные данные
    if not user_data or not any(key.startswith('birth_') for key in user_data.keys()):
        db_data = load_user_profile(user_id)
        if db_data:
            user_data = {**db_data, **user_data}  # Объединяем данные
    else:
        # Если переданные данные есть, дополнительно загружаем из базы для полноты
        # но переданные данные имеют приоритет
        try:
            db_data = load_user_profile(user_id)
            if db_data:
                user_data = {**db_data, **user_data}  # Переданные данные имеют приоритет
        except Exception as load_error:
            logger.warning(f"⚠️ Ошибка при загрузке профиля пользователя {user_id} в get_profile_message_and_buttons: {load_error}")
            # Продолжаем с переданными данными
    
    has_profile = is_profile_complete(user_data)
    
    if has_profile:
        profile_text = f'''📋 *Данные о рождении*

💡 Вы можете ввести данные любого человека для расчета натальной карты.

*Данные:*
🆔 Имя: {user_data.get('birth_name', 'Не указано')}
📅 Дата рождения: {user_data.get('birth_date', 'Не указано')}
🕐 Время рождения: {user_data.get('birth_time', 'Не указано')}
🌍 Место рождения: {user_data.get('birth_place', 'Не указано')}'''
        
        buttons = [
            InlineKeyboardButton("✏️ Редактировать данные", callback_data='select_edit_field'),
            InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
        ]
    else:
        profile_text = '''📋 *Данные о рождении*

*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*

Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта, а также сделает ответы Звёздного Чата более персональными.🔮'''
        
        buttons = [
            InlineKeyboardButton("➕ Заполнить данные", callback_data='edit_profile'),
            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
        ]
    
    keyboard = InlineKeyboardMarkup([[button] for button in buttons])
    return profile_text, keyboard


async def my_profile(query, context):
    """Данные о рождении"""
    user_id = query.from_user.id
    
    # Логируем просмотр профиля
    try:
        log_event(user_id, 'profile_viewed', {})
    except:
        pass
    
    # Загружаем данные из базы, если их нет в context.user_data
    user_data = context.user_data
    
    # Если в user_data нет данных профиля, загружаем из базы
    if not user_data or not any(key.startswith('birth_') for key in user_data.keys()):
        try:
            loaded_data = load_user_profile(user_id)
            if loaded_data:
                # Обновляем context.user_data данными из базы
                user_data.update(loaded_data)
                context.user_data.update(loaded_data)
        except Exception as load_error:
            logger.warning(f"⚠️ Ошибка при загрузке профиля пользователя {user_id} в my_profile: {load_error}")
    
    try:
        profile_text, keyboard = get_profile_message_and_buttons(user_id, user_data)
        await query.edit_message_text(
            profile_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при показе профиля пользователю {user_id}: {e}", exc_info=True)
        # Пытаемся отправить простое сообщение
        try:
            await query.answer("Ошибка при загрузке профиля. Попробуйте позже.", show_alert=True)
        except:
            pass


async def show_profile_message(update, user_data):
    """Показывает сообщение с профилем через обычное сообщение (не через query)"""
    user_id = update.message.from_user.id
    
    # Обновляем user_data данными из базы для актуальности
    # Но сначала используем переданные данные, так как они могут быть только что сохранены
    try:
        loaded_data = load_user_profile(user_id)
        if loaded_data:
            # Объединяем: сначала данные из базы, потом переданные (переданные имеют приоритет, если они свежее)
            # Если в переданных user_data есть только что сохраненное поле, оно должно иметь приоритет
            user_data = {**loaded_data, **user_data}
        # Если данные из базы не загрузились, используем переданные
    except Exception as load_error:
        logger.warning(f"⚠️ Ошибка при загрузке профиля пользователя {user_id} из базы: {load_error}")
        # Продолжаем с переданными данными - они уже сохранены в базу
    
    try:
        profile_text, keyboard = get_profile_message_and_buttons(user_id, user_data)
        logger.info(f"📤 Отправка профиля пользователю {user_id}: имя={user_data.get('birth_name', 'N/A')}")
        await update.message.reply_text(
            profile_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Профиль успешно показан пользователю {user_id}")
    except Exception as show_error:
        logger.error(f"❌ Ошибка при показе профиля пользователю {user_id}: {show_error}", exc_info=True)
        raise


async def select_edit_field(query, context):
    """Выбор поля для редактирования"""
    user_id = query.from_user.id
    log_event(user_id, 'profile_edit_select', {})
    
    await query.edit_message_text(
        "✏️ *Редактирование данных о рождении*\n\n"
        "Выберите, что вы хотите изменить:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🆔 Имя", callback_data='edit_name')],
            [InlineKeyboardButton("📅 Дата рождения", callback_data='edit_date')],
            [InlineKeyboardButton("🕐 Время рождения", callback_data='edit_time')],
            [InlineKeyboardButton("🌍 Место рождения", callback_data='edit_place')],
            [InlineKeyboardButton("◀️ Назад", callback_data='my_profile')]
        ]),
        parse_mode='Markdown'
    )


async def start_payment_process(query, context, custom_price_rub=None):
    """Начало процесса оплаты через ЮKassa (внешняя ссылка - сразу открывается выбор способов оплаты)"""
    user_id = query.from_user.id
    
    # ВАЖНО: Отвечаем на callback query СРАЗУ, чтобы избежать timeout
    try:
        await query.answer("⏳ Создаю ссылку на оплату...")
    except Exception as answer_error:
        logger.warning(f"Не удалось ответить на callback query: {answer_error}")
    
    # Определяем цену для пользователя
    if custom_price_rub is not None:
        price_rub = custom_price_rub
        price_minor = custom_price_rub * 100
    else:
        price_rub, price_minor = get_user_price(user_id)
    
    # Логируем начало процесса оплаты
    log_event(user_id, 'payment_start', {
        'amount_rub': price_rub,
        'payment_provider': 'yookassa'
    })
    
    # Проверяем наличие необходимых ключей ЮKassa
    shop_id = os.getenv('YOOKASSA_SHOP_ID')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY')
    
    if not shop_id or not secret_key:
        logger.error(f"YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены для пользователя {user_id}")
        try:
            await query.message.reply_text(
                "❌ *Ошибка настройки оплаты*\n\n"
                "Настройка оплаты не завершена.\n\n"
                "Обратитесь в поддержку для решения проблемы.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💬 Поддержка", callback_data='support'),
                    InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
                ]]),
                parse_mode='Markdown'
            )
        except Exception as send_error:
            logger.error(f"Не удалось отправить сообщение об ошибке: {send_error}")
        log_event(user_id, 'payment_error', {'error': 'yookassa_credentials_not_set'})
        return
    
    logger.info(f"💰 Создание ссылки на оплату через ЮKassa: цена = {price_rub} ₽")
    
    try:
        # Выполняем запрос к ЮKassa в отдельном потоке, чтобы не блокировать event loop
        import asyncio
        loop = asyncio.get_event_loop()
        payment_url = await loop.run_in_executor(
            None,
            lambda: create_yookassa_payment_link(
                user_id=user_id,
                amount_rub=price_rub,
                description="Натальная карта - детальный астрологический разбор"
            )
        )
        
        if not payment_url:
            logger.error(f"❌ Не удалось создать ссылку на оплату для пользователя {user_id}")
            log_event(user_id, 'payment_error', {'error': 'payment_link_creation_failed'})
            
            await query.message.reply_text(
                "❌ *Ошибка создания ссылки на оплату*\n\n"
                "Не удалось создать ссылку для оплаты.\n\n"
                "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Попробовать снова", callback_data='buy_natal_chart'),
                    InlineKeyboardButton("💬 Поддержка", callback_data='support'),
                    InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
                ]]),
                parse_mode='Markdown'
            )
            return
        
        logger.info(f"✅ Ссылка на оплату создана для пользователя {user_id}")
        
        # Отправляем сообщение с кнопкой для перехода на оплату
        # При нажатии на кнопку сразу откроется экран выбора способов оплаты
        payment_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
            [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')]
        ])
        
        await query.message.reply_text(
            f"*Оплата натальной карты*\n\n"
            f"Сумма к оплате: *{price_rub} ₽*\n\n"
            f"Нажмите кнопку ниже, чтобы перейти к оплате.\n\n"
            f"*После оплаты сразу приступлю к подготовке отчета!*✨",
            reply_markup=payment_keyboard,
            parse_mode='Markdown'
        )
        
    except Exception as payment_error:
        logger.error(f"❌ Ошибка при создании ссылки на оплату: {payment_error}", exc_info=True)
        log_event(user_id, 'payment_error', {'error': str(payment_error), 'stage': 'payment_link_creation'})
        await query.answer("Ошибка при создании ссылки на оплату. Попробуйте позже.", show_alert=True)


async def start_edit_field(query, context, field_type):
    """Начало редактирования конкретного поля"""
    user_id = query.from_user.id
    log_event(user_id, 'profile_edit_start', {'field': field_type})
    
    user_data = context.user_data
    
    field_info = {
        'name': ('имя', 'Введите имя (может быть любого человека)'),
        'date': ('дату рождения', 'Введите дату рождения в формате: ДД.ММ.ГГГГ\nНапример: 15.03.1990'),
        'time': ('время рождения', 'Введите время рождения в формате: ЧЧ:ММ\nНапример: 14:30'),
        'place': ('место рождения', 'Введите место рождения (город, страна)\nНапример: Москва, Россия')
    }
    
    field_name, format_info = field_info.get(field_type, ('', ''))
    
    user_data['natal_chart_state'] = f'edit_{field_type}'
    
    await query.edit_message_text(
        f"✏️ Редактирование {field_name}\n\n"
        f"Текущее значение: {user_data.get(f'birth_{field_type}', 'Не указано')}\n\n"
        f"{format_info}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Отмена", callback_data='my_profile')
        ]]),
        parse_mode='Markdown'
    )


async def handle_natal_chart_request(query, context):
    """Обработка запроса на натальную карту"""
    user_id = query.from_user.id
    user_data = context.user_data
    
    # Проверяем, не идет ли уже генерация для этого пользователя
    # Сначала проверяем в памяти
    if user_id in active_generations:
        await query.edit_message_text(
            "⏳ *Генерация уже идет...*\n\n"
            "Пожалуйста, подождите завершения текущей генерации натальной карты.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
                [InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support')]
            ]),
            parse_mode='Markdown'
        )
        return
    
    # Проверяем по базе данных - не зависла ли предыдущая генерация
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Получаем последнюю незавершенную генерацию
        if db_type == 'postgresql':
            cursor.execute('''
                SELECT e1.timestamp 
                FROM events e1
                WHERE e1.user_id = %s 
                AND e1.event_type = 'natal_chart_generation_start'
                AND NOT EXISTS (
                    SELECT 1 
                    FROM events e2 
                    WHERE e2.user_id = %s 
                    AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                    AND e2.timestamp > e1.timestamp
                )
                ORDER BY e1.timestamp DESC
                LIMIT 1
            ''', (user_id, user_id))
        else:
            cursor.execute('''
                SELECT e1.timestamp 
                FROM events e1
                WHERE e1.user_id = ? 
                AND e1.event_type = 'natal_chart_generation_start'
                AND NOT EXISTS (
                    SELECT 1 
                    FROM events e2 
                    WHERE e2.user_id = ? 
                    AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                    AND e2.timestamp > e1.timestamp
                )
                ORDER BY e1.timestamp DESC
                LIMIT 1
            ''', (user_id, user_id))
        
        start_row = cursor.fetchone()
        
        if start_row:
            start_time_str = str(start_row[0])
            try:
                # Парсим timestamp
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                diff_seconds = (now - start_time).total_seconds()
                diff_minutes = diff_seconds / 60
                
                # Если прошло более 10 минут, считаем генерацию зависшей
                if diff_seconds > 600:  # 10 минут
                    logger.warning(f"⚠️ Обнаружена зависшая генерация для пользователя {user_id}, начавшаяся {diff_minutes:.1f} минут назад. Логируем как ошибку и разрешаем новую генерацию.")
                    
                    # Логируем зависшую генерацию как ошибку
                    log_event(user_id, 'natal_chart_error', {
                        'error_type': 'StuckGeneration',
                        'error_message': f'Генерация зависла и не завершилась за {diff_minutes:.1f} минут',
                        'stage': 'generation',
                        'stuck_duration_minutes': diff_minutes,
                        'generation_start': start_time_str
                    })
                    logger.warning(f"⚠️ Генерация для пользователя {user_id} зависла на {diff_minutes:.1f} минут - разрешаем новую попытку")
                else:
                    # Генерация еще идет, но не прошло 10 минут
                    await query.edit_message_text(
                        f"⏳ *Генерация уже идет...*\n\n"
                        f"Предыдущая генерация началась {diff_minutes:.0f} минут назад. Пожалуйста, подождите завершения.\n\n"
                        f"Обычно генерация занимает не более 5 минут.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
                            [InlineKeyboardButton("💬 Поддержка", callback_data='support')]
                        ]),
                        parse_mode='Markdown'
                    )
                    conn.close()
                    return
            except Exception as e:
                logger.warning(f"Ошибка при проверке зависшей генерации: {e}")
                # В случае ошибки разрешаем новую генерацию
    finally:
        conn.close()
    
    # Загружаем профиль из БД, если его нет в user_data
    if not user_data.get('birth_name'):
        loaded_data = load_user_profile(user_id)
        if loaded_data:
            user_data.update(loaded_data)
    
    has_profile = is_profile_complete(user_data)
    
    if not has_profile:
        # Логируем попытку запроса натальной карты без профиля
        log_event(user_id, 'natal_chart_request_no_profile', {})
        await query.edit_message_text(
            "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
            "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта, а также сделает ответы Звёздного Чата более персональными.🔮\n\n"
            "Нажмите кнопку ниже, чтобы заполнить данные:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    # Проверяем, оплатил ли пользователь
    if not user_has_paid(user_id):
        # Логируем попытку запроса натальной карты без оплаты
        log_event(user_id, 'natal_chart_request_no_payment', {})
        await query.edit_message_text(
            f"*Для получения натальной карты необходима оплата*\n\n"
            f"🔥 *Что вы получаете:*\n\n"
            f"• Разбор (≈30-40 страниц) с детальной интерпретацией в формате PDF\n"
            f"• не просто описание астрологических данных, а *глубокий анализ* их взаимосвязей\n"
            f"• *полноценная альтернатива личной консультации* у астролога\n\n"
            f"*Что будет в разборе:*\n\n"
            f"• Особенности личности: твой характер и эмоциональные реакции\n"
            f"• Как человека видят и воспринимают другие люди\n"
            f"• Сильные и слабые стороны личности и как с ними работать\n"
            f"• Карьерный потенциал (врожденные таланты, как поднять самооценку и обрести свободу)\n"
            f"• Типаж идеального партнера, трудности, возникающие в отношениях и как их избежать\n"
            f"• «Корневые» задачи души и направления развития\n\n"
            f"*Одна карта навсегда:*\n\n"
            f"Ты возвращаешься к карте снова и снова, когда возникают важные вопросы, поворотные моменты или желание понять, что делать дальше.\n\n"
            f"Нажмите кнопку ниже, чтобы перейти к оплате:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"💳 Оплатить {NATAL_CHART_PRICE_RUB} ₽", callback_data='buy_natal_chart'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    # Логируем начало генерации натальной карты
    log_event(user_id, 'natal_chart_generation_start', {
        'birth_date': user_data.get('birth_date'),
        'birth_time': user_data.get('birth_time'),
        'birth_place': user_data.get('birth_place')
    })
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
        [InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support')]
    ])
    
    await query.edit_message_text(
        "Создаём вашу натальную карту... Ожидайте ✨✨\n\n"
        "Обычно это занимает не более 5 минут.\n\n"
        "*Как подойти к чтению:*\n\n"
        "📖 *Читайте постепенно.*\n"
        "Не обязательно осваивать всё сразу — возвращайтесь к разделам по настроению или по запросу.\n\n"
        "🔍 *Замечайте повторяющиеся мотивы.*\n"
        "Они указывают на ваши главные темы и возможные точки трансформации.\n\n"
        "💭 *Сопоставляйте текст со своей реальностью.*\n"
        "Важно не просто прочитать, а увидеть, где это проявляется в вашей жизни.\n\n"
        "✍️ *Записывайте инсайты.*\n"
        "Мысли, эмоции, идеи — всё это помогает глубже интегрировать знания о себе.\n\n"
        "🔄 *Возвращайтесь к отчёту.*\n"
        "Натальная карта — живой инструмент. Она раскрывается по мере того, как вы открываетесь ей.\n\n"
        "Это пространство для себя.\n"
        "Для осознания.\n"
        "Для роста.",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    
    # Убеждаемся, что используем имя из заполненного профиля, а не из Telegram
    # Сначала пытаемся получить birth_name из user_data (заполненный профиль)
    birth_name = user_data.get('birth_name') or None
    
    # Если birth_name нет, загружаем из базы данных
    if not birth_name:
        loaded_profile = load_user_profile(user_id)
        if loaded_profile and loaded_profile.get('birth_name'):
            birth_name = loaded_profile.get('birth_name')
            user_data['birth_name'] = birth_name
    
    # Если все еще нет имени, используем fallback
    if not birth_name:
        birth_name = 'Пользователь'
    
    birth_data = {
        'name': birth_name,  # Используем имя из заполненного профиля
        'date': user_data.get('birth_date', 'Не указано'),
        'time': user_data.get('birth_time', 'Не указано'),
        'place': user_data.get('birth_place', 'Не указано')
    }
    
    openai_key = os.getenv('OPENAI_API_KEY')
    
    if not openai_key:
        await query.edit_message_text(
            "❌ *Ошибка настройки*\n\n"
            "API ключ OpenAI не настроен.\n"
            "Обратитесь к администратору бота.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    # Сохраняем информацию о генерации для отправки результата после завершения
    active_generations[user_id] = {
        'chat_id': query.message.chat_id,
        'message_id': query.message.message_id,
        'birth_data': birth_data,
        'openai_key': openai_key
    }
    
    # Запускаем генерацию в фоне, чтобы кнопки навигации работали
    asyncio.create_task(generate_natal_chart_background(user_id, context))


async def generate_natal_chart_background(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Генерация натальной карты в фоновом режиме"""
    if user_id not in active_generations:
        logger.warning(f"Генерация для пользователя {user_id} не найдена в active_generations")
        return
    
    gen_info = active_generations[user_id]
    chat_id = gen_info['chat_id']
    message_id = gen_info['message_id']
    birth_data = gen_info['birth_data']
    openai_key = gen_info['openai_key']
    
    # Проверяем оплату пользователя
    payment_consumed = user_has_paid(user_id)
    if not payment_consumed:
        logger.warning(f"⚠️ Пользователь {user_id} пытается сгенерировать натальную карту без оплаты")
        # Это не должно происходить, т.к. проверка уже была в handle_natal_chart_request
        # Но на всякий случай проверяем здесь тоже
    
    pdf_error_details = None
    
    # Логируем начало генерации
    generation_start_time = datetime.now()
    logger.info(f"🚀 Начало генерации натальной карты для пользователя {user_id} в {generation_start_time.isoformat()}")
    
    try:
        # Запускаем синхронную генерацию в отдельном потоке с таймаутом
        # Таймаут: 10 минут (600 секунд) - генерация не должна занимать дольше
        try:
            pdf_path, summary_text = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_natal_chart_with_gpt, 
                    birth_data, 
                    openai_key
                ),
                timeout=600.0  # 10 минут
            )
            
            generation_end_time = datetime.now()
            generation_duration = (generation_end_time - generation_start_time).total_seconds()
            logger.info(f"✅ Генерация завершена для пользователя {user_id} за {generation_duration:.1f} секунд ({generation_duration/60:.1f} минут)")
            
        except asyncio.TimeoutError:
            generation_end_time = datetime.now()
            generation_duration = (generation_end_time - generation_start_time).total_seconds()
            error_msg = f"Генерация превысила таймаут 10 минут (прошло {generation_duration/60:.1f} минут)"
            logger.error(f"❌ ТАЙМАУТ: {error_msg} для пользователя {user_id}")
            
            pdf_error_details = {
                'error_type': 'GenerationTimeout',
                'error_message': error_msg,
                'stage': 'generation',
                'timeout_seconds': 600,
                'actual_duration_seconds': generation_duration,
                'birth_data': {
                    'date': birth_data.get('date', 'N/A'),
                    'time': birth_data.get('time', 'N/A'),
                    'place': birth_data.get('place', 'N/A')
                }
            }
            log_event(user_id, 'natal_chart_error', pdf_error_details)
            
            # При таймауте оплата НЕ сбрасывается - пользователь может повторить попытку бесплатно
            payment_consumed = False
            
            # Отправляем сообщение об ошибке таймаута
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="⏱️ *Время ожидания истекло*\n\n"
                         "Генерация натальной карты заняла более 10 минут и была прервана.\n\n"
                         "Это может произойти из-за высокой нагрузки на сервер. Пожалуйста, попробуйте ещё раз.\n\n"
                         "Оплата сохранена для повторной попытки.\n\n"
                         "Если проблема повторяется, обратитесь в поддержку.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart'),
                        InlineKeyboardButton("💬 Поддержка", callback_data='support'),
                        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
                    ]])
                )
                logger.info(f"✅ Сообщение о таймауте отправлено пользователю {user_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке сообщения о таймауте пользователю {user_id}: {e}")
                # Пытаемся отправить обычное сообщение, если редактирование не удалось
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⏱️ *Время ожидания истекло*\n\n"
                             "Генерация натальной карты заняла более 10 минут и была прервана.\n\n"
                             "Пожалуйста, попробуйте ещё раз.",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart'),
                            InlineKeyboardButton("💬 Поддержка", callback_data='support'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
                        ]])
                    )
                except Exception as e2:
                    logger.error(f"❌ Критическая ошибка: не удалось отправить сообщение о таймауте пользователю {user_id}: {e2}")
            
            # Удаляем из active_generations и выходим
            if user_id in active_generations:
                del active_generations[user_id]
            return
        
        # Проверяем, что PDF был создан (даже fallback)
        if not pdf_path:
            pdf_error_details = {
                'error_type': 'PDFGenerationFailed',
                'error_message': 'PDF generation returned None (even fallback failed)',
                'stage': 'pdf_creation',
                'fallback_created': False,
                'birth_data': {
                    'date': birth_data.get('date', 'N/A'),
                    'time': birth_data.get('time', 'N/A'),
                    'place': birth_data.get('place', 'N/A')
                }
            }
            logger.error(f"❌ КРИТИЧНО: PDF не был создан даже fallback для пользователя {user_id}")
            # При ошибке генерации PDF оплата НЕ сбрасывается - пользователь может повторить попытку бесплатно
            payment_consumed = False
            log_event(user_id, 'natal_chart_error', {**pdf_error_details, 'payment_kept': True})
            
            # Отправляем сообщение об ошибке пользователю
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ *Ошибка*\n\n"
                         "К сожалению, не удалось сгенерировать натальную карту.\n"
                         "Попробуйте ещё раз позже.\n\n"
                         "Оплата сохранена для повторной попытки.\n\n"
                         "Если проблема повторяется, обратитесь в поддержку.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart'),
                        InlineKeyboardButton("💬 Поддержка", callback_data='support'),
                        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
                    ]])
                )
            except:
                pass

        async def send_text_message(text: str, chat: int, msg_id: int, is_edit: bool):
            """Отправка текстового сообщения с безопасной обработкой Markdown."""
            max_length = 4000

            async def do_send(message_text: str, edit: bool):
                if edit:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat,
                            message_id=msg_id,
                            text=message_text,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        # Если не удалось отредактировать, отправляем новое сообщение
                        await context.bot.send_message(
                            chat_id=chat,
                            text=message_text,
                            parse_mode='Markdown'
                        )
                else:
                    await context.bot.send_message(
                        chat_id=chat,
                        text=message_text,
                        parse_mode='Markdown'
                    )

            try:
                if len(text) <= max_length:
                    await do_send(text, is_edit)
                else:
                    first_part = text[:max_length]
                    last_newline = first_part.rfind('\n')
                    if last_newline > max_length * 0.8:
                        first_part = text[:last_newline]
                        remaining = text[last_newline + 1:]
                    else:
                        remaining = text[max_length:]

                    await do_send(first_part, is_edit)

                    while remaining:
                        if len(remaining) <= max_length:
                            await do_send(remaining, False)
                            break
                        chunk = remaining[:max_length]
                        last_newline = chunk.rfind('\n')
                        if last_newline > max_length * 0.8:
                            chunk = remaining[:last_newline]
                            remaining = remaining[last_newline + 1:]
                        else:
                            remaining = remaining[max_length:]

                        await do_send(chunk, False)
            except Exception as parse_error:
                logger.warning(f"Ошибка парсинга Markdown: {parse_error}, пробуем очистить текст")
                cleaned_text = clean_markdown(text)
                try:
                    await do_send(cleaned_text, is_edit)
                except Exception as second_error:
                    logger.warning(f"Не удалось отправить даже очищенный текст: {second_error}, отправляем без форматирования")
                    plain_text = text.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
                    if is_edit:
                        try:
                            await context.bot.edit_message_text(chat_id=chat, message_id=msg_id, text=plain_text)
                        except:
                            await context.bot.send_message(chat_id=chat, text=plain_text)
                    else:
                        await context.bot.send_message(chat_id=chat, text=plain_text)

        if pdf_path:
            try:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text="📄 *Натальная карта готова!*\n\nПолный отчет в PDF во вложении.",
                        parse_mode='Markdown'
                    )
                except:
                    # Если не удалось отредактировать, отправляем новое сообщение
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="📄 *Натальная карта готова!*\n\nПолный отчет в PDF во вложении.",
                        parse_mode='Markdown'
                    )

                safe_name = ''.join(
                    ch for ch in birth_data.get('name', 'user') if ch.isalnum() or ch in ('_', '-', ' ')
                )
                if not safe_name:
                    safe_name = 'user'
                filename = f"natal_chart_{safe_name.replace(' ', '_')}.pdf"
                caption = "📄 Натальная карта в формате PDF"
                pdf_sent_successfully = False
                try:
                    with open(pdf_path, 'rb') as pdf_file:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=pdf_file,
                            filename=filename,
                            caption=caption
                        )
                    # PDF успешно отправлен - только теперь считаем оплату использованной
                    pdf_sent_successfully = True
                    payment_consumed = True
                
                    # Логируем успешную отправку натальной карты
                    log_event(user_id, 'natal_chart_success', {
                        'filename': filename,
                        'birth_date': birth_data.get('date'),
                        'birth_time': birth_data.get('time'),
                        'birth_place': birth_data.get('place')
                    })
                    
                    # Отправляем сообщение с кнопкой для возврата в главное меню
                    menu_keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
                    ]])
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="Используйте кнопки меню для навигации:",
                        reply_markup=menu_keyboard
                    )
                except Exception as send_error:
                    # Ошибка при отправке PDF - не сбрасываем оплату, чтобы пользователь мог повторить
                    logger.error(f"❌ Ошибка при отправке PDF: {send_error}", exc_info=True)
                    raise  # Пробрасываем исключение в блок except выше
            except Exception as pdf_error:
                error_type = type(pdf_error).__name__
                error_message = str(pdf_error)
                logger.error(f"❌ ОШИБКА при отправке PDF пользователю {user_id}: {error_type}: {error_message}", exc_info=True)
                
                # При ошибке отправки PDF оплата НЕ должна сбрасываться - пользователь может повторить попытку бесплатно
                payment_consumed = False
                
                log_event(user_id, 'natal_chart_error', {
                    'error_type': error_type,
                    'error_message': error_message,
                    'stage': 'pdf_send',
                    'filename': filename,
                    'pdf_path': pdf_path if pdf_path else None,
                    'payment_kept': True  # Отмечаем, что оплата сохранена для повторной попытки
                })
                await send_text_message("⚠️ Не удалось отправить PDF. Попробуйте позже.", chat_id, message_id, is_edit=True)
                # Добавляем кнопку Повторить попытку
                retry_keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart'),
                    InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                ]])
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Вы можете повторить попытку генерации отчёта. Оплата сохранена для повторной попытки.",
                    reply_markup=retry_keyboard
                )
            finally:
                if pdf_path and os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except OSError as remove_error:
                        logger.warning(f"Не удалось удалить временный PDF-файл: {remove_error}")
        else:
            # PDF не был создан
            logger.error(f"❌ PDF не был создан для пользователя {user_id}")
            # При ошибке создания PDF оплата НЕ сбрасывается - пользователь может повторить попытку бесплатно
            payment_consumed = False
            log_event(user_id, 'natal_chart_error', {
                'error_type': 'PDFNotCreated',
                'error_message': 'PDF generation returned None',
                'stage': 'pdf_creation',
                'payment_kept': True,
                'birth_data': {
                    'date': birth_data.get('date', 'N/A'),
                    'time': birth_data.get('time', 'N/A'),
                    'place': birth_data.get('place', 'N/A')
                }
            })
            
            await send_text_message("⚠️ Не удалось получить PDF. Попробуйте позже.", chat_id, message_id, is_edit=True)
            # Не списываем оплату, позволяем повторить генерацию
            retry_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]])
            await context.bot.send_message(
                chat_id=chat_id,
                text="Вы можете повторить попытку генерации отчёта. Оплата сохранена для повторной попытки.",
                reply_markup=retry_keyboard
            )
        
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        error_traceback = None
        try:
            import traceback
            error_traceback = traceback.format_exc()
        except:
            pass
        
        logger.error(f"❌ ОШИБКА при генерации натальной карты для пользователя {user_id}: {error_type}: {error_message}", exc_info=True)
        
        # При общей ошибке оплата НЕ сбрасывается - пользователь может повторить попытку бесплатно
        payment_consumed = False
        
        # Детальное логирование ошибки в базу данных
        error_details = {
            'error_type': error_type,
            'error_message': error_message,
            'stage': 'generation',
            'user_id': user_id,
            'birth_data': {
                'date': birth_data.get('date', 'N/A'),
                'time': birth_data.get('time', 'N/A'),
                'place': birth_data.get('place', 'N/A')
            }
        }
        
        # Добавляем traceback если есть, но обрезаем до первых 1000 символов
        if error_traceback:
            error_details['traceback'] = error_traceback[:1000]
        
        log_event(user_id, 'natal_chart_error', {**error_details, 'payment_kept': True})
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ *Ошибка*\n\n"
                     "Произошла ошибка при генерации натальной карты.\n"
                     "Попробуйте ещё раз.\n\n"
                     "Оплата сохранена для повторной попытки.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart')],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
                ]),
                parse_mode='Markdown'
            )
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ *Ошибка*\n\n"
                     "Произошла ошибка при генерации натальной карты.\n"
                     "Попробуйте ещё раз.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart')],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
                ]),
                parse_mode='Markdown'
            )
    finally:
        # Всегда очищаем active_generations, даже при ошибках или перезапуске
        # Это предотвращает зависание генераций при перезапуске контейнера
        if user_id in active_generations:
            logger.info(f"🧹 Очистка active_generations для пользователя {user_id}")
            del active_generations[user_id]
        
        # Сбрасываем статус оплаты после успешной генерации
        if payment_consumed:
            reset_user_payment(user_id)
            logger.info(f"Оплата сброшена для пользователя {user_id} после успешной генерации натальной карты")


def validate_date(date_str):
    """Валидация даты рождения"""
    try:
        parts = date_str.split('.')
        if len(parts) != 3:
            return False, "Неверный формат. Используйте ДД.ММ.ГГГГ"
        
        day, month, year = parts
        
        if not (day.isdigit() and month.isdigit() and year.isdigit()):
            return False, "Дата должна содержать только цифры"
        
        day, month, year = int(day), int(month), int(year)
        
        if not (1 <= day <= 31):
            return False, "День должен быть от 1 до 31"
        if not (1 <= month <= 12):
            return False, "Месяц должен быть от 1 до 12"
        if not (1900 <= year <= 2100):
            return False, "Год должен быть от 1900 до 2100"
        
        return True, None
    except Exception as e:
        return False, f"Ошибка в дате: {str(e)}"


def validate_time(time_str):
    """Валидация времени рождения"""
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            return False, "Неверный формат. Используйте ЧЧ:ММ"
        
        hour, minute = parts
        
        if not (hour.isdigit() and minute.isdigit()):
            return False, "Время должно содержать только цифры"
        
        hour, minute = int(hour), int(minute)
        
        if not (0 <= hour <= 23):
            return False, "Часы должны быть от 0 до 23"
        if not (0 <= minute <= 59):
            return False, "Минуты должны быть от 0 до 59"
        
        return True, None
    except Exception as e:
        return False, f"Ошибка во времени: {str(e)}"


def validate_place(place_str):
    """Валидация места рождения"""
    if not place_str or len(place_str.strip()) < 3:
        return False, "Место рождения должно содержать минимум 3 символа"
    
    if place_str.strip().isdigit():
        return False, "Место рождения не может состоять только из цифр"
    
    return True, None


def clean_markdown(text):
    """Очистка и исправление Markdown для Telegram"""
    import re
    # Удаляем или исправляем проблемные конструкции Markdown
    
    # Экранируем незакрытые подчеркивания
    # Ищем подчеркивания, которые не закрыты на строке
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Подсчитываем подчеркивания (одинарные)
        underscores = len(re.findall(r'(?<!\*)_(?!\*)', line))
        if underscores % 2 != 0:
            # Нечетное количество - экранируем все подчеркивания
            line = line.replace('_', '\\_')
        
        # Подсчитываем звездочки (одинарные для курсива)
        # Игнорируем двойные звездочки для жирного текста
        asterisks_single = len(re.findall(r'(?<!\*)\*(?!\*)', line))
        asterisks_double = len(re.findall(r'\*\*', line))
        # Если есть непарные одинарные звездочки
        if asterisks_single % 2 != 0 and asterisks_double == 0:
            line = line.replace('*', '\\*')
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    return text


# Определяем базовый путь проекта (абсолютный путь к директории, где находится bot.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, 'fonts')
DEJAVU_FONT_PATH = os.path.join(FONTS_DIR, 'DejaVuSans.ttf')

REPORTLAB_FONT_CANDIDATES = [
    DEJAVU_FONT_PATH,  # Основной шрифт в папке проекта
    os.path.join(os.path.dirname(__file__), 'fonts', 'DejaVuSans.ttf'),  # Относительный путь (fallback)
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    '/Library/Fonts/Arial Unicode.ttf',
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/Library/Fonts/Arial.ttf',
]

NATAL_CHART_PRICE_RUB = 499
NATAL_CHART_PRICE_MINOR = NATAL_CHART_PRICE_RUB * 100  # копейки для Telegram
SPECIAL_PRICE_RUB = 299
SPECIAL_PRICE_MINOR = SPECIAL_PRICE_RUB * 100  # копейки для Telegram


def get_user_price(user_id):
    """
    Получает цену для пользователя (299 или 499 руб)
    
    Args:
        user_id: ID пользователя Telegram
    
    Returns:
        tuple: (price_rub, price_minor) - цена в рублях и в копейках
    """
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if db_type == 'postgresql':
            # Проверяем, есть ли колонка special_price_299
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='special_price_299'
            """)
            has_column = cursor.fetchone() is not None
            
            if has_column:
                cursor.execute('SELECT special_price_299 FROM users WHERE user_id = %s', (user_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    conn.close()
                    return (SPECIAL_PRICE_RUB, SPECIAL_PRICE_MINOR)
        else:
            # Проверяем, есть ли колонка special_price_299
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            has_column = 'special_price_299' in columns
            
            if has_column:
                cursor.execute('SELECT special_price_299 FROM users WHERE user_id = ?', (user_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    conn.close()
                    return (SPECIAL_PRICE_RUB, SPECIAL_PRICE_MINOR)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при проверке специальной цены для пользователя {user_id}: {e}")
    finally:
        conn.close()
    
    # По умолчанию возвращаем стандартную цену
    return (NATAL_CHART_PRICE_RUB, NATAL_CHART_PRICE_MINOR)


def create_yookassa_payment_link(user_id: int, amount_rub: float, description: str = "Натальная карта") -> Optional[str]:
    """
    Создает ссылку на оплату через ЮKassa
    
    Требуемые переменные окружения:
    - YOOKASSA_SHOP_ID: ID магазина в ЮKassa
    - YOOKASSA_SECRET_KEY: Секретный ключ ЮKassa
    - PAYMENT_SUCCESS_URL: URL для редиректа после успешной оплаты (опционально)
    - PAYMENT_RETURN_URL: URL для возврата при отмене (опционально)
    
    Returns:
        str: URL для оплаты или None в случае ошибки
    """
    import requests
    import base64
    
    shop_id = os.getenv('YOOKASSA_SHOP_ID')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY')
    
    if not shop_id or not secret_key:
        logger.error(f"YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены")
        return None
    
    # Формируем ID платежа
    payment_id = f"natal_chart_{user_id}_{uuid.uuid4().hex[:8]}"
    
    # URL для уведомлений (webhook)
    webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    # Формируем URL для возврата после оплаты
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME', '')
    
    # Используем переменные окружения для URL или формируем по username
    # Приоритет: сначала проверяем переменные окружения, затем формируем по username
    success_url_env = os.getenv('PAYMENT_SUCCESS_URL', '').strip()
    return_url_env = os.getenv('PAYMENT_RETURN_URL', '').strip()
    
    # Обрабатываем случай, когда в переменной окружения может быть префикс (например, "PAYMENT_RETURN_URL=https://...")
    if return_url_env.startswith('PAYMENT_RETURN_URL='):
        return_url_env = return_url_env.replace('PAYMENT_RETURN_URL=', '', 1).strip()
    if success_url_env.startswith('PAYMENT_SUCCESS_URL='):
        success_url_env = success_url_env.replace('PAYMENT_SUCCESS_URL=', '', 1).strip()
    
    if success_url_env:
        success_url = success_url_env
    elif bot_username:
        # Просто открываем бота без параметров - генерация уже запускается через webhook автоматически
        success_url = f'https://t.me/{bot_username}'
    else:
        logger.error("❌ PAYMENT_SUCCESS_URL и TELEGRAM_BOT_USERNAME не установлены!")
        logger.error("❌ Не могу создать корректный URL для возврата после оплаты")
        # Используем заглушку как fallback
        success_url = 'https://t.me/your_bot'
    
    if return_url_env:
        return_url = return_url_env
    elif bot_username:
        # Просто открываем бота без параметров - генерация уже запускается через webhook автоматически
        return_url = f'https://t.me/{bot_username}'
    else:
        return_url = 'https://t.me/your_bot'
    
    logger.info(f"🔗 Success URL: {success_url}")
    logger.info(f"🔗 Return URL: {return_url}")
    
    # Валидация return_url (должен быть валидным HTTPS URL)
    if not return_url.startswith('https://'):
        logger.error(f"❌ return_url должен начинаться с https://, получен: {return_url}")
        return None
    
    # Подготовка данных для создания платежа
    # Минимальный набор полей согласно документации ЮKassa API v3
    # https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start
    
    # ВАЖНО: НЕ указываем payment_method_data, чтобы показать ВСЕ доступные способы оплаты
    # Если указать payment_method_data с конкретным типом (bank_card, sbp и т.д.),
    # ЮKassa покажет только этот метод + привязанные дефолтные
    # Без payment_method_data - показываются все способы оплаты, включенные в настройках магазина
    
    # Форматируем amount.value как строку с двумя знаками после запятой (требование API)
    amount_value_str = f"{amount_rub:.2f}"
    
    # Проверяем, что amount не отрицательный и не нулевой
    if amount_rub <= 0:
        logger.error(f"❌ Сумма платежа должна быть больше 0, получено: {amount_rub}")
        return None
    
    payment_data = {
        "amount": {
            "value": amount_value_str,  # Строка с двумя знаками после запятой
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url  # Обязательное поле для redirect типа
        },
        "capture": True,  # Автоматическое подтверждение платежа
        "description": description,  # Описание платежа (максимум 128 символов)
        "metadata": {
            "user_id": str(user_id),
            "payment_type": "natal_chart"
        }
        # ВАЖНО: payment_method_data НЕ указываем - это позволяет показать все способы оплаты
    }
    
    # Проверяем длину description (максимум 128 символов по документации)
    if len(description) > 128:
        logger.warning(f"⚠️ Description слишком длинный ({len(description)} символов), обрезаем до 128")
        payment_data["description"] = description[:125] + "..."
    
    # Добавляем receipt (фискальный чек) - требуется для некоторых магазинов ЮKassa
    # Согласно документации: https://yookassa.ru/developers/api#create_payment
    # Receipt обязателен если включена фискализация в настройках магазина
    # Для receipt требуется customer (email или phone) и items (список товаров)
    payment_data["receipt"] = {
        "customer": {
            "email": f"user_{user_id}@telegram.bot"  # Минимальный email для фискализации
        },
        "items": [
            {
                "description": description[:128],  # Название товара (максимум 128 символов)
                "quantity": "1.00",
                "amount": {
                    "value": amount_value_str,
                    "currency": "RUB"
                },
                "vat_code": 1,  # НДС 20% (стандартная ставка для цифровых услуг в РФ)
                "payment_mode": "full_prepayment",  # Полная предоплата
                "payment_subject": "service"  # Цифровая услуга
            }
        ]
    }
    
    # Авторизация через Basic Auth
    auth_string = f"{shop_id}:{secret_key}"
    auth_bytes = auth_string.encode('ascii')
    auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/json",
        "Idempotence-Key": payment_id
    }
    
    # Проверяем, что shop_id и secret_key не пустые и имеют корректный формат
    if not shop_id or shop_id.strip() == '':
        logger.error("❌ YOOKASSA_SHOP_ID пустой или не установлен")
        return None
    if not secret_key or secret_key.strip() == '':
        logger.error("❌ YOOKASSA_SECRET_KEY пустой или не установлен")
        return None
    
    # Проверяем базовый формат shop_id (должен быть числом)
    try:
        int(shop_id)
    except ValueError:
        logger.error(f"❌ YOOKASSA_SHOP_ID имеет неверный формат (ожидается число): {shop_id[:10]}...")
        return None
    
    logger.info(f"🔑 Создание платежа в ЮKassa: user_id={user_id}, amount={amount_rub}, shop_id={shop_id}")
    logger.debug(f"📦 Payment data: {json.dumps(payment_data, ensure_ascii=False, indent=2)}")
    
    # Явно определяем URL для платежа
    payment_api_url = "https://api.yookassa.ru/v3/payments"
    logger.info(f"🌐 URL для запроса: {payment_api_url}")
    
    # Проверяем наличие прокси в окружении (может влиять на подключение)
    proxy_env_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
    proxy_found = False
    for proxy_var in proxy_env_vars:
        proxy_value = os.getenv(proxy_var)
        if proxy_value:
            logger.info(f"⚠️ Найден прокси в окружении: {proxy_var}={proxy_value}")
            proxy_found = True
    if not proxy_found:
        logger.info("✅ Прокси в окружении не обнаружено")
    
    try:
        # Создаем платеж через API ЮKassa
        # Увеличен timeout для чтения до 60 секунд из-за медленного ответа API ЮKassa
        logger.info(f"📤 Отправка POST запроса к ЮKassa API (timeout: 10s connect, 60s read)...")
        response = requests.post(
            payment_api_url,
            json=payment_data,
            headers=headers,
            timeout=(10, 60)  # 10 сек на подключение, 60 сек на чтение ответа
        )
        
        logger.info(f"📡 Ответ от ЮKassa: status={response.status_code}")
        
        if response.status_code == 200:
            payment_info = response.json()
            
            # Проверяем структуру ответа согласно документации
            # Ответ должен содержать: id, status, confirmation.confirmation_url
            payment_yookassa_id = payment_info.get('id')
            payment_status = payment_info.get('status')
            confirmation = payment_info.get('confirmation', {})
            payment_url = confirmation.get('confirmation_url')
            
            if not payment_yookassa_id:
                logger.error(f"❌ ЮKassa вернула платеж без ID. Ответ: {json.dumps(payment_info, ensure_ascii=False)}")
                return None
            
            if not payment_url:
                logger.error(f"❌ ЮKassa вернула платеж без URL подтверждения. Ответ: {json.dumps(payment_info, ensure_ascii=False)}")
                return None
            
            logger.info(f"✅ Ссылка на оплату создана для пользователя {user_id}")
            logger.info(f"   Payment ID: {payment_yookassa_id}")
            logger.info(f"   Status: {payment_status}")
            logger.info(f"   Payment URL: {payment_url}")
            
            # Сохраняем информацию о платеже в базу для отслеживания
            save_payment_info(user_id, payment_yookassa_id, payment_id, amount_rub)
            
            return payment_url
        else:
            logger.error(f"❌ Ошибка при создании платежа в ЮKassa: status={response.status_code}")
            logger.error(f"📄 Ответ сервера: {response.text}")
            try:
                error_details = response.json()
                logger.error(f"📋 Детали ошибки: {json.dumps(error_details, ensure_ascii=False, indent=2)}")
                
                # Специальная обработка ошибки 401 (неверные credentials)
                if response.status_code == 401:
                    error_code = error_details.get('code', '')
                    if error_code == 'invalid_credentials':
                        logger.error("=" * 60)
                        logger.error("🚨 КРИТИЧЕСКАЯ ОШИБКА АУТЕНТИФИКАЦИИ ЮKASSA!")
                        logger.error("=" * 60)
                        logger.error("❌ YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY неверны или истек срок действия")
                        logger.error("💡 Решение:")
                        logger.error("   1. Проверьте значения YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в переменных окружения")
                        logger.error("   2. Убедитесь, что используете ключи из правильного окружения (тестовое/продакшн)")
                        logger.error("   3. Перевыпустите секретный ключ в личном кабинете ЮKassa (Merchant Profile)")
                        logger.error("   4. Проверьте, что shop_id и secret_key соответствуют друг другу")
                        logger.error("=" * 60)
                
                # Специальная обработка ошибки 400 (неверный запрос, например, receipt)
                if response.status_code == 400:
                    error_code = error_details.get('code', '')
                    error_parameter = error_details.get('parameter', '')
                    if error_code == 'invalid_request' and error_parameter == 'receipt':
                        logger.error("=" * 60)
                        logger.error("🚨 ОШИБКА В СТРУКТУРЕ RECEIPT (ФИСКАЛЬНЫЙ ЧЕК)")
                        logger.error("=" * 60)
                        logger.error(f"❌ ЮKassa отклонил запрос из-за неправильного receipt")
                        logger.error(f"📋 Детали ошибки: {error_details.get('description', '')}")
                        logger.error("💡 Решение:")
                        logger.error("   1. Проверьте настройки фискализации в личном кабинете ЮKassa")
                        logger.error("   2. Убедитесь, что receipt содержит корректные данные (customer, items, vat_code)")
                        logger.error("   3. Проверьте, что vat_code соответствует вашему типу налогообложения")
                        logger.error("=" * 60)
            except:
                pass
            return None
            
    except requests.exceptions.ConnectTimeout:
        logger.error("=" * 60)
        logger.error(f"❌ ConnectTimeout до api.yookassa.ru для пользователя {user_id}")
        logger.error(f"   Не удалось установить TCP соединение в течение 30 секунд")
        logger.error(f"   Это указывает на проблему сети/доступа к api.yookassa.ru")
        logger.error("=" * 60)
        return None
    except requests.exceptions.ReadTimeout:
        logger.error("=" * 60)
        logger.error(f"❌ ReadTimeout от api.yookassa.ru для пользователя {user_id}")
        logger.error(f"   Соединение установлено, но ответ не получен в течение 60 секунд")
        logger.error(f"   Это указывает на серьезную проблему с API ЮKassa")
        logger.error(f"   Возможные причины:")
        logger.error(f"   • API ЮKassa перегружен или недоступен")
        logger.error(f"   • Проблемы с сетью Railway → ЮKassa")
        logger.error(f"   • Неверный формат запроса (хотя соединение установлено)")
        logger.error("=" * 60)
        return None
    except requests.exceptions.Timeout as timeout_error:
        logger.error(f"❌ ТАЙМАУТ при запросе к ЮKassa API для пользователя {user_id}")
        logger.error(f"   Тип таймаута: {type(timeout_error).__name__}")
        logger.error(f"   Запрос не был завершен в течение 30 секунд")
        logger.error(f"   Детали: {timeout_error}")
        return None
    except requests.exceptions.ConnectionError as conn_error:
        error_str = str(conn_error)
        logger.error("=" * 60)
        logger.error(f"❌ ОШИБКА ПОДКЛЮЧЕНИЯ к ЮKassa API для пользователя {user_id}")
        logger.error(f"   Тип ошибки: {type(conn_error).__name__}")
        logger.error(f"   Детали: {error_str}")
        
        # Проверяем тип ConnectionError
        if "RemoteDisconnected" in error_str or "Remote end closed connection" in error_str:
            logger.error("   🔍 Сервер ЮKassa закрыл соединение без ответа")
            logger.error("   💡 Возможные причины:")
            logger.error("      • Проблемы на стороне API ЮKassa (перегрузка, временная недоступность)")
            logger.error("      • Блокировка соединений на уровне сети (firewall, rate limiting)")
            logger.error("      • Проблемы с keep-alive соединениями")
            logger.error("   💡 Рекомендация: Попробуйте повторить запрос через несколько секунд")
        elif "NewConnectionError" in error_str or "Failed to establish" in error_str:
            logger.error("   🔍 Не удалось установить TCP соединение")
            logger.error("   💡 Возможные причины:")
            logger.error("      • Недоступность api.yookassa.ru")
            logger.error("      • Проблемы с DNS")
            logger.error("      • Блокировка на уровне сети")
        else:
            logger.error("   🔍 Общая ошибка соединения")
        
        logger.error("=" * 60)
        return None
    except requests.exceptions.RequestException as req_error:
        logger.error(f"❌ ОШИБКА СЕТИ при запросе к ЮKassa для пользователя {user_id}")
        logger.error(f"   Тип ошибки: {type(req_error).__name__}")
        logger.error(f"   Детали: {req_error}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"❌ НЕИЗВЕСТНОЕ ИСКЛЮЧЕНИЕ при создании платежа в ЮKassa для пользователя {user_id}")
        logger.error(f"   Тип: {type(e).__name__}")
        logger.error(f"   Детали: {e}", exc_info=True)
        return None


async def check_yookassa_payment_status(yookassa_payment_id: str) -> Optional[dict]:
    """
    Проверяет статус платежа через API ЮKassa
    
    Returns:
        dict: Информация о платеже или None в случае ошибки
    """
    import requests
    import base64
    
    shop_id = os.getenv('YOOKASSA_SHOP_ID')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY')
    
    if not shop_id or not secret_key:
        logger.error("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены")
        return None
    
    # Авторизация через Basic Auth
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
            timeout=10
        )
        
        if response.status_code == 200:
            payment_info = response.json()
            logger.info(f"✅ Статус платежа {yookassa_payment_id}: {payment_info.get('status')}")
            return payment_info
        elif response.status_code == 404:
            # Платеж не найден - возможно, был удален или не существует
            error_data = response.json() if response.text else {}
            logger.warning(f"⚠️  Платеж {yookassa_payment_id} не найден в YooKassa (404). Помечаем как canceled.")
            # Помечаем платеж как canceled в базе
            try:
                update_payment_status(yookassa_payment_id, 'canceled', {
                    'status': 'canceled',
                    'cancellation_details': {
                        'reason': 'not_found',
                        'party': 'yookassa'
                    },
                    'description': 'Payment not found in YooKassa (404)'
                })
            except Exception as e:
                logger.error(f"❌ Ошибка при обновлении статуса платежа: {e}")
            return None
        else:
            logger.error(f"❌ Ошибка при проверке статуса платежа: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Исключение при проверке статуса платежа: {e}", exc_info=True)
        return None


def update_payment_status(yookassa_payment_id: str, status: str, payment_data: dict = None):
    """Обновляет статус платежа в базе данных"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if db_type == 'postgresql':
            cursor.execute('''
                UPDATE payments
                SET status = %s, updated_at = %s
                WHERE yookassa_payment_id = %s
                RETURNING user_id, amount
            ''', (status, datetime.now(), yookassa_payment_id))
        else:
            cursor.execute('''
                UPDATE payments
                SET status = ?, updated_at = ?
                WHERE yookassa_payment_id = ?
            ''', (status, datetime.now().isoformat(), yookassa_payment_id))
            # Для SQLite нужно отдельно получить user_id
            cursor.execute('''
                SELECT user_id, amount FROM payments
                WHERE yookassa_payment_id = ?
            ''', (yookassa_payment_id,))
        
        result = cursor.fetchone()
        conn.commit()
        
        if result:
            user_id = result[0]
            amount = result[1]
            logger.info(f"💾 Статус платежа обновлен: payment_id={yookassa_payment_id}, status={status}, user_id={user_id}")
            return user_id, amount
        return None, None
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении статуса платежа: {e}", exc_info=True)
        conn.rollback()
        return None, None
    finally:
        conn.close()


class ApplicationContextWrapper:
    """Обертка для Application, имитирующая Context для использования в check_and_process_pending_payment"""
    def __init__(self, application: Application, user_id: int):
        self.bot = application.bot
        self.application = application
        self.user_id = user_id
        # Загружаем user_data из базы данных
        self.user_data = load_user_profile(user_id) or {}


async def check_and_process_pending_payment(user_id: int, context_or_application) -> bool:
    """
    Проверяет и обрабатывает ожидающие платежи для пользователя
    Также проверяет succeeded платежи, которые еще не были обработаны
    
    Args:
        user_id: ID пользователя
        context_or_application: ContextTypes.DEFAULT_TYPE или Application объект
    
    Returns:
        bool: True если платеж был найден и обработан, False иначе
    """
    # Если передан Application, создаем wrapper
    if isinstance(context_or_application, Application):
        context = ApplicationContextWrapper(context_or_application, user_id)
    else:
        context = context_or_application
    
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Сначала ищем последний ожидающий платеж пользователя
        if db_type == 'postgresql':
            cursor.execute('''
                SELECT yookassa_payment_id, amount, created_at
                FROM payments
                WHERE user_id = %s AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT yookassa_payment_id, amount, created_at
                FROM payments
                WHERE user_id = ? AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            ''', (user_id,))
        
        payment = cursor.fetchone()
        
        # Если нет pending платежей, проверяем succeeded платежи, которые еще не обработаны
        if not payment:
            # Ищем succeeded платежи, для которых нет события payment_success
            if db_type == 'postgresql':
                cursor.execute('''
                    SELECT p.yookassa_payment_id, p.amount, p.created_at
                    FROM payments p
                    WHERE p.user_id = %s 
                    AND p.status = 'succeeded'
                    AND NOT EXISTS (
                        SELECT 1 FROM events e
                        WHERE e.user_id = %s
                        AND e.event_type = 'payment_success'
                        AND e.event_data::text LIKE '%%' || p.yookassa_payment_id || '%%'
                    )
                    ORDER BY p.created_at DESC
                    LIMIT 1
                ''', (user_id, user_id))
            else:
                cursor.execute('''
                    SELECT p.yookassa_payment_id, p.amount, p.created_at
                    FROM payments p
                    WHERE p.user_id = ?
                    AND p.status = 'succeeded'
                    AND NOT EXISTS (
                        SELECT 1 FROM events e
                        WHERE e.user_id = ?
                        AND e.event_type = 'payment_success'
                        AND e.event_data LIKE '%' || p.yookassa_payment_id || '%'
                    )
                    ORDER BY p.created_at DESC
                    LIMIT 1
                ''', (user_id, user_id))
            
            payment = cursor.fetchone()
            
            # Если нашли succeeded платеж, обрабатываем его напрямую
            if payment:
                yookassa_payment_id = payment[0]
                amount = payment[1]
                
                logger.info(f"🔍 Найден необработанный succeeded платеж {yookassa_payment_id} для пользователя {user_id}")
                
                # Помечаем пользователя как оплатившего
                mark_user_paid(user_id)
                
                # Логируем успешную оплату
                log_event(user_id, 'payment_success', {
                    'yookassa_payment_id': yookassa_payment_id,
                    'amount': amount,
                    'source': 'auto_processing_succeeded'
                })
                
                # Запускаем генерацию натальной карты
                user_data = context.user_data
                if not user_data.get('birth_name'):
                    loaded_data = load_user_profile(user_id)
                    if loaded_data:
                        user_data.update(loaded_data)
                
                has_profile = is_profile_complete(user_data)
                
                if has_profile:
                    await handle_natal_chart_request_from_payment(user_id, context)
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="✅ *Оплата получена!*\n\n"
                             "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
                             "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]]),
                        parse_mode='Markdown'
                    )
                
                conn.close()
                return True
        
        if not payment:
            return False
        
        yookassa_payment_id = payment[0]
        amount = payment[1]
        
        # Проверяем статус платежа через API ЮKassa
        payment_info = await check_yookassa_payment_status(yookassa_payment_id)
        
        if not payment_info:
            logger.warning(f"Не удалось получить статус платежа {yookassa_payment_id}")
            return False
        
        payment_status = payment_info.get('status')
        
        # Обновляем статус в базе
        update_payment_status(yookassa_payment_id, payment_status, payment_info)
        
        # Если платеж успешен, обрабатываем его
        if payment_status == 'succeeded':
            logger.info(f"✅ Платеж успешно обработан для пользователя {user_id}, payment_id={yookassa_payment_id}")
            
            # Помечаем пользователя как оплатившего
            mark_user_paid(user_id)
            
            # Логируем успешную оплату
            log_event(user_id, 'payment_success', {
                'yookassa_payment_id': yookassa_payment_id,
                'amount': amount,
                'payment_method': payment_info.get('payment_method', {}).get('type', 'unknown')
            })
            
            # Автоматически запускаем генерацию натальной карты
            user_data = context.user_data
            if not user_data.get('birth_name'):
                loaded_data = load_user_profile(user_id)
                if loaded_data:
                    user_data.update(loaded_data)
            
            has_profile = is_profile_complete(user_data)
            
            if has_profile:
                # Запускаем генерацию натальной карты
                await handle_natal_chart_request_from_payment(user_id, context)
            else:
                # Профиль не заполнен
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ *Оплата получена!*\n\n"
                         "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
                         "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                    ]]),
                    parse_mode='Markdown'
                )
            
            return True
        
        elif payment_status in ['canceled', 'pending']:
            logger.info(f"ℹ️ Платеж {yookassa_payment_id} в статусе {payment_status}")
            return False
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке платежа: {e}", exc_info=True)
        return False
    finally:
        conn.close()


async def handle_natal_chart_request_from_payment(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Запускает генерацию натальной карты после успешной оплаты"""
    # Проверяем, не запущена ли уже генерация для этого пользователя
    if user_id in active_generations:
        logger.warning(f"⚠️ Генерация для пользователя {user_id} уже запущена, пропускаем дублирующий запрос")
        return
    
    # Проверяем по базе данных - не началась ли генерация только что
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    try:
        # Получаем последнюю незавершенную генерацию (за последние 2 минуты)
        if db_type == 'postgresql':
            cursor.execute('''
                SELECT e1.timestamp 
                FROM events e1
                WHERE e1.user_id = %s 
                AND e1.event_type = 'natal_chart_generation_start'
                AND e1.timestamp > NOW() - INTERVAL '2 minutes'
                AND NOT EXISTS (
                    SELECT 1 
                    FROM events e2 
                    WHERE e2.user_id = %s 
                    AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                    AND e2.timestamp > e1.timestamp
                )
                ORDER BY e1.timestamp DESC
                LIMIT 1
            ''', (user_id, user_id))
        else:
            # SQLite - проверяем последние 2 минуты
            two_minutes_ago = (datetime.now() - timedelta(minutes=2)).isoformat()
            cursor.execute('''
                SELECT e1.timestamp 
                FROM events e1
                WHERE e1.user_id = ? 
                AND e1.event_type = 'natal_chart_generation_start'
                AND e1.timestamp > ?
                AND NOT EXISTS (
                    SELECT 1 
                    FROM events e2 
                    WHERE e2.user_id = ? 
                    AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                    AND e2.timestamp > e1.timestamp
                )
                ORDER BY e1.timestamp DESC
                LIMIT 1
            ''', (user_id, two_minutes_ago, user_id))
        
        recent_generation = cursor.fetchone()
        if recent_generation:
            logger.warning(f"⚠️ Обнаружена недавно начатая генерация для пользователя {user_id} (в последние 2 минуты), пропускаем дублирующий запрос")
            conn.close()
            return
    except Exception as check_error:
        logger.warning(f"⚠️ Ошибка при проверке дублирующей генерации: {check_error}")
    finally:
        conn.close()
    
    # Получаем bot token для создания нового bot в новом event loop
    bot_token = None
    if hasattr(context, 'bot') and context.bot:
        bot_token = context.bot.token
    elif hasattr(context, 'application') and context.application:
        bot_token = context.application.bot.token
    
    if not bot_token:
        logger.error(f"❌ Не удалось получить bot token для пользователя {user_id}")
        return
    
    try:
        # Загружаем данные пользователя из контекста или базы данных
        user_data = context.user_data if hasattr(context, 'user_data') else {}
        if not user_data.get('birth_name'):
            loaded_data = load_user_profile(user_id)
            if loaded_data:
                user_data.update(loaded_data)
        
        # Проверяем наличие всех необходимых данных
        birth_name = user_data.get('birth_name')
        birth_date = user_data.get('birth_date')
        birth_time = user_data.get('birth_time')
        birth_place = user_data.get('birth_place')
        
        if not all([birth_name, birth_date, birth_time, birth_place]):
            # Отправляем сообщение в отдельном потоке с новым event loop
            def send_profile_message():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Создаем новый bot в новом event loop
                        new_bot = Bot(token=bot_token)
                        loop.run_until_complete(new_bot.send_message(
                            chat_id=user_id,
                            text="✅ *Оплата получена!*\n\n"
                                 "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
                                 "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта.",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                            ]]),
                            parse_mode='Markdown'
                        ))
                    finally:
                        loop.close()
                except Exception as send_error:
                    logger.error(f"❌ Ошибка при отправке сообщения: {send_error}", exc_info=True)
            
            thread = threading.Thread(target=send_profile_message, daemon=True)
            thread.start()
            return
        
        # Логируем начало генерации натальной карты
        log_event(user_id, 'natal_chart_generation_start', {
            'birth_date': birth_date,
            'birth_time': birth_time,
            'birth_place': birth_place,
            'source': 'payment_auto'
        })
        
        # Используем имя из профиля, если есть
        if not birth_name:
            birth_name = 'Пользователь'
        
        birth_data = {
            'name': birth_name,
            'date': birth_date,
            'time': birth_time,
            'place': birth_place
        }
        
        # Проверяем наличие OpenAI ключа
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            def send_error_message():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Создаем новый bot в новом event loop
                        new_bot = Bot(token=bot_token)
                        loop.run_until_complete(new_bot.send_message(
                            chat_id=user_id,
                            text="❌ *Ошибка настройки*\n\n"
                                 "API ключ OpenAI не настроен.\n"
                                 "Обратитесь к администратору бота.",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                            ]]),
                            parse_mode='Markdown'
                        ))
                    finally:
                        loop.close()
                except Exception as send_error:
                    logger.error(f"❌ Ошибка при отправке сообщения: {send_error}", exc_info=True)
            
            thread = threading.Thread(target=send_error_message, daemon=True)
            thread.start()
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
            [InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support')]
        ])
        
        # Отправляем сообщение о начале генерации в отдельном потоке с новым event loop
        # и получаем message_id для сохранения в active_generations
        status_message_result = {'message': None, 'error': None}
        
        def send_status_message():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Создаем новый bot в новом event loop
                    new_bot = Bot(token=bot_token)
                    message = loop.run_until_complete(new_bot.send_message(
                        chat_id=user_id,
                        text="✅ *Оплата получена!*\n\n"
                             "Создаём вашу натальную карту... Ожидайте ✨✨\n\n"
                             "Обычно это занимает не более 5 минут.\n\n"
                             "*Как подойти к чтению:*\n\n"
                             "📖 *Читайте постепенно.*\n"
                             "Не обязательно осваивать всё сразу — возвращайтесь к разделам по настроению или по запросу.\n\n"
                             "🔍 *Замечайте повторяющиеся мотивы.*\n"
                             "Они указывают на ваши главные темы и возможные точки трансформации.\n\n"
                             "💭 *Сопоставляйте текст со своей реальностью.*\n"
                             "Важно не просто прочитать, а увидеть, где это проявляется в вашей жизни.\n\n"
                             "✍️ *Записывайте инсайты.*\n"
                             "Мысли, эмоции, идеи — всё это помогает глубже интегрировать знания о себе.\n\n"
                             "🔄 *Возвращайтесь к отчёту.*\n"
                             "Натальная карта — живой инструмент. Она раскрывается по мере того, как вы открываетесь ей.\n\n"
                             "Это пространство для себя.\n"
                             "Для осознания.\n"
                             "Для роста.",
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    ))
                    status_message_result['message'] = message
                except Exception as e:
                    status_message_result['error'] = e
                    logger.error(f"❌ Ошибка при отправке статусного сообщения: {e}", exc_info=True)
                finally:
                    loop.close()
            except Exception as thread_error:
                logger.error(f"❌ Ошибка в потоке отправки сообщения: {thread_error}", exc_info=True)
        
        status_thread = threading.Thread(target=send_status_message, daemon=True)
        status_thread.start()
        status_thread.join(timeout=5)  # Ждем до 5 секунд для отправки сообщения
        
        if status_message_result['error']:
            raise status_message_result['error']
        
        status_message = status_message_result['message']
        if not status_message:
            logger.error(f"❌ Не удалось отправить статусное сообщение пользователю {user_id}")
            return
        
        # Сохраняем информацию о генерации для отправки результата после завершения
        active_generations[user_id] = {
            'chat_id': status_message.chat_id,
            'message_id': status_message.message_id,
            'birth_data': birth_data,
            'openai_key': openai_key
        }
        
        # Запускаем генерацию в фоне в отдельном потоке
        # Создаем новый context для генерации с правильным bot
        def run_generation():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Создаем новый context с правильным bot для нового event loop
                    # Создаем новый bot в новом event loop - это безопасно, так как
                    # каждый Bot объект работает независимо и использует свой собственный HTTP сессион
                    new_bot = Bot(token=bot_token)
                    
                    # Создаем SimpleContext для передачи в generate_natal_chart_background
                    # Это не мешает callback queries, т.к. они обрабатываются в основном event loop
                    from telegram.ext import ContextTypes
                    class SimpleContext:
                        def __init__(self, bot_instance, user_id_val):
                            self.bot = bot_instance
                            self.user_id = user_id_val
                            self.user_data = load_user_profile(user_id_val) or {}
                    
                    new_context = SimpleContext(new_bot, user_id)
                    
                    loop.run_until_complete(generate_natal_chart_background(user_id, new_context))
                finally:
                    loop.close()
            except Exception as gen_error:
                logger.error(f"❌ Ошибка при запуске генерации в потоке: {gen_error}", exc_info=True)
        
        gen_thread = threading.Thread(target=run_generation, daemon=True)
        gen_thread.start()
        logger.info(f"🚀 Генерация натальной карты запущена в фоновом потоке для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске генерации после оплаты: {e}", exc_info=True)
        # Отправляем сообщение об ошибке в отдельном потоке
        def send_error_fallback():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Создаем новый bot в новом event loop
                    new_bot = Bot(token=bot_token)
                    loop.run_until_complete(new_bot.send_message(
                        chat_id=user_id,
                        text="✅ *Оплата получена!*\n\n"
                             "Для начала генерации натальной карты нажмите кнопку ниже:",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]]),
                        parse_mode='Markdown'
                    ))
                finally:
                    loop.close()
            except Exception as send_error:
                logger.error(f"❌ Ошибка при отправке сообщения об ошибке: {send_error}", exc_info=True)
        
        error_thread = threading.Thread(target=send_error_fallback, daemon=True)
        error_thread.start()


def save_payment_info(user_id: int, yookassa_payment_id: str, internal_payment_id: str, amount: float):
    """Сохраняет информацию о платеже в базу данных для отслеживания"""
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Таблица payments должна быть создана в init_db(), но проверяем на всякий случай
        # Сохраняем информацию о платеже
        if db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO payments (user_id, yookassa_payment_id, internal_payment_id, amount, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'pending', %s, %s)
                ON CONFLICT (yookassa_payment_id) DO UPDATE SET
                    updated_at = EXCLUDED.updated_at
            ''', (user_id, yookassa_payment_id, internal_payment_id, amount, datetime.now(), datetime.now()))
        else:
            cursor.execute('''
                INSERT INTO payments (user_id, yookassa_payment_id, internal_payment_id, amount, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT (yookassa_payment_id) DO UPDATE SET
                    updated_at = excluded.updated_at
            ''', (user_id, yookassa_payment_id, internal_payment_id, amount, datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        logger.info(f"💾 Информация о платеже сохранена: user_id={user_id}, payment_id={yookassa_payment_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении информации о платеже: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()


def _register_reportlab_font() -> str:
    """Регистрирует Unicode-шрифт для поддержки кириллицы в PDF"""
    logger.info("🔍 Поиск шрифта для PDF...")
    
    # Сначала проверяем, что папка fonts существует
    fonts_dir = os.path.join(os.path.dirname(__file__), 'fonts')
    logger.info(f"📁 Папка fonts: {fonts_dir}")
    logger.info(f"📁 Папка fonts существует: {os.path.exists(fonts_dir)}")
    
    if os.path.exists(fonts_dir):
        files_in_fonts = os.listdir(fonts_dir)
        logger.info(f"📄 Файлы в папке fonts: {files_in_fonts}")
    
    for candidate in REPORTLAB_FONT_CANDIDATES:
        exists = os.path.exists(candidate)
        logger.info(f"   Проверка: {candidate} - {'✅ существует' if exists else '❌ не найден'}")
        
        if exists:
            try:
                logger.info(f"   Попытка регистрации шрифта: {candidate}")
                pdfmetrics.registerFont(TTFont('ReportLabUnicode', candidate))
                logger.info(f"✅ Шрифт успешно зарегистрирован: {candidate}")
                return 'ReportLabUnicode'
            except Exception as font_error:
                logger.warning(f"   ⚠️ Не удалось зарегистрировать шрифт {candidate}: {font_error}", exc_info=True)
    
    # Критическое предупреждение - без Unicode шрифта кириллица не будет отображаться
    logger.error("❌ КРИТИЧНО: Не найден Unicode-шрифт с поддержкой кириллицы!")
    logger.error("   Проверенные пути:")
    for candidate in REPORTLAB_FONT_CANDIDATES:
        logger.error(f"     - {candidate}")
    logger.error("   Текст в PDF будет отображаться как прямоугольники.")
    logger.error("   Решение: добавьте DejaVuSans.ttf в папку fonts/ проекта")
    logger.warning("   Используется Helvetica (без поддержки кириллицы)")
    return 'Helvetica'


def _clean_inline_markdown(text: str) -> str:
    replacements = [
        ('**', ''),
        ('__', ''),
        ('*', ''),
        ('`', ''),
        ('\u2014', '—'),
    ]
    cleaned = text
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)
    return cleaned.strip()


def _extract_summary(markdown_text: str) -> Optional[str]:
    lines = markdown_text.split('\n')
    buffer = []
    capturing = False
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith('##'):
            header = line.lstrip('#').strip().lower()
            if 'крат' in header and 'резюм' in header:
                capturing = True
                continue
            elif capturing:
                break
        if capturing:
            buffer.append(raw_line)

    summary = '\n'.join(buffer).strip()
    if summary:
        return summary

    # Фолбэк: первые ~10 строк текста
    preview = '\n'.join(lines[:10]).strip()
    return preview or None


def draw_cosmic_background(canvas, doc):
    """Рисует премиум космический фон со звёздами для каждой страницы (Premium Astro Style)"""
    # Premium цветовая палитра
    dark_cosmic = HexColor('#0A0F1F')  # Тёмно-синий космический
    deep_blue_violet = HexColor('#151B2D')  # Сине-фиолетовый глубокий
    gold_metallic = HexColor('#F4D491')  # Золотой металлический (светлый)
    gold_metallic_dark = HexColor('#CDAF6D')  # Золотой металлический (тёмный)
    lunar_silver = HexColor('#C8D0E2')  # Лунный серебристый
    warm_beige = HexColor('#F8F4E9')  # Тёплый светлый беж
    shadow_dark_1 = HexColor('#101629')  # Тень слева сверху
    shadow_dark_2 = HexColor('#0D1321')  # Тень справа снизу
    
    width, height = A4
    
    # Основной фон
    canvas.setFillColor(dark_cosmic)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    
    # Градиентные тени для 3D-эффекта
    # Тень слева сверху
    canvas.setFillColor(shadow_dark_1)
    canvas.setFillAlpha(0.4)
    canvas.circle(width * 0.15, height * 0.85, width * 0.5, fill=1, stroke=0)
    
    # Тень справа снизу
    canvas.setFillColor(shadow_dark_2)
    canvas.setFillAlpha(0.4)
    canvas.circle(width * 0.85, height * 0.15, width * 0.5, fill=1, stroke=0)
    
    canvas.setFillAlpha(1.0)
    
    # Уменьшенное количество звёзд (20-25 крупных вместо 80)
    random.seed(42)  # Для одинаковых звёзд на всех страницах
    for _ in range(25):
        x = random.uniform(0, width)
        y = random.uniform(0, height)
        # Крупные звёзды (2-3px)
        star_size = random.choice([2.0, 2.5, 3.0])
        star_color = random.choice([gold_metallic, lunar_silver])
        
        canvas.setFillColor(star_color)
        # Некоторые звёзды с размытием для глубины
        if random.random() < 0.3:  # 30% звёзд с размытием
            canvas.setFillAlpha(0.4)
            canvas.circle(x, y, star_size * 1.5, fill=1, stroke=0)
        
        canvas.setFillAlpha(random.uniform(0.7, 1.0))
        canvas.circle(x, y, star_size, fill=1, stroke=0)
    
    canvas.setFillAlpha(1.0)


# Путь к статичному изображению натальной карты
NATAL_CHART_IMAGE_PATH = os.path.join(os.path.dirname(__file__), 'images', 'natal_chart.png')

# Вводный текст для натальной карты
INTRODUCTORY_TEXT = """Перед вами — персональный разбор вашей натальной карты.

Он создан на основе точных астрономических данных момента рождения: даты, времени и места. Это не прогноз и не гадание, а аналитическая модель, которая описывает ваши врождённые качества, эмоциональные реакции, сильные стороны, уязвимости, жизненные задачи и направления личного роста.

Натальная карта — это не инструкция, а навигация.

Она показывает возможности, внутренние механизмы и природные настройки, с которыми вы пришли в этот мир. Как именно они раскроются — зависит от выбора, опыта и зрелости каждого человека.

# Как работать с разбором

## 1. Читайте спокойно и постепенно

Не нужно пытаться «освоить» всё сразу. Разбор объёмный, и ваша задача — почувствовать, что откликается.

Возвращайтесь к отчёту в разные периоды жизни: с каждым разом он будет читаться по-новому.

## 2. Отмечайте повторяющиеся темы

Если в разных разделах всплывают одинаковые мотивы — это ваши ключевые точки роста или силы.

Повтор в астрологии — не случайность, а акцент.

## 3. Сопоставляйте с реальностью

Смотрите, где описанные качества проявляются в вашей жизни:

— в отношениях

— в работе

— в характере

— в привычках

— в реакции на стресс

— в способах достижения целей

Это помогает увидеть закономерности и получить инсайты.

## 4. Записывайте наблюдения и открытия

Натальная карта — процесс, а не разовый документ.

Ведите заметки:

— что совпало

— что удивило

— где хочется развиваться

— какие изменения происходят со временем

Это делает разбор инструментом реального развития.

## 5. Используйте карту как компас, а не как ограничение

Если что-то кажется "не про вас", это не ошибка — это может быть потенциал, который ещё не раскрылся, или часть личности, которую вы привыкли подавлять.

Иногда карта отражает глубинные вещи, которые мы узнаём позже.

# Какие есть ограничения у разбора

Чтобы использовать документ экологично, важно понимать его рамки.

## 1. Астрология описывает потенциал, а не готовую личность

Карта — это «исходный код», который проявляется по-разному в разных условиях.

Жизненный опыт, травмы, воспитание и выбор человека могут усилить или ослабить проявления.

## 2. Натальная карта не даёт конкретных предсказаний

Она не скажет: «Будет так».

Она скажет: «Вот механизм. Вот направление. Вот вероятность».

Человек всегда остаётся ведущим.

## 3. Возможны погрешности времени рождения

Даже 5–10 минут могут изменить Асцендент, положение домов и акценты в интерпретации.

Если время рождения примерное — часть описаний может быть менее точной.

## 4. Разбор не заменяет психологию и терапию

Он даёт понимание почему что-то происходит, но не всегда отвечает "как именно" это изменить.

Это инструмент осознания, а не лечение.

## 5. Некоторые проявления раскрываются только с возрастом

Есть аспекты, которые включаются:

— после 21 года

— после 30 лет (Сатурн)

— после 40 (транзиты внешних планет)

Поэтому молодому человеку может казаться, что часть описаний «ещё не про него».

## 6. Карта не ограничивает, а показывает выборы

Негативные описания — это не приговор.

Это зоны, где человек может стать сильнее, мудрее и свободнее.

# Главное

Натальная карта — это инструмент, который помогает увидеть себя глубже, точнее и честнее.

Относитесь к этому разбору как к карте возможностей, а не как к автоматическому сценарию.

Вы — тот, кто управляет движением.

Карта лишь освещает путь."""

def _extract_section_headings(markdown_text: str) -> list:
    """
    Извлекает заголовки разделов из markdown текста.
    Возвращает список кортежей (уровень, текст заголовка, имя для anchor)
    """
    headings = []
    lines = markdown_text.split('\n')
    section_num = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith('##'):
            heading_level = len(stripped) - len(stripped.lstrip('#'))
            if heading_level == 2:  # Только заголовки второго уровня (## Раздел N: ...)
                heading_text = stripped.lstrip('#').strip()
                section_num += 1
                # Создаем имя для anchor (уникальное, безопасное для PDF)
                anchor_name = f"section_{section_num}"
                headings.append((heading_level, heading_text, anchor_name))
    return headings


def _generate_anchor_name(heading_text: str) -> str:
    """Генерирует безопасное имя для anchor из текста заголовка"""
    # Извлекаем номер раздела из заголовка (формат: "Раздел N: Название" или "## Раздел N: Название")
    import re
    # Убираем знаки # в начале, если есть
    cleaned = heading_text.lstrip('#').strip()
    match = re.match(r'Раздел\s+(\d+)', cleaned, re.IGNORECASE)
    if match:
        section_num = match.group(1)
        return f"section_{section_num}"
    # Если нет номера, используем хэш (fallback)
    return f"section_{abs(hash(cleaned)) % 10000}"


def draw_static_natal_chart_image(canvas, doc, gold_color):
    """Рисует статичное изображение натальной карты на первой странице (Premium Astro Style)"""
    if not os.path.exists(NATAL_CHART_IMAGE_PATH):
        # Если изображение не найдено, просто пропускаем (не критично)
        return
    
    try:
        from reportlab.lib.utils import ImageReader
        
        width, height = A4
        
        # Размер изображения уменьшен на 15-20% от исходного размера
        page_min_dimension = min(width, height)
        base_image_size = page_min_dimension / 2  # Было: половина страницы
        image_size = base_image_size * 0.825  # Уменьшено на 17.5% (15-20%)
        
        # Центрируем изображение по горизонтали и вертикали (по центру страницы)
        image_x = (width - image_size) / 2
        image_y = (height - image_size) / 2  # По центру страницы по вертикали
        
        # Загружаем и рисуем изображение с поддержкой прозрачности
        img = ImageReader(NATAL_CHART_IMAGE_PATH)
        
        # ReportLab автоматически поддерживает прозрачность PNG
        canvas.drawImage(
            img, 
            image_x, 
            image_y, 
            width=image_size, 
            height=image_size, 
            preserveAspectRatio=True,
            mask='auto'  # Автоматически использует альфа-канал для прозрачности
        )
    except Exception as e:
        logger.warning(f"Не удалось отобразить изображение натальной карты: {e}")


def draw_page_footer(canvas, doc, title, page_num, gold_color, text_color, font_name):
    """Рисует подпись страницы внизу (Premium Astro Style)"""
    try:
        width, height = A4
        footer_y = 40  # Отступ от низа страницы
        
        # Извлекаем имя пользователя из заголовка
        user_name = "Пользователь"
        if title and ":" in title:
            user_name = title.split(":", 1)[1].strip()
        
        # Текущая дата
        from datetime import datetime
        current_date = datetime.now().strftime("%d.%m.%Y")
        
        # Подпись (мелким шрифтом, используем font_name для поддержки кириллицы)
        canvas.setFillColor(text_color)
        canvas.setFont(font_name, 9)
        
        # Левая часть: имя пользователя
        footer_text_left = f"Создано специально для {user_name}"
        canvas.drawString(80, footer_y, footer_text_left)
        
        # Правая часть: название бота и дата
        footer_text_right = f"Astrology_bot • {current_date}"
        text_width = canvas.stringWidth(footer_text_right, font_name, 9)
        canvas.drawString(width - 80 - text_width, footer_y, footer_text_right)
        
        # Тонкая золотая линия над подписью
        canvas.setStrokeColor(gold_color)
        canvas.setLineWidth(0.5)
        canvas.line(80, footer_y + 12, width - 80, footer_y + 12)
        
    except Exception as e:
        logger.warning(f"Не удалось нарисовать подпись страницы: {e}")


def generate_pdf_from_markdown(markdown_text: str, title: str, chart_data: Optional[dict] = None) -> Optional[str]:
    """
    Формирование PDF из Markdown-текста с космическим оформлением.
    chart_data параметр оставлен для обратной совместимости, но не используется для генерации диаграммы.
    Вместо этого используется статичное изображение из images/natal_chart.png
    """
    try:
        lines = (markdown_text or '').split('\n')
        font_name = _register_reportlab_font()
        
        # Проверяем, что шрифт действительно поддерживает кириллицу
        if font_name == 'Helvetica':
            logger.error("⚠️ ВНИМАНИЕ: Используется шрифт без поддержки кириллицы!")
            logger.error("   PDF будет содержать прямоугольники вместо текста.")
            logger.error("   Необходимо добавить DejaVuSans.ttf в папку fonts/")

        fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)

        # Premium цветовая палитра
        cosmic_text = HexColor('#EAE6D9')  # Мягкий кремовый текст
        cosmic_gold = HexColor('#F4D491')  # Золотой металлический (светлый)
        cosmic_gold_dark = HexColor('#CDAF6D')  # Золотой металлический (тёмный, для градиентов)
        cosmic_silver = HexColor('#C8D0E2')  # Лунный серебристый
        cosmic_accent = HexColor('#151B2D')  # Сине-фиолетовый глубокий
        
        # Используем BaseDocTemplate для кастомного PageTemplate
        width, height = A4
        # Premium дизайн: ширина колонки 600-650px при A4 (595x842 pt)
        # Для колонки 600-650px (213-230 pt) нужны отступы примерно 75-85pt с каждой стороны
        left_margin = 80  # Отступ для колонки ~600px
        right_margin = 80
        # Одинаковые отступы сверху и снизу на всех страницах (уменьшенные)
        top_margin = 60  # Уменьшенный верхний отступ
        bottom_margin = 60  # Одинаковый нижний отступ для единообразия
        
        doc = BaseDocTemplate(
            temp_path,
            pagesize=A4,
            leftMargin=left_margin,
            rightMargin=right_margin,
            topMargin=top_margin,
            bottomMargin=bottom_margin,
            title=title or 'Натальная карта'
        )
        
        # Создаём Frame для контента
        frame = Frame(
            left_margin,
            bottom_margin,
            width - left_margin - right_margin,
            height - top_margin - bottom_margin,
            leftPadding=0,
            bottomPadding=0,
            rightPadding=0,
            topPadding=0,
            id='cosmic_frame'
        )
        
        # Переменные для отслеживания состояния страниц
        first_page_drawn = {'flag': False}
        page_count = {'num': 0}
        document_title = title  # Сохраняем для подписи страницы
        
        # Универсальная функция для всех страниц (Premium Astro Style)
        def page_template_with_image(canvas, doc):
            draw_cosmic_background(canvas, doc)
            page_count['num'] += 1
            
            # Рисуем статичное изображение только на первой странице
            if not first_page_drawn['flag']:
                # Убрана золотая линия под заголовком (чтобы не залезала на имя)
                draw_static_natal_chart_image(canvas, doc, cosmic_gold)
                first_page_drawn['flag'] = True
            
            # Подпись страницы убрана со всех страниц
        
        # Создаём PageTemplate (всегда используем функцию с изображением, даже если chart_data нет)
        cosmic_template = PageTemplate(
            id='cosmic_page',
            frames=[frame],
            onPage=page_template_with_image
        )
        
        doc.addPageTemplates([cosmic_template])

        styles = getSampleStyleSheet()
        
        # Базовый стиль с premium типографикой
        # Межстрочный интервал 1.55-1.65 при размере 15-16pt
        base_style = ParagraphStyle(
            'Base',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=15,  # 15pt согласно premium дизайну
            leading=24,  # 15pt * 1.6 = 24pt (межстрочный 1.6)
            spaceAfter=14,  # Отступы между абзацами 14pt
            textColor=cosmic_text,
            backColor=None,
            alignment=4  # 4 = TA_JUSTIFY (выравнивание по ширине)
        )
        
        # Premium заголовки (Serif premium стиль, но используем доступные шрифты)
        heading_styles = {
            1: ParagraphStyle(
                'H1', 
                parent=base_style, 
                fontSize=36,  # 36pt для заголовка согласно premium дизайну
                leading=44,  # 36pt * 1.22 ≈ 44pt
                spaceBefore=60,  # 60-80px между разделами
                spaceAfter=20,
                textColor=cosmic_gold,
                fontName=font_name,
                alignment=0,  # По левому краю
                # letterSpacing не поддерживается в ReportLab, но можно эмулировать через пробелы
            ),
            2: ParagraphStyle(
                'H2', 
                parent=base_style, 
                fontSize=24,  # 24pt для подзаголовков
                leading=30,  # 24pt * 1.25 = 30pt
                spaceBefore=20,  # Одинаковый отступ перед всеми разделами (как перед первым)
                spaceAfter=18,
                textColor=cosmic_gold,
                fontName=font_name,
                alignment=0  # По левому краю
            ),
            3: ParagraphStyle(
                'H3', 
                parent=base_style, 
                fontSize=18,  # Немного больше базового текста
                leading=26,  # 18pt * 1.44 = 26pt
                spaceBefore=24,
                spaceAfter=14,
                textColor=cosmic_silver,
                fontName=font_name,
                alignment=0  # По левому краю
            ),
        }
        
        # Базовый стиль для вводного текста (такие же отступы как в основном тексте)
        intro_base_style = ParagraphStyle(
            'Intro_Base',
                parent=base_style, 
                fontName=font_name,
            fontSize=15,
                leading=24, 
            spaceAfter=14,  # Одинаковые отступы между абзацами как в основном тексте (14pt)
            textColor=cosmic_text,
            backColor=None,
            alignment=4  # Выравнивание по ширине
        )
        
        # Стиль для пронумерованных пунктов в статичном тексте (обычный текст с золотым цветом)
        intro_numbered_style = ParagraphStyle(
            'Intro_Numbered',
            parent=intro_base_style,
                fontName=font_name,
            fontSize=15,
                leading=24, 
            spaceBefore=0,  # Убран дополнительный отступ перед пронумерованными пунктами
            spaceAfter=14,  # Одинаковые отступы между абзацами как в основном тексте (14pt)
            textColor=cosmic_gold,  # Золотой цвет как у заголовков
            backColor=None,
            alignment=4  # Выравнивание по ширине
        )
        
        # Стили заголовков для вводного текста - используем те же стили что и в основном тексте
        intro_heading_styles = {
            1: heading_styles[1],  # H1 - тот же стиль что и для основных разделов (36pt)
            2: heading_styles[2],  # H2 - тот же стиль что и для подзаголовков (24pt)
            3: heading_styles[3],  # H3 - тот же стиль что и для подзаголовков третьего уровня (18pt)
        }
        
        # Premium стиль для заголовка документа (по центру, 36pt)
        title_style = ParagraphStyle(
            'Title', 
            parent=base_style, 
            fontSize=36,  # 36pt согласно premium дизайну
            leading=44,  # Межстрочный ~1.22
            alignment=1,  # 1 = TA_CENTER (по центру)
            spaceAfter=32,  # Отступ перед золотой линией (32-48px)
            textColor=cosmic_gold,
            fontName=font_name
        )

        story = []
        
        # ===== СТРАНИЦА 1: ТИТУЛЬНЫЙ ЛИСТ =====
        # Заголовок документа с premium оформлением
        if title:
            title_text = f"<b>{_clean_inline_markdown(title)}</b>"
            story.append(Paragraph(title_text, title_style))
            # Золотая линия убрана, изображение теперь по центру страницы
            # Добавляем отступ для визуального баланса
            story.append(Spacer(1, 30))
        
        # Изображение теперь рисуется по центру страницы в функции onPage
        # Не нужно добавлять Spacer, так как изображение позиционируется абсолютно
        
        # ===== РАЗРЫВ СТРАНИЦЫ =====
        story.append(PageBreak())
        
        # Сначала обрабатываем весь контент для создания Paragraph объектов с якорями
        # Затем добавим их в story в правильном порядке (содержание -> вводный -> основной)
        main_content = []  # Основной контент с якорями
        intro_content = []  # Вводный текст
        
        # Обрабатываем вводный текст
        intro_lines = INTRODUCTORY_TEXT.split('\n')
        for raw_line in intro_lines:
            line = raw_line.rstrip('\r')
            if not line.strip():
                # Не добавляем Spacer для пустых строк, чтобы отступы были одинаковые как в основном тексте
                # spaceAfter=14 из стиля сам добавит отступы между абзацами
                continue
            
            stripped = line.lstrip()
            
            # Пропускаем строки с разделителями "---"
            if stripped.strip() == '---':
                continue
            
            heading_level = 0
            is_numbered_item = False
            
            if stripped.startswith('#'):
                heading_level = len(stripped) - len(stripped.lstrip('#'))
                stripped = stripped.lstrip('#').strip()
                
                # Убраны символы ✦ из заголовков
                
                # Проверяем, является ли это пронумерованным пунктом (например "4. Разбор не заменяет")
                # Паттерн: начинается с цифры и точки
                if re.match(r'^\d+\.\s', stripped):
                    is_numbered_item = True
                    heading_level = 0  # Не обрабатываем как заголовок
            
            bullet = False
            if stripped.startswith(('- ', '* ', '+ ')):
                bullet = True
                stripped = stripped[2:].strip()
                bullet_char = "✦"
            
            cleaned = _clean_inline_markdown(stripped)
            
            if is_numbered_item:
                # Пронумерованные пункты - обычный текст с золотым цветом (15pt)
                intro_content.append(Paragraph(cleaned, intro_numbered_style))
            elif heading_level:
                # Все заголовки используют стиль H2 (24pt)
                intro_content.append(Paragraph(cleaned, heading_styles[2]))
            elif bullet:
                intro_content.append(Paragraph(f"{bullet_char} {cleaned}", intro_base_style))
            else:
                intro_content.append(Paragraph(cleaned, intro_base_style))
        
        # Обрабатываем основной контент для создания якорей
        for raw_line in lines:
            line = raw_line.rstrip('\r')
            if line.strip() == '[[PAGE_BREAK]]':
                main_content.append(PageBreak())
                continue
            if not line.strip():
                main_content.append(Spacer(1, 10))
                continue

            stripped = line.lstrip()
            
            # Пропускаем пустые строки СРАЗУ, до любой обработки
            if not stripped:
                continue
            
            heading_level = 0
            if stripped.startswith('#'):
                heading_level = len(stripped) - len(stripped.lstrip('#'))
                stripped = stripped.lstrip('#').strip()
                
                # Убраны символы ✦ из заголовков
                
                # Проверяем, что после удаления # остался текст
                if not stripped:
                    continue

            bullet = False
            if stripped.startswith(('- ', '* ', '+ ')):
                bullet = True
                stripped = stripped[2:].strip()
                # Космические символы для списков
                bullet_char = "✦"
                
                # Проверяем, что после удаления маркера остался текст
                if not stripped:
                    continue
                
            cleaned = _clean_inline_markdown(stripped)
            
            # Якоря убраны - заголовки больше не имеют якорей для навигации
            
            if heading_level:
                # Все заголовки используют стиль H2 (24pt)
                # Для первого раздела после PageBreak убираем spaceBefore, чтобы отступ был одинаковым
                # Проверяем, является ли это первым разделом (H2) после PageBreak
                if heading_level == 2:
                    # Создаем стиль без spaceBefore для первого раздела после PageBreak
                    # Но нам нужно отследить, был ли перед этим PageBreak
                    # Для простоты - убираем spaceBefore у всех разделов, чтобы они были одинаковыми
                    first_section_style = ParagraphStyle(
                        'H2_NoSpace',
                        parent=heading_styles[2],
                        spaceBefore=0  # Убираем отступ для единообразия
                    )
                    main_content.append(Paragraph(cleaned, first_section_style))
                else:
                    main_content.append(Paragraph(cleaned, heading_styles[heading_level]))
            elif bullet:
                main_content.append(Paragraph(f"{bullet_char} {cleaned}", base_style))
            else:
                main_content.append(Paragraph(cleaned, base_style))
        
        # Теперь добавляем в story в правильном порядке: содержание -> вводный -> основной контент
        
        # ===== СТРАНИЦА 2: СОДЕРЖАНИЕ =====
        # Извлекаем заголовки разделов для содержания
        section_headings = _extract_section_headings(markdown_text)
        
        # Стиль для заголовка "Содержание"
        toc_title_style = ParagraphStyle(
            'TOC_Title',
            parent=base_style,
            fontSize=24,
            leading=30,
            spaceBefore=20,
            spaceAfter=20,
            textColor=cosmic_gold,
            fontName=font_name,
            alignment=1  # По центру
        )
        
        # Стиль для пунктов содержания
        toc_item_style = ParagraphStyle(
            'TOC_Item',
            parent=base_style,
            fontSize=16,
            leading=24,
            spaceAfter=10,
            textColor=cosmic_text,
            fontName=font_name,
            alignment=0,  # По левому краю
            leftIndent=0
        )
        
        story.append(Paragraph("<b>Содержание</b>", toc_title_style))
        story.append(Spacer(1, 20))
        
        # Добавляем пункты содержания (без кликабельных ссылок)
        # Используем тот же цвет что и заголовок "Содержание" (cosmic_gold)
        toc_item_style_gold = ParagraphStyle(
            'TOC_Item_Gold',
            parent=toc_item_style,
            textColor=cosmic_gold,  # Золотой цвет как у заголовка "Содержание"
        )
        for level, heading_text, anchor_name in section_headings:
            cleaned_heading = _clean_inline_markdown(heading_text)
            # Обычный текст без ссылок
            story.append(Paragraph(cleaned_heading, toc_item_style_gold))
        
        # ===== РАЗРЫВ СТРАНИЦЫ =====
        story.append(PageBreak())
        
        # ===== СТРАНИЦА 3: ВВОДНЫЙ ТЕКСТ =====
        # Добавляем заголовок "Вводное слово"
        intro_title_cleaned = _clean_inline_markdown("Вводное слово")
        story.append(Paragraph(intro_title_cleaned, heading_styles[2]))  # Используем H2 стиль (24pt)
        # Убран Spacer - отступ формируется через spaceAfter=18 в стиле заголовка для единообразия
        
        # Добавляем вводный текст
        story.extend(intro_content)
        
        # ===== РАЗРЫВ СТРАНИЦЫ =====
        story.append(PageBreak())
        
        # ===== ОСНОВНОЙ КОНТЕНТ =====
        # Добавляем основной контент с якорями
        story.extend(main_content)

        if not story:
            story.append(Paragraph("Данные недоступны.", base_style))

        # Собираем документ (PageTemplate уже добавлен выше)
        logger.info(f"📄 Создание PDF документа (используется шрифт: {font_name})...")
        doc.build(story)
        logger.info(f"✅ PDF успешно создан: {temp_path}")
        return temp_path
    except Exception as pdf_error:
        error_type = type(pdf_error).__name__
        error_message = str(pdf_error)
        import traceback
        error_traceback = traceback.format_exc()
        
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА при формировании PDF: {error_type}: {error_message}", exc_info=True)
        logger.error(f"   Использовался шрифт: {font_name}")
        logger.error(f"   Длина текста: {len(markdown_text) if markdown_text else 0} символов")
        logger.error(f"   Количество строк: {len(lines) if lines else 0}")
        
        # Сохраняем детали ошибки для последующего логирования (будет залогировано в generate_natal_chart_background)
        # Здесь мы только логируем в консоль, т.к. у нас нет доступа к user_id
        
        return None


async def natal_chart_start(query, context):
    """Начало создания натальной карты"""
    user_id = query.from_user.id
    log_event(user_id, 'profile_filling_start', {})
    
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
    ]])
    
    await query.edit_message_text(
        "📜 *Создание натальной карты*\n\n"
        "💡 Вы можете ввести данные любого человека для расчета натальной карты.\n\n"
        "Пожалуйста, введите имя (дальше я запрошу остальные данные):",
        reply_markup=buttons,
        parse_mode='Markdown'
    )
    context.user_data['natal_chart_state'] = 'name'


async def handle_natal_chart_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода данных для натальной карты"""
    text = update.message.text
    user_data = context.user_data
    
    if 'natal_chart_state' not in user_data:
        return
    
    state = user_data['natal_chart_state']
    
    back_button = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
    ]])
    
    if state == 'name':
        user_id = update.message.from_user.id
        user_data['birth_name'] = text
        user_data['natal_chart_state'] = 'date'
        log_event(user_id, 'profile_field_entered', {'field': 'name', 'step': 1, 'total_steps': 4})
        await update.message.reply_text(
            "✅ Имя сохранено!\n\n"
            "📅 Теперь введите дату рождения в формате: ДД.ММ.ГГГГ\n"
            "Например: 15.03.1990",
            reply_markup=back_button
        )
    elif state == 'date':
        user_id = update.message.from_user.id
        is_valid, error_msg = validate_date(text)
        if not is_valid:
            log_event(user_id, 'profile_field_validation_error', {'field': 'date', 'error': error_msg})
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите дату в правильном формате: ДД.ММ.ГГГГ\n"
                "Например: 15.03.1990",
                reply_markup=back_button
            )
            return
        
        user_id = update.message.from_user.id
        user_data['birth_date'] = text
        user_data['natal_chart_state'] = 'time'
        log_event(user_id, 'profile_field_entered', {'field': 'date', 'step': 2, 'total_steps': 4})
        await update.message.reply_text(
            "✅ Дата рождения сохранена!\n\n"
            "🕐 Теперь введите время рождения в формате: ЧЧ:ММ\n"
            "Например: 14:30",
            reply_markup=back_button
        )
    elif state == 'time':
        user_id = update.message.from_user.id
        is_valid, error_msg = validate_time(text)
        if not is_valid:
            log_event(user_id, 'profile_field_validation_error', {'field': 'time', 'error': error_msg})
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите время в правильном формате: ЧЧ:ММ\n"
                "Например: 14:30",
                reply_markup=back_button
            )
            return
        
        user_id = update.message.from_user.id
        user_data['birth_time'] = text
        user_data['natal_chart_state'] = 'place'
        log_event(user_id, 'profile_field_entered', {'field': 'time', 'step': 3, 'total_steps': 4})
        await update.message.reply_text(
            "✅ Время рождения сохранено!\n\n"
            "🌍 Теперь введите место рождения (город, страна)\n"
            "Например: Москва, Россия",
            reply_markup=back_button
        )
    elif state == 'place':
        user_id = update.message.from_user.id
        is_valid, error_msg = validate_place(text)
        if not is_valid:
            log_event(user_id, 'profile_field_validation_error', {'field': 'place', 'error': error_msg})
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите место рождения (город, страна)\n"
                "Например: Москва, Россия",
                reply_markup=back_button
            )
            return
        
        user_data['birth_place'] = text
        user_data['natal_chart_state'] = 'complete'
        
        log_event(user_id, 'profile_field_entered', {'field': 'place', 'step': 4, 'total_steps': 4})
        save_user_profile(user_id, user_data)
        
        # Логируем полное заполнение профиля
        log_event(user_id, 'profile_complete', {
            'birth_name': user_data.get('birth_name'),
            'birth_date': user_data.get('birth_date'),
            'birth_time': user_data.get('birth_time'),
            'birth_place': user_data.get('birth_place'),
            'source': 'initial_fill'
        })
        
        await update.message.reply_text(
            "✅ *Профиль успешно сохранен!*\n\n"
            "Теперь вы можете получить свою натальную карту.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 Получить натальную карту", callback_data='natal_chart')],
                [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
            ])
        )
        
        user_data.pop('natal_chart_state', None)
    
    # Обработка редактирования полей
    elif state == 'edit_name':
        user_id = update.message.from_user.id
        logger.info(f"✏️ Редактирование имени для пользователя {user_id}: '{text}'")
        
        # Сохраняем имя в user_data
        user_data['birth_name'] = text
        # НЕ удаляем natal_chart_state здесь - удалим после успешного показа профиля
        
        # Сохраняем профиль в базу
        try:
            save_user_profile(user_id, user_data)
            log_event(user_id, 'profile_field_edited', {'field': 'name', 'value': text})
            
            # Проверяем, стал ли профиль полным после редактирования
            if is_profile_complete(user_data):
                log_event(user_id, 'profile_complete', {
                    'birth_name': user_data.get('birth_name'),
                    'birth_date': user_data.get('birth_date'),
                    'birth_time': user_data.get('birth_time'),
                    'birth_place': user_data.get('birth_place'),
                    'source': 'edit'
                })
            
            logger.info(f"✅ Имя пользователя {user_id} успешно сохранено в БД: {text}")
        except Exception as save_error:
            logger.error(f"❌ Ошибка при сохранении имени пользователя {user_id}: {save_error}", exc_info=True)
            # Продолжаем, даже если сохранение не удалось
        
        # Удаляем состояние после успешного сохранения
        user_data.pop('natal_chart_state', None)
        
        # Загружаем полный профиль из базы, чтобы показать все данные
        try:
            loaded_data = load_user_profile(user_id)
            if loaded_data:
                # Объединяем: сначала данные из базы, потом переданные (переданные имеют приоритет)
                user_data = {**loaded_data, **user_data}
        except Exception as load_error:
            logger.warning(f"⚠️ Ошибка при загрузке профиля пользователя {user_id} из базы: {load_error}")
            # Продолжаем с переданными данными
        
        # Показываем профиль с обновленными данными напрямую
        logger.info(f"📤 Показ профиля пользователю {user_id} после редактирования имени. user_data: {user_data}")
        try:
            profile_text, keyboard = get_profile_message_and_buttons(user_id, user_data)
            await update.message.reply_text(
                profile_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            logger.info(f"✅ Профиль пользователя {user_id} успешно показан после редактирования имени")
        except Exception as show_error:
            error_str = str(show_error)
            logger.error(f"❌ Ошибка при показе профиля пользователя {user_id}: {show_error}", exc_info=True)
            # Проверяем, не является ли ошибка связанной с закрытым event loop
            if 'Event loop is closed' in error_str or 'event loop is closed' in error_str.lower():
                logger.warning(f"⚠️ Event loop закрыт, пропускаем повторную попытку отправки для пользователя {user_id}")
                # Не пытаемся делать еще один await, так как event loop закрыт
                return
            # Если не удалось показать профиль, пытаемся загрузить из базы и показать снова
            try:
                loaded_data = load_user_profile(user_id)
                if loaded_data:
                    profile_text, keyboard = get_profile_message_and_buttons(user_id, loaded_data)
                    await update.message.reply_text(
                        profile_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Профиль пользователя {user_id} успешно показан после редактирования имени (fallback)")
                else:
                    # Если не удалось загрузить из базы, показываем сообщение с кнопкой для просмотра профиля
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
            except Exception as fallback_error:
                fallback_error_str = str(fallback_error)
                logger.error(f"❌ Критическая ошибка: не удалось отправить сообщение пользователю {user_id}: {fallback_error}", exc_info=True)
                # Проверяем, не является ли ошибка связанной с закрытым event loop
                if 'Event loop is closed' in fallback_error_str or 'event loop is closed' in fallback_error_str.lower():
                    logger.warning(f"⚠️ Event loop закрыт в fallback, пропускаем отправку для пользователя {user_id}")
                    return
                # Последняя попытка - просто сообщение
                try:
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
                except:
                    pass
    
    elif state == 'edit_date':
        user_id = update.message.from_user.id
        is_valid, error_msg = validate_date(text)
        if not is_valid:
            log_event(user_id, 'profile_field_validation_error', {'field': 'date', 'error': error_msg, 'context': 'edit'})
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите дату в правильном формате: ДД.ММ.ГГГГ",
                reply_markup=back_button
            )
            return
        user_data['birth_date'] = text
        user_data.pop('natal_chart_state', None)
        user_id = update.message.from_user.id
        save_user_profile(user_id, user_data)
        log_event(user_id, 'profile_field_edited', {'field': 'date'})
        
        # Проверяем, стал ли профиль полным после редактирования
        if is_profile_complete(user_data):
            log_event(user_id, 'profile_complete', {
                'birth_name': user_data.get('birth_name'),
                'birth_date': user_data.get('birth_date'),
                'birth_time': user_data.get('birth_time'),
                'birth_place': user_data.get('birth_place'),
                'source': 'edit'
            })
        # Сразу показываем профиль вместо сообщения об успехе
        try:
            await show_profile_message(update, user_data)
        except Exception as show_error:
            error_str = str(show_error)
            logger.error(f"❌ Ошибка при показе профиля пользователя {user_id}: {show_error}", exc_info=True)
            # Проверяем, не является ли ошибка связанной с закрытым event loop
            if 'Event loop is closed' in error_str or 'event loop is closed' in error_str.lower():
                logger.warning(f"⚠️ Event loop закрыт, пропускаем повторную попытку отправки для пользователя {user_id}")
                return
            # Если не удалось показать профиль, пытаемся загрузить из базы и показать снова
            try:
                loaded_data = load_user_profile(user_id)
                if loaded_data:
                    profile_text, keyboard = get_profile_message_and_buttons(user_id, loaded_data)
                    await update.message.reply_text(
                        profile_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Профиль пользователя {user_id} успешно показан после редактирования даты (fallback)")
                else:
                    # Если не удалось загрузить из базы, показываем сообщение с кнопкой для просмотра профиля
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
            except Exception as fallback_error:
                fallback_error_str = str(fallback_error)
                logger.error(f"❌ Критическая ошибка при показе профиля пользователю {user_id}: {fallback_error}", exc_info=True)
                # Проверяем, не является ли ошибка связанной с закрытым event loop
                if 'Event loop is closed' in fallback_error_str or 'event loop is closed' in fallback_error_str.lower():
                    logger.warning(f"⚠️ Event loop закрыт в fallback, пропускаем отправку для пользователя {user_id}")
                    return
                # Последняя попытка - просто сообщение
                try:
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
                except:
                    pass
    
    elif state == 'edit_time':
        user_id = update.message.from_user.id
        is_valid, error_msg = validate_time(text)
        if not is_valid:
            log_event(user_id, 'profile_field_validation_error', {'field': 'time', 'error': error_msg, 'context': 'edit'})
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите время в правильном формате: ЧЧ:ММ",
                reply_markup=back_button
            )
            return
        user_data['birth_time'] = text
        user_data.pop('natal_chart_state', None)
        user_id = update.message.from_user.id
        save_user_profile(user_id, user_data)
        log_event(user_id, 'profile_field_edited', {'field': 'time'})
        
        # Проверяем, стал ли профиль полным после редактирования
        if is_profile_complete(user_data):
            log_event(user_id, 'profile_complete', {
                'birth_name': user_data.get('birth_name'),
                'birth_date': user_data.get('birth_date'),
                'birth_time': user_data.get('birth_time'),
                'birth_place': user_data.get('birth_place'),
                'source': 'edit'
            })
        # Сразу показываем профиль вместо сообщения об успехе
        try:
            await show_profile_message(update, user_data)
        except Exception as show_error:
            error_str = str(show_error)
            logger.error(f"❌ Ошибка при показе профиля пользователя {user_id}: {show_error}", exc_info=True)
            # Проверяем, не является ли ошибка связанной с закрытым event loop
            if 'Event loop is closed' in error_str or 'event loop is closed' in error_str.lower():
                logger.warning(f"⚠️ Event loop закрыт, пропускаем повторную попытку отправки для пользователя {user_id}")
                return
            # Если не удалось показать профиль, пытаемся загрузить из базы и показать снова
            try:
                loaded_data = load_user_profile(user_id)
                if loaded_data:
                    profile_text, keyboard = get_profile_message_and_buttons(user_id, loaded_data)
                    await update.message.reply_text(
                        profile_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Профиль пользователя {user_id} успешно показан после редактирования времени (fallback)")
                else:
                    # Если не удалось загрузить из базы, показываем сообщение с кнопкой для просмотра профиля
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
            except Exception as fallback_error:
                fallback_error_str = str(fallback_error)
                logger.error(f"❌ Критическая ошибка при показе профиля пользователю {user_id}: {fallback_error}", exc_info=True)
                # Проверяем, не является ли ошибка связанной с закрытым event loop
                if 'Event loop is closed' in fallback_error_str or 'event loop is closed' in fallback_error_str.lower():
                    logger.warning(f"⚠️ Event loop закрыт в fallback, пропускаем отправку для пользователя {user_id}")
                    return
                # Последняя попытка - просто сообщение
                try:
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
                except:
                    pass
    
    elif state == 'edit_place':
        user_id = update.message.from_user.id
        is_valid, error_msg = validate_place(text)
        if not is_valid:
            log_event(user_id, 'profile_field_validation_error', {'field': 'place', 'error': error_msg, 'context': 'edit'})
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите место рождения",
                reply_markup=back_button
            )
            return
        user_data['birth_place'] = text
        user_data.pop('natal_chart_state', None)
        user_id = update.message.from_user.id
        save_user_profile(user_id, user_data)
        log_event(user_id, 'profile_field_edited', {'field': 'place'})
        
        # Проверяем, стал ли профиль полным после редактирования
        if is_profile_complete(user_data):
            log_event(user_id, 'profile_complete', {
                'birth_name': user_data.get('birth_name'),
                'birth_date': user_data.get('birth_date'),
                'birth_time': user_data.get('birth_time'),
                'birth_place': user_data.get('birth_place'),
                'source': 'edit'
            })
        # Сразу показываем профиль вместо сообщения об успехе
        try:
            await show_profile_message(update, user_data)
        except Exception as show_error:
            error_str = str(show_error)
            logger.error(f"❌ Ошибка при показе профиля пользователя {user_id}: {show_error}", exc_info=True)
            # Проверяем, не является ли ошибка связанной с закрытым event loop
            if 'Event loop is closed' in error_str or 'event loop is closed' in error_str.lower():
                logger.warning(f"⚠️ Event loop закрыт, пропускаем повторную попытку отправки для пользователя {user_id}")
                return
            # Если не удалось показать профиль, пытаемся загрузить из базы и показать снова
            try:
                loaded_data = load_user_profile(user_id)
                if loaded_data:
                    profile_text, keyboard = get_profile_message_and_buttons(user_id, loaded_data)
                    await update.message.reply_text(
                        profile_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Профиль пользователя {user_id} успешно показан после редактирования места (fallback)")
                else:
                    # Если не удалось загрузить из базы, показываем сообщение с кнопкой для просмотра профиля
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
            except Exception as fallback_error:
                fallback_error_str = str(fallback_error)
                logger.error(f"❌ Критическая ошибка при показе профиля пользователю {user_id}: {fallback_error}", exc_info=True)
                # Проверяем, не является ли ошибка связанной с закрытым event loop
                if 'Event loop is closed' in fallback_error_str or 'event loop is closed' in fallback_error_str.lower():
                    logger.warning(f"⚠️ Event loop закрыт в fallback, пропускаем отправку для пользователя {user_id}")
                    return
                # Последняя попытка - просто сообщение
                try:
                    await update.message.reply_text(
                        "Профиль обновлен.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
                            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                        ]])
                    )
                except:
                    pass


def get_coordinates_from_place(place_str: str) -> Tuple[Optional[float], Optional[float]]:
    """Получение координат (широта, долгота) из названия места рождения."""
    try:
        geolocator = Nominatim(user_agent="astral_bot")
        location = geolocator.geocode(place_str, timeout=10)
        if location:
            return location.latitude, location.longitude
        logger.warning(f"Не удалось найти координаты для места: {place_str}")
        return None, None
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.error(f"Ошибка геокодирования: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при геокодировании: {e}")
        return None, None


def resolve_timezone_from_place(place_str: str, lat: float, lon: float, naive_local_dt: datetime):
    """
    Определяет таймзону без timezonefinder.
    Стратегия:
    1) reverse-geocode -> country_code
    2) если у страны 1 таймзона — берём её
    3) если несколько — выбираем ближайшую к долготе по UTC offset на дату рождения
    """
    place_lower = (place_str or "").lower()
    city_overrides = {
        "моск": "Europe/Moscow",
        "moscow": "Europe/Moscow",
        "питер": "Europe/Moscow",
        "saint petersburg": "Europe/Moscow",
        "новосибир": "Asia/Novosibirsk",
        "екатерин": "Asia/Yekaterinburg",
        "владивост": "Asia/Vladivostok",
        "new york": "America/New_York",
        "лос-анджел": "America/Los_Angeles",
        "los angeles": "America/Los_Angeles",
        "london": "Europe/London",
        "лондон": "Europe/London",
        "berlin": "Europe/Berlin",
        "берлин": "Europe/Berlin",
    }
    for key, tz_name in city_overrides.items():
        if key in place_lower:
            tz = pytz.timezone(tz_name)
            logger.info("Таймзона определена по городу '%s': %s", place_str, tz.zone)
            return tz

    def tz_from_longitude():
        # 1 градус долготы ~= 4 минуты смещения UTC.
        minutes = int(round(lon * 4))
        tz = pytz.FixedOffset(minutes)
        logger.info("Таймзона определена по долготе (lon=%.4f): UTC%+.2f", lon, minutes / 60.0)
        return tz

    try:
        geolocator = Nominatim(user_agent="astral_bot")
        location = geolocator.reverse(
            (lat, lon),
            exactly_one=True,
            language="en",
            timeout=10,
            addressdetails=True,
            zoom=10,
        )

        country_code = None
        if location and location.raw:
            address = location.raw.get("address", {}) or {}
            country_code = (address.get("country_code") or "").upper()

        if not country_code:
            logger.warning("Не удалось определить country_code для %s, %s. Используется fallback по долготе.", lat, lon)
            return tz_from_longitude()

        country_timezones = pytz.country_timezones.get(country_code)
        if not country_timezones:
            logger.warning("Для country_code=%s не найдены таймзоны. Используется fallback по долготе.", country_code)
            return tz_from_longitude()

        if len(country_timezones) == 1:
            tz = pytz.timezone(country_timezones[0])
            logger.info("Таймзона определена по стране (%s): %s", country_code, tz.zone)
            return tz

        target_offset = int(round(lon / 15.0))
        best_tz_name = None
        best_score = float("inf")

        for tz_name in country_timezones:
            try:
                tz = pytz.timezone(tz_name)
                try:
                    local_dt = tz.localize(naive_local_dt, is_dst=None)
                except Exception:
                    local_dt = tz.localize(naive_local_dt, is_dst=False)
                offset_hours = local_dt.utcoffset().total_seconds() / 3600.0
                score = abs(offset_hours - target_offset)
                if score < best_score:
                    best_score = score
                    best_tz_name = tz_name
            except Exception:
                continue

        if best_tz_name:
            tz = pytz.timezone(best_tz_name)
            logger.info(
                "Таймзона определена по стране/долготе (%s, lon=%.4f): %s",
                country_code,
                lon,
                tz.zone,
            )
            return tz

        logger.warning("Не удалось выбрать таймзону из списка страны %s. Используется fallback по долготе.", country_code)
        return tz_from_longitude()
    except Exception as err:
        logger.warning("Ошибка определения таймзоны для '%s': %s. Используется fallback по долготе.", place_str, err)
        return tz_from_longitude()


def calculate_natal_chart(birth_data: dict) -> dict:
    """
    Расчет натальной карты через Swiss Ephemeris.
    Возвращает словарь с данными о планетах, домах, узлах, аспектах.
    """
    try:
        # Парсинг даты и времени
        date_str = birth_data.get('date', '')
        time_str = birth_data.get('time', '')
        place_str = birth_data.get('place', '')
        
        logger.info(f"Расчет натальной карты для: дата={date_str}, время={time_str}, место={place_str}")
        
        if not date_str or not time_str or not place_str:
            raise ValueError("Не указаны дата, время или место рождения")
        
        # Парсинг даты (формат: ДД.ММ.ГГГГ)
        try:
            day, month, year = map(int, date_str.split('.'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Некорректный формат даты: {date_str}. Ожидается ДД.ММ.ГГГГ")
        
        # Парсинг времени (формат: ЧЧ:ММ)
        try:
            hour, minute = map(int, time_str.split(':'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Некорректный формат времени: {time_str}. Ожидается ЧЧ:ММ")
        
        # Валидация даты
        try:
            test_date = datetime(year, month, day)
        except ValueError as e:
            raise ValueError(f"Некорректная дата: {day}.{month}.{year}")
        
        # Валидация времени
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise ValueError(f"Некорректное время: {hour}:{minute}")
        
        # Получение координат места рождения
        lat, lon = get_coordinates_from_place(place_str)
        if lat is None or lon is None:
            # Используем дефолтные координаты (Москва) если не удалось определить
            logger.warning(f"Используются координаты по умолчанию для места: {place_str}")
            lat, lon = 55.7558, 37.6173  # Москва
        
        logger.info(f"Координаты места рождения: широта={lat}, долгота={lon}")
        
        # Определение таймзоны без timezonefinder (через geopy + pytz)
        naive_local_dt = datetime(year, month, day, hour, minute)
        tz = resolve_timezone_from_place(place_str, lat, lon, naive_local_dt)
        logger.info("Часовой пояс места рождения: %s", getattr(tz, "zone", str(tz)))
        
        # Создание datetime объекта в локальном времени места рождения
        local_dt = tz.localize(naive_local_dt)
        
        # Конвертация в UTC (Swiss Ephemeris работает с UTC)
        utc_dt = local_dt.astimezone(pytz.UTC)
        
        logger.info(f"Локальное время: {local_dt}, UTC: {utc_dt}")
        
        # Расчет юлианской даты в UTC
        # Вариант А (правильный): передаём час сразу в swe.julday
        hour_decimal = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
        jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour_decimal, swe.GREG_CAL)
        
        logger.info(f"Юлианская дата (UTC): {jd}")
        
        # Константы планет в Swiss Ephemeris
        PLANETS = {
            'Sun': swe.SUN,
            'Moon': swe.MOON,
            'Mercury': swe.MERCURY,
            'Venus': swe.VENUS,
            'Mars': swe.MARS,
            'Jupiter': swe.JUPITER,
            'Saturn': swe.SATURN,
            'Uranus': swe.URANUS,
            'Neptune': swe.NEPTUNE,
            'Pluto': swe.PLUTO,
        }
        
        # Расчет положений планет
        planets_data = {}
        retrograde_planets = []
        
        for planet_name, planet_id in PLANETS.items():
            # Расчет положения планеты
            result = swe.calc_ut(jd, planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED)
            # В Swiss Ephemeris result[0] - это ТУПЛЬ с данными, result[1] - код возврата
            # Проверяем наличие данных в result[0]
            if len(result) >= 2 and result[0] is not None and len(result[0]) >= 4:
                longitude = result[0][0]  # Долгота в градусах
                latitude = result[0][1]   # Широта в градусах
                distance = result[0][2]   # Расстояние
                speed = result[0][3]      # Скорость (отрицательная = ретроградность)
                
                # Нормализуем долготу в диапазон 0-360
                longitude = longitude % 360
                
                # Определение знака зодиака (0-11: Овен-Рыбы)
                sign_num = int(longitude / 30) % 12
                sign_degrees = longitude % 30
                
                signs = ['Овен', 'Телец', 'Близнецы', 'Рак', 'Лев', 'Дева',
                        'Весы', 'Скорпион', 'Стрелец', 'Козерог', 'Водолей', 'Рыбы']
                
                is_retrograde = speed < 0
                if is_retrograde:
                    retrograde_planets.append(planet_name)
                
                planets_data[planet_name] = {
                    'longitude': longitude,
                    'latitude': latitude,
                    'distance': distance,
                    'speed': speed,
                    'sign': signs[sign_num],
                    'sign_degrees': sign_degrees,
                    'is_retrograde': is_retrograde,
                }
                logger.info(f"{planet_name}: {signs[sign_num]} {sign_degrees:.2f}° (долгота: {longitude:.2f}°), ретроградность: {is_retrograde}")
            else:
                logger.error(f"Ошибка расчета для планеты {planet_name}: некорректные данные в result = {result}")
        
        # Расчет Лунных узлов
        node_result = swe.calc_ut(jd, swe.TRUE_NODE, swe.FLG_SWIEPH)
        # В Swiss Ephemeris result[0] - это ТУПЛЬ с данными, result[1] - код возврата
        if len(node_result) >= 2 and node_result[0] is not None and len(node_result[0]) >= 1:
            north_node_longitude = node_result[0][0] % 360  # Нормализуем в 0-360
        else:
            logger.error(f"Ошибка расчета лунных узлов: некорректные данные в result = {node_result}")
            north_node_longitude = 0
        north_node_sign_num = int(north_node_longitude / 30) % 12
        north_node_sign_degrees = north_node_longitude % 30
        
        south_node_longitude = (north_node_longitude + 180) % 360
        south_node_sign_num = int(south_node_longitude / 30)
        south_node_sign_degrees = south_node_longitude % 30
        
        signs = ['Овен', 'Телец', 'Близнецы', 'Рак', 'Лев', 'Дева',
                'Весы', 'Скорпион', 'Стрелец', 'Козерог', 'Водолей', 'Рыбы']
        
        # Расчет домов по системе Placidus
        houses_result = swe.houses(jd, lat, lon, b'P')  # 'P' = Placidus
        # В Swiss Ephemeris result[0] - это тупль с куспидами домов (12 элементов для домов 1-12)
        # result[1] - это тупль с ASC/MC и другими данными
        if len(houses_result) >= 2 and houses_result[0] is not None and houses_result[1] is not None:
            houses_cusps_tuple = houses_result[0]  # Тупль с 12 куспидами домов (1-12)
            ascmc = houses_result[1]  # Тупль: ascmc[0] = ASC, ascmc[1] = MC
            # Преобразуем тупль в список для удобства индексирования
            houses_cusps = [0] * 13  # Массив из 13 элементов (индекс 0 не используется)
            for i in range(min(12, len(houses_cusps_tuple))):
                houses_cusps[i+1] = houses_cusps_tuple[i] % 360  # Дома 1-12
            
            houses_asc = ascmc[0] % 360 if len(ascmc) > 0 else 0  # Асцендент, нормализуем в 0-360
            houses_mc = ascmc[1] % 360 if len(ascmc) > 1 else 0   # MC (Medium Coeli)
            houses_ic = (houses_mc + 180) % 360  # IC (Imum Coeli)
            logger.info(f"Дома рассчитаны: ASC={houses_asc:.2f}°, MC={houses_mc:.2f}°, IC={houses_ic:.2f}°")
        else:
            logger.error(f"Ошибка расчета домов: некорректные данные в result = {houses_result}")
            houses_cusps = [0] * 13
            houses_asc = 0
            houses_mc = 0
            houses_ic = 0
        
        # Определение знаков для куспидов домов
        houses_data = {}
        for i in range(1, 13):  # Дома 1-12, индексы в массиве 1-12
            cusp_longitude = houses_cusps[i]
            sign_num = int(cusp_longitude / 30)
            sign_degrees = cusp_longitude % 30
            houses_data[f'House{i}'] = {
                'longitude': cusp_longitude,
                'sign': signs[sign_num],
                'sign_degrees': sign_degrees,
            }
        
        # Определение знаков для ASC, MC, IC
        asc_sign_num = int(houses_asc / 30)
        mc_sign_num = int(houses_mc / 30)
        ic_sign_num = int(houses_ic / 30)
        
        # Расчет аспектов между планетами
        aspects_data = []
        planet_list = list(PLANETS.items())
        
        for i, (p1_name, p1_id) in enumerate(planet_list):
            if p1_name not in planets_data:
                continue
            p1_long = planets_data[p1_name]['longitude']
            
            for j, (p2_name, p2_id) in enumerate(planet_list[i+1:], start=i+1):
                if p2_name not in planets_data:
                    continue
                p2_long = planets_data[p2_name]['longitude']
                
                # Расчет угла между планетами
                angle = abs(p1_long - p2_long)
                if angle > 180:
                    angle = 360 - angle
                
                # Определение аспекта
                aspect_name = None
                orb = None
                
                # Соединение (±6°)
                if angle <= 6 or angle >= 354:
                    aspect_name = "Соединение"
                    orb = min(angle, 360 - angle)
                # Оппозиция (±5°)
                elif 175 <= angle <= 185:
                    aspect_name = "Оппозиция"
                    orb = abs(angle - 180)
                # Квадрат (±5°)
                elif 85 <= angle <= 95:
                    aspect_name = "Квадрат"
                    orb = abs(angle - 90)
                elif 265 <= angle <= 275:
                    aspect_name = "Квадрат"
                    orb = abs(angle - 270)
                # Трин (±4°)
                elif 116 <= angle <= 124:
                    aspect_name = "Трин"
                    orb = abs(angle - 120)
                elif 236 <= angle <= 244:
                    aspect_name = "Трин"
                    orb = abs(angle - 240)
                # Секстиль (±4°)
                elif 56 <= angle <= 64:
                    aspect_name = "Секстиль"
                    orb = abs(angle - 60)
                elif 296 <= angle <= 304:
                    aspect_name = "Секстиль"
                    orb = abs(angle - 300)
                
                if aspect_name:
                    aspects_data.append({
                        'planet1': p1_name,
                        'planet2': p2_name,
                        'aspect': aspect_name,
                        'angle': angle,
                        'orb': orb,
                    })
        
        # Определение планет в домах
        # Стандарт Swiss/Placidus: Cusp_n ≤ Planet < Cusp_(n+1) → планета в доме N
        # Планета принадлежит дому, если её долгота между куспидом текущего и следующего дома
        planets_in_houses = {}
        for planet_name, planet_info in planets_data.items():
            planet_long = planet_info['longitude']
            # Проверяем каждый дом
            for house_num in range(1, 13):
                cusp_current = houses_cusps[house_num]
                # Следующий дом (с учётом цикличности)
                next_house_num = (house_num % 12) + 1
                cusp_next = houses_cusps[next_house_num]
                
                # Проверка: Cusp_n ≤ Planet < Cusp_(n+1)
                if cusp_current <= cusp_next:
                    # Обычный случай: куспиды не переходят через 0°
                    if cusp_current <= planet_long < cusp_next:
                        planets_in_houses[planet_name] = house_num
                        break
                else:
                    # Переход через 0° (wrap-around): дом 12→1
                    if planet_long >= cusp_current or planet_long < cusp_next:
                        planets_in_houses[planet_name] = house_num
                        break
        
        return {
            'planets': planets_data,
            'houses': houses_data,
            'ascendant': {
                'longitude': houses_asc,
                'sign': signs[asc_sign_num],
                'sign_degrees': houses_asc % 30,
            },
            'mc': {
                'longitude': houses_mc,
                'sign': signs[mc_sign_num],
                'sign_degrees': houses_mc % 30,
            },
            'ic': {
                'longitude': houses_ic,
                'sign': signs[ic_sign_num],
                'sign_degrees': houses_ic % 30,
            },
            'north_node': {
                'longitude': north_node_longitude,
                'sign': signs[north_node_sign_num],
                'sign_degrees': north_node_sign_degrees,
            },
            'south_node': {
                'longitude': south_node_longitude,
                'sign': signs[south_node_sign_num],
                'sign_degrees': south_node_sign_degrees,
            },
            'retrograde_planets': retrograde_planets,
            'aspects': aspects_data,
            'planets_in_houses': planets_in_houses,
        }
        
    except Exception as e:
        logger.error(f"Ошибка при расчете натальной карты: {e}", exc_info=True)
        raise


def format_natal_chart_data(chart_data: dict) -> str:
    """
    Форматирование данных натальной карты в текстовый формат для передачи в промпт.
    """
    lines = []
    
    lines.append("=== ТОЧНЫЕ АСТРОЛОГИЧЕСКИЕ ДАННЫЕ (Swiss Ephemeris, Placidus, Тропический зодиак) ===")
    lines.append("ВСЕ УКАЗАННЫЕ НИЖЕ ДАННЫЕ РАССЧИТАНЫ АВТОМАТИЧЕСКИ И ЯВЛЯЮТСЯ ТОЧНЫМИ.")
    lines.append("ИСПОЛЬЗУЙ ТОЛЬКО ЭТИ ДАННЫЕ ДЛЯ ИНТЕРПРЕТАЦИИ. НЕ ПРИДУМЫВАЙ И НЕ ИЗМЕНЯЙ ИХ.\n")
    
    # Планеты
    lines.append("ПОЛОЖЕНИЕ ЛИЧНЫХ ПЛАНЕТ:")
    planet_ru = {
        'Sun': 'Солнце',
        'Moon': 'Луна',
        'Mercury': 'Меркурий',
        'Venus': 'Венера',
        'Mars': 'Марс',
        'Jupiter': 'Юпитер',
        'Saturn': 'Сатурн',
        'Uranus': 'Уран',
        'Neptune': 'Нептун',
        'Pluto': 'Плутон',
    }
    
    personal_planets = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars']
    for planet_name in personal_planets:
        if planet_name in chart_data['planets']:
            planet_info = chart_data['planets'][planet_name]
            planet_name_ru = planet_ru.get(planet_name, planet_name)
            retrograde = " (R)" if planet_info['is_retrograde'] else ""
            lines.append(
                f"  {planet_name_ru}: {planet_info['sign']} {planet_info['sign_degrees']:.1f}°{retrograde}"
            )
    
    lines.append("\nПОЛОЖЕНИЕ СОЦИАЛЬНЫХ ПЛАНЕТ:")
    social_planets = ['Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto']
    for planet_name in social_planets:
        if planet_name in chart_data['planets']:
            planet_info = chart_data['planets'][planet_name]
            planet_name_ru = planet_ru.get(planet_name, planet_name)
            retrograde = " (R)" if planet_info['is_retrograde'] else ""
            lines.append(
                f"  {planet_name_ru}: {planet_info['sign']} {planet_info['sign_degrees']:.1f}°{retrograde}"
            )
    
    # Ретроградные планеты
    if chart_data['retrograde_planets']:
        retro_list = [planet_ru.get(p, p) for p in chart_data['retrograde_planets']]
        lines.append(f"\nРЕТРОГРАДНЫЕ ПЛАНЕТЫ НА МОМЕНТ РОЖДЕНИЯ:")
        for retro_planet in chart_data['retrograde_planets']:
            lines.append(f"  • {planet_ru.get(retro_planet, retro_planet)}")
    else:
        lines.append("\nРЕТРОГРАДНЫЕ ПЛАНЕТЫ НА МОМЕНТ РОЖДЕНИЯ: нет")
    
    # Угловые точки (важно показать первыми)
    lines.append("\nУГЛОВЫЕ ТОЧКИ КАРТЫ:")
    lines.append(f"  АСЦЕНДЕНТ (ASC): {chart_data['ascendant']['sign']} "
                 f"{chart_data['ascendant']['sign_degrees']:.1f}°")
    lines.append(f"  MC (Середина неба): {chart_data['mc']['sign']} "
                 f"{chart_data['mc']['sign_degrees']:.1f}°")
    lines.append(f"  IC (Глубина неба): {chart_data['ic']['sign']} "
                 f"{chart_data['ic']['sign_degrees']:.1f}°")
    lines.append(f"  DSC (Десцендент): {chart_data['ascendant']['sign']} "
                 f"{(chart_data['ascendant']['sign_degrees'] + 180) % 360:.1f}°")
    
    # Дома
    lines.append("\nКУСПИДЫ ДОМОВ (система Placidus):")
    for house_num in range(1, 13):
        house_key = f'House{house_num}'
        if house_key in chart_data['houses']:
            house_info = chart_data['houses'][house_key]
            lines.append(
                f"  Дом {house_num:2d}: {house_info['sign']} {house_info['sign_degrees']:.1f}°"
            )
    
    # Планеты в домах
    lines.append("\nПЛАНЕТЫ В ДОМАХ (важно для интерпретации):")
    for planet_name in ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto']:
        if planet_name in chart_data['planets_in_houses']:
            house_num = chart_data['planets_in_houses'][planet_name]
            lines.append(f"  {planet_ru.get(planet_name, planet_name)}: Дом {house_num}")
    
    # Лунные узлы
    lines.append(f"\nЛУННЫЕ УЗЛЫ:")
    lines.append(f"  Северный узел (Раху): {chart_data['north_node']['sign']} "
                 f"{chart_data['north_node']['sign_degrees']:.1f}°")
    lines.append(f"  Южный узел (Кету): {chart_data['south_node']['sign']} "
                 f"{chart_data['south_node']['sign_degrees']:.1f}°")
    
    # Аспекты
    lines.append("\nГЛАВНЫЕ АСПЕКТЫ МЕЖДУ ПЛАНЕТАМИ (узкие орбисы):")
    if chart_data['aspects']:
        for aspect in chart_data['aspects']:
            p1_ru = planet_ru.get(aspect['planet1'], aspect['planet1'])
            p2_ru = planet_ru.get(aspect['planet2'], aspect['planet2'])
            lines.append(
                f"  {p1_ru} {aspect['aspect']} {p2_ru} (орбис {aspect['orb']:.1f}°)"
            )
    else:
        lines.append("  Нет значимых аспектов в указанных орбисах")
    
    lines.append("\n" + "=" * 70)
    lines.append("ИНСТРУКЦИЯ: Используй ВСЕ указанные выше данные для анализа.")
    lines.append("НЕ придумывай новые позиции планет или аспекты.")
    lines.append("Опирайся ТОЛЬКО на эти точные расчёты Swiss Ephemeris.")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def generate_natal_chart_with_gpt(birth_data, api_key):
    """Генерация натальной карты с помощью OpenAI GPT и преобразование текста в PDF."""

    # Увеличенный таймаут на случай длинных ответов
    client = OpenAI(api_key=api_key, timeout=180)
    
    # Расчет натальной карты через Swiss Ephemeris
    try:
        chart_data = calculate_natal_chart(birth_data)
        chart_data_text = format_natal_chart_data(chart_data)
        logger.info("Натальная карта успешно рассчитана через Swiss Ephemeris")
        # Логируем первые 1000 символов данных для отладки
        preview = chart_data_text[:1000] + "..." if len(chart_data_text) > 1000 else chart_data_text
        logger.info(f"Данные натальной карты (первые 1000 символов):\n{preview}")
    except Exception as e:
        logger.error(f"Ошибка при расчете натальной карты: {e}", exc_info=True)
        chart_data_text = "Ошибка расчета натальной карты. Используются базовые данные."

    # Разнесённая генерация по группам разделов для стабильности
    try:
        def _build_common_preamble() -> str:
            return (
                "- Составь подробный астрологический отчет по натальной карте по системе Placidus.\n"
                "- Используй Классическую астрологию (узкие орбисы): соединения ±6°, оппозиции/квадраты ±5°, трины/секстили ±4°.\n"
                "- Не добавляй никаких вступлений, пояснений, выводов, заголовков вроде “введение”, “итог”, “анализ” или обращений к читателю.\n"
                "- один непрерывный документ целиком\n"
                "- Выводи только структурированный отчёт с разделами из указанного диапазона, без лишнего текста и комментариев.\n\n"
                "Мои данные:\n"
                f"Имя: {birth_data.get('name', 'Не указано')}\n"
                f"Дата рождения: {birth_data.get('date', 'Не указано')}\n"
                f"Время рождения: {birth_data.get('time', 'Не указано')}\n"
                f"Место рождения: {birth_data.get('place', 'Не указано')}\n\n"
                f"{chart_data_text}\n\n"
                "ВАЖНО: Используй ТОЛЬКО указанные выше данные натальной карты для интерпретации. "
                "Не выдумывай положения планет, домов, узлов или аспектов. "
                "Все астрономические данные уже рассчитаны и предоставлены выше.\n"
            )

        def _sections_prompt(range_note: str, structure_lines: str) -> str:
            return f"{_build_common_preamble()}\nСгенерируй ТОЛЬКО разделы {range_note}:\n{structure_lines}\n"

        def _call_openai_with_retry(messages, token_attempts=(10000,), use_stream: bool = True) -> str:
            last_err = None
            for max_t in token_attempts:
                try:
                    if use_stream:
                        stream = client.chat.completions.create(
                            model="gpt-4.1",
                            messages=messages,
                            max_tokens=max_t,
                            temperature=0.4,
                            stream=True
                        )
                        collected = []
                        for event in stream:
                            try:
                                delta = event.choices[0].delta  # type: ignore[attr-defined]
                                piece = getattr(delta, "content", None)
                                if piece:
                                    collected.append(piece)
                            except Exception:
                                # На случай нестандартного события (finish_reason и т.п.)
                                continue
                        content = ("".join(collected)).strip()
                        if content:
                            return content
                    else:
                        resp = client.chat.completions.create(
                            model="gpt-4.1",
                            messages=messages,
                            max_tokens=max_t,
                            temperature=0.4
                        )
                        content = (resp.choices[0].message.content or "").strip()
                        if content:
                            return content
                except Exception as e:
                    last_err = e
                    logger.warning(f"OpenAI ошибка (max_tokens={max_t}): {e}; повтор...")
                    time.sleep(1.0)
            raise last_err or RuntimeError("Не удалось получить ответ от OpenAI")

        example_from_file = load_prompt_example()
        example_sections = _split_example_by_sections(example_from_file) if example_from_file else {}
        system_base = [
            {"role": "system", "content": "Ты профессиональный астролог и пишешь структурированные отчёты на русском языке."}
        ]

        # Генерация каждого раздела отдельным запросом
        section_specs = {
            1: "- Раздел 1 (не менее 2 500 символов): Опиши особенности личности на основе Солнца и Луны",
            2: "- Раздел 2 (не менее 1 000 символов): Опиши как человека видят другие люди на основе асцендента",
            3: "- Раздел 3 (не менее 6 000 символов): ОБЯЗАТЕЛЬНО пропиши два подзаголовка: 'Сильные стороны' и 'Слабые стороны'. Под подзаголовком 'Сильные стороны' опиши сильные стороны (как они проявляются, как можно их усилить; упомяни планеты, дома, аспекты) с перечислением. Под подзаголовком 'Слабые стороны' опиши слабые стороны (как они проявляются, как можно их исправить; упомяни планеты, дома, аспекты) с перечислением. Оба подзаголовка должны быть обязательно включены в текст.",
            4: "- Раздел 4 (не менее 2 000 символов): Сфера карьеры и финансов (врожденные таланты; подходящие профессии; сильные стороны на работе и как нужно проявляться, чтобы достигать успех; способ реализации: найм, фриланс, бизнес; финансовая стратегия: копить или тратить; как поднять самооценку и обрести внутреннюю опору; где брать энергию и как мотивировать себя; упомяни планеты, дома, аспекты)",
            5: "- Раздел 5 (не менее 3 000 символов): Сфера романтических отношений (Типаж идеального партнера, который нравится; типаж идеального партнера, с которым получится построить отношения; какие могут быть трудности в отношениях и что делать с трудностями; упомяни планеты, дома, аспекты)",
            6: "- Раздел 6 (не менее 1 000 символов): Физическая активность и спорт (какой вид физической активности подходит по Марсу; как нужно следить за здоровьем физическим и ментальным; упомяни планеты, дома, аспекты)",
            7: "- Раздел 7 (не менее 1 000 символов): Опиши предназначение на эту жизнь в соответствии с Северным и Южным Лунными Узлами",
        }

        parts = []  # каждый элемент — уже со своим заголовком и, при необходимости, с разрывом страницы
        static_titles = {
            1: "Особенности личности на основе Солнца и Луны",
            2: "Как человека видят другие люди на основе асцендента",
            3: "Сильные и слабые стороны",
            4: "Сфера карьеры и финансов",
            5: "Сфера романтических отношений",
            6: "Сфера физической активности и спорта",
            7: "Предназначение на эту жизнь в соответствии с Северным и Южным Лунными Узлами",
        }
        for i in range(1, 8):
            # Для каждого раздела берём соответствующий пример, если есть
            sys_msgs = list(system_base)
            example_key = str(i)
            if example_key in example_sections:
                sys_msgs.append({"role": "system", "content": f"Пример для ориентира (только стиль, Раздел {i}):\n{example_sections[example_key]}"})
            # Формируем точечный промпт на раздел
            user_prompt = (
                _build_common_preamble() + 
                f"\nСгенерируй ТОЛЬКО Раздел {i}:\n{section_specs[i]}\n"
            )
            messages = sys_msgs + [{"role": "user", "content": user_prompt}]
            # Логируем промпт для первого раздела (чтобы не спамить логами)
            if i == 1:
                logger.info("=" * 80)
                logger.info("ПОЛНЫЙ ПРОМПТ ДЛЯ OPENAI (Раздел 1):")
                logger.info("=" * 80)
                logger.info(user_prompt)
                logger.info("=" * 80)
            section_text = _call_openai_with_retry(messages)
            section_text = section_text.strip()
            if not section_text:
                section_text = "Секция недоступна."
            else:
                # Убираем возможный дублирующий заголовок в начале тела раздела:
                # - строки вида "Раздел N: ...", "Раздел N." и т.п.
                # - строки, повторяющие статичный заголовок или его основную часть
                import re
                lines = section_text.splitlines()
                cleaned_lines = []
                skipped_header = False
                static_title = static_titles.get(i, "").strip().lower()
                core_title = static_title.split("(")[0].strip() if static_title else ""
                for line in lines:
                    stripped = line.strip()
                    lower = stripped.lower().lstrip("#").strip()
                    if not skipped_header and stripped:
                        is_section_line = re.match(r"^раздел\s+\d+[:\. ]", lower)
                        matches_title = False
                        if core_title:
                            matches_title = (
                                lower.startswith(core_title)
                                or core_title.startswith(lower)
                                or core_title in lower
                                or lower in core_title
                            )
                        if is_section_line or matches_title:
                            skipped_header = True
                            continue
                    cleaned_lines.append(line)
                section_text = "\n".join(cleaned_lines).strip() or section_text
            # Статичный заголовок: "Раздел N: <фиксированное название>"
            header_title = static_titles.get(i, "").strip()
            header = f"## Раздел {i}: {header_title}" if header_title else f"## Раздел {i}"
            block = f"{header}\n\n{section_text}"
            parts.append(block)

        # Склейка итогового Markdown по порядку разделов с разрывами страниц
        markdown_text = ("\n\n[[PAGE_BREAK]]\n\n").join(parts).strip()

        pdf_title = f"Натальная карта: {birth_data.get('name', 'Пользователь')}"
        # Передаём chart_data для отображения диаграммы на первой странице
        pdf_path = generate_pdf_from_markdown(markdown_text, pdf_title, chart_data)

        if not pdf_path:
            error_msg = "Не удалось сформировать PDF из Markdown"
            logger.error(f"❌ {error_msg}")
            # Ошибка будет залогирована в generate_natal_chart_background с user_id
            raise ValueError(error_msg)

        summary_section = _extract_summary(markdown_text) or markdown_text
        summary_clean = _clean_inline_markdown(summary_section)
        summary_text = summary_clean.strip()
        if summary_text:
            summary_text = "Краткое резюме:\n" + summary_text
        if len(summary_text) > 920:
            summary_text = summary_text[:920].rsplit(' ', 1)[0] + '…'

        if not summary_text:
            summary_text = "Краткое резюме недоступно. Подробности в PDF-файле."

        logger.info("Натальная карта успешно сгенерирована через OpenAI GPT и сконвертирована в PDF")

        return pdf_path, summary_text

    except Exception as error:
        error_type = type(error).__name__
        error_message = str(error)
        logger.error(f"Ошибка при генерации натальной карты через GPT: {error_type}: {error_message}", exc_info=True)

        fallback_text = "Карта временно недоступна. Попробуйте повторить запрос позже."
        # Пытаемся получить chart_data для fallback PDF
        fallback_chart_data = None
        try:
            fallback_chart_data = calculate_natal_chart(birth_data)
        except Exception as e:
            logger.warning(f"Не удалось получить chart_data для fallback PDF: {e}")
        
        # Пытаемся создать fallback PDF
        fallback_pdf = None
        try:
            # Создаем минимальный markdown для fallback PDF
            fallback_markdown = f"# Натальная карта: {birth_data.get('name', 'Пользователь')}\n\n{fallback_text}"
            fallback_pdf = generate_pdf_from_markdown(
                fallback_markdown,
                f"Натальная карта: {birth_data.get('name', 'Пользователь')}",
                fallback_chart_data
            )
        except Exception as pdf_error:
            error_type = type(pdf_error).__name__
            error_message = str(pdf_error)
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать даже fallback PDF: {error_type}: {error_message}", exc_info=True)
            logger.error(f"   Fallback markdown: {fallback_markdown[:100]}...")
            # Fallback PDF тоже не создался - это критическая ситуация

        return fallback_pdf, fallback_text


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех текстовых сообщений"""
    if 'natal_chart_state' in context.user_data:
        await handle_natal_chart_input(update, context)
    else:
        await update.message.reply_text(
            "👋 Используйте кнопки меню для навигации или отправьте команду /help для справки."
        )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    user_id = query.from_user.id
    
    logger.info(f"🔔 Получен pre-checkout запрос от пользователя {user_id}")
    logger.info(f"   Payload: {query.invoice_payload}")
    logger.info(f"   Сумма: {query.total_amount} {query.currency}")
    
    try:
        # Проверяем формат payload (поддерживаем оба формата: старый с двоеточием и новый)
        if not (query.invoice_payload.startswith('natal_chart:') or query.invoice_payload.startswith('natal_chart_')):
            logger.warning(f"❌ Неверный payload: {query.invoice_payload}")
            log_event(user_id, 'payment_error', {'error': 'invalid_payload', 'payload': query.invoice_payload})
            await query.answer(ok=False, error_message='Некорректный платежный запрос')
            return
        
        # Проверяем сумму платежа (может быть 299 или 499 руб)
        user_price_rub, user_price_minor = get_user_price(user_id)
        expected_amount = user_price_minor  # В копейках
        
        # Также проверяем стандартную цену на случай, если пользователь оплачивает по обычной ссылке
        if query.total_amount != expected_amount and query.total_amount != NATAL_CHART_PRICE_MINOR:
            logger.warning(f"❌ Неверная сумма платежа: ожидалось {expected_amount} или {NATAL_CHART_PRICE_MINOR}, получено {query.total_amount}")
            log_event(user_id, 'payment_error', {
                'error': 'invalid_amount',
                'expected': expected_amount,
                'expected_standard': NATAL_CHART_PRICE_MINOR,
                'received': query.total_amount
            })
            await query.answer(ok=False, error_message='Неверная сумма платежа')
            return
        
        # Логируем предварительную проверку оплаты
        log_event(user_id, 'payment_precheckout', {
            'invoice_payload': query.invoice_payload,
            'total_amount': query.total_amount,
            'currency': query.currency
        })
        
        logger.info(f"✅ Pre-checkout подтвержден для пользователя {user_id}")
        await query.answer(ok=True)
    except Exception as error:
        logger.error(f"❌ Ошибка при подтверждении оплаты: {error}", exc_info=True)
        log_event(user_id, 'payment_error', {'error': str(error), 'stage': 'precheckout'})
        await query.answer(ok=False, error_message='Ошибка при обработке платежа')


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    payment = message.successful_payment
    
    logger.info(f"💳 Получен успешный платеж от пользователя {user_id}")
    logger.info(f"   Сумма: {payment.total_amount} {payment.currency}")
    logger.info(f"   Payload: {payment.invoice_payload}")
    logger.info(f"   Charge ID: {payment.provider_payment_charge_id}")
    
    # Логируем успешную оплату
    log_event(user_id, 'payment_success', {
        'invoice_payload': payment.invoice_payload,
        'total_amount': payment.total_amount,
        'currency': payment.currency,
        'provider_payment_charge_id': payment.provider_payment_charge_id
    })
    
    mark_user_paid(user_id)
    logger.info(f"✅ Пользователь {user_id} помечен как оплативший")
    
    # Сразу запускаем генерацию натальной карты (как если бы пользователь нажал кнопку)
    # Загружаем профиль пользователя
    user_data = context.user_data
    if not user_data.get('birth_name'):
        loaded_data = load_user_profile(user_id)
        if loaded_data:
            user_data.update(loaded_data)
    
    has_profile = is_profile_complete(user_data)
    
    if not has_profile:
        # Если профиль не заполнен, показываем сообщение о необходимости заполнить данные
        await message.reply_text(
            "✅ Оплата получена!\n\n"
            "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
            "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта, а также сделает ответы Звёздного Чата более персональными.🔮\n\n"
            "Нажмите кнопку ниже, чтобы заполнить данные:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Заполнить данные", callback_data='edit_profile'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    # Профиль заполнен, запускаем генерацию
    # Проверяем, не идет ли уже генерация
    if user_id in active_generations:
        await message.reply_text(
            "⏳ *Генерация уже идет...*\n\n"
            "Пожалуйста, подождите завершения текущей генерации натальной карты.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
                [InlineKeyboardButton("💬 Поддержка", callback_data='support')]
            ]),
            parse_mode='Markdown'
        )
        return
    
    # Формируем birth_data для генерации
    birth_name = user_data.get('birth_name') or None
    if not birth_name:
        loaded_profile = load_user_profile(user_id)
        if loaded_profile and loaded_profile.get('birth_name'):
            birth_name = loaded_profile.get('birth_name')
            user_data['birth_name'] = birth_name
    if not birth_name:
        birth_name = 'Пользователь'
    
    birth_data = {
        'name': birth_name,
        'date': user_data.get('birth_date', 'Не указано'),
        'time': user_data.get('birth_time', 'Не указано'),
        'place': user_data.get('birth_place', 'Не указано')
    }
    
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        await message.reply_text(
            "❌ *Ошибка настройки*\n\n"
            "API ключ OpenAI не настроен.\n"
            "Обратитесь к администратору бота.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    # Отправляем сообщение о начале генерации
    generation_message = await message.reply_text(
        "⏳ *Генерация натальной карты...*\n\n"
        "Обычно генерация занимает не более 5 минут.\n\n"
        "Пожалуйста, подождите.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')],
            [InlineKeyboardButton("💬 Поддержка", callback_data='support')]
        ]),
        parse_mode='Markdown'
    )
    
    # Логируем начало генерации
    log_event(user_id, 'natal_chart_generation_start', {
        'birth_date': birth_data.get('date'),
        'birth_time': birth_data.get('time'),
        'birth_place': birth_data.get('place')
    })
    
    # Сохраняем информацию о генерации
    active_generations[user_id] = {
        'chat_id': generation_message.chat_id,
        'message_id': generation_message.message_id,
        'birth_data': birth_data,
        'openai_key': openai_key
    }
    
    # Запускаем генерацию в фоне в отдельном потоке
    def run_generation_from_message():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(generate_natal_chart_background(user_id, context))
            finally:
                loop.close()
        except Exception as gen_error:
            logger.error(f"❌ Ошибка при запуске генерации в потоке: {gen_error}", exc_info=True)
    
    gen_thread = threading.Thread(target=run_generation_from_message, daemon=True)
    gen_thread.start()
    logger.info(f"🚀 Генерация натальной карты запущена в фоновом потоке для пользователя {user_id}")


# Глобальная переменная для хранения application (нужна для webhook и проверки платежей)
telegram_application = None
# Флаг для корректного завершения (используется в run_bot())
shutdown_event = threading.Event()


def create_webhook_app(application_instance):
    """Создает Flask приложение для webhook Telegram и ЮKassa"""
    app = Flask(__name__)
    
    # Webhook для Telegram
    @app.route('/webhook/telegram', methods=['POST'])
    def telegram_webhook():
        """Webhook endpoint для получения обновлений от Telegram"""
        try:
            update_data = request.get_json()
            if update_data:
                # Создаем объект Update
                update = Update.de_json(update_data, application_instance.bot)
                if update:
                    # Определяем тип обновления для логирования
                    update_type = "unknown"
                    if update.message:
                        update_type = "message"
                    elif update.callback_query:
                        update_type = "callback_query"
                        logger.info(f"📨 Callback query получен: data={update.callback_query.data}, user_id={update.callback_query.from_user.id if update.callback_query.from_user else 'unknown'}")
                    elif update.pre_checkout_query:
                        update_type = "pre_checkout_query"
                    
                    logger.debug(f"📨 Обновление получено от Telegram: type={update_type}, update_id={update.update_id}")
                    
                    # Обрабатываем обновление через Application
                    # Используем asyncio для обработки в правильном event loop
                    try:
                        logger.debug(f"Обработка update {update.update_id} через process_update()...")
                        
                        # Пытаемся получить event loop Application
                        app_loop = None
                        try:
                            # Пытаемся получить из Application
                            if hasattr(application_instance, '_loop') and application_instance._loop:
                                app_loop = application_instance._loop
                            elif hasattr(application_instance, 'updater') and hasattr(application_instance.updater, '_loop'):
                                app_loop = application_instance.updater._loop
                        except Exception as loop_error:
                            logger.debug(f"Ошибка при получении event loop: {loop_error}")
                        
                        if app_loop and app_loop.is_running() and not app_loop.is_closed():
                            # Если есть работающий event loop, используем его
                            logger.info(f"✅ Используем event loop Application для обработки update {update.update_id}")
                            future = asyncio.run_coroutine_threadsafe(
                                application_instance.process_update(update),
                                app_loop
                            )
                            # Ждем завершения обработки (максимум 30 секунд)
                            try:
                                future.result(timeout=30)
                                logger.info(f"✅ Обновление обработано: update_id={update.update_id}, type={update_type}")
                            except Exception as future_error:
                                logger.error(f"❌ Ошибка при ожидании обработки обновления {update.update_id}: {future_error}", exc_info=True)
                        else:
                            # Если нет работающего loop, создаем новый
                            logger.warning(f"⚠️ Event loop Application недоступен для update {update.update_id}, создаем новый")
                            logger.warning(f"   app_loop={app_loop}, is_running={app_loop.is_running() if app_loop else 'N/A'}, is_closed={app_loop.is_closed() if app_loop else 'N/A'}")
                            def process_update():
                                try:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        # Обрабатываем обновление через Application
                                        logger.info(f"🔄 Обработка update {update.update_id} в новом event loop")
                                        loop.run_until_complete(application_instance.process_update(update))
                                        logger.info(f"✅ Обновление обработано: update_id={update.update_id}, type={update_type}")
                                    except Exception as process_error:
                                        logger.error(f"❌ Ошибка при обработке обновления {update.update_id}: {process_error}", exc_info=True)
                                    finally:
                                        try:
                                            # Закрываем loop только если он не был закрыт
                                            if not loop.is_closed():
                                                loop.close()
                                        except Exception as close_error:
                                            logger.warning(f"⚠️ Ошибка при закрытии loop: {close_error}")
                                except Exception as thread_error:
                                    logger.error(f"❌ Ошибка в потоке обработки обновления: {thread_error}", exc_info=True)
                            
                            # Запускаем обработку в отдельном потоке
                            update_thread = threading.Thread(target=process_update, daemon=True)
                            update_thread.start()
                            # Не ждем завершения потока, чтобы не блокировать webhook
                            
                    except Exception as process_error:
                        logger.error(f"❌ Критическая ошибка при обработке обновления {update.update_id}: {process_error}", exc_info=True)
                
                    return jsonify({'status': 'ok'}), 200
                else:
                    logger.warning("Не удалось создать объект Update из webhook данных")
                    return jsonify({'status': 'error', 'message': 'Invalid update'}), 400
            else:
                logger.warning("Получен пустой webhook от Telegram")
                return jsonify({'status': 'error', 'message': 'Empty request'}), 400
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке webhook от Telegram: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    @app.route('/webhook/yookassa', methods=['POST'])
    def yookassa_webhook():
        """Webhook endpoint для получения уведомлений от ЮKassa"""
        try:
            # Получаем данные из запроса
            event_data = request.json
            
            if not event_data:
                logger.warning("Получен пустой webhook от ЮKassa")
                return jsonify({'status': 'error', 'message': 'Empty request'}), 400
            
            event_type = event_data.get('event')
            payment_object = event_data.get('object', {})
            
            logger.info(f"🔔 Получен webhook от ЮKassa: event={event_type}, payment_id={payment_object.get('id')}")
            
            # Обрабатываем только события о платежах
            if event_type == 'payment.succeeded':
                yookassa_payment_id = payment_object.get('id')
                payment_status = payment_object.get('status')
                metadata = payment_object.get('metadata', {})
                user_id = metadata.get('user_id')
                amount_value = payment_object.get('amount', {}).get('value')
                
                if not user_id:
                    logger.warning(f"Платеж {yookassa_payment_id} не содержит user_id в metadata")
                    return jsonify({'status': 'ok'}), 200
                
                user_id = int(user_id)
                
                # Обновляем статус платежа в базе
                update_payment_status(yookassa_payment_id, payment_status, payment_object)
                
                # Помечаем пользователя как оплатившего
                mark_user_paid(user_id)
                
                # Логируем успешную оплату
                log_event(user_id, 'payment_success', {
                    'yookassa_payment_id': yookassa_payment_id,
                    'amount': amount_value,
                    'payment_method': payment_object.get('payment_method', {}).get('type', 'unknown'),
                    'source': 'webhook'
                })
                
                # Запускаем обработку платежа (проверка профиля и запуск генерации)
                if application_instance:
                    # Запускаем в отдельном потоке, т.к. Flask - синхронный
                    def process_payment_thread():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(process_payment_async(user_id, application_instance))
                            loop.close()
                        except Exception as e:
                            logger.error(f"❌ Ошибка при обработке платежа в потоке: {e}", exc_info=True)
                    
                    payment_thread = threading.Thread(target=process_payment_thread, daemon=True)
                    payment_thread.start()
                
                logger.info(f"✅ Платеж {yookassa_payment_id} успешно обработан через webhook для пользователя {user_id}")
                
            elif event_type == 'payment.canceled':
                yookassa_payment_id = payment_object.get('id')
                payment_status = payment_object.get('status')
                
                # Извлекаем причину отмены, если она есть
                cancellation_details = payment_object.get('cancellation_details', {})
                cancel_reason = cancellation_details.get('reason', 'unknown')
                cancel_party = cancellation_details.get('party', 'unknown')
                
                # Логируем детальную информацию об отмене
                logger.info(f"ℹ️ Платеж {yookassa_payment_id} отменен")
                logger.info(f"   Причина: {cancel_reason}, Инициатор: {cancel_party}")
                
                # Сохраняем причину отмены в логах событий, если есть user_id
                metadata = payment_object.get('metadata', {})
                user_id = metadata.get('user_id')
                if user_id:
                    log_event(int(user_id), 'payment_canceled', {
                        'yookassa_payment_id': yookassa_payment_id,
                        'cancel_reason': cancel_reason,
                        'cancel_party': cancel_party,
                        'source': 'webhook'
                    })
                
                update_payment_status(yookassa_payment_id, payment_status, payment_object)
            
            return jsonify({'status': 'ok'}), 200
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке webhook от ЮKassa: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint для проверки работоспособности"""
        return jsonify({'status': 'ok'}), 200
    
    @app.route('/', methods=['GET'])
    def root():
        """Корневой endpoint для health check Docker и других проверок"""
        return jsonify({
            'status': 'ok',
            'service': 'Astral Bot',
            'version': '1.0',
            'endpoints': {
                'health': '/health',
                'telegram_webhook': '/webhook/telegram',
                'yookassa_webhook': '/webhook/yookassa'
            }
        }), 200
    
    return app


async def process_payment_async(user_id: int, application):
    """Асинхронная обработка успешного платежа - запускает генерацию натальной карты"""
    try:
        logger.info(f"🚀 Обработка успешного платежа для пользователя {user_id} через webhook")
        
        # Создаем Context wrapper для Application
        from telegram.ext import ContextTypes
        if isinstance(application, Application):
            context = ApplicationContextWrapper(application, user_id)
        else:
            context = application
        
        # Загружаем данные пользователя
        user_data = context.user_data
        if not user_data.get('birth_name'):
            loaded_data = load_user_profile(user_id)
            if loaded_data:
                user_data.update(loaded_data)
        
        # Проверяем наличие всех необходимых данных профиля
        birth_name = user_data.get('birth_name')
        birth_date = user_data.get('birth_date')
        birth_time = user_data.get('birth_time')
        birth_place = user_data.get('birth_place')
        
        # Если профиль не заполнен, отправляем сообщение с кнопкой для заполнения
        if not all([birth_name, birth_date, birth_time, birth_place]):
            logger.info(f"⚠️ Профиль пользователя {user_id} не заполнен полностью, отправляем сообщение для заполнения")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ *Оплата получена!*\n\n"
                         "*Чтобы составить подробный отчёт, мне нужно узнать вас чуть лучше.*\n\n"
                         "Пожалуйста, заполните свой профиль. Информация оттуда необходима для составления отчёта.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                    ]]),
                    parse_mode='Markdown'
                )
            except Exception as send_error:
                logger.error(f"❌ Ошибка при отправке сообщения пользователю {user_id}: {send_error}", exc_info=True)
            return
        
        # Профиль заполнен - запускаем генерацию автоматически
        logger.info(f"✅ Профиль пользователя {user_id} заполнен, запускаем генерацию натальной карты автоматически")
        logger.info(f"   Данные профиля: name={birth_name}, date={birth_date}, time={birth_time}, place={birth_place}")
        try:
            await handle_natal_chart_request_from_payment(user_id, context)
            logger.info(f"✅ Генерация натальной карты успешно запущена для пользователя {user_id}")
        except Exception as gen_error:
            logger.error(f"❌ Ошибка при запуске генерации для пользователя {user_id}: {gen_error}", exc_info=True)
            raise
        
    except Exception as e:
        logger.error(f"❌ Ошибка при асинхронной обработке платежа: {e}", exc_info=True)


async def check_pending_payments_periodically(application):
    """Периодическая проверка ожидающих платежей"""
    logger.info("🔄 Запущена периодическая проверка платежей (каждые 2 минуты)")
    
    while True:
        try:
            await asyncio.sleep(120)  # Проверяем каждые 2 минуты
            
            conn, db_type = get_db_connection()
            cursor = conn.cursor()
            
            try:
                # Находим платежи со статусом 'pending', которые старше 1 минуты
                # Для PostgreSQL: при SELECT DISTINCT нужно включать created_at в SELECT для ORDER BY
                if db_type == 'postgresql':
                    cursor.execute('''
                        SELECT DISTINCT ON (user_id) user_id, yookassa_payment_id, created_at
                        FROM payments
                        WHERE status = 'pending'
                        AND created_at < NOW() - INTERVAL '1 minute'
                        ORDER BY user_id, created_at DESC
                        LIMIT 10
                    ''')
                else:
                    cursor.execute('''
                        SELECT DISTINCT user_id, yookassa_payment_id
                        FROM payments
                        WHERE status = 'pending'
                        AND datetime(created_at) < datetime('now', '-1 minute')
                        ORDER BY created_at DESC
                        LIMIT 10
                    ''')
                
                pending_payments = cursor.fetchall()
                
                if pending_payments:
                    logger.info(f"🔍 Найдено {len(pending_payments)} ожидающих платежей для проверки")
                    
                    for payment_row in pending_payments:
                        # Извлекаем значения в зависимости от количества колонок
                        # PostgreSQL возвращает: (user_id, yookassa_payment_id, created_at)
                        # SQLite возвращает: (user_id, yookassa_payment_id)
                        user_id = payment_row[0]
                        yookassa_payment_id = payment_row[1]
                        try:
                            # Проверяем статус платежа через API
                            payment_info = await check_yookassa_payment_status(yookassa_payment_id)
                            
                            if payment_info:
                                payment_status = payment_info.get('status')
                                
                                # Обновляем статус в базе
                                update_payment_status(yookassa_payment_id, payment_status, payment_info)
                                
                                # Если платеж успешен, обрабатываем его
                                if payment_status == 'succeeded':
                                    logger.info(f"✅ Платеж {yookassa_payment_id} успешно обработан при периодической проверке")
                                    try:
                                        # Создаем задачу для обработки платежа через основной event loop
                                        if application:
                                            # Используем application для отправки сообщений
                                            await check_and_process_pending_payment(user_id, application)
                                    except Exception as process_error:
                                        logger.error(f"❌ Ошибка при обработке платежа для user_id {user_id}: {process_error}", exc_info=True)
                            else:
                                # Если payment_info = None, значит платеж не найден (404) и уже помечен как canceled
                                logger.debug(f"ℹ️  Платеж {yookassa_payment_id} не найден, статус уже обновлен")
                            
                            # Небольшая задержка между проверками
                            await asyncio.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"❌ Ошибка при проверке платежа {yookassa_payment_id}: {e}", exc_info=True)
                            
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"❌ Ошибка в периодической проверке платежей: {e}", exc_info=True)
            await asyncio.sleep(60)  # В случае ошибки ждем минуту перед следующей попыткой


def cleanup_bot():
    """Корректное завершение работы бота - упрощенная версия для новой архитектуры"""
    global telegram_application, shutdown_event
    
    logger.info("🛑 Начало корректного завершения работы бота...")
    
    # Устанавливаем флаг остановки
    # В новой архитектуре все работает в одном event loop через asyncio.run()
    # shutdown_event используется в run_bot() для корректного завершения
    shutdown_event.set()
    
    # В новой упрощенной архитектуре:
    # - Application и webhook server работают в одном event loop
    # - Завершаются автоматически через shutdown_event в run_bot()
    # - Дополнительная очистка не требуется
    
    logger.info("✅ Сигнал остановки установлен, приложение завершится корректно")


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"📡 Получен сигнал {signum}, запускаем корректное завершение...")
    cleanup_bot()
    sys.exit(0)


def start_webhook_server(application_instance):
    """Запускает Flask сервер для webhook Telegram и YooKassa в отдельном потоке"""
    global flask_app, webhook_thread, werkzeug_server
    
    telegram_webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
    yookassa_webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
    
    # Определяем, нужен ли webhook сервер
    need_telegram_webhook = bool(telegram_webhook_url)
    need_yookassa_webhook = bool(yookassa_webhook_url)
    
    if not need_telegram_webhook and not need_yookassa_webhook:
        logger.error("❌ TELEGRAM_WEBHOOK_URL и YOOKASSA_WEBHOOK_URL не установлены.")
        logger.error("💡 Установите хотя бы один из webhook URLs для работы бота.")
        return None
    
    try:
        # Определяем порт и хост
        # Приоритет: PORT (для платформ типа Railway/Render) > WEBHOOK_PORT > 8080
        port = int(os.getenv('PORT') or os.getenv('WEBHOOK_PORT', '8080'))
        host = '0.0.0.0'  # Слушаем на всех интерфейсах - это позволяет принимать запросы извне
        
        # Если есть TELEGRAM_WEBHOOK_URL, пытаемся извлечь порт из него
        if telegram_webhook_url:
            from urllib.parse import urlparse
            parsed = urlparse(telegram_webhook_url)
            if parsed.port:
                # Порт указан в URL - это может быть для прокси, но мы все равно слушаем на своем порту
                pass  # Используем порт из переменной окружения
        
        flask_app = create_webhook_app(application_instance)
        
        # Добавляем shutdown hook для Flask
        @flask_app.route('/shutdown', methods=['POST'])
        def shutdown():
            """Endpoint для остановки сервера (только для внутреннего использования)"""
            shutdown_event.set()
            return jsonify({'status': 'shutting down'}), 200
        
        # Используем Werkzeug для более контролируемого запуска/остановки
        from werkzeug.serving import make_server
        
        server = None
        
        def run_flask():
            nonlocal server
            try:
                logger.info(f"🌐 Запуск webhook сервера на {host}:{port}")
                if need_telegram_webhook:
                    logger.info(f"   📱 Telegram webhook: /webhook/telegram")
                if need_yookassa_webhook:
                    logger.info(f"   💳 YooKassa webhook: /webhook/yookassa")
                logger.info(f"   ❤️  Health check: / и /health")
                
                # Используем Werkzeug server для возможности корректной остановки
                server = make_server(host, port, flask_app, threaded=True)
                global werkzeug_server
                werkzeug_server = server
                logger.info("   Используется Werkzeug server (threaded mode)")
                
                # Запускаем сервер в отдельном потоке для возможности остановки
                # serve_forever() блокирует, поэтому запускаем его в daemon потоке
                def serve():
                    try:
                        server.serve_forever()
                    except Exception as e:
                        if not shutdown_event.is_set():
                            logger.error(f"❌ Ошибка в Werkzeug server: {e}")
                
                server_thread = threading.Thread(target=serve, daemon=True)
                server_thread.start()
                
                # Ждем сигнала остановки
                while not shutdown_event.is_set():
                    time.sleep(0.5)
                            
                logger.info("🛑 Flask сервер получил сигнал остановки")
            except Exception as e:
                if not shutdown_event.is_set():
                    logger.error(f"❌ Ошибка в Flask сервере: {e}", exc_info=True)
                else:
                    logger.info("🛑 Flask сервер остановлен")
            finally:
                if server:
                    try:
                        server.shutdown()
                        logger.info("✅ Werkzeug server остановлен")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка при остановке Werkzeug server: {e}")
        
        webhook_thread = threading.Thread(target=run_flask, daemon=False)
        webhook_thread.start()
        logger.info("✅ Webhook сервер запущен в отдельном потоке")
        
        return webhook_thread
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске webhook сервера: {e}", exc_info=True)
        if need_telegram_webhook:
            logger.error("❌ КРИТИЧНО: Не удалось запустить webhook сервер для Telegram!")
            logger.error("   Бот не сможет получать обновления от Telegram!")
        else:
            logger.warning("⚠️ Бот продолжит работу без webhook. Платежи будут проверяться периодически.")
        return None


def main():
    """Запуск бота"""
    global telegram_application
    
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
        return
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    telegram_application = application
    
    # Логирование событий теперь происходит внутри самих обработчиков,
    # чтобы не блокировать обработку команд и callback queries
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    
    # Проверяем, установлен ли webhook URL
    telegram_webhook_url = os.getenv('TELEGRAM_WEBHOOK_URL', '')
    
    if telegram_webhook_url:
        # Режим WEBHOOK (для продакшена) - УПРОЩЕННАЯ АРХИТЕКТУРА
        # Один event loop, один HTTP-вход через aiohttp
        logger.info("🌐 Запуск бота в режиме WEBHOOK (упрощенная архитектура)")
        logger.info("✅ Один event loop, один HTTP-вход")
        
        # Определяем порт
        port = int(os.getenv('PORT') or os.getenv('WEBHOOK_PORT', '8080'))
        yookassa_webhook_url = os.getenv('YOOKASSA_WEBHOOK_URL', '')
        
        # Извлекаем путь webhook из URL
        from urllib.parse import urlparse
        parsed = urlparse(telegram_webhook_url)
        webhook_path = parsed.path if parsed.path else '/webhook/telegram'
        
        # Сохраняем ссылку на application (уже объявлено в начале функции)
        telegram_application = application
        
        # Обработчики сигналов будут зарегистрированы в asyncio.run()
        # atexit.register не нужен, т.к. shutdown обрабатывается в run_bot()
        
        # Создаем async webhook server на aiohttp для обработки Telegram и YooKassa
        async def telegram_webhook_handler(request):
            """Обработчик webhook от Telegram"""
            try:
                update_data = await request.json()
                update = Update.de_json(update_data, application.bot)
                if update:
                    # Обрабатываем обновление через Application
                    await application.process_update(update)
                    return web.Response(text='ok', status=200)
                return web.Response(text='Invalid update', status=400)
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке webhook от Telegram: {e}", exc_info=True)
                return web.Response(text='Error', status=500)
        
        async def yookassa_webhook_handler(request):
            """Обработчик webhook от YooKassa"""
            try:
                event_data = await request.json()
                if not event_data:
                    return web.Response(text='Empty request', status=400)
                
                event_type = event_data.get('event')
                payment_object = event_data.get('object', {})
                
                logger.info(f"🔔 Получен webhook от ЮKassa: event={event_type}, payment_id={payment_object.get('id')}")
                
                if event_type == 'payment.succeeded':
                    yookassa_payment_id = payment_object.get('id')
                    metadata = payment_object.get('metadata', {})
                    user_id = metadata.get('user_id')
                    
                    if user_id:
                        user_id = int(user_id)
                        update_payment_status(yookassa_payment_id, payment_object.get('status'), payment_object)
                        mark_user_paid(user_id)
                        
                        log_event(user_id, 'payment_success', {
                            'yookassa_payment_id': yookassa_payment_id,
                            'amount': payment_object.get('amount', {}).get('value'),
                            'source': 'webhook'
                        })
                        
                        # Обрабатываем платеж асинхронно
                        await process_payment_async(user_id, application)
                
                elif event_type == 'payment.canceled':
                    yookassa_payment_id = payment_object.get('id')
                    metadata = payment_object.get('metadata', {})
                    user_id = metadata.get('user_id')
                    if user_id:
                        log_event(int(user_id), 'payment_canceled', {
                            'yookassa_payment_id': yookassa_payment_id,
                            'source': 'webhook'
                        })
                    update_payment_status(yookassa_payment_id, payment_object.get('status'), payment_object)
                
                return web.Response(text='ok', status=200)
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке webhook от ЮKassa: {e}", exc_info=True)
                return web.Response(text='Error', status=500)
        
        async def health_handler(request):
            """Health check endpoint - отвечает сразу для быстрого healthcheck"""
            # Проверяем, инициализирован ли Application (опционально)
            app_ready = hasattr(application, 'initialized') and application.initialized if hasattr(application, 'initialized') else True
            status = {
                'status': 'ok',
                'ready': app_ready,
                'timestamp': datetime.now().isoformat()
            }
            return web.json_response(status, status=200)
        
        # Создаем aiohttp приложение
        aioapp = web.Application()
        aioapp.router.add_post(webhook_path, telegram_webhook_handler)
        if yookassa_webhook_url:
            aioapp.router.add_post('/webhook/yookassa', yookassa_webhook_handler)
        aioapp.router.add_get('/health', health_handler)
        aioapp.router.add_get('/', health_handler)
        
        # Запускаем Application и webhook server в одном event loop
        async def run_bot():
            """Запускает Application и webhook server в одном event loop"""
            logger.info("🚀 Запуск бота в упрощенной архитектуре (один event loop, aiohttp)")
            
            # ВАЖНО: Сначала запускаем webhook server для healthcheck
            # Это позволяет healthcheck работать сразу, даже до полной инициализации Application
            runner = web.AppRunner(aioapp)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            logger.info(f"✅ Webhook server (aiohttp) запущен на порту {port} (healthcheck доступен)")
            logger.info(f"   Telegram webhook path: {webhook_path}")
            if yookassa_webhook_url:
                logger.info(f"   YooKassa webhook path: /webhook/yookassa")
            
            # Теперь инициализируем Application (может занять время)
            logger.info("🔧 Инициализация Application...")
            await application.initialize()
            logger.info("✅ Application инициализирован")
            
            # Устанавливаем webhook в Telegram
            try:
                result = await application.bot.set_webhook(
                    url=telegram_webhook_url,
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True
                )
                if result:
                    logger.info("✅ Webhook успешно установлен в Telegram")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при установке webhook: {e}")
            
            # Запускаем Application
            await application.start()
            logger.info("✅ Application запущен и готов обрабатывать обновления")
            
            # Ждем сигнала остановки
            shutdown_evt = asyncio.Event()
            async def check_shutdown():
                while not shutdown_event.is_set():
                    await asyncio.sleep(1)
                shutdown_evt.set()
            
            asyncio.create_task(check_shutdown())
            await shutdown_evt.wait()
            
            # Останавливаем в правильном порядке
            logger.info("🛑 Начало остановки компонентов...")
            
            # Сначала останавливаем webhook server
            try:
                await site.stop()
                logger.info("✅ Webhook server остановлен")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при остановке webhook server: {e}")
            
            try:
                await runner.cleanup()
                logger.info("✅ AppRunner очищен")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при очистке AppRunner: {e}")
            
            # Затем останавливаем Application
            try:
                if hasattr(application, 'running') and application.running:
                    await application.stop()
                    logger.info("✅ Application остановлен")
            except Exception as e:
                error_str = str(e)
                if 'different loop' in error_str.lower() or 'event loop is closed' in error_str.lower():
                    logger.warning(f"⚠️ Event loop уже закрыт, пропускаем остановку Application")
                else:
                    logger.warning(f"⚠️ Ошибка при остановке Application: {e}")
            
            try:
                await application.shutdown()
                logger.info("✅ Application завершен")
            except Exception as e:
                error_str = str(e)
                if 'different loop' in error_str.lower() or 'event loop is closed' in error_str.lower():
                    logger.warning(f"⚠️ Event loop уже закрыт, пропускаем shutdown Application")
                else:
                    logger.warning(f"⚠️ Ошибка при shutdown Application: {e}")
        
        # Запускаем в event loop
        try:
            # Регистрируем обработчики сигналов перед запуском
            def signal_handler_async(signum, frame):
                """Обработчик сигналов для async контекста"""
                logger.info(f"📡 Получен сигнал {signum}, устанавливаем флаг остановки...")
                shutdown_event.set()
            
            signal.signal(signal.SIGTERM, signal_handler_async)
            signal.signal(signal.SIGINT, signal_handler_async)
            
            asyncio.run(run_bot())
        except KeyboardInterrupt:
            logger.info("📡 Получен KeyboardInterrupt, завершаем работу...")
            shutdown_event.set()
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при запуске бота: {e}", exc_info=True)
            raise
    else:
        # Режим POLLING (для разработки/тестирования)
        logger.info("🔄 Запуск бота в режиме POLLING")
        logger.info("💡 Для продакшена установите TELEGRAM_WEBHOOK_URL")
        
        # Удаляем webhook, если он был установлен ранее
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(application.bot.delete_webhook(drop_pending_updates=True))
            loop.close()
            logger.info("✅ Старый webhook удален")
        except Exception as e:
            logger.warning(f"⚠️  Не удалось удалить webhook: {e}")
        
        # Запускаем polling (блокирующий вызов - не нужен дополнительный цикл)
        logger.info("🔄 Запуск polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


def cleanup_stuck_generations_on_startup():
    """Очистка зависших генераций при запуске бота (синхронная функция)"""
    logger.info("🔍 Проверка зависших генераций при запуске...")
    try:
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        ten_minutes_ago = (now - timedelta(minutes=10)).isoformat()
        
        if db_type == 'postgresql':
            cursor.execute("""
                SELECT e1.user_id, e1.timestamp
                FROM events e1
                WHERE e1.event_type = 'natal_chart_generation_start'
                AND e1.timestamp < %s
                AND NOT EXISTS (
                    SELECT 1 
                    FROM events e2 
                    WHERE e2.user_id = e1.user_id 
                    AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                    AND e2.timestamp > e1.timestamp
                )
            """, (ten_minutes_ago,))
        else:
            cursor.execute("""
                SELECT e1.user_id, e1.timestamp
                FROM events e1
                WHERE e1.event_type = 'natal_chart_generation_start'
                AND e1.timestamp < ?
                AND NOT EXISTS (
                    SELECT 1 
                    FROM events e2 
                    WHERE e2.user_id = e1.user_id 
                    AND e2.event_type IN ('natal_chart_success', 'natal_chart_error')
                    AND e2.timestamp > e1.timestamp
                )
            """, (ten_minutes_ago,))
        
        stuck_generations = cursor.fetchall()
        
        if stuck_generations:
            logger.warning(f"⚠️ Найдено {len(stuck_generations)} незавершенных генераций при запуске (вероятно из-за перезапуска контейнера)")
            for row in stuck_generations:
                user_id = row[0]
                start_time_str = str(row[1])
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    duration_minutes = (now - start_time).total_seconds() / 60
                    
                    # Логируем как ошибку перезапуска
                    error_data = {
                        'error_type': 'ContainerRestart',
                        'error_message': f'Генерация была прервана из-за перезапуска контейнера. Длительность до перезапуска: {duration_minutes:.1f} минут',
                        'stage': 'generation',
                        'stuck_duration_minutes': duration_minutes,
                        'generation_start': start_time_str,
                        'detected_at_startup': True
                    }
                    log_event(user_id, 'natal_chart_error', error_data)
                    logger.info(f"   ✅ Зависшая генерация для user_id {user_id} залогирована как ContainerRestart")
                except Exception as e:
                    logger.warning(f"   ⚠️ Ошибка при обработке зависшей генерации для user_id {user_id}: {e}")
        else:
            logger.info("✅ Незавершенных генераций не найдено")
        
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке зависших генераций при запуске: {e}", exc_info=True)


if __name__ == '__main__':
    # Инициализация базы данных при запуске
    logger.info("Запуск инициализации базы данных...")
    try:
        init_db()
        logger.info("Инициализация БД завершена успешно")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при инициализации БД: {e}", exc_info=True)
        logger.error("Бот не может быть запущен без инициализированной БД!")
        sys.exit(1)
    
    # Очистка зависших генераций при запуске (синхронная функция)
    try:
        cleanup_stuck_generations_on_startup()
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке зависших генераций: {e}", exc_info=True)
        # Не останавливаем бота из-за этого
    
    logger.info("Запуск бота...")
    main()
