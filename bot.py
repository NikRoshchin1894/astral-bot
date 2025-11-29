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
from datetime import datetime
from typing import Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.error import Conflict
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
from datetime import datetime, timezone
import pytz
from timezonefinder import TimezoneFinder

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
DATABASE_URL = os.getenv('DATABASE_URL')
DATABASE = 'users.db'  # Для SQLite локально

# Логируем состояние DATABASE_URL при запуске
if DATABASE_URL:
    logger.info(f"✅ DATABASE_URL найдена (первые 20 символов: {DATABASE_URL[:20]}...)")
else:
    logger.warning("⚠️ DATABASE_URL не найдена в переменных окружения! Используется SQLite.")

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

    birth_place = user_data.get('birth_place', '')
    if ',' in birth_place:
        parts = birth_place.split(',')
        city = parts[0].strip()
        country = ','.join(parts[1:]).strip() if len(parts) > 1 else ''
    else:
        city = birth_place
        country = ''

    # Получаем текущий статус оплаты
    if db_type == 'postgresql':
        cursor.execute('SELECT has_paid FROM users WHERE user_id = %s', (user_id,))
    else:
        cursor.execute('SELECT has_paid FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    has_paid = row[0] if row else 0

    # Сохраняем профиль
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
            user_data.get('birth_name', ''),
            country,
            city,
            user_data.get('birth_date', ''),
            user_data.get('birth_time', ''),
            birth_place,
            has_paid,
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
            user_data.get('birth_name', ''),
            country,
            city,
            user_data.get('birth_date', ''),
            user_data.get('birth_time', ''),
            birth_place,
            has_paid,
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
    try:
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        data_json = json.dumps(event_data, ensure_ascii=False) if event_data else None
        
        if db_type == 'postgresql':
            cursor.execute('''
                INSERT INTO events (user_id, event_type, event_data, timestamp)
                VALUES (%s, %s, %s, %s)
            ''', (
                user_id,
                event_type,
                data_json,
                datetime.now().isoformat()
            ))
        else:
            cursor.execute('''
                INSERT INTO events (user_id, event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (
                user_id,
                event_type,
                data_json,
                datetime.now().isoformat()
            ))
        conn.commit()
        conn.close()
        logger.info(f"Event logged: {event_type} for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to log event: {e}")


def user_has_paid(user_id: int) -> bool:
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    
    if db_type == 'postgresql':
        cursor.execute('SELECT has_paid FROM users WHERE user_id = %s', (user_id,))
    else:
        cursor.execute('SELECT has_paid FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False


def mark_user_paid(user_id: int):
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
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
    user = update.effective_user
    user_id = user.id
    
    # Сохраняем username в базу данных
    save_user_username(user_id, user.username, user.first_name)
    
    # Логируем событие старта
    log_event(user_id, 'start', {
        'username': user.username,
        'first_name': user.first_name,
        'language_code': user.language_code
    })
    
    welcome_message = f'''🌟 *Добро пожаловать в АстроБот, {user.first_name}!* 🌟

Этот бот поможет вам получить персональную натальную карту на основе ваших данных рождения.

💳 Стоимость детальной натальной карты — *{NATAL_CHART_PRICE_RUB} ₽*.'''

    buttons = [
        InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
        InlineKeyboardButton("🪐 Положение планет", callback_data='planets_info'),
        InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
        InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support'),
    ]
    
    keyboard = InlineKeyboardMarkup([[b] for b in buttons])
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
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Логируем событие нажатия кнопки
    log_event(user_id, 'button_click', {
        'button': data
    })
    
    if data == 'my_profile':
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
        # ВРЕМЕННО: Оплата отключена, сразу запускаем генерацию
        # TODO: Вернуть start_payment_process после настройки платежной системы
        await handle_natal_chart_request(query, context)
    elif data == 'support':
        await show_support(query, context)
    elif data == 'planets_info':
        await show_planets_info(query, context)
    elif data == 'get_planets_data':
        await handle_planets_request(query, context)


async def back_to_menu(query):
    """Вернуться в главное меню"""
    buttons = [
        InlineKeyboardButton("📋 Данные о рождении", callback_data='my_profile'),
        InlineKeyboardButton("🪐 Положение планет", callback_data='planets_info'),
        InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
        InlineKeyboardButton("💬 Поддержка и обратная связь", callback_data='support'),
    ]
    
    keyboard = InlineKeyboardMarkup([[b] for b in buttons])
    await query.edit_message_text(
        "🌟 *Главное меню*\n\nВыберите раздел:",
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

📧 @Astral_bot_support

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
    
    info_message = f'''🪐 *Положение планет*

Здесь вы можете получить данные, на основе которых строится ваша натальная карта:

• Положение планет (Солнце, Луна, Меркурий, Венера, Марс, Юпитер, Сатурн, Уран, Нептун, Плутон)
• Ваши дома (куспиды домов)
• Асцендент, MC, IC, Десцендент
• Лунные узлы
• Аспекты между планетами

Чтобы получить интерпретацию этих данных, перейдите в пункт "📜 Натальная карта" и оплатите {NATAL_CHART_PRICE_RUB} ₽.'''
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Узнать положение планет", callback_data='get_planets_data')],
        [InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')]
    ])
    
    await query.edit_message_text(
        info_message,
        reply_markup=keyboard,
        parse_mode='Markdown'
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
    
    lines.append("\n💡 <i>Для получения интерпретации этих данных перейдите в раздел '📜 Натальная карта'</i>")
    
    return "\n".join(lines)


async def handle_planets_request(query, context):
    """Обработка запроса на получение данных о планетах"""
    user_id = query.from_user.id
    
    # Логируем запрос данных о планетах
    log_event(user_id, 'planets_data_requested', {})
    
    # Загружаем профиль пользователя
    profile = load_user_profile(user_id)
    
    # Проверяем наличие всех необходимых данных
    has_profile = profile and all([
        profile.get('birth_name'), 
        profile.get('birth_date'), 
        profile.get('birth_time'), 
        profile.get('birth_place')
    ])
    
    if not has_profile:
        # Логируем попытку запроса без профиля
        log_event(user_id, 'planets_data_request_no_profile', {})
        await query.edit_message_text(
            "❌ *Данные не заполнены*\n\n"
            "Для получения данных о положении планет необходимо заполнить данные о рождении.\n\n"
            "💡 Вы можете ввести данные любого человека.\n\n"
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
            [InlineKeyboardButton(f"📜 Получить интерпретацию ({NATAL_CHART_PRICE_RUB} ₽)", callback_data='natal_chart')],
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


async def my_profile(query, context):
    """Данные о рождении"""
    user_id = query.from_user.id
    
    # Логируем просмотр профиля
    log_event(user_id, 'profile_viewed', {})
    user_data = context.user_data
    
    db_data = load_user_profile(user_id)
    if db_data:
        user_data.update(db_data)
    
    has_profile = all(key in user_data for key in ['birth_name', 'birth_date', 'birth_time', 'birth_place'])
    paid_status = user_data.get('has_paid') or user_has_paid(user_id)
    if paid_status:
        user_data['has_paid'] = True
    
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

💡 Вы можете ввести данные любого человека для расчета натальной карты.

❌ Данные не заполнены

Для получения натальной карты необходимо заполнить данные.'''
        
        buttons = [
            InlineKeyboardButton("➕ Заполнить данные", callback_data='edit_profile'),
            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
        ]
    
    keyboard = InlineKeyboardMarkup([[button] for button in buttons])
    await query.edit_message_text(
        profile_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


async def select_edit_field(query, context):
    """Выбор поля для редактирования"""
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


async def start_payment_process(query, context):
    """Начало процесса оплаты через Telegram Payments"""
    user_id = query.from_user.id
    
    # Логируем начало процесса оплаты
    log_event(user_id, 'payment_start', {
        'amount_rub': NATAL_CHART_PRICE_RUB,
        'amount_minor': NATAL_CHART_PRICE_MINOR
    })
    
    provider_token = os.getenv('TELEGRAM_PROVIDER_TOKEN')
    if not provider_token:
        logger.error(f"TELEGRAM_PROVIDER_TOKEN не установлен для пользователя {user_id}")
        await query.answer(
            "❌ Настройка оплаты не завершена.\n\n"
            "Для получения тестового токена провайдера:\n"
            "1. Откройте @BotFather в Telegram\n"
            "2. Отправьте /mybots\n"
            "3. Выберите вашего бота\n"
            "4. Выберите 'Payments'\n"
            "5. Выберите 'Test' для тестового токена\n"
            "6. Скопируйте токен и добавьте в переменную окружения TELEGRAM_PROVIDER_TOKEN",
            show_alert=True
        )
        log_event(user_id, 'payment_error', {'error': 'provider_token_not_set'})
        return
    
    logger.info(f"Используется provider_token для создания invoice (первые 10 символов: {provider_token[:10]}...)")
    logger.info(f"💰 Создание invoice: цена = {NATAL_CHART_PRICE_RUB} ₽ ({NATAL_CHART_PRICE_MINOR} копеек)")
    
    # Валидация: проверяем, что цена в допустимых пределах для Telegram Payments
    if NATAL_CHART_PRICE_MINOR < 1 or NATAL_CHART_PRICE_MINOR > 999999999:
        logger.error(f"❌ Некорректная цена для платежа: {NATAL_CHART_PRICE_MINOR} копеек")
        await query.answer("Ошибка: некорректная цена. Свяжитесь с администратором.", show_alert=True)
        log_event(user_id, 'payment_error', {'error': 'invalid_price', 'amount_minor': NATAL_CHART_PRICE_MINOR})
        return

    prices = [LabeledPrice(label='Натальная карта', amount=NATAL_CHART_PRICE_MINOR)]
    payload = f"natal_chart:{query.from_user.id}:{uuid.uuid4()}"

    await query.answer()
    
    try:
        await query.message.reply_invoice(
            title='Натальная карта',
            description=f'Подробная натальная карта в PDF-формате. Стоимость {NATAL_CHART_PRICE_RUB} ₽.',
            payload=payload,
            provider_token=provider_token,
            currency='RUB',
            prices=prices,
            need_name=True
        )
        logger.info(f"✅ Invoice успешно отправлен пользователю {user_id}")
    except Exception as invoice_error:
        logger.error(f"❌ Ошибка при отправке invoice: {invoice_error}", exc_info=True)
        log_event(user_id, 'payment_error', {'error': str(invoice_error), 'stage': 'invoice_creation'})
        await query.answer("Ошибка при создании платежа. Попробуйте позже.", show_alert=True)
        return

    menu_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
    ]])
    await query.message.reply_text(
        "Если хотите вернуться, нажмите «Главное меню».",
        reply_markup=menu_keyboard
    )


async def start_edit_field(query, context, field_type):
    """Начало редактирования конкретного поля"""
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
    
    has_profile = all(key in user_data for key in ['birth_name', 'birth_date', 'birth_time', 'birth_place'])
    
    if not has_profile:
        # Логируем попытку запроса натальной карты без профиля
        log_event(user_id, 'natal_chart_request_no_profile', {})
        await query.edit_message_text(
            "❌ *Данные не заполнены*\n\n"
            "Для получения натальной карты необходимо заполнить данные о рождении.\n\n"
            "💡 Вы можете ввести данные любого человека.\n\n"
            "Нажмите кнопку ниже, чтобы заполнить данные:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Заполнить данные", callback_data='natal_chart_start'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    # ВРЕМЕННО: Оплата отключена, сразу запускаем генерацию
    # TODO: Вернуть проверку оплаты после настройки платежной системы
    
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
        "⏳ *Генерация натальной карты...*\n\n"
        "Пожалуйста, подождите. Обычно это занимает не более 5 минут.",
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
    
    # ВРЕМЕННО: Оплата отключена
    payment_consumed = False
    
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
            
            # Отправляем сообщение об ошибке
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ *Ошибка генерации*\n\n"
                         "Генерация натальной карты заняла слишком много времени.\n"
                         "Попробуйте ещё раз.\n\n"
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
            log_event(user_id, 'natal_chart_error', pdf_error_details)
            
            # Отправляем сообщение об ошибке пользователю
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ *Ошибка*\n\n"
                         "К сожалению, не удалось сгенерировать натальную карту.\n"
                         "Попробуйте ещё раз позже.\n\n"
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
                with open(pdf_path, 'rb') as pdf_file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=pdf_file,
                        filename=filename,
                        caption=caption
                    )

                # ВРЕМЕННО: Оплата отключена
                # payment_consumed = True
                
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
            except Exception as pdf_error:
                error_type = type(pdf_error).__name__
                error_message = str(pdf_error)
                logger.error(f"❌ ОШИБКА при отправке PDF пользователю {user_id}: {error_type}: {error_message}", exc_info=True)
                
                log_event(user_id, 'natal_chart_error', {
                    'error_type': error_type,
                    'error_message': error_message,
                    'stage': 'pdf_send',
                    'filename': filename,
                    'pdf_path': pdf_path if pdf_path else None
                })
                await send_text_message("⚠️ Не удалось отправить PDF. Попробуйте позже.", chat_id, message_id, is_edit=True)
                # Добавляем кнопку Повторить попытку
                retry_keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Попробовать снова", callback_data='natal_chart'),
                    InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
                ]])
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Вы можете повторить попытку генерации отчёта.",
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
            log_event(user_id, 'natal_chart_error', {
                'error_type': 'PDFNotCreated',
                'error_message': 'PDF generation returned None',
                'stage': 'pdf_creation',
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
                text="Вы можете повторить попытку генерации отчёта.",
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
        
        log_event(user_id, 'natal_chart_error', error_details)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ *Ошибка*\n\n"
                     "Произошла ошибка при генерации натальной карты.\n"
                     "Попробуйте ещё раз.",
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
        # Сначала удаляем информацию о генерации, чтобы предотвратить дублирующие запросы
        if user_id in active_generations:
            del active_generations[user_id]
        
        # ВРЕМЕННО: Оплата отключена, не сбрасываем статус оплаты
        # TODO: Вернуть сброс оплаты после настройки платежной системы
        # if payment_consumed:
        #     reset_user_payment(user_id)
        #     logger.info(f"Оплата сброшена для пользователя {user_id} после успешной генерации натальной карты")


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
    """Рисует космический фон со звёздами для каждой страницы"""
    # Космические цвета
    dark_blue = HexColor('#0a0e27')  # Тёмно-синий космос
    deep_purple = HexColor('#1a1a3e')  # Глубокий фиолетовый
    star_gold = HexColor('#ffd700')  # Золотые звёзды
    star_silver = HexColor('#c0c0c0')  # Серебристые звёзды
    nebula_purple = HexColor('#6b3fa0')  # Туманность фиолетовая
    nebula_blue = HexColor('#2d5aa0')  # Туманность синяя
    
    width, height = A4
    
    # Градиентный фон (от тёмного к чуть светлее)
    canvas.setFillColor(dark_blue)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    
    # Добавляем туманность (градиентные круги)
    canvas.setFillColor(nebula_purple)
    canvas.setFillAlpha(0.15)
    canvas.circle(width * 0.2, height * 0.8, width * 0.3, fill=1, stroke=0)
    
    canvas.setFillColor(nebula_blue)
    canvas.setFillAlpha(0.1)
    canvas.circle(width * 0.8, height * 0.2, width * 0.4, fill=1, stroke=0)
    
    canvas.setFillAlpha(1.0)
    
    # Рисуем звёзды
    random.seed(42)  # Для одинаковых звёзд на всех страницах
    for _ in range(80):
        x = random.uniform(0, width)
        y = random.uniform(0, height)
        star_size = random.choice([1, 1.5, 2])
        star_color = random.choice([star_gold, star_silver])
        
        canvas.setFillColor(star_color)
        canvas.setFillAlpha(random.uniform(0.6, 1.0))
        canvas.circle(x, y, star_size, fill=1, stroke=0)
    
    canvas.setFillAlpha(1.0)
    
    # Декоративные линии по краям (космические поля)
    canvas.setStrokeColor(HexColor('#1a4a6a'))
    canvas.setStrokeAlpha(0.3)
    canvas.setLineWidth(1)
    # Верхняя линия
    canvas.line(0, height - 20, width, height - 20)
    # Нижняя линия
    canvas.line(0, 20, width, 20)
    
    canvas.setStrokeAlpha(1.0)


# Путь к статичному изображению натальной карты
NATAL_CHART_IMAGE_PATH = os.path.join(os.path.dirname(__file__), 'images', 'natal_chart.png')

# Вводный текст для натальной карты
INTRODUCTORY_TEXT = """Перед вами — персональный разбор вашей натальной карты.

Он создан на основе точных астрономических данных момента рождения: даты, времени и места. Это не прогноз и не гадание, а аналитическая модель, которая описывает ваши врождённые качества, эмоциональные реакции, сильные стороны, уязвимости, жизненные задачи и направления личного роста.

Натальная карта — это не инструкция, а навигация.

Она показывает возможности, внутренние механизмы и природные настройки, с которыми вы пришли в этот мир. Как именно они раскроются — зависит от выбора, опыта и зрелости каждого человека.

---

# 🌙 Как работать с разбором

## 1. Читайте спокойно и постепенно

Не нужно пытаться «освоить» всё сразу. Разбор объёмный, и ваша задача — почувствовать, что откликается.

Возвращайтесь к отчёту в разные периоды жизни: с каждым разом он будет читаться по-новому.

---

## 2. Отмечайте повторяющиеся темы

Если в разных разделах всплывают одинаковые мотивы — это ваши ключевые точки роста или силы.

Повтор в астрологии — не случайность, а акцент.

---

## 3. Сопоставляйте с реальностью

Смотрите, где описанные качества проявляются в вашей жизни:

— в отношениях

— в работе

— в характере

— в привычках

— в реакции на стресс

— в способах достижения целей

Это помогает увидеть закономерности и получить инсайты.

---

## 4. Записывайте наблюдения и открытия

Натальная карта — процесс, а не разовый документ.

Ведите заметки:

— что совпало

— что удивило

— где хочется развиваться

— какие изменения происходят со временем

Это делает разбор инструментом реального развития.

---

## 5. Используйте карту как компас, а не как ограничение

Если что-то кажется "не про вас", это не ошибка — это может быть потенциал, который ещё не раскрылся, или часть личности, которую вы привыкли подавлять.

Иногда карта отражает глубинные вещи, которые мы узнаём позже.

---

# ✨ Какие есть ограничения у разбора

Чтобы использовать документ экологично, важно понимать его рамки.

---

## 1. Астрология описывает потенциал, а не готовую личность

Карта — это «исходный код», который проявляется по-разному в разных условиях.

Жизненный опыт, травмы, воспитание и выбор человека могут усилить или ослабить проявления.

---

## 2. Натальная карта не даёт конкретных предсказаний

Она не скажет: «Будет так».

Она скажет: «Вот механизм. Вот направление. Вот вероятность».

Человек всегда остаётся ведущим.

---

## 3. Возможны погрешности времени рождения

Даже 5–10 минут могут изменить Асцендент, положение домов и акценты в интерпретации.

Если время рождения примерное — часть описаний может быть менее точной.

---

## 4. Разбор не заменяет психологию и терапию

Он даёт понимание почему что-то происходит, но не всегда отвечает "как именно" это изменить.

Это инструмент осознания, а не лечение.

---

## 5. Некоторые проявления раскрываются только с возрастом

Есть аспекты, которые включаются:

— после 21 года

— после 30 лет (Сатурн)

— после 40 (транзиты внешних планет)

Поэтому молодому человеку может казаться, что часть описаний «ещё не про него».

---

## 6. Карта не ограничивает, а показывает выборы

Негативные описания — это не приговор.

Это зоны, где человек может стать сильнее, мудрее и свободнее.

---

# 🌟 Главное

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


def draw_static_natal_chart_image(canvas, doc):
    """Рисует статичное изображение натальной карты на первой странице (половина страницы, прозрачный фон)"""
    if not os.path.exists(NATAL_CHART_IMAGE_PATH):
        # Если изображение не найдено, просто пропускаем (не критично)
        return
    
    try:
        from reportlab.lib.utils import ImageReader
        
        width, height = A4
        
        # Размер изображения - половина страницы по меньшей стороне
        page_min_dimension = min(width, height)
        image_size = page_min_dimension / 2  # Половина страницы
        
        # Центрируем изображение
        image_x = (width - image_size) / 2
        image_y = height - 140 - image_size  # Под заголовком (уменьшен отступ)
        
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

        # Космические цвета
        cosmic_text = HexColor('#e8e8f0')  # Светлый текст на тёмном фоне
        cosmic_gold = HexColor('#ffd700')  # Золотой для заголовков
        cosmic_silver = HexColor('#b0b0d0')  # Серебристый для подзаголовков
        cosmic_accent = HexColor('#9b59b6')  # Фиолетовый акцент
        
        # Используем BaseDocTemplate для кастомного PageTemplate
        width, height = A4
        left_margin = 80  # Увеличены отступы слева
        right_margin = 80  # Увеличены отступы справа
        top_margin = 60
        bottom_margin = 60
        
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
        
        # Переменная для отслеживания первой страницы
        first_page_drawn = {'flag': False}
        
        # Универсальная функция для всех страниц (рисует статичное изображение только на первой)
        def page_template_with_image(canvas, doc):
            draw_cosmic_background(canvas, doc)
            # Рисуем статичное изображение только на первой странице
            if not first_page_drawn['flag']:
                draw_static_natal_chart_image(canvas, doc)
                first_page_drawn['flag'] = True
        
        # Создаём PageTemplate (всегда используем функцию с изображением, даже если chart_data нет)
        cosmic_template = PageTemplate(
            id='cosmic_page',
            frames=[frame],
            onPage=page_template_with_image
        )
        
        doc.addPageTemplates([cosmic_template])

        styles = getSampleStyleSheet()
        
        # Базовый стиль с космическим цветом текста и выравниванием по ширине
        base_style = ParagraphStyle(
            'Base',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=16,
            leading=24,
            spaceAfter=8,
            textColor=cosmic_text,
            backColor=None,
            alignment=4  # 4 = TA_JUSTIFY (выравнивание по ширине)
        )
        
        # Заголовки с космическим оформлением
        heading_styles = {
            1: ParagraphStyle(
                'H1', 
                parent=base_style, 
                fontSize=24, 
                leading=30, 
                spaceBefore=20, 
                spaceAfter=12,
                textColor=cosmic_gold,
                fontName=font_name,
                alignment=0  # 0 = TA_LEFT (по левому краю для заголовков)
            ),
            2: ParagraphStyle(
                'H2', 
                parent=base_style, 
                fontSize=20, 
                leading=26, 
                spaceBefore=16, 
                spaceAfter=10,
                textColor=cosmic_gold,
                fontName=font_name,
                alignment=0  # По левому краю для заголовков
            ),
            3: ParagraphStyle(
                'H3', 
                parent=base_style, 
                fontSize=17, 
                leading=22, 
                spaceBefore=14, 
                spaceAfter=8,
                textColor=cosmic_silver,
                fontName=font_name,
                alignment=0  # По левому краю для подзаголовков
            ),
        }
        
        # Стиль для заголовка документа (по центру)
        title_style = ParagraphStyle(
            'Title', 
            parent=base_style, 
            fontSize=28, 
            leading=34, 
            alignment=1,  # 1 = TA_CENTER (по центру)
            spaceAfter=20,
            textColor=cosmic_gold,
            fontName=font_name
        )

        story = []
        
        # ===== СТРАНИЦА 1: ТИТУЛЬНЫЙ ЛИСТ =====
        # Заголовок документа с космическим оформлением
        if title:
            title_text = f"<b>✦ {_clean_inline_markdown(title)} ✦</b>"
            story.append(Paragraph(title_text, title_style))
            story.append(Spacer(1, 15))
        
        # Добавляем место для статичного изображения на первой странице (половина страницы)
        # Проверяем, существует ли изображение
        if os.path.exists(NATAL_CHART_IMAGE_PATH):
            width, height = A4
            image_size = min(width, height) / 2  # Половина страницы
            story.append(Spacer(1, image_size + 20))  # Место для изображения + уменьшенный отступ
        
        # ===== РАЗРЫВ СТРАНИЦЫ =====
        story.append(PageBreak())
        
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
        
        story.append(Paragraph("<b>✦ Содержание ✦</b>", toc_title_style))
        story.append(Spacer(1, 20))
        
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
        
        # Добавляем пункты содержания с кликабельными ссылками
        for level, heading_text, anchor_name in section_headings:
            cleaned_heading = _clean_inline_markdown(heading_text)
            # Создаем кликабельную ссылку в содержании
            # Используем тег <link> для создания внутренней ссылки
            link_text = f'<link destination="{anchor_name}" color="#ffd700"><u>• {cleaned_heading}</u></link>'
            story.append(Paragraph(link_text, toc_item_style))
        
        # ===== РАЗРЫВ СТРАНИЦЫ =====
        story.append(PageBreak())
        
        # ===== СТРАНИЦА 3: ВВОДНЫЙ ТЕКСТ =====
        # Добавляем вводный текст
        intro_lines = INTRODUCTORY_TEXT.split('\n')
        for raw_line in intro_lines:
            line = raw_line.rstrip('\r')
            if not line.strip():
                story.append(Spacer(1, 10))
                continue
            
            stripped = line.lstrip()
            heading_level = 0
            if stripped.startswith('#'):
                heading_level = len(stripped) - len(stripped.lstrip('#'))
                stripped = stripped.lstrip('#').strip()
                
                if heading_level == 1:
                    stripped = f"✦ {stripped} ✦"
            
            bullet = False
            if stripped.startswith(('- ', '* ', '+ ')):
                bullet = True
                stripped = stripped[2:].strip()
                bullet_char = "✦"
            
            cleaned = _clean_inline_markdown(stripped)
            if heading_level and heading_level in heading_styles:
                story.append(Paragraph(cleaned, heading_styles[heading_level]))
            elif bullet:
                story.append(Paragraph(f"{bullet_char} {cleaned}", base_style))
            else:
                story.append(Paragraph(cleaned, base_style))
        
        # ===== РАЗРЫВ СТРАНИЦЫ =====
        story.append(PageBreak())
        
        # ===== ОСНОВНОЙ КОНТЕНТ =====
        # Обработка содержимого с космическим форматированием
        for raw_line in lines:
            line = raw_line.rstrip('\r')
            if line.strip() == '[[PAGE_BREAK]]':
                story.append(PageBreak())
                continue
            if not line.strip():
                story.append(Spacer(1, 10))
                continue

            stripped = line.lstrip()
            heading_level = 0
            if stripped.startswith('#'):
                heading_level = len(stripped) - len(stripped.lstrip('#'))
                stripped = stripped.lstrip('#').strip()
                
                # Для заголовков второго уровня (разделы) добавляем якорь для навигации
                # Используем тег <a name="..."> в самом заголовке
                if heading_level == 2:
                    # Генерируем имя для anchor из заголовка
                    anchor_name = _generate_anchor_name(stripped)
                    # Добавляем якорь в начало заголовка через тег <a name="...">
                    stripped = f'<a name="{anchor_name}"/>{stripped}'
                
                # Добавляем космические символы к заголовкам разделов
                if heading_level == 1:
                    stripped = f"✦ {stripped} ✦"

            bullet = False
            if stripped.startswith(('- ', '* ', '+ ')):
                bullet = True
                stripped = stripped[2:].strip()
                # Космические символы для списков
                bullet_char = "✦"

            cleaned = _clean_inline_markdown(stripped)
            if heading_level and heading_level in heading_styles:
                story.append(Paragraph(cleaned, heading_styles[heading_level]))
            elif bullet:
                story.append(Paragraph(f"{bullet_char} {cleaned}", base_style))
            else:
                story.append(Paragraph(cleaned, base_style))

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
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
    ]])
    
    await query.edit_message_text(
        "📜 *Создание натальной карты*\n\n"
        "💡 Вы можете ввести данные любого человека для расчета натальной карты.\n\n"
        "Мне понадобятся следующие данные:\n"
        "1️⃣ Имя\n"
        "2️⃣ Дата рождения\n"
        "3️⃣ Время рождения\n"
        "4️⃣ Место рождения\n\n"
        "‼️ *Важно:* первым сообщением отправьте _только имя_ (без даты, времени и места).\n"
        "После этого я по очереди попрошу остальные данные.\n\n"
        "Пожалуйста, начните с отправки имени:",
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
        user_data['birth_name'] = text
        user_data['natal_chart_state'] = 'date'
        await update.message.reply_text(
            "✅ Имя сохранено!\n\n"
            "📅 Теперь введите дату рождения в формате: ДД.ММ.ГГГГ\n"
            "Например: 15.03.1990",
            reply_markup=back_button
        )
    elif state == 'date':
        is_valid, error_msg = validate_date(text)
        if not is_valid:
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите дату в правильном формате: ДД.ММ.ГГГГ\n"
                "Например: 15.03.1990",
                reply_markup=back_button
            )
            return
        
        user_data['birth_date'] = text
        user_data['natal_chart_state'] = 'time'
        await update.message.reply_text(
            "✅ Дата рождения сохранена!\n\n"
            "🕐 Теперь введите время рождения в формате: ЧЧ:ММ\n"
            "Например: 14:30",
            reply_markup=back_button
        )
    elif state == 'time':
        is_valid, error_msg = validate_time(text)
        if not is_valid:
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите время в правильном формате: ЧЧ:ММ\n"
                "Например: 14:30",
                reply_markup=back_button
            )
            return
        
        user_data['birth_time'] = text
        user_data['natal_chart_state'] = 'place'
        await update.message.reply_text(
            "✅ Время рождения сохранено!\n\n"
            "🌍 Теперь введите место рождения (город, страна)\n"
            "Например: Москва, Россия",
            reply_markup=back_button
        )
    elif state == 'place':
        is_valid, error_msg = validate_place(text)
        if not is_valid:
            await update.message.reply_text(
                f"❌ {error_msg}\n\n"
                "Пожалуйста, введите место рождения (город, страна)\n"
                "Например: Москва, Россия",
                reply_markup=back_button
            )
            return
        
        user_data['birth_place'] = text
        user_data['natal_chart_state'] = 'complete'
        
        user_id = update.message.from_user.id
        save_user_profile(user_id, user_data)
        
        # Логируем полное заполнение профиля
        log_event(user_id, 'profile_complete', {
            'birth_name': user_data.get('birth_name'),
            'birth_date': user_data.get('birth_date'),
            'birth_time': user_data.get('birth_time'),
            'birth_place': user_data.get('birth_place')
        })
        
        await update.message.reply_text(
            "✅ *Профиль успешно сохранен!*\n\n"
            "Теперь вы можете получить свою натальную карту.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📜 Получить карту", callback_data='natal_chart'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]])
        )
        
        user_data.pop('natal_chart_state', None)
    
    # Обработка редактирования полей
    elif state == 'edit_name':
        user_data['birth_name'] = text
        user_data.pop('natal_chart_state', None)
        user_id = update.message.from_user.id
        save_user_profile(user_id, user_data)
        await update.message.reply_text(
            "✅ Имя успешно изменено!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Данные", callback_data='my_profile'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]])
        )
    
    elif state == 'edit_date':
        is_valid, error_msg = validate_date(text)
        if not is_valid:
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
        await update.message.reply_text(
            "✅ Дата рождения успешно изменена!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Данные", callback_data='my_profile'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]])
        )
    
    elif state == 'edit_time':
        is_valid, error_msg = validate_time(text)
        if not is_valid:
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
        await update.message.reply_text(
            "✅ Время рождения успешно изменено!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Данные", callback_data='my_profile'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]])
        )
    
    elif state == 'edit_place':
        is_valid, error_msg = validate_place(text)
        if not is_valid:
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
        await update.message.reply_text(
            "✅ Место рождения успешно изменено!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Данные", callback_data='my_profile'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]])
        )


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
        
        # Определение часового пояса по координатам
        tf = TimezoneFinder()
        try:
            timezone_str = tf.timezone_at(lat=lat, lng=lon)
            if timezone_str:
                tz = pytz.timezone(timezone_str)
                logger.info(f"Часовой пояс места рождения: {timezone_str}")
            else:
                # Если не удалось определить, используем UTC
                logger.warning(f"Не удалось определить часовой пояс для {lat}, {lon}, используется UTC")
                tz = pytz.UTC
        except Exception as e:
            logger.warning(f"Ошибка определения часового пояса: {e}, используется UTC")
            tz = pytz.UTC
        
        # Создание datetime объекта в локальном времени места рождения
        local_dt = tz.localize(datetime(year, month, day, hour, minute))
        
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
            1: "- Раздел 1 (не менее 4 000 символов): Опиши особенности личности на основе Солнца и Луны",
            2: "- Раздел 2 (не менее 2 000 символов): Опиши как человека видят другие люди на основе асцендента",
            3: "- Раздел 3 (не менее 7 000 символов): Опиши сильные стороны (как они проявляются, как можно их усилить; упомяни планеты, дома, аспекты) и слабые стороны (как они проявляются, как можно их исправить; упомяни планеты, дома, аспекты)",
            4: "- Раздел 4 (не менее 3 000 символов): Сфера карьеры и финансов (врожденные таланты; подходящие профессии; сильные стороны на работе и как нужно проявляться, чтобы достигать успех; способ реализации: найм, фриланс, бизнес; финансовая стратегия: копить или тратить; как поднять самооценку и обрести внутреннюю опору; где брать энергию и как мотивировать себя; упомяни планеты, дома, аспекты)",
            5: "- Раздел 5 (не менее 3 000 символов): Сфера романтических отношений (Типаж идеального партнера, который нравится; типаж идеального партнера, с которым получится построить отношения; какие могут быть трудности в отношениях и что делать с трудностями; упомяни планеты, дома, аспекты)",
            6: "- Раздел 6 (не менее 2 000 символов): Физическая активность и спорт (какой вид физической активности подходит по Марсу; как нужно следить за здоровьем физическим и ментальным; упомяни планеты, дома, аспекты)",
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
            fallback_pdf = generate_pdf_from_markdown(
                fallback_text,
                f"Натальная карта: {birth_data.get('name', 'Пользователь')}",
                fallback_chart_data
            )
        except Exception as pdf_error:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать даже fallback PDF: {pdf_error}", exc_info=True)
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
        if not query.invoice_payload.startswith('natal_chart:'):
            logger.warning(f"❌ Неверный payload: {query.invoice_payload}")
            log_event(user_id, 'payment_error', {'error': 'invalid_payload', 'payload': query.invoice_payload})
            await query.answer(ok=False, error_message='Некорректный платежный запрос')
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
    
    has_profile = all(key in user_data for key in ['birth_name', 'birth_date', 'birth_time', 'birth_place'])
    
    if not has_profile:
        # Если профиль не заполнен, показываем сообщение о необходимости заполнить данные
        await message.reply_text(
            "✅ Оплата получена!\n\n"
            "❌ *Данные не заполнены*\n\n"
            "Для получения натальной карты необходимо заполнить данные о рождении.\n\n"
            "💡 Вы можете ввести данные любого человека.\n\n"
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
    
    # Запускаем генерацию в фоне
    asyncio.create_task(generate_natal_chart_background(user_id, context))


def main():
    """Запуск бота"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
        return
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Логирование событий теперь происходит внутри самих обработчиков,
    # чтобы не блокировать обработку команд и callback queries
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    
    # Задержка перед запуском для предотвращения конфликтов при одновременном старте нескольких инстансов
    time.sleep(2)
    
    logger.info("Бот запущен!")
    
    # Попытки запуска с обработкой ошибки Conflict
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            # Удаляем webhook перед polling (асинхронно через run_polling)
            logger.info(f"Попытка запуска {attempt + 1}/{max_retries}...")
            
            # run_polling автоматически удаляет webhook и использует drop_pending_updates
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,  # Пропускаем старые обновления
                close_loop=False
            )
            # Если дошли сюда, значит бот остановлен нормально
            break
            
        except Conflict as e:
            logger.error(f"Конфликт обнаружен: {e}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.warning(f"Ожидание {wait_time} секунд перед повторной попыткой...")
                time.sleep(wait_time)
                logger.info("Повторная попытка запуска...")
            else:
                logger.error("Достигнуто максимальное количество попыток. Возможно, другой инстанс бота уже запущен.")
                logger.error("Убедитесь, что запущен только один экземпляр бота на платформе.")
                sys.exit(1)
                
        except KeyboardInterrupt:
            logger.info("Бот остановлен пользователем")
            break
            
        except Exception as e:
            logger.error(f"Критическая ошибка при запуске бота: {e}")
            raise


if __name__ == '__main__':
    # Инициализация базы данных при запуске
    logger.info("Запуск инициализации базы данных...")
    try:
        init_db()
        logger.info("Инициализация БД завершена успешно, запуск бота...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при инициализации БД: {e}", exc_info=True)
        logger.error("Бот не может быть запущен без инициализированной БД!")
        sys.exit(1)
    main()
