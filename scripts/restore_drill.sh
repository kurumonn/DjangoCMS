#!/usr/bin/env bash
# 復元の訓練。**本番のデータベースには一切触らない。**
#
#   ./scripts/restore_drill.sh backups/db-20260805-090000.dump
#
# バックアップを、使い捨ての別データベースへ復元して中身を数える。
#
# なぜ訓練が要るか:
#   バックアップは「取れているか」ではなく「戻せるか」でしか価値が測れない。
#   そして戻せないと分かるのは、たいてい本当に必要になったときである。
#   月に一度これを流しておけば、その日に初めて気づくことがなくなる。
set -euo pipefail

DUMP="${1:?使い方: ./scripts/restore_drill.sh <ダンプファイル>}"
DRILL_DB="kururucms_restore_drill"

if [ ! -s "$DUMP" ]; then
    echo "[drill] ダンプが見つからないか空です: $DUMP" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

# 本番の DB 名と同じ名前を使っていないことを確かめる。
# ここを間違えると訓練が事故になる。
if [ "$DRILL_DB" = "$POSTGRES_DB" ]; then
    echo "[drill] 中止: 訓練用の名前が本番と同じです" >&2
    exit 1
fi

cleanup() {
    echo "[drill] 訓練用データベースを片付けます..."
    docker compose exec -T db \
        psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS $DRILL_DB;" > /dev/null
}
# 途中で失敗しても必ず片付ける。
# 残しておくと、次回「既にある」で失敗し、訓練そのものをやらなくなる。
trap cleanup EXIT

echo "[drill] 訓練用データベースを作ります: $DRILL_DB"
docker compose exec -T db \
    psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $DRILL_DB;" > /dev/null
docker compose exec -T db \
    psql -U "$POSTGRES_USER" -d postgres \
    -c "CREATE DATABASE $DRILL_DB;" > /dev/null

echo "[drill] 復元します..."
# ファイル名は渡さず、標準入力から読ませる（backup.sh と同じ理由）。
docker compose exec -T db \
    sh -c "pg_restore -U '$POSTGRES_USER' -d '$DRILL_DB' --no-owner" < "$DUMP"

echo "[drill] 復元した中身を数えます..."
docker compose exec -T db \
    psql -U "$POSTGRES_USER" -d "$DRILL_DB" -tA -c "
        SELECT 'articles=' || (SELECT count(*) FROM blog_article)
            || ' users='    || (SELECT count(*) FROM accounts_user)
            || ' comments=' || (SELECT count(*) FROM comments_comment)
            || ' media='    || (SELECT count(*) FROM media_library_mediaasset);
    "

echo "[drill] 現在の本番と比べます..."
docker compose exec -T db \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "
        SELECT 'articles=' || (SELECT count(*) FROM blog_article)
            || ' users='    || (SELECT count(*) FROM accounts_user)
            || ' comments=' || (SELECT count(*) FROM comments_comment)
            || ' media='    || (SELECT count(*) FROM media_library_mediaasset);
    "

echo
echo "[drill] 完了。上の2行を見比べてください。"
echo "        バックアップ以降に増えたぶんだけ差が出るのが正常です。"
echo "        差が大きすぎる／復元側が 0 なら、バックアップが壊れています。"
