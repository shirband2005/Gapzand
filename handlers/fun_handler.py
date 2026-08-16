# -*- coding: utf-8 -*-
import json

from core.helpers import Helpers
from core.telegram import Telegram

# key => (برچسب دکمه, آدرس پخش زنده آپارات)
CHANNELS = {
    'tv1':      {'label': 'شبکه یک',   'url': 'https://www.aparat.com/live/tv1'},
    'tv2':      {'label': 'شبکه دو',   'url': 'https://www.aparat.com/live/tv2'},
    'tv3':      {'label': 'شبکه سه',   'url': 'https://www.aparat.com/live/tv3'},
    'tv4':      {'label': 'شبکه چهار', 'url': 'https://www.aparat.com/live/tv4'},
    'tv5':      {'label': 'شبکه پنج',  'url': 'https://www.aparat.com/live/tv5'},
    'khabar':   {'label': 'شبکه خبر',  'url': 'https://www.aparat.com/live/irinn'},
    'ifilm':    {'label': 'آی‌فیلم',   'url': 'https://www.aparat.com/live/ifilm'},
    'namayesh': {'label': 'نمایش',     'url': 'https://www.aparat.com/liveamayesh'},
    'varzesh':  {'label': 'ورزش',      'url': 'https://www.aparat.com/live/varzesh'},
    'nasim':    {'label': 'نسیم',      'url': 'https://www.aparat.com/liveasim'},
    'mostanad': {'label': 'مستند',     'url': 'https://www.aparat.com/live/mostanad'},
    'quran':    {'label': 'قرآن',      'url': 'https://www.aparat.com/live/quran'},
    'pouya':    {'label': 'پویا',      'url': 'https://www.aparat.com/live/pouya'},
    'hd':       {'label': 'HD',        'url': 'https://www.aparat.com/live/hd'},
    'press':    {'label': 'پرس‌تی‌وی', 'url': 'https://www.aparat.com/live/press'},
}

# آدرس API فال حافظ (تصویری)
FAL_API_URL = 'http://api.updl.tk/fal/'


class FunHandler:
    """
    بخش سرگرمی: فال حافظ + تلویزیون زنده.
    کاملاً به‌صورت ویزارد شیشه‌ای (inline keyboard) کار می‌کند؛ دقیقاً شبیه HelpHandler/PanelHandler
    یک پیام ثابت که با هر تپ ادیت می‌شود، به‌جز فال که چون عکسه پیام تازه می‌فرستد.

    Port of handlers/FunHandler.php.
    """

    @staticmethod
    def send_menu(chat_id, message_id: int = None) -> None:
        text = "🎲 <b>بخش سرگرمی</b>\n\nیکی از گزینه‌های زیر رو انتخاب کن:"
        FunHandler._render(chat_id, message_id, text, FunHandler._main_keyboard())

    @staticmethod
    def handle_callback(cq: dict) -> None:
        data = cq.get('data') or ''  # fun|action|extra
        parts = data.split('|')
        action = parts[1] if len(parts) > 1 else 'menu'
        extra = parts[2] if len(parts) > 2 else ''
        chat_id = int(cq['message']['chat']['id'])
        message_id = int(cq['message']['message_id'])

        if action == 'fal':
            FunHandler._send_fal(chat_id)
        elif action == 'tvlist':
            FunHandler._render_tv_list(chat_id, message_id)
        elif action == 'tv':
            FunHandler._render_channel(chat_id, message_id, extra)
        elif action == 'close':
            Telegram.delete_message(chat_id, message_id)
            Telegram.answer_callback_query(cq['id'])
            return
        else:  # 'menu' and default
            FunHandler.send_menu(chat_id, message_id)

        Telegram.answer_callback_query(cq['id'])

    @staticmethod
    def _main_keyboard() -> list:
        return [
            [{'text': '🔮 فال حافظ', 'callback_data': 'fun|fal|'}],
            [{'text': '📺 تلویزیون زنده', 'callback_data': 'fun|tvlist|'}],
            [{'text': '❌ بستن', 'callback_data': 'fun|close|'}],
        ]

    @staticmethod
    def _send_fal(chat_id) -> None:
        """
        فال به‌صورت عکس ارسال می‌شود، پس روی پیام قبلی قابل ادیت نیست؛
        برای همین همیشه پیام تازه می‌فرستیم، با دکمه‌ی «دوباره» و «بازگشت» زیرش.
        """
        keyboard = [
            [{'text': '🔁 یک فال دیگر', 'callback_data': 'fun|fal|'}],
            [{'text': '↩️ بازگشت به منو', 'callback_data': 'fun|menu|'}],
        ]

        ok = Telegram.call('sendPhoto', {
            'chat_id': chat_id,
            'photo': FAL_API_URL,
            'caption': '🔮 اینم فال شما، به نیت خودتون باشه 🌹',
            'reply_markup': json.dumps({'inline_keyboard': keyboard}),
        })

        if ok is None:
            Telegram.send_message(chat_id, '⚠️ الان امکان گرفتن فال نیست، چند لحظه دیگه دوباره امتحان کن.', {
                'reply_markup': json.dumps({'inline_keyboard': [
                    [{'text': '↩️ بازگشت به منو', 'callback_data': 'fun|menu|'}],
                ]}),
            })

    @staticmethod
    def _render_tv_list(chat_id, message_id) -> None:
        keyboard = []
        row = []
        i = 0
        for key, ch in CHANNELS.items():
            row.append({'text': ch['label'], 'callback_data': f'fun|tv|{key}'})
            i += 1
            if i % 2 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([{'text': '↩️ بازگشت', 'callback_data': 'fun|menu|'}])

        FunHandler._render(chat_id, message_id, "📺 <b>تلویزیون زنده</b>\n\nشبکه موردنظرت رو انتخاب کن:", keyboard)

    @staticmethod
    def _render_channel(chat_id, message_id, key: str) -> None:
        keyboard = [[{'text': '↩️ بازگشت به لیست شبکه‌ها', 'callback_data': 'fun|tvlist|'}]]

        ch = CHANNELS.get(key)
        if not ch:
            FunHandler._render(chat_id, message_id, 'شبکه نامعتبر است.', keyboard)
            return

        text = (f"📺 <b>{Helpers.escape(ch['label'])}</b>\n\n"
                f"برای تماشای پخش زنده روی لینک زیر بزن:\n{ch['url']}")
        FunHandler._render(chat_id, message_id, text, keyboard)

    @staticmethod
    def _render(chat_id, message_id, text: str, keyboard: list) -> None:
        markup = {'inline_keyboard': keyboard}
        if message_id:
            # اگر پیام قبلی عکس فال بوده باشه، editMessageText روش کار نمی‌کنه (None برمی‌گرده)
            # و در اون صورت به‌صورت خودکار پیام تازه فرستاده می‌شود.
            ok = Telegram.edit_message_text(chat_id, message_id, text, {'reply_markup': json.dumps(markup)})
            if ok is not None:
                return
        Telegram.send_message(chat_id, text, {'reply_markup': json.dumps(markup)})
