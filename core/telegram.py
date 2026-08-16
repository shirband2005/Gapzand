# -*- coding: utf-8 -*-
import json
import os
import time

import requests

from core.config import Config

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'storage')


class Telegram:
    """Port of core/Telegram.php."""

    @staticmethod
    def _api_url(method: str) -> str:
        token = Config.get('bot_token')
        return f"https://api.telegram.org/bot{token}/{method}"

    @staticmethod
    def call(method: str, params: dict = None):
        """Low level call. Returns decoded 'result' or None on failure."""
        params = params or {}
        try:
            resp = requests.post(Telegram._api_url(method), data=params, timeout=15)
        except requests.RequestException:
            return None

        try:
            data = resp.json()
        except ValueError:
            return None

        if not data.get('ok'):
            Telegram._log_error(method, params, resp.text)
            return None
        return data.get('result')

    @staticmethod
    def _log_error(method: str, params: dict, response: str) -> None:
        try:
            os.makedirs(STORAGE_DIR, exist_ok=True)
            line = "[{}] {} params={} resp={}\n".format(
                time.strftime('%Y-%m-%d %H:%M:%S'), method,
                json.dumps(params, ensure_ascii=False, default=str), response,
            )
            with open(os.path.join(STORAGE_DIR, 'telegram_errors.log'), 'a', encoding='utf-8') as f:
                f.write(line)
        except OSError:
            pass

    @staticmethod
    def send_message(chat_id, text: str, extra: dict = None):
        params = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        params.update(extra or {})
        return Telegram.call('sendMessage', params)

    @staticmethod
    def send_photo(chat_id, file_id: str, caption: str = '', extra: dict = None):
        params = {'chat_id': chat_id, 'photo': file_id, 'caption': caption, 'parse_mode': 'HTML'}
        params.update(extra or {})
        return Telegram.call('sendPhoto', params)

    @staticmethod
    def send_animation(chat_id, file_id: str, caption: str = '', extra: dict = None):
        params = {'chat_id': chat_id, 'animation': file_id, 'caption': caption, 'parse_mode': 'HTML'}
        params.update(extra or {})
        return Telegram.call('sendAnimation', params)

    @staticmethod
    def edit_message_text(chat_id, message_id: int, text: str, extra: dict = None):
        params = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML'}
        params.update(extra or {})
        return Telegram.call('editMessageText', params)

    @staticmethod
    def edit_message_reply_markup(chat_id, message_id: int, markup: dict):
        return Telegram.call('editMessageReplyMarkup', {
            'chat_id': chat_id, 'message_id': message_id, 'reply_markup': json.dumps(markup),
        })

    @staticmethod
    def delete_message(chat_id, message_id: int):
        return Telegram.call('deleteMessage', {'chat_id': chat_id, 'message_id': message_id})

    @staticmethod
    def answer_callback_query(callback_id: str, text: str = '', alert: bool = False):
        return Telegram.call('answerCallbackQuery', {
            'callback_query_id': callback_id, 'text': text, 'show_alert': alert,
        })

    @staticmethod
    def get_chat_member(chat_id, user_id: int):
        return Telegram.call('getChatMember', {'chat_id': chat_id, 'user_id': user_id})

    @staticmethod
    def get_chat(chat_id):
        """Resolve a chat (e.g. "@channelusername") to its id/title/type. None if not found/accessible."""
        return Telegram.call('getChat', {'chat_id': chat_id})

    @staticmethod
    def bot_id() -> int:
        """The bot's own numeric user id, derived from the token (format "<id>:<hash>") — no API call needed."""
        return int(str(Config.get('bot_token')).split(':')[0])

    @staticmethod
    def export_chat_invite_link(chat_id):
        return Telegram.call('exportChatInviteLink', {'chat_id': chat_id})

    @staticmethod
    def get_chat_administrators(chat_id):
        return Telegram.call('getChatAdministrators', {'chat_id': chat_id}) or []

    @staticmethod
    def restrict_chat_member(chat_id, user_id: int, permissions: dict, until_date: int = None):
        params = {
            'chat_id': chat_id, 'user_id': user_id, 'permissions': json.dumps(permissions),
        }
        if until_date:
            params['until_date'] = until_date
        return Telegram.call('restrictChatMember', params)

    @staticmethod
    def mute_user(chat_id, user_id: int, minutes: int = 0):
        until = int(time.time()) + minutes * 60 if minutes > 0 else 0
        return Telegram.restrict_chat_member(chat_id, user_id, {'can_send_messages': False}, until)

    @staticmethod
    def unmute_user(chat_id, user_id: int):
        return Telegram.restrict_chat_member(chat_id, user_id, {
            'can_send_messages': True,
            'can_send_media_messages': True,
            'can_send_polls': True,
            'can_send_other_messages': True,
            'can_add_web_page_previews': True,
        })

    @staticmethod
    def ban_chat_member(chat_id, user_id: int, until_date: int = None):
        params = {'chat_id': chat_id, 'user_id': user_id}
        if until_date:
            params['until_date'] = until_date
        return Telegram.call('banChatMember', params)

    @staticmethod
    def unban_chat_member(chat_id, user_id: int):
        return Telegram.call('unbanChatMember', {'chat_id': chat_id, 'user_id': user_id, 'only_if_banned': True})

    @staticmethod
    def kick_chat_member(chat_id, user_id: int):
        Telegram.ban_chat_member(chat_id, user_id)
        return Telegram.unban_chat_member(chat_id, user_id)

    @staticmethod
    def pin_chat_message(chat_id, message_id: int, silent: bool = True):
        return Telegram.call('pinChatMessage', {
            'chat_id': chat_id, 'message_id': message_id, 'disable_notification': silent,
        })

    @staticmethod
    def set_webhook(url: str, secret: str):
        return Telegram.call('setWebhook', {
            'url': url,
            'secret_token': secret,
            'allowed_updates': json.dumps(['message', 'edited_message', 'callback_query', 'my_chat_member']),
        })
