"""管理画面へ入る利用者に多要素認証を必須にするミドルウェア。

なぜ必要か:

管理画面は「全記事を書き換えられる」「利用者を作れる」「権限を配れる」場所です。
ここのパスワードが1つ漏れるだけで、サイト全体が乗っ取られます。

一方、記事を書くだけの利用者にまで多要素認証を強制すると、
運用が回らなくなって「じゃあ全員 is_staff にしよう」といった逆流が起きます。
そこで **対象を is_staff だけに絞って** 必須化します。

設計上の注意:

  * 「MFA 設定ページ自体」を塞いではいけない。塞ぐと設定しに行けなくなる。
  * ログアウトも通す。塞ぐと詰む。
  * 静的ファイルとメディアは対象外。
  * 判定は「登録済みの認証手段があるか」で行う。
    「いま多要素認証を通ったか」ではない。
    後者にすると、セッションのたびに設定を求められる。
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


class StaffMfaRequiredMiddleware:
    """is_staff の利用者に多要素認証の登録を求める。"""

    def __init__(self, get_response):
        self.get_response = get_response
        # 除外パスは起動時に1回だけ組み立てる。
        # リクエストのたびに reverse() を呼ぶと無駄が増える。
        self._exempt_prefixes = self._build_exempt_prefixes()

    @staticmethod
    def _build_exempt_prefixes() -> tuple[str, ...]:
        prefixes = [
            settings.STATIC_URL,
            settings.MEDIA_URL,
        ]
        # これらを塞ぐと「設定しに行けない」「ログアウトもできない」になる。
        for name in (
            "mfa_index",
            "mfa_activate_totp",
            "mfa_view_recovery_codes",
            "mfa_generate_recovery_codes",
            "mfa_download_recovery_codes",
            "mfa_list_webauthn",
            "mfa_add_webauthn",
            "mfa_reauthenticate",
            "mfa_authenticate",
            "account_logout",
            "account_login",
            "account_email",
            "account_email_verification_sent",
            "account_reauthenticate",
        ):
            try:
                prefixes.append(reverse(name))
            except NoReverseMatch:
                # その機能を入れていない構成もある。
                continue
        return tuple(p for p in prefixes if p)

    def __call__(self, request):
        if self._should_require(request):
            messages.warning(
                request,
                "管理者権限のアカウントでは、多要素認証の設定が必要です。"
                "認証アプリかパスキーを登録してください。",
            )
            return redirect("mfa_index")
        return self.get_response(request)

    def _should_require(self, request) -> bool:
        if not getattr(settings, "MFA_REQUIRED_FOR_STAFF", False):
            return False

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_staff:
            return False

        path = request.path
        if path.startswith(self._exempt_prefixes):
            return False

        return not self._has_authenticator(user)

    @staticmethod
    def _has_authenticator(user) -> bool:
        """多要素認証の手段を1つ以上登録しているか。

        リカバリコードだけを登録した状態は「設定済み」とみなさない。
        リカバリコードは他の手段を失ったときの控えであって、
        単体で日常的に使うものではないため。
        """
        from allauth.mfa.models import Authenticator

        return Authenticator.objects.filter(user=user).exclude(
            type=Authenticator.Type.RECOVERY_CODES
        ).exists()
