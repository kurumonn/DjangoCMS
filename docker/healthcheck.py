"""コンテナの死活監視。compose の healthcheck から実行される。

    python docker/healthcheck.py

なぜ `curl http://127.0.0.1:8000/healthz/` で済まないのか:

コンテナの中から自分自身を叩くと、**nginx を通らない**。
そのため本番設定の2つの仕組みに、両方とも引っかかる。

1. ALLOWED_HOSTS
   Host は `127.0.0.1:8000` になる。本番の ALLOWED_HOSTS は
   `cms.example.com` なので、Django は 400 を返す。

2. SECURE_SSL_REDIRECT
   nginx が付けるはずの `X-Forwarded-Proto: https` が無いので、
   Django は「HTTP で来た」と判断して 301 を返す。

どちらも設定が正しいからこそ起きる。
「監視が落ちているから設定を緩める」は逆で、
**監視側が、本番と同じ形のリクエストを送る**のが正しい。

このスクリプトは nginx のふりをして、その2つのヘッダーを付けて叩く。
"""

import os
import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000/healthz/"
TIMEOUT = 5


def first_allowed_host() -> str:
    """ALLOWED_HOSTS の先頭を Host ヘッダーに使う。

    設定を二重管理しない。ここに固定値を書くと、
    ドメインを変えたときに監視だけ古いままになる。
    """
    hosts = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")]
    hosts = [h for h in hosts if h]
    if not hosts:
        print("DJANGO_ALLOWED_HOSTS が未設定です", file=sys.stderr)
        sys.exit(1)
    return hosts[0]


def main() -> int:
    request = urllib.request.Request(
        URL,
        headers={
            "Host": first_allowed_host(),
            # nginx が付けるヘッダーを再現する。
            # 無いと SECURE_SSL_REDIRECT が 301 を返す。
            "X-Forwarded-Proto": "https",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            if response.status != 200:
                print(f"healthz が {response.status} を返しました", file=sys.stderr)
                return 1
    except urllib.error.HTTPError as exc:
        # 400 なら ALLOWED_HOSTS、301 なら X-Forwarded-Proto を疑う。
        print(f"healthz が {exc.code} を返しました: {exc.reason}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"healthz へ到達できません: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
