#!/usr/bin/env bash
# データベースとアップロード画像のバックアップを取る。
#
#   ./scripts/backup.sh
#   ./scripts/backup.sh /mnt/backup       # 保存先を指定する
#
# 前提: compose の db / web コンテナが動いていること。
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

# .env から DB の名前とユーザーを読む。
# ここで値を直書きすると、パスワードを変えたときにバックアップだけ古いまま失敗する。
set -a
# shellcheck disable=SC1091
. ./.env
set +a

DB_DUMP="$BACKUP_DIR/db-$STAMP.dump"
MEDIA_TAR="$BACKUP_DIR/media-$STAMP.tar.gz"

echo "[backup] データベースを書き出します..."
# -Fc はカスタム形式。テキストの SQL より小さく、
# pg_restore で「テーブル単位の復元」ができる。
docker compose exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
    > "$DB_DUMP"

echo "[backup] アップロード画像を固めます..."
# コンテナ内のパスは、必ず `sh -c '...'` の中へ入れる。
# Windows の Git Bash は、引数に現れた /app のような絶対パスを
# Windows のパスへ勝手に書き換える（MSYS のパス変換）。
# 引用符でくくった1つの文字列にしておけば変換されない。
docker compose exec -T web sh -c 'cd /app && tar -cz media' \
    > "$MEDIA_TAR"

# ★ここが本題★
# 「バックアップを取った」ではなく「**戻せる**」ことを確かめる。
# 取れているつもりのファイルが 0 バイトだった、という事故は珍しくない。
echo "[backup] 取得したファイルを検査します..."
if [ ! -s "$DB_DUMP" ]; then
    echo "[backup] 失敗: データベースのダンプが空です" >&2
    exit 1
fi
# pg_restore --list は、ダンプの目次を読むだけで復元はしない。
# 壊れたダンプならここで失敗する。
#
# ファイル名を渡さないのが要点。標準入力から読ませる。
# `pg_restore --list /dev/stdin` と書くと
# 「did not find magic string in file header」で必ず失敗する。
# ファイル引数として開かれるとシークしようとするが、
# パイプはシークできないためである。
docker compose exec -T db sh -c 'pg_restore --list' < "$DB_DUMP" > /dev/null
echo "[backup] ダンプの目次を読めました（壊れていません）。"

if [ ! -s "$MEDIA_TAR" ]; then
    echo "[backup] 失敗: 画像のアーカイブが空です" >&2
    exit 1
fi
tar -tzf "$MEDIA_TAR" > /dev/null
echo "[backup] 画像アーカイブを読めました。"

echo "[backup] $KEEP_DAYS 日より古いバックアップを削除します..."
find "$BACKUP_DIR" -name 'db-*.dump' -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'media-*.tar.gz' -mtime "+$KEEP_DAYS" -delete

echo "[backup] 完了:"
ls -lh "$DB_DUMP" "$MEDIA_TAR"
