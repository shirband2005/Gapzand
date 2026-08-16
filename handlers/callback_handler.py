# -*- coding: utf-8 -*-
from core.database import Database
from core.telegram import Telegram
from handlers.force_join_handler import ForceJoinHandler
from handlers.fun_handler import FunHandler
from handlers.help_handler import HelpHandler
from handlers.panel_handler import PanelHandler


class CallbackHandler:
    """Port of handlers/CallbackHandler.php."""

    @staticmethod
    def handle(cq: dict) -> None:
        data = cq.get('data') or ''

        if data.startswith('pnl|'):
            PanelHandler.handle_callback(cq)
            return

        if data.startswith('hlp|'):
            HelpHandler.handle_callback(cq)
            return

        if data.startswith('fun|'):
            FunHandler.handle_callback(cq)
            return

        if data.startswith('fj|'):
            ForceJoinHandler.handle_callback(cq, data)
            return

        if data.startswith('verify:'):
            CallbackHandler._handle_verify(cq, data)
            return

        if data.startswith('rules:'):
            CallbackHandler._handle_rules(cq, data)
            return

        Telegram.answer_callback_query(cq['id'])

    @staticmethod
    def _handle_verify(cq: dict, data: str) -> None:
        from handlers.member_handler import MemberHandler

        _, chat_id_str, user_id_str = data.split(':')
        chat_id = int(chat_id_str)
        target_user_id = int(user_id_str)
        clicker_id = int(cq['from']['id'])

        if clicker_id != target_user_id:
            Telegram.answer_callback_query(cq['id'], 'این دکمه برای شما نیست.', True)
            return

        Telegram.unmute_user(chat_id, target_user_id)
        Database.set_verified(chat_id, target_user_id, True)
        Telegram.answer_callback_query(cq['id'], '✅ تایید شدی، خوش اومدی!')

        group = Database.get_group(chat_id)
        if group['settings'].get('welcome', {}).get('enabled'):
            built = MemberHandler.build_welcome_message(group['settings'], cq['from'], group.get('title') or '', None, 0, chat_id)
            Telegram.edit_message_text(chat_id, int(cq['message']['message_id']), built['text'])
        else:
            Telegram.delete_message(chat_id, int(cq['message']['message_id']))

    @staticmethod
    def _handle_rules(cq: dict, data: str) -> None:
        _, chat_id_str = data.split(':')
        chat_id = int(chat_id_str)
        group = Database.get_group(chat_id)
        rules = group['settings']['rules']
        Telegram.answer_callback_query(cq['id'], rules if rules != '' else 'قوانینی ثبت نشده.', True)
