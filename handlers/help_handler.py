# -*- coding: utf-8 -*-
import json

from core.telegram import Telegram

SECTIONS = {
    'locks': {
        'button': '🔒 مدیریت قفل‌ها',
        'text': (
            "🔒 <b>مدیریت قفل‌ها</b>\n\n"
            "• <b>قفل</b> [نوع] — قفل کردن یک نوع محتوا\n"
            "• <b>بازکردن_قفل</b> [نوع] — باز کردن یک قفل\n"
            "• <b>لیست_قفل‌ها</b> — نمایش وضعیت همه قفل‌ها\n\n"
            "انواع: link, forward, sticker, gif, photo, video, voice, video_note, audio, document, "
            "contact, location, poll, game, mention, hashtag, english\n\n"
            "<i>معادل انگلیسی: /lock /unlock /locks</i>"
        ),
    },
    'messages': {
        'button': '💬 خوش‌آمد و قوانین',
        'text': (
            "💬 <b>خوش‌آمد، خداحافظی و قوانین</b>\n\n"
            "• <b>خوشامد</b> on|off — روشن/خاموش کردن پیام خوش‌آمد\n"
            "• <b>تنظیم_خوشامد</b> [متن] — متغیرها: {user} {inviter} {inviter_invites_count} {group} "
            "{date} {time} {day_of_week} {month_name} {user_id} {username} {emoji}\n"
            "• برای رسانه، دکمه سفارشی و حذف خودکار پیام خوش‌آمد از پنل (/panel ← سیستم و دستورات) استفاده کن\n"
            "• <b>خداحافظی</b> on|off — روشن/خاموش پیام خداحافظی\n"
            "• <b>تنظیم_خداحافظی</b> [متن] — تنظیم متن خداحافظی\n"
            "• <b>قوانین</b> — نمایش قوانین گروه\n"
            "• <b>تنظیم_قوانین</b> [متن] — تنظیم قوانین گروه\n\n"
            "<i>معادل انگلیسی: /welcome /setwelcome /goodbye /setgoodbye /rules /setrules</i>"
        ),
    },
    'discipline': {
        'button': '⚖️ بخش انضباطی',
        'text': (
            "⚖️ <b>بخش انضباطی</b>\n\n"
            "• <b>بن / آنبن / اخراج</b> — روی ریپلای پیام فرد\n"
            "• <b>سکوت</b> [مدت مثل 10m 2h 1d] / <b>رفع_سکوت</b> — روی ریپلای\n"
            "• <b>اخطار / حذف_اخطار / اخطارها</b> — روی ریپلای\n"
            "• <b>سقف_اخطار</b> [عدد] — تنظیم سقف اخطار\n"
            "• <b>اکشن_اخطار</b> ban|mute|kick — اکشن پس از پر شدن اخطار\n"
            "• <b>افزودن_فیلتر / حذف_فیلتر / فیلترها</b> [کلمه] — فیلتر کلمات\n"
            "• <b>ضدفلود</b> on|off|limit عدد|seconds عدد|mute عدد\n\n"
            "<i>معادل انگلیسی: /ban /unban /kick /mute /unmute /warn /unwarn /warns /setwarnlimit "
            "/warnaction /addbadword /rembadword /badwords /flood</i>"
        ),
    },
    'security': {
        'button': '🛡 امنیت و ورود',
        'text': (
            "🛡 <b>امنیت و ورود اعضا</b>\n\n"
            "• <b>کپچا</b> on|off — تایید هویت اعضای تازه‌وارد\n"
            "• <b>فقط_ادمین</b> on|off — فقط پیام ادمین‌ها مجاز باشد\n"
            "• <b>ضدسرویس</b> on|off — حذف پیام‌های ورود/خروج اعضا\n\n"
            "<i>معادل انگلیسی: /captcha /onlyadmins /antiservice</i>"
        ),
    },
    'tools': {
        'button': '🧰 ابزارهای کاربردی',
        'text': (
            "🧰 <b>ابزارهای کاربردی</b>\n\n"
            "• <b>پین</b> — پین کردن پیام ریپلای‌شده\n"
            "• <b>ادمین‌ها</b> — نمایش لیست ادمین‌های گروه\n"
            "• <b>شناسه</b> — نمایش آیدی گروه/کاربر\n"
            "• <b>پنل</b> — باز کردن پنل شیشه‌ای تنظیمات در پی‌وی\n\n"
            "<i>معادل انگلیسی: /pin /admins /id /panel</i>"
        ),
    },
    'members': {
        'button': '👥 مدیریت اعضا',
        'text': (
            "👥 <b>مدیریت اعضا</b>\n\n"
            "• <b>ادمین</b> — ارتقا به ادمین، روی ریپلای پیام فرد\n"
            "• <b>عزل</b> — برکناری از ادمینی، روی ریپلای پیام فرد\n\n"
            "<i>معادل انگلیسی: /promote /demote</i>"
        ),
    },
    'fun': {
        'button': '🎲 سرگرمی',
        'text': (
            "🎲 <b>سرگرمی</b>\n\n"
            "• <b>سرگرمی</b> — باز کردن منوی سرگرمی (🔮 فال حافظ، 📺 تلویزیون زنده)\n\n"
            "همه‌چیز با دکمه‌های شیشه‌ای انجام می‌شه، فقط کافیه لمس کنی."
        ),
    },
    'changelog': {
        'button': '🔥 آخرین تغییرات',
        'text': (
            "🔥 <b>آخرین تغییرات</b>\n\n"
            "✅ همه‌ی دستورات ربات الان معادل فارسی هم دارن و دیگه نیازی به «/» نیست؛ کافیه متن فارسی "
            "دستور رو مستقیم بفرستی (مثلاً «بن» یا «قفل لینک»).\n"
            "معادل انگلیسی دستورات هم مثل قبل با «/» کار می‌کنه (مثلاً /ban).\n\n"
            "✅ دستور «ریستارت بات» اضافه شد (مخصوص مالک ربات) — با نوشتنش، ربات خودش رو ری‌استارت "
            "می‌کنه تا آخرین قابلیت‌های آپلودشده فعال بشن."
        ),
    },
}


class HelpHandler:
    """
    راهنمای تعاملی (ویزارد دکمه‌ای) ربات.
    با فرستادن «راهنما» یا «/start» باز می‌شود و با دکمه‌های شیشه‌ای بین بخش‌ها جابه‌جا می‌شود،
    دقیقاً شبیه پنل تنظیمات: یک پیام ثابت که با هر تپ ویرایش می‌شود.

    Port of handlers/HelpHandler.php.
    """

    @staticmethod
    def send_main(chat_id, message_id: int = None) -> None:
        text = (
            "📘 <b>راهنمای ربات</b>\n\n"
            "به بخش راهنمای ربات مدیریت گروه خوش اومدید. از این‌جا می‌تونید با دستورات و بخش‌های اصلی ربات آشنا بشید.\n\n"
            "📌 لطفاً از منوی زیر گزینه موردنظر را انتخاب کنید:"
        )
        HelpHandler._render(chat_id, message_id, text, HelpHandler._main_keyboard())

    @staticmethod
    def handle_callback(cq: dict) -> None:
        data = cq.get('data') or ''  # hlp|action
        parts = data.split('|')
        action = parts[1] if len(parts) > 1 else 'main'
        chat_id = int(cq['message']['chat']['id'])
        message_id = int(cq['message']['message_id'])

        if action == 'close':
            Telegram.delete_message(chat_id, message_id)
            Telegram.answer_callback_query(cq['id'])
            return

        if action == 'main' or action not in SECTIONS:
            HelpHandler.send_main(chat_id, message_id)
            Telegram.answer_callback_query(cq['id'])
            return

        keyboard = []
        if action == 'fun':
            keyboard.append([{'text': '🎲 باز کردن بخش سرگرمی', 'callback_data': 'fun|menu|'}])
        keyboard.append([{'text': '↩️ بازگشت', 'callback_data': 'hlp|main'}])
        HelpHandler._render(chat_id, message_id, SECTIONS[action]['text'], keyboard)
        Telegram.answer_callback_query(cq['id'])

    @staticmethod
    def _main_keyboard() -> list:
        return [
            [
                {'text': SECTIONS['locks']['button'], 'callback_data': 'hlp|locks'},
                {'text': SECTIONS['messages']['button'], 'callback_data': 'hlp|messages'},
            ],
            [
                {'text': SECTIONS['discipline']['button'], 'callback_data': 'hlp|discipline'},
                {'text': SECTIONS['security']['button'], 'callback_data': 'hlp|security'},
            ],
            [
                {'text': SECTIONS['tools']['button'], 'callback_data': 'hlp|tools'},
                {'text': SECTIONS['fun']['button'], 'callback_data': 'hlp|fun'},
            ],
            [
                {'text': SECTIONS['members']['button'], 'callback_data': 'hlp|members'},
                {'text': SECTIONS['changelog']['button'], 'callback_data': 'hlp|changelog'},
            ],
            [
                {'text': '❌ بستن', 'callback_data': 'hlp|close'},
            ],
        ]

    @staticmethod
    def _render(chat_id, message_id, text: str, keyboard: list) -> None:
        markup = {'inline_keyboard': keyboard}
        if message_id:
            ok = Telegram.edit_message_text(chat_id, message_id, text, {'reply_markup': json.dumps(markup)})
            if ok is not None:
                return
        Telegram.send_message(chat_id, text, {'reply_markup': json.dumps(markup)})
