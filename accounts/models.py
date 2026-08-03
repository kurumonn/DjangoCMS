"""CMS のユーザーモデル。

Django のユーザーモデルは、プロジェクト開始直後に確定させる。
記事の著者・コメント・権限がすべてこのモデルを外部キーで参照するため、
運用開始後の差し替えは大規模な移行作業になる。
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """KururuCMS で使用するユーザー。

    AbstractUser を継承しているので、username / password / is_staff /
    is_superuser / groups / user_permissions といった標準機能はそのまま使える。
    ここでは CMS に必要な項目だけを追加する。
    """

    # 標準の User は email が重複可能。ログインIDとして使うため一意にする。
    email = models.EmailField("メールアドレス", unique=True)

    display_name = models.CharField(
        "表示名",
        max_length=50,
        blank=True,
        help_text="記事の著者名として表示される。空ならユーザー名を使う。",
    )
    bio = models.TextField("プロフィール", blank=True, default="")

    class Meta:
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー"

    def __str__(self) -> str:
        return self.display_name or self.username

    @property
    def byline(self) -> str:
        """記事に表示する著者名。"""
        return self.display_name or self.username
