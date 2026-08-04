"""コメント投稿。"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import View

from blog.models import Article
from core.ratelimit import check_rate_limit, client_ip

from .forms import CommentForm
from .models import hash_ip

# 同じ人が10分間に投稿できるコメント数。
COMMENT_LIMIT = 5
COMMENT_WINDOW_SECONDS = 600


class CommentCreateView(View):
    """記事詳細ページのコメントフォームからの POST を処理する。

    GET は受け付けない。コメント投稿は状態を変える操作なので、
    URL を踏むだけで実行できてはいけない。
    """

    def post(self, request, slug):
        article = get_object_or_404(Article, slug=slug)

        # 未公開記事にはコメントできない。
        if not article.is_visible_to_public:
            messages.error(request, "この記事にはコメントできません。")
            return redirect("blog:article_list")

        ip_hash = hash_ip(client_ip(request))
        result = check_rate_limit(
            f"comment:{ip_hash}",
            limit=COMMENT_LIMIT,
            window_seconds=COMMENT_WINDOW_SECONDS,
        )
        if not result.allowed:
            messages.error(
                request,
                f"コメントの投稿が続いています。{result.retry_after} 秒ほどおいてからお試しください。",
            )
            return redirect(article.get_absolute_url())

        form = CommentForm(request.POST, user=request.user)
        if not form.is_valid():
            # エラー内容をセッションへ持ち回すのではなく、
            # その場でフォーム付きの詳細ページを描画し直す。
            from django.shortcuts import render

            return render(
                request,
                "blog/article_detail.html",
                {
                    "article": article,
                    "comments": article.comments.approved(),
                    "comment_form": form,
                    "is_preview": False,
                    "can_edit": False,
                    "related_articles": [],
                },
                status=400,
            )

        comment = form.save(commit=False)
        comment.article = article
        comment.ip_hash = ip_hash
        comment.user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]
        comment.save()

        messages.success(
            request, "コメントを受け付けました。承認後に表示されます。"
        )
        return redirect(article.get_absolute_url())
