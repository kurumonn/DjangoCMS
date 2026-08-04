# 6日目に実際に起きたエラー

6日目はサイドバーとキャッシュを足した日で、
**実装は正しいのにテストが落ちる** 種類の問題が3つ続けて出ました。
どれも初心者がつまずきやすく、原因が見えにくいものです。

---

## 1. サイトマップと RSS が空で返る（テスト間のキャッシュ汚染）

**症状**

サイトマップのテストが、作った覚えのない記事の URL を返す。

```text
AssertionError: Couldn't find '/articles/post-0f61a601/' in the following response
b'...<loc>https://testserver/articles/post-f8daebaf/</loc>...'
```

RSS のテストは、記事を作ったのに空のフィードが返る。

```text
b'<rss version="2.0"><channel><title>KururuCMS</title>...</channel></rss>'
```

**再現条件**

サイトマップと RSS に `cache_page` を付け、複数のテストで同じ URL を叩く。

```python
path("sitemap.xml", cache_page(60 * 60)(sitemap), {"sitemaps": SITEMAPS}, name="sitemap"),
path("feed/", cache_page(60 * 5)(LatestArticlesFeed()), name="feed"),
```

**原因**

Django のテストは、テストごとにデータベースをロールバックしますが、
**キャッシュはロールバックしません**。
既定のローカルメモリキャッシュはプロセス内に残り続けます。

その結果、最初に走ったテストが作った記事のサイトマップがキャッシュされ、
次のテストがそれをそのまま受け取ります。
「実装が壊れている」ように見えますが、実際にはキャッシュを見ているだけです。

**症状の見分け方**

* 単体で実行すると通るのに、まとめて実行すると落ちる
* 実行順を変えると、落ちるテストが変わる
* レスポンスに、そのテストが作っていないデータが入っている

この3つが揃ったら、まずキャッシュか、テスト間で共有している状態を疑います。

**直し方**

テストの前にキャッシュを捨てます。共通の基底クラスにまとめました。

```python
class CacheClearingTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
```

**判断方法**

まとめて実行しても、単体で実行しても、同じ結果になること。

```bash
python manage.py test seo
python manage.py test
```

---

## 2. サイドバーを足したら `assertNotContains` が落ちるようになった

**症状**

検索テストが「検索していない記事が結果に出ている」と言って落ちる。

```text
AssertionError: 'Nginxのリバースプロキシ' unexpectedly found in the following response
```

**再現条件**

`assertNotContains(response, "記事タイトル")` でページ全体の HTML を調べている状態で、
サイドバーに「最新記事」を追加する。

**原因**

サイドバーは、検索結果とは無関係に最新記事を表示します。
`assertNotContains` は HTML 全体を見るので、
**サイドバーに載っているだけ**で「見つかった」と判定されます。

実装は正しく、テストの調べ方が大雑把すぎた、というのが原因です。

**直し方**

「一覧の中身」を確かめたいときは、HTML ではなく `context` を見ます。

```python
def found_titles(response) -> set[str]:
    """検索ビューが実際に返した記事のタイトル。"""
    return {article.title for article in response.context["articles"]}


def test_matches_title(self):
    response = self.client.get(self.url, {"q": "マイグレーション"})
    titles = found_titles(response)
    self.assertIn("Djangoのマイグレーション入門", titles)
    self.assertNotIn("Nginxのリバースプロキシ", titles)
```

**ただし `assertNotContains` を全部やめてはいけない**

「下書きが漏れていないか」の確認は、ページ全体で見る必要があります。
一覧に出ていなくても、サイドバーやパンくずから漏れる可能性があるためです。

そこで、目的によって使い分けます。

```python
def test_draft_is_never_found(self):
    response = self.client.get(self.url, {"q": "下書き"})
    # 検索結果に出ない
    self.assertNotIn("下書きのDjango記事", found_titles(response))
    # ページのどこにも出ない
    self.assertNotContains(response, "下書きのDjango記事")
```

---

## 3. `assertNumQueries(3)` がコンテキストプロセッサ追加で壊れた

**症状**

N+1 を防ぐために書いたテストが、機能追加のたびに落ちる。

```text
AssertionError: 8 != 3 : 8 queries executed, 3 expected
```

**原因**

サイト設定とサイドバーをコンテキストプロセッサで足したので、
すべてのページでクエリが増えました。N+1 が起きたわけではありません。

`assertNumQueries(3)` のように **回数を固定** すると、
機能を足すたびに数字を書き換えるだけの作業が発生します。
そのうち「とりあえず数字を合わせる」ようになり、
本物の N+1 が混ざっても気づけなくなります。

**直し方**

見たいのは「記事が増えてもクエリが増えないこと」なので、
件数を変えて2回測り、同じであることを確認します。

```python
def test_list_query_count_does_not_grow_with_articles(self):
    def count_queries() -> int:
        cache.clear()
        reset_queries()
        self.client.get(url)
        return len(connection.queries)

    with override_settings(DEBUG=True):
        for i in range(5):
            create_article(title=f"N+1テストA{i}", category=self.category)
        count_queries()          # 1回目は捨てる（後述）
        baseline = count_queries()

        for i in range(15):
            create_article(title=f"N+1テストB{i}", category=self.category)
        grown = count_queries()

    self.assertEqual(baseline, grown)
```

これなら、コンテキストプロセッサを足しても落ちません。
`select_related()` を消すと落ちます。テストが見たいものだけを見るようになりました。

**補足: `connection.queries` は `DEBUG=True` でないと記録されない**

`override_settings(DEBUG=True)` を忘れると、常に 0 件になり、
`0 == 0` でテストが通ってしまいます。**通るのに何も検査していない**状態です。

---

## 4. 1回目のリクエストだけクエリ数が多い

**症状**

上のテストを書いたら、今度は逆向きに落ちた。

```text
AssertionError: 11 != 8 : 記事を増やしたらクエリが 11 → 8 に増えた（N+1 の疑い）
```

記事を増やしたのに、クエリが **減って** います。

**原因**

`SiteSetting.load()` は、行が無ければその場で作ります。

```python
@classmethod
def load(cls) -> "SiteSetting":
    obj, _ = cls.objects.get_or_create(pk=1)
    return obj
```

1回目のリクエストで `SELECT` → `SAVEPOINT` → `INSERT` → `RELEASE SAVEPOINT` の
4クエリが余計に走ります。2回目以降は `SELECT` だけです。

**直し方**

1回目は測らず、捨てます。

```python
count_queries()          # サイト設定の行を作らせるだけ
baseline = count_queries()
```

**判断方法**

`baseline` と `grown` が一致すること。
`with_related()` から `select_related("author")` を削ると落ちること
（テストが本当に N+1 を検出できるかの確認）。

---

## 5. コンテキストプロセッサが同じ SELECT を2回走らせる

**症状（エラーではなく無駄）**

クエリログを見ると、`seo_sitesetting` の SELECT が1ページで2回走っていた。

**原因**

コンテキストプロセッサを2つ登録し、どちらも `SiteSetting.load()` を呼んでいた。

```python
"seo.context_processors.site_settings",
"seo.context_processors.sidebar",
```

**直し方**

リクエストオブジェクトへ覚えさせ、1リクエスト1回にします。

```python
def get_site_setting(request) -> SiteSetting:
    cached = getattr(request, "_site_setting", None)
    if cached is None:
        cached = SiteSetting.load()
        request._site_setting = cached
    return cached
```

グローバルなキャッシュにしなかったのは、
設定変更の反映が遅れる問題と、キャッシュ破棄の書き忘れを避けるためです。
リクエスト内だけなら、失効を考える必要がありません。

**判断方法**

`DEBUG=True` でページを開き、`connection.queries` に
`seo_sitesetting` の SELECT が1回だけ出ること。

---

## 6. JSON-LD にタイトルをそのまま埋め込むと HTML が壊れる

**症状（テストで再現させた問題）**

記事タイトルに `</script>` が含まれると、
構造化データのブロックがそこで終わったことになり、以降の HTML が壊れる。

**原因**

ブラウザーは `<script>` の中身を JavaScript として読むより先に、
`</script>` という文字列でブロックの終わりを判断します。
JSON の文字列の中にあっても関係ありません。

テンプレートに手書きしていると、確実にこの問題が起きます。

```django
{# 危険な書き方 #}
<script type="application/ld+json">
{"headline": "{{ article.title }}"}
</script>
```

**直し方**

Python 側で `dict` を組み立て、`json.dumps` に任せたうえで `<` をエスケープします。

```python
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
# "<" を \u003C にすると "</script>" が生成されない。JSON としては同じ文字列。
payload = payload.replace("<", "\\u003C")
payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
return mark_safe(payload)
```

`\u2028` / `\u2029`（行区切り文字）も置き換えているのは、
これらが JavaScript の文法上そのままでは書けないためです。

**判断方法**

危険なタイトルの記事を作り、JSON として読み直せることを確認します。

```python
def test_script_tag_in_title_does_not_break_json_ld(self):
    article = create_article(title="危険な</script>タイトル", ...)
    response = self.client.get(article.get_absolute_url())
    blocks = self._extract_json_ld(response.content.decode())
    posting = next(b for b in blocks if b["@type"] == "BlogPosting")
    self.assertEqual(posting["headline"], "危険な</script>タイトル")
```

---

## 7. サイトマップと canonical URL が別のドメインを指していた

**症状**

テストは全部通っていたのに、ブラウザーで実際に開いて確認したら、
同じサイトの中で3種類のドメインが出ていました。

```text
robots.txt   Sitemap: http://localhost:8000/sitemap.xml   ← サイト設定の値
sitemap.xml  <loc>https://localhost:8810/articles/...</loc> ← 実際のホスト名
```

開発サーバーは 8810 番で動いていたので、`robots.txt` が案内する
`localhost:8000/sitemap.xml` は存在しません。

**原因**

絶対URLの出所が2つありました。

| 出力 | 使っていたもの |
| --- | --- |
| canonical / OGP / JSON-LD / robots.txt | `SiteSetting.base_url` |
| sitemap.xml / RSS | リクエストのホスト名 |

`django.contrib.sitemaps` は、`django.contrib.sites` が入っていない場合、
リクエストの `Host` ヘッダーからドメインを組み立てます。
RSS の `Feed` も同じです。

開発中は両方 `localhost` なので気づきにくいのですが、本番では次のように壊れます。

```text
canonical : https://cms.example.com/articles/hello/
sitemap   : https://cms.internal.local/articles/hello/
```

リバースプロキシの背後で内部ホスト名が渡ったときや、
`www` あり／なしが混ざったときに実際に起きます。
検索エンジンから見ると「サイトマップに載っている URL と、
そのページが名乗る正規 URL が違う」状態になり、どちらを登録すべきか判断できません。

**なぜテストで気づけなかったか**

テストクライアントは常に `testserver` というホスト名を使います。
サイトマップも canonical も `testserver` になるので、食い違いが表に出ませんでした。

**テストだけでは見つからない種類のバグです。**
実際にサーバーを起動して、出力を目で見たことで見つかりました。

**直し方**

サイトマップは、Django が用意している `get_domain()` / `get_protocol()` を上書きします。
`get_urls()` を丸ごと差し替えると、ページ分割や `lastmod` の扱いまで
自前で面倒を見ることになるので避けます。

```python
class ConfiguredDomainSitemap(Sitemap):
    def _parts(self):
        return urlsplit(SiteSetting.load().base_url)

    def get_domain(self, site=None):
        netloc = self._parts().netloc
        return netloc or super().get_domain(site)

    def get_protocol(self, protocol=None):
        scheme = self._parts().scheme
        return scheme or super().get_protocol(protocol)
```

RSS は、絶対URLを返すようにします。
Django の `add_domain()` は、すでに `http://` / `https://` で始まる URL を
そのまま通すため、これだけで設定のドメインが使われます。

```python
def link(self):
    return self.setting.absolute_url(reverse("blog:article_list"))

def item_link(self, item):
    return self.setting.absolute_url(item.get_absolute_url())
```

**そして、ここで1か所だけ直し漏れました**

上の2つを直してテストを走らせたら、まだ内部ホスト名が残っていました。

```text
AssertionError: 'internal.local' unexpectedly found in
'...<atom:link href="http://internal.local/feed/" rel="self"/>...'
```

`<atom:link rel="self">`（フィード自身の URL）は、
`link()` でも `item_link()` でもなく `feed_url()` から作られます。
既定では `request.path` を使うため、ここだけ取り残されていました。

```python
class LatestArticlesFeed(Feed):
    self_url_name = "seo:feed"

    def feed_url(self, obj=None) -> str:
        return self.setting.absolute_url(reverse(self.self_url_name))


class LatestArticlesAtomFeed(LatestArticlesFeed):
    feed_type = Atom1Feed
    self_url_name = "seo:feed_atom"
```

**判断方法**

設定と違うホスト名でアクセスしても、出力が設定どおりになることを確認します。

```python
def test_absolute_urls_use_configured_domain(self):
    setting = SiteSetting.load()
    setting.base_url = "https://cms.example.com"
    setting.save()

    create_article(title="ドメインテスト", category=self.category)
    with override_settings(ALLOWED_HOSTS=["internal.local", "testserver"]):
        response = self.client.get(self.url, headers={"host": "internal.local"})

    body = response.content.decode()
    self.assertIn("https://cms.example.com/articles/", body)
    self.assertNotIn("internal.local", body)
```

`override_settings(ALLOWED_HOSTS=...)` を忘れると Django が 400 を返し、
サイトマップの中身を見る前に終わります。私は最初これを忘れて、
「サイトマップが空だ」と勘違いしました。

```text
AssertionError: 'https://cms.example.com/articles/' not found in
'<h1>Bad Request (400)</h1>'
```

---

## 8. RSS のインスタンスにサイト設定をキャッシュしてはいけない

**症状（レビュー中に気づいた問題）**

管理画面でサイト名を変えても、RSS のタイトルが変わらない。

**原因**

`Feed` のインスタンスは、URLconf の読み込み時に **1個だけ** 作られます。

```python
path("feed/", cache_page(60 * 5)(LatestArticlesFeed()), name="feed"),
```

このインスタンスはプロセスが生きているあいだ使い回されるので、
`self._setting` へ結果を覚えさせると、**プロセスを再起動するまで**古い値が返り続けます。

「開発中は runserver が自動再起動するので気づかず、本番だけ直らない」
という、いちばん厄介な種類の不具合になります。

**直し方**

インスタンスへ覚えさせず、毎回読みます。
フィード自体が `cache_page` で5分キャッシュされるので、負荷はほぼ増えません。

```python
@property
def setting(self) -> SiteSetting:
    return SiteSetting.load()
```

**判断方法**

```python
def test_feed_reflects_setting_change_without_restart(self):
    setting.site_name = "変更前サイト"
    setting.save()
    self.assertIn("変更前サイト", self.client.get(self.url).content.decode())

    setting.site_name = "変更後サイト"
    setting.save()
    cache.clear()
    self.assertIn("変更後サイト", self.client.get(self.url).content.decode())
```

---

## この日の教訓

6日目に出た8件のうち、

* テストが教えてくれたもの … 5件
* テストは通っていて、**実際に開いて初めて分かった**もの … 1件（サイトマップのドメイン）
* コードを読み返して気づいたもの … 2件

テストは「壊れたことに気づく」ためのものであって、
「正しいことを保証する」ものではありません。
テストクライアントは常に `testserver` を名乗るので、
ホスト名にまつわる不具合は原理的に検出できませんでした。

**動かして目で見る工程を省かないこと。**
これが6日目にいちばんはっきりした教訓です。
