"""blog アプリの URL 定義。

URL の並び順は上から順に照合される。
"articles/new/" を "articles/<slug>/" より先に置かないと、
"new" がスラッグとして解釈されてしまう。
"""

from django.urls import path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.ArticleListView.as_view(), name="article_list"),
    path("search/", views.SearchView.as_view(), name="search"),
    path("articles/new/", views.ArticleCreateView.as_view(), name="article_create"),
    path("articles/<slug:slug>/", views.ArticleDetailView.as_view(), name="article_detail"),
    path(
        "articles/<slug:slug>/edit/",
        views.ArticleUpdateView.as_view(),
        name="article_update",
    ),
    path(
        "articles/<slug:slug>/delete/",
        views.ArticleDeleteView.as_view(),
        name="article_delete",
    ),
    path(
        "categories/<slug:slug>/",
        views.CategoryArticleListView.as_view(),
        name="category_detail",
    ),
    path("tags/<slug:slug>/", views.TagArticleListView.as_view(), name="tag_detail"),
]
