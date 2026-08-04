"""記事に載せるスクリーンショットを撮る。

    python tools/capture_screenshots.py

開発サーバー（既定 http://127.0.0.1:8810）へ接続し、
docs/images/ 配下に PNG を保存する。

保存先はリポジトリに含めない（`.gitignore` 済み）。
画像はブログ記事へ載せるためだけのもので、コードの理解には要らないためである。
記事側は `<!-- screenshot: ファイル名 | 説明 -->` というマーカーだけを持ち、
ブログへ投稿するときにそのマーカーを実画像へ差し替える。

なぜスクリプトにするか:

  * 手で撮ると、記事を書き直すたびに画面と食い違っていく
  * ウィンドウ幅や配色がばらつくと、記事の見た目がそろわない
  * 撮り直しが一発でできると、UI を直すことへの心理的な抵抗が減る
  * リポジトリに画像を置かなくても、必要なときに再生成できる

前提: playwright がインストール済みであること。

    pip install playwright
    python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "docs" / "images"

# (ファイル名, パス, ログインが必要か, 説明)
SHOTS: list[tuple[str, str, bool, str]] = [
    ("day-03-article-list.png", "/", False, "記事一覧"),
    ("day-04-article-detail.png", "/articles/csrf/", False, "記事詳細とコメント欄"),
    ("day-04-search.png", "/search/?q=%E6%8B%A1%E5%BC%B5%E5%AD%90", False, "サイト内検索"),
    ("day-06-sitemap.png", "/sitemap.xml", False, "XMLサイトマップ"),
    ("day-07-dashboard.png", "/dashboard/", True, "ダッシュボード"),
    ("day-07-block-editor.png", "/articles/csrf/edit/", True, "ブロックエディター"),
    ("day-08-login.png", "/accounts/login/", False, "ログイン画面"),
    ("day-08-login-by-code.png", "/accounts/login/code/", False, "ワンタイムコードの要求"),
    ("day-08-signup.png", "/accounts/signup/", False, "ユーザー登録"),
    ("day-09-mfa-index.png", "/accounts/2fa/", True, "多要素認証の一覧"),
    ("day-09-totp-activate.png", "/accounts/2fa/totp/activate/", True, "TOTPの設定（QRコード）"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8810")
    # ACCOUNT_LOGIN_METHODS = {"email"} なので、ログイン欄はメールアドレス。
    # ユーザー名を入れても通らない。
    parser.add_argument("--username", default="demo_editor@example.com")
    parser.add_argument("--password", default="demo-pass-phrase-1234")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument(
        "--dark", action="store_true", help="ダークテーマで撮る"
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright が見つかりません。\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def new_context():
            return browser.new_context(
                viewport={"width": args.width, "height": args.height},
                device_scale_factor=2,  # 高解像度。記事で拡大しても粗くならない。
                color_scheme="dark" if args.dark else "light",
                locale="ja-JP",
            )

        # ログイン前と後で、ブラウザーの状態（Cookie）を分ける。
        #
        # 1つのコンテキストで使い回すと、ログイン後に
        # /accounts/login/ を開いてもダッシュボードへリダイレクトされ、
        # 「ログイン画面のつもりがダッシュボードの写真」になる。
        # 実際にこれをやって、4枚が同じ画像になった。
        anon_context = new_context()
        anon_page = anon_context.new_page()

        auth_context = new_context()
        auth_page = auth_context.new_page()
        logged_in = _login(auth_page, args)

        saved = 0
        for filename, path, needs_login, label in SHOTS:
            if needs_login and not logged_in:
                print(f"  skip  {filename}（ログインできていない）")
                continue

            page = auth_page if needs_login else anon_page
            url = f"{args.base_url}{path}"
            page.goto(url, wait_until="networkidle")

            # 撮ろうとしたページと違うページが表示されていないか確かめる。
            # リダイレクトに気づかず撮り続けるのが、いちばんありがちな失敗。
            if not page.url.endswith(path) and path not in page.url:
                print(f"  skip  {filename}（{page.url} へ遷移した）")
                continue

            target = OUTPUT_DIR / filename
            page.screenshot(path=str(target), full_page=True)
            print(f"  saved {filename}  ({label})")
            saved += 1

        browser.close()

    _warn_about_duplicates()
    print(f"\n{saved} 枚を {OUTPUT_DIR} へ保存しました。")
    return 0


def _warn_about_duplicates() -> None:
    """同じ内容の画像が複数ないか確かめる。

    リダイレクトで別のページを撮ってしまうと、
    ファイル名は違うのに中身が同じ画像ができる。
    見た目では気づきにくいので、ハッシュで検出する。
    """
    import hashlib
    from collections import defaultdict

    by_hash: dict[str, list[str]] = defaultdict(list)
    for path in sorted(OUTPUT_DIR.glob("*.png")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        by_hash[digest].append(path.name)

    for names in by_hash.values():
        if len(names) > 1:
            print(f"  警告: 内容が同じ画像があります -> {', '.join(names)}")


def _login(page, args) -> bool:
    """ダッシュボードなど、ログインが要る画面のために認証する。"""
    page.goto(f"{args.base_url}/accounts/login/", wait_until="networkidle")

    # allauth のログインフォームは name="login" と name="password"。
    login_field = page.query_selector('input[name="login"]')
    if login_field is None:
        print("  ログインフォームが見つかりません。")
        return False

    login_field.fill(args.username)
    page.fill('input[name="password"]', args.password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")

    if "/accounts/login" in page.url:
        print("  ログインに失敗しました（ユーザー名かパスワードを確認）。")
        return False

    print(f"  ログイン成功: {page.url}")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
