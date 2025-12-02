# Настройка оплаты через ЮKassa

## Где добавить переменные окружения

### Вариант 1: Локально (для тестирования)

1. Создайте файл `.env` в корне проекта (если его еще нет):
   ```bash
   cd /Users/nsroschin/Documents/Astral_Bot
   nano .env
   ```

2. Добавьте следующие строки (замените на ваши реальные значения):
   ```
   YOOKASSA_SHOP_ID=ваш_shop_id_здесь
   YOOKASSA_SECRET_KEY=ваш_secret_key_здесь
   PAYMENT_SUCCESS_URL=https://t.me/ваш_бот?start=payment_success
   PAYMENT_RETURN_URL=https://t.me/ваш_бот?start=payment_cancel
   ```

3. **Важно:** Файл `.env` должен быть в `.gitignore`, чтобы не попасть в репозиторий!

### Вариант 2: Railway.app ⭐ (Рекомендуется)

1. Откройте ваш проект на https://railway.app
2. Перейдите в раздел **"Variables"** (Переменные окружения)
3. Нажмите **"+ New Variable"** и добавьте каждую переменную:

   - **Key:** `YOOKASSA_SHOP_ID`
     **Value:** ваш Shop ID из ЮKassa

   - **Key:** `YOOKASSA_SECRET_KEY`
     **Value:** ваш Secret Key из ЮKassa

   - **Key:** `PAYMENT_SUCCESS_URL`
     **Value:** `https://t.me/ваш_бот?start=payment_success`
     (замените `ваш_бот` на username вашего бота без @)

   - **Key:** `PAYMENT_RETURN_URL`
     **Value:** `https://t.me/ваш_бот?start=payment_cancel`

4. После добавления Railway автоматически перезапустит бота

### Вариант 3: Render.com

1. Откройте ваш проект на https://render.com
2. Перейдите в раздел **"Environment"**
3. В секции **"Environment Variables"** нажмите **"Add Environment Variable"**
4. Добавьте переменные (как в Railway выше)

### Вариант 4: Другие платформы (Heroku, PythonAnywhere и т.д.)

Добавьте переменные окружения через:
- Heroku: `heroku config:set YOOKASSA_SHOP_ID=значение`
- PythonAnywhere: через веб-интерфейс в разделе "Web App" → "Environment variables"

## Как получить YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY

1. Зарегистрируйтесь в [ЮKassa](https://yookassa.ru/)
2. Создайте магазин (если еще нет)
3. В личном кабинете перейдите в **"Настройки"** → **"API ключи"**
4. Скопируйте:
   - **Shop ID** (например: `123456`)
   - **Secret Key** (например: `live_xxxxxxxxxxxxxxxxxxxxx`)

   ⚠️ **Важно:**
   - Для тестирования используйте тестовые ключи (начинаются с `test_`)
   - Для продакшена используйте боевые ключи (начинаются с `live_`)

## Проверка настройки

После добавления переменных:
1. Перезапустите бота
2. Проверьте логи - не должно быть ошибок о отсутствующих переменных
3. Попробуйте создать ссылку на оплату - должна появиться кнопка "Перейти к оплате"

## Безопасность

⚠️ **НИКОГДА не добавляйте `.env` файл в git!**
- Проверьте, что `.env` в `.gitignore`
- Secret Key - это секретная информация, не делитесь ей публично

