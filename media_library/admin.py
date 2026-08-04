from django.contrib import admin
from django.utils.html import format_html

from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("thumbnail", "title", "image_format", "dimensions", "uploaded_by", "created_at")
    list_display_links = ("thumbnail", "title")
    search_fields = ("title", "alt_text")
    readonly_fields = ("width", "height", "byte_size", "image_format", "checksum")
    date_hierarchy = "created_at"

    @admin.display(description="サムネイル")
    def thumbnail(self, obj: MediaAsset):
        if not obj.file:
            return "—"
        # format_html は引数をエスケープする。f-string で HTML を組み立てると
        # ファイル名経由で管理画面に HTML を注入されうる。
        return format_html(
            '<img src="{}" alt="" style="max-height:48px;max-width:80px">', obj.file.url
        )

    @admin.display(description="寸法")
    def dimensions(self, obj: MediaAsset) -> str:
        return f"{obj.width}×{obj.height}"

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)
