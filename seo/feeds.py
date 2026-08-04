"""RSS / Atom フィード。"""

from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils.feedgenerator import Atom1Feed

from blog.models import Article

from .models import SiteSetting


class LatestArticlesFeed(Feed):
    """最新記事の RSS 2.0 フィード。

    絶対URLの出所は SiteSetting.base_url に統一する。
    Django は既定でリクエストのホスト名を使うため、
    次の3か所をそれぞれ上書きしないと、内部ホスト名が混ざる。

        link()      … チャンネルのリンク
        item_link() … 各記事のリンクと guid
        feed_url()  … <atom:link rel="self"> （自分自身のURL）

    3つ目は見落としやすい。1つ直すと他が直ったように見えるが、
    XML を実際に読むと1か所だけ別ドメインが残る。
    """

    #: <atom:link rel="self"> に使う URL 名。サブクラスで差し替える。
    self_url_name = "seo:feed"

    @property
    def setting(self) -> SiteSetting:
        """毎回読み直す。

        Feed のインスタンスは URLconf の読み込み時に1個だけ作られ、
        プロセスが生きているあいだ使い回される。
        ここで self へキャッシュすると、管理画面でサイト名やURLを変えても
        プロセスを再起動するまでフィードに反映されない。

        フィード自体が cache_page で5分キャッシュされるので、
        毎回1クエリ増えることによる負荷はほぼない。
        """
        return SiteSetting.load()

    def title(self) -> str:
        return self.setting.site_name

    def description(self) -> str:
        return self.setting.description or self.setting.tagline or self.setting.site_name

    def link(self) -> str:
        # 絶対URLを返す。
        # Django の add_domain() は、すでに http:// / https:// で始まる URL を
        # そのまま通すため、これでサイト設定のドメインが使われる。
        # 相対パスのまま返すと、リクエストのホスト名から組み立てられてしまい、
        # canonical URL やサイトマップと食い違う。
        return self.setting.absolute_url(reverse("blog:article_list"))

    def feed_url(self, obj=None) -> str:
        """<atom:link rel="self"> の URL。

        既定では request.path から組み立てられるため、
        リバースプロキシの内部ホスト名がそのまま出てしまう。
        """
        return self.setting.absolute_url(reverse(self.self_url_name))

    def items(self):
        # フィードにも published() を必ず通す。
        # RSS リーダーは購読者の手元にキャッシュされるため、
        # 一度漏れると取り消せない。
        return Article.objects.published().with_related()[:20]

    def item_title(self, item: Article) -> str:
        return item.title

    def item_description(self, item: Article) -> str:
        # 本文全体ではなく要約を配信する。
        # 全文を出すと、フィードだけ読まれてサイトに来なくなる。
        return item.display_seo_description

    def item_link(self, item: Article) -> str:
        return self.setting.absolute_url(item.get_absolute_url())

    def item_pubdate(self, item: Article):
        return item.published_at

    def item_updateddate(self, item: Article):
        return item.updated_at

    def item_author_name(self, item: Article) -> str:
        return item.author.byline

    def item_categories(self, item: Article):
        return [item.category.name] + [tag.name for tag in item.tags.all()]


class LatestArticlesAtomFeed(LatestArticlesFeed):
    """同じ内容の Atom 版。"""

    feed_type = Atom1Feed
    subtitle = LatestArticlesFeed.description
    self_url_name = "seo:feed_atom"
