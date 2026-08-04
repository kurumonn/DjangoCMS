"""起動時に走るシステムチェック。

「本番で危険な設定になっていないか」は、テストではなくここで検出する。
テストは開発者が実行しないと動かないが、システムチェックは
`manage.py runserver` でも `manage.py migrate` でも必ず走る。
デプロイ時の `manage.py check --deploy` にも乗る。

設計方針: 開発を邪魔しないこと。
DEBUG=True のあいだは何も言わず、DEBUG=False のときだけ声を上げる。
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Warning, register


@register(deploy=True)
def check_mfa_settings(app_configs, **kwargs):
    """多要素認証まわりの設定が本番向きか。"""
    issues = []

    if settings.DEBUG:
        # 開発中は何も言わない。
        return issues

    if getattr(settings, "MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN", False):
        issues.append(
            Error(
                "MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN が本番で有効になっています。",
                hint=(
                    "パスキーは HTTPS を前提にした仕組みです。"
                    "この設定を有効にしたまま公開すると、"
                    "通信を書き換えられる経路でパスキー認証を成立させられます。"
                    "環境変数 DJANGO_MFA_ALLOW_INSECURE_ORIGIN=0 を設定してください。"
                ),
                id="accounts.E001",
            )
        )

    supported = set(getattr(settings, "MFA_SUPPORTED_TYPES", []))
    if supported and "recovery_codes" not in supported:
        issues.append(
            Warning(
                "MFA_SUPPORTED_TYPES にリカバリコードが含まれていません。",
                hint=(
                    "認証アプリの入った端末を失った利用者が、"
                    "自力でログインできなくなります。"
                    "管理者による本人確認の手順を用意していないなら、"
                    "recovery_codes を有効にしてください。"
                ),
                id="accounts.W001",
            )
        )

    if not getattr(settings, "MFA_RECOVERY_CODES_SHOW_ONCE", True):
        issues.append(
            Warning(
                "リカバリコードが何度でも表示できる設定になっています。",
                hint=(
                    "ログイン中の画面を覗かれるだけで、"
                    "以後の多要素認証を回避されます。"
                    "MFA_RECOVERY_CODES_SHOW_ONCE = True を推奨します。"
                ),
                id="accounts.W002",
            )
        )

    return issues


@register(deploy=True)
def check_account_settings(app_configs, **kwargs):
    """認証まわりで、本番に出してはいけない設定。"""
    issues = []

    if settings.DEBUG:
        return issues

    if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
        issues.append(
            Error(
                "メールの送信先がコンソールのままです。",
                hint=(
                    "メール確認・ワンタイムコード・パスワード再設定が"
                    "利用者へ届きません。SMTP を設定してください。"
                ),
                id="accounts.E002",
            )
        )

    if getattr(settings, "ACCOUNT_EMAIL_VERIFICATION", "") != "mandatory":
        issues.append(
            Warning(
                "メールアドレスの確認が必須になっていません。",
                hint=(
                    "他人のメールアドレスで登録できてしまい、"
                    "そのアドレス宛の通知を受け取られる可能性があります。"
                ),
                id="accounts.W003",
            )
        )

    if not getattr(settings, "ACCOUNT_PREVENT_ENUMERATION", False):
        issues.append(
            Warning(
                "アカウントの存在を漏らさない設定が無効です。",
                hint=(
                    "「そのメールアドレスは登録されていません」といった応答から、"
                    "誰が会員かを総当たりで調べられます。"
                ),
                id="accounts.W004",
            )
        )

    return issues
