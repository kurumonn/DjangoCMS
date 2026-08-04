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
