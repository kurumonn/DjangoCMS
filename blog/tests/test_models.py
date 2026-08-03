"""2日目: モデルの振る舞いを固定するテスト。"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from blog.models import Article, Category, Tag

from .factories import create_article, create_category, create_tag


class SlugGenerationTests(TestCase):
    """スラッグの自動生成。"""

    def test_ascii_title_becomes_slug(self):
        article = create_article(title="Hello Django CMS")
        self.assertEqual(article.slug, "hello-django-cms")

    def test_japanese_only_title_gets_fallback_slug(self):
        """日本語だけのタイトルは slugify で空になるため、代替スラッグを割り当てる。"""
        article = create_article(title="日本語だけのタイトル")
        self.assertTrue(article.slug)
        self.assertTrue(article.slug.startswith("post-"))

    def test_duplicate_titles_get_unique_slugs(self):
        first = create_article(title="Same Title")
        second = create_article(title="Same Title")
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.slug, "same-title-2")

    def test_explicit_slug_is_kept(self):
        article = create_article(title="Hello", slug="custom-slug")
        self.assertEqual(article.slug, "custom-slug")

    def test_category_and_tag_generate_slugs(self):
        category = create_category(name="Django Tips")
        tag = create_tag(name="Web Security")
        self.assertEqual(category.slug, "django-tips")
        self.assertEqual(tag.slug, "web-security")


class PublishedQuerySetTests(TestCase):
    """公開判定は published() 1か所に集約する。"""

    def setUp(self):
        self.category = create_category()
        self.public = create_article(title="Public", category=self.category)
        self.draft = create_article(
            title="Draft", category=self.category, status=Article.Status.DRAFT
        )
        self.review = create_article(
            title="Review", category=self.category, status=Article.Status.REVIEW
        )
        self.scheduled = create_article(
            title="Scheduled",
            category=self.category,
            published_at=timezone.now() + timedelta(days=1),
        )
        self.no_date = create_article(
            title="No date", category=self.category, published_at=None
        )

    def test_published_contains_only_public_article(self):
        titles = set(Article.objects.published().values_list("title", flat=True))
        self.assertEqual(titles, {"Public"})

    def test_draft_is_excluded(self):
        self.assertNotIn(self.draft, Article.objects.published())

    def test_review_is_excluded(self):
        self.assertNotIn(self.review, Article.objects.published())

    def test_future_dated_article_is_excluded(self):
        """予約投稿は status=published でも、公開日時までは表に出さない。"""
        self.assertNotIn(self.scheduled, Article.objects.published())

    def test_article_without_published_at_is_excluded(self):
        self.assertNotIn(self.no_date, Article.objects.published())

    def test_is_visible_to_public_matches_queryset(self):
        """オブジェクト単位の判定と QuerySet の判定を食い違わせない。"""
        for article in Article.objects.all():
            with self.subTest(article=article.title):
                in_queryset = Article.objects.published().filter(pk=article.pk).exists()
                self.assertEqual(article.is_visible_to_public, in_queryset)


class RelationTests(TestCase):
    """外部キーの削除保護と related_name。"""

    def test_category_in_use_cannot_be_deleted(self):
        """PROTECT なので、記事が残っているカテゴリは削除できない。"""
        from django.db.models import ProtectedError

        category = create_category(name="使用中")
        create_article(title="Uses category", category=category)
        with self.assertRaises(ProtectedError):
            category.delete()

    def test_author_in_use_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        article = create_article(title="Has author")
        with self.assertRaises(ProtectedError):
            article.author.delete()

    def test_related_name_lets_us_walk_backwards(self):
        category = create_category(name="逆引き")
        article = create_article(title="Backwards", category=category)
        tag = create_tag(name="逆引きタグ")
        article.tags.add(tag)

        self.assertIn(article, category.articles.all())
        self.assertIn(article, tag.articles.all())
        self.assertIn(article, article.author.articles.all())

    def test_str_returns_human_readable_name(self):
        self.assertEqual(str(create_category(name="表示名")), "表示名")
        self.assertEqual(str(create_tag(name="tag-str")), "tag-str")
        self.assertEqual(str(create_article(title="記事の表示名")), "記事の表示名")
