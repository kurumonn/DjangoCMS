"""ブログのビュー。

3日目で記事の一覧・詳細・投稿・編集・削除（CRUD）をそろえる。

  GET  /                    記事一覧
  GET  /articles/<slug>/    記事詳細
  GET  /articles/new/       投稿フォーム
  POST /articles/new/       投稿
  GET  /articles/<slug>/edit/    編集フォーム
  POST /articles/<slug>/edit/    更新
  POST /articles/<slug>/delete/  削除
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import ArticleForm
from .models import Article, Category, Tag


class ArticleListView(ListView):
    """公開済み記事の一覧。"""

    model = Article
    template_name = "blog/article_list.html"
    context_object_name = "articles"
    paginate_by = 10

    def get_queryset(self):
        # published() を通さないと、下書きや予約投稿が一般利用者へ漏れる。
        return Article.objects.published().with_related()


class ArticleDetailView(DetailView):
    """記事詳細。

    未公開記事は、著者本人とスタッフだけが確認できる（プレビュー）。
    それ以外には 404 を返す。403 を返すと「その slug の記事は存在する」
    という情報が漏れるため、存在自体を隠す。
    """

    model = Article
    template_name = "blog/article_detail.html"
    context_object_name = "article"

    def get_queryset(self):
        return Article.objects.all().with_related()

    def get_object(self, queryset=None):
        article = super().get_object(queryset)
        if article.is_visible_to_public:
            return article

        user = self.request.user
        if user.is_authenticated and (user == article.author or user.is_staff):
            return article

        raise Http404("記事が見つかりません。")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = context["article"]
        context["is_preview"] = not article.is_visible_to_public
        context["can_edit"] = _can_edit(self.request.user, article)
        return context


def _can_edit(user, article: Article) -> bool:
    """記事を編集・削除してよいか。

    判定をここ1か所にまとめる。View・テンプレート・API で
    別々の条件を書くと、片方だけ直し忘れて権限が抜ける。
    """
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return article.author_id == user.pk


class ArticleOwnerMixin:
    """自分の記事か、スタッフ権限があるときだけ通す。"""

    def get_object(self, queryset=None):
        article = super().get_object(queryset)
        if not _can_edit(self.request.user, article):
            raise PermissionDenied("この記事を編集する権限がありません。")
        return article


class ArticleCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Article
    form_class = ArticleForm
    template_name = "blog/article_form.html"
    permission_required = "blog.add_article"

    def form_valid(self, form):
        # 著者はフォームの値ではなく、ログイン中のユーザーで決める。
        form.instance.author = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "記事を作成しました。")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "記事を作成"
        return context


class ArticleUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, ArticleOwnerMixin, UpdateView
):
    model = Article
    form_class = ArticleForm
    template_name = "blog/article_form.html"
    permission_required = "blog.change_article"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "記事を更新しました。")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "記事を編集"
        return context


class ArticleDeleteView(
    LoginRequiredMixin, PermissionRequiredMixin, ArticleOwnerMixin, DeleteView
):
    model = Article
    template_name = "blog/article_confirm_delete.html"
    permission_required = "blog.delete_article"
    success_url = reverse_lazy("blog:article_list")

    def form_valid(self, form):
        messages.success(self.request, "記事を削除しました。")
        return super().form_valid(form)


class CategoryArticleListView(ArticleListView):
    """カテゴリ別の記事一覧。"""

    template_name = "blog/article_list.html"

    def get_queryset(self):
        from django.shortcuts import get_object_or_404

        self.category = get_object_or_404(Category, slug=self.kwargs["slug"])
        return super().get_queryset().filter(category=self.category)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heading"] = f"カテゴリ: {self.category.name}"
        return context


class TagArticleListView(ArticleListView):
    """タグ別の記事一覧。"""

    template_name = "blog/article_list.html"

    def get_queryset(self):
        from django.shortcuts import get_object_or_404

        self.tag = get_object_or_404(Tag, slug=self.kwargs["slug"])
        return super().get_queryset().filter(tags=self.tag)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["heading"] = f"タグ: {self.tag.name}"
        return context
