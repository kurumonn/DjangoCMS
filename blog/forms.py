"""記事の入力フォーム。

View は「入力を受け取ってレスポンスを返す」役割、
Form は「入力が正しいかを検証する」役割に分ける。
検証を View へ書くと、投稿・編集・API で同じチェックを3回書くことになる。
"""

from django import forms
from django.utils import timezone

from .models import Article


class ArticleForm(forms.ModelForm):
    """記事の投稿・編集フォーム。

    author はフォームに含めない。画面から送られてきた値で著者を決めると、
    他人の名前で記事を投稿できてしまうため、View 側で request.user を入れる。
    """

    class Meta:
        model = Article
        fields = ["title", "body", "category", "tags", "status", "published_at"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 18}),
            "published_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "tags": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # datetime-local 入力は "YYYY-MM-DDTHH:MM" 形式しか受け付けない。
        self.fields["published_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["tags"].required = False

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        published_at = cleaned.get("published_at")

        # 「公開」にしたのに公開日時が無い場合は、現在時刻を補う。
        # 空のままだと published() の条件に一致せず、
        # 「公開したはずなのに一覧に出ない」という分かりにくい状態になる。
        if status == Article.Status.PUBLISHED and not published_at:
            cleaned["published_at"] = timezone.now()

        return cleaned
