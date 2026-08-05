# 【1日目】Django CMS 開発を始めよう――環境構築からカスタムユーザーまで

> 連載「10日で作る Django CMS」の1日目です。
> 成果物: <https://github.com/kurumonn/DjangoCMS>（タグ `day-01`）

---

## 1. 今日の結論

**今日やること**は、次の5つです。

1. Python の仮想環境を作り、Django をインストールする
2. `config` プロジェクトと `accounts` / `blog` アプリを作る
3. **カスタムユーザーモデルを、最初の `migrate` より前に作る**
4. トップページを表示する
5. Git リポジトリを作る

**今日いちばん大事なのは 3 です。** 残りは後からいくらでも直せますが、
カスタムユーザーモデルだけは後から差し替えるのが極端に難しくなります。
理由は「6. 内部で起きていること」で説明します。

---

## 2. 今日の完成画面

トップページが表示されれば1日目は完了です。

```text
ブラウザー
   ↓  GET /
config/urls.py        ← どの View に渡すか決める
   ↓
blog/views.py         ← リクエストを受け取る
   ↓
templates/blog/index.html   ← HTML を組み立てる
   ↓
トップページが表示される
```

---

## 3. 今日変更するファイル

```text
DjangoCMS/
├── manage.py                 新規
├── config/
│   ├── __init__.py           新規
│   ├── settings.py           新規
│   ├── urls.py               新規
│   ├── wsgi.py               新規
│   └── asgi.py               新規
├── accounts/
│   ├── __init__.py           新規
│   ├── apps.py               新規
│   └── models.py             新規  ← 今日の主役
├── blog/
│   ├── __init__.py           新規
│   ├── apps.py               新規
│   └── views.py              新規
├── templates/
│   ├── base.html             新規
│   └── blog/index.html       新規
├── static/css/site.css       新規
├── requirements.txt          新規
└── .gitignore                新規
```

---

## 4. 完成コード

### 4.1 仮想環境と Django のインストール

```bash
python -m venv .venv
```

仮想環境を有効化します。ここだけ OS で書き方が違います。

<div class="env-block env-linux env-macos">

**Linux / macOS**

```bash
source .venv/bin/activate
```

</div>

<div class="env-block env-windows">

**Windows (PowerShell)**

```powershell
.venv\Scripts\Activate.ps1
```

初回は実行ポリシーで止められることがあります。
その場合は、**現在のユーザーに対してのみ**署名付きスクリプトを許可します。

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

`-Scope CurrentUser` を付けるのが要点です。付けないと機械全体の設定を変えることになります。

</div>

Django と、パスワードハッシュに使う `argon2-cffi` を入れます。

```bash
pip install Django==5.2.17 argon2-cffi
```

> **版を `==` で固定する理由と、その代わりに負う責任**
>
> `==` で固定すると「昨日は動いたのに今日は動かない」が無くなります。
> ただし固定は「変わらない」ことを保証するだけで、
> **「安全であり続ける」ことは保証しません**。
>
> この記事は当初 `Django==5.2.15` で書いていましたが、
> 2026年8月4日に公開された Django 5.2.17 が
> 4件の脆弱性（RCE・SSRF・DoS・格納型XSS）を修正したため、5.2.17 へ更新しました。
> 5.2.15 は、それ以前に修正された分の影響も受けます。
>
> Django 5.2 は LTS（2028年4月までサポート）ですが、
> サポートされるのは **5.2 系列の最新パッチ**です。
> 「LTS だから安全」ではありません。
>
> どの脆弱性がこのプロジェクトに到達するかを実際に確かめた記録は
> [`docs/security-updates.md`](https://github.com/kurumonn/DjangoCMS/blob/main/docs/security-updates.md)
> にあります。4件のうち3件は「この構成では踏まない」と判断できましたが、
> **判断できたことと、更新しなくてよいことは別**です。

### 4.2 プロジェクトとアプリの作成

```bash
django-admin startproject config .
```

```bash
python manage.py startapp accounts
```

```bash
python manage.py startapp blog
```

`django-admin startproject config .` の末尾の `.`（ドット）を忘れないでください。
これが無いと `config/config/settings.py` という一段深い構成になります。

### 4.3 カスタムユーザーモデル

```python
# accounts/models.py
"""CMS のユーザーモデル。

Django のユーザーモデルは、プロジェクト開始直後に確定させる。
記事の著者・コメント・権限がすべてこのモデルを外部キーで参照するため、
運用開始後の差し替えは大規模な移行作業になる。
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """KururuCMS で使用するユーザー。

    AbstractUser を継承しているので、username / password / is_staff /
    is_superuser / groups / user_permissions といった標準機能はそのまま使える。
    ここでは CMS に必要な項目だけを追加する。
    """

    # 標準の User は email が重複可能。ログインIDとして使うため一意にする。
    email = models.EmailField("メールアドレス", unique=True)

    display_name = models.CharField(
        "表示名",
        max_length=50,
        blank=True,
        help_text="記事の著者名として表示される。空ならユーザー名を使う。",
    )
    bio = models.TextField("プロフィール", blank=True, default="")

    class Meta:
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー"

    def __str__(self) -> str:
        return self.display_name or self.username

    @property
    def byline(self) -> str:
        """記事に表示する著者名。"""
        return self.display_name or self.username
```

### 4.4 settings.py の要点

長いので、今日の要点だけを抜き出します。

```python
# config/settings.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- 秘密情報 -------------------------------------------------------------
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError(
            "DJANGO_SECRET_KEY が未設定です。本番では環境変数で必ず指定してください。"
        )
    SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# 管理画面のパスを環境変数で変えられるようにする。
# 既定の /admin/ は総当たり攻撃の標的になりやすい。
ADMIN_URL_PATH = os.environ.get("DJANGO_ADMIN_URL_PATH", "admin").strip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 自作アプリ
    "accounts",
    "blog",
]

# --- 認証 -----------------------------------------------------------------
# ★最重要★ カスタムユーザーモデルは「最初の migrate より前」に指定する。
AUTH_USER_MODEL = "accounts.User"

# Argon2 を第一候補にする。Django 標準の PBKDF2 より攻撃コストが高い。
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- 国際化 ---------------------------------------------------------------
LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

# --- セキュリティ既定値 ---------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
```

### 4.5 URLconf

```python
# config/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
    path("", include("blog.urls")),
]

if settings.DEBUG:
    # 開発時のみ Django がメディアファイルを配信する。
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### 4.6 View とテンプレート

```python
# blog/views.py
from django.views.generic import TemplateView


class IndexView(TemplateView):
    """CMS のトップページ。"""

    template_name = "blog/index.html"
```

```python
# blog/urls.py
from django.urls import path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
]
```

---

## 5. コードの意味

### `class User(AbstractUser)`

| コード | 意味 |
| --- | --- |
| `class` | 新しい設計図を定義する Python の命令 |
| `User` | 今回作るユーザーモデルの名前 |
| `AbstractUser` | Django 標準ユーザーの機能（パスワード・権限・グループ）を引き継ぐ |
| `models.EmailField` | メールアドレス形式を検証するフィールド |
| `unique=True` | 同じメールアドレスの重複登録を禁止する |
| `blank=True` | フォーム上で空欄を許す（DB の NULL とは別の話） |
| `AUTH_USER_MODEL` | プロジェクトで使うユーザーモデルを Django へ教える設定 |

### `blank=True` と `null=True` の違い

初心者がよく混同するところです。

| | 意味 | 対象 |
| --- | --- | --- |
| `blank=True` | フォームで空欄を許す | 入力の検証 |
| `null=True` | データベースに NULL を保存できる | データベース |

文字列のフィールドには `null=True` を付けません。
「空文字」と「NULL」という2種類の"空"ができてしまい、
検索条件をそのつど両方書く羽目になります。

```python
# 良い書き方
bio = models.TextField("プロフィール", blank=True, default="")

# 避ける書き方（空の状態が2種類できる）
bio = models.TextField("プロフィール", blank=True, null=True)
```

### `@property` を付けた `byline`

```python
@property
def byline(self) -> str:
    return self.display_name or self.username
```

| 部分 | 意味 |
| --- | --- |
| `@property` | メソッドを「属性のように」呼べるようにする |
| `a or b` | `a` が空文字・None なら `b` を返す Python の書き方 |

テンプレートからは `{{ user.byline }}` と書けます。
`{{ user.byline() }}` のようにカッコを付けないのが Django テンプレートの流儀です。

このメソッドを用意しておくと、
「表示名があればそれ、無ければユーザー名」という判断が1か所にまとまります。
テンプレートで `{% if %}` を書くと、表示箇所が増えるたびに同じ分岐が増えます。

---

## 6. 内部で起きていること

### なぜカスタムユーザーモデルを最初に作るのか

Django のプロジェクトでは、**多くのテーブルがユーザーを外部キーで参照します**。

```text
accounts_user
    ↑ 外部キー
    ├── blog_article.author_id       記事の著者
    ├── comments_comment.author_id   コメントの投稿者
    ├── django_admin_log.user_id     管理画面の操作ログ
    ├── auth_user_groups             所属グループ
    └── auth_user_user_permissions   個別の権限
```

`migrate` を1回でも実行すると、これらのテーブルが
**その時点のユーザーモデルを指した状態で** 作られます。

後からユーザーモデルを差し替えると、次を全部やり直すことになります。

1. 既存のマイグレーションをすべて削除する
2. データベースを作り直す
3. 本番にデータがあれば、手作業で移行する

Django の公式ドキュメントも「プロジェクト開始時に必ず設定すること」と書いています。

**1日目に作ってしまえば、この問題は起きません。**
認証機能を実装するのは8日目ですが、**設計だけは今日済ませます**。

### `makemigrations` と `migrate` の関係

```text
accounts/models.py（Python のクラス）
        ↓  makemigrations
accounts/migrations/0001_initial.py（設計図）
        ↓  migrate
データベースのテーブル（accounts_user）
```

`makemigrations` は **ファイルを作るだけ** で、データベースには触りません。
`migrate` が、その設計図どおりに `CREATE TABLE` を実行します。

分かれている理由は、**設計図を Git で共有するため**です。
チームの全員が同じ `0001_initial.py` を受け取って `migrate` すれば、
全員のデータベースが同じ形になります。

---

## 7. コマンドの説明

### `python -m venv .venv`

| 項目 | 内容 |
| --- | --- |
| 目的 | このプロジェクト専用の Python 環境を作る |
| 実行場所 | プロジェクトのルート |
| 正常例 | 何も表示されず、`.venv/` ができる |
| 異常例 | `No module named venv`（Python が不完全） |
| 判断方法 | `.venv/` の中に `Scripts`（Windows）か `bin`（Linux）がある |

仮想環境を使うのは、プロジェクトごとにライブラリの版を分けるためです。
分けないと、別のプロジェクトで Django を更新した瞬間にこちらが壊れます。

### `python manage.py makemigrations`

| 項目 | 内容 |
| --- | --- |
| 目的 | モデルの変更をマイグレーションファイルへ変換する |
| 実行場所 | `manage.py` があるディレクトリ |
| 正常例 | `Migrations for 'accounts': accounts/migrations/0001_initial.py + Create model User` |
| 異常例 | `No installed app with label 'accounts'`（`INSTALLED_APPS` へ追加していない） |
| 判断方法 | `accounts/migrations/` に新しいファイルができている |

`No changes detected` と出たら、モデルを変更していないか、
`INSTALLED_APPS` にアプリを登録し忘れています。

### `python manage.py migrate`

| 項目 | 内容 |
| --- | --- |
| 目的 | マイグレーションファイルの内容をデータベースへ適用する |
| 実行場所 | `manage.py` があるディレクトリ |
| 正常例 | `Applying accounts.0001_initial... OK` が並ぶ |
| 異常例 | `InconsistentMigrationHistory`（ユーザーモデルを後から変えた） |
| 判断方法 | `python manage.py showmigrations` で `[X]` が付く |

### `python manage.py createsuperuser`

| 項目 | 内容 |
| --- | --- |
| 目的 | 管理画面へログインできる最初のユーザーを作る |
| 正常例 | `Superuser created successfully.` |
| 異常例 | `That email address is already taken.` |
| 判断方法 | 管理画面へログインできる |

### `python manage.py runserver`

| 項目 | 内容 |
| --- | --- |
| 目的 | 開発用のサーバーを起動する |
| 正常例 | `Starting development server at http://127.0.0.1:8000/` |
| 異常例 | `That port is already in use.`（別のプロセスが使用中） |
| 判断方法 | ブラウザーでトップページが開ける |

このサーバーは **開発専用** です。本番では使いません（デプロイ編5日目）。

---

## 8. よくあるエラー

ここに書くのは、この CMS を実際に作る途中で **本当に出たエラー** だけです。
記録は [`docs/errors/day-01.md`](../errors/day-01.md) にあります。

### 8.1 `AttributeError: 'Settings' object has no attribute 'ADMIN_URL_PATH'`

```text
File "config/urls.py", line 14, in <module>
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
AttributeError: 'Settings' object has no attribute 'ADMIN_URL_PATH'
```

**原因**: `urls.py` で参照した設定を `settings.py` へ書き忘れています。

つまずきやすいのは、**画面を1つも開いていないのにエラーが出る**点です。
`urls.py` は「リクエストが来たとき」ではなく「プロジェクト起動時」に実行されます。
トレースバックの一番下ではなく、`File "config/urls.py"` の行を見てください。

**確認**:

```bash
python manage.py check
```

### 8.2 `NoReverseMatch: Reverse for 'login' not found`

**原因**: テンプレートに `{% url 'login' %}` と書いたのに、
URLconf にログイン画面を登録していません。

`settings.LOGIN_URL = "login"` を書いただけでは URL は作られません。
`LOGIN_URL` は「ログインが必要なときにどこへ送るか」の設定であって、
そこにページを用意する設定ではありません。

この連載では、ログイン画面は3日目に追加します。
1日目のテンプレートには、ログインリンクを置いていません。

**確認**:

```bash
python manage.py shell -c "from django.urls import reverse; print(reverse('login'))"
```

### 8.3 仮想環境を有効にしないまま `manage.py` を実行する

```text
ImportError: Couldn't import Django.
```

`pip install` したシェルと、`python manage.py` を実行しているシェルが別です。
Windows で PowerShell とコマンドプロンプトを行き来したときに起きがちです。

**確認** — どの Python が使われているかを見ます。

<div class="env-block env-windows">

**Windows (PowerShell)**

```powershell
(Get-Command python).Source
```

</div>

<div class="env-block env-linux env-macos">

**Linux / macOS**

```bash
which python
```

</div>

プロジェクト内の `.venv` を指していれば正しい状態です。

---

## 9. 動作確認

- [ ] `python manage.py check` が `System check identified no issues` を返す
- [ ] `python manage.py makemigrations accounts` が `Create model User` を表示する
- [ ] `python manage.py migrate` がエラーなく完了する
- [ ] `python manage.py createsuperuser` でユーザーを作れる
- [ ] `http://127.0.0.1:8000/` でトップページが HTTP 200 で表示される
- [ ] 管理画面にログインでき、「ユーザー」の一覧に `display_name` 欄がある
- [ ] `accounts/migrations/0001_initial.py` が Git に含まれている

最後の項目は見落としがちです。
マイグレーションファイルは **必ず Git にコミットします**。
`.gitignore` へ入れてしまうと、他の人の環境でテーブルが作られません。

---

## 10. セキュリティ上の注意

1日目から入れておく設定です。あとから足すより、最初から入っている方が確実です。

### `SECRET_KEY` をコードに書かない

`SECRET_KEY` はセッション署名や CSRF トークンの生成に使われます。
漏れると、ログイン状態を偽装される可能性があります。

この連載では、環境変数から読み、開発時だけフォールバックを許しています。

```python
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY が未設定です。")
    SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"
```

`DEBUG=False`（本番）で環境変数が無ければ **起動しない** ようにしています。
「うっかり開発用の鍵のまま本番へ出る」ことを防ぐためです。

### `.gitignore` を最初に書く

```gitignore
# 秘密情報 — 絶対にコミットしない
.env
.env.*
!.env.example
*.pem
*.key
id_ed25519
credentials.json
secrets/

# データベース
db.sqlite3
```

Git は一度コミットしたファイルを履歴から消すのが面倒です。
**最初のコミットの前**に `.gitignore` を用意してください。

### パスワードハッシュに Argon2 を使う

Django の既定は PBKDF2 です。動きますが、
Argon2 の方が「総当たりのコストを上げる」目的に向いています。

```bash
pip install argon2-cffi
```

```python
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    ...
]
```

既存のパスワードは、次回ログイン時に自動で新しい方式へ移行されます。

### 管理画面のパスを変える

```python
ADMIN_URL_PATH = os.environ.get("DJANGO_ADMIN_URL_PATH", "admin").strip("/")
```

これは「隠したから安全」という話ではありません。
`/admin/` は自動化された総当たりの標的になりやすく、
パスを変えるだけでログの雑音が大きく減ります。
**認証を強くすることの代わりにはなりません**（8日目・9日目で強くします）。

---

## 11. 今日の復習問題

**問1.** カスタムユーザーモデルを、最初の `migrate` より前に作らなければならないのはなぜですか。

**問2.** `blank=True` と `null=True` の違いを説明してください。
文字列のフィールドで `null=True` を避けるのはなぜですか。

**問3.** `makemigrations` と `migrate` は、それぞれ何をしますか。
2つに分かれている理由も答えてください。

**問4.** `SECRET_KEY` が漏れると、何ができてしまいますか。

<details>
<summary>解答</summary>

**問1.**
記事の著者・コメント・管理ログ・グループ・権限など、多くのテーブルが
ユーザーを外部キーで参照します。`migrate` を実行すると、それらのテーブルが
その時点のユーザーモデルを指した状態で作られます。
後から差し替えるには、マイグレーションの削除・データベースの作り直し・
本番データの手作業移行が必要になります。

**問2.**
`blank=True` はフォームで空欄を許す設定（入力の検証）、
`null=True` はデータベースに NULL を保存できる設定（データベース）です。
文字列で `null=True` を使うと「空文字」と「NULL」の2種類の"空"ができ、
検索条件を毎回2通り書くことになります。

**問3.**
`makemigrations` はモデルの変更を読み取り、マイグレーションファイル
（設計図）を作ります。データベースには触れません。
`migrate` はその設計図を読んで、実際に `CREATE TABLE` などを実行します。
分かれているのは、設計図を Git で共有し、
チーム全員が同じ手順でデータベースを再現できるようにするためです。

**問4.**
セッション Cookie の署名や CSRF トークンの生成に使われているため、
ログイン状態の偽装や、パスワード再設定リンクの偽造が可能になります。

</details>

---

## 12. Git の差分

```text
ブランチ: main
タグ    : day-01
コミット: day-01: Djangoプロジェクトの土台とカスタムユーザーモデルを作る
```

この日の状態を手元で動かします。

```bash
git clone https://github.com/kurumonn/DjangoCMS.git
```

```bash
git checkout day-01
```

---

## 13. 次回予告

2日目は、CMS の中心になる **記事モデル** を作ります。

- `Article` / `Category` / `Tag` / `Page` の4つのモデル
- 外部キー（`ForeignKey`）と多対多（`ManyToManyField`）の使い分け
- `on_delete` に何を指定すべきか
- 「公開済みの記事だけを取り出す」条件を1か所へまとめる設計
- 日本語のタイトルからスラッグを作るときの落とし穴

次回 → [【2日目】Django モデル入門](day-02.md)
