"""4日目: サイト内検索のテスト。"""

from django.test import TestCase
from django.urls import reverse

from blog.models import Article

from .factories import create_article, create_category


class SearchViewTests(TestCase):
    def setUp(self):
        self.category = create_category()
        create_article(
            title="Djangoのマイグレーション入門",
            category=self.category,
            body="makemigrations と migrate の違いを説明します。",
        )
        create_article(
            title="Nginxのリバースプロキシ",
            category=self.category,
            body="proxy_pass の書き方を説明します。",
        )
        create_article(
            title="下書きのDjango記事",
            category=self.category,
            body="Django の下書きです。",
            status=Article.Status.DRAFT,
        )
        self.url = reverse("blog:search")

    def test_matches_title(self):
        response = self.client.get(self.url, {"q": "マイグレーション"})
        self.assertContains(response, "Djangoのマイグレーション入門")
        self.assertNotContains(response, "Nginxのリバースプロキシ")

    def test_matches_body(self):
        response = self.client.get(self.url, {"q": "proxy_pass"})
        self.assertContains(response, "Nginxのリバースプロキシ")

    def test_draft_is_never_found(self):
        """検索は published() を通すので、下書きは絶対に出ない。"""
        response = self.client.get(self.url, {"q": "下書き"})
        self.assertNotContains(response, "下書きのDjango記事")

    def test_multiple_terms_are_and_search(self):
        response = self.client.get(self.url, {"q": "Django マイグレーション"})
        self.assertContains(response, "Djangoのマイグレーション入門")

        response = self.client.get(self.url, {"q": "Django proxy_pass"})
        self.assertNotContains(response, "Djangoのマイグレーション入門")

    def test_empty_query_shows_form_without_error(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "一致する記事が見つかりませんでした")

    def test_no_result_message(self):
        response = self.client.get(self.url, {"q": "存在しない語句zzz"})
        self.assertContains(response, "一致する記事が見つかりませんでした")

    def test_query_is_escaped_in_output(self):
        """検索語をそのまま画面へ戻すため、エスケープを確認する（反射型XSS対策）。"""
        response = self.client.get(self.url, {"q": "<script>alert(1)</script>"})
        self.assertNotContains(response, "<script>alert(1)</script>", html=False)

    def test_long_query_is_truncated(self):
        response = self.client.get(self.url, {"q": "あ" * 500})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.context["query"]), 100)


class RelatedArticlesTests(TestCase):
    def setUp(self):
        from .factories import create_tag

        self.category = create_category(name="関連テスト")
        self.other_category = create_category(name="別分野")
        self.tag = create_tag(name="共通タグ")

        self.main = create_article(title="基準記事", category=self.category)
        self.main.tags.add(self.tag)

        self.same_tag = create_article(title="同じタグの記事", category=self.other_category)
        self.same_tag.tags.add(self.tag)

        self.same_category = create_article(title="同じカテゴリの記事", category=self.category)

        self.draft = create_article(
            title="関連の下書き",
            category=self.category,
            status=Article.Status.DRAFT,
        )
        self.draft.tags.add(self.tag)

    def test_related_includes_same_tag(self):
        titles = [a.title for a in self.main.related_articles()]
        self.assertIn("同じタグの記事", titles)

    def test_related_falls_back_to_same_category(self):
        titles = [a.title for a in self.main.related_articles()]
        self.assertIn("同じカテゴリの記事", titles)

    def test_related_excludes_self(self):
        titles = [a.title for a in self.main.related_articles()]
        self.assertNotIn("基準記事", titles)

    def test_related_excludes_drafts(self):
        titles = [a.title for a in self.main.related_articles()]
        self.assertNotIn("関連の下書き", titles)
