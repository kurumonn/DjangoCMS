"""コメント投稿フォーム。"""

from __future__ import annotations

import time

from django import forms
from django.utils import timezone

from .models import Comment

# 送信までの最短時間（秒）。人間はこれより速くフォームを埋められない。
MIN_FILL_SECONDS = 3

# フォーム表示から送信までの猶予（秒）。古すぎるトークンは拒否する。
MAX_FORM_AGE_SECONDS = 60 * 60 * 6


class CommentForm(forms.ModelForm):
    """コメント投稿フォーム。

    CAPTCHA を使わずにスパムを減らす手段を2つ入れる。

      1. ハニーポット … 人間には見えない入力欄。自動入力ボットだけが埋める。
      2. 送信までの時間 … 表示から3秒未満の送信は機械とみなす。

    どちらも完璧ではないが、利用者に負担をかけずに大半の自動投稿を落とせる。
    """

    # 見えない欄。CSS で隠し、autocomplete も切る。
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "honeypot",
                "tabindex": "-1",
                "autocomplete": "off",
                "aria-hidden": "true",
            }
        ),
        label="ウェブサイト（入力しないでください）",
    )
    # フォームを表示した時刻。改ざんは CSRF と併せて検知する。
    rendered_at = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Comment
        fields = ["name", "email", "body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5, "maxlength": 2000}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if not self.is_bound:
            self.fields["rendered_at"].initial = int(time.time())
        if user is not None and user.is_authenticated:
            # ログイン中は名前・メールを再入力させない。
            self.fields["name"].required = False
            self.fields["name"].widget = forms.HiddenInput()
            self.fields["email"].widget = forms.HiddenInput()
            self.fields["email"].required = False

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("送信を受け付けられませんでした。")
        return ""

    def clean_rendered_at(self):
        value = self.cleaned_data.get("rendered_at")
        if value is None:
            # 隠しフィールドが無い＝フォームを経由していない可能性が高い。
            raise forms.ValidationError("送信を受け付けられませんでした。")

        elapsed = int(time.time()) - int(value)
        if elapsed < MIN_FILL_SECONDS:
            raise forms.ValidationError(
                "送信が速すぎます。数秒おいてからもう一度お試しください。"
            )
        if elapsed > MAX_FORM_AGE_SECONDS:
            raise forms.ValidationError(
                "フォームの有効期限が切れました。ページを再読み込みしてください。"
            )
        return value

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        if len(body) < 2:
            raise forms.ValidationError("本文が短すぎます。")
        return body

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if self.user is not None and self.user.is_authenticated:
            return self.user.byline
        if not name:
            raise forms.ValidationError("表示名を入力してください。")
        return name

    def save(self, commit=True):
        comment = super().save(commit=False)
        if self.user is not None and self.user.is_authenticated:
            comment.author = self.user
            comment.name = self.user.byline
        # 承認は管理者が行う。既定では公開しない。
        comment.is_approved = False
        if commit:
            comment.save()
        return comment
