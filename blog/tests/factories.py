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


def grant(user, *codenames):
    """``app_label.codename`` 形式で権限を付与する。

    テストの中で「権限を持つ人／持たない人」を明示的に作り分けるために使う。
    """
    from django.contrib.auth.models import Permission

    for dotted in codenames:
        app_label, codename = dotted.split(".", 1)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label=app_label, codename=codename
            )
        )
    # 権限キャッシュを捨てて、追加した権限を即座に反映させる。
    if hasattr(user, "_perm_cache"):
        del user._perm_cache
    return User.objects.get(pk=user.pk)


def create_author(username="writer", **kwargs):
    """記事を投稿・編集・削除できる一般ユーザー。"""
    user = create_user(username=username, **kwargs)
    return grant(
        user, "blog.add_article", "blog.change_article", "blog.delete_article"
    )


def create_staff(username="editor", **kwargs):
    """スタッフ（他人の記事も編集できる）。"""
    user = create_user(username=username, is_staff=True, **kwargs)
    return grant(
        user, "blog.add_article", "blog.change_article", "blog.delete_article"
    )


def create_editor(username="reviewer", **kwargs):
    """編集者（承認と公開ができる）。"""
    user = create_user(username=username, **kwargs)
    return grant(
        user,
        "blog.add_article",
        "blog.change_article",
        "blog.delete_article",
        "blog.publish_article",
        "blog.review_article",
    )


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
