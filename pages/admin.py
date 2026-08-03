from django.contrib import admin

from .models import Page


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "published_at", "show_in_footer", "menu_order")
    list_filter = ("status", "show_in_footer")
    search_fields = ("title", "body")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"

    # 記事と同じ理由で、3日目まで「サイト上で表示」を無効にしておく。
    view_on_site = False
