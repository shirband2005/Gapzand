# -*- coding: utf-8 -*-
import html
import random
import re
import time as time_module
from datetime import datetime

from core.config import Config
from core.telegram import Telegram


class Helpers:
    """Port of core/Helpers.php."""

    # ---------- permissions ----------

    @staticmethod
    def is_owner(user_id: int) -> bool:
        return user_id in (Config.get('owners') or [])

    @staticmethod
    def is_group_admin(chat_id, user_id: int) -> bool:
        if Helpers.is_owner(user_id):
            return True
        member = Telegram.get_chat_member(chat_id, user_id)
        if not member:
            return False
        return member.get('status') in ('creator', 'administrator')

    @staticmethod
    def is_group_creator(chat_id, user_id: int) -> bool:
        if Helpers.is_owner(user_id):
            return True
        member = Telegram.get_chat_member(chat_id, user_id)
        return bool(member) and member.get('status') == 'creator'

    # ---------- text ----------

    @staticmethod
    def mention(user_id: int, name: str) -> str:
        return f'<a href="tg://user?id={user_id}">{Helpers.escape(name)}</a>'

    @staticmethod
    def escape(text: str) -> str:
        return html.escape(text or '', quote=True)

    @staticmethod
    def full_name(user: dict) -> str:
        user = user or {}
        return ((user.get('first_name') or '') + ' ' + (user.get('last_name') or '')).strip()

    @staticmethod
    def extract_target_user_id(message: dict, arg: str):
        """extract target user id from a command: reply-to message OR numeric arg"""
        reply = message.get('reply_to_message') or {}
        if (reply.get('from') or {}).get('id') is not None:
            return int(reply['from']['id'])
        if arg and re.match(r'^\d+$', arg):
            return int(arg)
        return None

    @staticmethod
    def target_name(message: dict) -> str:
        reply = message.get('reply_to_message') or {}
        if reply.get('from'):
            return Helpers.full_name(reply['from'])
        return 'کاربر'

    @staticmethod
    def contains_link(text: str) -> bool:
        return bool(re.search(r'(https?://|t\.me/|telegram\.me/|www\.)', text, re.IGNORECASE)) \
            or bool(re.search(r'@[a-zA-Z0-9_]{4,}', text))

    @staticmethod
    def contains_english(text: str) -> bool:
        clean = (text or '').strip()
        return clean != '' and bool(re.match(r'^[\x00-\x7F\s.,!?0-9]+$', clean)) \
            and bool(re.search(r'[a-zA-Z]', clean))

    @staticmethod
    def contains_hashtag(text: str) -> bool:
        return bool(re.search(r'#[\u0600-\u06FFa-zA-Z0-9_]+', text or ''))

    @staticmethod
    def contains_badword(text: str, badwords: list):
        normalized = (text or '').lower()
        for word in badwords or []:
            if word and word.lower() in normalized:
                return word
        return None

    @staticmethod
    def human_time(minutes: int) -> str:
        if minutes < 60:
            return f'{minutes} دقیقه'
        if minutes < 1440:
            return f'{round(minutes / 60, 1)} ساعت'
        return f'{round(minutes / 1440, 1)} روز'

    @staticmethod
    def parse_duration(s):
        """parse "10m" "2h" "3d" style durations into minutes, or None"""
        if not s:
            return None
        m = re.match(r'^(\d+)([mhd])$', s.strip())
        if not m:
            return None
        n = int(m.group(1))
        unit = m.group(2)
        if unit == 'm':
            return n
        if unit == 'h':
            return n * 60
        if unit == 'd':
            return n * 1440
        return None

    # ---------- Jalali (Persian) calendar helpers ----------

    @staticmethod
    def to_jalali(timestamp: int):
        """Gregorian timestamp -> (jy, jm, jd)"""
        dt = datetime.fromtimestamp(timestamp)
        return Helpers._gregorian_to_jalali(dt.year, dt.month, dt.day)

    @staticmethod
    def _gregorian_to_jalali(gy: int, gm: int, gd: int):
        g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        gy2 = gy + 1 if gm > 2 else gy
        days = (355666 + (365 * gy) + (gy2 + 3) // 4 - (gy2 + 99) // 100
                + (gy2 + 399) // 400 + gd + g_d_m[gm - 1])
        jy = -1595 + (33 * (days // 12053))
        days %= 12053
        jy += 4 * (days // 1461)
        days %= 1461
        if days > 365:
            jy += (days - 1) // 365
            days = (days - 1) % 365
        if days < 186:
            jm = 1 + days // 31
            jd = 1 + (days % 31)
        else:
            jm = 7 + (days - 186) // 30
            jd = 1 + ((days - 186) % 30)
        return jy, jm, jd

    @staticmethod
    def jalali_date_string(timestamp: int) -> str:
        jy, jm, jd = Helpers.to_jalali(timestamp)
        return f'{jy:04d}/{jm:02d}/{jd:02d}'

    @staticmethod
    def jalali_month_name(jm: int) -> str:
        names = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
                 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
        return names[max(1, min(12, jm)) - 1]

    @staticmethod
    def weekday_name_persian(timestamp: int) -> str:
        """Python's weekday(): Monday=0..Sunday=6; Persian week starts Saturday."""
        names_by_python_weekday = {
            6: 'یکشنبه', 0: 'دوشنبه', 1: 'سه\u200cشنبه', 2: 'چهارشنبه',
            3: 'پنجشنبه', 4: 'جمعه', 5: 'شنبه',
        }
        dt = datetime.fromtimestamp(timestamp)
        return names_by_python_weekday[dt.weekday()]

    @staticmethod
    def random_emoji() -> str:
        emojis = ['🌸', '🎉', '✨', '🌟', '🎊', '🥳', '💫', '🌺', '🌼', '🍀', '🔥', '💐', '🌈', '🎈']
        return random.choice(emojis)
