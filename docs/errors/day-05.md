# 5日目に実際に起きたエラー

## 1. 権限を厳しくしたら、3日目に書いたテストが3件落ちた

**症状**

5日目に「公開は独立した権限」へ変えた直後、テストを走らせると
5日目のテストは全部通るのに、3日目のテストが落ちた。

```text
FAIL: test_author_can_create
AssertionError: 200 != 302

ERROR: test_author_cannot_be_spoofed
blog.models.Article.DoesNotExist: Article matching query does not exist.
```

**再現条件**

3日目のテストは「記事を書ける利用者が `status=published` で投稿する」前提で書かれていた。
5日目に `blog.publish_article` 権限を持たない利用者は公開できないよう変更した。

**原因**

これは **バグではなく仕様変更** です。
フォームが検証エラーで再表示されるので、リダイレクト（302）ではなく 200 が返り、
記事も作られていません。テスト側が古い仕様のままでした。

```python
def clean_status(self):
    status = self.cleaned_data.get("status")
    if status == Article.Status.PUBLISHED and not self.can_publish:
        raise forms.ValidationError("記事を公開する権限がありません。")
    return status
```

**判断のしかた**

テストが落ちたとき、まず次を切り分けます。

| 状況 | 直す場所 |
| --- | --- |
| 意図せず壊れた | 実装 |
| 意図して仕様を変えた | テスト |

今回は後者なので、テストを新しい仕様へ合わせます。
このとき「とりあえず通るように書き換える」のではなく、
**新しい仕様を表現するテストになっているか** を確認します。

**直し方**

投稿テストの既定を「下書き」にし、公開が必要なテストだけ
公開権限を持つ利用者で実行するようにしました。

```python
def _payload(self, **overrides):
    # 既定は下書き。公開は publish 権限を持つ利用者で試す。
    data = {..., "status": Article.Status.DRAFT}
    data.update(overrides)
    return data

def test_published_without_date_gets_current_time(self):
    create_editor(username="dateless-editor")   # 公開権限あり
    self.client.login(username="dateless-editor", password=PASSWORD)
    self.client.post(self.url, self._payload(status=Article.Status.PUBLISHED))
```

**ここで学べること**

画面から「公開」の選択肢を消すだけでは対策になりません。
POST は画面を経由せずに直接送れるからです。

この CMS では、フォームの `choices` を実際に差し替えたうえで、
`clean_status()` でも二重に検証しています。テストもその両方を確認しています。

```python
def test_author_cannot_choose_published_in_form(self):
    # 画面に出ないこと
    choices = dict(response.context["form"].fields["status"].choices)
    self.assertNotIn(Article.Status.PUBLISHED, choices)

def test_author_posting_published_is_rejected(self):
    # 直接 POST しても通らないこと
    response = self.client.post(self.url, self._payload(Article.Status.PUBLISHED))
    self.assertFalse(Article.objects.filter(title="権限テスト記事").exists())
```

---

## 2. 履歴が「変更後」の内容で保存されてしまう

**症状**

記事を編集したあと履歴を見ると、変更前の内容ではなく
変更後の内容が版として残っている。

**原因**

`form_valid()` の中で `super().form_valid(form)` を先に呼ぶと、
その時点で `self.object` は保存済みの新しい内容になります。
そのあとにスナップショットを取ると、当然「変更後」が残ります。

**直し方**

保存の **前** に、データベースから読み直した内容を版にします。

```python
@transaction.atomic
def form_valid(self, form):
    # 更新の「前」に現在の内容を版として保存する
    before = Article.objects.get(pk=self.object.pk)
    before.snapshot(created_by=self.request.user, note="編集前の自動保存")

    response = super().form_valid(form)
    ...
```

`self.object` をそのまま使わずに `Article.objects.get()` で読み直しているのは、
`ModelFormMixin` が `self.object` にフォームの値をすでに反映している場合があるためです。

**判断方法**

```python
def test_editing_creates_revision_of_previous_content(self):
    self._edit("2番目のタイトル", "2番目の本文")
    revision = ArticleRevision.objects.get(article=self.article)
    self.assertEqual(revision.title, "最初のタイトル")   # ← 変更前
```

---

## 3. 操作ログの外部キーが、記事を消すと一緒に消える

**症状（設計段階で気づいた問題）**

「誰が記事を削除したか」を残したいのに、記録も一緒に消えてしまう。

**原因**

操作ログの対象を `ForeignKey(Article, on_delete=models.CASCADE)` にすると、
記事が削除された瞬間にログも削除されます。
`SET_NULL` にしても「何を消したか」が分からなくなります。

**直し方**

対象を外部キーにせず、アプリラベル・モデル名・ID・表示名を文字列で持ちます。

```python
target_app_label = models.CharField(max_length=100, blank=True, default="")
target_model = models.CharField(max_length=100, blank=True, default="")
target_id = models.CharField(max_length=64, blank=True, default="")
target_repr = models.CharField(max_length=200, blank=True, default="")
```

さらに、削除の記録は削除の **前** に取ります。
後で取ると、対象が消えていて何を消したのか書けません。

```python
def form_valid(self, form):
    record(AuditLog.Action.DELETE, actor=self.request.user,
           target=self.object, request=self.request, title=self.object.title)
    return super().form_valid(form)
```

**判断方法**

```python
def test_delete_is_recorded_with_title(self):
    self.client.post(reverse("blog:article_delete", args=[article.slug]))
    entry = AuditLog.objects.get(action=AuditLog.Action.DELETE)
    self.assertEqual(entry.detail["title"], "消える記事")
    self.assertFalse(Article.objects.filter(pk=article.pk).exists())
```
