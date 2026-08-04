from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """操作ログは読むだけ。管理画面からの改ざんを塞ぐ。"""

    list_display = ("created_at", "actor_label", "action", "target_repr")
    list_filter = ("action", "created_at", "target_model")
    search_fields = ("actor_label", "target_repr")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # 保持期間の運用は別途決める（デプロイ編9日目）。
        # 少なくとも管理画面から1件ずつ消せる状態にはしない。
        return False
