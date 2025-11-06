#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mini App Server для Telegram Bot
Сервер для отображения формы профиля пользователя
"""

from flask import Flask, render_template_string, request, jsonify
import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-in-production')

# Путь к базе данных
DATABASE = 'users.db'


def get_db():
    """Получить соединение с базой данных"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация базы данных"""
    conn = get_db()
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
    logger.info("База данных инициализирована")


# Инициализация базы данных при запуске
init_db()


# HTML шаблон для Mini App
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Мои данные</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            padding: 0;
        }
        
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
        }
        
        .header {
            padding: 16px;
            background: white;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .title {
            font-size: 28px;
            font-weight: bold;
            color: #212121;
            margin-bottom: 4px;
        }
        
        .subtitle {
            font-size: 14px;
            color: #757575;
        }
        
        .form-container {
            padding: 16px;
        }
        
        .form-group {
            margin-bottom: 16px;
        }
        
        .form-label {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            font-size: 14px;
            font-weight: 500;
            color: #424242;
        }
        
        .form-label .icon {
            width: 20px;
            height: 20px;
            margin-right: 8px;
            opacity: 0.6;
        }
        
        .form-input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            background: #fafafa;
            transition: all 0.2s;
        }
        
        .form-input:focus {
            outline: none;
            border-color: #9c27b0;
            background: white;
        }
        
        .date-row {
            display: flex;
            gap: 8px;
        }
        
        .date-row .date-input {
            flex: 1;
        }
        
        .zodiac-display {
            flex: 1;
            padding: 12px 16px;
            background: #f3e5f5;
            border: 1px solid #ce93d8;
            border-radius: 8px;
            display: flex;
            align-items: center;
            font-size: 14px;
        }
        
        .save-button {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 24px;
            transition: transform 0.2s;
        }
        
        .save-button:active {
            transform: scale(0.98);
        }
        
        .message {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            display: none;
        }
        
        .message.success {
            background: #e8f5e9;
            color: #2e7d32;
            border: 1px solid #81c784;
        }
        
        .message.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef5350;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">Мои данные</div>
            <div class="subtitle">Укажите данные о себе для точных прогнозов</div>
        </div>
        
        <div class="form-container">
            <div id="message" class="message"></div>
            
            <form id="profileForm">
                <div class="form-group">
                    <label class="form-label">
                        <span class="icon">👤</span>
                        Имя *
                    </label>
                    <input type="text" class="form-input" id="first_name" name="first_name" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">
                        <span class="icon">👤</span>
                        Фамилия
                    </label>
                    <input type="text" class="form-input" id="last_name" name="last_name">
                </div>
                
                <div class="form-group">
                    <label class="form-label">
                        <span class="icon">🌍</span>
                        Страна *
                    </label>
                    <input type="text" class="form-input" id="country" name="country" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">
                        <span class="icon">📍</span>
                        Город *
                    </label>
                    <input type="text" class="form-input" id="city" name="city" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">
                        <span class="icon">📅</span>
                        Дата рождения *
                    </label>
                    <div class="date-row">
                        <input type="date" class="form-input date-input" id="birth_date" name="birth_date" required>
                        <div class="zodiac-display" id="zodiac_sign">
                            <span>Знак зодиака</span>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label class="form-label">
                        <span class="icon">🕐</span>
                        Время рождения
                    </label>
                    <input type="time" class="form-input" id="birth_time" name="birth_time">
                </div>
                
                <button type="submit" class="save-button">Сохранить</button>
            </form>
        </div>
    </div>
    
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        
        // Получаем данные пользователя
        const userData = new URLSearchParams(window.location.search).get('data');
        if (userData) {
            try {
                const data = JSON.parse(decodeURIComponent(userData));
                document.getElementById('first_name').value = data.first_name || '';
                document.getElementById('last_name').value = data.last_name || '';
                document.getElementById('country').value = data.country || '';
                document.getElementById('city').value = data.city || '';
                document.getElementById('birth_date').value = data.birth_date || '';
                document.getElementById('birth_time').value = data.birth_time || '';
                
                if (data.birth_date) {
                    updateZodiac(data.birth_date);
                }
            } catch (e) {
                console.error('Error parsing user data:', e);
            }
        }
        
        // Обновление знака зодиака при изменении даты
        document.getElementById('birth_date').addEventListener('change', function() {
            updateZodiac(this.value);
        });
        
        function updateZodiac(dateString) {
            if (!dateString) return;
            
            const date = new Date(dateString);
            const month = date.getMonth() + 1;
            const day = date.getDate();
            
            const zodiacSigns = [
                {name: 'Козерог', emoji: '♑', start: [12, 22], end: [1, 19]},
                {name: 'Водолей', emoji: '♒', start: [1, 20], end: [2, 18]},
                {name: 'Рыбы', emoji: '♓', start: [2, 19], end: [3, 20]},
                {name: 'Овен', emoji: '♈', start: [3, 21], end: [4, 19]},
                {name: 'Телец', emoji: '♉', start: [4, 20], end: [5, 20]},
                {name: 'Близнецы', emoji: '♊', start: [5, 21], end: [6, 20]},
                {name: 'Рак', emoji: '♋', start: [6, 21], end: [7, 22]},
                {name: 'Лев', emoji: '♌', start: [7, 23], end: [8, 22]},
                {name: 'Дева', emoji: '♍', start: [8, 23], end: [9, 22]},
                {name: 'Весы', emoji: '♎', start: [9, 23], end: [10, 22]},
                {name: 'Скорпион', emoji: '♏', start: [10, 23], end: [11, 21]},
                {name: 'Стрелец', emoji: '♐', start: [11, 22], end: [12, 21]}
            ];
            
            for (const sign of zodiacSigns) {
                if ((month === sign.start[0] && day >= sign.start[1]) || 
                    (month === sign.end[0] && day <= sign.end[1]) ||
                    (sign.start[0] > sign.end[0] && (month === sign.start[0] || month === sign.end[0]))) {
                    document.getElementById('zodiac_sign').innerHTML = `${sign.emoji} ${sign.name}`;
                    return;
                }
            }
        }
        
        // Обработка отправки формы
        document.getElementById('profileForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = {
                first_name: document.getElementById('first_name').value,
                last_name: document.getElementById('last_name').value,
                country: document.getElementById('country').value,
                city: document.getElementById('city').value,
                birth_date: document.getElementById('birth_date').value,
                birth_time: document.getElementById('birth_time').value
            };
            
            try {
                const response = await fetch('/api/save_profile', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formData)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showMessage('Данные успешно сохранены!', 'success');
                    setTimeout(() => {
                        tg.close();
                    }, 1500);
                } else {
                    showMessage('Ошибка при сохранении данных', 'error');
                }
            } catch (error) {
                console.error('Error:', error);
                showMessage('Ошибка при сохранении данных', 'error');
            }
        });
        
        function showMessage(text, type) {
            const messageDiv = document.getElementById('message');
            messageDiv.textContent = text;
            messageDiv.className = 'message ' + type;
            messageDiv.style.display = 'block';
            
            setTimeout(() => {
                messageDiv.style.display = 'none';
            }, 3000);
        }
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """Главная страница Mini App"""
    # Получаем user_id из параметров Telegram
    user_id = request.args.get('user_id')
    
    if user_id:
        # Загружаем данные пользователя из базы
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        ).fetchone()
        conn.close()
        
        # Формируем данные для передачи в HTML
        user_data = {}
        if user:
            user_data = {
                'first_name': user['first_name'] or '',
                'last_name': user['last_name'] or '',
                'country': user['country'] or '',
                'city': user['city'] or '',
                'birth_date': user['birth_date'] or '',
                'birth_time': user['birth_time'] or ''
            }
        
        # Вставляем данные в HTML
        import json
        data_attr = f'?data={json.dumps(user_data)}' if user_data else ''
        html = HTML_TEMPLATE.replace(
            'window.location.search',
            f'"{data_attr}"'
        )
        return html
    else:
        return HTML_TEMPLATE


@app.route('/api/save_profile', methods=['POST'])
def save_profile():
    """API для сохранения профиля пользователя"""
    try:
        data = request.json
        user_id = request.args.get('user_id') or 0
        
        conn = get_db()
        conn.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, first_name, last_name, country, city, birth_date, birth_time, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            data.get('first_name'),
            data.get('last_name'),
            data.get('country'),
            data.get('city'),
            data.get('birth_date'),
            data.get('birth_time'),
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error saving profile: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_profile/<user_id>', methods=['GET'])
def get_profile(user_id):
    """API для получения профиля пользователя"""
    try:
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        ).fetchone()
        conn.close()
        
        if user:
            return jsonify({
                'success': True,
                'data': {
                    'first_name': user['first_name'],
                    'last_name': user['last_name'],
                    'country': user['country'],
                    'city': user['city'],
                    'birth_date': user['birth_date'],
                    'birth_time': user['birth_time']
                }
            })
        else:
            return jsonify({'success': False, 'message': 'Profile not found'})
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)



