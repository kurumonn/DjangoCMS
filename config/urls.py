"""KururuCMS のルート URLconf。

リクエストは必ずここを最初に通り、上から順にパターンが照合される。
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # 管理画面のパスは環境変数で変更できるようにしておく。
    # 既定の /admin/ は総当たり攻撃の標的になりやすい。
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
    # ログイン・ログアウト・パスワード変更。
    # 8日目に django-allauth へ置き換える。
    path("accounts/", include("django.contrib.auth.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("pages/", include("pages.urls")),
    # sitemap.xml / feed / robots.txt はサイト直下に置く。
    path("", include("seo.urls")),
    path("", include("comments.urls")),
    path("", include("blog.urls")),
]

if settings.DEBUG:
    # 開発時のみ Django がメディアファイルを配信する。
    # 本番では Nginx が配信する（デプロイ編6日目）。
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
