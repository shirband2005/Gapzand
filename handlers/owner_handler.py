# -*- coding: utf-8 -*-
from core.database import Database
from core.helpers import Helpers
from core.restart import trigger_restart
from core.telegram import Telegram

RESTART_PHRASES = {'ریستارت بات', 'ریستارت_بات', '/restart', 'restart'}


class OwnerHandler:
    """Port of handlers/OwnerHandler.php."""

    @staticmethod
    def maybe_handle_restart(message: dict) -> bool:
        """
        دستور «ریستارت بات» — فقط برای مالک(های) ربات، هم تو گروه هم تو پی‌وی کار می‌کند.
        اپ رو مجبور می‌کنه از نو بالا بیاد تا هر قابلیت جدیدی که آپلود شده فعال بشه.
        قبل از هر پردازش دیگه‌ای روی پیام باید چک بشه (چون به تنظیمات گروه ربطی نداره).
        """
        text = (message.get('text') or '').strip()
        if text not in RESTART_PHRASES:
            return False

        user_id = int((message.get('from') or {}).get('id') or 0)
        chat_id = int(message['chat']['id'])

        if not Helpers.is_owner(user_id):
            return False  # کاربر عادی نوشته، نادیده بگیر - نه پیام خطا (مثل بقیه دستورات ادمین‌محور)

        ok = trigger_restart()
        if ok:
            Telegram.send_message(chat_id,
                "🔄 دستور ری‌استارت ارسال شد.\n"
                "ربات ظرف چند ثانیه با آخرین نسخه‌ی آپلودشده دوباره بالا می‌آید. "
                "اگه همین الان یه پیام بفرستی و جواب ندید، چند ثانیه صبر کن و دوباره امتحان کن.")
        else:
            Telegram.send_message(chat_id, '⚠️ ری‌استارت ناموفق بود (دسترسی نوشتن روی هاست را چک کن).')
        return True

    @staticmethod
    def handle_private(message: dict) -> bool:
        """Returns True if the message was a recognized owner command and was handled."""
        user_id = int(message['from']['id'])
        if not Helpers.is_owner(user_id):
            return False
        chat_id = int(message['chat']['id'])
        text = (message.get('text') or '').strip()

        if text in ('/stats', '/آمار', 'آمار'):
            groups = Database.count_groups()
            users = Database.count_users()
            Telegram.send_message(chat_id, f"📊 <b>آمار ربات</b>\n👥 کاربران: {users}\n👨‍👩‍👧‍👦 گروه‌ها: {groups}")
            return True

        # پخش_گروه‌ها باید قبل از پخش چک شود، وگرنه با startswith اشتباه گرفته می‌شود
        if text.startswith('/broadcastgroups') or text.startswith('/پخش_گروه‌ها') or text.startswith('پخش_گروه‌ها'):
            OwnerHandler._start_broadcast(chat_id, 'groups')
            return True

        if text.startswith('/broadcast') or text.startswith('/پخش') or text.startswith('پخش'):
            OwnerHandler._start_broadcast(chat_id)
            return True

        return False

    @staticmethod
    def _start_broadcast(chat_id, target: str = 'users') -> None:
        """call when a reply arrives after /broadcast was requested - simplified single-step flow"""
        target_label = 'کاربران' if target == 'users' else 'گروه‌ها'
        Telegram.send_message(
            chat_id,
            f"پیامی که می‌خوای برای همه‌ی {target_label} فوروارد بشه رو با <b>ریپلای روی همین پیام</b> بفرست.\n\n"
            "استفاده: پیام موردنظر رو بفرست، بعد روش ریپلای کن و بنویس:\n"
            f"<code>تایید_ارسال {target}</code>",
        )

    @staticmethod
    def handle_confirm_send(message: dict) -> bool:
        user_id = int(message['from']['id'])
        if not Helpers.is_owner(user_id):
            return False
        chat_id = int(message['chat']['id'])
        text = (message.get('text') or '').strip()
        if not (text.startswith('/confirmsend') or text.startswith('/تایید_ارسال') or text.startswith('تایید_ارسال')):
            return False
        if 'reply_to_message' not in message:
            Telegram.send_message(chat_id, 'باید روی پیامی که می‌خوای ارسال بشه ریپلای کنی.')
            return True
        parts = text.split(' ')
        target = parts[1] if len(parts) > 1 else 'users'
        target = target if target in ('users', 'groups') else 'users'

        src = message['reply_to_message']
        payload = {
            'from_chat_id': chat_id,
            'message_id': src['message_id'],
        }
        bid = Database.queue_broadcast(user_id, payload, target)
        Telegram.send_message(chat_id, f"✅ پیام همگانی در صف قرار گرفت (#{bid}). ارسال طی چند دقیقه با کران‌جاب انجام می‌شود.")
        return True
