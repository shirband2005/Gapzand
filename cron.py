# -*- coding: utf-8 -*-
"""
راهنما:
این فایل را روی سرور خود به عنوان یک Cron Job با فاصله‌ی هر ۱ دقیقه اجرا کنید:
    * * * * * /usr/bin/python3 /path/to/zandbot/cron.py >/dev/null 2>&1

وظیفه: پیام‌های همگانی (/broadcast در پی‌وی ربات توسط مالک) را به‌صورت
دسته‌ای (batch) ارسال می‌کند تا به محدودیت ریت‌لیمیت تلگرام برخورد نکنیم،
و پیام‌های خوش‌آمد/خداحافظی که «حذف خودکار» برایشان فعال شده را در زمان مقرر پاک می‌کند.

Port of cron.php.
"""
import json
import os
import time

from core.database import Database
from core.telegram import Telegram

BATCH_SIZE = 25  # messages per cron run, per pending broadcast
STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage')


def run_broadcasts() -> None:
    conn = Database.conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM broadcasts WHERE status IN ('pending','running') ORDER BY id ASC LIMIT 1")
        rows = cur.fetchall()

    for row in rows:
        payload = json.loads(row['payload'])
        target = row['target']
        ids = Database.all_user_ids() if target == 'users' else Database.all_group_ids()
        sent = int(row['sent'])
        slice_ = ids[sent:sent + BATCH_SIZE]

        if not slice_:
            with conn.cursor() as cur:
                cur.execute("UPDATE broadcasts SET status='done' WHERE id=%s", [row['id']])
            continue

        with conn.cursor() as cur:
            cur.execute("UPDATE broadcasts SET status='running' WHERE id=%s", [row['id']])

        for chat_id in slice_:
            Telegram.call('copyMessage', {
                'chat_id': chat_id,
                'from_chat_id': payload['from_chat_id'],
                'message_id': payload['message_id'],
            })
            time.sleep(0.06)  # ~16 msgs/sec ceiling, well under Telegram's global limit

        new_sent = sent + len(slice_)
        status = 'done' if new_sent >= int(row['total']) else 'running'
        with conn.cursor() as cur:
            cur.execute("UPDATE broadcasts SET sent=%s, status=%s WHERE id=%s", [new_sent, status, row['id']])


def run_auto_delete_sweep() -> None:
    """
    "حذف خودکار" پیام خوش‌آمد/خداحافظی: هر پیام با تاخیر اختصاصی خودش (پیش‌فرض ۱۰ ثانیه، قابل تنظیم در پنل) پاک می‌شود.
    توجه: دقت واقعی حذف به فاصله‌ی اجرای این کرون وابسته است. اگه این کرون هر ۱ دقیقه اجرا بشه،
    زمان‌های زیر ۶۰ ثانیه (مثل ۱۰ یا ۳۰ ثانیه) ممکنه با کمی تاخیر (تا ~۱ دقیقه) اجرا بشن، نه دقیقاً سروقت.
    برای دقت بهتر روی زمان‌های کوتاه، فاصله‌ی اجرای کرون رو کمتر کنید (مثلاً هر ۱۰ ثانیه با یک حلقه‌ی shell).
    """
    welcome_file = os.path.join(STORAGE_DIR, 'welcome_pending_delete.json')
    if not os.path.isfile(welcome_file):
        return

    try:
        with open(welcome_file, encoding='utf-8') as f:
            items = json.load(f) or []
    except (ValueError, OSError):
        items = []

    remaining = []
    for item in items:
        delay = int(item.get('delay') or 60)  # legacy entries saved before this setting existed
        if int(time.time()) - int(item.get('time') or 0) >= delay:
            Telegram.delete_message(int(item['chat_id']), int(item['message_id']))
        else:
            remaining.append(item)

    try:
        with open(welcome_file, 'w', encoding='utf-8') as f:
            json.dump(remaining, f)
    except OSError:
        pass


if __name__ == '__main__':
    run_broadcasts()
    run_auto_delete_sweep()
    # نکته: مطابق نسخه‌ی اصلی (PHP)، اخراج خودکار اعضای تاییدنشده‌ی کپچا در این کرون
    # پیاده‌سازی نشده و به‌صورت lazy باقی مانده (طبق کامنت اصلی در MemberHandler).
