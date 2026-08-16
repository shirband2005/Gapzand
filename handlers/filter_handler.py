# -*- coding: utf-8 -*-
from core.database import Database
from core.helpers import Helpers
from core.telegram import Telegram
from handlers.force_join_handler import ForceJoinHandler


class FilterHandler:
    """Port of handlers/FilterHandler.php."""

    @staticmethod
    def check(message: dict, group: dict) -> bool:
        """
        Runs all checks on a normal group message.
        Returns True if the message was handled/removed (caller should stop further processing).
        """
        chat_id = int(message['chat']['id'])
        user_id = int(message['from']['id'])
        settings = group['settings']

        # never restrict admins
        if Helpers.is_group_admin(chat_id, user_id):
            return False

        if ForceJoinHandler.check_and_enforce(message, group):
            return True

        force_add = settings.get('force_add') or {'enabled': False, 'required': 0}
        if force_add.get('enabled') and int(force_add.get('required') or 0) > 0:
            required = int(force_add['required'])
            have = Database.get_invites(chat_id, user_id)
            if have < required:
                Telegram.delete_message(chat_id, int(message['message_id']))
                name = Helpers.full_name(message['from'])
                left = required - have
                Telegram.send_message(chat_id, Helpers.mention(user_id, name)
                                       + f" برای صحبت در این گروه باید {required} نفر عضو جدید به گروه اضافه کنی.\n"
                                       + f"تا الان {have} نفر آورده‌ای، {left} نفر دیگه مونده. پیامت حذف شد.")
                return True

        if (settings.get('only_admins') or False) is True:
            Telegram.delete_message(chat_id, int(message['message_id']))
            return True

        violation = FilterHandler._detect_lock_violation(message, settings['locks'])
        if violation is not None:
            return FilterHandler._punish(chat_id, user_id, message, group,
                                          f"پیام شما به‌دلیل قفل بودن «{violation}» حذف شد.")

        char_limit = settings.get('char_limit') or {'enabled': False, 'max': 0}
        if char_limit.get('enabled') and int(char_limit.get('max') or 0) > 0:
            text = message.get('text') or message.get('caption') or ''
            if text != '' and len(text) > int(char_limit['max']):
                return FilterHandler._punish(
                    chat_id, user_id, message, group,
                    f"پیام شما به‌دلیل عبور از سقف مجاز کاراکتر (حداکثر {char_limit['max']} کاراکتر) حذف شد.")

        # "قفل فحش" gates the custom bad-word list: the list is managed from
        # لیست‌ها و گزارشات -> فیلترها, but only enforced while this lock is on.
        if settings['locks'].get('profanity') and message.get('text'):
            bad = Helpers.contains_badword(message['text'], settings['badwords'])
            if bad is not None:
                return FilterHandler._punish(chat_id, user_id, message, group,
                                              "پیام شما به‌دلیل استفاده از کلمه‌ی نامناسب حذف شد.")

        if settings.get('flood', {}).get('enabled', True):
            if FilterHandler._is_flooding(chat_id, user_id, settings['flood']):
                return FilterHandler._punish(
                    chat_id, user_id, message, group,
                    'پیام شما به‌دلیل ارسال پیام پشت‌سرهم (رگبار پیام/اسپم) حذف شد.',
                    int(settings['flood']['mute_minutes']))

        return False

    @staticmethod
    def _detect_lock_violation(message: dict, locks: dict):
        field_to_lock = {
            'photo': 'photo', 'video': 'video', 'voice': 'voice',
            'video_note': 'video_note', 'audio': 'audio', 'document': 'document',
            'contact': 'contact', 'location': 'location', 'sticker': 'sticker',
            'game': 'game', 'poll': 'poll',
        }
        labels = {
            'photo': 'عکس', 'video': 'ویدیو', 'voice': 'صدا', 'video_note': 'ویدیو-پیام',
            'audio': 'موزیک', 'document': 'فایل', 'contact': 'مخاطب', 'location': 'لوکیشن',
            'sticker': 'استیکر', 'game': 'بازی', 'poll': 'نظرسنجی', 'link': 'لینک',
            'forward': 'فوروارد', 'gif': 'گیف', 'mention': 'منشن', 'hashtag': 'هشتگ',
            'english': 'زبان انگلیسی', 'text': 'متن', 'reply': 'ریپلای',
        }

        for field, lock_key in field_to_lock.items():
            if locks.get(lock_key) and message.get(field) is not None:
                return labels[lock_key]

        if locks.get('gif') and message.get('animation') is not None:
            return labels['gif']
        if locks.get('forward') and (message.get('forward_from') or message.get('forward_from_chat')
                                      or message.get('forward_sender_name')):
            return labels['forward']
        if locks.get('reply') and message.get('reply_to_message') is not None:
            return labels['reply']

        text = message.get('text') or message.get('caption') or ''
        if text != '':
            if locks.get('link') and Helpers.contains_link(text):
                return labels['link']
            if locks.get('mention') and '@' in text:
                return labels['mention']
            if locks.get('hashtag') and Helpers.contains_hashtag(text):
                return labels['hashtag']
            if locks.get('english') and Helpers.contains_english(text):
                return labels['english']

        # "قفل متن" — a catch-all silence lock: any plain text message (not a media
        # caption) is blocked outright, regardless of its content. Checked last so
        # the more specific labels above (link/mention/hashtag/...) win when they
        # also apply — the message is deleted either way.
        if locks.get('text') and message.get('text') is not None:
            return labels['text']

        return None

    @staticmethod
    def _is_flooding(chat_id: int, user_id: int, flood_settings: dict) -> bool:
        count = Database.bump_flood(chat_id, user_id, int(flood_settings['seconds']))
        return count > int(flood_settings['limit'])

    @staticmethod
    def _punish(chat_id: int, user_id: int, message: dict, group: dict, reason: str,
                mute_minutes: int = None) -> bool:
        """delete + warn escalation, shared by lock, badword & flood violations."""
        Telegram.delete_message(chat_id, int(message['message_id']))

        settings = group['settings']
        member = Database.get_member(chat_id, user_id)
        warns = int(member['warns']) + 1
        Database.set_warns(chat_id, user_id, warns)

        name = Helpers.full_name(message['from'])
        limit = int(settings['warn_limit'])

        if warns >= limit:
            FilterHandler._apply_warn_action(chat_id, user_id, settings['warn_action'], mute_minutes)
            Database.set_warns(chat_id, user_id, 0)
            action_text = {
                'ban': 'و از گروه حذف شد (بن) 🚫',
                'mute': (f"و به مدت {Helpers.human_time(mute_minutes)} سکوت شد 🔇"
                         if mute_minutes else 'و به مدت نامحدود سکوت شد 🔇'),
                'kick': 'و از گروه اخراج شد 👢',
            }.get(settings['warn_action'], '')
            Telegram.send_message(chat_id, Helpers.mention(user_id, name) + f" {reason}\n"
                                   + f"با این اخطار به سقف {limit} اخطار رسید {action_text}")
        else:
            Telegram.send_message(chat_id, Helpers.mention(user_id, name) + f" {reason}\n"
                                   + f"⚠️ اخطار {warns} از {limit}")

        return True

    @staticmethod
    def _apply_warn_action(chat_id: int, user_id: int, action: str, mute_minutes: int = None) -> None:
        if action == 'ban':
            Telegram.ban_chat_member(chat_id, user_id)
        elif action == 'kick':
            Telegram.kick_chat_member(chat_id, user_id)
        elif action == 'mute':
            Telegram.mute_user(chat_id, user_id, mute_minutes or 0)
