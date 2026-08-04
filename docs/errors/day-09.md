# 9日目に実際に起きたエラー

---

## 1. `KeyError: 'humanize'` でパスキー一覧だけが落ちる

**症状**

多要素認証の設定画面は開けるのに、パスキー一覧（`/accounts/2fa/webauthn/`）だけが 500 になる。

```text
KeyError: 'humanize'
```

**原因**

allauth の次のテンプレートが `naturaltime` フィルタを使っています。

* `mfa/webauthn/authenticator_list.html`（パスキー一覧）
* `usersessions/usersession_list.html`（ログイン中の端末）

このフィルタは `django.contrib.humanize` が提供します。
`INSTALLED_APPS` に入れていないと、**その画面だけ**落ちます。

**気づきにくい理由**

`manage.py check` は通ります。テンプレートは描画時に初めて読まれるためです。
「多要素認証を一通り試したつもり」でも、パスキー一覧を開いていなければ気づけません。

**直し方**

```python
INSTALLED_APPS = [
    ...
    "django.contrib.humanize",
    ...
]
```

**判断方法**

該当の画面を1つずつ開くテストを書きます。

```python
def test_staff_can_still_reach_mfa_setup(self):
    for name in ("mfa_index", "mfa_activate_totp", "mfa_list_webauthn"):
        with self.subTest(name=name):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
```

`subTest` を使うと、どの画面で落ちたかが出力に残ります。

---

## 2. `force_login()` では再認証が要る画面を開けない

**症状**

TOTP の設定画面を開くテストが 302 で落ちた。

```text
AssertionError: 302 != 200
```

ログインしているのに、設定画面へ入れません。

**原因**

`ACCOUNT_REAUTHENTICATION_REQUIRED = True` にしているため、
認証手段を追加・削除する画面は **直前にパスワードを入力したこと** を求めます。

`self.client.force_login(user)` はセッションへユーザーを入れるだけで、
「いつ本人確認したか」を記録しません。
そのため allauth は「再認証が必要」と判断してリダイレクトします。

**これはバグではなく、意図した動作**

セッションを盗まれても、パスワードを知らなければ
攻撃者が自分のパスキーを勝手に追加できない——という保護です。
むしろ、ここで 200 が返る方が危険です。

**直し方**

テストでも、実際にパスワードを入力してログインします。

```python
def _login_with_password(self):
    self.client.post(
        reverse("account_login"),
        {"login": self.user.email, "password": PASSWORD},
    )
```

そして「再認証を求めること」自体もテストにします。

```python
def test_totp_activation_requires_recent_authentication(self):
    self.client.force_login(self.user)
    response = self.client.get(reverse("mfa_activate_totp"))
    self.assertEqual(response.status_code, 302)
    self.assertIn("reauthenticate", response.url)
```

---

## 3. レート制限がテスト間で持ち越されて 429 になる

**症状**

単体では通るテストが、まとめて実行すると落ちる。

```text
AssertionError: 429 != 302
```

**原因**

allauth のログイン試行回数はキャッシュに記録されます。
Django のテストはデータベースをロールバックしますが、**キャッシュは戻しません**。

同じテストクラスの前のテストがログインを何度も試していると、
その回数が次のテストへ持ち越され、無関係なテストが 429 になります。

6日目の「サイトマップがテスト間で汚染される」問題と、原因はまったく同じです。

**直し方**

```python
def setUp(self):
    cache.clear()
    ...
```

**より根本的な対策**

キャッシュを使う機能が増えるたびに `cache.clear()` を書き足すのは漏れます。
共通の基底クラスを作るか、テスト用設定で
毎回新しいキャッシュを使う構成にしておくのが確実です。

---

## 4. `DEBUG` に紐づけた危険設定は、DEBUG の書き忘れで一緒に外れる

**症状（設計の見直し）**

最初、パスキーの安全装置をこう書いていました。

```python
# 開発中だけ緩め、本番では必ず False にする
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = DEBUG
```

一見すると正しく見えます。しかし問題が2つありました。

**問題1: DEBUG の書き忘れで保護まで一緒に外れる**

`DEBUG` の既定値は `True` です。

```python
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
```

本番で `DJANGO_DEBUG=0` を設定し忘れると、
`DEBUG=True` になるだけでなく、**WebAuthn の保護も同時に外れます**。
1つの設定ミスが2つの穴になります。

**問題2: テストで確かめられない**

Django のテストランナーは実行時に `settings.DEBUG` を `False` へ書き換えます。
しかし `MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN` は
**settings.py を読み込んだ時点**で計算済みなので、`True` のまま残ります。

```text
AssertionError: True is not false
```

このテストは「本番が安全か」を確かめているつもりで、何も確かめられていません。

**直し方**

独立した環境変数にしたうえで、**システムチェック**で検出します。

```python
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = (
    os.environ.get("DJANGO_MFA_ALLOW_INSECURE_ORIGIN", "1" if DEBUG else "0") == "1"
)
```

```python
# accounts/checks.py
@register(deploy=True)
def check_mfa_settings(app_configs, **kwargs):
    if settings.DEBUG:
        return []          # 開発中は何も言わない

    issues = []
    if getattr(settings, "MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN", False):
        issues.append(Error(
            "MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN が本番で有効になっています。",
            hint="環境変数 DJANGO_MFA_ALLOW_INSECURE_ORIGIN=0 を設定してください。",
            id="accounts.E001",
        ))
    return issues
```

**なぜテストではなくシステムチェックなのか**

| | 実行されるタイミング |
| --- | --- |
| テスト | 開発者が `manage.py test` を打ったときだけ |
| システムチェック | `runserver` でも `migrate` でも `check --deploy` でも必ず |

「本番で危険な設定になっていないか」は、
**実行し忘れようがない場所** に置くべきです。

実際に動かすと、こう出ます。

```bash
DJANGO_DEBUG=0 python manage.py check --deploy
```

```text
ERRORS:
?: (accounts.E002) メールの送信先がコンソールのままです。
	HINT: メール確認・ワンタイムコード・パスワード再設定が利用者へ届きません。
```

---

## 5. 編集者が他人の記事を編集できなかった（スクリーンショットで発見）

**症状**

記事用のスクリーンショットを撮ろうとしたら、編集画面が真っ白の 403 になった。

```text
403 Forbidden
```

テストは **252 件すべて通っていました**。

**原因**

権限判定がこうなっていました。

```python
def _can_edit(user, article):
    if not user.is_authenticated:
        return False
    if user.is_staff:          # ← ここだけ
        return True
    return article.author_id == user.pk
```

一方、5日目に作った役割の定義はこうです。

| 役割 | できること |
| --- | --- |
| 投稿者 | 自分の記事を作成・編集する |
| 編集者 | **すべての記事を確認・承認する** |

編集者には `blog.review_article` と `blog.change_article` を与えていましたが、
`_can_edit()` は `is_staff` しか見ていませんでした。

`is_staff` は「Django の管理画面へ入れる」という意味であって、
「編集者である」という意味ではありません。**この2つを混同していました**。

結果として、編集者は
「レビューして公開する役目なのに、本文を直せない」状態でした。

**なぜテストで気づけなかったか**

テストの `create_staff()` は `is_staff=True` を付けていました。
「スタッフは他人の記事を編集できる」というテストは通ります。

しかし **実運用の「編集者」グループには is_staff が付いていません**。
テスト用のユーザーと、実際に配る役割が食い違っていました。

7日目にも同じ食い違いを踏んでいます（コメント権限の不足）。
そのときは「気づける側」の食い違いでしたが、今回は
**テストが通ってしまう側**の食い違いでした。

**直し方**

役割の定義に合わせて、判定を直します。

```python
def _can_edit(user, article: Article) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    # 編集者（レビュー権限を持つ人）は、どの記事でも編集できる。
    if user.has_perm("blog.review_article"):
        return True
    return article.author_id == user.pk
```

自動保存 API も、独自の条件を書かずに同じ関数を使うよう直しました。

```python
# 画面側と同じ判定関数を使う。
# ここで独自の条件を書くと、画面では編集できるのに
# 自動保存だけ 403 になる、といった食い違いが起きる。
from blog.views import _can_edit

if not _can_edit(request.user, article):
    return _error("この記事を編集する権限がありません。", 403)
```

**判断方法**

「is_staff が無い編集者」で明示的にテストします。

```python
def test_editor_is_not_staff(self):
    """前提の確認。is_staff を付けずに編集できることが要点。"""
    self.assertFalse(self.editor.is_staff)

def test_editor_can_open_edit_form(self):
    self.client.login(username="edit-editor", password=PASSWORD)
    response = self.client.get(reverse("blog:article_update", args=[self.article.slug]))
    self.assertEqual(response.status_code, 200)

def test_plain_author_still_cannot_edit_others(self):
    """権限を広げすぎていないこと。"""
    ...
    self.assertEqual(response.status_code, 403)
```

**スクリーンショットを撮ったことで見つかった**

6日目のサイトマップの件に続いて、
**テストが全通過している状態で見つかった2件目のバグ**です。

どちらも「実際に画面を出して目で見た」ことが発見のきっかけでした。
記事用にスクリーンショットを撮る作業は、手間のように見えて、
実は一番安上がりな検査になっています。

---

## 6. 多要素認証を必須にしたら、既存のテストが3件落ちた

**症状**

```text
FAIL: test_staff_can_preview_any_draft      AssertionError: 302 != 200
FAIL: test_staff_can_edit_others_article    AssertionError: 302 != 200
FAIL: test_staff_can_autosave_others_article AssertionError: 302 != 200
```

**原因**

「管理者は多要素認証を登録するまで他の画面へ進めない」ミドルウェアを入れたためです。
テスト用の `create_staff()` が作るユーザーは、認証手段を登録していませんでした。

5日目にも同じことが起きています（公開権限を分離したら3日目のテストが落ちた）。
**バグではなく仕様変更** なので、直すのはテストの側です。

**直し方**

テスト用のスタッフも、実運用と同じ「多要素認証を登録済み」の状態にします。

```python
def create_staff(username="editor", **kwargs):
    """スタッフ（他人の記事も編集できる）。

    9日目に「管理者は多要素認証が必須」というミドルウェアを入れた。
    テスト用のスタッフも同じ状態にそろえないと、
    「テストでは動くのに実際には設定画面へ飛ばされる」という食い違いが起きる。
    """
    user = create_user(username=username, is_staff=True, **kwargs)
    user = grant(user, "blog.add_article", "blog.change_article", "blog.delete_article")
    add_totp(user)
    return user
```

**ミドルウェアを書くときに注意したこと**

必須化の実装は、次を通し忘れると **利用者が詰みます**。

| 通すべきもの | 通さないと |
| --- | --- |
| 多要素認証の設定画面 | 設定しに行けない（無限リダイレクト） |
| ログアウト | 抜け出せない |
| 再認証の画面 | 設定画面の手前で止まる |
| 静的ファイル | CSS が当たらず画面が崩れる |

```python
def test_staff_can_still_reach_mfa_setup(self):
    """設定ページ自体を塞ぐと、設定しに行けなくなる。"""

def test_staff_can_still_log_out(self):
    """ログアウトを塞ぐと詰む。"""
```

また、判定は「登録済みの認証手段があるか」で行い、
リカバリコードだけの状態は「設定済み」とみなしていません。

```python
return Authenticator.objects.filter(user=user).exclude(
    type=Authenticator.Type.RECOVERY_CODES
).exists()
```

リカバリコードは他の手段を失ったときの控えであって、
日常的に使う認証手段ではないためです。

---

## この日の教訓

9日目で分かったことは1つです。

**テストが全部通っていることと、正しく動くことは別物です。**

* 6日目 … サイトマップのドメイン（ブラウザーで開いて発見）
* 9日目 … 編集者の権限（スクリーンショットを撮ろうとして発見）

どちらも、テストの書き方が悪かったというより、
**テストの前提（テスト用ユーザーの作り方）が実運用とずれていた** ことが原因でした。

対策として有効だったのは次の2つです。

1. テスト用のユーザー生成を、実運用の役割定義（`setup_groups`）にそろえる
2. 記事用のスクリーンショットをスクリプトで自動撮影し、変更のたびに撮り直す

2 は特に効きます。撮り直しが一発で終わるので、
「とりあえず全画面を出してみる」ことへの心理的な抵抗が無くなります。

```bash
python tools/capture_screenshots.py
```
