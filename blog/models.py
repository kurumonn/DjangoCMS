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

    # --- SEO（6日目に追加）---------------------------------------------
    # 記事タイトルと検索結果のタイトルは、目的が違うので分けられるようにする。
    # 記事内では「ORMでN+1クエリを避ける」で十分でも、
    # 検索結果では「Django ORMのN+1問題を解決する方法」の方がクリックされる。
    seo_title = models.CharField(
        "SEOタイトル", max_length=70, blank=True, default="",
        help_text="空なら記事タイトルを使う。全角35文字程度が目安。",
    )
    seo_description = models.CharField(
        "SEO説明文", max_length=160, blank=True, default="",
        help_text="空なら本文の冒頭を使う。",
    )
    canonical_url = models.URLField(
        "正規URL", blank=True, default="",
        help_text="他サイトへ転載した記事など、正規のURLが別にある場合に指定する。",
    )
    noindex = models.BooleanField(
        "検索エンジンから除外", default=False,
        help_text="この記事だけを検索結果に出したくない場合に有効にする。",
    )
    og_image = models.ForeignKey(
        "media_library.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="og_articles",
        verbose_name="OG画像",
        help_text="空ならアイキャッチ画像、それも空ならサイト既定の画像を使う。",
    )

    objects = ArticleQuerySet.as_manager()

    class Meta:
        verbose_name = "記事"
        verbose_name_plural = "記事"
        ordering = ["-published_at", "-created_at"]
        indexes = [
            # 一覧ページの絞り込み（status + published_at 降順）を高速化する。
            models.Index(fields=["status", "-published_at"]),
        ]
        # Django が自動で作る add/change/delete に加えて、
        # 「公開してよいか」「承認してよいか」を独立した権限にする。
        # これがないと「記事を書ける人＝勝手に公開できる人」になってしまう。
        permissions = [
            ("publish_article", "記事を公開できる"),
            ("review_article", "記事のレビューを承認できる"),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(Article, self.title, instance=self)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:article_detail", kwargs={"slug": self.slug})

    # --- SEO の導出値 ---------------------------------------------------
    # テンプレート内で {% if %} を重ねるのではなく、
    # 「最終的に何を出すか」をモデル側で決める。
    # 出力箇所（詳細ページ・OGP・RSS・サイトマップ）が増えても矛盾しない。
    @property
    def display_seo_title(self) -> str:
        return self.seo_title or self.title

    @property
    def display_seo_description(self) -> str:
        if self.seo_description:
            return self.seo_description
        # 本文から作る。改行を潰し、160文字で切る。
        flattened = " ".join(self.body.split())
        return flattened[:157] + "…" if len(flattened) > 160 else flattened

    @property
    def display_og_image(self):
        """OG画像 → アイキャッチ → なし、の順で解決する。"""
        return self.og_image or self.featured_image

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

    @property
    def is_scheduled(self) -> bool:
        """予約投稿（公開状態だが、公開日時がまだ来ていない）か。"""
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and self.published_at > timezone.now()
        )

    def snapshot(self, *, created_by, note: str = "") -> "ArticleRevision":
        """現在の内容を1つの版として保存する。

        更新の**前**に呼ぶ。更新後に呼ぶと、変更前の内容が残らない。
        """
        return ArticleRevision.objects.create(
            article=self,
            title=self.title,
            body=self.body,
            status=self.status,
            published_at=self.published_at,
            created_by=created_by,
            note=note,
        )


class ArticleRevision(models.Model):
    """記事の変更履歴。

    「誰が・いつ・どんな内容だったか」を残し、事故があれば戻せるようにする。
    本文だけでなく status と published_at も残すのは、
    「うっかり公開してしまった」を戻すときに必要になるため。
    """

    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="revisions",
        verbose_name="記事",
    )
    title = models.CharField("タイトル", max_length=200)
    body = models.TextField("本文")
    status = models.CharField("公開状態", max_length=20)
    published_at = models.DateTimeField("公開日時", null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="article_revisions",
        verbose_name="保存者",
    )
    created_at = models.DateTimeField("保存日時", auto_now_add=True)
    note = models.CharField("メモ", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "記事の版"
        verbose_name_plural = "記事の版"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["article", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.title}（{self.created_at:%Y-%m-%d %H:%M}）"

    def restore_to_article(self, *, restored_by) -> Article:
        """この版の内容を記事へ書き戻す。

        書き戻す前に、いまの内容も1つの版として保存する。
        そうしないと「復元したけれど、やっぱり戻したい」ができなくなる。
        """
        article = self.article
        article.snapshot(created_by=restored_by, note="復元前の自動保存")

        article.title = self.title
        article.body = self.body
        # status と published_at は戻さない。
        # 「公開中の記事の本文だけを古い版に戻す」が実務では最も多く、
        # 復元操作が同時に公開状態まで変えると事故になる。
        article.save(update_fields=["title", "body", "updated_at"])
        return article
