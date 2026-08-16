# -*- coding: utf-8 -*-
import json
import time as time_module

import pymysql
import pymysql.cursors

from core.config import Config


def _deep_merge_defaults(defaults: dict, overrides: dict) -> dict:
    """Python port of PHP's array_replace_recursive(defaults, overrides).

    Every key from `defaults` is kept unless `overrides` supplies a value for
    it; when both sides have a dict for the same key, merge recursively;
    otherwise the override value wins outright (this matches PHP's behaviour
    for lists/scalars — array_replace_recursive does not merge sequential
    arrays element-by-element for non-dict values, it just replaces them).
    """
    result = dict(defaults)
    for key, val in (overrides or {}).items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_defaults(result[key], val)
        else:
            result[key] = val
    return result


class Database:
    _conn = None

    # ---------- connection ----------

    @staticmethod
    def conn():
        if Database._conn is None:
            c = Config.get('db')
            Database._conn = pymysql.connect(
                host=c['host'],
                port=int(c.get('port') or 3306),
                user=c['user'],
                password=c['pass'],
                database=c['name'],
                charset=c.get('charset', 'utf8mb4'),
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
        return Database._conn

    @staticmethod
    def _execute(sql, params=None):
        conn = Database.conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or [])
                return cur
        except pymysql.err.OperationalError:
            # connection may have timed out - reconnect once and retry
            Database._conn = None
            conn = Database.conn()
            with conn.cursor() as cur:
                cur.execute(sql, params or [])
                return cur

    @staticmethod
    def _fetchone(sql, params=None):
        conn = Database.conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchone()

    @staticmethod
    def _fetchall(sql, params=None):
        conn = Database.conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()

    # ---------- Groups ----------

    @staticmethod
    def default_settings() -> dict:
        return {
            'locks': {
                'link': False, 'forward': False, 'sticker': False, 'gif': False,
                'photo': False, 'video': False, 'voice': False, 'video_note': False,
                'audio': False, 'document': False, 'contact': False, 'location': False,
                'poll': False, 'game': False, 'mention': False, 'hashtag': False,
                'english': False, 'edit': False, 'profanity': False, 'text': False,
            },
            'flood': {'enabled': True, 'limit': 6, 'seconds': 8, 'mute_minutes': 10},
            'char_limit': {'enabled': False, 'max': 0},  # 0 = تنظیم نشده
            'force_add': {'enabled': False, 'required': 0},  # 0 = تنظیم نشده
            'welcome': {
                'enabled': True,
                'text': "سلام {user} عزیز، به گروه {group} خوش اومدی 🌸",
                'auto_delete': False,
                'auto_delete_seconds': 10,
                'show_rules_button': False,
                'media': {'type': None, 'file_id': None},  # type: photo|animation
                'buttons': [],  # custom buttons, unlimited: [{'text':..,'url':..}, ...]
            },
            'goodbye': {
                'enabled': False,
                'text': "خداحافظ {user} عزیز 👋 امیدواریم باز هم به {group} سر بزنی 🌸",
                'auto_delete': False,
                'auto_delete_seconds': 10,
                'media': {'type': None, 'file_id': None},  # type: photo|animation
            },
            'captcha': {'enabled': False},
            'rules': '',
            'badwords': [],
            'warn_limit': 3,
            'warn_action': 'ban',  # ban | mute | kick
            'only_admins': False,
            'antiservice': True,  # delete "user joined/left" service messages
            'force_join': {'enabled': False},  # چندکاناله - channels live in force_join_channels table
        }

    @staticmethod
    def get_group(chat_id: int) -> dict:
        row = Database._fetchone('SELECT * FROM `groups` WHERE id = %s', [chat_id])

        if not row:
            settings = Database.default_settings()
            Database._execute(
                'INSERT INTO `groups` (id, settings) VALUES (%s, %s)',
                [chat_id, json.dumps(settings, ensure_ascii=False)],
            )
            return {'id': chat_id, 'title': None, 'settings': settings}

        try:
            settings = json.loads(row.get('settings') or '{}') or {}
        except (TypeError, ValueError):
            settings = {}

        # migrate legacy single welcome button ('button') to the unlimited 'buttons' list
        welcome = settings.get('welcome') or {}
        if not welcome.get('buttons') and (welcome.get('button') or {}).get('text') and (welcome.get('button') or {}).get('url'):
            welcome['buttons'] = [welcome['button']]
        welcome.pop('button', None)
        settings['welcome'] = welcome

        # merge with defaults so new fields added later always exist
        row['settings'] = _deep_merge_defaults(Database.default_settings(), settings)
        return row

    @staticmethod
    def save_group_settings(chat_id: int, settings: dict) -> None:
        Database._execute(
            'UPDATE `groups` SET settings = %s WHERE id = %s',
            [json.dumps(settings, ensure_ascii=False), chat_id],
        )

    @staticmethod
    def touch_group_title(chat_id: int, title) -> None:
        Database._execute('UPDATE `groups` SET title = %s WHERE id = %s', [title, chat_id])

    @staticmethod
    def all_group_ids() -> list:
        rows = Database._fetchall('SELECT id FROM `groups`')
        return [r['id'] for r in rows]

    @staticmethod
    def count_groups() -> int:
        row = Database._fetchone('SELECT COUNT(*) AS c FROM `groups`')
        return int(row['c'])

    # ---------- Users ----------

    @staticmethod
    def upsert_user(user_id: int, first_name, username) -> None:
        Database._execute(
            'INSERT INTO users (id, first_name, username) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE first_name = VALUES(first_name), username = VALUES(username)',
            [user_id, first_name, username],
        )

    @staticmethod
    def count_users() -> int:
        row = Database._fetchone('SELECT COUNT(*) AS c FROM users')
        return int(row['c'])

    @staticmethod
    def all_user_ids() -> list:
        rows = Database._fetchall('SELECT id FROM users')
        return [r['id'] for r in rows]

    # ---------- Group members (per-group state: warns, flood, verification) ----------

    @staticmethod
    def get_member(chat_id: int, user_id: int) -> dict:
        row = Database._fetchone(
            'SELECT * FROM group_members WHERE group_id = %s AND user_id = %s', [chat_id, user_id]
        )
        if not row:
            Database._execute(
                'INSERT IGNORE INTO group_members (group_id, user_id) VALUES (%s, %s)',
                [chat_id, user_id],
            )
            return {'group_id': chat_id, 'user_id': user_id, 'warns': 0,
                     'flood_count': 0, 'flood_time': 0, 'is_verified': 0, 'invites': 0}
        return row

    @staticmethod
    def set_warns(chat_id: int, user_id: int, warns: int) -> None:
        Database._execute(
            'INSERT INTO group_members (group_id, user_id, warns) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE warns = VALUES(warns)',
            [chat_id, user_id, warns],
        )

    @staticmethod
    def set_verified(chat_id: int, user_id: int, verified: bool) -> None:
        Database._execute(
            'INSERT INTO group_members (group_id, user_id, is_verified) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE is_verified = VALUES(is_verified)',
            [chat_id, user_id, 1 if verified else 0],
        )

    @staticmethod
    def bump_flood(chat_id: int, user_id: int, window_seconds: int) -> int:
        now = int(time_module.time())
        m = Database.get_member(chat_id, user_id)
        if now - int(m.get('flood_time') or 0) > window_seconds:
            count = 1
        else:
            count = int(m.get('flood_count') or 0) + 1
        Database._execute(
            'UPDATE group_members SET flood_count = %s, flood_time = %s WHERE group_id = %s AND user_id = %s',
            [count, now, chat_id, user_id],
        )
        return count

    @staticmethod
    def count_warned_members(group_id: int) -> int:
        row = Database._fetchone(
            'SELECT COUNT(*) AS c FROM group_members WHERE group_id = %s AND warns > 0', [group_id]
        )
        return int(row['c'])

    @staticmethod
    def bump_invites(chat_id: int, inviter_id: int, by: int = 1) -> int:
        Database.get_member(chat_id, inviter_id)  # ensure row exists
        Database._execute(
            'UPDATE group_members SET invites = invites + %s WHERE group_id = %s AND user_id = %s',
            [by, chat_id, inviter_id],
        )
        return int(Database.get_member(chat_id, inviter_id)['invites'])

    @staticmethod
    def get_invites(chat_id: int, user_id: int) -> int:
        return int(Database.get_member(chat_id, user_id)['invites'])

    @staticmethod
    def list_warned_members(group_id: int, limit: int = 20) -> list:
        limit = max(1, min(100, limit))
        return Database._fetchall(
            'SELECT gm.user_id, gm.warns, u.first_name, u.username '
            'FROM group_members gm '
            'LEFT JOIN users u ON u.id = gm.user_id '
            'WHERE gm.group_id = %s AND gm.warns > 0 '
            'ORDER BY gm.warns DESC '
            f'LIMIT {limit}',
            [group_id],
        )

    # ---------- Panel pending text input (admin is mid-edit in the panel) ----------

    @staticmethod
    def set_pending_input(user_id: int, group_id: int, field: str, origin: str, message_id: int, payload=None) -> None:
        Database._execute(
            'INSERT INTO panel_pending (user_id, group_id, field, origin, message_id, payload) '
            'VALUES (%s, %s, %s, %s, %s, %s) '
            'ON DUPLICATE KEY UPDATE group_id = VALUES(group_id), field = VALUES(field), '
            'origin = VALUES(origin), message_id = VALUES(message_id), payload = VALUES(payload), '
            'created_at = CURRENT_TIMESTAMP',
            [user_id, group_id, field, origin, message_id, payload],
        )

    @staticmethod
    def get_pending_input(user_id: int):
        row = Database._fetchone('SELECT * FROM panel_pending WHERE user_id = %s', [user_id])
        return row or None

    @staticmethod
    def clear_pending_input(user_id: int) -> None:
        Database._execute('DELETE FROM panel_pending WHERE user_id = %s', [user_id])

    # ---------- Force-join channels (چندکاناله) ----------

    @staticmethod
    def list_force_join_channels(group_id: int) -> list:
        return Database._fetchall(
            'SELECT * FROM force_join_channels WHERE group_id = %s ORDER BY id ASC', [group_id]
        )

    @staticmethod
    def count_force_join_channels(group_id: int) -> int:
        row = Database._fetchone(
            'SELECT COUNT(*) AS c FROM force_join_channels WHERE group_id = %s', [group_id]
        )
        return int(row['c'])

    @staticmethod
    def force_join_channel_exists(group_id: int, channel_id: int) -> bool:
        row = Database._fetchone(
            'SELECT 1 AS x FROM force_join_channels WHERE group_id = %s AND channel_id = %s',
            [group_id, channel_id],
        )
        return bool(row)

    @staticmethod
    def add_force_join_channel(group_id: int, channel_id: int, username, title, invite_link, added_by: int) -> bool:
        if Database.force_join_channel_exists(group_id, channel_id):
            return False
        Database._execute(
            'INSERT INTO force_join_channels (group_id, channel_id, username, title, invite_link, added_by) '
            'VALUES (%s, %s, %s, %s, %s, %s)',
            [group_id, channel_id, username, title, invite_link, added_by],
        )
        return True

    @staticmethod
    def remove_force_join_channel(group_id: int, row_id: int) -> None:
        Database._execute(
            'DELETE FROM force_join_channels WHERE group_id = %s AND id = %s', [group_id, row_id]
        )

    # ---------- Broadcast queue (processed by cron.py) ----------

    @staticmethod
    def queue_broadcast(admin_id: int, payload: dict, target: str) -> int:
        total = Database.count_users() if target == 'users' else Database.count_groups()
        conn = Database.conn()
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO broadcasts (admin_id, payload, target, total, status) '
                "VALUES (%s, %s, %s, %s, 'pending')",
                [admin_id, json.dumps(payload, ensure_ascii=False), target, total],
            )
            return cur.lastrowid

    # ---------- advisory lock (used by the in-process scheduler so that, if the app is run
    # with multiple worker processes, only one of them performs the periodic sweep at a time) ----------

    @staticmethod
    def try_acquire_lock(name: str) -> bool:
        """MySQL named lock, non-blocking (timeout 0). True if acquired."""
        row = Database._fetchone('SELECT GET_LOCK(%s, 0) AS ok', [name])
        return bool(row and row.get('ok') == 1)

    @staticmethod
    def release_lock(name: str) -> None:
        Database._fetchone('SELECT RELEASE_LOCK(%s) AS ok', [name])
