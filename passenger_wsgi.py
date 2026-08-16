# -*- coding: utf-8 -*-
"""
این فایل مخصوص هاست‌های اشتراکی است که ران‌کردن اپ پایتون را با Passenger
(همون چیزی که پنل هاست شما زیر گزینه‌ی "Setup Python App" می‌سازد) انجام می‌دهند.

وقتی از داخل پنل یک "Python App" جدید می‌سازید، خودِ پنل یک فایل passenger_wsgi.py
در پوشه‌ی اپ برایتان می‌سازد (معمولاً با یک نمونه‌ی خالی Flask داخلش). محتوای همون
فایل را پاک کنید و دقیقاً همین کد پایین را جایگزینش کنید — کاری با بقیه‌ی پروژه ندارد،
فقط به Passenger می‌گوید اپ اصلی (app.py) کجاست.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as application  # noqa: E402  (Passenger specifically looks for a variable named "application")
