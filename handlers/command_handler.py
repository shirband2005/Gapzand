# -*- coding: utf-8 -*-
import re

from core.database import Database
from core.helpers import Helpers
from core.telegram import Telegram
from handlers.fun_handler import FunHandler
from handlers.help_handler import HelpHandler

LOCK_LABELS = {
    'link': 'لینک', 'forward': 'فوروارد', 'sticker': 'استیکر', 'gif': 'گیف',
    'photo': 'عکس', 'video': 'ویدیو', 'voice': 'صدا', 'video_note': 'ویدیو-پیام',
    'audio': 'موزیک', 'document': 'فایل', 'contact': 'مخاطب', 'location': 'لوکیشن',
    'poll': 'نظرسنجی', 'game': 'بازی', 'mention': 'منشن', 'hashtag': 'هشتگ',
    'english': 'انگلیسی', 'edit': 'ادیت پیام',
}

# Persian command -> English command it's an alias for.
# Every command below can be typed in Persian OR English; both work identically.
FA_ALIASES = {
    'شروع': 'start',
    'راهنما': 'help',
    'شناسه': 'id',
    'قوانین': 'rules',
    'تنظیم_قوانین': 'setrules',
    'بن': 'ban',
    'آنبن': 'unban',
    'اخراج': 'kick',
    'سکوت': 'mute',
    'رفع_سکوت': 'unmute',
    'اخطار': 'warn',
    'حذف_اخطار': 'unwarn',
    'اخطارها': 'warns',
    'ادمین': 'promote',
    'عزل': 'demote',
    'پین': 'pin',
    'قفل': 'lock',
    'بازکردن_قفل': 'unlock',
    'لیست_قفل\u200cها': 'locks',
    'فقط_ادمین': 'onlyadmins',
    'ضدسرویس': 'antiservice',
    'کپچا': 'captcha',
    'خوشامد': 'welcome',
    'تنظیم_خوشامد': 'setwelcome',
    'خداحافظی': 'goodbye',
    'تنظیم_خداحافظی': 'setgoodbye',
    'افزودن_فیلتر': 'addbadword',
    'حذف_فیلتر': 'rembadword',
    'فیلترها': 'badwords',
    'سقف_اخطار': 'setwarnlimit',
    'اکشن_اخطار': 'warnaction',
    'ضدفلود': 'flood',
    'پنل': 'panel',
    'تنظیمات': 'settings',
    'ادمین\u200cها': 'admins',
    'سرگرمی': 'fun',
}

ADMIN_ONLY = {
    'ban', 'unban', 'mute', 'unmute', 'kick', 'warn', 'unwarn', 'warns', 'setrules', 'pin', 'unpin',
    'lock', 'unlock', 'locks', 'panel', 'promote', 'demote', 'setwelcome', 'setgoodbye', 'welcome',
    'goodbye', 'addbadword', 'rembadword', 'badwords', 'setwarnlimit', 'warnaction', 'flood',
    'onlyadmins', 'captcha', 'antiservice', 'settings',
}


class CommandHandler:
    """Port of handlers/CommandHandler.php."""

    @staticmethod
    def is_persian_command_text(text: str) -> bool:
        """
        برای دستورات فارسی نیازی به / نیست؛ اگه اولین کلمه‌ی متن دقیقاً یکی از
        دستورات فارسیه، به‌عنوان دستور شناخته می‌شه. دستورات انگلیسی همچنان به / نیاز دارن.
        """
        text = (text or '').strip()
        if text == '' or text[0] == '/':
            return False
        first = text.split(' ', 1)[0].lower()
        return first in FA_ALIASES

    @staticmethod
    def handle(message: dict, group: dict) -> None:
        # Late import to avoid a circular import with panel_handler (which imports CommandHandler indirectly)
        from handlers.panel_handler import PanelHandler

        chat_id = int(message['chat']['id'])
        user_id = int(message['from']['id'])
        text = message['text'].strip()

        cmd, arg_line = CommandHandler._split_command(text)
        cmd = FA_ALIASES.get(cmd, cmd)  # فارسی -> معادل انگلیسی داخلی
        args = re.split(r'\s+', arg_line) if arg_line != '' else []
        arg1 = args[0] if args else None

        if cmd in ADMIN_ONLY and not Helpers.is_group_admin(chat_id, user_id):
            return  # silently ignore - avoid noisy "you're not admin" spam

        if cmd in ('start', 'help'):
            CommandHandler._help(chat_id, message['chat']['type'])

        elif cmd == 'id':
            CommandHandler._send_id(message)

        elif cmd == 'rules':
            r = group['settings']['rules']
            Telegram.send_message(chat_id, r if r != '' else 'هنوز قوانینی برای این گروه ثبت نشده.')

        elif cmd == 'setrules':
            def _mut(s):
                s['rules'] = arg_line
            CommandHandler._update_settings(chat_id, group, _mut)
            Telegram.send_message(chat_id, '✅ قوانین گروه ذخیره شد.')

        elif cmd == 'ban':
            CommandHandler._mod_action(message, group, 'ban')
        elif cmd == 'unban':
            CommandHandler._mod_action(message, group, 'unban')
        elif cmd == 'kick':
            CommandHandler._mod_action(message, group, 'kick')
        elif cmd == 'mute':
            CommandHandler._mod_action(message, group, 'mute')
        elif cmd == 'unmute':
            CommandHandler._mod_action(message, group, 'unmute')

        elif cmd == 'warn':
            CommandHandler._warn_user(message, group)
        elif cmd == 'unwarn':
            CommandHandler._unwarn_user(message, group)
        elif cmd == 'warns':
            CommandHandler._show_warns(message, group)

        elif cmd == 'promote':
            CommandHandler._promote(message, chat_id)
        elif cmd == 'demote':
            CommandHandler._demote(message, chat_id)

        elif cmd == 'pin':
            if 'reply_to_message' in message:
                Telegram.pin_chat_message(chat_id, int(message['reply_to_message']['message_id']))
                Telegram.send_message(chat_id, '📌 پیام پین شد.')

        elif cmd == 'lock':
            CommandHandler._toggle_lock(chat_id, group, arg1, True)
        elif cmd == 'unlock':
            CommandHandler._toggle_lock(chat_id, group, arg1, False)
        elif cmd == 'locks':
            CommandHandler._list_locks(chat_id, group)

        elif cmd == 'onlyadmins':
            CommandHandler._toggle_flag(chat_id, group, 'only_admins', arg1, 'فقط پیام ادمین\u200cها', 'فقط_ادمین')
        elif cmd == 'antiservice':
            CommandHandler._toggle_flag(chat_id, group, 'antiservice', arg1, 'حذف پیام\u200cهای ورود/خروج', 'ضدسرویس')
        elif cmd == 'captcha':
            CommandHandler._toggle_captcha(chat_id, group, arg1)

        elif cmd == 'welcome':
            CommandHandler._toggle_flag(chat_id, group, 'welcome.enabled', arg1, 'پیام خوش\u200cآمد', 'خوشامد')
        elif cmd == 'setwelcome':
            def _mut(s):
                s['welcome']['text'] = arg_line
            CommandHandler._update_settings(chat_id, group, _mut)
            Telegram.send_message(chat_id, "✅ پیام خوش\u200cآمد ذخیره شد.\nمتغیرها: {mention} {name} {group} {id}")

        elif cmd == 'goodbye':
            CommandHandler._toggle_flag(chat_id, group, 'goodbye.enabled', arg1, 'پیام خداحافظی', 'خداحافظی')
        elif cmd == 'setgoodbye':
            def _mut(s):
                s['goodbye']['text'] = arg_line
            CommandHandler._update_settings(chat_id, group, _mut)
            Telegram.send_message(chat_id, '✅ پیام خداحافظی ذخیره شد.')

        elif cmd == 'addbadword':
            if arg_line != '':
                def _mut(s):
                    if arg_line not in s['badwords']:
                        s['badwords'].append(arg_line)
                CommandHandler._update_settings(chat_id, group, _mut)
                Telegram.send_message(chat_id, f"✅ «{arg_line}» به لیست کلمات فیلتر اضافه شد.")
        elif cmd == 'rembadword':
            if arg_line != '':
                def _mut(s):
                    s['badwords'] = [w for w in s['badwords'] if w != arg_line]
                CommandHandler._update_settings(chat_id, group, _mut)
                Telegram.send_message(chat_id, f"✅ «{arg_line}» از لیست حذف شد.")
        elif cmd == 'badwords':
            lst = group['settings']['badwords']
            Telegram.send_message(chat_id, "🚫 کلمات فیلتر:\n" + '، '.join(lst) if lst else 'لیست فیلتر خالی است.')

        elif cmd == 'setwarnlimit':
            if arg1 and arg1.isdigit():
                def _mut(s):
                    s['warn_limit'] = int(arg1)
                CommandHandler._update_settings(chat_id, group, _mut)
                Telegram.send_message(chat_id, f"✅ سقف اخطار روی {arg1} تنظیم شد.")
        elif cmd == 'warnaction':
            if arg1 in ('ban', 'mute', 'kick'):
                def _mut(s):
                    s['warn_action'] = arg1
                CommandHandler._update_settings(chat_id, group, _mut)
                Telegram.send_message(chat_id, f"✅ اکشن پس از پر شدن اخطارها: {arg1}")

        elif cmd == 'flood':
            CommandHandler._flood_settings(chat_id, group, args)

        elif cmd in ('panel', 'settings'):
            PanelHandler.send_group_panel_entry(chat_id, user_id, message['chat'].get('title') or '')

        elif cmd == 'admins':
            CommandHandler._list_admins(chat_id)

        elif cmd == 'fun':
            FunHandler.send_menu(chat_id)

    # ---------- helpers ----------

    @staticmethod
    def _split_command(text: str):
        parts = text.split(' ', 1)
        cmd = parts[0].lstrip('/')
        cmd = cmd.split('@')[0]
        cmd = cmd.lower()
        arg_line = parts[1].strip() if len(parts) > 1 else ''
        return cmd, arg_line

    @staticmethod
    def _update_settings(chat_id, group: dict, mutator) -> None:
        settings = group['settings']
        mutator(settings)
        Database.save_group_settings(chat_id, settings)

    @staticmethod
    def _help(chat_id, chat_type: str) -> None:
        HelpHandler.send_main(chat_id)

    @staticmethod
    def _send_id(message: dict) -> None:
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        text = f"🆔 آیدی گروه: <code>{chat_id}</code>\n🆔 آیدی شما: <code>{user_id}</code>"
        reply_from = (message.get('reply_to_message') or {}).get('from') or {}
        if reply_from.get('id') is not None:
            rid = reply_from['id']
            text += f"\n🆔 آیدی کاربر ریپلای‌شده: <code>{rid}</code>"
        Telegram.send_message(chat_id, text)

    @staticmethod
    def _mod_action(message: dict, group: dict, action: str) -> None:
        chat_id = int(message['chat']['id'])
        text = message['text'].strip()
        _, arg_line = CommandHandler._split_command(text)
        args = re.split(r'\s+', arg_line) if arg_line != '' else []
        is_reply = (message.get('reply_to_message') or {}).get('from', {}).get('id') is not None

        # when replying, the only arg (if any) is the duration; otherwise first arg is the target id
        target_id = (int(message['reply_to_message']['from']['id']) if is_reply
                     else Helpers.extract_target_user_id(message, args[0] if args else None))
        duration_arg = (args[0] if args else None) if is_reply else (args[1] if len(args) > 1 else None)

        if not target_id:
            Telegram.send_message(chat_id, 'روی پیام فرد مورد نظر ریپلای کن یا آیدی عددی بده.')
            return
        if Helpers.is_group_admin(chat_id, target_id):
            Telegram.send_message(chat_id, 'روی ادمین‌ها این دستور اجرا نمی‌شود.')
            return
        name = Helpers.target_name(message)

        if action == 'ban':
            Telegram.ban_chat_member(chat_id, target_id)
            Telegram.send_message(chat_id, "🚫 " + Helpers.mention(target_id, name) + ' از گروه بن شد.')
        elif action == 'unban':
            Telegram.unban_chat_member(chat_id, target_id)
            Telegram.send_message(chat_id, "✅ " + Helpers.mention(target_id, name) + ' آنبن شد.')
        elif action == 'kick':
            Telegram.kick_chat_member(chat_id, target_id)
            Telegram.send_message(chat_id, "👢 " + Helpers.mention(target_id, name) + ' از گروه اخراج شد.')
        elif action == 'mute':
            minutes = Helpers.parse_duration(duration_arg) or 0
            Telegram.mute_user(chat_id, target_id, minutes)
            dur = f'به مدت {Helpers.human_time(minutes)}' if minutes > 0 else 'به\u200cصورت نامحدود'
            Telegram.send_message(chat_id, "🔇 " + Helpers.mention(target_id, name) + f" {dur} سکوت شد.")
        elif action == 'unmute':
            Telegram.unmute_user(chat_id, target_id)
            Telegram.send_message(chat_id, "🔊 " + Helpers.mention(target_id, name) + ' از سکوت خارج شد.')

    @staticmethod
    def _warn_user(message: dict, group: dict) -> None:
        chat_id = int(message['chat']['id'])
        target_id = Helpers.extract_target_user_id(message, None)
        if not target_id:
            Telegram.send_message(chat_id, 'روی پیام فرد مورد نظر ریپلای کن.')
            return
        member = Database.get_member(chat_id, target_id)
        warns = int(member['warns']) + 1
        Database.set_warns(chat_id, target_id, warns)
        limit = int(group['settings']['warn_limit'])
        name = Helpers.target_name(message)

        if warns >= limit:
            action = group['settings']['warn_action']
            if action == 'ban':
                Telegram.ban_chat_member(chat_id, target_id)
            elif action == 'kick':
                Telegram.kick_chat_member(chat_id, target_id)
            elif action == 'mute':
                Telegram.mute_user(chat_id, target_id, 0)
            Database.set_warns(chat_id, target_id, 0)
            Telegram.send_message(chat_id, Helpers.mention(target_id, name) + f" به سقف {limit} اخطار رسید و {action} شد.")
        else:
            Telegram.send_message(chat_id, "⚠️ " + Helpers.mention(target_id, name) + f" اخطار گرفت ({warns}/{limit})")

    @staticmethod
    def _unwarn_user(message: dict, group: dict) -> None:
        chat_id = int(message['chat']['id'])
        target_id = Helpers.extract_target_user_id(message, None)
        if not target_id:
            return
        member = Database.get_member(chat_id, target_id)
        warns = max(0, int(member['warns']) - 1)
        Database.set_warns(chat_id, target_id, warns)
        Telegram.send_message(chat_id, "✅ یک اخطار از " + Helpers.mention(target_id, Helpers.target_name(message))
                               + f" کم شد. ({warns}/{group['settings']['warn_limit']})")

    @staticmethod
    def _show_warns(message: dict, group: dict) -> None:
        chat_id = int(message['chat']['id'])
        target_id = Helpers.extract_target_user_id(message, None) or int(message['from']['id'])
        member = Database.get_member(chat_id, target_id)
        Telegram.send_message(chat_id, f"⚠️ اخطارها: {member['warns']}/{group['settings']['warn_limit']}")

    @staticmethod
    def _promote(message: dict, chat_id: int) -> None:
        target_id = Helpers.extract_target_user_id(message, None)
        if not target_id:
            return
        Telegram.call('promoteChatMember', {
            'chat_id': chat_id, 'user_id': target_id,
            'can_delete_messages': True, 'can_restrict_members': True,
            'can_pin_messages': True, 'can_invite_users': True,
        })
        Telegram.send_message(chat_id, '⭐️ ' + Helpers.mention(target_id, Helpers.target_name(message)) + ' ادمین شد.')

    @staticmethod
    def _demote(message: dict, chat_id: int) -> None:
        target_id = Helpers.extract_target_user_id(message, None)
        if not target_id:
            return
        Telegram.call('promoteChatMember', {
            'chat_id': chat_id, 'user_id': target_id,
            'can_delete_messages': False, 'can_restrict_members': False,
            'can_pin_messages': False, 'can_invite_users': False,
        })
        Telegram.send_message(chat_id, '⬇️ ' + Helpers.mention(target_id, Helpers.target_name(message)) + ' از ادمینی برکنار شد.')

    @staticmethod
    def _toggle_lock(chat_id, group: dict, lock_type, value: bool) -> None:
        if not lock_type or lock_type not in LOCK_LABELS:
            Telegram.send_message(chat_id, 'نوع قفل نامعتبر است. لیست انواع را با «لیست_قفل‌ها» ببین.')
            return
        def _mut(s):
            s['locks'][lock_type] = value
        CommandHandler._update_settings(chat_id, group, _mut)
        label = LOCK_LABELS[lock_type]
        Telegram.send_message(chat_id, f"🔒 قفل «{label}» فعال شد." if value else f"🔓 قفل «{label}» غیرفعال شد.")

    @staticmethod
    def _list_locks(chat_id, group: dict) -> None:
        lines = []
        for key, label in LOCK_LABELS.items():
            on = bool(group['settings']['locks'].get(key))
            lines.append(('🔒' if on else '🔓') + f" {label} — <code>{key}</code>")
        Telegram.send_message(chat_id, "وضعیت قفل‌ها:\n" + "\n".join(lines)
                               + "\n\nبرای تغییر: «قفل نوع» یا «بازکردن_قفل نوع» بنویس")

    @staticmethod
    def _toggle_flag(chat_id, group: dict, path: str, arg, label: str, fa_cmd: str = '') -> None:
        value = CommandHandler._parse_on_off(arg)
        if value is None:
            cmd_name = fa_cmd if fa_cmd != '' else path
            Telegram.send_message(chat_id, f"استفاده: «{cmd_name} on» یا «{cmd_name} off»")
            return

        def _mut(s):
            keys = path.split('.')
            ref = s
            for k in keys[:-1]:
                ref = ref[k]
            ref[keys[-1]] = value
        CommandHandler._update_settings(chat_id, group, _mut)
        Telegram.send_message(chat_id, f"✅ {label} فعال شد." if value else f"❌ {label} غیرفعال شد.")

    @staticmethod
    def _toggle_captcha(chat_id, group: dict, arg) -> None:
        value = CommandHandler._parse_on_off(arg)
        if value is None:
            Telegram.send_message(chat_id, 'استفاده: «کپچا on» یا «کپچا off»')
            return

        def _mut(s):
            s['captcha']['enabled'] = value
        CommandHandler._update_settings(chat_id, group, _mut)
        Telegram.send_message(chat_id, '✅ تایید هویت اعضای جدید (کپچا) فعال شد.' if value else '❌ کپچا غیرفعال شد.')

    @staticmethod
    def _parse_on_off(arg):
        if arg is None:
            return None
        arg = arg.lower()
        if arg in ('on', 'روشن', 'فعال', '1'):
            return True
        if arg in ('off', 'خاموش', 'غیرفعال', '0'):
            return False
        return None

    @staticmethod
    def _flood_settings(chat_id, group: dict, args: list) -> None:
        if not args:
            f = group['settings']['flood']
            status = 'فعال' if f['enabled'] else 'غیرفعال'
            Telegram.send_message(chat_id, f"🌊 ضدفلود: {status}\nحد مجاز: {f['limit']} پیام در {f['seconds']} ثانیه\n"
                                   f"مدت سکوت: " + Helpers.human_time(int(f['mute_minutes']))
                                   + "\n\nتنظیم: «ضدفلود on/off» , «ضدفلود limit عدد» , «ضدفلود seconds عدد» , «ضدفلود mute عدد(دقیقه)»")
            return
        sub = args[0].lower()
        val = args[1] if len(args) > 1 else None

        def _mut(s):
            if sub == 'on':
                s['flood']['enabled'] = True
            elif sub == 'off':
                s['flood']['enabled'] = False
            elif sub == 'limit':
                if val and val.isdigit():
                    s['flood']['limit'] = int(val)
            elif sub == 'seconds':
                if val and val.isdigit():
                    s['flood']['seconds'] = int(val)
            elif sub == 'mute':
                if val and val.isdigit():
                    s['flood']['mute_minutes'] = int(val)
        CommandHandler._update_settings(chat_id, group, _mut)
        Telegram.send_message(chat_id, '✅ تنظیمات ضدفلود بروزرسانی شد.')

    @staticmethod
    def _list_admins(chat_id) -> None:
        admins = Telegram.get_chat_administrators(chat_id)
        lines = ['• ' + Helpers.mention(int(a['user']['id']), Helpers.full_name(a['user'])) for a in admins]
        Telegram.send_message(chat_id, "👮‍♂️ ادمین‌های گروه:\n" + "\n".join(lines))
