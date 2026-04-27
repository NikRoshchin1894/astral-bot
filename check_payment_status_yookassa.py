#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки реального статуса платежей через API YooKassa
"""

import os
import sys
import requests
import base64
import json
from dotenv import load_dotenv

load_dotenv()

def check_payment_status(yookassa_payment_id):
    """Проверяет статус платежа через API YooKassa"""
    shop_id = os.getenv('YOOKASSA_SHOP_ID')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY')
    
    if not shop_id or not secret_key:
        print("❌ YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены")
        return None
    
    # Авторизация через Basic Auth
    auth_string = f"{shop_id}:{secret_key}"
    auth_bytes = auth_string.encode('ascii')
    auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"https://api.yookassa.ru/v3/payments/{yookassa_payment_id}",
            headers=headers,
            timeout=(10, 60)
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Ошибка API: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Ошибка при запросе: {e}")
        return None


def format_cancellation_details(cancellation_details):
    """Форматирует информацию об отмене"""
    if not cancellation_details:
        return "Нет данных"
    
    reason = cancellation_details.get('reason', 'unknown')
    party = cancellation_details.get('party', 'unknown')
    
    reason_messages = {
        '3d_secure_failed': 'Ошибка 3D Secure аутентификации',
        'call_issuer': 'Банк отклонил платеж',
        'canceled_by_merchant': 'Платеж отменен магазином',
        'expired_on_confirmation': 'Время на оплату истекло',
        'expired_on_capture': 'Время на подтверждение платежа истекло',
        'fraud_suspected': 'Подозрение в мошенничестве',
        'insufficient_funds': 'Недостаточно средств на карте',
        'invalid_csc': 'Неверный CVV/CVC код',
        'invalid_card_number': 'Неверный номер карты',
        'invalid_cardholder_name': 'Неверное имя держателя карты',
        'issuer_unavailable': 'Банк-эмитент недоступен',
        'payment_method_limit_exceeded': 'Превышен лимит по способу оплаты',
        'payment_method_restricted': 'Способ оплаты недоступен',
        'permission_revoked': 'Разрешение на платеж отозвано',
        'unsupported_mobile_operator': 'Мобильный оператор не поддерживается'
    }
    
    reason_text = reason_messages.get(reason, reason)
    
    return {
        'reason': reason_text,
        'reason_code': reason,
        'party': party
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python check_payment_status_yookassa.py <yookassa_payment_id>")
        print("\nПример:")
        print("  python check_payment_status_yookassa.py 30c3d6d8-000f-5000-8000-1316cc5dc8e1")
        sys.exit(1)
    
    payment_id = sys.argv[1]
    print(f"🔍 Проверка статуса платежа: {payment_id}\n")
    
    payment_info = check_payment_status(payment_id)
    
    if not payment_info:
        print("❌ Не удалось получить информацию о платеже")
        sys.exit(1)
    
    print("=" * 80)
    print("📋 ИНФОРМАЦИЯ О ПЛАТЕЖЕ")
    print("=" * 80)
    print(f"\nID: {payment_info.get('id')}")
    print(f"Статус: {payment_info.get('status')}")
    print(f"Сумма: {payment_info.get('amount', {}).get('value')} {payment_info.get('amount', {}).get('currency')}")
    print(f"Описание: {payment_info.get('description', 'N/A')}")
    print(f"Создан: {payment_info.get('created_at', 'N/A')}")
    print(f"Оплачен: {payment_info.get('paid_at', 'N/A')}")
    
    if payment_info.get('status') == 'canceled':
        print(f"\n❌ ПЛАТЕЖ ОТМЕНЕН")
        cancellation_details = payment_info.get('cancellation_details', {})
        cancel_info = format_cancellation_details(cancellation_details)
        print(f"   Причина: {cancel_info['reason']}")
        print(f"   Код причины: {cancel_info['reason_code']}")
        print(f"   Инициатор: {cancel_info['party']}")
    
    if payment_info.get('status') == 'pending':
        print(f"\n⏳ ПЛАТЕЖ В ОЖИДАНИИ")
        expires_at = payment_info.get('expires_at', 'N/A')
        print(f"   Истекает: {expires_at}")
        if expires_at != 'N/A':
            from datetime import datetime
            try:
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                now = datetime.now(expires_dt.tzinfo)
                if expires_dt < now:
                    print(f"   ⚠️ ВРЕМЯ ИСТЕКЛО! Платеж должен быть автоматически отменен.")
            except:
                pass
    
    if payment_info.get('status') == 'succeeded':
        print(f"\n✅ ПЛАТЕЖ УСПЕШЕН")
        print(f"   Оплачен: {payment_info.get('paid_at', 'N/A')}")
    
    # Метод оплаты
    payment_method = payment_info.get('payment_method', {})
    if payment_method:
        print(f"\n💳 Метод оплаты: {payment_method.get('type', 'N/A')}")
        if payment_method.get('type') == 'bank_card':
            card = payment_method.get('card', {})
            if card:
                print(f"   Карта: ****{card.get('last4', '****')}")
                print(f"   Тип: {card.get('card_type', 'N/A')}")
    
    # Metadata
    metadata = payment_info.get('metadata', {})
    if metadata:
        print(f"\n📝 Metadata:")
        for key, value in metadata.items():
            print(f"   {key}: {value}")
    
    print("\n" + "=" * 80)






