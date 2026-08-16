# -*- coding: utf-8 -*-
from config import CONFIG


class Config:
    """Port of core/Config.php — simple accessor over the CONFIG dict in config.py."""

    _data = CONFIG

    @staticmethod
    def get(key: str = None):
        if key is None:
            return Config._data
        return Config._data.get(key)
