"""簡易レート制限。

コメント投稿・自動保存・ログインなど、「短時間に何度も叩かれると困る」
入口の前に置く。Django のキャッシュを使うため、追加パッケージは要らない。

制限の単位は「キー」。キーの作り方で意味が変わる。

    comment:<記事ID>:<IPハッシュ>   同じ人が同じ記事へ連投するのを止める
    login:<ユーザー名>              1アカウントへの総当たりを止める
    login:<IPハッシュ>              1か所から多数アカウントを試すのを止める

注意: 既定のローカルメモリキャッシュはプロセスごとに独立する。
Gunicorn を複数ワーカーで動かすと制限がワーカー数だけ緩くなるため、
本番では Redis を共有キャッシュにする（10日目）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.core.cache import cache


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int  # 秒


def _bucket_key(key: str) -> str:
    return f"ratelimit:{key}"


def check_rate_limit(key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
    """`window_seconds` 秒の間に `limit` 回まで許可する。

    「窓」を固定長で区切る単純な方式（fixed window）。
    窓の境目で瞬間的に2倍まで通る弱点があるが、実装が単純で読みやすく、
    嫌がらせを止める目的には十分機能する。
    """
    now = int(time.time())
    window_start = now - (now % window_seconds)
    cache_key = f"{_bucket_key(key)}:{window_start}"

    # add() は「まだ無いときだけ入れる」。競合しても最初の1回だけ成功する。
    cache.add(cache_key, 0, timeout=window_seconds)
    try:
        count = cache.incr(cache_key)
    except ValueError:
        # add と incr の間にキーが失効した場合。作り直す。
        cache.set(cache_key, 1, timeout=window_seconds)
        count = 1

    retry_after = window_start + window_seconds - now
    if count > limit:
        return RateLimitResult(allowed=False, remaining=0, retry_after=retry_after)
    return RateLimitResult(
        allowed=True, remaining=limit - count, retry_after=retry_after
    )


def client_ip(request) -> str:
    """リクエスト元の IP を取得する。

    X-Forwarded-For をそのまま信用してはいけない。利用者が自由に付けられるため、
    偽装するとレート制限を無限に回避できる。
    信頼できるリバースプロキシ（Nginx）の背後にいるときだけ、
    プロキシが付けた「一番右から数えて自分のホップ」を採用する。
    ここでは設定 ``TRUSTED_PROXY_COUNT`` で段数を明示する。
    """
    from django.conf import settings

    proxy_count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxy_count > 0:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            # 右端は直近のプロキシ。信頼できる段数だけ右から数えて戻る。
            index = len(parts) - proxy_count
            if 0 <= index < len(parts):
                return parts[index]
    return request.META.get("REMOTE_ADDR", "")
