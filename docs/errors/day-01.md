# 1日目に実際に起きたエラー

## 1. `AttributeError: 'Settings' object has no attribute 'ADMIN_URL_PATH'`

**症状**

`runserver` を起動した瞬間、リクエストを1つも送っていないのに次で落ちる。

```text
File "config/urls.py", line 14, in <module>
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
AttributeError: 'Settings' object has no attribute 'ADMIN_URL_PATH'
```

**再現条件**

`config/urls.py` で独自の設定値を参照し、`config/settings.py` へ定義を書き忘れる。

**原因**

`urls.py` は「リクエストが来たとき」ではなく「プロジェクト起動時」に一度だけ実行される。
モジュールのトップレベルで `settings.XXX` を読むと、その時点で存在しない設定は即座に例外になる。

初心者がつまずきやすいのは、**画面を1つも開いていないのにエラーが出る**点です。
「どのページが悪いのか」を探しても見つかりません。トレースバックの一番下ではなく、
`File "config/urls.py"` の行を見るのが正解です。

**直し方**

`config/settings.py` に定義を追加する。

```python
ADMIN_URL_PATH = os.environ.get("DJANGO_ADMIN_URL_PATH", "admin").strip("/")
```

`.strip("/")` を付けているのは、環境変数に `/secret/` のようにスラッシュ付きで入れられても
`//secret//` という URL にならないようにするためです。

**判断方法**

```bash
python manage.py check
```

`System check identified no issues` と出れば読み込みは通っています。

---

## 2. `NoReverseMatch: Reverse for 'login' not found`

**症状**

トップページを開くと 500 になり、次が表示される。

```text
NoReverseMatch at /
Reverse for 'login' not found. 'login' is not a valid view function or pattern name.
```

**再現条件**

`base.html` に `{% url 'login' %}` と書いたが、`config/urls.py` に
`django.contrib.auth.urls` を include していない。

**原因**

`settings.LOGIN_URL = "login"` を書いただけでは URL は作られません。
`LOGIN_URL` は「ログインが必要なときにどこへ送るか」の設定であって、
そこに実際のページを用意する設定ではありません。

`{% url %}` は URLconf に登録された名前を逆引きするタグなので、
`urlpatterns` にパターンが無ければ必ず失敗します。

**直し方**

3日目まではログイン画面を作らない方針だったので、1日目は
テンプレートからログインリンクを外しました。

3日目に認証画面を作るとき、次を追加しています。

```python
path("accounts/", include("django.contrib.auth.urls")),
```

**判断方法**

```bash
python manage.py shell -c "from django.urls import reverse; print(reverse('login'))"
```

`/accounts/login/` と表示されれば逆引きできています。

---

## 3. 仮想環境を有効にせずに `manage.py` を実行してしまう

**症状**

```text
ImportError: Django をインポートできません。仮想環境が有効か、
pip install -r requirements.txt が済んでいるか確認してください。
```

**原因**

`pip install django` を実行したシェルと、`python manage.py` を実行しているシェルが別で、
仮想環境が有効になっていない。Windows では PowerShell とコマンドプロンプトを
行き来したときに起きやすいです。

**判断方法**

どの Python が使われているかを確認します。

Windows PowerShell:

```powershell
(Get-Command python).Source
```

Linux / macOS:

```bash
which python
```

プロジェクト内の `.venv` を指していれば正しい状態です。

---

## 4. 記事に書いた `python -m venv` が、Linux では動かなかった

**症状**

読者から見て最初の1行目が動かない。

```text
python: command not found
```

**再現条件**

記事の 4.1 に `python -m venv .venv` と書いていた。
これは Windows と、`python` が用意されている一部の環境でしか動かない。

**調べた結果**

コンテナで実際に確かめました。

| 環境 | `python` | `python3` |
| --- | --- | --- |
| Ubuntu 24.04（素のイメージ） | 無し | 無し |
| Debian 12（素のイメージ） | 無し | 無し |
| Oracle Linux 9 | 無し | 3.9.25 |
| AlmaLinux 9 | 無し | 3.9.25 |
| Oracle Linux 10.2（この連載の本番サーバー） | 3.12.13 | 3.12.13 |

Oracle Linux 10 だけ `python` があるのは、
`python-unversioned-command` というパッケージが入っているからです。
OS が新しいから、ではありません。

```text
$ readlink -f $(command -v python)
/usr/bin/python3.12
$ rpm -qf $(command -v python)
python-unversioned-command-3.12.13-2.0.1.el10_2.1.noarch
```

**さらに分かったこと**

RHEL 9 系の既定の `python3` は 3.9 で、Django 5.2 が入りません。

```text
$ pip install Django==5.2.17
ERROR: Could not find a version that satisfies the requirement Django==5.2.17
       (from versions: ... 4.2.29, 4.2.30)
```

Django 5.2 の配布物には `Requires-Python: >=3.10` が記録されているため、
pip が 3.9 で使える版だけを候補に出し、その中に 5.2.17 が無い、という結果です。
「そんな版は無い」という意味に読めるメッセージですが、
無いのは版ではなく、**その Python で使える版**です。

**直し方**

記事の該当箇所を環境別ブロックに書き換え、`python3`（Windows は `py -3`）に統一しました。
そのうえで、**仮想環境を有効化した後は `python` でよい**ことを明記しました。
`venv` が `.venv/bin/python` を必ず作るためです。

**この記録の意味**

これは読者が踏むエラーではなく、**書いた側が踏んでいたエラー**です。
Windows で書いて Windows で確認していたため、最後まで気づけませんでした。
手順書は、書いた環境以外で一度動かすまで正しいとは言えません。

---

## 5. `python3` はあるのに `python3 -m venv` だけが失敗する

**症状**

Ubuntu 24.04 で、`python3 -V` は動くのに次で止まる。

```text
The virtual environment was not created successfully because ensurepip is not
available.  On Debian/Ubuntu systems, you need to install the python3-venv
package using the following command.

    apt install python3.12-venv

You may need to use sudo with that command.  After installing the python3-venv
package, recreate your virtual environment.

Failing command: /tmp/.venv/bin/python3
```

**原因**

Debian / Ubuntu は Python の標準ライブラリを複数のパッケージに分けています。
`python3` を入れても `venv`（正確にはその中で使う `ensurepip`）は付いてきません。

**直し方**

```bash
sudo apt install -y python3-venv
rm -rf .venv && python3 -m venv .venv
```

**作り直しが必要な理由**

失敗した `.venv/` が中途半端に残ります。実際に中を見ました。

```text
.venv/bin/
├── python
├── python3
└── python3.12
```

`activate` がありません。`pip` もありません。
この状態で `source .venv/bin/activate` を実行すると、
シェルによっては何も表示せずに終わります。
エラーが見えないまま、有効化できていない状態で作業を続けることになり、
結果として 3番のエラーと同じ場所に迷い込みます。

**確かめたこと**

「消してから作り直す必要が本当にあるのか」を確認しました。
結果は **無い** です。パッケージを入れた後に、同じディレクトリへ
そのまま再実行するだけで `activate` も `pip` も作られました。

```text
$ python3 -m venv .venv        # 消さずに再実行
$ ls -A .venv/bin
Activate.ps1  activate  activate.csh  activate.fish
pip  pip3  pip3.12  python  python3  python3.12
```

それでも `rm -rf .venv` を書いているのは、
**残骸を見分けるより、消す方が確実だから**です。
中途半端な `.venv/` は「エラーを出さずに何もしない」という形で失敗するので、
気づける保証がありません。
