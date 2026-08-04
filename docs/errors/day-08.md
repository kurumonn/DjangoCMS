# 8日目に実際に起きたエラー

8日目は django-allauth の導入です。
テンプレートを1枚置き換えるだけの作業に見えて、**同じ罠を2回踏みました**。

---

## 1. `{# ... #}` は1行コメント専用（複数行に使うとタグが解釈される）

**症状**

allauth のレイアウトを差し替えた途端、認証画面がすべて 500 になった。

```text
django.template.exceptions.TemplateSyntaxError:
Unclosed tag on line 9: 'block'. Looking for one of: endblock.
```

「9行目の block が閉じていない」と言われますが、
9行目には `{% block %}` を **書いていません**。

**原因**

説明のためにファイル先頭へ書いた複数行コメントの中に、
`{% block content %}` という文字列が入っていました。

```django
{# django-allauth の画面を差し替えるための土台。

   * allauth の子テンプレートは {% block content %} を埋める。   ← ここ
     ここで content を再定義すると名前が衝突する。
#}
```

Django の `{# ... #}` は **1行コメント専用** です。
複数行にまたがって書くと、2行目以降はコメントとして扱われず、
中に書いたタグが本物として解釈されます。

**直し方**

複数行は `{% comment %} ... {% endcomment %}` を使います。

```django
{% comment %}
  * allauth の子テンプレートは content ブロックを埋める。
{% endcomment %}
```

コメントの中でタグの見た目を残したい場合は、
`{% templatetag openblock %}` などで組み立てます。

**判断方法**

```bash
python manage.py check
```

テンプレートの構文エラーは `check` では出ません（描画時に初めて読まれるため）。
実際にそのページを開くか、テストを1件通すのが確実です。

---

## 2. 同じ罠をもう一度踏んだ

上を直した直後、別のテンプレートで **まったく同じことをしました**。

```text
django.template.exceptions.TemplateSyntaxError:
'url' takes at least one argument, a URL pattern name.
```

`partials/account_nav.html` の冒頭コメントに、
`{% url %} を直接書くと落ちます` という説明文が入っていました。
この `{% url %}` が本物のタグとして解釈されていました。

**教訓**

「テンプレートの書き方を説明するコメント」は、
書いた説明そのものが実行されうる、という点で特別です。
`{% comment %}` を既定にしてしまうのが安全です。

---

## 3. `{% extends %}` はテンプレート内の最初のタグでなければならない

**症状**

1 を直したら、今度はこうなった。

```text
django.template.exceptions.TemplateSyntaxError:
{% extends "base.html" %} must be the first tag in 'allauth/layouts/base.html'.
```

**原因**

`{% comment %}` へ書き換えたコメントを、`{% extends %}` の **前** に置いていました。
`{% extends %}` は最初のタグでなければなりません。
`{# ... #}`（1行コメント）は前に置けますが、`{% comment %}` はタグなので置けません。

**直し方**

`{% extends %}` を1行目に置き、説明はその直後へ移します。

```django
{% extends "base.html" %}
{% comment %}
このファイルの役割 …
{% endcomment %}
```

**1 と 3 は互いに引っ張り合う**

* 複数行コメントにしたい → `{% comment %}` を使う必要がある
* `{% comment %}` はタグ → `{% extends %}` より前に置けない

結果として「extends を1行目、説明はその下」という形に落ち着きます。
最初からこの順序で書いていれば、両方とも踏みませんでした。

---

## 4. allauth の URL を二重に include して、リンク先が変わった

**症状**

テストは全部通っているのに、画面上の「ログイン中の端末」リンクが
`/accounts/sessions/` ではなく `/accounts/` を指していた。

**再現条件**

`allauth.urls` に加えて、`allauth.usersessions.urls` も個別に include した。

```python
path("accounts/", include("allauth.urls")),
path("accounts/", include("allauth.usersessions.urls")),   # ← 余計
```

**原因**

`allauth.urls` は、`INSTALLED_APPS` の中身を見て
`socialaccount` / `mfa` / `usersessions` の URL を **自動で足します**。

```python
# allauth/urls.py
urlpatterns += [path("sessions/", include("allauth.usersessions.urls"))]
```

個別に include すると、同じ URL 名 `usersessions_list` が2回登録されます。
Django の `reverse()` は **後から登録された方** を返すため、
自分で足した `/accounts/` の方が使われていました。

**なぜテストで気づけなかったか**

「ログインできる」「セッション一覧が見られる」というテストは通ります。
どちらの URL でもビューは同じだからです。
食い違うのは **リンクの文字列** だけで、動作は変わりません。

ブラウザーで開き、リンクの href を目で見たことで見つかりました。

**直し方**

個別の include を消します。

```python
# allauth.urls は INSTALLED_APPS を見て必要な URL を自動で足す。
# それぞれを個別に include してはいけない。
path("accounts/", include("allauth.urls")),
```

**判断方法**

URL 名がどこへ解決されるかを、テストで固定します。

```python
def test_usersessions_url_is_under_sessions(self):
    self.assertEqual(reverse("usersessions_list"), "/accounts/sessions/")
```

---

## 5. ワンタイムコードの形式が想定と違った

**症状**

「メールに届いたコードでログインできる」テストが落ちた。

```text
AssertionError: '' is not true : メール本文にコードが見つからない
```

**原因**

テストは6桁の数字を探していました。

```python
match = re.search(r"\b(\d{6})\b", message.body)
```

実際に届いたコードはこれでした。

```text
SHMK-ZHHG
```

allauth の既定は **英字8桁（4桁ずつハイフン区切り）** です。
しかも使う文字は `BCDFGHJKLMNPQRSTVWXZ` の20種類に限られています
（RFC 8628 に沿って、`0` と `O`、`1` と `I` のような紛らわしい組を除いてある）。

**直し方**

この CMS では、スマートフォンで入力しやすい数字6桁にしました。

```python
ACCOUNT_LOGIN_BY_CODE_FORMAT = {"numeric": True, "length": 6, "dashed": False}
```

**ただし、桁数を減らすなら防御をそろえること**

数字6桁は 100 万通りしかありません。単体では弱い設定です。
次の3つが **すべて** そろって初めて実用に耐えます。

| 防御 | 設定 | 値 |
| --- | --- | --- |
| 有効期限 | `ACCOUNT_LOGIN_BY_CODE_TIMEOUT` | 180 秒 |
| 試行回数 | `ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS` | 3 回 |
| 発行の制限 | `ACCOUNT_RATE_LIMITS["request_login_code"]` | 5分に3回 |

どれか1つを外すと総当たりが成立します。
「あとで緩めよう」と思ったときに気づけるよう、3つまとめてテストで固定しました。

```python
def test_login_code_defences_are_all_present(self):
    self.assertLessEqual(settings.ACCOUNT_LOGIN_BY_CODE_TIMEOUT, 600)
    self.assertLessEqual(settings.ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS, 5)
    self.assertIn("request_login_code", settings.ACCOUNT_RATE_LIMITS)
```

---

## 6. 確認メールの差出人が `example.com` のままだった

**症状（メール本文を実際に見て気づいた）**

ログインコードのメール本文がこうなっていました。

```text
こんにちは、example.com です!

以下にあなたのログインコードが記載されています。
...
example.com をご利用いただきありがとうございます!
```

**原因**

allauth のメールは `django.contrib.sites` の `Site` から
サイト名とドメインを取ります。
`Site` の初期値は `example.com` で、マイグレーションで自動作成されます。

この CMS はサイト名を `SiteSetting`（6日目に作ったモデル）で持っているので、
**設定の置き場所が2つに割れていました**。

**気づきにくい理由**

* 画面上はどこにも `example.com` が出ない
* テストも通る（メールの本文まで見ていなかった）
* 本番で気づいたときには、その文面のメールが既に配信済み

**直し方**

`SiteSetting` を保存したら `Site` も更新します。

```python
def save(self, *args, **kwargs):
    ...
    super().save(*args, **kwargs)
    self._sync_django_site()

def _sync_django_site(self) -> None:
    netloc = urlsplit(self.base_url).netloc
    if not netloc:
        return
    Site.objects.update_or_create(
        pk=settings.SITE_ID, defaults={"domain": netloc, "name": self.site_name}
    )
    # get_current() はキャッシュを持つので、明示的に捨てる
    Site.objects.clear_cache()
```

`Site.objects.clear_cache()` を忘れると、
同じプロセスの中では古い値が返り続けます。

**判断方法**

```python
def test_site_is_synced_with_site_setting(self):
    setting = SiteSetting.load()
    setting.base_url = "https://cms.example.jp"
    setting.site_name = "同期テストCMS"
    setting.save()

    site = Site.objects.get(pk=1)
    self.assertEqual(site.domain, "cms.example.jp")
    self.assertEqual(site.name, "同期テストCMS")
```

**メールは、実際に本文を読むまで確認したことにならない**

開発中は `EMAIL_BACKEND` をコンソールにしておき、
届く文面を必ず一度は目で読んでください。
「送信されたかどうか」だけを見ていると、この種の間違いは必ず残ります。

---

## この日の教訓

8日目のエラーは、**設定を1行変えるだけで挙動が変わり、しかも画面では気づけない**
種類のものばかりでした。

* URL の二重登録 → 動作は同じ、リンクだけ違う
* コードの形式 → テストを書いていなければ気づかない
* メールのサイト名 → 本文を読むまで分からない

だからこそ、8日目のテストは
「allauth が正しく動くか」ではなく
**「この CMS の設定が意図どおりか」** を固定する形にしています。
allauth 自体の動作は本家がテストしているので、
こちらが確かめるべきなのは設定の方です。
