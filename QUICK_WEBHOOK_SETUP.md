# Быстрая настройка Webhook YooKassa ⚡

## Минимальная инструкция (5 минут)

### 1. Определите ваш webhook URL

**Формат:** `https://ваш-домен.com/webhook/yookassa`

**Примеры:**
- Railway: `https://your-app.railway.app/webhook/yookassa`
- Render: `https://your-app.onrender.com/webhook/yookassa`
- VPS: `https://your-domain.com/webhook/yookassa`

### 2. Установите переменную окружения

**Railway:**
```
YOOKASSA_WEBHOOK_URL=https://your-app.railway.app/webhook/yookassa
```

**Render:**
```
YOOKASSA_WEBHOOK_URL=https://your-app.onrender.com/webhook/yookassa
```

**Локально (.env):**
```
YOOKASSA_WEBHOOK_URL=https://your-ngrok-url.ngrok.io/webhook/yookassa
```

### 3. Зарегистрируйте webhook в YooKassa

1. Войдите в https://yookassa.ru/
2. Перейдите: **Настройки** → **Уведомления**
3. Добавьте URL: `https://ваш-домен.com/webhook/yookassa`
4. Выберите события:
   - ✅ `payment.succeeded`
   - ✅ `payment.canceled`
5. Сохраните

### 4. Проверьте настройку

```bash
python check_webhook_setup.py
```

### 5. Перезапустите бота

После настройки перезапустите бота. В логах должно появиться:
```
🌐 Запуск webhook сервера на 0.0.0.0:8080
```

---

## Проверка работы

1. **Создайте тестовый платеж** через бота
2. **Проверьте логи** — должны появиться сообщения:
   ```
   🔔 Получен webhook от ЮKassa: event=payment.succeeded
   ✅ Платеж ... успешно обработан через webhook
   ```

---

## Важно ⚠️

- ✅ URL должен быть **HTTPS** (обязательно!)
- ✅ URL должен быть **доступен из интернета**
- ✅ URL должен **заканчиваться на** `/webhook/yookassa`

---

## Подробная инструкция

См. файл `YOOKASSA_WEBHOOK_SETUP.md` для детальной информации.






