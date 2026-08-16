# -*- coding: utf-8 -*-
"""
این فایل را فقط یک‌بار، بعد از بالا آوردن اپ Flask روی سرور (پشت HTTPS)، اجرا کنید تا وبهوک ثبت شود:

    python3 install/set_webhook.py

قبلش متغیر WEBHOOK_URL پایین را با آدرس عمومی و https اپ خودتان جایگزین کنید
(همان آدرسی که app.py روی آن جواب می‌دهد، مثلاً از پشت nginx + gunicorn).

بعد از اجرای موفق، به‌خاطر امنیت این فایل را حذف یا نام آن را تغییر دهید،
یا حداقل WEBHOOK_URL را دوباره به CHANGE-ME برگردانید.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.telegram import Telegram

# آدرس کامل و https اپ روی سرور شما (بدون اسلش انتهایی اضافه)
WEBHOOK_URL = 'https://CHANGE-ME.example.com/zandbot/'


def main() -> None:
    if 'CHANGE-ME' in WEBHOOK_URL:
        print('ابتدا متغیر WEBHOOK_URL را در همین فایل با آدرس واقعی اپ روی سرور خودتان جایگزین کنید.')
        return

    result = Telegram.set_webhook(WEBHOOK_URL, Config.get('webhook_secret'))

    if result is not None:
        print('✅ وبهوک با موفقیت ثبت شد.')
        print(f'آدرس: {WEBHOOK_URL}')
    else:
        print('❌ ثبت وبهوک ناموفق بود. توکن و آدرس را بررسی کنید.')


if __name__ == '__main__':
    main()
