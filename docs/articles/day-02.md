# 【2日目】Django モデル入門――記事・カテゴリ・タグをデータベースへ保存する

> 連載「10日で作る Django CMS」の2日目です。
> 成果物: <https://github.com/kurumonn/DjangoCMS>（タグ `day-02`）

---

## 1. 今日の結論

CMS の中心になる4つのモデルを作り、管理画面からデータを登録できるようにします。

- `Article`（記事）
- `Category`（カテゴリ／1記事に1つ）
- `Tag`（タグ／1記事に複数）
- `Page`（固定ページ）

**今日いちばん大事なのは、「公開してよい記事」の定義を1か所にまとめること**です。
この判定が散らばると、あとで必ず下書きが漏れます。

---

## 2. 今日の完成画面

管理画面から記事を登録できるようになります。

```text
Django 管理画面
   ├── ユーザー
   ├── 記事        ← 今日追加
   ├── カテゴリ    ← 今日追加
   ├── タグ        ← 今日追加
   └── 固定ページ  ← 今日追加
```

モデル同士の関係はこうなります。

```text
    User
     │ 1
     │
     │ 多
  Article ──── Category
     │  多      1
     │
     │ 多対多
     │
    Tag
```

---

## 3. 今日変更するファイル

```text
blog/
├── models.py        新規（今日の主役）
├── utils.py         新規（スラッグ生成）
├── admin.py         新規
├── migrations/
│   └── 0001_initial.py   自動生成
└── tests/
    ├── __init__.py       新規
    ├── factories.py      新規
    └── test_models.py    新規
pages/
├── models.py        新規
├── admin.py         新規
└── migrations/0001_initial.py
config/
└── settings.py      変更（INSTALLED_APPS へ pages を追加）
```

---

## 4. 完成コード

### 4.1 カテゴリとタグ

```python
# blog/models.py（抜粋）
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
```

### 4.2 記事モデル

```python
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
        return self.select_related("author", "category").prefetch_related("tags")


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

    @property
    def is_visible_to_public(self) -> bool:
        """一般利用者へ見せてよいか。published() と同じ判定をオブジェクト単位で行う。"""
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )
```

### 4.3 スラッグの自動生成

```python
# blog/utils.py
from __future__ import annotations

import secrets

from django.utils.text import slugify


def unique_slugify(model, source: str, *, instance=None, max_length: int = 200) -> str:
    """タイトルから一意なスラッグを作る。

    日本語だけのタイトルは slugify() の結果が空文字になる。
    その場合はランダムな英数字を割り当てて、URL が壊れないようにする。
    """
    base = slugify(source, allow_unicode=False)[:max_length].strip("-")
    if not base:
        # 日本語のみのタイトルなど、ASCII へ落とせなかった場合。
        base = f"post-{secrets.token_hex(4)}"

    candidate = base
    queryset = model.objects.all()
    if instance is not None and instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    # 衝突したら -2, -3 … と連番を足す。
    counter = 2
    while queryset.filter(slug=candidate).exists():
        suffix = f"-{counter}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
        counter += 1

    return candidate
```

### 4.4 管理画面

```python
# blog/admin.py
from django.contrib import admin

from .models import Article, Category, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "article_count")
    search_fields = ("name",)          # autocomplete_fields の前提になる
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="記事数")
    def article_count(self, obj: Category) -> int:
        return obj.articles.count()


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "status", "published_at")
    list_filter = ("status", "category", "tags")
    search_fields = ("title", "body")
    autocomplete_fields = ("category", "tags")
    date_hierarchy = "published_at"
    prepopulated_fields = {"slug": ("title",)}

    # 3日目に記事詳細ページを作るまで「サイト上で表示」を隠す。
    # get_absolute_url() はあるのに URL が無いため、押すと 500 になる。
    view_on_site = False

    def save_model(self, request, obj, form, change):
        # 著者が未設定なら、操作したユーザーを著者にする。
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)
```

---

## 5. コードの意味

### `ForeignKey` と `ManyToManyField`

| コード | 意味 |
| --- | --- |
| `ForeignKey` | 「多対一」。1つの記事は1人の著者・1つのカテゴリに属する |
| `ManyToManyField` | 「多対多」。1つの記事に複数のタグ、1つのタグに複数の記事 |
| `related_name="articles"` | 逆方向の名前。`category.articles.all()` と書けるようになる |
| `on_delete=models.PROTECT` | 参照されている間は削除させない |

`related_name` を指定しないと、Django は `article_set` という名前を作ります。
`category.article_set.all()` より `category.articles.all()` の方が読みやすいので、
明示的に付けています。

### `on_delete` の選び方

**この引数は必須です。** 省略できません。
「参照先が消えたとき、こちらをどうするか」を必ず決めさせる設計です。

| 値 | 動き | 使いどころ |
| --- | --- | --- |
| `CASCADE` | 一緒に削除する | 記事を消したらコメントも消す |
| `PROTECT` | 削除を拒否する（例外） | 記事があるカテゴリは消せない |
| `SET_NULL` | NULL にする（`null=True` が必要） | 画像を消しても記事は残す |
| `SET_DEFAULT` | 既定値にする | 「未分類」へ移す |
| `DO_NOTHING` | 何もしない | 原則使わない（不整合が残る） |

この CMS では、著者とカテゴリを `PROTECT` にしています。

```python
author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, ...)
```

もし `CASCADE` にすると、**退職者のアカウントを削除した瞬間に、
その人が書いた記事が全部消えます**。実際に起こりうる事故です。

`PROTECT` にしておくと、削除しようとした時点で例外になり、
「先に記事の著者を移してください」と気づけます。

### `settings.AUTH_USER_MODEL` と直接の import

```python
# 良い書き方
author = models.ForeignKey(settings.AUTH_USER_MODEL, ...)

# 避ける書き方
from accounts.models import User
author = models.ForeignKey(User, ...)
```

文字列で指定すると、アプリの読み込み順に依存しなくなります。
直接 import すると、循環 import が起きやすくなります。

### `TextChoices`

```python
class Status(models.TextChoices):
    DRAFT = "draft", "下書き"
    #       ↑ DB へ保存する値
    #                ↑ 画面に表示する名前
```

| 書き方 | 得られるもの |
| --- | --- |
| `Article.Status.DRAFT` | `"draft"`（DB の値） |
| `article.get_status_display()` | `"下書き"`（表示名） |
| `Article.Status.choices` | `[("draft", "下書き"), ...]` |

文字列を直に書かず定数にする理由は、打ち間違いを防ぐためです。
`status="drafts"` と書いても Python は何も言いませんが、
`Article.Status.DRAFTS` は `AttributeError` になります。

### カスタム QuerySet

```python
class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(...)

class Article(models.Model):
    objects = ArticleQuerySet.as_manager()
```

こう書くと、次のように使えます。

```python
Article.objects.published()
Article.objects.published().filter(category=cat)
Article.objects.filter(author=user).published()   # つなげられる
```

**なぜこうするのか。** 公開判定を View に直接書くと、こうなります。

```python
# 一覧ビュー
Article.objects.filter(status="published", published_at__lte=now)

# 検索ビュー
Article.objects.filter(status="published")          # ← 予約投稿が漏れる

# RSS
Article.objects.filter(status="published", published_at__lte=now)

# サイトマップ
Article.objects.all()                                # ← 下書きが漏れる
```

書く場所が増えるほど、書き漏らしが増えます。
**1か所にまとめれば、直すのも1か所で済みます。**

---

## 6. 内部で起きていること

### モデルからテーブルへ

```text
Python のクラス（blog/models.py）
        ↓  makemigrations
マイグレーションファイル（blog/migrations/0001_initial.py）
        ↓  migrate
データベースのテーブル
        blog_article
        blog_category
        blog_tag
        blog_article_tags   ← 多対多の中間テーブル（自動で作られる）
```

`ManyToManyField` を1つ書くと、Django は **中間テーブル** を自動で作ります。

```text
blog_article_tags
├── id
├── article_id  → blog_article.id
└── tag_id      → blog_tag.id
```

「記事1件にタグ3つ」なら、この表に3行入ります。

### `published()` が生成する SQL

```python
Article.objects.published()
```

```sql
SELECT ... FROM "blog_article"
WHERE "blog_article"."status" = 'published'
  AND "blog_article"."published_at" IS NOT NULL
  AND "blog_article"."published_at" <= '2026-08-04 05:00:00'
ORDER BY "blog_article"."published_at" DESC
```

`Meta.indexes` に付けたインデックスが、この `WHERE` と `ORDER BY` に効きます。

```python
indexes = [models.Index(fields=["status", "-published_at"])]
```

記事が数万件になると、あるとないとで応答時間が桁で変わります。

---

## 7. コマンドの説明

### `python manage.py makemigrations blog pages`

| 項目 | 内容 |
| --- | --- |
| 目的 | `blog` と `pages` のモデル変更を設計図にする |
| 正常例 | `Create model Category` `Create model Tag` `Create model Article` |
| 異常例 | `No changes detected`（`INSTALLED_APPS` への追加漏れ） |
| 判断方法 | `blog/migrations/0001_initial.py` ができている |

アプリ名を省略すると全アプリが対象になります。
どのアプリのマイグレーションを作るのか意識したい場合は、明示します。

### `python manage.py sqlmigrate blog 0001`

| 項目 | 内容 |
| --- | --- |
| 目的 | マイグレーションが実行する SQL を **表示するだけ**（実行しない） |
| 正常例 | `CREATE TABLE "blog_article" (...)` が表示される |
| 判断方法 | 意図した列・インデックスができるか目で確かめる |

`migrate` する前にこれを見る習慣を付けると、
「思っていたのと違うテーブルができた」を防げます。

### `python manage.py shell`

```python
>>> from blog.models import Article, Category
>>> Category.objects.create(name="Django入門")
<Category: Django入門>
>>> Article.objects.published().count()
0
```

管理画面を経由せずにモデルを触れます。
動きを確かめるのに一番早い方法です。

---

## 8. よくあるエラー

記録は [`docs/errors/day-02.md`](../errors/day-02.md) にあります。

### 8.1 管理画面の「サイト上で表示」が `NoReverseMatch` で落ちる

```text
NoReverseMatch at /admin/blog/article/1/change/
Reverse for 'article_detail' not found.
```

**原因**: モデルに `get_absolute_url()` を定義したが、
対応する URL パターンをまだ作っていません。

Django の管理画面は、`get_absolute_url()` が **定義されているかどうか** だけを見て
「サイト上で表示」ボタンを出します。中身が動くかは見ていません。

**対処**: 記事詳細ページを作る3日目まで、ボタンを隠します。

```python
@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    # 3日目に一覧・詳細ビューを作ったらこの行を削除する
    view_on_site = False
```

### 8.2 `admin.E040: ... must define "search_fields"`

```text
<class 'blog.admin.ArticleAdmin'>: (admin.E040) CategoryAdmin must define
"search_fields", because it's referenced by ArticleAdmin.autocomplete_fields.
```

**原因**: `autocomplete_fields` は「入力しながら候補を絞り込む」UI で、
絞り込みは **参照先の Admin の `search_fields`** を使います。
検索対象が決まっていないと候補を出せないため、Django が起動時に止めます。

**対処**:

```python
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)
```

これは起動時のシステムチェックで出るので、本番まで持ち越すことはありません。

### 8.3 日本語だけのタイトルでスラッグが空になる

```text
UNIQUE constraint failed: blog_article.slug
```

**原因**: `slugify()` は既定で ASCII 以外を落とします。

```python
>>> from django.utils.text import slugify
>>> slugify("日本語だけのタイトル")
''
```

空文字は1件目なら保存できてしまい、2件目で `unique=True` に衝突します。

**対処**: 空になった場合の代替を用意します。

```python
base = slugify(source, allow_unicode=False)[:max_length].strip("-")
if not base:
    base = f"post-{secrets.token_hex(4)}"
```

`slugify(..., allow_unicode=True)` で日本語をそのまま URL に使う方法もありますが、
共有時に URL エンコードされて読みにくくなるため、この CMS では採用していません。

### 8.4 `autocomplete_fields` と `filter_horizontal` の併用

同じフィールドに両方を指定すると、片方が無視されます。
「設定したのに UI が変わらない」と見えるので、どちらか一方に決めます。

---

## 9. 動作確認

- [ ] `python manage.py makemigrations blog pages` が4つのモデルを検出する
- [ ] `python manage.py migrate` が完了する
- [ ] 管理画面に「記事」「カテゴリ」「タグ」「固定ページ」が出る
- [ ] カテゴリを作らずに記事を保存しようとすると、エラーになる
- [ ] 記事があるカテゴリを削除しようとすると、保護されて削除できない
- [ ] タイトルが日本語だけの記事を2件作っても、両方保存できる
- [ ] `python manage.py test blog` が通る

削除保護は、管理画面から実際に試してみてください。
「削除できません」という画面が出れば `PROTECT` が効いています。

---

## 10. セキュリティ上の注意

### 公開判定を1か所にまとめる

今日の設計でいちばんセキュリティに効くのはここです。

```python
def published(self):
    return self.filter(
        status=Article.Status.PUBLISHED,
        published_at__isnull=False,
        published_at__lte=timezone.now(),
    )
```

この CMS では、次の**すべて**がこのメソッドを通ります。

- 記事一覧
- 記事詳細
- サイト内検索
- カテゴリ別・タグ別一覧
- RSS フィード
- XML サイトマップ
- 関連記事

1つでも `.all()` を使っている場所があれば、そこから下書きが漏れます。
特に **サイトマップと RSS は見落としやすい** です。
画面で隠せていても、サイトマップに URL が載れば
検索エンジンへ「下書きの存在と URL」を自分から教えることになります。

6日目で、この漏れを1つずつテストで固定します。

### `is_visible_to_public` を QuerySet と一致させる

オブジェクト単位の判定（`article.is_visible_to_public`）と、
QuerySet の判定（`Article.objects.published()`）は
**同じ条件でなければなりません**。

食い違うと、「一覧には出ないのに、直接 URL を叩くと見える」
という状態になります。

テストで固定しておきます。

```python
def test_is_visible_to_public_matches_queryset(self):
    for article in Article.objects.all():
        with self.subTest(article=article.title):
            in_queryset = Article.objects.published().filter(pk=article.pk).exists()
            self.assertEqual(article.is_visible_to_public, in_queryset)
```

### `PROTECT` でデータの消失を防ぐ

`CASCADE` は便利ですが、**削除の影響範囲が見えなくなります**。

```text
ユーザーを1人削除
   → その人の記事が全部消える（CASCADE）
      → その記事へのコメントも全部消える（CASCADE）
```

管理画面の削除確認では影響が一覧されますが、
シェルや管理コマンドから消すと、警告なしに実行されます。

「消えて困るもの」は `PROTECT` にして、
消す前に意識的な作業を要求するのが安全です。

---

## 11. 今日の復習問題

**問1.** `ForeignKey` はどのような関係を表しますか。`ManyToManyField` との違いも答えてください。

**問2.** `on_delete=models.CASCADE` は何を意味しますか。
記事の著者を `CASCADE` にすると、どのような事故が起きますか。

**問3.** `related_name` を指定する理由は何ですか。

**問4.** 公開判定を `published()` という1つのメソッドにまとめる利点を、
具体的な漏れの例を挙げて説明してください。

**問5.** 日本語だけのタイトルで記事を2件作ると、なぜ2件目で
`UNIQUE constraint failed` になるのですか。

<details>
<summary>解答</summary>

**問1.**
`ForeignKey` は「多対一」で、1つの記事が1人の著者・1つのカテゴリに属する関係です。
`ManyToManyField` は「多対多」で、1つの記事に複数のタグが付き、
1つのタグが複数の記事に付く関係です。
多対多では中間テーブルが自動で作られます。

**問2.**
参照先が削除されたとき、こちらのレコードも一緒に削除されます。
記事の著者を `CASCADE` にすると、
退職者のアカウントを削除しただけで、その人が書いた記事が全部消えます。
`PROTECT` にしておけば削除時に例外が出て、事前に気づけます。

**問3.**
関連先から逆方向にたどるときの名前を決めるためです。
指定しないと `category.article_set.all()` になりますが、
`related_name="articles"` を指定すると `category.articles.all()` と書けます。

**問4.**
記事一覧・詳細・検索・RSS・サイトマップ・関連記事など、
記事を取り出す場所は多数あります。
それぞれに条件を書くと、たとえばサイトマップだけ `.all()` のままにしてしまい、
下書き記事の URL を検索エンジンへ渡してしまう、といった漏れが起きます。
1か所にまとめれば、条件を直すのも1か所で済みます。

**問5.**
`slugify()` は ASCII 以外を落とすため、日本語だけのタイトルでは空文字を返します。
1件目は空文字のスラッグで保存できますが、
2件目も空文字になるため `unique=True` に違反します。

</details>

---

## 12. Git の差分

```text
タグ    : day-02
コミット: day-02: 記事・カテゴリ・タグ・固定ページのモデルを作る
```

前日から何が変わったかを見ます。

```bash
git diff day-01 day-02
```

この日の状態で動かします。

```bash
git checkout day-02
```

---

## 13. 次回予告

3日目は、モデルを画面につなぎます。

- 記事一覧・詳細・投稿・編集・削除（CRUD）
- ページネーション
- ログイン必須化と「自分の記事だけ編集できる」権限
- 未公開記事を **404 で隠す**（403 にしない理由）
- `select_related` / `prefetch_related` で N+1 クエリを防ぐ

次回 → [【3日目】Django CRUD 完全入門](day-03.md)
