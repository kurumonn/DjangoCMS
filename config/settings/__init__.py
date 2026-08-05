"""設定パッケージ。

9日目までは `config/settings.py` という1枚のファイルだった。
10日目に、環境ごとに違う部分だけを切り離す。

    base.py        どの環境でも同じ設定
    local.py       開発機（SQLite・コンソールへメール・DEBUG=True）
    test.py        テスト（速いハッシュ・インメモリDB）
    production.py  本番（PostgreSQL・Redis・HTTPS強制）

このファイルは**わざと空にしてある**。

`config.settings` を import できるようにすると、
「どの環境の設定で動いているか分からないまま動く」状態が生まれる。
本番で `manage.py migrate` を打ったつもりが開発用の SQLite を
書き換えていた、という事故はこれで起きる。

そのため、必ず次のどれかを明示する。

    DJANGO_SETTINGS_MODULE=config.settings.local
    DJANGO_SETTINGS_MODULE=config.settings.production

manage.py は local を、wsgi.py / asgi.py は production を既定にしている。
「開発コマンドは開発用へ、本番サーバーは本番用へ」という向きを、
既定値そのもので表している。
"""
