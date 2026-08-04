"""コメント。

公開サイトのコメント欄は、スパムと嫌がらせの入口になる。
この CMS では次の方針を取る。

  * 既定は「未承認」。承認されるまで投稿者本人以外には見えない。
  * 本文は HTML として解釈しない（テンプレートでエスケープする）。
  * IP アドレスは生のまま保存せず、ハッシュ化して保存する。
    連投の検出には十分で、漏えいしても個人の追跡には使いにくい。
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models


def hash_ip(ip: str | None) -> str:
    """IP アドレスをハッシュ化する。

    SECRET_KEY を混ぜるため、DB だけが漏れても元の IP は復元しにくい。
    完全な匿名化ではないが、生の IP を並べておくよりはるかに安全。
    """
    if not ip:
        return ""
    salted = f"{settings.SECRET_KEY}:{ip}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


class CommentQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(is_approved=True, is_spam=False)

    def pending(self):
        return self.filter(is_approved=False, is_spam=False)


class Comment(models.Model):
    """記事に対する1件のコメント。"""

    article = models.ForeignKey(
        "blog.Article",
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="記事",
    )

    # ログインしていれば author が入り、していなければ name を使う。
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comments",
        verbose_name="投稿ユーザー",
    )
    name = models.CharField("表示名", max_length=50)
    email = models.EmailField(
        "メールアドレス",
        blank=True,
        default="",
        help_text="公開されない。連絡が必要なときだけ使う。",
    )
    body = models.TextField("本文", max_length=2000)

    is_approved = models.BooleanField("承認済み", default=False)
    is_spam = models.BooleanField("スパム", default=False)

    ip_hash = models.CharField("IPハッシュ", max_length=64, blank=True, editable=False)
    user_agent = models.CharField(
        "User-Agent", max_length=255, blank=True, default="", editable=False
    )

    created_at = models.DateTimeField("投稿日時", auto_now_add=True)

    objects = CommentQuerySet.as_manager()

    class Meta:
        verbose_name = "コメント"
        verbose_name_plural = "コメント"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["article", "is_approved", "created_at"]),
            models.Index(fields=["ip_hash", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name}: {self.body[:30]}"

    @property
    def display_name(self) -> str:
        if self.author_id:
            return self.author.byline
        return self.name
