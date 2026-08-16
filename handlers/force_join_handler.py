# -*- coding: utf-8 -*-
import json

from core.database import Database
from core.helpers import Helpers
from core.telegram import Telegram


class ForceJoinHandler:
    """
    جوین اجباری (چندکاناله) — enforcement side.

    The panel (PanelHandler.render_force_join) manages the on/off switch and the
    list of required channels (force_join_channels table). This class checks,
    for a given group message, whether the sender is a member of every
    required channel and — if not — deletes the message and prompts them to
    join, with a "✅ عضو شدم" button that re-checks membership.

    Requirement for this to work: the bot must be an admin in every channel
    that's added (enforced at add-time in PanelHandler), since getChatMember
    on a channel only works for chats the bot can see into.

    Port of handlers/ForceJoinHandler.php.
    """

    @staticmethod
    def check_and_enforce(message: dict, group: dict) -> bool:
        settings = group['settings']
        if not (settings.get('force_join') or {}).get('enabled'):
            return False

        chat_id = int(message['chat']['id'])
        user_id = int(message['from']['id'])

        channels = Database.list_force_join_channels(chat_id)
        if not channels:
            return False  # toggle is on but list is empty - nothing to enforce

        missing = ForceJoinHandler.missing_channels(channels, user_id)
        if not missing:
            return False

        Telegram.delete_message(chat_id, int(message['message_id']))
        ForceJoinHandler._send_join_prompt(chat_id, user_id, message['from'], missing)
        return True

    @staticmethod
    def missing_channels(channels: list, user_id: int) -> list:
        """Subset of `channels` the user is NOT currently a member of."""
        missing = []
        for ch in channels:
            member = Telegram.get_chat_member(int(ch['channel_id']), user_id)
            status = (member or {}).get('status')
            # treat an unreadable channel (bot removed/demoted) as "pass" rather than
            # permanently locking the group out - admins will notice via renderForceJoin
            if member is None:
                continue
            if status not in ('member', 'administrator', 'creator'):
                missing.append(ch)
        return missing

    @staticmethod
    def _send_join_prompt(chat_id: int, user_id: int, user: dict, missing: list) -> None:
        name = Helpers.full_name(user) or ('@' + (user.get('username') or 'کاربر'))

        keyboard = []
        for ch in missing:
            label = ch.get('title') or (('@' + ch['username']) if ch.get('username') else 'کانال')
            keyboard.append([{'text': '📢 عضویت در ' + str(label)[:30], 'url': ForceJoinHandler._channel_url(ch)}])
        keyboard.append([{'text': '✅ عضو شدم، بررسی کن', 'callback_data': f'fj|check|{chat_id}|{user_id}'}])

        text = (Helpers.mention(user_id, name)
                + " عزیز، برای ارسال پیام در این گروه ابتدا باید در کانال‌(های) زیر عضو بشی 👇\n\n"
                + "بعد از عضویت، روی دکمه‌ی «✅ عضو شدم، بررسی کن» بزن.")

        Telegram.send_message(chat_id, text, {'reply_markup': json.dumps({'inline_keyboard': keyboard})})

    @staticmethod
    def _channel_url(ch: dict) -> str:
        if ch.get('username'):
            return 'https://t.me/' + ch['username']
        if ch.get('invite_link'):
            return ch['invite_link']
        # last-resort fallback for a private channel with no stored invite link
        return 'https://t.me/c/' + str(ch['channel_id']).lstrip('-100')

    @staticmethod
    def handle_callback(cq: dict, data: str) -> None:
        """callback_data: fj|check|{chatId}|{userId}"""
        parts = data.split('|')
        if (parts[1] if len(parts) > 1 else '') != 'check':
            Telegram.answer_callback_query(cq['id'])
            return
        chat_id = int(parts[2]) if len(parts) > 2 else 0
        target_user_id = int(parts[3]) if len(parts) > 3 else 0
        clicker_id = int(cq['from']['id'])

        if clicker_id != target_user_id:
            Telegram.answer_callback_query(cq['id'], 'این دکمه برای شما نیست.', True)
            return

        channels = Database.list_force_join_channels(chat_id)
        missing = ForceJoinHandler.missing_channels(channels, target_user_id)

        if missing:
            names = '، '.join(c.get('title') or (('@' + c['username']) if c.get('username') else 'کانال')
                               for c in missing)
            Telegram.answer_callback_query(cq['id'], f"هنوز عضو همه‌ی کانال‌ها نشدی: {names}", True)
            return

        Telegram.answer_callback_query(cq['id'], '✅ عضویت تایید شد، حالا می‌تونی پیام بدی.', True)
        Telegram.delete_message(chat_id, int(cq['message']['message_id']))
