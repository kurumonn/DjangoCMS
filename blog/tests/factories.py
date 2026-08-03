"""テスト用のオブジェクト生成ヘルパー。

外部ライブラリを増やさず、素の ORM だけで書く。
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from blog.models import Article, Category, Tag

User = get_user_model()


def create_user(username="author1", **kwargs):
    defaults = {
        "email": f"{username}@example.com",
        "password": "test-pass-phrase-1234",
    }
    defaults.update(kwargs)
    password = defaults.pop("password")
    user = User(username=username, **defaults)
    user.set_password(password)
    user.save()
    return user


def create_category(name="お知らせ", **kwargs):
    return Category.objects.create(name=name, **kwargs)


def create_tag(name="django", **kwargs):
    return Tag.objects.create(name=name, **kwargs)


def create_article(
    title="テスト記事",
    *,
    author=None,
    category=None,
    status=Article.Status.PUBLISHED,
    published_at="now",
    body="本文です。",
    **kwargs,
):
    """記事を1件作る。

    published_at に "now" を渡すと現在時刻、None を渡すとそのまま未設定になる。
    """
    if author is None:
        author = create_user(username=f"author-{Article.objects.count() + 1}")
    if category is None:
        category = Category.objects.first() or create_category()
    if published_at == "now":
        published_at = timezone.now()

    return Article.objects.create(
        title=title,
        author=author,
        category=category,
        status=status,
        published_at=published_at,
        body=body,
        **kwargs,
    )
