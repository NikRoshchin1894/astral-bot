#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Astral Bot - Astrology Telegram Bot
Астрологический бот для консультаций и получения информации о знаках зодиака
"""

import logging
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from dotenv import load_dotenv
from openai import OpenAI
import sqlite3

# Загружаем переменные окружения
load_dotenv()

# База данных
DATABASE = 'users.db'

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DATABASE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            country TEXT,
            city TEXT,
            birth_date TEXT,
            birth_time TEXT,
            updated_at TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("База данных инициализирована")


def save_user_profile(user_id, user_data):
    """Сохранение профиля пользователя в базу данных"""
    conn = sqlite3.connect(DATABASE)
    
    birth_place = user_data.get('birth_place', '')
    if ',' in birth_place:
        parts = birth_place.split(',')
        city = parts[0].strip()
        country = ','.join(parts[1:]).strip() if len(parts) > 1 else ''
    else:
        city = birth_place
        country = ''
    
    conn.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, first_name, country, city, birth_date, birth_time, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        user_data.get('birth_name', ''),
        country,
        city,
        user_data.get('birth_date', ''),
        user_data.get('birth_time', ''),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def load_user_profile(user_id):
    """Загрузка профиля пользователя из базы данных"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        columns = ['user_id', 'first_name', 'last_name', 'country', 'city', 
                   'birth_date', 'birth_time', 'updated_at']
        result = dict(zip(columns, row))
        
        user_data = {}
        if result['first_name']:
            user_data['birth_name'] = result['first_name']
        if result['birth_date']:
            user_data['birth_date'] = result['birth_date']
        if result['birth_time']:
            user_data['birth_time'] = result['birth_time']
        
        if result['city'] and result['country']:
            user_data['birth_place'] = f"{result['city']}, {result['country']}"
        elif result['city']:
            user_data['birth_place'] = result['city']
        
        return user_data
    return {}




async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    welcome_message = f'''🌟 *Добро пожаловать в АстроБот, {user.first_name}!* 🌟

Этот бот поможет вам получить персональную натальную карту на основе ваших данных рождения.

*Доступные функции:*
👤 Мой профиль - заполните данные о себе
📜 Натальная карта - персональная астрологическая карта

Используйте меню ниже:'''

    buttons = [
        InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile'),
        InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
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
    
    data = query.data
    
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


async def back_to_menu(query):
    """Вернуться в главное меню"""
    buttons = [
        InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile'),
        InlineKeyboardButton("📜 Натальная карта", callback_data='natal_chart'),
    ]
    
    keyboard = InlineKeyboardMarkup([[b] for b in buttons])
    await query.edit_message_text(
        "🌟 *Главное меню*\n\nВыберите раздел:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


async def my_profile(query, context):
    """Мой профиль"""
    user_id = query.from_user.id
    user_data = context.user_data
    
    db_data = load_user_profile(user_id)
    if db_data:
        user_data.update(db_data)
    
    has_profile = all(key in user_data for key in ['birth_name', 'birth_date', 'birth_time', 'birth_place'])
    
    if has_profile:
        profile_text = f'''👤 *Мой профиль*

*Данные:*
🆔 Имя: {user_data.get('birth_name', 'Не указано')}
📅 Дата рождения: {user_data.get('birth_date', 'Не указано')}
🕐 Время рождения: {user_data.get('birth_time', 'Не указано')}
🌍 Место рождения: {user_data.get('birth_place', 'Не указано')}'''
        
        buttons = [
            InlineKeyboardButton("✏️ Редактировать профиль", callback_data='select_edit_field'),
            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
        ]
    else:
        profile_text = '''👤 *Мой профиль*

❌ Профиль не заполнен

Для получения натальной карты необходимо заполнить профиль.'''
        
        buttons = [
            InlineKeyboardButton("➕ Заполнить профиль", callback_data='edit_profile'),
            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
        ]
    
    keyboard = InlineKeyboardMarkup([buttons])
    await query.edit_message_text(
        profile_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


async def select_edit_field(query, context):
    """Выбор поля для редактирования"""
    await query.edit_message_text(
        "✏️ *Редактирование профиля*\n\n"
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


async def start_edit_field(query, context, field_type):
    """Начало редактирования конкретного поля"""
    user_data = context.user_data
    
    field_info = {
        'name': ('имя', 'Просто введите ваше имя'),
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
    user_data = context.user_data
    
    # Загружаем профиль из БД, если его нет в user_data
    if not user_data.get('birth_name'):
        user_id = query.from_user.id
        loaded_data = load_user_profile(user_id)
        if loaded_data:
            user_data.update(loaded_data)
    
    has_profile = all(key in user_data for key in ['birth_name', 'birth_date', 'birth_time', 'birth_place'])
    
    if not has_profile:
        await query.edit_message_text(
            "❌ *Профиль не заполнен*\n\n"
            "Для получения натальной карты необходимо заполнить профиль.\n\n"
            "Нажмите кнопку ниже, чтобы заполнить данные:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Заполнить профиль", callback_data='natal_chart_start'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )
        return
    
    await query.edit_message_text(
        "⏳ *Генерация натальной карты...*\n\n"
        "Пожалуйста, подождите..."
    )
    
    birth_data = {
        'name': user_data.get('birth_name', 'Пользователь'),
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
    
    try:
        natal_chart = generate_natal_chart_with_gpt(birth_data, openai_key)
        
        # Разбиваем сообщение на части, если оно слишком длинное (лимит Telegram - 4096 символов)
        max_length = 4000  # Оставляем запас для форматирования
        
        async def send_message_safe(text, is_edit=False):
            """Безопасная отправка сообщения с обработкой ошибок парсинга"""
            try:
                if is_edit:
                    await query.edit_message_text(text, parse_mode='Markdown')
                else:
                    await query.message.reply_text(text, parse_mode='Markdown')
            except Exception as e:
                # Если ошибка парсинга, очищаем Markdown и отправляем снова
                logger.warning(f"Ошибка парсинга Markdown: {e}, очищаем и отправляем без форматирования")
                cleaned_text = clean_markdown(text)
                try:
                    if is_edit:
                        await query.edit_message_text(cleaned_text, parse_mode='Markdown')
                    else:
                        await query.message.reply_text(cleaned_text, parse_mode='Markdown')
                except Exception as e2:
                    # Если все еще ошибка, отправляем как обычный текст без форматирования
                    logger.warning(f"Все еще ошибка после очистки: {e2}, отправляем без форматирования")
                    # Убираем все markdown символы
                    plain_text = text.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
                    if is_edit:
                        await query.edit_message_text(plain_text)
                    else:
                        await query.message.reply_text(plain_text)
        
        if len(natal_chart) <= max_length:
            await send_message_safe(natal_chart, is_edit=True)
        else:
            # Отправляем первую часть через edit_message_text
            first_part = natal_chart[:max_length]
            # Находим последний перенос строки, чтобы не разрывать предложения
            last_newline = first_part.rfind('\n')
            if last_newline > max_length * 0.8:  # Если есть разумный перенос строки
                first_part = natal_chart[:last_newline]
                remaining = natal_chart[last_newline+1:]
            else:
                remaining = natal_chart[max_length:]
            
            await send_message_safe(first_part, is_edit=True)
            
            # Отправляем оставшиеся части отдельными сообщениями
            while remaining:
                if len(remaining) <= max_length:
                    await send_message_safe(remaining, is_edit=False)
                    break
                else:
                    # Находим разумное место для разрыва
                    chunk = remaining[:max_length]
                    last_newline = chunk.rfind('\n')
                    if last_newline > max_length * 0.8:
                        chunk = remaining[:last_newline]
                        remaining = remaining[last_newline+1:]
                    else:
                        remaining = remaining[max_length:]
                    
                    await send_message_safe(chunk, is_edit=False)
        
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
        ]])
        await query.message.reply_text(
            "Используйте кнопки меню для навигации:",
            reply_markup=buttons
        )
        
    except Exception as e:
        logger.error(f"Ошибка при генерации натальной карты: {e}")
        await query.edit_message_text(
            "❌ *Ошибка*\n\n"
            "Произошла ошибка при генерации натальной карты.\n"
            "Попробуйте еще раз позже.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]]),
            parse_mode='Markdown'
        )


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


async def natal_chart_start(query, context):
    """Начало создания натальной карты"""
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu')
    ]])
    
    await query.edit_message_text(
        "📜 *Создание натальной карты*\n\n"
        "Мне понадобятся следующие данные:\n"
        "1️⃣ Ваше имя\n"
        "2️⃣ Дата рождения\n"
        "3️⃣ Время рождения\n"
        "4️⃣ Место рождения\n\n"
        "Пожалуйста, начните с отправки вашего имени:",
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
        
        await update.message.reply_text(
            "✅ *Профиль успешно сохранен!*\n\n"
            "Теперь вы можете получить свою натальную карту.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📜 Получить натальную карту", callback_data='natal_chart'),
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
                InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile'),
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
                InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile'),
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
                InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile'),
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
                InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile'),
                InlineKeyboardButton("🏠 Главное меню", callback_data='back_menu'),
            ]])
        )


def generate_natal_chart_with_gpt(birth_data, api_key):
    """Генерация натальной карты с помощью OpenAI GPT"""
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Формируем промпт для GPT
        prompt = f"""Создай натальную карту на основе следующих данных:

Имя: {birth_data.get('name', 'Пользователь')}
Дата рождения: {birth_data.get('date', 'Не указано')}
Время рождения: {birth_data.get('time', 'Не указано')}
Место рождения: {birth_data.get('place', 'Не указано')}

Создай астрологическую натальную карту (максимум 1200-1500 слов), которая включает:
1. Положение основных планет (Солнце, Луна, Меркурий, Венера, Марс, Юпитер, Сатурн) в знаках зодиака
2. Асцендент и важные углы карты
3. Краткое описание личности на основе положений планет
4. Характерные черты и таланты
5. Области жизни, требующие внимания
6. Краткая астрологическая интерпретация основных аспектов

ВАЖНО: 
- Ответ должен быть ЛАКОНИЧНЫМ, структурированным и не превышать 1500 слов
- Используй простой Markdown: **жирный текст** для заголовков, *курсив* для акцентов
- ВСЕГДА закрывай все Markdown теги правильно (каждая * должна иметь пару, каждая _ должна иметь пару)
- Используй эмодзи для разделения разделов
- Пиши на русском языке
- Избегай сложных Markdown конструкций, используй только ** и *
"""
        
        logger.info("Отправка запроса в OpenAI GPT для генерации натальной карты")
        
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Ты профессиональный астролог с глубокими знаниями натальной астрологии. Создаешь детальные и точные натальные карты. Ответ должен быть лаконичным, но информативным (максимум 1200-1500 слов)."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        natal_chart_text = response.choices[0].message.content
        
        logger.info("Натальная карта успешно сгенерирована через OpenAI GPT")
        
        # Добавляем заголовок, если его нет
        if not natal_chart_text.startswith("📜"):
            natal_chart_text = "📜 *Натальная карта*\n\n" + natal_chart_text
        
        return natal_chart_text
        
    except Exception as e:
        logger.error(f"Ошибка при вызове OpenAI API: {e}")
        # Возвращаем базовую натальную карту при ошибке API
        return """📜 *Натальная карта*

*Астрологический профиль:*

На основе предоставленных данных создана персональная натальная карта.

*Важные элементы:*
• Солнце определяет вашу сущность
• Луна показывает вашу эмоциональную природу
• Асцендент - ваш образ в глазах окружающих

*Примечание:* Для более детального анализа рекомендуется консультация с профессиональным астрологом."""


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех текстовых сообщений"""
    if 'natal_chart_state' in context.user_data:
        await handle_natal_chart_input(update, context)
    else:
        await update.message.reply_text(
            "👋 Используйте кнопки меню для навигации или отправьте команду /help для справки."
        )


def main():
    """Запуск бота"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    # Инициализация базы данных при запуске
    init_db()
    main()
