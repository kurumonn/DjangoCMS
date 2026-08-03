"""blog アプリの URL 定義。

app_name を付けると、テンプレートから {% url 'blog:index' %} のように
名前空間つきで参照できる。URL を後から変更してもテンプレートを直さずに済む。
"""

from django.urls import path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
]
