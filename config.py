# -*- coding: utf-8 -*-
"""
تنظیمات ربات مدیریت گروه دانشگاه زند شیراز
------------------------------------------------
همه‌ی مقادیر از "متغیرهای محیطی" (Environment Variables) خوانده می‌شوند — دقیقاً
همون چیزی که Railway (و بیشتر پلتفرم‌های ابری) برای تنظیمات استفاده می‌کنن.

روی Railway: از تب "Variables" همین متغیرها رو ست کن (توضیح کامل در README.md).
روی هاست اشتراکی / اجرای محلی: اگه هیچ متغیری ست نکنی، همون مقادیر پیش‌فرض
(که قبلاً این‌جا هاردکد بودن) استفاده می‌شن — یعنی چیزی خراب نمی‌شه.

اگه دیتابیس MySQL رو از مارکت‌پلیس Railway اضافه کنی، Railway خودش به‌صورت خودکار
متغیرهای MYSQLHOST / MYSQLUSER / MYSQLPASSWORD / MYSQLDATABASE / MYSQLPORT رو
می‌سازه و به این سرویس تزریق می‌کنه — نیازی نیست دستی چیزی برای دیتابیس تنظیم کنی.
"""
import os


def _env_int_list(name: str, default: str) -> list:
    raw = os.environ.get(name, default)
    return [int(x.strip()) for x in raw.split(',') if x.strip()]


CONFIG = {

    # توکن ربات (از @BotFather)
    'bot_token': os.environ.get('BOT_TOKEN', '8680723464:AAGca2_GEFJhHAOHXvCjUo_5A1PXop7tEEc'),

    # یوزرنیم ربات بدون @
    'bot_username': os.environ.get('BOT_USERNAME', 'Gapzandbot'),

    # نام دانشگاه / برند ربات - در متن‌های پیش‌فرض استفاده می‌شود
    'university_name': os.environ.get('UNIVERSITY_NAME', 'دانشگاه زند شیراز'),

    # لینک گروه اصلی (اختیاری - در پیام خوش‌آمد نمایش داده می‌شود)
    'main_group_link': os.environ.get('MAIN_GROUP_LINK', 'https://t.me/Gapzand'),

    # آیدی عددی مالک/مالکان ربات (سوپر ادمین)، جدا شده با کاما اگه چندتا هستن (مثلاً "111,222").
    # با @userinfobot آیدی خودتان را پیدا کنید. این افراد به پنل مدیریت کلی ربات
    # (آمار، پیام همگانی، ریستارت بات) دسترسی دارند
    'owners': _env_int_list('OWNERS', '8406519786'),

    # یک رشته‌ی دلخواه و محرمانه برای اعتبارسنجی وبهوک (X-Telegram-Bot-Api-Secret-Token)
    'webhook_secret': os.environ.get('WEBHOOK_SECRET', 'zand-shiraz-secret-2026'),

    # اتصال دیتابیس — روی Railway با افزودن پلاگین MySQL این‌ها خودکار پر می‌شوند
    'db': {
        'host': os.environ.get('MYSQLHOST', os.environ.get('DB_HOST', 'localhost')),
        'port': int(os.environ.get('MYSQLPORT', os.environ.get('DB_PORT', '3306'))),
        'name': os.environ.get('MYSQLDATABASE', os.environ.get('DB_NAME', 'nojewwou_gapzand')),
        'user': os.environ.get('MYSQLUSER', os.environ.get('DB_USER', 'nojewwou_gapzand')),
        'pass': os.environ.get('MYSQLPASSWORD', os.environ.get('DB_PASS', 'Abolfazl1384')),
        'charset': 'utf8mb4',
    },

}
