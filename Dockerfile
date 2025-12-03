# Используем официальный образ Python
FROM python:3.9-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    swig \
    libswisseph-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаем директории для логов
RUN mkdir -p logs && \
    chmod 755 logs

# Копируем шрифты (если они есть)
COPY fonts/ fonts/ 2>/dev/null || true
COPY images/ images/ 2>/dev/null || true

# Устанавливаем переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Открываем порт для webhook (если используется)
EXPOSE 8080

# Команда для запуска бота
CMD ["python3", "bot.py"]

