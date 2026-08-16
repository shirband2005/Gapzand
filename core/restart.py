# -*- coding: utf-8 -*-
"""
راه‌اندازی مجدد اپ، بدون نیاز به SSH یا رفتن تو پنل.

روی هاست اشتراکی (همونی که با «Setup Python App» بالا آوردیم)، اپ زیر Passenger
اجرا می‌شه. قرارداد استاندارد Passenger این‌طوریه: اگه فایلی به اسم tmp/restart.txt
داخل پوشه‌ی اصلی اپ وجود داشته باشه و زمان تغییرش (mtime) جدید باشه، Passenger با
اولین درخواستی که بعدش می‌رسه، پردازه‌ی اپ رو کاملاً از نو بالا می‌آورد — یعنی
تمام فایل‌های پایتون (از جمله هر قابلیت جدیدی که آپلود کردی) دوباره خونده می‌شن.

برای اجرای دستی روی VPS/سرور با systemd یا Gunicorn هم بی‌ضرره (فقط این فایل رو
می‌سازه)، ولی روی اون‌جور دیپلوی‌ها اگه سرویس‌تون خودش watcher نداره، ری‌استارت
واقعی رو باید با systemctl/supervisor انجام بدید؛ لمس این فایل به‌تنهایی روی
Gunicorn معمولی اثری نداره.
"""
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ریشه‌ی پروژه
RESTART_FILE = os.path.join(BASE_DIR, 'tmp', 'restart.txt')


def trigger_restart() -> bool:
    """tmp/restart.txt رو می‌سازه (یا اگه بود، mtime‌ش رو آپدیت می‌کنه). موفق بود True برمی‌گردونه."""
    try:
        os.makedirs(os.path.dirname(RESTART_FILE), exist_ok=True)
        if not os.path.isfile(RESTART_FILE):
            with open(RESTART_FILE, 'w', encoding='utf-8') as f:
                f.write('')
        now = time.time()
        os.utime(RESTART_FILE, (now, now))
        return True
    except OSError:
        return False
