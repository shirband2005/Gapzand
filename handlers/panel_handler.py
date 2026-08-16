# -*- coding: utf-8 -*-
"""Port of handlers/PanelHandler.php — the inline-button admin panel (private-chat wizard)."""
import json
import re
import time
from datetime import datetime

from core.config import Config
from core.database import Database
from core.helpers import Helpers
from core.telegram import Telegram
from data.panel_data import MEDIA_ITEMS, CONFIRM_INFO, SYSTEM_ITEMS, NOT_IMPLEMENTED, WARN_ACTION_LABELS


class PanelHandler:

    # ---------- entry points ----------

    @staticmethod
    def send_group_panel_entry(chat_id: int, user_id: int, title: str) -> None:
        if not Helpers.is_group_admin(chat_id, user_id):
            return
        bot = Config.get('bot_username')
        pv_url = f"https://t.me/{bot}?start=panel_{chat_id}"

        keyboard = [
            [{'text': '🌐 ورود به داشبورد پیشرفته', 'callback_data': f'pnl|web_soon|{chat_id}|'}],
            [
                {'text': '📱 تنظیمات در گروه', 'callback_data': f'pnl|open_group|{chat_id}|'},
                {'text': '📱 تنظیمات در پیوی', 'url': pv_url},
            ],
            [{'text': '❌ بستن پیام', 'callback_data': f'pnl|close|{chat_id}|'}],
        ]

        text = (
            "⚙️ <b>پنل مدیریت گروه</b>\n"
            "مدیر عزیز، برای اعمال تنظیمات محیط دلخواه خود را انتخاب کنید:\n\n"
            "🌐 <b>داشبورد پیشرفته (وب):</b>\n"
            "به‌زودی اضافه می‌شود.\n\n"
            "📱 <b>پنل سریع:</b>\n"
            "دسترسی سریع و کامل برای تغییرات لحظه‌ای، همین‌جا در گروه یا در پی‌وی ربات.\n\n"
            "یکی از گزینه‌های زیر را لمس کنید 👇"
        )

        PanelHandler._render(chat_id, None, text, keyboard)

    @staticmethod
    def open_from_deep_link(private_chat_id: int, user_id: int, payload: str, admin_name: str = '') -> None:
        # payload like "panel_-1001234567890"
        if not payload.startswith('panel_'):
            return
        group_id = int(payload[6:] or 0)
        if not Helpers.is_group_admin(group_id, user_id):
            Telegram.send_message(private_chat_id, '⛔️ شما ادمین آن گروه نیستید یا دسترسی تایید نشد.')
            return
        Database.clear_pending_input(user_id)  # fresh session -> drop any stale edit-in-progress
        PanelHandler._render_main(private_chat_id, None, group_id, admin_name)

    @staticmethod
    def maybe_handle_text_input(message: dict) -> bool:
        """
        Call this first for every private-chat text message. If the admin has
        a pending panel edit (welcome text, rules, a bad word, ...), this
        consumes the message, applies it, and re-renders the right screen.
        Returns False if there was nothing pending, so the caller should keep
        processing the message as usual.
        """
        user_id = int((message.get('from') or {}).get('id') or 0)
        if user_id == 0:
            return False
        pending = Database.get_pending_input(user_id)
        if not pending:
            return False

        chat_id = int(message['chat']['id'])
        text = (message.get('text') or '').strip()

        # ⏱ every panel prompt gives the admin 2 minutes; past that, auto-cancel.
        created_at = pending.get('created_at')
        created_ts = int(created_at.timestamp()) if hasattr(created_at, 'timestamp') else 0
        if created_ts and (int(time.time()) - created_ts) > 120:
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⏰ زمان شما (۲ دقیقه) به پایان رسید. لطفاً دوباره از منو اقدام کنید.')
            return True

        if text in ('/cancel', 'لغو', '/لغو'):
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '❌ لغو شد.')
            return True

        if pending['field'] == 'force_join_add':
            # its own flow: accepts a forward (no text) as well as a plain text id,
            # so it can't go through the generic empty-text bail below.
            return PanelHandler._handle_force_join_add_input(message, pending, user_id, chat_id)

        if pending['field'] == 'welcome_media':
            # accepts a photo/gif, not text — own flow, own validation.
            return PanelHandler._handle_welcome_media_input(message, pending, user_id, chat_id)

        if pending['field'] == 'goodbye_media':
            # accepts a photo/gif, not text — own flow, own validation.
            return PanelHandler._handle_goodbye_media_input(message, pending, user_id, chat_id)

        if pending['field'] in ('welcome_button_title', 'welcome_button_url'):
            # two-step flow (1/2 title, 2/2 link) — unlimited buttons, own validation/retry loop.
            return PanelHandler._handle_welcome_button_input(message, pending, user_id, chat_id)

        if text == '':
            Telegram.send_message(chat_id, 'یه پیام متنی بفرست، یا برای انصراف بنویس: لغو')
            return True

        group_id = int(pending['group_id'])
        if not Helpers.is_group_admin(group_id, user_id):
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⛔️ دیگه ادمین اون گروه نیستی، عملیات لغو شد.')
            return True

        group = Database.get_group(group_id)
        settings = group['settings']

        field = pending['field']
        if field == 'welcome_text':
            settings['welcome']['text'] = text[:500]
        elif field == 'goodbye_text':
            settings['goodbye']['text'] = text[:500]
        elif field == 'rules_text':
            settings['rules'] = text[:3000]
        elif field == 'badword_add':
            words = [w.strip() for w in re.split(r'[,،\n]+', text) if w.strip()]
            for w in words:
                if w != '' and w not in settings['badwords']:
                    settings['badwords'].append(w)
        else:
            Database.clear_pending_input(user_id)
            return True

        Database.save_group_settings(group_id, settings)
        Database.clear_pending_input(user_id)

        message_id = int(pending['message_id'])
        origin = pending['origin']
        if origin == 'badwords':
            PanelHandler._render_badwords(chat_id, message_id, group_id, settings)
        elif origin == 'welcome':
            PanelHandler._render_welcome(chat_id, message_id, group_id, settings)
        elif origin == 'goodbye':
            PanelHandler._render_goodbye(chat_id, message_id, group_id, settings)
        else:
            PanelHandler._render_system(chat_id, message_id, group_id, settings)
        Telegram.send_message(chat_id, '✅ ذخیره شد.')
        return True

    # ---------- callback dispatcher ----------

    @staticmethod
    def handle_callback(cq: dict) -> None:
        data = cq['data']  # pnl|action|groupId|extra
        parts = data.split('|')
        if parts[0] != 'pnl':
            return
        parts = (parts + ['', '', '', ''])[:4]
        _, action, group_id_str, extra = parts
        group_id = int(group_id_str or 0)
        user_id = int(cq['from']['id'])
        private_chat_id = int(cq['message']['chat']['id'])
        message_id = int(cq['message']['message_id'])

        if not Helpers.is_group_admin(group_id, user_id):
            Telegram.answer_callback_query(cq['id'], 'دسترسی نداری.', True)
            return

        group = Database.get_group(group_id)
        settings = group['settings']

        if action == 'open_group':
            Database.clear_pending_input(user_id)
            PanelHandler._render_main(private_chat_id, message_id, group_id, Helpers.full_name(cq['from']))

        elif action == 'web_soon':
            Telegram.answer_callback_query(cq['id'], '🌐 داشبورد پیشرفته (وب) به‌زودی اضافه می‌شود.', True)
            return

        elif action == 'ns':  # generic "not supported yet" toast — no state change, no re-render
            label = NOT_IMPLEMENTED.get(extra, 'این بخش')
            Telegram.answer_callback_query(cq['id'], f"🚧 {label} به‌زودی تکمیل می‌شود.", True)
            return

        elif action == 'main':
            Database.clear_pending_input(user_id)
            PanelHandler._render_main(private_chat_id, message_id, group_id, Helpers.full_name(cq['from']))

        elif action == 'security':
            PanelHandler._render_security(private_chat_id, message_id, group_id, settings)

        elif action in ('media', 'locks'):  # 'locks' = legacy callback alias, kept so old messages still work
            PanelHandler._render_media(private_chat_id, message_id, group_id, settings)

        elif action == 'system':
            PanelHandler._render_system(private_chat_id, message_id, group_id, settings)

        elif action == 'welcome':
            PanelHandler._render_welcome(private_chat_id, message_id, group_id, settings)

        elif action == 'goodbye':
            PanelHandler._render_goodbye(private_chat_id, message_id, group_id, settings)

        elif action == 'w_media':
            PanelHandler._start_text_input(private_chat_id, message_id, group_id, user_id, 'welcome_media', 'welcome',
                                            "🖼 <b>افزودن تصویر/گیف به پیام خوش‌آمد</b>\n\nیک عکس یا گیف بفرست.\n\nبرای انصراف بنویس: لغو")

        elif action == 'w_media_clear':
            settings['welcome']['media'] = {'type': None, 'file_id': None}
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_welcome(private_chat_id, message_id, group_id, settings)

        elif action == 'w_button':
            PanelHandler._start_text_input(
                private_chat_id, message_id, group_id, user_id, 'welcome_button_title', 'welcome',
                "➕ <b>افزودن دکمه سفارشی (مرحله ۱ از ۲)</b>\n\n"
                "لطفاً عنوان دکمه را ارسال کنید.\n"
                "مثال: وبسایت رسمی\n\n"
                "⏱ شما ۲ دقیقه فرصت دارید.\n"
                "❌ برای لغو، دستور «لغو» را ارسال کنید.")

        elif action == 'w_button_clear':
            idx = int(extra or -1)
            buttons = settings['welcome'].get('buttons') or []
            if 0 <= idx < len(buttons):
                del buttons[idx]
                Database.save_group_settings(group_id, settings)
            PanelHandler._render_welcome(private_chat_id, message_id, group_id, settings)

        elif action == 'w_preview':
            PanelHandler._send_welcome_preview(private_chat_id, group_id, settings, cq['from'], group.get('title') or str(group_id))
            Telegram.answer_callback_query(cq['id'], '📤 پیش‌نمایش برات ارسال شد.')
            return

        elif action == 'g_media':
            PanelHandler._start_text_input(private_chat_id, message_id, group_id, user_id, 'goodbye_media', 'goodbye',
                                            "🖼 <b>افزودن تصویر/گیف به پیام خداحافظی</b>\n\nیک عکس یا گیف بفرست.\n\nبرای انصراف بنویس: لغو")

        elif action == 'g_media_clear':
            settings['goodbye']['media'] = {'type': None, 'file_id': None}
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_goodbye(private_chat_id, message_id, group_id, settings)

        elif action == 'g_preview':
            PanelHandler._send_goodbye_preview(private_chat_id, group_id, settings, cq['from'], group.get('title') or str(group_id))
            Telegram.answer_callback_query(cq['id'], '📤 پیش‌نمایش برات ارسال شد.')
            return

        elif action == 'lists':
            PanelHandler._render_lists(private_chat_id, message_id, group_id, settings)

        elif action == 'backup':
            PanelHandler._render_backup(private_chat_id, message_id, group_id)

        elif action == 'status':
            PanelHandler._render_status(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'stat_v':
            PanelHandler._render_status(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']), extra or 'today')

        elif action == 'warns_list':
            PanelHandler._render_warns_list(private_chat_id, message_id, group_id)

        elif action == 'admins_list':
            PanelHandler._render_admins_list(private_chat_id, message_id, group_id)

        elif action == 'toggle_lock':
            settings['locks'][extra] = not settings['locks'].get(extra, False)
            Database.save_group_settings(group_id, settings)
            if extra == 'game':
                PanelHandler._render_system(private_chat_id, message_id, group_id, settings)
            else:
                PanelHandler._render_media(private_chat_id, message_id, group_id, settings)

        elif action == 'lock_confirm':  # opens the "are you sure?" screen for a CONFIRM_INFO-backed toggle
            store, key = (extra.split(':', 1) + [''])[:2]
            PanelHandler._render_lock_confirm(private_chat_id, message_id, group_id, settings, store, key)

        elif action == 'lock_confirm_yes':  # user tapped "بله" — actually flip the setting now
            store, key = (extra.split(':', 1) + [''])[:2]
            if store == 'path':
                PanelHandler._toggle_path(settings, key)
            elif key != '':
                settings['locks'][key] = not settings['locks'].get(key, False)
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_media(private_chat_id, message_id, group_id, settings)

        elif action == 'tg':  # generic toggle: extra = "screen:dotted.path"
            screen, path = (extra.split(':', 1) + [''])[:2]
            PanelHandler._toggle_path(settings, path)
            Database.save_group_settings(group_id, settings)
            if screen == 'media':
                PanelHandler._render_media(private_chat_id, message_id, group_id, settings)
            elif screen == 'system':
                PanelHandler._render_system(private_chat_id, message_id, group_id, settings)
            elif screen == 'security':
                PanelHandler._render_security(private_chat_id, message_id, group_id, settings)
            elif screen == 'welcome':
                PanelHandler._render_welcome(private_chat_id, message_id, group_id, settings)
            elif screen == 'goodbye':
                PanelHandler._render_goodbye(private_chat_id, message_id, group_id, settings)
            else:
                PanelHandler._render_main(private_chat_id, message_id, group_id, Helpers.full_name(cq['from']))

        # ---- auto-delete timer (welcome/goodbye): extra = "welcome" or "goodbye", except ad_set which is "screen:seconds" ----
        elif action in ('ad_dec', 'ad_inc'):
            screen = extra  # 'welcome' | 'goodbye'
            if 'auto_delete_seconds' not in settings.get(screen, {}):
                pass
            else:
                cur = int(settings[screen]['auto_delete_seconds'])
                cur += 5 if action == 'ad_inc' else -5
                settings[screen]['auto_delete_seconds'] = max(5, min(21600, cur))
                Database.save_group_settings(group_id, settings)
                if screen == 'goodbye':
                    PanelHandler._render_goodbye(private_chat_id, message_id, group_id, settings)
                else:
                    PanelHandler._render_welcome(private_chat_id, message_id, group_id, settings)

        elif action == 'ad_set':  # extra = "screen:seconds"
            screen, sec_str = (extra.split(':', 1) + [''])[:2]
            if 'auto_delete_seconds' not in settings.get(screen, {}):
                pass
            else:
                settings[screen]['auto_delete_seconds'] = max(5, min(21600, int(sec_str or 0)))
                Database.save_group_settings(group_id, settings)
                if screen == 'goodbye':
                    PanelHandler._render_goodbye(private_chat_id, message_id, group_id, settings)
                else:
                    PanelHandler._render_welcome(private_chat_id, message_id, group_id, settings)

        elif action == 'ad_noop':  # tap on the middle "X ثانیه/دقیقه" label — just a display, no state change
            screen = extra
            secs = int(settings.get(screen, {}).get('auto_delete_seconds') or 10)
            Telegram.answer_callback_query(cq['id'], '⏱ ' + PanelHandler._format_duration(secs) + ' بعد از ارسال حذف می‌شود.')
            return

        elif action == 'cycle_warnaction':
            order = ['ban', 'mute', 'kick']
            cur = order.index(settings['warn_action']) if settings['warn_action'] in order else -1
            settings['warn_action'] = order[(0 if cur == -1 else cur + 1) % len(order)]
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_security(private_chat_id, message_id, group_id, settings)

        elif action == 'flood_limit':
            settings['flood']['limit'] = PanelHandler._cycle_number(int(settings['flood']['limit']), [3, 5, 6, 8, 10, 15])
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_security(private_chat_id, message_id, group_id, settings)

        elif action == 'flood_mute':
            settings['flood']['mute_minutes'] = PanelHandler._cycle_number(int(settings['flood']['mute_minutes']), [5, 10, 15, 30, 60])
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_security(private_chat_id, message_id, group_id, settings)

        elif action == 'warn_limit':
            settings['warn_limit'] = PanelHandler._cycle_number(int(settings['warn_limit']), [1, 2, 3, 4, 5])
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_security(private_chat_id, message_id, group_id, settings)

        elif action == 'edit_welcome':
            PanelHandler._start_text_input(
                private_chat_id, message_id, group_id, user_id, 'welcome_text', 'welcome',
                "✏️ <b>ویرایش متن خوشامدگویی</b>\n\n"
                "لطفاً متن جدید را به همراه جایگزین‌های {user} و {group} در گروه ارسال کنید.\n"
                "مثال:\n🎉 سلام {user} جان! به {group} خوش اومدی\n\n"
                "💡 جایگزین‌های بیشتر ({inviter}, {date}, {time}, {username} و ...) در صفحه‌ی پیام خوش‌آمدگویی لیست شده‌اند.\n\n"
                "⏱ شما ۲ دقیقه فرصت دارید.\n"
                "❌ برای لغو، دستور «لغو» را ارسال کنید یا روی دکمه زیر کلیک کنید.")

        elif action == 'edit_goodbye':
            PanelHandler._start_text_input(
                private_chat_id, message_id, group_id, user_id, 'goodbye_text', 'goodbye',
                "✏️ <b>ویرایش متن خداحافظی</b>\n\n"
                "لطفاً متن جدید را به همراه جایگزین‌های {user} و {group} در گروه ارسال کنید.\n"
                "مثال:\nخداحافظ {user} جان! امیدواریم به {group} بازگردی 🎉\n\n"
                "💡 جایگزین‌های بیشتر ({date}, {time}, {username} و ...) در صفحه‌ی پیام خداحافظی لیست شده‌اند.\n\n"
                "⏱ شما ۲ دقیقه فرصت دارید.\n"
                "❌ برای لغو، دستور «لغو» را ارسال کنید یا روی دکمه زیر کلیک کنید.")

        elif action == 'edit_rules':
            PanelHandler._start_text_input(private_chat_id, message_id, group_id, user_id, 'rules_text', 'system',
                                            "📜 <b>ویرایش قوانین گروه</b>\n\nمتن جدید قوانین رو بفرست.\n\nبرای انصراف بنویس: لغو")

        elif action == 'badwords':
            PanelHandler._render_badwords(private_chat_id, message_id, group_id, settings)

        elif action == 'badword_add':
            PanelHandler._start_text_input(private_chat_id, message_id, group_id, user_id, 'badword_add', 'badwords',
                                            "➕ <b>افزودن کلمه ممنوعه</b>\n\nکلمه یا کلمه‌ها رو بفرست (برای چند کلمه با کاما یا خط جدید جدا کن).\n\nبرای انصراف بنویس: لغو")

        elif action == 'badword_del':
            idx = int(extra or -1)
            if 0 <= idx < len(settings['badwords']):
                del settings['badwords'][idx]
                Database.save_group_settings(group_id, settings)
            PanelHandler._render_badwords(private_chat_id, message_id, group_id, settings)

        elif action == 'badword_clear':
            settings['badwords'] = []
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_badwords(private_chat_id, message_id, group_id, settings)

        elif action == 'cancel_input':
            Database.clear_pending_input(user_id)
            if extra == 'badwords':
                PanelHandler._render_badwords(private_chat_id, message_id, group_id, settings)
            elif extra == 'force_join':
                PanelHandler._render_force_join(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))
            elif extra == 'welcome':
                PanelHandler._render_welcome(private_chat_id, message_id, group_id, settings)
            else:
                PanelHandler._render_system(private_chat_id, message_id, group_id, settings)

        elif action == 'force_join':
            PanelHandler._render_force_join(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'fj_toggle':
            if not settings['force_join'].get('enabled') and Database.count_force_join_channels(group_id) == 0:
                Telegram.answer_callback_query(cq['id'], '⚠️ ابتدا حداقل یک کانال اضافه کنید، سپس قفل را فعال نمایید.', True)
                return
            settings['force_join']['enabled'] = not settings['force_join'].get('enabled', False)
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_force_join(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'fj_add':
            if Database.count_force_join_channels(group_id) >= 10:
                Telegram.answer_callback_query(cq['id'], '⚠️ به سقف ۱۰ کانال برای جوین اجباری رسیدید.', True)
                return
            PanelHandler._start_text_input(
                private_chat_id, message_id, group_id, user_id, 'force_join_add', 'force_join',
                "🔧 <b>افزودن کانال جدید برای جوین اجباری</b>\n\n"
                "لطفاً یکی از روش‌های زیر را انتخاب کنید:\n\n"
                "1️⃣ ارسال آیدی عمومی کانال (مثل @UnlimitedNewsIR)\n"
                "2️⃣ فوروارد کردن یک پیام از آن کانال به همین گروه\n\n"
                "✨ <b>توصیه:</b> اگر از آیدی کانال مطمئن نیستید یا با خطا مواجه می‌شوید، حتماً از روش فوروارد استفاده کنید.\n\n"
                "⏰ شما ۲ دقیقه فرصت دارید.\n"
                "❌ برای لغو، روی دکمه زیر کلیک کنید یا دستور «لغو» را ارسال کنید.")

        elif action == 'fj_del':
            Database.remove_force_join_channel(group_id, int(extra or 0))
            PanelHandler._render_force_join(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'char_limit':
            PanelHandler._render_char_limit(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'cl_toggle':
            if not settings['char_limit'].get('enabled') and int(settings['char_limit'].get('max') or 0) <= 0:
                Telegram.answer_callback_query(cq['id'], '⚠️ ابتدا تعداد کاراکتر مجاز را مشخص کنید، سپس قفل را فعال نمایید.', True)
                return
            settings['char_limit']['enabled'] = not settings['char_limit'].get('enabled', False)
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_char_limit(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'cl_step':
            cur = int(settings['char_limit'].get('max') or 0)
            new = max(0, min(4096, cur + int(extra or 0)))
            settings['char_limit']['max'] = new
            if new <= 0:
                settings['char_limit']['enabled'] = False
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_char_limit(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'cl_set':
            settings['char_limit']['max'] = max(0, min(4096, int(extra or 0)))
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_char_limit(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'cl_info':
            mx = int(settings['char_limit'].get('max') or 0)
            Telegram.answer_callback_query(cq['id'], f"مقدار فعلی: {mx} کاراکتر" if mx > 0 else '⚠️ هنوز مقداری تنظیم نشده.', False)
            return

        elif action == 'force_add':
            PanelHandler._render_force_add(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'fa_toggle':
            if not settings['force_add'].get('enabled') and int(settings['force_add'].get('required') or 0) <= 0:
                Telegram.answer_callback_query(cq['id'], '⚠️ ابتدا تعداد مورد نیاز را مشخص کنید، سپس قفل را فعال نمایید.', True)
                return
            settings['force_add']['enabled'] = not settings['force_add'].get('enabled', False)
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_force_add(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'fa_step':
            cur = int(settings['force_add'].get('required') or 0)
            new = max(0, min(100, cur + int(extra or 0)))
            settings['force_add']['required'] = new
            if new <= 0:
                settings['force_add']['enabled'] = False
            Database.save_group_settings(group_id, settings)
            PanelHandler._render_force_add(private_chat_id, message_id, group_id, settings, group.get('title') or str(group_id), Helpers.full_name(cq['from']))

        elif action == 'fa_info':
            req = int(settings['force_add'].get('required') or 0)
            Telegram.answer_callback_query(cq['id'], f"مقدار فعلی: {req} نفر" if req > 0 else '⚠️ هنوز مقداری تنظیم نشده.', False)
            return

        elif action == 'close':
            Database.clear_pending_input(user_id)
            PanelHandler._render(private_chat_id, message_id,
                                  "✅ پنل مدیریت بسته شد.\nبرای باز کردن دوباره، داخل گروه بنویس: /panel", [])

        Telegram.answer_callback_query(cq['id'])

    # ---------- helpers ----------

    @staticmethod
    def _toggle_path(settings: dict, path: str) -> None:
        keys = path.split('.')
        ref = settings
        for k in keys[:-1]:
            if k not in ref:
                ref[k] = {}
            ref = ref[k]
        last = keys[-1]
        ref[last] = not ref.get(last, False)

    @staticmethod
    def _get_path(settings: dict, path: str) -> bool:
        ref = settings
        for k in path.split('.'):
            if not isinstance(ref, dict) or k not in ref:
                return False
            ref = ref[k]
        return bool(ref)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """"10 ثانیه" / "2 دقیقه" — used for the auto-delete timer label and toast."""
        if seconds >= 60 and seconds % 60 == 0:
            return f'{seconds // 60} دقیقه'
        return f'{seconds} ثانیه'

    @staticmethod
    def _auto_delete_rows(group_id: int, screen: str, seconds: int) -> list:
        """
        The two extra rows shown under "حذف خودکار" once it's toggled on, for both
        پیام خوش‌آمدگویی and پیام خداحافظی: a −5/label/+5 row, then quick-pick presets.
        `screen` is 'welcome' or 'goodbye' — used to route the callback to the right setting.
        """
        return [
            [
                {'text': '➖', 'callback_data': f'pnl|ad_dec|{group_id}|{screen}'},
                {'text': PanelHandler._format_duration(seconds), 'callback_data': f'pnl|ad_noop|{group_id}|{screen}'},
                {'text': '➕', 'callback_data': f'pnl|ad_inc|{group_id}|{screen}'},
            ],
            [
                {'text': '30 ثانیه', 'callback_data': f'pnl|ad_set|{group_id}|{screen}:30'},
                {'text': '1 دقیقه', 'callback_data': f'pnl|ad_set|{group_id}|{screen}:60'},
                {'text': '2 دقیقه', 'callback_data': f'pnl|ad_set|{group_id}|{screen}:120'},
                {'text': '5 دقیقه', 'callback_data': f'pnl|ad_set|{group_id}|{screen}:300'},
            ],
        ]

    @staticmethod
    def _cycle_number(current: int, steps: list) -> int:
        idx = steps.index(current) if current in steps else None
        if idx is None:
            return steps[0]
        return steps[(idx + 1) % len(steps)]

    @staticmethod
    def _handle_force_join_add_input(message: dict, pending: dict, user_id: int, chat_id: int) -> bool:
        """
        Consumes one message while an admin has "➕ افزودن کانال جدید" pending.
        Accepts either a forwarded message from the channel, or a plain-text
        public username/link. Always returns True (message is consumed either
        way — success, validation error, or expiry).
        """
        group_id = int(pending['group_id'])

        if not Helpers.is_group_admin(group_id, user_id):
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⛔️ دیگه ادمین اون گروه نیستی، عملیات لغو شد.')
            return True

        # 2-minute window, per the prompt shown when "افزودن کانال جدید" was tapped.
        created_at = pending.get('created_at')
        created_ts = int(created_at.timestamp()) if hasattr(created_at, 'timestamp') else 0
        if created_ts and (int(time.time()) - created_ts) > 120:
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⏰ زمان ۲ دقیقه‌ای به پایان رسید. اگه هنوز لازمه، دوباره روی «افزودن کانال جدید» بزن.')
            group = Database.get_group(group_id)
            PanelHandler._render_force_join(chat_id, None, group_id, group['settings'], group.get('title') or str(group_id), Helpers.full_name(message.get('from') or {}))
            return True

        cancel_hint = "\nبرای لغو بنویس: لغو"
        fw_chat = message.get('forward_from_chat')
        channel_id = None
        username = None
        title = None

        if fw_chat:
            if (fw_chat.get('type') or '') != 'channel':
                Telegram.send_message(chat_id, '❌ پیام فوروارد شده باید از یک کانال باشه، نه گروه یا چت دیگه.' + cancel_hint)
                return True
            channel_id = int(fw_chat['id'])
            username = fw_chat.get('username')
            title = fw_chat.get('title')
        else:
            text = (message.get('text') or '').strip()
            ref = PanelHandler._extract_channel_ref(text) if text != '' else None
            if ref is None:
                Telegram.send_message(chat_id,
                    "❌ این آیدی معتبر به نظر نمی‌رسه.\n"
                    "آیدی عمومی کانال رو بفرست (مثل @channel) یا یک پیام از اون کانال رو فوروارد کن." + cancel_hint)
                return True
            chat = Telegram.get_chat(ref)
            if not chat:
                Telegram.send_message(chat_id,
                    "❌ کانالی با این آیدی پیدا نشد یا ربات به اون دسترسی نداره.\n"
                    "✨ توصیه: از روش فوروارد کردن پیام استفاده کن." + cancel_hint)
                return True
            if (chat.get('type') or '') != 'channel':
                Telegram.send_message(chat_id, '❌ این آیدی متعلق به یک کانال نیست.' + cancel_hint)
                return True
            channel_id = int(chat['id'])
            username = chat.get('username')
            title = chat.get('title')

        bot_member = Telegram.get_chat_member(channel_id, Telegram.bot_id())
        bot_status = (bot_member or {}).get('status')
        if bot_status not in ('administrator', 'creator'):
            Telegram.send_message(chat_id,
                '⚠️ ربات باید ادمین کانال «' + Helpers.escape(str(title)) + '» باشه تا بتونه عضویت کاربرها رو بررسی کنه.'
                + "\nاول ربات رو تو اون کانال ادمین کن، بعد دوباره امتحان کن." + cancel_hint)
            return True

        if Database.count_force_join_channels(group_id) >= 10:
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⚠️ به سقف ۱۰ کانال برای جوین اجباری رسیدید.')
            group = Database.get_group(group_id)
            PanelHandler._render_force_join(chat_id, None, group_id, group['settings'], group.get('title') or str(group_id), Helpers.full_name(message.get('from') or {}))
            return True

        invite_link = None
        if not username:
            link = Telegram.export_chat_invite_link(channel_id)
            invite_link = link if isinstance(link, str) else None

        added = Database.add_force_join_channel(group_id, channel_id, username, title, invite_link, user_id)
        Database.clear_pending_input(user_id)

        Telegram.send_message(chat_id, ('✅ کانال «' + Helpers.escape(str(title)) + '» با موفقیت اضافه شد.') if added
                               else '⚠️ این کانال قبلاً به لیست اضافه شده بود.')

        group = Database.get_group(group_id)
        PanelHandler._render_force_join(chat_id, None, group_id, group['settings'], group.get('title') or str(group_id), Helpers.full_name(message.get('from') or {}))
        return True

    @staticmethod
    def _handle_welcome_media_input(message: dict, pending: dict, user_id: int, chat_id: int) -> bool:
        """Consumes one message while "🖼 افزودن تصویر/گیف" is pending — expects a photo or an animation (gif)."""
        group_id = int(pending['group_id'])
        if not Helpers.is_group_admin(group_id, user_id):
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⛔️ دیگه ادمین اون گروه نیستی، عملیات لغو شد.')
            return True

        file_id = None
        media_type = None
        if message.get('photo'):
            file_id = message['photo'][-1]['file_id']  # largest size is last
            media_type = 'photo'
        elif message.get('animation'):
            file_id = message['animation']['file_id']
            media_type = 'animation'

        if not file_id:
            Telegram.send_message(chat_id, '❌ لطفاً فقط یک عکس یا گیف بفرست.' + "\nبرای انصراف بنویس: لغو")
            return True

        group = Database.get_group(group_id)
        settings = group['settings']
        settings['welcome']['media'] = {'type': media_type, 'file_id': file_id}
        Database.save_group_settings(group_id, settings)
        Database.clear_pending_input(user_id)

        Telegram.send_message(chat_id, '✅ رسانه ذخیره شد.')
        PanelHandler._render_welcome(chat_id, None, group_id, settings)
        return True

    @staticmethod
    def _handle_goodbye_media_input(message: dict, pending: dict, user_id: int, chat_id: int) -> bool:
        """Consumes one message while "🖼 افزودن تصویر/گیف" (goodbye) is pending — expects a photo or an animation (gif)."""
        group_id = int(pending['group_id'])
        if not Helpers.is_group_admin(group_id, user_id):
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⛔️ دیگه ادمین اون گروه نیستی، عملیات لغو شد.')
            return True

        file_id = None
        media_type = None
        if message.get('photo'):
            file_id = message['photo'][-1]['file_id']  # largest size is last
            media_type = 'photo'
        elif message.get('animation'):
            file_id = message['animation']['file_id']
            media_type = 'animation'

        if not file_id:
            Telegram.send_message(chat_id, '❌ لطفاً فقط یک عکس یا گیف بفرست.' + "\nبرای انصراف بنویس: لغو")
            return True

        group = Database.get_group(group_id)
        settings = group['settings']
        settings['goodbye']['media'] = {'type': media_type, 'file_id': file_id}
        Database.save_group_settings(group_id, settings)
        Database.clear_pending_input(user_id)

        Telegram.send_message(chat_id, '✅ رسانه ذخیره شد.')
        PanelHandler._render_goodbye(chat_id, None, group_id, settings)
        return True

    @staticmethod
    def _handle_welcome_button_input(message: dict, pending: dict, user_id: int, chat_id: int) -> bool:
        """
        Consumes messages for the 2-step "➕ افزودن دکمه سفارشی" flow — unlimited buttons.
        Stage 1/2 ('welcome_button_title'): expects the button's title, then asks for the link.
        Stage 2/2 ('welcome_button_url'): expects the link, then appends the new button and saves.
        """
        group_id = int(pending['group_id'])
        if not Helpers.is_group_admin(group_id, user_id):
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '⛔️ دیگه ادمین اون گروه نیستی، عملیات لغو شد.')
            return True

        text = (message.get('text') or '').strip()
        if text == '':
            Telegram.send_message(chat_id, 'یه پیام متنی بفرست، یا برای انصراف بنویس: لغو')
            return True

        message_id = int(pending['message_id'])

        if pending['field'] == 'welcome_button_title':
            title = text[:40]
            Database.set_pending_input(user_id, group_id, 'welcome_button_url', 'welcome', message_id, title)

            keyboard = [[{'text': '❌ لغو عملیات', 'callback_data': f'pnl|cancel_input|{group_id}|welcome'}]]
            PanelHandler._render(
                chat_id, message_id,
                "➕ <b>افزودن دکمه سفارشی (مرحله ۲ از ۲)</b>\n\n"
                "لطفاً لینک دکمه را ارسال کنید (باید با http، https یا t.me شروع بشه).\n"
                "مثال: https://t.me/example\n\n"
                "⏱ شما ۲ دقیقه فرصت دارید.\n"
                "❌ برای لغو، دستور «لغو» را ارسال کنید یا روی دکمه زیر کلیک کنید.",
                keyboard)
            return True

        # stage 2/2 — 'welcome_button_url'
        btn_url = text
        if not re.match(r'^(https?://|tg://|t\.me/)', btn_url, re.IGNORECASE):
            Telegram.send_message(chat_id, "❌ لینک معتبر نیست. باید با http://، https:// یا t.me/ شروع بشه.\nدوباره بفرست یا برای انصراف بنویس: لغو")
            return True
        if btn_url.startswith('t.me/'):
            btn_url = 'https://' + btn_url

        btn_text = str(pending.get('payload') or '')
        if btn_text == '':
            Database.clear_pending_input(user_id)
            Telegram.send_message(chat_id, '❌ مشکلی پیش اومد، لطفاً دوباره از منو اقدام کن.')
            return True

        group = Database.get_group(group_id)
        settings = group['settings']
        settings['welcome'].setdefault('buttons', []).append({'text': btn_text, 'url': btn_url})
        Database.save_group_settings(group_id, settings)
        Database.clear_pending_input(user_id)

        Telegram.send_message(chat_id, '✅ دکمه ذخیره شد.')
        PanelHandler._render_welcome(chat_id, None, group_id, settings)
        return True

    @staticmethod
    def _send_welcome_preview(private_chat_id: int, group_id: int, settings: dict, admin_user: dict, group_title: str) -> None:
        """"📤 ارسال پیش‌نمایش" — sends the built welcome message to the admin's own private chat, using their own info as the new member."""
        from handlers.member_handler import MemberHandler
        built = MemberHandler.build_welcome_message(settings, admin_user, group_title, None, 0, group_id)
        extra = {'reply_markup': json.dumps(built['markup'])} if built['markup'] else {}

        if built['media']:
            if built['media']['type'] == 'animation':
                Telegram.send_animation(private_chat_id, built['media']['file_id'], built['text'], extra)
            else:
                Telegram.send_photo(private_chat_id, built['media']['file_id'], built['text'], extra)
        else:
            Telegram.send_message(private_chat_id, built['text'], extra)

    @staticmethod
    def _send_goodbye_preview(private_chat_id: int, group_id: int, settings: dict, admin_user: dict, group_title: str) -> None:
        """"📤 ارسال پیش‌نمایش" for the goodbye message — sends the built message to the admin's own private chat."""
        from handlers.member_handler import MemberHandler
        built = MemberHandler.build_goodbye_message(settings, admin_user, group_title)
        extra = {}

        if built['media']:
            if built['media']['type'] == 'animation':
                Telegram.send_animation(private_chat_id, built['media']['file_id'], built['text'], extra)
            else:
                Telegram.send_photo(private_chat_id, built['media']['file_id'], built['text'], extra)
        else:
            Telegram.send_message(private_chat_id, built['text'], extra)

    @staticmethod
    def _extract_channel_ref(text: str):
        """"@name", "name", "t.me/name", "https://t.me/name" -> "@name" for getChat(); None if not a plausible username."""
        text = text.strip()
        m = re.match(r'^(?:https?://)?t(?:elegram)?\.me/([A-Za-z][A-Za-z0-9_]{4,31})/?$', text, re.IGNORECASE)
        if m:
            return '@' + m.group(1)
        m = re.match(r'^@?([A-Za-z][A-Za-z0-9_]{4,31})$', text)
        if m:
            return '@' + m.group(1)
        return None

    @staticmethod
    def _start_text_input(chat_id: int, message_id: int, group_id: int, user_id: int,
                           field: str, origin: str, prompt: str) -> None:
        Database.set_pending_input(user_id, group_id, field, origin, message_id)
        keyboard = [[{'text': '❌ لغو عملیات', 'callback_data': f'pnl|cancel_input|{group_id}|{origin}'}]]
        PanelHandler._render(chat_id, message_id, prompt, keyboard)

    @staticmethod
    def _toggle_button(item: dict, group_id: int, settings: dict, screen: str) -> dict:
        """Builds one inline button for a MEDIA_ITEMS/SYSTEM_ITEMS entry."""
        label = item['label']

        if item['kind'] == 'lock':
            on = bool(settings['locks'].get(item['key']))
            icon = '🟢' if on else '🔴'
            return {'text': f'{icon} {label}', 'callback_data': f"pnl|toggle_lock|{group_id}|{item['key']}"}
        if item['kind'] == 'path':
            on = PanelHandler._get_path(settings, item['key'])
            icon = '🟢' if on else '🔴'
            return {'text': f'{icon} {label}', 'callback_data': f"pnl|tg|{group_id}|{screen}:{item['key']}"}
        if item['kind'] == 'confirm':
            on = PanelHandler._get_path(settings, item['key']) if item['store'] == 'path' else bool(settings['locks'].get(item['key']))
            icon = '🟢' if on else '🔴'
            return {'text': f'{icon} {label}', 'callback_data': f"pnl|lock_confirm|{group_id}|{item['store']}:{item['key']}"}
        # soon
        return {'text': f'🔴 {label}', 'callback_data': f"pnl|ns|{group_id}|{item['key']}"}

    @staticmethod
    def _count_active_tools(s: dict):
        """[active, total] across every real on/off toggle we actually have."""
        lock_keys = ['link', 'photo', 'video', 'gif', 'document', 'forward', 'sticker', 'hashtag',
                     'contact', 'voice', 'audio', 'video_note', 'location', 'profanity', 'english', 'game',
                     'mention', 'text', 'reply']
        active = sum(1 for k in lock_keys if bool(s['locks'].get(k)))
        path_keys = ['flood.enabled', 'welcome.enabled', 'goodbye.enabled', 'only_admins', 'captcha.enabled',
                     'antiservice', 'char_limit.enabled', 'force_add.enabled']
        active += sum(1 for p in path_keys if PanelHandler._get_path(s, p))
        return active, len(lock_keys) + len(path_keys)

    @staticmethod
    def _admin_lines(group_id: int) -> list:
        admins = Telegram.get_chat_administrators(group_id) or []
        lines = []
        for i, a in enumerate(admins):
            u = a.get('user') or {}
            name = ((u.get('first_name') or '') + ' ' + (u.get('last_name') or '')).strip() or ('کاربر ' + str(u.get('id') or ''))
            role = 'سازنده' if (a.get('status') or '') == 'creator' else 'ادمین'
            lines.append(f'{i + 1}. ' + Helpers.escape(name) + f' ({role})')
        return lines

    # ---------- screens ----------

    @staticmethod
    def _render_main(chat_id: int, message_id, group_id: int, admin_name: str = '') -> None:
        group = Database.get_group(group_id)
        title = group.get('title') or str(group_id)
        s = group['settings']

        active, total = PanelHandler._count_active_tools(s)
        now_str = datetime.now().strftime('%H:%M')

        keyboard = [
            [{'text': '🛡 امنیت و کنترل', 'callback_data': f'pnl|security|{group_id}|'}],
            [
                {'text': '🎮 رسانه و محتوا', 'callback_data': f'pnl|media|{group_id}|'},
                {'text': '⚙️ سیستم و دستورات', 'callback_data': f'pnl|system|{group_id}|'},
            ],
            [{'text': '📋 لیست‌ها و گزارشات', 'callback_data': f'pnl|lists|{group_id}|'}],
            [{'text': '🔧 کاستومایز کردن دستورات', 'callback_data': f'pnl|ns|{group_id}|customize'}],
            [{'text': '📁 مدیریت بکاپ و تمپلیت', 'callback_data': f'pnl|backup|{group_id}|'}],
            [{'text': '📊 آمار پیشرفته گروه', 'callback_data': f'pnl|status|{group_id}|'}],
            [{'text': '❌ بستن پنل', 'callback_data': f'pnl|close|{group_id}|'}],
        ]

        text = (
            "🎮 <b>مرکز فرماندهی گروه</b>\n"
            "――――――――――\n"
            "🏷 گروه: <b>" + Helpers.escape(title) + "</b>\n"
            + (f"👤 مدیر: " + Helpers.escape(admin_name) + f" {now_str}\n" if admin_name != '' else '')
            + f"📊 وضعیت سیستم: {active} ابزار فعال از {total}\n"
            "――――――――――\n"
            "بخش مورد نظر را انتخاب کنید:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_media(chat_id: int, message_id, group_id: int, s: dict) -> None:
        """🎮 رسانه و محتوا — content/media locks, 2 per row, green/red circle state."""
        keyboard = []
        row = []
        for item in MEDIA_ITEMS:
            row.append(PanelHandler._toggle_button(item, group_id, s, 'media'))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([{'text': '↩️ بازگشت به داشبورد', 'callback_data': f'pnl|main|{group_id}|'}])

        text = (
            "🎮 <b>رسانه و محتوا</b>\n"
            "کنترل دقیق روی محتوای گروه. با استفاده از این قفل‌ها مشخص کنید کاربران اجازه ارسال چه نوع فایل‌ها، رسانه‌ها و فرمت‌هایی را در چت دارند.\n\n"
            "وضعیت قفل‌ها را با دکمه‌های زیر تغییر دهید:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_lock_confirm(chat_id: int, message_id, group_id: int, settings: dict, store: str, key: str) -> None:
        """🔐 Rich "are you sure?" screen for a handful of sensitive toggles (see CONFIRM_INFO)."""
        info = CONFIRM_INFO.get(f'{store}:{key}')
        if info is None:
            PanelHandler._render_media(chat_id, message_id, group_id, settings)
            return

        label = key
        for item in MEDIA_ITEMS:
            if item.get('store') == store and item['key'] == key:
                label = item['label']
                break

        current = PanelHandler._get_path(settings, key) if store == 'path' else bool(settings['locks'].get(key))
        turning_on = not current
        command_icon = '🟢' if turning_on else '🔴'
        command_text = 'روشن‌کردن (فعال)' if turning_on else 'خاموش‌کردن (غیرفعال)'
        verb = 'فعال' if turning_on else 'غیرفعال'

        lines = [
            '🛡 <b>تاییدیه تغییرات سیستم</b>',
            '――――――――――',
            '',
            'تنظیمات مورد نظر:',
            f"🔷 <b>ابزار:</b> {info['icon']} " + Helpers.escape(label),
            f"🎯 <b>فرمان:</b> {command_icon} {command_text}",
            '',
            '💡 <b>توضیحات:</b>',
            f"{info['icon']} " + Helpers.escape(info['tagline']),
            '',
            Helpers.escape(info['paragraph']),
            info['why_header'],
        ]
        for item_title, item_desc in info['why_items']:
            lines.append('🔹 <b>' + Helpers.escape(item_title) + ':</b> ' + Helpers.escape(item_desc))
        lines.append('⚡ <b>واکنش ربات:</b> ' + Helpers.escape(info['reaction']))
        lines.append('――――――――――')
        lines.append('')
        lines.append('آیا از اعمال این تغییر اطمینان دارید؟')

        keyboard = [
            [{'text': f'✅ بله، {verb} کن', 'callback_data': f'pnl|lock_confirm_yes|{group_id}|{store}:{key}'}],
            [{'text': '❌ خیر، بازگشت', 'callback_data': f'pnl|media|{group_id}|'}],
        ]

        PanelHandler._render(chat_id, message_id, "\n".join(lines), keyboard)

    @staticmethod
    def _render_system(chat_id: int, message_id, group_id: int, s: dict) -> None:
        """⚙️ سیستم و دستورات — bot-wide switches, group lock, and the leveling/fun toggles."""
        def b(v):
            return '🟢' if v else '🔴'

        keyboard = [
            [{'text': f"{b(s['welcome']['enabled'])} پیام خوش‌آمدگویی", 'callback_data': f'pnl|welcome|{group_id}|'}],
            [{'text': f"{b(s['goodbye']['enabled'])} پیام خداحافظی", 'callback_data': f'pnl|goodbye|{group_id}|'}],
            [{'text': f"{b(s['only_admins'])} قفل گروه", 'callback_data': f'pnl|tg|{group_id}|system:only_admins'}],
        ]

        row = []
        for item in SYSTEM_ITEMS:
            row.append(PanelHandler._toggle_button(item, group_id, s, 'system'))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([{'text': '↩️ بازگشت به داشبورد', 'callback_data': f'pnl|main|{group_id}|'}])

        text = (
            "⚙️ <b>سیستم و دستورات</b>\n"
            "――――――――――\n\n"
            "💡 در این بخش می‌توانید ساختار کلی ربات، سیستم‌های کاربری (مثل لول‌بندی) و عملکردهای پایه گروه را پیکربندی کنید. این ابزارها برای مدیریت تعاملات و ایجاد جذابیت در گروه طراحی شده‌اند.\n\n"
            "🔽 وضعیت قفل‌ها را با دکمه‌های زیر تغییر دهید:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_welcome(chat_id: int, message_id, group_id: int, s: dict) -> None:
        """💬 پیام خوش‌آمدگویی — opened by tapping the row in ⚙️ سیستم و دستورات."""
        w = s['welcome']

        def b(v):
            return '🟢' if v else '🔴'

        media_line = 'هیچ رسانه‌ای تنظیم نشده است.' if not (w.get('media') or {}).get('file_id') \
            else ('تنظیم شده (' + ('گیف' if w['media']['type'] == 'animation' else 'عکس') + ')')

        buttons = [btn for btn in (w.get('buttons') or []) if btn.get('text') and btn.get('url')]
        button_count = len(buttons)
        if button_count == 0:
            button_line = 'هیچ دکمه‌ای تعریف نشده است.'
        else:
            lines = []
            for i, btn in enumerate(buttons):
                lines.append(f'{i + 1}. ' + Helpers.escape(btn['text']) + ' → ' + Helpers.escape(btn['url']))
            button_line = "\n".join(lines)

        text_preview = Helpers.escape(w['text'][:300])

        text = (
            "💬 <b>پیام خوش‌آمدگویی</b>\n"
            "――――――――――\n\n"
            "وضعیت: " + ('فعال 🟢' if w['enabled'] else 'غیرفعال 🔴') + "\n"
            "حذف خودکار: " + ('فعال 🟢' if w.get('auto_delete') else 'غیرفعال 🔴') + "\n"
            f"📎 رسانه: {media_line}\n\n"
            f"📝 متن:\n{text_preview}\n\n"
            "💡 <b>متغیرهای قابل استفاده:</b>\n"
            "• {user} → منشن کاربر جدید\n"
            "• {inviter} → منشن دعوت‌کننده (اگر وجود داشته باشد)\n"
            "• {inviter_invites_count} → تعداد کاربرانی که دعوت‌کننده تا کنون دعوت کرده\n"
            "• {group} → نام گروه\n"
            "• {date} → تاریخ شمسی\n"
            "• {time} → ساعت\n"
            "• {day_of_week} → نام روز هفته\n"
            "• {month_name} → نام ماه شمسی\n"
            "• {user_id} → شناسه عددی کاربر\n"
            "• {username} → یوزرنیم کاربر\n"
            "• {emoji} → ایموجی تصادفی\n\n"
            f"🔘 دکمه‌های سفارشی (بی‌نهایت، در حال حاضر {button_count} عدد):\n{button_line}"
        )

        keyboard = [
            [
                {'text': f"{b(w['enabled'])} فعال/غیرفعال", 'callback_data': f'pnl|tg|{group_id}|welcome:welcome.enabled'},
                {'text': '✏️ ویرایش متن', 'callback_data': f'pnl|edit_welcome|{group_id}|'},
            ],
            [{'text': f"{b(bool(w.get('show_rules_button')))} نمایش دکمه قوانین", 'callback_data': f'pnl|tg|{group_id}|welcome:welcome.show_rules_button'}],
        ]

        if not (w.get('media') or {}).get('file_id'):
            keyboard.append([{'text': '🖼 افزودن تصویر/گیف', 'callback_data': f'pnl|w_media|{group_id}|'}])
        else:
            keyboard.append([
                {'text': '🖼 افزودن تصویر/گیف', 'callback_data': f'pnl|w_media|{group_id}|'},
                {'text': '🗑 حذف رسانه', 'callback_data': f'pnl|w_media_clear|{group_id}|'},
            ])

        keyboard.append([{'text': '➕ افزودن دکمه سفارشی', 'callback_data': f'pnl|w_button|{group_id}|'}])
        for i, btn in enumerate(buttons):
            label = btn['text'][:30]
            keyboard.append([{'text': f'🗑 حذف: {label}', 'callback_data': f'pnl|w_button_clear|{group_id}|{i}'}])

        keyboard.append([{'text': f"{b(bool(w.get('auto_delete')))} حذف خودکار", 'callback_data': f'pnl|tg|{group_id}|welcome:welcome.auto_delete'}])
        if w.get('auto_delete'):
            for row in PanelHandler._auto_delete_rows(group_id, 'welcome', int(w.get('auto_delete_seconds') or 10)):
                keyboard.append(row)
        keyboard.append([{'text': '📤 ارسال پیش‌نمایش', 'callback_data': f'pnl|w_preview|{group_id}|'}])
        keyboard.append([{'text': '↩️ بازگشت به بخش سیستم', 'callback_data': f'pnl|system|{group_id}|'}])

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_goodbye(chat_id: int, message_id, group_id: int, s: dict) -> None:
        """👋 پیام خداحافظی — opened by tapping the row in ⚙️ سیستم و دستورات."""
        g = s['goodbye']

        def b(v):
            return '🟢' if v else '🔴'

        media_line = 'هیچ رسانه‌ای تنظیم نشده است.' if not (g.get('media') or {}).get('file_id') \
            else ('تنظیم شده (' + ('گیف' if g['media']['type'] == 'animation' else 'عکس') + ')')

        text_preview = Helpers.escape(g['text'][:300])

        text = (
            "👋 <b>پیام خداحافظی</b>\n"
            "――――――――――\n\n"
            "وضعیت: " + ('فعال 🟢' if g['enabled'] else 'غیرفعال 🔴') + "\n"
            "حذف خودکار: " + ('فعال 🟢' if g.get('auto_delete') else 'غیرفعال 🔴') + "\n"
            f"📎 رسانه: {media_line}\n\n"
            f"📝 متن:\n{text_preview}\n\n"
            "💡 <b>متغیرهای قابل استفاده:</b>\n"
            "• {user} → منشن کاربر خروج‌کننده\n"
            "• {group} → نام گروه\n"
            "• {date} → تاریخ شمسی\n"
            "• {time} → ساعت\n"
            "• {day_of_week} → نام روز هفته\n"
            "• {month_name} → نام ماه شمسی\n"
            "• {user_id} → شناسه عددی کاربر\n"
            "• {username} → یوزرنیم کاربر\n"
            "• {emoji} → ایموجی تصادفی"
        )

        keyboard = [
            [
                {'text': f"{b(g['enabled'])} فعال/غیرفعال", 'callback_data': f'pnl|tg|{group_id}|goodbye:goodbye.enabled'},
                {'text': '✏️ ویرایش متن', 'callback_data': f'pnl|edit_goodbye|{group_id}|'},
            ],
        ]

        if not (g.get('media') or {}).get('file_id'):
            keyboard.append([{'text': '🖼 افزودن تصویر/گیف', 'callback_data': f'pnl|g_media|{group_id}|'}])
        else:
            keyboard.append([
                {'text': '🖼 افزودن تصویر/گیف', 'callback_data': f'pnl|g_media|{group_id}|'},
                {'text': '🗑 حذف رسانه', 'callback_data': f'pnl|g_media_clear|{group_id}|'},
            ])

        keyboard.append([{'text': f"{b(bool(g.get('auto_delete')))} حذف خودکار", 'callback_data': f'pnl|tg|{group_id}|goodbye:goodbye.auto_delete'}])
        if g.get('auto_delete'):
            for row in PanelHandler._auto_delete_rows(group_id, 'goodbye', int(g.get('auto_delete_seconds') or 10)):
                keyboard.append(row)
        keyboard.append([{'text': '📤 ارسال پیش‌نمایش', 'callback_data': f'pnl|g_preview|{group_id}|'}])
        keyboard.append([{'text': '↩️ بازگشت به بخش سیستم', 'callback_data': f'pnl|system|{group_id}|'}])

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_security(chat_id: int, message_id, group_id: int, s: dict) -> None:
        """🛡 امنیت و کنترل — join/character rules up top (per new design), flood/warn/captcha kept below."""
        def b(v):
            return '🟢' if v else '🔴'
        warn_label = WARN_ACTION_LABELS.get(s['warn_action'], s['warn_action'])

        fj_on = b(bool(s['force_join'].get('enabled')))
        cl_on = b(bool(s['char_limit'].get('enabled')))
        keyboard = [
            [
                {'text': f'{cl_on} قفل تعداد کاراکتر', 'callback_data': f'pnl|char_limit|{group_id}|'},
                {'text': f'{fj_on} جوین اجباری', 'callback_data': f'pnl|force_join|{group_id}|'},
            ],
            [{'text': f"{b(bool(s['force_add'].get('enabled')))} اد اجباری", 'callback_data': f'pnl|force_add|{group_id}|'}],
            [{'text': '🚧 قفل‌های ویژه این بخش (به‌زودی)', 'callback_data': f'pnl|ns|{group_id}|vip_locks_sec'}],
            [
                {'text': f"{b(s['captcha']['enabled'])} کپچای عضو جدید", 'callback_data': f'pnl|tg|{group_id}|security:captcha.enabled'},
                {'text': f"{b(s['antiservice'])} حذف پیام ورود/خروج", 'callback_data': f'pnl|tg|{group_id}|security:antiservice'},
            ],
            [
                {'text': f"حد فلود: {s['flood']['limit']} پیام", 'callback_data': f'pnl|flood_limit|{group_id}|'},
                {'text': 'سکوت فلود: ' + Helpers.human_time(int(s['flood']['mute_minutes'])), 'callback_data': f'pnl|flood_mute|{group_id}|'},
            ],
            [
                {'text': f"سقف اخطار: {s['warn_limit']}", 'callback_data': f'pnl|warn_limit|{group_id}|'},
                {'text': f"اکشن اخطار: {warn_label}", 'callback_data': f'pnl|cycle_warnaction|{group_id}|'},
            ],
            [{'text': '↩️ بازگشت به داشبورد', 'callback_data': f'pnl|main|{group_id}|'}],
        ]

        text = (
            "🛡 <b>امنیت و کنترل</b>\n"
            "کنترل کامل ورود و خروج کاربران. با این بخش می‌توانید قوانین عضویت (جوین اجباری چندکاناله، اد اجباری)، محدودیت‌های محتوایی پیشرفته (کاراکتر، پیام) و فیلترهای رفتارهای مشکوک را مدیریت کنید.\n\n"
            "وضعیت قفل‌ها را با دکمه‌های زیر تغییر دهید:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_force_join(chat_id: int, message_id, group_id: int, s: dict, title: str, admin_name: str = '') -> None:
        """📢 مدیریت جوین اجباری (چندکاناله) — toggle + channel list, lives under امنیت و کنترل."""
        enabled = bool(s['force_join'].get('enabled'))
        channels = Database.list_force_join_channels(group_id)
        now_str = datetime.now().strftime('%H:%M')

        keyboard = [
            [{'text': ('🟢' if enabled else '🔴') + ' قفل جوین اجباری', 'callback_data': f'pnl|fj_toggle|{group_id}|'}],
            [{'text': '➕ افزودن کانال جدید', 'callback_data': f'pnl|fj_add|{group_id}|'}],
        ]

        row = []
        for ch in channels:
            label = ch.get('title') or (('@' + ch['username']) if ch.get('username') else ('کانال ' + str(ch['id'])))
            row.append({'text': '❌ ' + str(label)[:16], 'callback_data': f"pnl|fj_del|{group_id}|{ch['id']}"})
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([{'text': '↩️ بازگشت به بخش امنیت', 'callback_data': f'pnl|security|{group_id}|'}])

        if channels:
            lines = []
            for i, ch in enumerate(channels):
                ref = ('@' + ch['username']) if ch.get('username') else (ch.get('title') or ('کانال ' + str(ch['channel_id'])))
                lines.append(f'{i + 1}. ' + Helpers.escape(str(ref)))
            channels_block = "\n".join(lines)
        else:
            channels_block = "هیچ کانالی ثبت نشده است. ⚠️ ابتدا حداقل یک کانال اضافه کنید، سپس قفل را فعال نمایید."

        text = (
            "📢 <b>مدیریت جوین اجباری (چندکاناله)</b>\n"
            "――――――――――\n\n"
            "🏷 گروه: <b>" + Helpers.escape(title) + "</b>\n"
            + (f"👤 مدیر: " + Helpers.escape(admin_name) + f" {now_str}\n" if admin_name != '' else '')
            + "\n📊 وضعیت: " + ('🟢 فعال' if enabled else '🔴 غیرفعال') + "\n"
            f"🔗 <b>کانال‌های عضوگیری اجباری:</b>\n{channels_block}\n\n"
            "برای تغییر، از دکمه‌های زیر استفاده کنید:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_char_limit(chat_id: int, message_id, group_id: int, s: dict, title: str, admin_name: str = '') -> None:
        """🔤 مدیریت محدودیت کاراکتر — max chars per message, lives under امنیت و کنترل."""
        cl = s['char_limit']
        enabled = bool(cl.get('enabled'))
        mx = int(cl.get('max') or 0)
        now_str = datetime.now().strftime('%H:%M')

        max_label = Helpers.escape(str(mx)) if mx > 0 else 'تنظیم نشده'

        keyboard = [
            [{'text': ('🟢' if enabled else '🔴') + ' قفل کاراکتر:', 'callback_data': f'pnl|cl_toggle|{group_id}|'}],
            [
                {'text': '➖ کاهش (۲۰)', 'callback_data': f'pnl|cl_step|{group_id}|-20'},
                {'text': max_label, 'callback_data': f'pnl|cl_info|{group_id}|'},
                {'text': '➕ افزایش (۲۰)', 'callback_data': f'pnl|cl_step|{group_id}|20'},
            ],
            [{'text': '⚡ انتخاب تعداد کاراکتر سریع‌تر 👇', 'callback_data': f'pnl|cl_info|{group_id}|'}],
            [
                {'text': '۵۰', 'callback_data': f'pnl|cl_set|{group_id}|50'},
                {'text': '۱۰۰', 'callback_data': f'pnl|cl_set|{group_id}|100'},
                {'text': '۵۰۰', 'callback_data': f'pnl|cl_set|{group_id}|500'},
                {'text': '۱۰۰۰', 'callback_data': f'pnl|cl_set|{group_id}|1000'},
                {'text': '۳۰۰۰', 'callback_data': f'pnl|cl_set|{group_id}|3000'},
            ],
            [{'text': '↩️ بازگشت به بخش امنیت', 'callback_data': f'pnl|security|{group_id}|'}],
        ]

        text = (
            "🔤 <b>مدیریت محدودیت کاراکتر</b>\n"
            "――――――――――\n\n"
            "🏷 گروه: <b>" + Helpers.escape(title) + "</b>\n"
            + (f"👤 مدیر: " + Helpers.escape(admin_name) + f" {now_str}\n" if admin_name != '' else '')
            + "\n📊 وضعیت: " + ('🟢 فعال' if enabled else '🔴 غیرفعال') + "\n"
            f"🔢 <b>حداکثر کاراکتر مجاز:</b> {max_label}\n\n"
            + ("⚠️ ابتدا تعداد کاراکتر مجاز را با دکمه‌های ➕ / ➖ مشخص کنید یا از دکمه‌های سریع استفاده کنید، سپس قفل را فعال نمایید.\n" if mx <= 0 else '')
            + "برای تغییر، از دکمه‌های زیر استفاده کنید:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_force_add(chat_id: int, message_id, group_id: int, s: dict, title: str, admin_name: str = '') -> None:
        """➕ مدیریت اد اجباری — member must invite N new members before they're allowed to talk."""
        fa = s['force_add']
        enabled = bool(fa.get('enabled'))
        required = int(fa.get('required') or 0)
        now_str = datetime.now().strftime('%H:%M')

        req_label = Helpers.escape(str(required)) if required > 0 else 'تنظیم نشده'

        keyboard = [
            [{'text': ('🟢' if enabled else '🔴') + ' قفل اد اجباری:', 'callback_data': f'pnl|fa_toggle|{group_id}|'}],
            [
                {'text': '➖ کاهش', 'callback_data': f'pnl|fa_step|{group_id}|-1'},
                {'text': req_label, 'callback_data': f'pnl|fa_info|{group_id}|'},
                {'text': '➕ افزایش', 'callback_data': f'pnl|fa_step|{group_id}|1'},
            ],
            [{'text': '↩️ بازگشت به بخش امنیت', 'callback_data': f'pnl|security|{group_id}|'}],
        ]

        text = (
            "➕ <b>مدیریت اد اجباری</b>\n"
            "――――――――――\n\n"
            "🏷 گروه: <b>" + Helpers.escape(title) + "</b>\n"
            + (f"👤 مدیر: " + Helpers.escape(admin_name) + f" {now_str}\n" if admin_name != '' else '')
            + "\n📊 وضعیت: " + ('🟢 فعال' if enabled else '🔴 غیرفعال') + "\n"
            f"🔢 <b>تعداد مورد نیاز:</b> {req_label}\n\n"
            + ("⚠️ ابتدا تعداد مورد نیاز را با دکمه‌های ➕ / ➖ مشخص کنید، سپس قفل را فعال نمایید.\n" if required <= 0
               else "هر عضو باید این تعداد نفر جدید به گروه اضافه کند تا اجازه پیام دادن داشته باشد.\n")
            + "برای تغییر، از دکمه‌های زیر استفاده کنید:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_backup(chat_id: int, message_id, group_id: int) -> None:
        """📁 مدیریت بکاپ و تمپلیت — no backup engine yet, both actions are "coming soon"."""
        keyboard = [
            [{'text': '➕ ایجاد بکاپ جدید', 'callback_data': f'pnl|ns|{group_id}|create_backup'}],
            [{'text': '📋 مشاهده بکاپ‌های من', 'callback_data': f'pnl|ns|{group_id}|view_backups'}],
            [{'text': '↩️ بازگشت به داشبورد', 'callback_data': f'pnl|main|{group_id}|'}],
        ]

        text = (
            "📁 <b>مدیریت بکاپ و تمپلیت</b>\n"
            "در این بخش می‌توانید از تنظیمات گروه خود بکاپ تهیه کنید، بکاپ‌های ذخیره‌شده را مشاهده کنید و آن‌ها را روی گروه‌های دیگر اعمال نمایید.\n\n"
            "گزینه‌های موجود:"
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_lists(chat_id: int, message_id, group_id: int, s: dict) -> None:
        """📋 لیست‌ها و گزارشات — filters/warns/admins are real, the rest need infra we don't have yet."""
        filter_count = len(s.get('badwords') or [])
        warn_count = Database.count_warned_members(group_id)

        keyboard = [
            [
                {'text': f'📝 فیلترها ({filter_count})', 'callback_data': f'pnl|badwords|{group_id}|'},
                {'text': '🧠 یادگیری (۰)', 'callback_data': f'pnl|ns|{group_id}|learning'},
            ],
            [
                {'text': '🚫 لیست بن‌ها (۰)', 'callback_data': f'pnl|ns|{group_id}|ban_list'},
                {'text': '🔇 لیست سکوت‌ها (۰)', 'callback_data': f'pnl|ns|{group_id}|mute_list'},
            ],
            [
                {'text': f'⚠️ لیست اخطارها ({warn_count})', 'callback_data': f'pnl|warns_list|{group_id}|'},
                {'text': '🛡 لیست معافیت‌ها (۰)', 'callback_data': f'pnl|ns|{group_id}|exempt_list'},
            ],
            [{'text': '👥 لیست مدیران', 'callback_data': f'pnl|admins_list|{group_id}|'}],
            [{'text': '↩️ بازگشت به پنل اصلی', 'callback_data': f'pnl|main|{group_id}|'}],
        ]

        text = "📋 <b>لیست‌ها و گزارشات گروه</b>\nاز دکمه‌های زیر برای مشاهده لیست‌ها استفاده کنید:"

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_warns_list(chat_id: int, message_id, group_id: int) -> None:
        rows = Database.list_warned_members(group_id, 20)
        if not rows:
            text = "⚠️ <b>لیست اخطارها</b>\nهیچ کاربری در حال حاضر اخطار فعال ندارد."
        else:
            lines = []
            for i, r in enumerate(rows):
                name = (r.get('first_name') or '').strip() or ('کاربر ' + str(r['user_id']))
                lines.append(f'{i + 1}. ' + Helpers.escape(name) + f" — {r['warns']} اخطار")
            text = "⚠️ <b>لیست اخطارها</b>\n" + "\n".join(lines)
        keyboard = [[{'text': '↩️ بازگشت', 'callback_data': f'pnl|lists|{group_id}|'}]]
        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_admins_list(chat_id: int, message_id, group_id: int) -> None:
        lines = PanelHandler._admin_lines(group_id)
        text = "👥 <b>لیست مدیران گروه</b>\n" + ("\n".join(lines) if lines else 'دریافت لیست مدیران ناموفق بود.')
        keyboard = [[{'text': '↩️ بازگشت', 'callback_data': f'pnl|lists|{group_id}|'}]]
        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_badwords(chat_id: int, message_id, group_id: int, s: dict) -> None:
        words = s.get('badwords') or []
        keyboard = []
        row = []
        for i, w in enumerate(words[:40]):
            row.append({'text': '❌ ' + w[:15], 'callback_data': f'pnl|badword_del|{group_id}|{i}'})
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([{'text': '➕ افزودن کلمه', 'callback_data': f'pnl|badword_add|{group_id}|'}])
        if words:
            keyboard.append([{'text': '🗑 پاک‌کردن همه', 'callback_data': f'pnl|badword_clear|{group_id}|'}])
        keyboard.append([{'text': '↩️ بازگشت', 'callback_data': f'pnl|lists|{group_id}|'}])

        count = len(words)
        text = "🚫 <b>کلمات ممنوعه</b>\n" + (
            f"روی هر کلمه بزن تا حذف بشه ({count} کلمه ثبت‌شده). یادت باشه «قفل فحش» در بخش رسانه و محتوا هم باید روشن باشه تا این فیلتر اعمال بشه."
            if count > 0 else "هنوز کلمه‌ای ثبت نشده."
        )

        PanelHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render_status(chat_id: int, message_id, group_id: int, s: dict, title: str, admin_name: str = '', view: str = 'today') -> None:
        """📊 آمار پیشرفته گروه — time-range selector; only "امروز"/قفل‌ها/ادمین‌ها have real data behind them."""
        now_str = datetime.now().strftime('%H:%M')

        keyboard = [
            [
                {'text': '📅 امروز', 'callback_data': f'pnl|stat_v|{group_id}|today'},
                {'text': '📅 ۷ روز', 'callback_data': f'pnl|stat_v|{group_id}|week'},
                {'text': '📅 ۳۰ روز', 'callback_data': f'pnl|stat_v|{group_id}|month'},
            ],
            [
                {'text': '⏰ ساعتی (۲۴h)', 'callback_data': f'pnl|stat_v|{group_id}|hourly'},
                {'text': '👥 کاربران برتر', 'callback_data': f'pnl|stat_v|{group_id}|top'},
            ],
            [
                {'text': '🛡 آمار قفل‌ها', 'callback_data': f'pnl|stat_v|{group_id}|locks'},
                {'text': '👮 آمار ادمین‌ها', 'callback_data': f'pnl|stat_v|{group_id}|admins'},
            ],
            [{'text': '↩️ بازگشت به داشبورد', 'callback_data': f'pnl|main|{group_id}|'}],
        ]

        header = (
            "📊 <b>آمار پیشرفته گروه</b>\n"
            "🏷 گروه: <b>" + Helpers.escape(title) + "</b>\n"
            + (f"👤 مدیر: " + Helpers.escape(admin_name) + f" {now_str}\n" if admin_name != '' else '')
            + "――――――――――\n"
        )

        if view == 'week':
            body = '🚧 ' + NOT_IMPLEMENTED['stats_week'] + ' به‌زودی تکمیل می‌شود.'
        elif view == 'month':
            body = '🚧 ' + NOT_IMPLEMENTED['stats_month'] + ' به‌زودی تکمیل می‌شود.'
        elif view == 'hourly':
            body = '🚧 ' + NOT_IMPLEMENTED['stats_hourly'] + ' به‌زودی تکمیل می‌شود.'
        elif view == 'top':
            body = '🚧 ' + NOT_IMPLEMENTED['top_users'] + ' به‌زودی تکمیل می‌شود.'
        elif view == 'locks':
            body = PanelHandler._locks_summary_text(s)
        elif view == 'admins':
            admin_lines = PanelHandler._admin_lines(group_id)
            body = ("👮 <b>آمار ادمین‌ها</b>\n" + "\n".join(admin_lines)) if admin_lines else 'دریافت لیست مدیران ناموفق بود.'
        else:
            body = PanelHandler._today_summary_text(s)

        PanelHandler._render(chat_id, message_id, header + body, keyboard)

    @staticmethod
    def _today_summary_text(s: dict) -> str:
        active, total = PanelHandler._count_active_tools(s)
        warn_label = WARN_ACTION_LABELS.get(s['warn_action'], s['warn_action'])

        def on(v):
            return 'روشن' if v else 'خاموش'

        return (
            "📈 <b>وضعیت امروز</b>\n"
            f"🔒 ابزارهای فعال: {active} از {total}\n"
            f"🛡 ضدفلود (ضد اسپم): {on(s['flood']['enabled'])} (حد {s['flood']['limit']} پیام)\n"
            f"⚠️ سقف اخطار: {s['warn_limit']} — اکشن: {warn_label}\n"
            f"🤖 کپچای عضو جدید: {on(s['captcha']['enabled'])}\n"
            f"📌 قفل گروه (فقط ادمین): {on(s['only_admins'])}\n"
            f"💬 پیام خوش‌آمد: {on(s['welcome']['enabled'])}\n"
            f"👋 پیام خداحافظی: {on(s['goodbye']['enabled'])}\n"
            "🚫 کلمات ممنوعه: " + str(len(s.get('badwords') or [])) + " مورد\n"
            "――――――――――\n"
            "📈 آمار پیام، اعضا و نمودار فعالیت زمانی: به‌زودی اضافه می‌شود."
        )

    @staticmethod
    def _locks_summary_text(s: dict) -> str:
        lock_count = sum(1 for v in (s.get('locks') or {}).values() if v)
        lock_total = sum(1 for i in MEDIA_ITEMS if i['kind'] != 'soon') + sum(1 for i in SYSTEM_ITEMS if i['kind'] == 'lock')

        lines = ['🛡 <b>آمار قفل‌ها</b>', f'قفل‌های فعال: {lock_count} از {lock_total}', '']
        for item in MEDIA_ITEMS:
            if item['kind'] not in ('lock', 'confirm'):
                continue
            on = PanelHandler._get_path(s, item['key']) if (item['kind'] == 'confirm' and item.get('store', 'locks') == 'path') \
                else bool(s['locks'].get(item['key']))
            lines.append(('🟢' if on else '🔴') + ' ' + item['label'])
        return "\n".join(lines)

    @staticmethod
    def _render(chat_id: int, message_id, text: str, keyboard: list) -> None:
        markup = {'inline_keyboard': keyboard}
        if message_id:
            ok = Telegram.edit_message_text(chat_id, message_id, text, {'reply_markup': json.dumps(markup)})
            if ok is not None:
                return
        Telegram.send_message(chat_id, text, {'reply_markup': json.dumps(markup)})
