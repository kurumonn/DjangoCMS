from django.urls import path

from . import api, views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="index"),
    path(
        "api/articles/<int:pk>/autosave/",
        api.AutosaveView.as_view(),
        name="autosave",
    ),
]
