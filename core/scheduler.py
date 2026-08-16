# -*- coding: utf-8 -*-
"""
جایگزین کرون‌جاب: همین‌جا، داخل خودِ پردازه‌ی Flask، یک ترد پس‌زمینه اجرا می‌شود
که هر چند ثانیه یک‌بار کارهای دوره‌ای (ارسال پیام همگانی و حذف خودکار پیام
خوش‌آمد/خداحافظی) را انجام می‌دهد. دیگر نیازی به تنظیم Cron Job روی سرور نیست.

اگر اپ را با چند worker اجرا کنید (مثلاً `gunicorn -w 4`)، هر worker یک نسخه از
این ترد را بالا می‌آورد؛ برای این‌که کار دو بار انجام نشود، قبل از هر دور از یک
قفل نام‌دار در MySQL (GET_LOCK) استفاده می‌شود — فقط یکی از worker/pid ها در هر
لحظه واقعاً کار را انجام می‌دهد، بقیه فقط چک کرده و رد می‌شوند.
"""
import threading
import time
import traceback

INTERVAL_SECONDS = 10  # هر چند وقت یک‌بار سوییپ اجرا شود (روی زمان‌های کوتاهِ حذف خودکار هم دقت خوبی می‌دهد)
LOCK_NAME = 'zandbot_scheduler'

_started = False
_lock = threading.Lock()


def _loop() -> None:
    from core.database import Database
    from cron import run_broadcasts, run_auto_delete_sweep

    while True:
        try:
            if Database.try_acquire_lock(LOCK_NAME):
                try:
                    run_broadcasts()
                    run_auto_delete_sweep()
                finally:
                    Database.release_lock(LOCK_NAME)
        except Exception:
            # هیچ خطایی در ترد پس‌زمینه نباید کل اپ را متوقف کند؛ فقط لاگ می‌کنیم و ادامه می‌دهیم
            traceback.print_exc()
        time.sleep(INTERVAL_SECONDS)


def start() -> None:
    """یک‌بار، موقع بالا آمدن اپ صدا زده می‌شود (از app.py)."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
        t = threading.Thread(target=_loop, name='zandbot-scheduler', daemon=True)
        t.start()
