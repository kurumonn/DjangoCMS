"""メディアライブラリ。

アップロードした画像を1か所で管理し、記事から再利用する。
記事ごとに ImageField を持たせるだけだと、同じ画像を何度も
アップロードすることになり、差し替えも一括でできない。
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models

from .validators import ImageUploadValidator


def upload_to(instance, filename: str) -> str:
    """保存先のパスを決める。

    利用者が付けたファイル名は使わない。理由は3つある。

      1. ``../../etc/passwd`` のようなパス移動を狙う名前を防ぐ
      2. 日本語や記号を含む名前が環境によって壊れるのを防ぐ
      3. ``secret-contract.pdf`` のような名前から中身を推測されるのを防ぐ

    拡張子だけは検証済みのものを引き継ぐ。
    """
    extension = ""
    if "." in filename:
        extension = filename[filename.rfind(".") :].lower()
    stamp = instance.created_at if instance.created_at else None
    prefix = stamp.strftime("%Y/%m") if stamp else "unsorted"
    return f"library/{prefix}/{secrets.token_hex(16)}{extension}"


class MediaAsset(models.Model):
    """アップロードされた1つの画像。"""

    file = models.ImageField(
        "ファイル",
        upload_to=upload_to,
        validators=[ImageUploadValidator()],
        width_field="width",
        height_field="height",
    )
    title = models.CharField("タイトル", max_length=200, blank=True, default="")
    alt_text = models.CharField(
        "代替テキスト",
        max_length=200,
        blank=True,
        default="",
        help_text="画像が見えない利用者へ内容を伝える文章。装飾目的なら空でよい。",
    )

    width = models.PositiveIntegerField("幅", default=0, editable=False)
    height = models.PositiveIntegerField("高さ", default=0, editable=False)
    byte_size = models.PositiveIntegerField("サイズ", default=0, editable=False)
    image_format = models.CharField("形式", max_length=10, blank=True, editable=False)
    checksum = models.CharField(
        "チェックサム",
        max_length=64,
        blank=True,
        editable=False,
        db_index=True,
        help_text="SHA-256。同じ画像の重複アップロードを検出する。",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="media_assets",
        verbose_name="アップロード者",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "メディア"
        verbose_name_plural = "メディア"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title or self.file.name

    def save(self, *args, **kwargs):
        # 新規アップロード時だけ、実体からメタ情報を採る。
        if self.file and not self.checksum:
            payload = self.file.read()
            self.file.seek(0)
            self.checksum = hashlib.sha256(payload).hexdigest()
            self.byte_size = len(payload)
        super().save(*args, **kwargs)

    @property
    def display_alt(self) -> str:
        return self.alt_text or self.title
