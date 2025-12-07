# Исправление ошибки "Event loop is closed" при генерации после оплаты

## Проблема

При попытке автоматически запустить генерацию натальной карты после успешной оплаты возникала ошибка:
```
telegram.error.NetworkError: Unknown error in HTTP implementation: RuntimeError('Event loop is closed')
```

## Причина

Функция `handle_natal_chart_request_from_payment` вызывалась из `process_payment_async`, который работает в отдельном потоке с временным event loop. Когда функция пыталась использовать `context.bot` для отправки сообщений, этот bot был привязан к уже закрытому event loop.

## Решение

1. **Получение токена бота** вместо самого bot объекта:
   ```python
   bot_token = context.bot.token if hasattr(context, 'bot') else context.application.bot.token
   ```

2. **Создание нового Bot в каждом новом event loop**:
   ```python
   def send_message_in_thread():
       loop = asyncio.new_event_loop()
       asyncio.set_event_loop(loop)
       try:
           new_bot = Bot(token=bot_token)
           loop.run_until_complete(new_bot.send_message(...))
       finally:
           loop.close()
   ```

3. **Создание нового context для генерации** с правильным bot:
   ```python
   def run_generation():
       loop = asyncio.new_event_loop()
       asyncio.set_event_loop(loop)
       try:
           new_bot = Bot(token=bot_token)
           new_context = ApplicationContextWrapper(context.application, user_id)
           new_context.bot = new_bot
           loop.run_until_complete(generate_natal_chart_background(user_id, new_context))
       finally:
           loop.close()
   ```

## Изменения в коде

- Все вызовы `bot.send_message()` теперь выполняются в отдельных потоках с новыми event loops
- В каждом потоке создается новый `Bot` объект с тем же токеном
- Context для генерации создается с новым bot, привязанным к новому event loop

## Результат

Теперь генерация натальной карты после оплаты должна работать корректно:
1. ✅ Сообщения отправляются без ошибок
2. ✅ Генерация запускается в отдельном потоке
3. ✅ Нет конфликтов с event loops

