#!/usr/bin/env python
"""Django のコマンドラインユーティリティ。"""
import os
import sys


def main():
    # 開発コマンドの既定は開発用設定。
    # 本番サーバーで manage.py を叩くときは DJANGO_SETTINGS_MODULE を明示する。
    # 忘れると、本番機の上で開発用の SQLite を migrate してしまい、
    # 「成功と出たのに本番のデータベースは何も変わっていない」状態になる。
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django をインポートできません。仮想環境が有効か、"
            "pip install -r requirements.txt が済んでいるか確認してください。"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
