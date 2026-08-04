# 2日目に実際に起きたエラー

## 1. 管理画面の「サイト上で表示」が `NoReverseMatch` で落ちる

**症状**

管理画面から記事を1件開き、右上の「サイト上で表示」を押すと 500 になる。

```text
NoReverseMatch at /admin/blog/article/1/change/
Reverse for 'article_detail' not found.
```

**再現条件**

モデルに `get_absolute_url()` を定義したが、対応する URL パターンをまだ作っていない。

**原因**

Django の管理画面は、モデルに `get_absolute_url()` が **定義されているかどうか** を見て
「サイト上で表示」ボタンを出すか決めます。中身が動くかどうかは見ていません。

2日目は「モデルと管理画面まで」を作る日で、記事詳細ページは3日目に作ります。
つまり、この時点では

* `get_absolute_url()` は存在する → ボタンが出る
* `blog:article_detail` という URL は存在しない → 押すと落ちる

という食い違いが必ず起きます。

**直し方**

2日目のあいだだけ、Admin でボタンを消します。

```python
@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    # 3日目に一覧・詳細ビューを作ったらこの行を削除する
    view_on_site = False
```

3日目に URL を作った時点で、この行を消します。

**別の直し方（採用しなかった案）**

「3日目まで `get_absolute_url()` を書かない」という選択もあります。
採用しなかったのは、`get_absolute_url()` がモデルの一部として自然な情報であり、
テンプレートで `{{ article.get_absolute_url }}` と書けるようにしておきたかったためです。

**判断方法**

管理画面で記事を開き、「サイト上で表示」ボタンが消えていること。
3日目に行を削除したら、押して記事ページが開くこと。

---

## 2. `admin.E040: ... must define "search_fields"`

**症状**

`manage.py check` や `runserver` が次で止まる。

```text
<class 'blog.admin.ArticleAdmin'>: (admin.E040) CategoryAdmin must define "search_fields",
because it's referenced by ArticleAdmin.autocomplete_fields.
```

**再現条件**

`ArticleAdmin` に `autocomplete_fields = ("category", "tags")` を書いたが、
`CategoryAdmin` / `TagAdmin` に `search_fields` が無い。

**原因**

`autocomplete_fields` は「入力しながら候補を絞り込む」UI です。
絞り込みは **参照先の Admin の `search_fields`** を使って行われます。
検索対象が決まっていなければ候補を出せないため、Django が起動時に止めます。

これは実行時ではなくシステムチェックで検出されるので、
`runserver` した瞬間に分かります。放置して本番に出ることはありません。

**直し方**

参照先の Admin に `search_fields` を足します。

```python
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)
```

**判断方法**

```bash
python manage.py check
```

---

## 3. `autocomplete_fields` と `filter_horizontal` を同じフィールドへ指定する

**症状**

多対多フィールドの編集 UI が想定と違う（片方しか効かない）。

**原因**

`tags` に対して `autocomplete_fields` と `filter_horizontal` の両方を指定すると、
同じフィールドに2種類のウィジェットを割り当てることになります。
どちらか一方が無視されるため、「設定したのに変わらない」と見えます。

**直し方**

どちらか一方に決めます。この CMS では、タグが増えても扱いやすい
`autocomplete_fields` を採用しました。

```python
autocomplete_fields = ("category", "tags")
# filter_horizontal = ("tags",)  ← 併用しない
```

**判断方法**

管理画面の記事編集ページで、タグ欄が検索候補つきの入力欄になっていること。

---

## 4. 日本語だけのタイトルでスラッグが空になる

**症状**

例外は出ないが、記事の URL が `/articles//` のようになる、
または2件目の記事を保存したときに一意制約でエラーになる。

```text
UNIQUE constraint failed: blog_article.slug
```

**再現条件**

`django.utils.text.slugify()` に日本語だけの文字列を渡す。

```python
>>> from django.utils.text import slugify
>>> slugify("日本語だけのタイトル")
''
```

**原因**

`slugify()` は既定で ASCII 以外を落とします。
日本語だけのタイトルは、落とした結果が空文字になります。
空文字は1件目なら保存できてしまい、2件目で `unique=True` に衝突します。

**直し方**

空になった場合の代替を用意します。

```python
base = slugify(source, allow_unicode=False)[:max_length].strip("-")
if not base:
    base = f"post-{secrets.token_hex(4)}"
```

`slugify(..., allow_unicode=True)` にして日本語をそのまま URL に使う方法もありますが、
URL エンコードされて共有時に読みにくくなるため、この CMS では採用していません。

**判断方法**

```python
article = Article.objects.create(title="日本語だけのタイトル", ...)
assert article.slug  # 空でない
```

同じタイトルで2件作っても保存できること。
