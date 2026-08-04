"""開発用のデモデータを投入する。

    python manage.py seed_demo

本番では絶対に実行しない。既定のパスワードを持つユーザーを作るため、
DEBUG=False の環境では実行を拒否する。
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from blog.models import Article, Category, Tag
from pages.models import Page

User = get_user_model()

DEMO_PASSWORD = "demo-pass-phrase-1234"


class Command(BaseCommand):
    help = "開発用のデモ記事・カテゴリ・タグ・固定ページを作成する（DEBUG 時のみ）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="DEBUG=False でも実行する（推奨しない）",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False では実行できません。デモ用の既定パスワードを持つ"
                "ユーザーが作られるためです。"
            )

        author, created = User.objects.get_or_create(
            username="demo_author",
            defaults={"email": "demo_author@example.com", "display_name": "デモ投稿者"},
        )
        if created:
            author.set_password(DEMO_PASSWORD)
            author.save()
        for codename in ("add_article", "change_article", "delete_article"):
            author.user_permissions.add(
                Permission.objects.get(
                    content_type__app_label="blog", codename=codename
                )
            )

        categories = {}
        for name in ("Django入門", "セキュリティ", "運用"):
            categories[name], _ = Category.objects.get_or_create(name=name)

        tags = {}
        for name in ("django", "cms", "security"):
            tags[name], _ = Tag.objects.get_or_create(name=name)

        samples = [
            ("Djangoのプロジェクト構成を理解する", "Django入門", ["django"]),
            ("ORMでN+1クエリを避ける", "Django入門", ["django", "cms"]),
            ("CSRFトークンが守っているもの", "セキュリティ", ["security"]),
            ("アップロードファイルを拡張子で信用しない", "セキュリティ", ["security"]),
            ("systemdでDjangoを常駐させる", "運用", ["django"]),
        ]

        now = timezone.now()
        for index, (title, category_name, tag_names) in enumerate(samples):
            article, created = Article.objects.get_or_create(
                title=title,
                defaults={
                    "body": (
                        f"{title} についての本文です。\n\n"
                        "これはデモデータなので、内容には意味がありません。"
                    ),
                    "author": author,
                    "category": categories[category_name],
                    "status": Article.Status.PUBLISHED,
                    "published_at": now - timezone.timedelta(days=index),
                },
            )
            if created:
                article.tags.set([tags[name] for name in tag_names])

        # 未公開の記事も1件だけ作り、一覧に出ないことを目視確認できるようにする。
        Article.objects.get_or_create(
            title="【下書き】まだ公開していない記事",
            defaults={
                "body": "この記事は一覧に出てはいけない。",
                "author": author,
                "category": categories["運用"],
                "status": Article.Status.DRAFT,
            },
        )

        Page.objects.get_or_create(
            title="このサイトについて",
            defaults={
                "body": "KururuCMS は「10日で作る Django CMS」の成果物です。",
                "status": Page.Status.PUBLISHED,
                "published_at": now,
                "show_in_footer": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"デモデータを投入しました（記事 {Article.objects.count()} 件）。\n"
                f"投稿者: demo_author / パスワード: {DEMO_PASSWORD}"
            )
        )
