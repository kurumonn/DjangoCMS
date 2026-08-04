# 4日目に実際に起きたエラー

## 1. テンプレートを編集したのに画面が変わらない

**症状**

`article_detail.html` にコメント欄と関連記事を追加したが、
ブラウザーを再読み込みしても古い画面のまま。エラーは何も出ない。

**再現条件**

`runserver` を `--noreload` 付きで起動したまま、テンプレートだけを編集した。

**原因**

Django 4.1 以降、`DEBUG=True` でもテンプレートは
**プロセス内でキャッシュ**されます（`cached.Loader` 相当の挙動）。
通常は自動リロードでプロセスごと再起動するため気づきませんが、
`--noreload` を付けているとプロセスが生き続けるので、
古いテンプレートが返り続けます。

Python ファイルを直しても反映されないのも同じ理由です。

**やってしまいがちな遠回り**

* ブラウザーのキャッシュを疑ってスーパーリロードする → 変わらない
* `collectstatic` を実行する → テンプレートは静的ファイルではないので無関係
* テンプレートの継承やブロック名を疑って書き換える → 元から正しい

**直し方**

サーバーを再起動します。

```bash
python manage.py runserver
```

`--noreload` を外せば自動リロードされます。
自動リロードを切りたい事情がある場合（プロセス数を固定したいなど）は、
編集のたびに再起動する運用にします。

**判断方法**

再起動後にページを開き、追加した見出し（「コメント」など）が表示されること。

---

## 2. `X-Forwarded-For` からどの値を取るべきか間違える

**症状**

例外は出ないが、レート制限が効かない、あるいは全員が同じ IP として扱われる。

**再現条件**

Nginx の背後に置いた Django で、`X-Forwarded-For` の **左端** を利用者の IP として採用する。

**原因**

Nginx の次の設定は、受け取ったヘッダーの **末尾へ** 接続元を追記します。

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

つまり、利用者が最初から偽のヘッダーを付けて送ってくると、こうなります。

```text
利用者が送ったヘッダー : X-Forwarded-For: 1.2.3.4
Nginx が書き換えた結果 : X-Forwarded-For: 1.2.3.4, 203.0.113.9
                                                    ↑ここだけが信用できる
```

左端（`1.2.3.4`）を採用する実装にすると、利用者は好きな IP を名乗れます。
レート制限も IP 制限も、リクエストごとに違う値を送るだけで回避されます。

**直し方**

信頼するプロキシの段数を設定で明示し、右から数えます。

```python
proxy_count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
if proxy_count > 0:
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    index = len(parts) - proxy_count
    if 0 <= index < len(parts):
        return parts[index]
return request.META.get("REMOTE_ADDR", "")
```

* プロキシ無し（開発）: `TRUSTED_PROXY_COUNT = 0` → ヘッダーを一切見ない
* Nginx 1段: `1` → 右端
* CDN + Nginx: `2` → 右から2番目

**判断方法**

テストで確認します。

```python
request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.9")
with override_settings(TRUSTED_PROXY_COUNT=1):
    assert client_ip(request) == "203.0.113.9"
```

**補足: このとき私が間違えたのはテストの方でした**

実装は最初から正しく右から数えていましたが、
テストの期待値を「左端が正しい」と書いてしまい、失敗しました。

```text
AssertionError: '10.0.0.1' != '203.0.113.9'
```

実装を疑って直そうとしたのですが、Nginx の追記方向を確認した結果、
**テストの期待値が間違っている**と分かりました。
テストが落ちたとき、必ずしも実装が悪いとは限りません。

---

## 3. アップロード検証で Pillow がファイルを読めない

**症状**

正しい画像をアップロードしたのに「画像として読み取れませんでした」になる。

**原因**

`verify()` を呼んだ後の Pillow の画像オブジェクトは、再利用できません。
また、アップロードファイルは一度読むとファイルポインタが末尾へ進むため、
そのまま2回目を読むと空になります。

**直し方**

内容をいったんメモリへ読み、`BytesIO` から2回開き直します。
検証が終わったら、保存処理のためにポインタを先頭へ戻します。

```python
payload = _read_all(uploaded_file)

with Image.open(io.BytesIO(payload)) as image:
    image.verify()           # 壊れていないか
with Image.open(io.BytesIO(payload)) as image:
    image_format = image.format   # 開き直して形式を採る
    width, height = image.size

uploaded_file.seek(0)        # 保存処理のために巻き戻す
```

**判断方法**

検証後に読み直せることをテストで固定します。

```python
uploaded = SimpleUploadedFile("photo.png", png_bytes)
validate_image_upload(uploaded)
assert uploaded.tell() == 0
assert uploaded.read()      # 中身がある
```
