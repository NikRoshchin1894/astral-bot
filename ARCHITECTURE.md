# Архитектура Astral Bot

## НОВАЯ УПРОЩЕННАЯ АРХИТЕКТУРА (после рефакторинга)

### Принцип: Один event loop, один HTTP-вход

```
┌─────────────────────────────────────────────────────────────────┐
│                         TELEGRAM API                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Webhook (POST /webhook/telegram)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              AIOHTTP WEBHOOK SERVER                              │
│              (Один event loop, один поток)                        │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /webhook/telegram                                        │  │
│  │  - Получает Update от Telegram                           │  │
│  │  - Вызывает application.process_update(update)            │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /webhook/yookassa                                        │  │
│  │  - Получает уведомления о платежах                       │  │
│  │  - Обрабатывает асинхронно                               │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ process_update(update)
                             │ (в том же event loop)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              TELEGRAM APPLICATION                                │
│              (Тот же event loop)                                  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Обработчики (Handlers):                                  │  │
│  │  - CommandHandler("start", start)                        │  │
│  │  - CommandHandler("help", help_command)                 │  │
│  │  - CommandHandler("about", about_command)               │  │
│  │  - CallbackQueryHandler(button_handler) ✅ КНОПКИ       │  │
│  │  - MessageHandler(filters.TEXT, handle_message)         │  │
│  │  - PreCheckoutQueryHandler(precheckout_callback)        │  │
│  │  - MessageHandler(filters.SUCCESSFUL_PAYMENT, ...)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  button_handler(update, context)                         │  │
│  │  - Обрабатывает callback_query                          │  │
│  │  - Вызывает соответствующие функции                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Сохранение/загрузка данных
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL/SQLite)                  │
└─────────────────────────────────────────────────────────────────┘
```

### Преимущества новой архитектуры:
- ✅ **Один event loop** - нет конфликтов между потоками
- ✅ **Один HTTP-вход** - все webhook'и обрабатываются в одном месте
- ✅ **Простота** - нет сложной синхронизации между потоками
- ✅ **Надежность** - кнопки работают стабильно

---

## Старая архитектура (до рефакторинга)

## Общая схема

```
┌─────────────────────────────────────────────────────────────────┐
│                         TELEGRAM API                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Webhook (POST /webhook/telegram)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FLASK WEBHOOK SERVER                          │
│                    (Thread: webhook_thread)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  /webhook/telegram                                        │   │
│  │  - Получает Update от Telegram                           │   │
│  │  - Создает объект Update.de_json()                       │   │
│  │  - Ожидает готовности Application (application_ready_event)│   │
│  │  - Вызывает application.process_update(update)            │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  /webhook/yookassa                                        │   │
│  │  - Получает уведомления о платежах                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ process_update(update)
                             │ (через asyncio.run_coroutine_threadsafe)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              TELEGRAM APPLICATION                               │
│              (Thread: app_thread)                               │
│              Event Loop: application_event_loop                  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Обработчики (Handlers):                                  │  │
│  │  - CommandHandler("start", start)                        │  │
│  │  - CommandHandler("help", help_command)                 │  │
│  │  - CommandHandler("about", about_command)               │  │
│  │  - CallbackQueryHandler(button_handler) ⚠️ КНОПКИ       │  │
│  │  - MessageHandler(filters.TEXT, handle_message)          │  │
│  │  - PreCheckoutQueryHandler(precheckout_callback)        │  │
│  │  - MessageHandler(filters.SUCCESSFUL_PAYMENT, ...)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  button_handler(update, context)                         │  │
│  │  - Обрабатывает callback_query                          │  │
│  │  - Вызывает соответствующие функции:                    │  │
│  │    * my_profile()                                       │  │
│  │    * select_edit_field()                                │  │
│  │    * start_edit_field()                                 │  │
│  │    * handle_natal_chart_request()                       │  │
│  │    * back_to_menu()                                     │  │
│  │    * и т.д.                                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Сохранение/загрузка данных
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL/SQLite)                  │
│  - users (профили пользователей)                                │
│  - events (аналитика событий)                                   │
│  - payments (платежи ЮKassa)                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Потоки (Threads)

### 1. **Основной поток (Main Thread)**
- Запускает все остальные потоки
- Регистрирует обработчики сигналов (SIGTERM, SIGINT)
- Держит процесс живым (while not shutdown_event)

### 2. **Webhook Thread (webhook_thread)**
- Запускает Flask сервер (Werkzeug)
- Обрабатывает HTTP запросы от Telegram и ЮKassa
- **НЕ обрабатывает обновления напрямую** - только передает их в Application

### 3. **Application Thread (app_thread)**
- Запускает Telegram Application
- Создает свой собственный event loop (`application_event_loop`)
- Инициализирует Application (`await application.initialize()`)
- Устанавливает webhook в Telegram
- Запускает Application (`await application.start()`)
- Сохраняет event loop в глобальную переменную `application_event_loop`
- Ждет сигнала остановки (`shutdown_event`)

## Обработка обновлений (Updates)

### Поток обработки callback query (кнопки):

```
1. Telegram → POST /webhook/telegram
   └─> Update с callback_query

2. Flask webhook handler (telegram_webhook)
   └─> Update.de_json(update_data, bot)
   └─> Ожидает application_ready_event (макс 3 сек)
   └─> Получает application_event_loop

3. Обработка через Application:
   ├─> Если event loop доступен:
   │   └─> asyncio.run_coroutine_threadsafe(
   │       application.process_update(update),
   │       application_event_loop
   │   )
   │   └─> Ждет результат (timeout 30 сек)
   │
   └─> Если event loop недоступен:
       └─> Создает новый поток с новым event loop
       └─> loop.run_until_complete(
           application.process_update(update)
       )

4. Application.process_update(update)
   └─> Находит подходящий Handler
   └─> Для callback_query → CallbackQueryHandler
   └─> Вызывает button_handler(update, context)

5. button_handler(update, context)
   └─> query.answer() - отвечает на callback
   └─> Определяет callback_data
   └─> Вызывает соответствующую функцию:
       ├─> my_profile() - показать профиль
       ├─> select_edit_field() - выбор поля для редактирования
       ├─> start_edit_field() - начало редактирования
       ├─> handle_natal_chart_request() - запрос натальной карты
       └─> и т.д.
```

## Глобальные переменные

```python
telegram_application = None          # Экземпляр Application
application_event_loop = None        # Event loop Application (для обработки обновлений)
application_ready_event = threading.Event()  # Сигнал готовности Application
shutdown_event = threading.Event()   # Сигнал остановки
flask_app = None                     # Flask приложение
webhook_thread = None                # Поток Flask сервера
app_thread = None                    # Поток Application
werkzeug_server = None               # Werkzeug сервер
```

## Проблемные места

### ⚠️ Потенциальные проблемы:

1. **Event Loop недоступен**
   - Если `application_event_loop` не сохранился или недоступен
   - Создается новый event loop для каждого обновления
   - Это может вызывать проблемы с обработкой

2. **Обработка в разных потоках**
   - Flask webhook работает в одном потоке
   - Application работает в другом потоке
   - Обновления передаются через `asyncio.run_coroutine_threadsafe`
   - Если event loop недоступен, создается третий поток

3. **Задержка готовности Application**
   - Webhook может получить обновление до того, как Application готов
   - Есть таймаут 3 секунды на ожидание
   - Если Application не готов, обновление обрабатывается без ожидания

4. **Обработка ошибок**
   - Если `process_update()` падает, ошибка логируется
   - Но webhook все равно возвращает 200 OK
   - Пользователь не получает ответ

## Рекомендации по исправлению

1. **Убедиться, что event loop сохраняется**
   - Проверить, что `application_event_loop` устанавливается после `application.start()`
   - Добавить проверку доступности event loop перед обработкой

2. **Улучшить обработку ошибок**
   - Если `process_update()` падает, отправлять пользователю сообщение об ошибке
   - Логировать все ошибки с полным traceback

3. **Упростить архитектуру**
   - Рассмотреть использование одного event loop для всего
   - Или использовать очередь обновлений вместо прямых вызовов

4. **Добавить мониторинг**
   - Логировать все callback queries
   - Отслеживать время обработки
   - Мониторить доступность event loop

