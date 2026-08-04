from django.contrib import admin

from .models import Article, ArticleRevision, Category, Tag


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

    fieldsets = (
        (None, {"fields": ("title", "slug", "body")}),
        ("分類", {"fields": ("category", "tags")}),
        ("公開", {"fields": ("status", "published_at", "author")}),
    )

    def save_model(self, request, obj, form, change):
        # 著者が未設定なら、操作したユーザーを著者にする。
        if not obj.author_id:
            obj.author = request.user
        # 管理画面からの編集でも履歴を残す。CMS 画面だけで履歴を取ると、
        # 「管理画面から直したときだけ履歴が飛ぶ」という穴ができる。
        if change and obj.pk:
            before = Article.objects.filter(pk=obj.pk).first()
            if before is not None:
                before.snapshot(created_by=request.user, note="管理画面での編集前")
        super().save_model(request, obj, form, change)


@admin.register(ArticleRevision)
class ArticleRevisionAdmin(admin.ModelAdmin):
    """履歴は読むだけ。管理画面から書き換えられては履歴の意味が無い。"""

    list_display = ("article", "title", "status", "created_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "body", "article__title")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
