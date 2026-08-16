# -*- coding: utf-8 -*-
import json
import os
import time

from core.database import Database
from core.helpers import Helpers
from core.telegram import Telegram

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'storage')


class MemberHandler:
    """Port of handlers/MemberHandler.php."""

    @staticmethod
    def on_join(message: dict) -> None:
        chat_id = int(message['chat']['id'])
        group = Database.get_group(chat_id)
        settings = group['settings']

        for user in message.get('new_chat_members') or []:
            if user.get('is_bot'):
                continue  # don't welcome/captcha other bots
            user_id = int(user['id'])
            Database.upsert_user(user_id, user.get('first_name'), user.get('username'))
            Database.get_member(chat_id, user_id)  # ensure row exists

            # "اد اجباری": if someone else performed the add (not a self-join via link),
            # credit the inviter's running total for this group.
            inviter_id = int((message.get('from') or {}).get('id') or 0)
            inviter_user = None
            inviter_invites = 0
            if inviter_id != 0 and inviter_id != user_id:
                inviter_invites = Database.bump_invites(chat_id, inviter_id)
                inviter_user = message.get('from')

            group_title = message['chat'].get('title') or ''
            if settings['captcha']['enabled']:
                MemberHandler._send_captcha(chat_id, user_id, user, settings)
            elif settings['welcome']['enabled']:
                MemberHandler._send_welcome(chat_id, user_id, user, settings, group_title,
                                             inviter_user, inviter_invites)

        if settings.get('antiservice', True):
            Telegram.delete_message(chat_id, int(message['message_id']))

    @staticmethod
    def on_leave(message: dict) -> None:
        chat_id = int(message['chat']['id'])
        group = Database.get_group(chat_id)
        settings = group['settings']
        user = message['left_chat_member']

        if settings.get('goodbye', {}).get('enabled') and not user.get('is_bot'):
            MemberHandler._send_goodbye(chat_id, user, settings, message['chat'].get('title') or '')

        if settings.get('antiservice', True):
            Telegram.delete_message(chat_id, int(message['message_id']))

    # ---------- goodbye ----------

    @staticmethod
    def _send_goodbye(chat_id: int, user: dict, settings: dict, group_title: str = '') -> None:
        built = MemberHandler.build_goodbye_message(settings, user, group_title)

        if built['media']:
            sent = (Telegram.send_animation(chat_id, built['media']['file_id'], built['text'])
                    if built['media']['type'] == 'animation'
                    else Telegram.send_photo(chat_id, built['media']['file_id'], built['text']))
        else:
            sent = Telegram.send_message(chat_id, built['text'])

        if sent and settings.get('goodbye', {}).get('auto_delete'):
            delay = int(settings['goodbye'].get('auto_delete_seconds') or 10)
            MemberHandler._remember_auto_delete_message(chat_id, int(sent['message_id']), delay)

    @staticmethod
    def build_goodbye_message(settings: dict, user: dict, group_title: str) -> dict:
        g = settings['goodbye']
        user_id = int(user.get('id') or 0)
        name = Helpers.full_name(user) or user.get('username') or 'کاربر'
        username = user.get('username') or ''

        ts = int(time.time())
        _, jm, _ = Helpers.to_jalali(ts)

        replace = {
            '{user}': Helpers.mention(user_id, name),
            '{mention}': Helpers.mention(user_id, name),  # legacy alias
            '{name}': Helpers.escape(name),
            '{group}': Helpers.escape(group_title),
            '{date}': Helpers.jalali_date_string(ts),
            '{time}': time.strftime('%H:%M'),
            '{day_of_week}': Helpers.weekday_name_persian(ts),
            '{month_name}': Helpers.jalali_month_name(jm),
            '{id}': str(user_id),
            '{user_id}': str(user_id),
            '{username}': ('@' + username) if username else '—',
            '{emoji}': Helpers.random_emoji(),
        }
        text = _strtr(g['text'], replace)

        return {
            'text': text,
            'media': g['media'] if g.get('media', {}).get('file_id') else None,
        }

    # ---------- welcome ----------

    @staticmethod
    def _send_welcome(chat_id: int, user_id: int, user: dict, settings: dict, group_title: str = '',
                       inviter_user=None, inviter_invites: int = 0) -> None:
        built = MemberHandler.build_welcome_message(settings, user, group_title, inviter_user,
                                                      inviter_invites, chat_id)
        extra = {'reply_markup': json.dumps(built['markup'])} if built['markup'] else {}

        if built['media']:
            sent = (Telegram.send_animation(chat_id, built['media']['file_id'], built['text'], extra)
                    if built['media']['type'] == 'animation'
                    else Telegram.send_photo(chat_id, built['media']['file_id'], built['text'], extra))
        else:
            sent = Telegram.send_message(chat_id, built['text'], extra)

        if sent and settings.get('welcome', {}).get('auto_delete'):
            delay = int(settings['welcome'].get('auto_delete_seconds') or 10)
            MemberHandler._remember_auto_delete_message(chat_id, int(sent['message_id']), delay)

    @staticmethod
    def build_welcome_message(settings: dict, user: dict, group_title: str,
                               inviter_user, inviter_invites: int, chat_id: int) -> dict:
        w = settings['welcome']
        user_id = int(user.get('id') or 0)
        name = Helpers.full_name(user) or user.get('username') or 'کاربر'
        username = user.get('username') or ''

        inviter_mention = (
            Helpers.mention(int(inviter_user['id']), Helpers.full_name(inviter_user) or inviter_user.get('username') or 'کاربر')
            if inviter_user else '—'
        )

        ts = int(time.time())
        _, jm, _ = Helpers.to_jalali(ts)

        replace = {
            '{user}': Helpers.mention(user_id, name),
            '{mention}': Helpers.mention(user_id, name),  # legacy alias
            '{name}': Helpers.escape(name),
            '{inviter}': inviter_mention,
            '{inviter_invites_count}': str(inviter_invites),
            '{group}': Helpers.escape(group_title),
            '{date}': Helpers.jalali_date_string(ts),
            '{time}': time.strftime('%H:%M'),
            '{day_of_week}': Helpers.weekday_name_persian(ts),
            '{month_name}': Helpers.jalali_month_name(jm),
            '{id}': str(user_id),
            '{user_id}': str(user_id),
            '{username}': ('@' + username) if username else '—',
            '{emoji}': Helpers.random_emoji(),
        }
        text = _strtr(w['text'], replace)

        rows = []
        if w.get('show_rules_button') and str(settings.get('rules') or '').strip() != '':
            rows.append([{'text': '📜 قوانین گروه', 'callback_data': f'rules:{chat_id}'}])
        for btn in w.get('buttons') or []:
            if btn.get('text') and btn.get('url'):
                rows.append([{'text': btn['text'], 'url': btn['url']}])

        return {
            'text': text,
            'markup': {'inline_keyboard': rows} if rows else None,
            'media': w['media'] if w.get('media', {}).get('file_id') else None,
        }

    # ---------- auto-delete bookkeeping (consumed by cron.py) ----------

    @staticmethod
    def _remember_auto_delete_message(chat_id: int, message_id: int, delay_seconds: int = 10) -> None:
        file_path = os.path.join(STORAGE_DIR, 'welcome_pending_delete.json')
        data = []
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f) or []
            except (ValueError, OSError):
                data = []
        data.append({'chat_id': chat_id, 'message_id': message_id, 'time': int(time.time()), 'delay': delay_seconds})
        try:
            os.makedirs(STORAGE_DIR, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except OSError:
            pass

    # ---------- captcha ----------

    @staticmethod
    def _send_captcha(chat_id: int, user_id: int, user: dict, settings: dict) -> None:
        # restrict until verified
        Telegram.restrict_chat_member(chat_id, user_id, {'can_send_messages': False})

        name = Helpers.full_name(user) or user.get('username') or 'کاربر'
        text = (Helpers.mention(user_id, name)
                + " برای شروع صحبت در گروه، روی دکمه‌ی زیر بزن تا تایید بشی ✅\n"
                + "(۱۲۰ ثانیه فرصت داری، وگرنه از گروه حذف می‌شی)")

        markup = {'inline_keyboard': [[
            {'text': '✅ من ربات نیستم', 'callback_data': f'verify:{chat_id}:{user_id}'},
        ]]}

        sent = Telegram.send_message(chat_id, text, {'reply_markup': json.dumps(markup)})
        # Note: expiry/kick handled lazily - if user tries to talk while unverified they're reminded,
        # and admins can /kick manually. For strict auto-kick a cron sweep can be added if needed.
        if sent:
            MemberHandler._remember_captcha_message(chat_id, user_id, int(sent['message_id']))

    @staticmethod
    def _remember_captcha_message(chat_id: int, user_id: int, message_id: int) -> None:
        file_path = os.path.join(STORAGE_DIR, 'captcha_pending.json')
        data = []
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f) or []
            except (ValueError, OSError):
                data = []
        data.append({'chat_id': chat_id, 'user_id': user_id, 'message_id': message_id, 'time': int(time.time())})
        try:
            os.makedirs(STORAGE_DIR, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except OSError:
            pass


def _strtr(text: str, replace: dict) -> str:
    """Port of PHP's strtr($text, $replace) — longest-key-first literal replacement."""
    if not text:
        return text
    for key in sorted(replace.keys(), key=len, reverse=True):
        text = text.replace(key, replace[key])
    return text
