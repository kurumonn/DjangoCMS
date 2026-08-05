"""テスト用の設定。

    python manage.py test --settings=config.settings.test

local.py との違いは「速さ」と「他のテストから独立していること」だけで、
アプリの振る舞いは変えない。

テスト用設定でアプリの仕様まで変えると、
テストが通っても本番で動く保証にならなくなる。
たとえばここで ACCOUNT_EMAIL_VERIFICATION を "none" にすると、
メール確認まわりのバグをテストが一切拾えなくなる。
"""

from .local import *  # noqa: F401,F403

# パスワードハッシュを最速のものに差し替える。
# Argon2 は意図的に遅いので、ユーザーを作るテストが何百件もあると
# それだけで数分かかる。
#
# ハッシュ方式そのものを検証するテストは、この設定を
# override_settings で戻して書く。
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# テストごとにキャッシュを分ける。
# レート制限の回数はキャッシュに残るので、共有すると
# 「単体では通るのに、まとめて実行すると落ちる」テストができる。
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "kururucms-test",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# テストの実行中に外へメールが出ないことを、設定の側でも保証しておく。
# locmem バックエンドは django.core.mail.outbox に貯めるだけで送信しない。

# WebAuthn のテストは HTTPS を張らずに実行する。
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = True

# テスト実行を静かにする。
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"]},
}
