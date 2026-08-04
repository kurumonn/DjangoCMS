"""ブログのモデル。

モデルは最初から巨大にしない。2日目は「記事を保存して一覧に出す」ために
最低限必要なフィールドだけを定義し、必要になった日に追加していく。

  2日目: title / slug / body / author / category / tags / status / published_at
  4日目: featured_image（アイキャッチ）
  5日目: リビジョンと承認フロー
  6日目: SEO 項目
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .utils import unique_slugify


class Category(models.Model):
    """記事の分類。1記事につき1つだけ選ぶ。"""

    name = models.CharField("カテゴリ名", max_length=100, unique=True)
    slug = models.SlugField("スラッグ", max_length=120, unique=True, blank=True)
    description = models.TextField("説明", blank=True, default="")

    class Meta:
        verbose_name = "カテゴリ"
        verbose_name_plural = "カテゴリ"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(Category, self.name, instance=self)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:category_detail", kwargs={"slug": self.slug})


class Tag(models.Model):
    """記事に付ける自由なラベル。1記事に複数付けられる。"""

    name = models.CharField("タグ名", max_length=100, unique=True)
    slug = models.SlugField("スラッグ", max_length=120, unique=True, blank=True)

    class Meta:
        verbose_name = "タグ"
        verbose_name_plural = "タグ"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(Tag, self.name, instance=self)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:tag_detail", kwargs={"slug": self.slug})


class ArticleQuerySet(models.QuerySet):
    """「どの記事を取り出すか」の条件をここへ集める。

    View や Template に条件を散らかすと、公開判定の抜け漏れが必ず起きる。
    「一般利用者へ見せてよい記事」の定義は published() 1か所だけにする。
    """

    def published(self):
        """公開済みかつ公開日時が現在以前の記事だけを返す。

        status が PUBLISHED でも published_at が未来なら「予約投稿」であり、
        まだ一般利用者へ見せてはいけない。
        """
        return self.filter(
            status=Article.Status.PUBLISHED,
            published_at__isnull=False,
            published_at__lte=timezone.now(),
        )

    def with_related(self):
        """一覧表示で N+1 クエリを防ぐための事前読み込み。"""
        return self.select_related(
            "author", "category", "featured_image"
        ).prefetch_related("tags")

    def search(self, query: str):
        """タイトルと本文からの全文検索。

        SQLite / PostgreSQL のどちらでも動くよう、まずは icontains で実装する。
        PostgreSQL へ移行したあとは SearchVector に差し替えられるよう、
        検索条件をこの1メソッドへ閉じ込めておく。
        """
        from django.db.models import Q

        query = (query or "").strip()
        if not query:
            return self.none()

        # 空白区切りの語をすべて含む記事を返す（AND 検索）。
        queryset = self
        for term in query.split()[:5]:  # 語数を制限し、極端に重いクエリを防ぐ
            queryset = queryset.filter(
                Q(title__icontains=term) | Q(body__icontains=term)
            )
        return queryset


class Article(models.Model):
    """CMS の中心となる記事モデル。"""

    class Status(models.TextChoices):
        # 左が DB へ保存される値、右が管理画面などに表示される名前。
        DRAFT = "draft", "下書き"
        REVIEW = "review", "レビュー待ち"
        PUBLISHED = "published", "公開"

    title = models.CharField("タイトル", max_length=200)
    slug = models.SlugField(
        "スラッグ",
        max_length=220,
        unique=True,
        blank=True,
        help_text="URL に使う識別子。空なら自動生成する。",
    )
    body = models.TextField("本文")

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name="著者",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name="カテゴリ",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="articles",
        verbose_name="タグ",
    )

    # アイキャッチ画像。
    # ImageField を直接持たせるのではなく、メディアライブラリを参照する。
    # 直接持たせると、同じ画像を記事ごとに再アップロードすることになり、
    # 差し替えも一括でできない。
    featured_image = models.ForeignKey(
        "media_library.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="featured_articles",
        verbose_name="アイキャッチ画像",
    )

    status = models.CharField(
        "公開状態",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    published_at = models.DateTimeField(
        "公開日時",
        null=True,
        blank=True,
        help_text="未来の日時を入れると予約投稿になる。",
    )

    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        verbose_name = "記事"
        verbose_name_plural = "記事"
        ordering = ["-published_at", "-created_at"]
        indexes = [
            # 一覧ページの絞り込み（status + published_at 降順）を高速化する。
            models.Index(fields=["status", "-published_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(Article, self.title, instance=self)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:article_detail", kwargs={"slug": self.slug})

    def related_articles(self, limit: int = 4):
        """関連記事を返す。

        「同じタグが多く付いている記事」を優先し、足りなければ同じカテゴリで埋める。
        自分自身と未公開記事は必ず除外する。
        """
        from django.db.models import Count

        base = Article.objects.published().with_related().exclude(pk=self.pk)

        tag_ids = list(self.tags.values_list("id", flat=True))
        results = []
        if tag_ids:
            results = list(
                base.filter(tags__in=tag_ids)
                .annotate(shared=Count("tags"))
                .order_by("-shared", "-published_at")
                .distinct()[:limit]
            )

        if len(results) < limit:
            seen = {a.pk for a in results}
            filler = base.filter(category=self.category).exclude(pk__in=seen)
            results.extend(filler[: limit - len(results)])

        return results

    @property
    def is_visible_to_public(self) -> bool:
        """一般利用者へ見せてよいか。published() と同じ判定をオブジェクト単位で行う。"""
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )
