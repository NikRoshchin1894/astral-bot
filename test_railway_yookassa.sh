#!/bin/bash
# Скрипт для тестирования подключения Railway → ЮKassa API
# Использование: ./test_railway_yookassa.sh

echo "🔍 Проверка подключения Railway → ЮKassa API"
echo ""

# Проверяем, что переменные окружения установлены
if [ -z "$YOOKASSA_SHOP_ID" ] || [ -z "$YOOKASSA_SECRET_KEY" ]; then
    echo "❌ Ошибка: YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены"
    echo "Установите переменные окружения или укажите их явно:"
    echo "export YOOKASSA_SHOP_ID=ваш_shop_id"
    echo "export YOOKASSA_SECRET_KEY=ваш_secret_key"
    exit 1
fi

SHOP_ID="$YOOKASSA_SHOP_ID"
SECRET_KEY="$YOOKASSA_SECRET_KEY"

echo "🔑 Shop ID: $SHOP_ID"
echo "🔑 Secret Key: ${SECRET_KEY:0:4}****${SECRET_KEY: -4}"
echo ""
echo "📤 Отправка запроса к ЮKassa API..."
echo ""

# Правильный формат curl команды для создания платежа
curl -v https://api.yookassa.ru/v3/payments \
  -u "${SHOP_ID}:${SECRET_KEY}" \
  -H "Idempotence-Key: test-railway-$(date +%s)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": {
      "value": "100.00",
      "currency": "RUB"
    },
    "confirmation": {
      "type": "redirect",
      "return_url": "https://t.me/test_bot?start=test"
    },
    "capture": true,
    "description": "Тестовый платеж для проверки подключения Railway"
  }' \
  --max-time 30

echo ""
echo ""
echo "✅ Если вы видите ответ 401/400/200 - сеть работает нормально"
echo "❌ Если запрос висит/таймаутится - проблема с сетью Railway → ЮKassa"

