"""blog アプリの補助関数。"""

from __future__ import annotations

import secrets

from django.utils.text import slugify


def unique_slugify(model, source: str, *, instance=None, max_length: int = 200) -> str:
    """タイトルから一意なスラッグを作る。

    日本語だけのタイトルは ``slugify()`` の結果が空文字になる。
    その場合はランダムな英数字を割り当てて、URL が壊れないようにする。

    Args:
        model: 重複チェックの対象になるモデルクラス。
        source: 元になる文字列（記事タイトルなど）。
        instance: 更新中のオブジェクト。自分自身は重複とみなさない。
        max_length: スラッグの最大長。

    Returns:
        そのモデルの中で一意なスラッグ。
    """
    base = slugify(source, allow_unicode=False)[:max_length].strip("-")
    if not base:
        # 日本語のみのタイトルなど、ASCII へ落とせなかった場合。
        base = f"post-{secrets.token_hex(4)}"

    candidate = base
    queryset = model.objects.all()
    if instance is not None and instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    # 衝突したら -2, -3 … と連番を足す。
    counter = 2
    while queryset.filter(slug=candidate).exists():
        suffix = f"-{counter}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
        counter += 1

    return candidate
