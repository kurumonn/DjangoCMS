"""ブログのビュー。

1日目はトップページだけ。View は「リクエストを受け取り、レスポンスを返す」役割に限定する。
"""

from django.views.generic import TemplateView


class IndexView(TemplateView):
    """CMS のトップページ。"""

    template_name = "blog/index.html"
