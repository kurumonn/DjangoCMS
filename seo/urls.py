"""SEO 関連の URL（サイトマップ・RSS・robots.txt）。"""

from django.contrib.sitemaps.views import sitemap
from django.urls import path
from django.views.decorators.cache import cache_page

from .feeds import LatestArticlesAtomFeed, LatestArticlesFeed
from .sitemaps import SITEMAPS
from .views import robots_txt

app_name = "seo"

urlpatterns = [
    # サイトマップは全記事を走査するため、キャッシュして負荷を抑える。
    path(
        "sitemap.xml",
        cache_page(60 * 60)(sitemap),
        {"sitemaps": SITEMAPS},
        name="sitemap",
    ),
    path("feed/", cache_page(60 * 5)(LatestArticlesFeed()), name="feed"),
    path("feed/atom/", cache_page(60 * 5)(LatestArticlesAtomFeed()), name="feed_atom"),
    path("robots.txt", robots_txt, name="robots"),
]
