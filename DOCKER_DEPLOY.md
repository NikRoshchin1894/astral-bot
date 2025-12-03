# Развертывание бота через Docker 🐳

Инструкция по развертыванию Astral Bot с использованием Docker.

## 📋 Требования

- Docker установлен на сервере
- Docker Compose (опционально, для удобства)
- Файл `.env` с переменными окружения

## 🚀 Быстрый старт

### Вариант 1: Использование Docker напрямую

1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/NikRoshchin1894/astral-bot.git
   cd astral-bot
   ```

2. **Создайте файл `.env`:**
   ```bash
   cp env.example .env
   nano .env
   ```
   
   Заполните все необходимые переменные.

3. **Создайте директории для данных:**
   ```bash
   mkdir -p data logs
   ```

4. **Соберите Docker образ:**
   ```bash
   docker build -t astral-bot .
   ```

5. **Запустите контейнер:**
   ```bash
   docker run -d \
     --name astral-bot \
     --restart unless-stopped \
     --env-file .env \
     -v $(pwd)/data:/app/data \
     -v $(pwd)/logs:/app/logs \
     -p 8080:8080 \
     astral-bot
   ```

6. **Проверьте логи:**
   ```bash
   docker logs -f astral-bot
   ```

### Вариант 2: Использование Docker Compose (рекомендуется)

1. **Клонируйте репозиторий и перейдите в директорию:**
   ```bash
   git clone https://github.com/NikRoshchin1894/astral-bot.git
   cd astral-bot
   ```

2. **Создайте файл `.env`:**
   ```bash
   cp env.example .env
   nano .env
   ```
   
   Заполните все необходимые переменные.

3. **Создайте директории:**
   ```bash
   mkdir -p data logs
   ```

4. **Запустите контейнер:**
   ```bash
   docker-compose up -d
   ```

5. **Проверьте логи:**
   ```bash
   docker-compose logs -f
   ```

## 🔧 Управление контейнером

### Основные команды:

```bash
# Запуск
docker-compose start

# Остановка
docker-compose stop

# Перезапуск
docker-compose restart

# Остановка и удаление контейнера
docker-compose down

# Пересборка и запуск
docker-compose up -d --build

# Просмотр логов
docker-compose logs -f

# Просмотр статуса
docker-compose ps
```

### Для Docker (без Compose):

```bash
# Запуск
docker start astral-bot

# Остановка
docker stop astral-bot

# Перезапуск
docker restart astral-bot

# Просмотр логов
docker logs -f astral-bot

# Удаление контейнера
docker rm -f astral-bot

# Пересборка образа
docker build -t astral-bot .
```

## 🔄 Обновление бота

1. **Остановите контейнер:**
   ```bash
   docker-compose stop
   # или
   docker stop astral-bot
   ```

2. **Получите последние изменения:**
   ```bash
   git pull
   ```

3. **Пересоберите образ:**
   ```bash
   docker-compose build
   # или
   docker build -t astral-bot .
   ```

4. **Запустите контейнер:**
   ```bash
   docker-compose up -d
   # или
   docker run -d --name astral-bot --restart unless-stopped --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs -p 8080:8080 astral-bot
   ```

## 🗄️ Настройка базы данных

### SQLite (по умолчанию)

SQLite будет работать автоматически, данные сохраняются в `/app/data/users.db` (монтируется из `./data/users.db`).

### PostgreSQL

Если используете PostgreSQL на другом сервере/контейнере:

1. Добавьте в `.env`:
   ```env
   DATABASE_PUBLIC_URL=postgresql://user:password@host:port/database
   ```

2. Или добавьте PostgreSQL сервис в `docker-compose.yml`:
   ```yaml
   services:
     postgres:
       image: postgres:15
       environment:
         POSTGRES_USER: astralbot
         POSTGRES_PASSWORD: your_password
         POSTGRES_DB: astral_bot
       volumes:
         - postgres_data:/var/lib/postgresql/data
   
     astral-bot:
       # ... существующая конфигурация
       depends_on:
         - postgres
       environment:
         - DATABASE_PUBLIC_URL=postgresql://astralbot:your_password@postgres:5432/astral_bot
   
   volumes:
     postgres_data:
   ```

## 🌐 Настройка webhook для ЮKassa

Если используете домен:

1. **Настройте Nginx** (на хосте, не в контейнере):
   ```nginx
   server {
       listen 80;
       server_name ваш_домен.ru;
   
       location /webhook/yookassa {
           proxy_pass http://localhost:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

2. **Добавьте в `.env`:**
   ```env
   YOOKASSA_WEBHOOK_URL=https://ваш_домен.ru/webhook/yookassa
   WEBHOOK_PORT=8080
   ```

3. **Перезапустите контейнер:**
   ```bash
   docker-compose restart
   ```

## 📊 Мониторинг

### Просмотр использования ресурсов:

```bash
# Статистика контейнера
docker stats astral-bot

# Или через docker-compose
docker-compose top
```

### Логи:

```bash
# Все логи
docker-compose logs

# Последние 100 строк
docker-compose logs --tail=100

# Следить в реальном времени
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs astral-bot
```

## 🐛 Решение проблем

### Контейнер не запускается

1. **Проверьте логи:**
   ```bash
   docker logs astral-bot
   ```

2. **Проверьте переменные окружения:**
   ```bash
   docker exec astral-bot env | grep TELEGRAM_BOT_TOKEN
   ```

3. **Проверьте, что файл `.env` существует и правильно заполнен**

### Ошибки с базой данных

1. **Проверьте права доступа к директории data:**
   ```bash
   chmod 755 data
   chmod 644 data/*.db 2>/dev/null || true
   ```

2. **Для PostgreSQL - проверьте подключение:**
   ```bash
   docker exec astral-bot python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('DATABASE_PUBLIC_URL'))"
   ```

### Контейнер падает

1. **Проверьте логи:**
   ```bash
   docker logs astral-bot --tail=100
   ```

2. **Проверьте использование памяти:**
   ```bash
   docker stats astral-bot
   ```

3. **Увеличьте лимиты памяти в `docker-compose.yml`** (если нужно)

## 🔒 Безопасность

1. **Не коммитьте `.env` файл в Git** (он уже в `.dockerignore`)

2. **Используйте секреты Docker** для продакшена:
   ```bash
   docker secret create telegram_token your_token
   ```

3. **Ограничьте доступ к портам** - используйте firewall:
   ```bash
   ufw allow 8080/tcp  # Только для webhook
   ```

## 📝 Примечания

- Данные базы данных хранятся в `./data` и монтируются в контейнер
- Логи сохраняются в `./logs` и доступны с хоста
- Контейнер автоматически перезапускается при падении (`restart: unless-stopped`)
- Образ основан на `python:3.9-slim` для меньшего размера

---

**Готово!** Ваш бот запущен в Docker контейнере! 🎉

