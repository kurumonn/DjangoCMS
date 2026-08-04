"""9日目: TOTP・リカバリコード・パスキーのテスト。

allauth の MFA 実装そのものは本家がテストしている。
ここで固定するのは次の2点。

  1. この CMS の設定が意図どおりか（復旧手段を消していないか等）
  2. 自作した「管理者は多要素認証必須」ミドルウェアの挙動
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator

User = get_user_model()

PASSWORD = "test-pass-phrase-1234"


def make_user(username: str, *, is_staff: bool = False) -> User:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=PASSWORD,
        is_staff=is_staff,
    )
    EmailAddress.objects.create(
        user=user, email=user.email, verified=True, primary=True
    )
    return user


def add_totp(user) -> Authenticator:
    """TOTP を登録済みの状態にする。"""
    from allauth.mfa.totp.internal import auth as totp_auth

    secret = totp_auth.generate_totp_secret()
    return totp_auth.TOTP.activate(user, secret).instance


def current_totp_code(authenticator: Authenticator) -> str:
    """認証アプリが「いま」表示するのと同じコードを計算する。

    共有秘密鍵と現在時刻から、サーバーと端末が独立に同じ値を出す
    ——これが TOTP の仕組みそのもの。
    allauth には「コードを生成する」公開関数が無い（検証しかしない）ので、
    内部の hotp_value / format_hotp_value を使って組み立てる。
    """
    import time

    from allauth.mfa import app_settings as mfa_settings
    from allauth.mfa.utils import decrypt
    from allauth.mfa.totp.internal import auth as totp_auth

    secret = decrypt(authenticator.data["secret"])
    counter = int(time.time()) // mfa_settings.TOTP_PERIOD
    return totp_auth.format_hotp_value(totp_auth.hotp_value(secret, counter))


class MfaSettingsTests(TestCase):
    """設定を1行消すと静かに危険になる項目を固定する。"""

    def test_recovery_codes_are_enabled(self):
        """リカバリコードを外すと、端末を失った利用者が復旧できなくなる。"""
        from django.conf import settings

        self.assertIn("recovery_codes", settings.MFA_SUPPORTED_TYPES)

    def test_totp_and_webauthn_are_enabled(self):
        from django.conf import settings

        self.assertIn("totp", settings.MFA_SUPPORTED_TYPES)
        self.assertIn("webauthn", settings.MFA_SUPPORTED_TYPES)

    def test_recovery_codes_are_shown_once(self):
        """後からいつでも見られると、画面を覗かれただけで突破される。"""
        from django.conf import settings

        self.assertTrue(settings.MFA_RECOVERY_CODES_SHOW_ONCE)

    def test_passkey_signup_is_disabled(self):
        """登録時にパスキーだけで作らせない。

        その端末を失った時点で復旧手段が無くなるため、
        まずメールアドレスとパスワードを用意させる。
        """
        from django.conf import settings

        self.assertFalse(settings.MFA_PASSKEY_SIGNUP_ENABLED)

    def test_insecure_origin_is_flagged_by_system_check(self):
        """WebAuthn は HTTPS 前提。本番で緩めたままなら起動時に検出する。

        「テストで確かめる」だけでは不十分。
        テストは開発者が実行しないと動かないが、
        システムチェックは runserver や migrate のたびに必ず走る。
        """
        from django.test import override_settings

        from accounts.checks import check_mfa_settings

        with override_settings(DEBUG=False, MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN=True):
            issues = check_mfa_settings(None)
        self.assertTrue(any(i.id == "accounts.E001" for i in issues))

        with override_settings(DEBUG=False, MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN=False):
            issues = check_mfa_settings(None)
        self.assertFalse(any(i.id == "accounts.E001" for i in issues))

    def test_dev_settings_do_not_trigger_checks(self):
        """開発中は何も言わない。邪魔をしないことも要件のうち。"""
        from django.test import override_settings

        from accounts.checks import check_account_settings, check_mfa_settings

        with override_settings(DEBUG=True):
            self.assertEqual(check_mfa_settings(None), [])
            self.assertEqual(check_account_settings(None), [])

    def test_console_email_backend_is_flagged_in_production(self):
        """本番でメールがコンソール出力のままだと、確認メールが誰にも届かない。"""
        from django.test import override_settings

        from accounts.checks import check_account_settings

        with override_settings(
            DEBUG=False,
            EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        ):
            issues = check_account_settings(None)
        self.assertTrue(any(i.id == "accounts.E002" for i in issues))

    def test_totp_tolerance_is_not_too_wide(self):
        """時計のずれを吸収する幅を広げすぎない。

        広いほど、同時に有効なコードが増えて総当たりが楽になる。
        """
        from django.conf import settings

        self.assertLessEqual(settings.MFA_TOTP_TOLERANCE, 60)


class MfaPagesTests(TestCase):
    def setUp(self):
        # allauth のレート制限はキャッシュに残る。
        # 捨てないと、同じクラスの前のテストのログイン試行が数えられ、
        # 無関係なテストが 429 で落ちる。
        cache.clear()
        self.user = make_user("mfa-user")

    def _login_with_password(self):
        """パスワードを入力して実際にログインする。

        force_login() では「いつ本人確認したか」が記録されない。
        ACCOUNT_REAUTHENTICATION_REQUIRED を有効にしていると、
        多要素認証の設定画面が再認証へリダイレクトしてしまう。
        """
        self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": PASSWORD},
        )

    def test_mfa_index_is_reachable(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("mfa_index"))
        self.assertEqual(response.status_code, 200)

    def test_totp_activation_requires_recent_authentication(self):
        """設定変更の前に、もう一度本人確認を求める。

        セッションを盗まれても、パスワードを知らなければ
        認証手段を勝手に追加できないようにするための仕組み。
        """
        self.client.force_login(self.user)
        response = self.client.get(reverse("mfa_activate_totp"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("reauthenticate", response.url)

    def test_totp_activation_page_is_reachable_after_login(self):
        self._login_with_password()
        response = self.client.get(reverse("mfa_activate_totp"))
        self.assertEqual(response.status_code, 200)

    def test_mfa_pages_are_noindex(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("mfa_index"))
        self.assertContains(response, 'content="noindex, nofollow"')

    def test_anonymous_cannot_reach_mfa_index(self):
        self.client.logout()
        response = self.client.get(reverse("mfa_index"))
        self.assertEqual(response.status_code, 302)


class TotpLoginTests(TestCase):
    """TOTP を登録すると、パスワードだけではログインが完了しない。"""

    def setUp(self):
        cache.clear()
        self.user = make_user("totp-user")

    def test_password_alone_does_not_complete_login(self):
        add_totp(self.user)

        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        # 2段目の認証画面へ送られる。
        self.assertIn(reverse("mfa_authenticate"), response.url)

        # まだ本ログインは成立していない。
        dashboard = self.client.get(reverse("dashboard:index"))
        self.assertEqual(dashboard.status_code, 302)

    def test_wrong_totp_code_does_not_log_in(self):
        add_totp(self.user)
        self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": PASSWORD},
        )

        self.client.post(reverse("mfa_authenticate"), {"code": "000000"})
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 302)

    def test_correct_totp_code_completes_login(self):
        authenticator = add_totp(self.user)

        self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": PASSWORD},
        )

        code = current_totp_code(authenticator)
        response = self.client.post(reverse("mfa_authenticate"), {"code": code})
        self.assertEqual(response.status_code, 302)

        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 200)


class RecoveryCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("recovery-user")
        add_totp(self.user)

    def _generate_codes(self) -> list[str]:
        from allauth.mfa.recovery_codes.internal import auth as rc_auth

        authenticator = rc_auth.RecoveryCodes.activate(self.user).instance
        return rc_auth.RecoveryCodes(authenticator).get_unused_codes()

    def test_recovery_code_logs_in(self):
        codes = self._generate_codes()

        self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": PASSWORD},
        )
        response = self.client.post(reverse("mfa_authenticate"), {"code": codes[0]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 200)

    def test_recovery_code_cannot_be_reused(self):
        """一度使ったリカバリコードは二度と使えない。

        再利用できると、紙を一度覗かれただけで何度でも入られる。
        """
        codes = self._generate_codes()

        self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": PASSWORD},
        )
        self.client.post(reverse("mfa_authenticate"), {"code": codes[0]})
        self.client.post(reverse("account_logout"))

        # 同じコードでもう一度。
        self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": PASSWORD},
        )
        self.client.post(reverse("mfa_authenticate"), {"code": codes[0]})
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 302)

    def test_expected_number_of_codes_is_generated(self):
        from django.conf import settings

        self.assertEqual(len(self._generate_codes()), settings.MFA_RECOVERY_CODE_COUNT)


@override_settings(MFA_REQUIRED_FOR_STAFF=True)
class StaffMfaRequiredMiddlewareTests(TestCase):
    """管理者は多要素認証を登録するまで、他の画面へ進めない。"""

    def setUp(self):
        cache.clear()
        self.staff = make_user("mfa-staff", is_staff=True)
        self.author = make_user("mfa-author")

    def test_staff_without_mfa_is_redirected(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("blog:article_list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("mfa_index"))

    def test_staff_can_still_reach_mfa_setup(self):
        """設定ページ自体を塞ぐと、設定しに行けなくなる。

        ミドルウェアが 302 を返していないことが要点。
        再認証への 302 は allauth の仕様なので、
        「mfa_index へ差し戻されていない」ことで判定する。
        """
        self.client.post(
            reverse("account_login"),
            {"login": self.staff.email, "password": PASSWORD},
        )
        for name in ("mfa_index", "mfa_activate_totp", "mfa_list_webauthn"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_staff_can_still_log_out(self):
        """ログアウトを塞ぐと詰む。"""
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("account_logout")).status_code, 200)

    def test_staff_with_totp_passes_through(self):
        add_totp(self.staff)
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("blog:article_list")).status_code, 200
        )

    def test_recovery_codes_alone_do_not_count(self):
        """リカバリコードは控えであって、日常の認証手段ではない。"""
        from allauth.mfa.recovery_codes.internal import auth as rc_auth

        rc_auth.RecoveryCodes.activate(self.staff)
        self.client.force_login(self.staff)

        response = self.client.get(reverse("blog:article_list"))
        self.assertEqual(response.status_code, 302)

    def test_non_staff_is_not_forced(self):
        """記事を書くだけの利用者にまで強制すると運用が回らない。"""
        self.client.force_login(self.author)
        self.assertEqual(
            self.client.get(reverse("blog:article_list")).status_code, 200
        )

    def test_anonymous_is_not_affected(self):
        self.assertEqual(
            self.client.get(reverse("blog:article_list")).status_code, 200
        )

    def test_static_urls_are_not_redirected(self):
        self.client.force_login(self.staff)
        response = self.client.get("/static/css/site.css")
        self.assertNotEqual(response.status_code, 302)

    @override_settings(MFA_REQUIRED_FOR_STAFF=False)
    def test_can_be_disabled(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("blog:article_list")).status_code, 200
        )
