from django.urls import path

from . import views

app_name = "comments"

urlpatterns = [
    path(
        "articles/<slug:slug>/comments/",
        views.CommentCreateView.as_view(),
        name="create",
    ),
]
