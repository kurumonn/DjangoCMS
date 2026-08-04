"""robots.txt。"""

from django.http import HttpResponse
from django.urls import reverse

from .models import SiteSetting


def robots_txt(request) -> HttpResponse:
    """robots.txt を動的に返す。

    ステージング環境で ``noindex_site`` を有効にすると、
    サイト全体をクロール拒否に切り替えられる。
    静的ファイルとして置くと、本番の robots.txt を
    ステージングへコピーしてしまう事故が起きやすい。

    注意: robots.txt は「クロールするな」であって
    「インデックスするな」ではない。確実に検索結果から外すには、
    各ページの meta robots に noindex を出す必要がある（base.html を参照）。
    """
    setting = SiteSetting.load()

    if setting.noindex_site:
        body = "User-agent: *\nDisallow: /\n"
    else:
        sitemap_url = setting.absolute_url(reverse("seo:sitemap"))
        lines = [
            "User-agent: *",
            "Allow: /",
            # 管理画面・認証・検索結果はクロールさせない。
            # 検索結果ページを拾わせると、同じ内容のページが大量に登録される。
            "Disallow: /accounts/",
            "Disallow: /search/",
            "",
            f"Sitemap: {sitemap_url}",
            "",
        ]
        body = "\n".join(lines)

    return HttpResponse(body, content_type="text/plain; charset=utf-8")
