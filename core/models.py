"""アプリ横断で使うモデル。"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLogQuerySet(models.QuerySet):
    def for_object(self, obj):
        return self.filter(
            target_app_label=obj._meta.app_label,
            target_model=obj._meta.model_name,
            target_id=str(obj.pk),
        )


class AuditLog(models.Model):
    """「誰が・いつ・何に・何をしたか」の記録。

    Django 標準の LogEntry は管理画面の操作しか残らない。
    CMS 側の画面から行われた公開・承認・削除も追えるようにする。

    設計上の注意:

      * 追記専用にする。書き換えや削除の口を作らない。
      * 対象オブジェクトを ForeignKey にしない。記事を削除したときに
        「削除した」という記録まで一緒に消えてしまうため、
        アプリラベル・モデル名・ID を文字列で持つ。
      * 記録に個人情報を残しすぎない。IP はハッシュで持つ。
    """

    class Action(models.TextChoices):
        CREATE = "create", "作成"
        UPDATE = "update", "更新"
        DELETE = "delete", "削除"
        SUBMIT_REVIEW = "submit_review", "レビュー依頼"
        APPROVE = "approve", "承認"
        REJECT = "reject", "差し戻し"
        PUBLISH = "publish", "公開"
        UNPUBLISH = "unpublish", "非公開化"
        RESTORE = "restore", "版の復元"
        LOGIN_FAILED = "login_failed", "ログイン失敗"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="操作者",
    )
    actor_label = models.CharField(
        "操作者名",
        max_length=150,
        blank=True,
        default="",
        help_text="ユーザーが削除されても誰の操作か分かるよう、名前を控えておく。",
    )
    action = models.CharField("操作", max_length=32, choices=Action.choices)

    target_app_label = models.CharField("対象アプリ", max_length=100, blank=True, default="")
    target_model = models.CharField("対象モデル", max_length=100, blank=True, default="")
    target_id = models.CharField("対象ID", max_length=64, blank=True, default="")
    target_repr = models.CharField("対象の表示名", max_length=200, blank=True, default="")

    detail = models.JSONField("詳細", default=dict, blank=True)
    ip_hash = models.CharField("IPハッシュ", max_length=64, blank=True, default="")

    created_at = models.DateTimeField("日時", auto_now_add=True, db_index=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        verbose_name = "操作ログ"
        verbose_name_plural = "操作ログ"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_app_label", "target_model", "target_id"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor_label} {self.get_action_display()} {self.target_repr}"


def record(action: str, *, actor=None, target=None, request=None, **detail) -> AuditLog:
    """操作ログを1件残す。

        record(AuditLog.Action.PUBLISH, actor=request.user, target=article,
               request=request, from_status="review")

    ログの記録が失敗しても本来の処理は止めない、という設計にはしない。
    「承認したのに記録が無い」状態は監査上の欠陥なので、失敗させて気づかせる。
    """
    from comments.models import hash_ip
    from core.ratelimit import client_ip

    entry = AuditLog(action=action, detail=detail or {})

    if actor is not None and getattr(actor, "is_authenticated", False):
        entry.actor = actor
        entry.actor_label = str(actor)
    else:
        entry.actor_label = "(匿名)"

    if target is not None:
        entry.target_app_label = target._meta.app_label
        entry.target_model = target._meta.model_name
        entry.target_id = str(target.pk)
        entry.target_repr = str(target)[:200]

    if request is not None:
        entry.ip_hash = hash_ip(client_ip(request))

    entry.save()
    return entry
