"""CMS の役割（グループ）を作成する。

    python manage.py setup_groups

何度実行しても同じ結果になる（冪等）。権限を絞る変更をしたときは、
このコマンドを再実行すれば全環境の役割定義がそろう。

役割の設計方針は「既定で最小、必要なものだけ足す」。

    投稿者 (Author)  自分の記事を書き、レビューを依頼できる。公開はできない。
    編集者 (Editor)  すべての記事を編集し、承認して公開できる。コメントも管理する。
    管理者 (Admin)   上記に加え、カテゴリ・タグ・固定ページ・メディアを管理できる。

「投稿者がそのまま公開できる」構成にしないのが要点。
公開を独立した権限にしておくと、アカウントを1つ乗っ取られても
いきなり公開ページを書き換えられる事態を避けられる。
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

# グループ名 -> 権限（"app_label.codename"）
GROUP_PERMISSIONS: dict[str, list[str]] = {
    "投稿者": [
        "blog.add_article",
        "blog.change_article",
        "blog.view_article",
        "media_library.add_mediaasset",
        "media_library.view_mediaasset",
    ],
    "編集者": [
        "blog.add_article",
        "blog.change_article",
        "blog.delete_article",
        "blog.view_article",
        "blog.publish_article",
        "blog.review_article",
        "comments.change_comment",
        "comments.delete_comment",
        "comments.view_comment",
        "media_library.add_mediaasset",
        "media_library.change_mediaasset",
        "media_library.view_mediaasset",
    ],
    "サイト管理者": [
        "blog.add_article",
        "blog.change_article",
        "blog.delete_article",
        "blog.view_article",
        "blog.publish_article",
        "blog.review_article",
        "blog.add_category",
        "blog.change_category",
        "blog.delete_category",
        "blog.view_category",
        "blog.add_tag",
        "blog.change_tag",
        "blog.delete_tag",
        "blog.view_tag",
        "comments.change_comment",
        "comments.delete_comment",
        "comments.view_comment",
        "pages.add_page",
        "pages.change_page",
        "pages.delete_page",
        "pages.view_page",
        "media_library.add_mediaasset",
        "media_library.change_mediaasset",
        "media_library.delete_mediaasset",
        "media_library.view_mediaasset",
        "core.view_auditlog",
    ],
}


class Command(BaseCommand):
    help = "投稿者・編集者・サイト管理者のグループと権限を作成する"

    @transaction.atomic
    def handle(self, *args, **options):
        for group_name, dotted_permissions in GROUP_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=group_name)

            permissions = []
            missing = []
            for dotted in dotted_permissions:
                app_label, codename = dotted.split(".", 1)
                permission = Permission.objects.filter(
                    content_type__app_label=app_label, codename=codename
                ).first()
                if permission is None:
                    missing.append(dotted)
                else:
                    permissions.append(permission)

            # set() なので、リストから消した権限はグループからも消える。
            # add() だけにすると、権限を絞る変更が既存環境へ反映されない。
            group.permissions.set(permissions)

            state = "作成" if created else "更新"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{state}: {group_name}（権限 {len(permissions)} 件）"
                )
            )
            for dotted in missing:
                self.stdout.write(
                    self.style.WARNING(f"  見つからない権限をとばしました: {dotted}")
                )
