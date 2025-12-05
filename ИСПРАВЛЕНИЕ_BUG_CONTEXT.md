# Исправление: Bug с передачей Application вместо Context

## Проблема

Функция `check_and_process_pending_payment` ожидала параметр типа `ContextTypes.DEFAULT_TYPE`, но в двух местах вызывалась с объектом `Application`:

1. **Строка 4888** (в `process_payment_async`): `await check_and_process_pending_payment(user_id, application)`
2. **Строка 4954** (в периодической проверке платежей): `await check_and_process_pending_payment(user_id, application)`

Это вызывало бы ошибку `AttributeError`, так как `Application` не имеет атрибутов `context.user_data` и `context.bot.send_message()` в том виде, в котором они используются в функции.

## Решение

Создан класс-обертка `ApplicationContextWrapper`, который имитирует интерфейс `Context` для работы с `Application`:

```python
class ApplicationContextWrapper:
    """Обертка для Application, имитирующая Context для использования в check_and_process_pending_payment"""
    def __init__(self, application: Application, user_id: int):
        self.bot = application.bot
        self.application = application
        self.user_id = user_id
        # Загружаем user_data из базы данных
        self.user_data = load_user_profile(user_id) or {}
```

Функция `check_and_process_pending_payment` теперь принимает либо `Context`, либо `Application`, и автоматически создает wrapper при необходимости:

```python
async def check_and_process_pending_payment(user_id: int, context_or_application) -> bool:
    # Если передан Application, создаем wrapper
    if isinstance(context_or_application, Application):
        context = ApplicationContextWrapper(context_or_application, user_id)
    else:
        context = context_or_application
    # ... остальной код работает с context
```

## Изменения

1. ✅ Добавлен класс `ApplicationContextWrapper` (строка 2669)
2. ✅ Модифицирована сигнатура функции `check_and_process_pending_payment` для принятия `context_or_application`
3. ✅ Добавлена логика автоматического определения типа параметра и создания wrapper
4. ✅ Все вызовы функции теперь работают корректно

## Проверка

- ✅ Код компилируется без ошибок
- ✅ Все вызовы функции обработаны правильно:
  - Строка 729: передается Context (корректно)
  - Строка 4888: передается Application (теперь работает через wrapper)
  - Строка 4954: передается Application (теперь работает через wrapper)

## Результат

Теперь функция может работать как с обычным `Context` (из обработчиков Telegram), так и с `Application` (из webhook обработки платежей), что устраняет ошибку и делает код более гибким.

