# Используем официальный образ Python
FROM python:3.9-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
# Очищаем кэш перед обновлением для стабильности
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    swig \
    curl \
    && rm -rf /var/lib/apt/lists/*
    
# curl уже установлен выше, используется для HEALTHCHECK

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

# Создаем директории для шрифтов и изображений (если их нет)
RUN mkdir -p fonts images || true

# Устанавливаем переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Открываем порт для webhook (если используется)
EXPOSE 8080

# Health check для проверки работоспособности приложения
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Команда для запуска бота
CMD ["python3", "bot.py"]

