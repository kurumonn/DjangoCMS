"""WSGI エントリポイント（同期サーバー用）。

Gunicorn はこのモジュールを読む。既定を production にしているのは、
本番サーバーが開発用設定で起動してしまう事故を防ぐため。
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
