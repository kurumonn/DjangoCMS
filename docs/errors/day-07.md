# 7日目に実際に起きたエラー

## 1. 楽観ロックの「1秒の許容」が、そのまま同時編集を見逃す穴だった

**症状**

「他の人が先に保存していたら 409 を返す」テストが、200 を返して落ちた。

```text
FAIL: test_stale_updated_at_is_rejected
AssertionError: 200 != 409
```

**再現条件**

自動保存の競合検出を `updated_at`（更新時刻）の比較で実装し、
丸め誤差を吸収するために1秒の許容を入れていた。

```python
# 問題のあったコード
client_updated_at = parse_datetime(payload.get("updated_at") or "")
# マイクロ秒の丸め差で誤検知しないよう、1秒の余裕を持たせる
if (article.updated_at - client_updated_at).total_seconds() > 1:
    return _error("他の場所でこの記事が更新されています。", 409)
```

**原因**

許容を入れた動機そのものは正しいものでした。

* MySQL は既定でマイクロ秒を切り捨てる
* JSON とテンプレートを往復する間に精度が落ちることがある

しかし「1秒の許容」は、**1秒以内に起きた同時編集を必ず素通しする** という意味になります。
そして同時編集は、まさにその1秒以内に起きます。
2人が同じ記事を開いていれば、自動保存はほぼ同じタイミングで飛びます。

つまり、誤検知を防ぐために入れた許容が、
検出したかった事象そのものを検出できなくしていました。

**直し方**

時刻の比較をやめ、整数の版番号にしました。

```python
class Article(models.Model):
    # 保存のたびに1つ増える。同時編集の検出（楽観ロック）に使う。
    version = models.PositiveIntegerField("版番号", default=0, editable=False)

    def save(self, *args, **kwargs):
        ...
        self.version = (self.version or 0) + 1
        self._add_update_field(kwargs, "version")
        super().save(*args, **kwargs)
```

```python
client_version = payload.get("version")
if not isinstance(client_version, int):
    return _error("version を送ってください。", 400)
if client_version != article.version:
    return _error("他の場所でこの記事が更新されています。", 409,
                  server_version=article.version)
```

整数の比較には、精度も丸めもタイムゾーンもありません。
「1つでも違えば競合」と言い切れます。

**ここで学べること**

「安全側に倒すつもりで入れた例外」が、
守りたかったものをちょうど守れなくすることがあります。

許容値を入れたくなったら、
**その許容の中に、検出したい事象が入ってしまわないか** を確認してください。
今回は「同時編集は1秒以内に起きる」ので、完全に入っていました。

**判断方法**

```python
def test_stale_version_is_rejected(self):
    stale_version = self.article.version
    self.article.title = "他の場所で保存された題名"
    self.article.save()          # 同じ秒に起きる

    response = self._post(self._payload(version=stale_version))
    self.assertEqual(response.status_code, 409)
```

このテストは、時刻比較の実装では通りません。版番号なら通ります。

---

## 2. `update_fields` を指定した保存で、内部で変えた列が保存されない

**症状（1の修正中に踏んだ問題）**

版番号を増やすコードを書いたのに、データベースの `version` が 0 のままだった。

**原因**

自動保存は `update_fields` を指定して保存しています。

```python
article.save(update_fields=["title", "blocks", "body", "updated_at"])
```

`update_fields` を指定すると、Django は **そこに挙げた列だけ** を UPDATE します。
`save()` の中で `self.version` を変えても、`version` が一覧に入っていなければ
SQL に含まれず、メモリ上だけ変わって消えます。

同じ理由で、ブロックから `body` を自動生成する処理も効きません。

**この不具合が厄介なところ**

* 例外が出ない
* `article.version` を直後に読むと、増えた値が返る（メモリ上は変わっている）
* データベースを見に行くと 0 のまま

「コードは正しく見えるのに動かない」典型です。

**直し方**

内部で変えた列を `update_fields` へ足すヘルパーを用意しました。

```python
@staticmethod
def _add_update_field(kwargs: dict, name: str) -> None:
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and name not in update_fields:
        kwargs["update_fields"] = list(update_fields) + [name]
```

**判断方法**

`refresh_from_db()` を挟んでから確認します。
これを挟まないと、メモリ上の値を見て「保存できている」と勘違いします。

```python
self.article.refresh_from_db()
self.assertEqual(self.article.title, "自動保存された題名")
```

---

## 3. テスト用のユーザーと、実運用のグループで権限が食い違っていた

**症状**

ダッシュボードのテストで、編集者に未承認コメントが表示されなかった。

```text
KeyError: 'pending_comments'
```

**原因**

テスト用の `create_editor()` は blog の権限しか付けていませんでした。
一方、実運用のグループを作る `setup_groups` コマンドの「編集者」には
`comments.change_comment` が入っています。

```python
# テスト用（不足していた）
grant(user, "blog.add_article", "blog.change_article",
      "blog.delete_article", "blog.publish_article", "blog.review_article")
```

**なぜ危ないか**

食い違う方向によって、起きることが変わります。

| 食い違い | 起きること |
| --- | --- |
| テストの権限が**少ない** | 今回のように、テストだけが落ちる（気づける） |
| テストの権限が**多い** | テストは通るのに、実運用で権限不足になる（気づけない） |

後者が本当に怖い方です。今回はたまたま気づける側でしたが、
**テストのユーザー定義と、実際に配る権限は、同じ場所から作るべき** でした。

**直し方**

`create_editor()` を `setup_groups` の「編集者」ロールへそろえ、
その旨をコメントに残しました。

```python
def create_editor(username="reviewer", **kwargs):
    """編集者（承認・公開・コメント管理ができる）。

    setup_groups コマンドの「編集者」ロールと同じ権限をそろえる。
    ここがずれていると、テストは通るのに実運用のグループでは
    権限が足りない、という食い違いが起きる。
    """
```

**さらに良い直し方（今後の課題）**

テストでも `call_command("setup_groups")` を呼び、
実際のグループへユーザーを入れる方式にすれば、食い違いは原理的に起きません。
権限定義が1か所になるためです。

---

## 4. `<button>` に `type` を書かないとフォームが送信される

**症状（実装中に想定して回避した問題）**

ブロック追加ボタンを押すと、記事フォームがそのまま送信されてしまう。

**原因**

HTML の `<button>` は、`type` を省略すると `type="submit"` として扱われます。
フォームの中に置いた「ブロックを追加」ボタンは、押した瞬間に送信になります。

**直し方**

`type="button"` を明示します。JavaScript で動的に作るボタンも同じです。

```javascript
function makeButton(label, title, handler) {
  var button = document.createElement("button");
  button.type = "button";   // form の中なので type を明示しないと送信される
  ...
}
```

**判断方法**

ブロック追加ボタンを押しても、ページが遷移せず、
エディターにブロックが増えること。

---

## 5. ブロックの検証を「知らない種類は無視」にしない

**症状（設計上の判断）**

未知のブロック種別が来たとき、無視して保存するか、エラーにするか。

**採用した方針**

エラーにします。

```python
spec = BLOCK_TYPES.get(block_type)
if spec is None:
    raise ValidationError(f"{index} 番目: 未知のブロック種別「{block_type}」です。")
```

**理由**

無視すると「保存は成功したのに、開くと消えている」状態になります。
利用者から見ると、書いた内容が黙って失われたことになり、原因も分かりません。

エラーメッセージには **何番目のブロックか** を入れます。
「ブロックが不正です」だけでは、30個あるうちのどれが悪いのか分かりません。

```python
raise ValidationError(f"{index} 番目（{spec.label}）: {exc.messages[0]}")
```

---

## 6. `javascript:` で始まるリンクをブロックに保存させない

**症状（テストで確認した攻撃）**

行動喚起（CTA）ブロックのリンク先に `javascript:alert(1)` を保存できると、
読者がボタンを押した瞬間にスクリプトが動きます。

テンプレート側の `{{ data.url }}` はエスケープされますが、
`href="javascript:..."` は **エスケープしても動きます**。
エスケープは「HTML の構造を壊さない」ための処理であって、
「URL スキームの安全性」は別の話です。

**直し方**

保存時にスキームを制限します。

```python
def _validate_cta(data: dict) -> dict:
    url = _text(data, "url")
    # javascript: や data: を弾く。リンク先は http(s) と相対パスだけ許可する。
    if not (url.startswith(("https://", "http://", "/"))):
        raise ValidationError("リンク先は http(s) か / で始まるパスにしてください。")
    return {"text": _text(data), "url": url}
```

**判断方法**

```python
def test_cta_rejects_javascript_url(self):
    for url in ("javascript:alert(1)", "data:text/html,<script>", "vbscript:x"):
        with self.subTest(url=url):
            with self.assertRaises(ValidationError):
                validate_blocks([{"type": "cta", "data": {"text": "押す", "url": url}}])
```

---

## この日の教訓

7日目のエラーは、どれも **「正しく見えるコード」** から出ました。

* 1秒の許容 → 安全側に倒したつもりが、検出対象そのものを外していた
* `update_fields` → 例外も出ず、メモリ上は正しい値に見えていた
* 権限の食い違い → たまたま気づける方向だっただけ

共通しているのは、**確認方法を間違えると気づけない**という点です。

* メモリ上の値ではなく `refresh_from_db()` の後を見る
* 「同じ秒に起きる」条件でテストを書く
* テストが通ることと、実運用で動くことを混同しない
