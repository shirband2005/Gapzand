# -*- coding: utf-8 -*-
"""
نقطه ورود وبهوک ربات (معادل Python فایل‌های bootstrap.php + index.php).

اجرا (مثلاً پشت Gunicorn):
    gunicorn -w 2 -b 0.0.0.0:8000 app:app

سپس با install/set_webhook.py آدرس عمومی HTTPS این اپ را به تلگرام معرفی کنید.
"""
import hmac
import json
import os
import traceback
from datetime import datetime

from flask import Flask, request, Response

from core.config import Config
from core.database import Database
from core.helpers import Helpers
from core import scheduler
from handlers.callback_handler import CallbackHandler
from handlers.command_handler import CommandHandler
from handlers.filter_handler import FilterHandler
from handlers.force_join_handler import ForceJoinHandler
from handlers.member_handler import MemberHandler
from handlers.owner_handler import OwnerHandler
from handlers.panel_handler import PanelHandler

STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage')

app = Flask(__name__)

# جایگزین کرون‌جاب: کارهای دوره‌ای (پیام همگانی، حذف خودکار) همین‌جا در پس‌زمینه اجرا می‌شوند.
scheduler.start()


@app.route('/', methods=['GET'])
def health():
    """
    برای هلث‌چک پلتفرم‌هایی مثل Railway (که با یه درخواست GET ساده چک می‌کنن اپ بالاست یا نه).
    خودِ تلگرام همیشه POST می‌فرسته، پس این مسیر با وبهوک اصلی تداخلی نداره.
    """
    return Response('ربات فعال است ✅', status=200, mimetype='text/plain')


@app.route('/', methods=['POST'])
@app.route('/index.php', methods=['POST'])  # legacy path kept working, in case an old webhook URL is still set
def webhook():
    # --- validate secret token from Telegram ---
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not hmac.compare_digest(Config.get('webhook_secret'), secret):
        return Response('forbidden', status=403)

    update = request.get_json(silent=True)
    if not isinstance(update, dict):
        return Response(status=200)

    # ack Telegram immediately by responding 200 regardless of what happens below;
    # any processing error is caught and logged rather than surfaced to Telegram.
    try:
        if 'message' in update:
            _handle_message(update['message'])
        elif 'callback_query' in update:
            CallbackHandler.handle(update['callback_query'])
        # my_chat_member (bot added/removed/promoted) intentionally ignored - not required for core features
    except Exception as e:
        try:
            os.makedirs(STORAGE_DIR, exist_ok=True)
            with open(os.path.join(STORAGE_DIR, 'php_errors.log'), 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {e}\n{traceback.format_exc()}\n\n")
        except OSError:
            pass

    return Response(status=200)


def _handle_message(message: dict) -> None:
    chat_type = message['chat']['type']
    frm = message.get('from')

    if frm and not frm.get('is_bot'):
        Database.upsert_user(int(frm['id']), frm.get('first_name'), frm.get('username'))

    # «ریستارت بات» - فقط مالک(های) ربات، هم تو گروه هم تو پی‌وی، قبل از هرچیز دیگه چک می‌شود
    if OwnerHandler.maybe_handle_restart(message):
        return

    # ----- Private chat (owner tools + panel deep-link + generic help) -----
    if chat_type == 'private':
        text = (message.get('text') or '').strip()

        if text.startswith('/start'):
            parts = text.split(' ', 1)
            payload = parts[1] if len(parts) > 1 else ''
            if payload != '':
                PanelHandler.open_from_deep_link(int(message['chat']['id']), int(frm['id']), payload, Helpers.full_name(frm or {}))
                return
            CommandHandler.handle(message, {'settings': Database.default_settings()})
            return

        if PanelHandler.maybe_handle_text_input(message):
            return
        if OwnerHandler.handle_confirm_send(message):
            return
        if OwnerHandler.handle_private(message):
            return

        if text in ('/help', 'راهنما', 'شروع'):
            CommandHandler.handle(message, {'settings': Database.default_settings()})
        return

    # ----- Group / supergroup -----
    if chat_type not in ('group', 'supergroup'):
        return

    chat_id = int(message['chat']['id'])
    group = Database.get_group(chat_id)
    Database.touch_group_title(chat_id, message['chat'].get('title'))

    if message.get('new_chat_members'):
        MemberHandler.on_join(message)
        return
    if message.get('left_chat_member'):
        MemberHandler.on_leave(message)
        return

    text = message.get('text') or ''
    if text != '' and (text[0] == '/' or CommandHandler.is_persian_command_text(text)):
        CommandHandler.handle(message, group)
        return

    # Regular message -> run moderation filters (locks / badwords / flood)
    if frm and not frm.get('is_bot'):
        FilterHandler.check(message, group)


if __name__ == '__main__':
    # local/dev only - use gunicorn/uwsgi behind HTTPS in production.
    # روی Railway معمولاً Procfile با gunicorn اجرا می‌کنه، ولی اگه مستقیم با
    # "python app.py" هم اجرا بشه، از پورتی که خودِ Railway در PORT می‌ده استفاده می‌کنیم.
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
