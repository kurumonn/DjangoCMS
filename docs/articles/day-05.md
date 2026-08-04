# 【5日目】WordPress 級の記事管理――下書き・予約投稿・リビジョンを実装する

> 連載「10日で作る Django CMS」の5日目です。
> 成果物: <https://github.com/kurumonn/DjangoCMS>（タグ `day-05`）

---

## 1. 今日の結論

編集ワークフローを作ります。

- 下書き → レビュー待ち → 公開 の承認フロー
- **「公開」を独立した権限にする**
- 予約投稿（未来の日時を入れると、その時刻まで表に出ない）
- リビジョン（変更履歴）と過去版への復元
- 追記専用の操作ログ
- 投稿者・編集者・サイト管理者の3つの役割

**今日いちばん大事なのは、「記事を書ける」と「記事を公開できる」を分けること**です。
この2つを一緒にしていると、アカウントを1つ乗っ取られただけで
公開ページを書き換えられます。

---

## 2. 今日の完成画面

公開までの流れはこうなります。

```text
下書き
  ↓  投稿者が「レビューを依頼」
レビュー待ち
  ↓  編集者が確認
  ├─ 承認 →  公開（または予約投稿）
  └─ 差し戻し →  下書きへ戻る
```

記事詳細に、権限に応じた操作バーが出ます。

```text
┌─────────────────────────────────────────┐
│ 編集  履歴  削除   [レビューを依頼]      │  ← 投稿者
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ 編集  履歴  削除   [承認して公開]        │  ← 編集者
│                    [差し戻し理由___] [差し戻す] │
└─────────────────────────────────────────┘
```

---

## 3. 今日変更するファイル

```text
core/                      新規（アプリ横断）
├── models.py              AuditLog（操作ログ）
├── admin.py               読み取り専用の Admin
└── management/commands/
    └── setup_groups.py    役割（グループ）の作成
blog/
├── models.py              変更（ArticleRevision / 独自権限）
├── views.py               変更（ワークフローのビュー）
├── forms.py               変更（権限で status の選択肢を絞る）
├── urls.py                変更
├── admin.py               変更
└── tests/test_workflow.py 新規
templates/blog/
├── article_detail.html    変更（操作バー）
└── revision_list.html     新規
```

---

## 4. 完成コード

### 4.1 独自の権限を定義する

```python
# blog/models.py（Article.Meta）
class Meta:
    verbose_name = "記事"
    ordering = ["-published_at", "-created_at"]
    # Django が自動で作る add/change/delete に加えて、
    # 「公開してよいか」「承認してよいか」を独立した権限にする。
    # これがないと「記事を書ける人＝勝手に公開できる人」になってしまう。
    permissions = [
        ("publish_article", "記事を公開できる"),
        ("review_article", "記事のレビューを承認できる"),
    ]
```

`makemigrations` すると、この2つが `auth_permission` テーブルへ追加されます。

### 4.2 リビジョン（変更履歴）

```python
class Article(models.Model):
    ...

    def snapshot(self, *, created_by, note: str = "") -> "ArticleRevision":
        """現在の内容を1つの版として保存する。

        更新の**前**に呼ぶ。更新後に呼ぶと、変更前の内容が残らない。
        """
        return ArticleRevision.objects.create(
            article=self,
            title=self.title,
            body=self.body,
            status=self.status,
            published_at=self.published_at,
            created_by=created_by,
            note=note,
        )


class ArticleRevision(models.Model):
    """記事の変更履歴。

    本文だけでなく status と published_at も残すのは、
    「うっかり公開してしまった」を戻すときに必要になるため。
    """

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, related_name="revisions"
    )
    title = models.CharField("タイトル", max_length=200)
    body = models.TextField("本文")
    status = models.CharField("公開状態", max_length=20)
    published_at = models.DateTimeField("公開日時", null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="article_revisions",
    )
    created_at = models.DateTimeField("保存日時", auto_now_add=True)
    note = models.CharField("メモ", max_length=200, blank=True, default="")

    def restore_to_article(self, *, restored_by) -> Article:
        """この版の内容を記事へ書き戻す。

        書き戻す前に、いまの内容も1つの版として保存する。
        そうしないと「復元したけれど、やっぱり戻したい」ができなくなる。
        """
        article = self.article
        article.snapshot(created_by=restored_by, note="復元前の自動保存")

        article.title = self.title
        article.body = self.body
        # status と published_at は戻さない。
        # 「公開中の記事の本文だけを古い版に戻す」が実務では最も多く、
        # 復元操作が同時に公開状態まで変えると事故になる。
        article.save(update_fields=["title", "body", "updated_at"])
        return article
```

### 4.3 フォームで選択肢を絞る

```python
# blog/forms.py（抜粋）
class ArticleForm(forms.ModelForm):
    """公開状態の選択肢は、ログイン中のユーザーの権限で絞る。

    画面から「公開」を消すだけでは足りない（POST を直接送れば通ってしまう）。
    このフォームは choices を実際に差し替えるため、
    権限のない値を送っても検証で弾かれる。
    """

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["status"].choices = self._allowed_status_choices()
        if not self.can_publish:
            self.fields["published_at"].disabled = True

    @property
    def can_publish(self) -> bool:
        return bool(self.user and self.user.has_perm("blog.publish_article"))

    def _allowed_status_choices(self):
        if self.can_publish:
            return Article.Status.choices
        # 公開権限が無い人は「下書き」と「レビュー待ち」まで。
        return [
            (value, label)
            for value, label in Article.Status.choices
            if value != Article.Status.PUBLISHED
        ]

    def clean_status(self):
        status = self.cleaned_data.get("status")
        if status == Article.Status.PUBLISHED and not self.can_publish:
            raise forms.ValidationError("記事を公開する権限がありません。")
        return status
```

**2重に守っている**点に注目してください。

1. `choices` を差し替える（画面に出さない）
2. `clean_status()` で検証する（POST を直接送っても弾く）

1 だけでは不十分です。POST は画面を経由せずに送れます。

### 4.4 ワークフローのビュー

```python
class ArticleWorkflowView(LoginRequiredMixin, View):
    """状態を変える操作の共通土台。

    すべて POST のみ。GET で状態が変わる URL を作ってはいけない。
    """

    def get_article(self) -> Article:
        return get_object_or_404(Article, slug=self.kwargs["slug"])


class ArticleApproveView(ArticleWorkflowView):
    """レビュー待ちの記事を承認して公開する（編集者の操作）。"""

    def post(self, request, slug):
        article = self.get_article()
        if not _can_review(request.user):
            raise PermissionDenied("記事を承認する権限がありません。")
        if article.status != Article.Status.REVIEW:
            messages.error(request, "レビュー待ちの記事だけが承認できます。")
            return self.redirect_to_article(article)

        # 自分の記事を自分で承認できてしまうと、承認フローの意味が無くなる。
        if article.author_id == request.user.pk and not request.user.is_superuser:
            messages.error(request, "自分の記事は自分で承認できません。")
            return self.redirect_to_article(article)

        article.status = Article.Status.PUBLISHED
        if not article.published_at:
            article.published_at = timezone.now()
        article.save(update_fields=["status", "published_at", "updated_at"])

        record(
            AuditLog.Action.APPROVE,
            actor=request.user, target=article, request=request,
            published_at=article.published_at.isoformat(),
        )
        return self.redirect_to_article(article)
```

### 4.5 編集時にリビジョンを残す

```python
class ArticleUpdateView(...):
    @transaction.atomic
    def form_valid(self, form):
        # 更新の「前」に現在の内容を版として保存する。
        # 保存後に呼ぶと、変更前の内容がどこにも残らない。
        before = Article.objects.get(pk=self.object.pk)
        before.snapshot(created_by=self.request.user, note="編集前の自動保存")

        response = super().form_valid(form)

        record(
            AuditLog.Action.UPDATE,
            actor=self.request.user, target=self.object, request=self.request,
            from_status=before.status, to_status=self.object.status,
        )
        return response
```

### 4.6 操作ログ

```python
# core/models.py（抜粋）
class AuditLog(models.Model):
    """「誰が・いつ・何に・何をしたか」の記録。

    設計上の注意:

      * 追記専用にする。書き換えや削除の口を作らない。
      * 対象オブジェクトを ForeignKey にしない。記事を削除したときに
        「削除した」という記録まで一緒に消えてしまうため、
        アプリラベル・モデル名・ID を文字列で持つ。
      * 記録に個人情報を残しすぎない。IP はハッシュで持つ。
    """

    class Action(models.TextChoices):
        CREATE = "create", "作成"
        UPDATE = "update", "更新"
        DELETE = "delete", "削除"
        SUBMIT_REVIEW = "submit_review", "レビュー依頼"
        APPROVE = "approve", "承認"
        REJECT = "reject", "差し戻し"
        RESTORE = "restore", "版の復元"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_logs",
    )
    actor_label = models.CharField("操作者名", max_length=150, blank=True, default="")
    action = models.CharField("操作", max_length=32, choices=Action.choices)

    target_app_label = models.CharField(max_length=100, blank=True, default="")
    target_model = models.CharField(max_length=100, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    target_repr = models.CharField(max_length=200, blank=True, default="")

    detail = models.JSONField("詳細", default=dict, blank=True)
    ip_hash = models.CharField("IPハッシュ", max_length=64, blank=True, default="")
    created_at = models.DateTimeField("日時", auto_now_add=True, db_index=True)
```

```python
# core/admin.py
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """操作ログは読むだけ。管理画面からの改ざんを塞ぐ。"""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
```

### 4.7 役割（グループ）を作るコマンド

```python
# core/management/commands/setup_groups.py（抜粋）
GROUP_PERMISSIONS: dict[str, list[str]] = {
    "投稿者": [
        "blog.add_article",
        "blog.change_article",
        "blog.view_article",
        "media_library.add_mediaasset",
        "media_library.view_mediaasset",
    ],
    "編集者": [
        "blog.add_article", "blog.change_article", "blog.delete_article",
        "blog.view_article",
        "blog.publish_article",     # ← 投稿者には無い
        "blog.review_article",      # ← 投稿者には無い
        "comments.change_comment", "comments.delete_comment",
        "comments.view_comment",
        "media_library.add_mediaasset", "media_library.change_mediaasset",
        "media_library.view_mediaasset",
    ],
    "サイト管理者": [...],
}


class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args, **options):
        for group_name, dotted_permissions in GROUP_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=group_name)
            ...
            # set() なので、リストから消した権限はグループからも消える。
            # add() だけにすると、権限を絞る変更が既存環境へ反映されない。
            group.permissions.set(permissions)
```

---

## 5. コードの意味

### `Meta.permissions`

```python
permissions = [
    ("publish_article", "記事を公開できる"),
    ("review_article", "記事のレビューを承認できる"),
]
```

| 部分 | 意味 |
| --- | --- |
| `"publish_article"` | 権限のコード名。`user.has_perm("blog.publish_article")` で使う |
| `"記事を公開できる"` | 管理画面に表示される説明 |

Django はモデルごとに `add_` `change_` `delete_` `view_` の4つを自動で作ります。
それ以外の「業務上の権限」は、自分で定義します。

### `@transaction.atomic`

```python
@transaction.atomic
def form_valid(self, form):
    before.snapshot(...)      # 1. 履歴を保存
    response = super().form_valid(form)   # 2. 記事を更新
    record(...)               # 3. 操作ログを保存
```

3つの処理を **すべて成功するか、すべて無かったことにするか** のどちらかにします。

これが無いと、次のような中途半端な状態が起こりえます。

- 履歴は保存されたが、記事の更新が失敗した
- 記事は更新されたが、操作ログが残らなかった

### `update_fields` を使う保存

```python
article.save(update_fields=["status", "published_at", "updated_at"])
```

指定した列だけを UPDATE します。

利点は、他の人が同時に別の列を編集していても上書きしないことです。
ただし **落とし穴があります**（7日目で踏みます）。
`save()` の中で内部的に変えた列を `update_fields` に入れ忘れると、
その変更がデータベースへ反映されません。

### `record()` ヘルパー

```python
record(
    AuditLog.Action.APPROVE,
    actor=request.user,
    target=article,
    request=request,
    published_at=article.published_at.isoformat(),
)
```

キーワード引数はそのまま `detail`（JSONField）へ入ります。
操作ごとに残したい情報が違うため、固定の列にせず JSON にしています。

### `get_or_create` と `set()`

```python
group, created = Group.objects.get_or_create(name=group_name)
group.permissions.set(permissions)
```

| メソッド | 動き |
| --- | --- |
| `get_or_create` | あれば取得、無ければ作成。戻り値は `(オブジェクト, 作成したか)` |
| `set()` | 関連を **置き換える**（リストに無いものは外れる） |
| `add()` | 関連を **足す**（既存は残る） |

`set()` を使う理由は、あとから権限を絞る変更をしたときに、
既存の環境からもその権限が消えるようにするためです。
`add()` だけだと、絞ったつもりが古い環境に残り続けます。

---

## 6. 内部で起きていること

### 予約投稿は cron を必要としない

「未来の日時になったら公開する」という機能は、
定期実行の仕組み（cron）が必要に見えます。**必要ありません。**

```python
def published(self):
    return self.filter(
        status=Article.Status.PUBLISHED,
        published_at__isnull=False,
        published_at__lte=timezone.now(),   # ← ここ
    )
```

`timezone.now()` は **クエリを実行するたびに評価されます**。

```text
8月4日 13:00 にアクセス  →  published_at <= '2026-08-04 13:00' で検索
8月5日 09:00 にアクセス  →  published_at <= '2026-08-05 09:00' で検索
```

公開日時が `2026-08-05 08:00` の記事は、
8月5日 08:00 を過ぎた最初のアクセスから自然に一覧へ現れます。
**何も動かさなくても、時間が経つだけで公開されます。**

cron を使う設計にすると、cron が止まっていた間だけ記事が出ない、
という障害が起きます。この方式ならその心配がありません。

### リビジョンが増える場所

```text
記事を編集
   ↓
編集前の内容を ArticleRevision へ保存    ← 1件
   ↓
記事を更新

過去版を復元
   ↓
復元前の内容を ArticleRevision へ保存    ← 1件（これで復元を取り消せる）
   ↓
記事を書き戻す
```

「復元前の自動保存」を取っておくのが要点です。
これが無いと、間違えて復元したときに元へ戻せません。

### 操作ログを外部キーにしない理由

```python
# こう書くと、記事を削除した瞬間にログも消える
target = models.ForeignKey(Article, on_delete=models.CASCADE)

# こう書くと、記事が消えても記録は残る
target_app_label = models.CharField(max_length=100)
target_model = models.CharField(max_length=100)
target_id = models.CharField(max_length=64)
target_repr = models.CharField(max_length=200)
```

「誰が記事を削除したか」を残したいのに、
削除と同時に記録が消えては意味がありません。

さらに、削除の記録は **削除の前** に取ります。

```python
def form_valid(self, form):
    # 削除の記録は削除の前に取る。
    # 後に取ると、対象が消えていて何を消したのか書けない。
    record(AuditLog.Action.DELETE, actor=..., target=self.object,
           title=self.object.title)
    return super().form_valid(form)
```

---

## 7. コマンドの説明

### `python manage.py setup_groups`

| 項目 | 内容 |
| --- | --- |
| 目的 | 投稿者・編集者・サイト管理者のグループと権限を作る |
| 実行場所 | `manage.py` があるディレクトリ |
| 正常例 | `作成: 投稿者（権限 5 件）` `作成: 編集者（権限 12 件）` |
| 異常例 | `見つからない権限をとばしました: blog.publish_article`（`migrate` 前） |
| 判断方法 | 管理画面の「グループ」に3つ並ぶ |

**何度実行しても同じ結果になります**（冪等）。
`migrate` の後に必ず実行する運用にしておくと、全環境の役割定義がそろいます。

異常例の警告が出たら、先に `migrate` してください。
独自権限は `migrate` で `auth_permission` に登録されます。

### `python manage.py test blog.tests.test_workflow`

ワークフローのテストだけを実行します。

```text
Ran 20 tests in 2.1s
OK
```

---

## 8. よくあるエラー

記録は [`docs/errors/day-05.md`](../errors/day-05.md) にあります。

### 8.1 権限を厳しくしたら、3日目のテストが3件落ちた

```text
FAIL: test_author_can_create
AssertionError: 200 != 302

ERROR: test_author_cannot_be_spoofed
blog.models.Article.DoesNotExist: Article matching query does not exist.
```

**原因**: これは **バグではなく仕様変更** です。
3日目のテストは「記事を書ける利用者が `status=published` で投稿する」前提でした。
5日目に公開を独立権限にしたため、フォームが検証エラーで再表示され、
リダイレクト（302）ではなく 200 が返ります。

**判断のしかた**:

| 状況 | 直す場所 |
| --- | --- |
| 意図せず壊れた | 実装 |
| 意図して仕様を変えた | テスト |

今回は後者なので、テストを新しい仕様へ合わせます。
このとき「とりあえず通るように書き換える」のではなく、
**新しい仕様を表現するテストになっているか** を確認します。

```python
def _payload(self, **overrides):
    # 既定は下書き。公開は publish 権限を持つ利用者で試す。
    data = {..., "status": Article.Status.DRAFT}
    data.update(overrides)
    return data
```

### 8.2 履歴が「変更後」の内容で保存される

**原因**: `super().form_valid(form)` を先に呼ぶと、
その時点で `self.object` は保存済みの新しい内容になります。

**対処**: 保存の **前** に、データベースから読み直した内容を版にします。

```python
before = Article.objects.get(pk=self.object.pk)
before.snapshot(created_by=self.request.user, note="編集前の自動保存")
response = super().form_valid(form)
```

`self.object` をそのまま使わないのは、
`ModelFormMixin` がフォームの値をすでに反映している場合があるためです。

### 8.3 「公開」を選べない

**仕様です。** `blog.publish_article` 権限が無いユーザーには、
`status` の選択肢から「公開」が消えます。

管理画面から、そのユーザーを「編集者」グループへ入れてください。

```bash
python manage.py setup_groups
```

### 8.4 自分の記事を承認できない

**仕様です。**

```python
if article.author_id == request.user.pk and not request.user.is_superuser:
    messages.error(request, "自分の記事は自分で承認できません。")
```

自分で書いて自分で承認できるなら、承認フローは形だけになります。
1人で運用している場合は、`superuser` で承認するか、
直接「公開」を選んでください。

---

## 9. 動作確認

### 権限の分離

- [ ] 「投稿者」グループのユーザーで記事を作ると、状態に「公開」が無い
- [ ] そのユーザーが `status=published` を直接 POST しても、記事が作られない
- [ ] 「編集者」グループのユーザーには「公開」が出る

2つ目は開発者ツールか `curl` で試してください。
画面から消えているだけでは対策になりません。

### ワークフロー

- [ ] 下書きの記事に「レビューを依頼」ボタンが出る
- [ ] 依頼すると状態が「レビュー待ち」になる
- [ ] 編集者の画面に「承認して公開」「差し戻す」が出る
- [ ] 承認すると公開され、一覧に現れる
- [ ] 差し戻すと下書きへ戻り、理由が操作ログに残る
- [ ] 編集者が **自分の** 記事を承認しようとすると断られる
- [ ] ワークフローの URL を GET で開くと 405（Method Not Allowed）

### 予約投稿

- [ ] 公開日時を1時間後にして公開すると、一覧に出ない
- [ ] 記事詳細に「予約投稿です。◯月◯日 ◯◯:◯◯ に公開されます」と出る
- [ ] 公開日時を過去に変えると、**何も実行しなくても**一覧に現れる

### リビジョン

- [ ] 記事を編集すると履歴が1件増える
- [ ] 履歴に残っているのは **変更前** の内容
- [ ] 過去版を復元すると本文が戻る
- [ ] 復元後も履歴が残っていて、復元を取り消せる
- [ ] 公開中の記事を復元しても、公開状態は変わらない
- [ ] 他人の記事の履歴を開こうとすると 403

### 操作ログ

- [ ] 記事の作成・更新・削除・承認が記録される
- [ ] 記事を削除しても、削除の記録は残る
- [ ] 管理画面から操作ログを追加・編集・削除できない
- [ ] IP がハッシュ（64文字）で保存されている

---

## 10. セキュリティ上の注意

### 「書ける」と「公開できる」を分ける

これが今日いちばん重要な設計です。

```text
【分けていない場合】
投稿者のアカウントが1つ乗っ取られる
   → その場でトップページに任意の内容を公開できる

【分けている場合】
投稿者のアカウントが1つ乗っ取られる
   → 下書きは作れるが、公開はできない
   → 編集者が承認しない限り、外からは見えない
```

被害の大きさがまったく違います。

### 画面から消すだけでは対策にならない

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

**2つとも書いてください。** 上だけでは、
`curl -d "status=published"` で通ってしまいます。

### 状態を変える URL は POST のみ

```python
class ArticleWorkflowView(LoginRequiredMixin, View):
    """状態を変える操作の共通土台。

    すべて POST のみ。GET で状態が変わる URL を作ってはいけない。
    """
    def post(self, request, slug):
        ...
    # get() を定義しない → GET は 405 になる
```

`/articles/xxx/approve/` を GET で実行できると、
編集者にそのURLを踏ませるだけで記事を公開させられます。

### 操作ログは追記専用にする

```python
def has_change_permission(self, request, obj=None):
    return False

def has_delete_permission(self, request, obj=None):
    return False
```

書き換えられるログは、監査の役に立ちません。
「不正をした人が自分の記録を消せる」状態を作らないでください。

### 復元で公開状態を変えない

```python
# status と published_at は戻さない。
# 復元操作が同時に公開状態まで変えると事故になる。
article.save(update_fields=["title", "body", "updated_at"])
```

「公開中の記事の本文だけを、1つ前の版に戻したい」が実務で最も多い操作です。
このとき状態まで戻ると、記事が突然非公開になります。

---

## 11. 今日の復習問題

**問1.** 「記事を書ける権限」と「記事を公開できる権限」を分ける利点を、
攻撃を受けた場合の被害の違いで説明してください。

**問2.** フォームの `choices` から「公開」を消すだけでは不十分なのはなぜですか。

**問3.** 予約投稿に定期実行（cron）が不要なのはなぜですか。

**問4.** 操作ログの対象を `ForeignKey` にせず、
アプリラベル・モデル名・ID の文字列で持つのはなぜですか。

**問5.** 記事の更新でリビジョンを保存するとき、
`super().form_valid(form)` の **前** に保存しなければならないのはなぜですか。

<details>
<summary>解答</summary>

**問1.**
分けていない場合、投稿者アカウントを1つ乗っ取られただけで、
公開ページへ任意の内容を出せます。
分けていれば、乗っ取られても作れるのは下書きまでで、
編集者が承認しない限り外部からは見えません。

**問2.**
POST は画面を経由せずに送れるためです。
`curl` や開発者ツールから `status=published` を直接送れば、
画面に選択肢が無くても値は届きます。
サーバー側の検証（`clean_status()`）でも弾く必要があります。

**問3.**
公開判定に使う `timezone.now()` が、クエリを実行するたびに評価されるためです。
公開日時が過ぎていれば、次のアクセスから自然に一覧へ現れます。
cron 方式だと、cron が止まっていた間だけ記事が出ないという障害が起きます。

**問4.**
外部キーにすると、記事を削除したときに
「誰が削除したか」という記録まで一緒に消えてしまうためです。
文字列で持てば、対象が消えても記録は残ります。

**問5.**
`super().form_valid(form)` を呼んだ時点で記事は保存済みになり、
`self.object` は新しい内容になっています。
その後にスナップショットを取ると、「変更後」の内容が履歴として残り、
変更前の内容がどこにも残りません。

</details>

---

## 12. Git の差分

```text
タグ    : day-05
コミット: day-05: 下書き・レビュー・承認・予約投稿・リビジョン・操作ログ
```

```bash
git diff day-04 day-05
```

権限の変更だけを見たい場合はこちらです。

```bash
git show day-05 -- blog/forms.py core/management/commands/setup_groups.py
```

---

## 13. 次回予告

6日目は、公開サイトとしての体裁を整えます。

- SEO タイトル・説明文・canonical URL
- OGP と X カード
- **構造化データ（JSON-LD）をテンプレートに手書きしない理由**
- XML サイトマップと RSS
- パンくずリスト
- サイト設定とテーマ

6日目には、テストが全部通っている状態で見つかったバグの話も出てきます。
「サイトマップと canonical URL が別のドメインを指していた」という問題です。

次回 → [【6日目】Django CMS の SEO 対策](day-06.md)
