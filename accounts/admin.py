from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """標準の UserAdmin へ、追加したフィールドを差し込む。"""

    list_display = ("username", "email", "display_name", "is_staff", "is_active")
    search_fields = ("username", "email", "display_name")

    fieldsets = BaseUserAdmin.fieldsets + (
        ("CMS プロフィール", {"fields": ("display_name", "bio")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("CMS プロフィール", {"fields": ("email", "display_name")}),
    )
