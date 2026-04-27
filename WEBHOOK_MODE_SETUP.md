# Настройка бота в режиме Webhook только 🌐

## Что изменилось

Бот теперь поддерживает два режима работы:
1. **Webhook режим** (рекомендуется для продакшена) - обновления приходят через webhook
2. **Polling режим** (fallback) - используется, если `TELEGRAM_WEBHOOK_URL` не установлен

## Преимущества Webhook режима

✅ **Нет конфликтов** - только один способ получения обновлений  
✅ **Быстрее** - обновления приходят мгновенно  
✅ **Надежнее** - не нужно постоянно опрашивать API  
✅ **Меньше нагрузки** - на сервер и на Telegram API

---

## Шаг 1: Установка переменных окружения

### Для Timeweb Cloud

1. Откройте панель контейнера
2. Перейдите в раздел **"Переменные окружения"**
3. Добавьте переменную:

   **Key:** `TELEGRAM_WEBHOOK_URL`  
   **Value:** `https://nikroshchin1894-astral-bot-e77d.twc1.net/webhook/telegram`

   ⚠️ **Важно:** Замените на ваш реальный домен!

### Для других платформ

Добавьте в `.env` или переменные окружения:

```env
TELEGRAM_WEBHOOK_URL=https://ваш-домен.com/webhook/telegram
WEBHOOK_PORT=8080
```

**Примеры:**
- Railway: `https://your-app.railway.app/webhook/telegram`
- Render: `https://your-app.onrender.com/webhook/telegram`
- VPS: `https://your-domain.com/webhook/telegram`

---

## Шаг 2: Настройка прокси в Timeweb Cloud

В Timeweb Cloud нужно настроить проксирование запросов:

1. Откройте панель контейнера
2. Найдите раздел **"Домены"** или **"Прокси"**
3. Настройте маршрутизацию:
   - Путь: `/webhook/telegram`
   - Прокси на: `localhost:8080` или `127.0.0.1:8080`
   - Путь: `/webhook/yookassa`
   - Прокси на: `localhost:8080` или `127.0.0.1:8080`

Или через Nginx (если используется):

```nginx
location /webhook/telegram {
    proxy_pass http://localhost:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /webhook/yookassa {
    proxy_pass http://localhost:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## Шаг 3: Запуск бота

После установки переменных окружения:

1. **Перезапустите контейнер/сервис**
2. **Проверьте логи** - должно появиться:
   ```
   🌐 Запуск бота в режиме WEBHOOK
   🌐 Запуск webhook сервера на 0.0.0.0:8080
      📱 Telegram webhook: /webhook/telegram
      💳 YooKassa webhook: /webhook/yookassa
   ✅ Webhook сервер запущен в отдельном потоке
   🔗 Установка webhook в Telegram (попытка 1/3)...
      URL: https://nikroshchin1894-astral-bot-e77d.twc1.net/webhook/telegram
   ✅ Webhook успешно установлен в Telegram
   ✅ Бот запущен в режиме WEBHOOK и готов к работе!
   ```

---

## Шаг 4: Установка webhook вручную (опционально)

Если webhook не установился автоматически, используйте скрипт:

```bash
python setup_telegram_webhook.py
```

Или через curl:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://nikroshchin1894-astral-bot-e77d.twc1.net/webhook/telegram",
    "drop_pending_updates": true
  }'
```

---

## Шаг 5: Проверка работы

### 1. Проверка статуса webhook

```bash
python check_bot_status.py
```

Должно показать:
```
✅ Webhook установлен: https://nikroshchin1894-astral-bot-e77d.twc1.net/webhook/telegram
```

### 2. Тест бота

1. Откройте бота в Telegram
2. Отправьте команду `/start`
3. Бот должен ответить

### 3. Проверка логов

В логах должны появляться сообщения:
```
🔔 Получен webhook от Telegram
✅ Обновление обработано
```

---

## Структура Webhook endpoints

Бот теперь использует единый Flask сервер для обоих webhook:

- **`/webhook/telegram`** - обновления от Telegram
- **`/webhook/yookassa`** - уведомления от YooKassa
- **`/health`** - health check endpoint

Все работают на одном порту (по умолчанию 8080).

---

## Переключение между режимами

### Включить Webhook режим:
```env
TELEGRAM_WEBHOOK_URL=https://ваш-домен.com/webhook/telegram
```

### Включить Polling режим:
```env
# Просто не устанавливайте TELEGRAM_WEBHOOK_URL
# или удалите переменную
```

---

## Решение проблем

### Проблема: Webhook не устанавливается

**Симптомы:**
- В логах: "❌ Ошибка при установке webhook"
- Бот не получает обновления

**Решение:**
1. Проверьте, что `TELEGRAM_WEBHOOK_URL` установлен
2. Проверьте доступность endpoint:
   ```bash
   curl -X POST https://ваш-домен.com/webhook/telegram
   ```
3. Убедитесь, что webhook сервер запущен (проверьте логи)
4. Установите webhook вручную: `python setup_telegram_webhook.py`

### Проблема: Бот не получает обновления

**Симптомы:**
- Webhook установлен, но бот не отвечает

**Решение:**
1. Проверьте логи - должны быть сообщения о получении обновлений
2. Проверьте настройки прокси в Timeweb Cloud
3. Убедитесь, что порт 8080 доступен
4. Проверьте статус webhook: `python check_bot_status.py`

### Проблема: 502 Bad Gateway

**Симптомы:**
- Endpoint возвращает 502

**Решение:**
1. Проверьте, что бот запущен
2. Проверьте, что webhook сервер запустился (логи)
3. Проверьте настройки прокси
4. Убедитесь, что порт 8080 правильный

---

## Быстрая проверка

```bash
# 1. Проверка переменных
echo $TELEGRAM_WEBHOOK_URL

# 2. Проверка статуса webhook
python check_bot_status.py

# 3. Установка webhook (если нужно)
python setup_telegram_webhook.py

# 4. Проверка доступности
curl -X POST https://ваш-домен.com/webhook/telegram
```

---

## Готово! ✅

После настройки бот будет работать только через webhook, без конфликтов и ошибок 409!

**Преимущества:**
- ✅ Нет конфликтов между экземплярами
- ✅ Мгновенные обновления
- ✅ Меньше нагрузки на сервер
- ✅ Работает вместе с webhook YooKassa






