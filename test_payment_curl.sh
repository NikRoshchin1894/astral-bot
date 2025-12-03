#!/bin/bash

# Тест создания платежа через curl с авторизацией

# Загружаем переменные из .env
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

SHOP_ID="${YOOKASSA_SHOP_ID}"
SECRET_KEY="${YOOKASSA_SECRET_KEY}"
BOT_USERNAME="${TELEGRAM_BOT_USERNAME:-Astralogy_bot}"

if [ -z "$SHOP_ID" ] || [ -z "$SECRET_KEY" ]; then
  echo "❌ Ошибка: YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены"
  exit 1
fi

RETURN_URL="https://t.me/${BOT_USERNAME}?start=payment_cancel"
IDEMPOTENCE_KEY="test-curl-$(date +%s)"

echo "🔍 Тест создания платежа через curl"
echo "   Shop ID: ${SHOP_ID}"
echo "   Return URL: ${RETURN_URL}"
echo "   Idempotence Key: ${IDEMPOTENCE_KEY}"
echo ""

curl -v -X POST https://api.yookassa.ru/v3/payments \
  -u "${SHOP_ID}:${SECRET_KEY}" \
  -H "Idempotence-Key: ${IDEMPOTENCE_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": {
      "value": "499.00",
      "currency": "RUB"
    },
    "confirmation": {
      "type": "redirect",
      "return_url": "'"${RETURN_URL}"'"
    },
    "capture": true,
    "description": "Натальная карта - детальный астрологический разбор",
    "metadata": {
      "user_id": "123456789",
      "payment_type": "natal_chart"
    }
  }' \
  --max-time 30

echo ""
echo ""

