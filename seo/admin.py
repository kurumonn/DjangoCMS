from django.contrib import admin

from .models import SiteSetting


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    """設定は1行だけ。追加・削除の口を塞ぐ。"""

    fieldsets = (
        ("サイト情報", {"fields": ("site_name", "tagline", "description", "base_url")}),
        ("SNS・共有", {"fields": ("default_og_image", "twitter_site")}),
        ("見た目", {
            "fields": (
                "accent_color",
                "accent_color_dark",
                "show_sidebar",
                "sidebar_recent_count",
            )
        }),
        ("検索エンジン", {"fields": ("noindex_site",)}),
    )

    def has_add_permission(self, request):
        # すでに1行あるなら追加させない。
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """一覧を出さず、いきなり唯一の設定の編集画面へ送る。"""
        from django.shortcuts import redirect
        from django.urls import reverse

        setting = SiteSetting.load()
        return redirect(
            reverse("admin:seo_sitesetting_change", args=[setting.pk])
        )
