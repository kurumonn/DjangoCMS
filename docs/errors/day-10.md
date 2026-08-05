# 10日目に実際に起きたエラー

形式は 症状 / 再現条件 / 原因 / 直し方 / 判断方法。

---

## 1. `check --deploy` の警告が、正しい運用手順とぶつかる

### 症状

コンテナの起動スクリプトに検査を入れたところ、起動できなくなった。

```text
$ python manage.py check --deploy --fail-level WARNING
SystemCheckError: System check identified some issues:

WARNINGS:
?: (security.W005) You have not set the SECURE_HSTS_INCLUDE_SUBDOMAINS setting to True. ...
?: (security.W021) You have not set the SECURE_HSTS_PRELOAD setting to True. ...

System check identified 2 issues (0 silenced).
```

### 再現条件

`SECURE_HSTS_SECONDS` を設定しつつ、`SECURE_HSTS_INCLUDE_SUBDOMAINS` と
`SECURE_HSTS_PRELOAD` を False のままにして、`--fail-level WARNING` で検査する。

### 原因

Django の言い分は正しい。この2つを有効にした方が安全ではある。

しかし **HSTS は取り消せない設定**である。

ブラウザーは `Strict-Transport-Security` ヘッダーを受け取ると、
`max-age` の期間そのドメインを HTTPS 固定で覚える。
証明書が切れたとき、利用者の画面には回避できないエラーが出る。
「とりあえず HTTP に戻して直す」ができない。
`includeSubDomains` を付ければ、その影響がサブドメイン全部に及ぶ。

だから正しい運用は「短い期間から始めて、確認しながら上げる」であって、
「警告が出ているから今すぐ全部 True にする」ではない。

つまりこれは**設定ミスではなく、静的な検査が運用の途中経過を
表現できないことによる衝突**である。

### 直し方

まず、その2件だけを黙らせる。ただし黙らせるのは
「まだその段階に来ていないあいだ」に限る。

```python
# config/settings/production.py
SILENCED_SYSTEM_CHECKS = []
if not SECURE_HSTS_INCLUDE_SUBDOMAINS:
    SILENCED_SYSTEM_CHECKS.append("security.W005")
if not SECURE_HSTS_PRELOAD:
    SILENCED_SYSTEM_CHECKS.append("security.W021")
```

True にすれば警告の対象から外れるので、この行も自然に効かなくなる。
「一度黙らせたら永久に黙る」形にしないのが要点。

そのうえで、**黙らせた分の代わり**を用意する。
黙らせただけだと、結局そのまま忘れる。

`core/checks.py` に、今どの段階にいて次に何をすべきかを出すチェックを足した。

```text
INFOS:
?: (core.I001) HSTS: max-age=3600 秒 / includeSubDomains=False / preload=False
	HINT: 1時間。まず HTTPS が全ページで問題なく動くことを確かめる段階。
	      次にやること: 問題が無ければ DJANGO_SECURE_HSTS_SECONDS=604800 へ上げる
```

`Warning` ではなく `Info` にしているのは、
`--fail-level WARNING` で起動が止まると
「段階的に上げる」こと自体ができなくなるため。

### 判断方法

`max-age` を 3600 → 604800 → 31536000 → includeSubDomains → preload と
順に変えて、案内が次の段階を指すことを確かめる。
テストは `core/tests/test_checks.py` にある。

### 学び

**警告を黙らせるときは、必ず代わりを置く。**

`SILENCED_SYSTEM_CHECKS` に足すだけの対処は、
「静かになった」以外に何も生まない。
黙らせた理由と、いつ黙らせるのをやめるのかが、
コードのどこにも書かれない状態になる。

---

## 2. 設定を分割したら BASE_DIR が1階層ずれる

### 症状

分割直後、静的ファイルが見つからなくなった。

### 再現条件

`config/settings.py` を `config/settings/base.py` へ移したが、
`BASE_DIR` の定義をそのままにしている。

```python
BASE_DIR = Path(__file__).resolve().parent.parent
```

### 原因

ファイルの位置が1階層深くなったのに、遡る回数が同じままだった。

| ファイル | `parent.parent` の行き先 |
| --- | --- |
| `config/settings.py` | プロジェクトルート ✅ |
| `config/settings/base.py` | `config/` ❌ |

### 直し方

```python
BASE_DIR = Path(__file__).resolve().parent.parent.parent
```

### 判断方法

`python manage.py shell -c "from django.conf import settings; print(settings.BASE_DIR)"`
で確かめる。`manage.py` と同じ場所を指していれば正しい。

分割のときは `BASE_DIR` を使っている箇所（`STATICFILES_DIRS` /
`MEDIA_ROOT` / `TEMPLATES` の `DIRS` / SQLite の `NAME`）が
まとめてずれるので、症状が「あちこち同時におかしい」形で出る。
1か所ずつ追いかけると遠回りになる。

---

## 3. `sys.modules` に残った設定モジュールで、テストが通ってしまう

### 症状

本番設定のテストを書いたところ、
環境変数を消しても `RuntimeError` が出ず、テストが失敗した。

### 再現条件

同じ設定モジュールを、環境変数を変えながら2回 import する。

```python
os.environ["DJANGO_SECRET_KEY"] = "..."
importlib.import_module("config.settings.production")   # 1回目

del os.environ["DJANGO_SECRET_KEY"]
importlib.import_module("config.settings.production")   # 2回目: 例外が出ない
```

### 原因

Python はモジュールを**一度しか実行しない**。
2回目の `import_module` は `sys.modules` にあるものを返すだけで、
モジュール本体（＝環境変数を読む処理）は走らない。

つまり2回目以降は、1回目の環境変数のまま固定された結果を見ている。

厄介なのは、これが**テストを緑にする方向**に働くこと。
「必須の環境変数が無いと落ちる」ことを確かめたいのに、
1回目で成功した結果が使い回され、
「落ちなかった＝壊れている」のに気づけない。

### 直し方

import の前に `sys.modules` から消す。

```python
sys.modules.pop("config.settings.production", None)
module = importlib.import_module("config.settings.production")
```

テスト後は元に戻す。他のテストが同じモジュールを見ているためである。

### 判断方法

わざと壊す。`require()` を「無ければ空文字を返す」に変えて、
テストが**落ちること**を確かめる。
落ちなければ、そのテストは何も検査していない。

---

## 4. 実在しないバージョンを固定して、ビルドが落ちる

### 症状

Docker イメージのビルドが、依存のインストールで止まった。

```text
ERROR: Could not find a version that satisfies the requirement redis==6.5.0
       (from versions: 0.6.0, 0.6.1, ... 8.0.1, 8.1.0)
ERROR: No matching distribution found for redis==6.5.0
```

### 再現条件

`requirements.txt` に、実在しないバージョンを書く。

### 原因

`redis` パッケージに 6.5.0 は無い。6系は 6.4.0 で終わっていて、
そこから 7 系・8 系へ進んでいる。
「6.5 くらいはあるだろう」と書いた番号が、たまたま存在しなかった。

このエラー自体は5分で直る。記録しているのは**気づいた場所**の方。

ローカルの仮想環境には `redis` が既に入っていたので、
`manage.py test` は 290 件すべて通っていた。
`requirements.txt` の番号が嘘でも、手元では何も起きない。
**依存関係の記述が正しいかは、まっさらな環境で入れ直すまで分からない。**

Docker のビルドは、まさにその「まっさらな環境で入れ直す」作業である。
だからこの種の嘘は、必ずビルドで見つかる。逆に言えば、
ビルドを一度も通していない `requirements.txt` は、
動く保証がどこにもない。

### 直し方

推測で書かず、実際に配布されている版を調べてから固定する。

```bash
pip index versions redis
```

```text
redis (8.1.0)
Available versions: 8.1.0, 8.0.1, 8.0.0, 7.4.1, ...
```

### 判断方法

`docker compose build` が通ること。
手元のテストが通ることは、この件の判断材料にならない。

---

## 5. 依存の宣言が9日間ずっと間違っていた（手元では動いていた）

### 症状

ビルドは通ったが、コンテナが起動しなかった。

```text
web-1  | [entrypoint] データベースに接続できました。
web-1  | [entrypoint] 本番向けの設定を検査します...
web-1  |   File "/usr/local/lib/python3.12/site-packages/allauth/socialaccount/providers/google/provider.py", line 3, in <module>
web-1  |     import requests
web-1  | ModuleNotFoundError: No module named 'requests'
```

### 再現条件

`requirements.txt` に `django-allauth` と、その依存の一部
（`qrcode` / `fido2`）だけを手で書いている。まっさらな環境でインストールする。

### 原因

`allauth.socialaccount.providers.google` は `requests` を import する。
しかし `requirements.txt` に `requests` は無い。

**開発機ではこれで9日間動いていた。**
仮想環境に別の経路で `requests` が入っていたためである。
`pip install -r requirements.txt` だけで環境を作った人は、
8日目の時点で動かなかったはずだが、こちらでは気づけなかった。

つまりこれは10日目に壊れたのではなく、
**10日目に初めて分かった8日目の間違い**である。

原因は、依存を手で書き写したこと。
`qrcode` と `fido2` を自分で並べた時点で、
「allauth が必要とするもの」を自分の理解で列挙したことになる。
上流が依存を増やしても、こちらの一覧は増えない。

### 直し方

パッケージ側に依存を決めさせる。角かっこは追加機能（extras）の指定。

```text
django-allauth[mfa,socialaccount]==65.18.0
```

- `mfa` … TOTP とパスキー（`qrcode`, `fido2`）
- `socialaccount` … Google / GitHub ログイン（`requests`, `requests-oauthlib` ほか）

手で書いた `qrcode==8.2` / `fido2==2.2.1` の行は消す。
これで、allauth が将来必要な依存を増やしても自動で付いてくる。

### 判断方法

**手元のテストでは判断できない。**
290 件すべて通っている状態で、この間違いは残っていた。

判断できるのは、依存を空から入れ直したときだけ。

```bash
docker compose build --no-cache
```

Docker のビルドが、そのまま「まっさらな環境の再現」になっている。

### 学び

4 と 5 は原因が違うが、見つかった場所は同じ。

| | 間違い | 手元で気づけたか |
| --- | --- | --- |
| 4 | 存在しないバージョンを書いた | ❌ 既に入っていた |
| 5 | 必要な依存を書き忘れた | ❌ 別経由で入っていた |

どちらも「開発機に入っているもの」が
`requirements.txt` の間違いを覆い隠していた。

**動いている環境は、依存関係の宣言が正しい証拠にならない。**
証拠になるのは、空の環境で入れ直せることだけである。

---

## 6. コンテナのヘルスチェックが、本番設定に阻まれて必ず失敗する

### 症状

コンテナは起動しているのに、いつまでも healthy にならない。
Gunicorn のアクセスログには 301 が並ぶ。

```text
web-1  | [2026-08-05 07:55:55 +0000] [1] [INFO] Listening at: http://0.0.0.0:8000 (1)
web-1  | 127.0.0.1 - - [05/Aug/2026:16:55:55 +0900] "GET /healthz/ HTTP/1.1" 301 0 "-" "Python-urllib/3.12"
web-1  | 127.0.0.1 - - [05/Aug/2026:16:56:05 +0900] "GET /healthz/ HTTP/1.1" 301 0 "-" "Python-urllib/3.12"
```

### 再現条件

compose の healthcheck を、こう書く。

```yaml
test: ["CMD", "python", "-c",
       "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/')"]
```

### 原因

コンテナの中から自分自身を叩くと、**nginx を通らない**。
そのため、正しく設定した本番向けの仕組み2つに、両方とも引っかかる。

| 仕組み | 何が起きるか |
| --- | --- |
| `SECURE_SSL_REDIRECT` | nginx が付けるはずの `X-Forwarded-Proto: https` が無い → 301 |
| `ALLOWED_HOSTS` | Host が `127.0.0.1:8000` になる → 400 |

つまり**設定が正しいからこそ失敗する**。
ここで「監視が通らないから `SECURE_SSL_REDIRECT` を切る」と考えると、
本番の防御を監視の都合で下げることになる。向きが逆である。

### 直し方

監視側が、**nginx を通ってきたのと同じ形**でリクエストを送る。

```python
# docker/healthcheck.py
request = urllib.request.Request(
    "http://127.0.0.1:8000/healthz/",
    headers={
        "Host": first_allowed_host(),          # ALLOWED_HOSTS 対策
        "X-Forwarded-Proto": "https",          # SECURE_SSL_REDIRECT 対策
    },
)
```

Host は `DJANGO_ALLOWED_HOSTS` の先頭から取る。
ここに固定値を書くと、ドメインを変えたときに監視だけ古いまま残る。

### 判断方法

```text
$ docker compose ps
SERVICE   STATUS
db        Up 3 minutes (healthy)
nginx     Up 3 minutes
redis     Up 3 minutes (healthy)
web       Up 45 seconds (healthy)
```

`SECURE_REDIRECT_EXEMPT` で `/healthz/` を例外にする方法もある。
ただしそれは「防御に穴を1つ開けて監視を通す」やり方で、
穴は監視以外からも使える。ここでは監視側を直す方を選んだ。

---

## 7. Git Bash が、コンテナ内のパスを Windows のパスへ書き換える

### 症状

バックアップスクリプトが、存在しないディレクトリを見に行った。

```text
[backup] アップロード画像を固めます...
tar: C\:/Program Files/Git/app: Cannot open: No such file or directory
tar: Error is not recoverable: exiting now
```

`/app` と書いたのに `C:/Program Files/Git/app` になっている。

### 再現条件

Windows の Git Bash から、コンテナ内の絶対パスを引数として渡す。

```bash
docker compose exec -T web tar -cz -C /app media
```

### 原因

MSYS（Git Bash の基盤）は、`/` で始まる引数を
Windows のパスだと思って自動変換する。
`/app` は Git のインストール先を基準に `C:/Program Files/Git/app` になる。

コンテナの中のパスなのか、Windows のパスなのか、
シェルには区別が付かないので起きる。

サーバー（Linux）で実行する分には起きない。
だから「手元では動かないが本番では動く」という、
判断を誤りやすい形で出る。

### 直し方

パスを、引用符でくくった1つの文字列の中に入れる。

```bash
docker compose exec -T web sh -c 'cd /app && tar -cz media'
```

この引数は `cd` で始まっているので、パスとは見なされず変換されない。

### 判断方法

`docker compose exec -T web sh -c 'pwd'` が `/app` を返すこと。
`docker compose exec -T web pwd` と書き分けて挙動を比べると分かりやすい。

---

## 8. `pg_restore --list /dev/stdin` は必ず失敗する

### 症状

バックアップの検証だけが通らない。ダンプ自体は正常に見える。

```text
[backup] 取得したファイルを検査します...
pg_restore: error: did not find magic string in file header
```

### 再現条件

```bash
docker compose exec -T db sh -c 'pg_restore --list /dev/stdin' < backup.dump
```

### 原因

ファイルは壊れていない。先頭を見れば分かる。

```text
first 16 bytes: b'PGDMP\x01\x10\x00\x04\x08\x01\x01\x00\x14\x00\x00'
```

`PGDMP` で始まっているので、カスタム形式のダンプとして正しい。
コンテナへ渡る途中でも壊れていない（中で `wc -c` すると
ローカルと同じ 104537 バイトだった）。

原因は渡し方の方。
`pg_restore` はカスタム形式のアーカイブを読むときシークする。
`/dev/stdin` を**ファイル名として**渡すと、
`pg_restore` はそれを普通のファイルとして開き、シークしようとする。
しかしパイプはシークできない。

対して、ファイル名を渡さずに標準入力から読ませた場合は、
`pg_restore` が「シークできない入力」として扱うので通る。

同じ「標準入力」に見えて、渡し方で挙動が変わる。

### 直し方

ファイル名を渡さない。

```bash
docker compose exec -T db sh -c 'pg_restore --list' < backup.dump
```

### 判断方法

3つ試して切り分けた。

| 書き方 | 結果 |
| --- | --- |
| `pg_restore --list /dev/stdin` | ❌ |
| `pg_restore --list`（標準入力） | ✅ |
| 一度コンテナ内へファイルとして置いてから `--list` | ✅ |

3つ目が通る時点で、ファイルの中身ではなく渡し方の問題だと分かる。

---

## 9. `docker compose config` が `.env` を要求する

### 症状

構文だけ確かめようとしたら、ファイルが無いと言われた。

```text
env file E:\PycharmProjects\DjangoCMS\.env not found
```

### 原因

`compose.yaml` の web サービスに `env_file: - .env` と書いてある。
compose は構文検査の段階でこのファイルを読もうとする。

### 直し方

検証用の `.env` を作る。`.env.example` をそのままコピーせず、
**その場で生成した使い捨ての値**を入れる。

```bash
cp .env.example .env    # ← これは避ける
```

`.env.example` にはダミー値が書いてあるので、コピーしただけだと
`DJANGO_SECRET_KEY=ここに生成した値を貼る` のまま起動してしまう。
それでも動いてしまうのが最悪で、
「本番の署名鍵が example ファイルに書いてある文字列」という状態になる。

`.env.example` の必須項目に、あえて動かない日本語のダミーを入れてあるのは
このためである。英語のそれらしい文字列にすると、
気づかないまま本物として使われる。
