# KururuCMS

**10日で作る Django CMS ― 基礎からワンタイムコード・パスキー認証まで**、および
**10日で学ぶ Django 本番デプロイ ― Linux・Nginx・秘密鍵・Let's Encrypt・セキュリティ**
の成果物リポジトリです。

連載記事の1日分が、そのまま1つのタグ（`day-01` 〜 `day-20`）に対応します。
読者は「完成版」だけでなく「前日から何が変わったか」を `git diff` で確認できます。

```bash
git diff day-02 day-03      # 3日目に何を追加したか
git checkout day-05         # 5日目時点の状態で動かす
```

## 連載の対応表

### 第1部：CMS を作る

| タグ | 記事 | 完成する機能 |
| --- | --- | --- |
| `day-01` | [Django CMS 開発を始めよう](docs/articles/day-01.md) | プロジェクトの土台・カスタムユーザー |
| `day-02` | [Django モデル入門](docs/articles/day-02.md) | 記事・カテゴリ・タグ・固定ページ |
| `day-03` | [Django CRUD 完全入門](docs/articles/day-03.md) | 投稿・編集・削除・権限 |
| `day-04` | [Django CMS を実用化](docs/articles/day-04.md) | 画像・コメント・サイト内検索 |
| `day-05` | [WordPress 級の記事管理](docs/articles/day-05.md) | 下書き・予約投稿・リビジョン |
| `day-06` | [Django CMS の SEO 対策](docs/articles/day-06.md) | OGP・構造化データ・RSS・サイトマップ |
| `day-07` | [Django で管理画面を自作](docs/articles/day-07.md) | ダッシュボード・ブロックエディター |
| `day-08` | [django-allauth 完全入門](docs/articles/day-08.md) | メール認証・ワンタイムコード |
| `day-09` | [Django でパスキー認証](docs/articles/day-09.md) | TOTP・WebAuthn・復旧手段 |
| `day-10` | Django CMS 完成 | テスト・Docker・本番設定 |

### 第2部：本番へデプロイする

| タグ | 記事 | 完成するもの |
| --- | --- | --- |
| `day-11` | Linux サーバー初期設定 | 安全な作業ユーザーと更新基盤 |
| `day-12` | SSH 秘密鍵の安全な扱い | 公開鍵認証と root 制限 |
| `day-13` | Linux ファイアウォール入門 | 必要な入口だけを公開 |
| `day-14` | SECRET_KEY を Git へ置かない | 環境変数と権限設計 |
| `day-15` | systemd で常駐化 | Gunicorn + Uvicorn サービス |
| `day-16` | Nginx リバースプロキシ入門 | 転送と静的配信 |
| `day-17` | Let's Encrypt 完全入門 | HTTPS 証明書の取得 |
| `day-18` | TLS 秘密鍵を守る | HSTS・セキュリティヘッダー |
| `day-19` | 証明書切れを防ぐ | 自動更新・監視・バックアップ |
| `day-20` | Django 本番公開 | 検査・切り戻し・復旧 |

## 動かし方（開発環境）

```bash
python -m venv .venv
```

Linux / macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

続けて、依存パッケージのインストールとデータベースの初期化を行います。

```bash
pip install -r requirements.txt
```

```bash
python manage.py migrate
```

```bash
python manage.py createsuperuser
```

```bash
python manage.py runserver
```

`http://127.0.0.1:8000/` を開くとトップページが表示されます。

## セキュリティ方針

このリポジトリは学習用ですが、「学習用だから危なくてよい」とはしません。
公開する以上、そのままコピーされても事故が起きない構成を既定値にします。

- `SECRET_KEY` ・ DB パスワード・API トークンをリポジトリへ置かない（`.gitignore` で二重に防ぐ）
- `DEBUG=False` のとき、セキュアCookie と HTTPS リダイレクトが自動で有効になる
- パスワードハッシュは Argon2 を第一候補にする
- 外部 CDN を読み込まない（Content-Security-Policy を厳格に保つため）
- アップロードファイルは拡張子ではなく実体で検証する
- 認証まわりはレート制限と監査ログを前提にする

詳細は各日の記事、および `docs/` 配下を参照してください。

## ドキュメント

| 場所 | 内容 |
| --- | --- |
| [`docs/articles/`](docs/articles/) | 連載記事（13項目の統一構成） |
| [`docs/errors/`](docs/errors/) | **実際に発生した**エラーの記録。記事の「よくあるエラー」はここから引用 |

`docs/errors/` には、想像で書いた「起きそうなエラー」は入れていません。
開発中に手が止まった事実だけを、
「症状 / 再現条件 / 原因 / 直し方 / 判断方法」の形式で記録しています。

テストが全部通っている状態で見つかったバグも2件記録しています。

- [6日目](docs/errors/day-06.md): サイトマップと canonical URL が別ドメインを指していた
- [9日目](docs/errors/day-09.md): 編集者が他人の記事を編集できなかった

どちらも、ブラウザーで画面を出して初めて気づいたものです。

## スクリーンショットについて

画面キャプチャはブログ記事に載せるためのもので、**このリポジトリには含めていません**。
コードを読むうえで必要なものではなく、リポジトリを重くするだけだからです。

必要になったら、開発サーバーを起動した状態で次を実行すると
`docs/images/`（`.gitignore` 済み）へ生成されます。

```bash
python tools/capture_screenshots.py
```

内容が同じ画像ができた場合は警告が出ます（リダイレクトで別のページを
撮ってしまう事故の検出）。

記事側は画像を直接埋め込まず、次のマーカーだけを持ちます。

```text
<!-- screenshot: day-08-login.png | ログイン画面 -->
```

HTML コメントなので GitHub 上では何も表示されず、
ブログへ投稿するときにだけ実際の画像へ差し替えます。
どの画面のことかは、マーカーの直前の文が説明しています。

## ライセンス

MIT License（`LICENSE` を参照）。
