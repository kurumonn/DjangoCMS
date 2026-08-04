from django.contrib import admin

from .models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("display_name", "article", "short_body", "is_approved", "is_spam", "created_at")
    list_filter = ("is_approved", "is_spam", "created_at")
    search_fields = ("name", "body", "email")
    actions = ("approve_comments", "mark_as_spam")
    readonly_fields = ("ip_hash", "user_agent", "created_at")
    date_hierarchy = "created_at"

    @admin.display(description="本文")
    def short_body(self, obj: Comment) -> str:
        return obj.body[:40] + ("…" if len(obj.body) > 40 else "")

    @admin.action(description="選択したコメントを承認する")
    def approve_comments(self, request, queryset):
        updated = queryset.update(is_approved=True, is_spam=False)
        self.message_user(request, f"{updated} 件のコメントを承認しました。")

    @admin.action(description="選択したコメントをスパムにする")
    def mark_as_spam(self, request, queryset):
        updated = queryset.update(is_spam=True, is_approved=False)
        self.message_user(request, f"{updated} 件をスパムにしました。")
