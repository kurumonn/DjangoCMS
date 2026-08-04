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
    path(
        "articles/<slug:slug>/", views.ArticleDetailView.as_view(), name="article_detail"
    ),
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
    # 状態を変える操作はすべて POST 専用（View 側で get を実装していない）。
    path(
        "articles/<slug:slug>/submit/",
        views.ArticleSubmitReviewView.as_view(),
        name="article_submit_review",
    ),
    path(
        "articles/<slug:slug>/approve/",
        views.ArticleApproveView.as_view(),
        name="article_approve",
    ),
    path(
        "articles/<slug:slug>/reject/",
        views.ArticleRejectView.as_view(),
        name="article_reject",
    ),
    path(
        "articles/<slug:slug>/revisions/",
        views.ArticleRevisionListView.as_view(),
        name="article_revisions",
    ),
    path(
        "articles/<slug:slug>/revisions/<int:pk>/restore/",
        views.ArticleRevisionRestoreView.as_view(),
        name="article_revision_restore",
    ),
    path(
        "categories/<slug:slug>/",
        views.CategoryArticleListView.as_view(),
        name="category_detail",
    ),
    path("tags/<slug:slug>/", views.TagArticleListView.as_view(), name="tag_detail"),
]
