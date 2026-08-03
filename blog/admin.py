from django.contrib import admin

from .models import Article, Category, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "article_count")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="記事数")
    def article_count(self, obj: Category) -> int:
        return obj.articles.count()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "status", "published_at")
    list_filter = ("status", "category", "tags")
    search_fields = ("title", "body")
    # autocomplete_fields は参照先 Admin の search_fields を利用する。
    # CategoryAdmin / TagAdmin に search_fields が無いと admin.E040 で落ちる。
    autocomplete_fields = ("category", "tags")
    date_hierarchy = "published_at"
    # スラッグは save() で自動生成されるが、管理画面では手入力もできるようにする。
    prepopulated_fields = {"slug": ("title",)}

    # 2日目時点では記事詳細ページの URL がまだ無い。
    # get_absolute_url() は定義済みなので、放置すると管理画面の
    # 「サイト上で表示」ボタンが NoReverseMatch で落ちる。
    # 3日目に一覧・詳細ビューを作ったらこの行を削除する。
    view_on_site = False

    fieldsets = (
        (None, {"fields": ("title", "slug", "body")}),
        ("分類", {"fields": ("category", "tags")}),
        ("公開", {"fields": ("status", "published_at", "author")}),
    )

    def save_model(self, request, obj, form, change):
        # 著者が未設定なら、操作したユーザーを著者にする。
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)
