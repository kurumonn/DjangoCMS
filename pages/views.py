"""固定ページのビュー。"""

from django.http import Http404
from django.views.generic import DetailView

from .models import Page


class PageDetailView(DetailView):
    model = Page
    template_name = "pages/page_detail.html"
    context_object_name = "page"

    def get_object(self, queryset=None):
        page = super().get_object(queryset)
        if page.status == Page.Status.PUBLISHED and page.published_at:
            from django.utils import timezone

            if page.published_at <= timezone.now():
                return page

        user = self.request.user
        if user.is_authenticated and user.is_staff:
            return page

        raise Http404("ページが見つかりません。")
