"""KururuCMS の Django 設定。

1日目はまず「動く最小構成」を作る。
10日目に config/settings/ パッケージへ分割し、本番設定を切り離す。
"""

import os
from pathlib import Path

# BASE_DIR は manage.py があるディレクトリ。
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 秘密情報
# ---------------------------------------------------------------------------
# SECRET_KEY はセッション署名や CSRF トークンの生成に使う。
# 漏えいするとログイン偽装が可能になるため、本番では必ず環境変数で渡す。
# 開発用のフォールバックは DEBUG のときだけ許可する。
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError(
            "DJANGO_SECRET_KEY が未設定です。本番では環境変数で必ず指定してください。"
        )
    SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# 管理画面のURLパス。既定の "admin" のままだと総当たり攻撃の的になるため、
# 本番では環境変数で推測しにくい値へ変更する。
# ただしこれは「発見されにくくする」対策であって、認証の代わりにはならない。
# 実際の防御は 9日目の MFA 必須化とレート制限で行う。
ADMIN_URL_PATH = os.environ.get("DJANGO_ADMIN_URL_PATH", "admin").strip("/")

# ---------------------------------------------------------------------------
# アプリケーション
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    # 自作アプリ
    "core",
    "accounts",
    "blog",
    "pages",
    "media_library",
    "comments",
    "seo",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "seo.context_processors.site_settings",
                "seo.context_processors.sidebar",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# データベース
# ---------------------------------------------------------------------------
# 1日目は SQLite で始める。10日目に PostgreSQL へ移行する。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# 認証
# ---------------------------------------------------------------------------
# ★最重要★ カスタムユーザーモデルは「最初の migrate より前」に指定する。
# 後から差し替えると、記事の著者・コメント・権限の外部キーをすべて作り直すことになる。
AUTH_USER_MODEL = "accounts.User"

# Argon2 を第一候補にする。Django 標準の PBKDF2 より攻撃コストが高い。
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# 国際化
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# 静的ファイル・メディア
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# アップロードの上限。Django が受け取る段階で切るための保険。
# 実際の検証は media_library/validators.py が行う。
# Nginx 側でも client_max_body_size を設定する（デプロイ編6日目）。
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024   # 6 MiB
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
# フォームの項目数の上限。極端に多い項目を送りつけるDoSを防ぐ。
DATA_UPLOAD_MAX_NUMBER_FIELDS = 500

# 信頼できるリバースプロキシの段数。
# 0 のとき X-Forwarded-For を一切信用しない（開発既定）。
# Nginx の背後に置いたら 1 にする（デプロイ編6日目）。
TRUSTED_PROXY_COUNT = int(os.environ.get("DJANGO_TRUSTED_PROXY_COUNT", "0"))

# ---------------------------------------------------------------------------
# セキュリティ既定値
# ---------------------------------------------------------------------------
# DEBUG=False の環境（本番・ステージング）では常に有効化する。
# 8日目・10日目でさらに HSTS などを追加する。
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True

# 開発中はコンソールへメールを出す。8日目に本物の SMTP を設定する。
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "noreply@example.com")
