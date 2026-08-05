#!/usr/bin/env bash
# 「その利用者が、鍵で、実際にログインできたか」を認証ログから確かめる。
#
#   sudo ./verify-login.sh --user deploy
#
# 終了コード 0 = 確認できた / 1 = 記録が無い / 2 = 判断できない
#
# ------------------------------------------------------------------------
# なぜファイルの中身を見るだけでは駄目なのか
# ------------------------------------------------------------------------
# authorized_keys が存在し、権限も 600 で、中身も鍵の形をしている。
# それでもログインできないことがあります。実際の原因の例:
#
#   * 貼り付けた鍵が**公開鍵ではなく秘密鍵**だった
#   * 改行が混ざって1つの鍵が2行に割れていた
#   * ホームディレクトリの権限が緩く、sshd が .ssh ごと無視した
#   * SELinux のラベルが違って sshd から読めなかった（RHEL 系）
#   * 鍵は正しいが、手元の端末が別の鍵を送っていた
#
# どれも「ファイルは正しく見える」状態です。
# **実際に入れたという事実**だけが根拠になります。
#
# そこでこのスクリプトは、認証ログに
#   Accepted publickey for deploy ...
# が残っているかを見ます。これは「誰かが実際に鍵で入った」記録です。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/../lib/common.sh"

# 終了コードの意味
#   0 = 鍵ログインの記録があった
#   1 = 記録が無かった（＝まだ入れていない）
#   2 = **判断できなかった**（ログが読めない・空・sshd の記録が1行も無い）
#
# 1 と 2 を分けるのが重要。
# ログが空なだけなのに「入れていない」と言い切ると、
# 実際には入れている人の作業を止めてしまう。
# 逆に「読めなかったから大丈夫だろう」と通すと、締め出しを防げない。
# 分からないときは「分からない」と言う。
EXIT_FOUND=0
EXIT_NOT_FOUND=1
EXIT_UNKNOWN=2

TARGET_USER="deploy"
SINCE="7 days ago"
QUIET=0
LOG_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --user)     shift; TARGET_USER="${1:?--user には利用者名が必要です}" ;;
        --user=*)   TARGET_USER="${1#*=}" ;;
        --since)    shift; SINCE="${1:?--since には期間が必要です}" ;;
        # journald も /var/log/auth.log も使わず、別の場所へ記録している環境向け。
        --log-file) shift; LOG_FILE="${1:?--log-file にはパスが必要です}" ;;
        --quiet)    QUIET=1 ;;
        --help|-h) sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'; exit 0 ;;
        *) die "知らない引数です: $1" ;;
    esac
    shift
done

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }

LOG_SOURCE=""

read_auth_log() {
    if [ -n "$LOG_FILE" ]; then
        [ -r "$LOG_FILE" ] || return 1
        LOG_SOURCE="$LOG_FILE"
        cat "$LOG_FILE"
        return 0
    fi
    if command -v journalctl > /dev/null 2>&1 && journalctl -n1 > /dev/null 2>&1; then
        LOG_SOURCE="journald"
        journalctl _COMM=sshd --since "$SINCE" --no-pager 2>/dev/null && return 0
    fi
    for path in /var/log/auth.log /var/log/secure; do
        if [ -r "$path" ]; then
            LOG_SOURCE="$path"
            cat "$path"
            return 0
        fi
    done
    return 1
}

if ! LOG="$(read_auth_log)"; then
    say "⚠️ 認証ログを読めませんでした（root で実行していますか）。"
    say "   別の場所へ記録している場合は --log-file で指定してください。"
    exit "$EXIT_UNKNOWN"
fi

# ★ここを分けるのが要点★
# ログは読めたが sshd の記録が1行も無い、という状態がある。
#   * ログローテーションで直後に流れた
#   * sshd の記録先がここではない
#   * まだ一度も SSH 接続が来ていない
# これを「入れていない」と同じ扱いにすると、
# 実際には入れている人の作業を止めてしまう。
if ! printf '%s\n' "$LOG" | grep -qE 'sshd|Server listening|Accepted|Connection from'; then
    say "⚠️ 認証ログに sshd の記録が1行もありません（読んだ場所: $LOG_SOURCE）。"
    say ""
    say "   考えられること:"
    say "     * ログが直前にローテーションされた"
    say "     * sshd が別の場所へ記録している"
    say "     * まだ一度も SSH 接続が来ていない"
    say ""
    say "   「入れていない」とは断定できないため、判断を保留します。"
    say "   --log-file で記録先を指定するか、--since を延ばして再実行してください。"
    exit "$EXIT_UNKNOWN"
fi

# "Accepted publickey for deploy from 203.0.113.5 port 54321 ssh2: ED25519 SHA256:..."
matches="$(printf '%s\n' "$LOG" | grep -E "Accepted (publickey|hostbased) for ${TARGET_USER}( |$)" || true)"

if [ -z "$matches" ]; then
    say "❌ $TARGET_USER が鍵でログインした記録が、$SINCE 以降にありません。"
    say ""
    # パスワードで入れているなら、鍵の設定がまだ効いていないということ。
    password_logins="$(printf '%s\n' "$LOG" | grep -cE "Accepted password for ${TARGET_USER}( |$)" || true)"
    if [ "${password_logins:-0}" -gt 0 ]; then
        say "   ただし**パスワード**でのログインは $password_logins 件あります。"
        say "   鍵がまだ効いていません。この状態でパスワード認証を止めると、"
        say "   $TARGET_USER では入れなくなります。"
        say ""
    fi
    say "   先に手元の端末から次を実行し、パスワードを聞かれずに入れることを"
    say "   確かめてください。"
    say ""
    say "       ssh -o PreferredAuthentications=publickey $TARGET_USER@<このサーバー>"
    say ""
    say "   入れたら、このスクリプトをもう一度実行してください。"
    exit "$EXIT_NOT_FOUND"
fi

count="$(printf '%s\n' "$matches" | grep -c . || true)"
last_line="$(printf '%s\n' "$matches" | tail -1)"

say "✅ $TARGET_USER が鍵でログインした記録があります（$SINCE 以降 $count 件）。"
say ""
say "   最後の記録:"
say "     $last_line"
say ""

# 使われた鍵の種類も出す。RSA の古い鍵が使われていることに気づく機会になる。
key_types="$(printf '%s\n' "$matches" | grep -oE 'ssh2: [A-Z0-9-]+' | awk '{print $2}' | sort | uniq -c || true)"
if [ -n "$key_types" ]; then
    say "   使われた鍵の種類:"
    printf '%s\n' "$key_types" | sed 's/^/     /'
fi

exit "$EXIT_FOUND"
