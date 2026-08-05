#!/usr/bin/env bash
# このサーバーへ、実際にどれだけログイン試行が来ているかを数える。
#
#   sudo ./audit-login-attempts.sh
#   sudo ./audit-login-attempts.sh --since "24 hours ago"
#   sudo ./audit-login-attempts.sh --quiet         件数だけ
#
# 「対策しないと危ない」と言われても実感が湧かない。
# 自分のサーバーの数字を見るのが早い。
#
# 何も設定していないサーバーでも、公開して数十分で試行が始まる。
# 攻撃者は IPv4 の全空間を常に走査していて、
# 「見つかってから狙われる」のではなく「最初から全部見られている」。
set -euo pipefail

SINCE="24 hours ago"
QUIET=0

while [ $# -gt 0 ]; do
    case "$1" in
        --since) shift; SINCE="${1:-$SINCE}" ;;
        --quiet) QUIET=1 ;;
        --help|-h) sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'; exit 0 ;;
    esac
    shift
done

# ログの取り方は環境で違う。
#   journald があればそちらが確実（ローテーションを気にしなくてよい）
#   無ければ /var/log/auth.log（Debian系）か /var/log/secure（RHEL系）
read_log() {
    if command -v journalctl > /dev/null 2>&1 && journalctl -n1 > /dev/null 2>&1; then
        journalctl _COMM=sshd --since "$SINCE" --no-pager 2>/dev/null && return 0
    fi
    for path in /var/log/auth.log /var/log/secure; do
        [ -r "$path" ] && cat "$path" && return 0
    done
    echo "ログを読めませんでした（root で実行していますか）" >&2
    return 1
}

LOG="$(read_log || true)"

if [ -z "$LOG" ]; then
    echo "ログが空です。sshd が動いていないか、まだ記録が無い可能性があります。"
    exit 0
fi

invalid=$(printf '%s\n' "$LOG" | grep -c "Invalid user" || true)
failed=$(printf '%s\n' "$LOG" | grep -c "Failed password" || true)
accepted=$(printf '%s\n' "$LOG" | grep -c "Accepted " || true)

if [ "$QUIET" -eq 1 ]; then
    printf '  ログイン試行: 存在しない利用者=%s / パスワード失敗=%s / 成功=%s（%s以降）\n' \
        "$invalid" "$failed" "$accepted" "$SINCE"
    exit 0
fi

echo "=== $SINCE 以降のログイン試行 ==="
echo
printf '存在しない利用者への試行: %s 件\n' "$invalid"
printf 'パスワード認証の失敗　　: %s 件\n' "$failed"
printf 'ログイン成功　　　　　　: %s 件\n' "$accepted"
echo
echo "※ パスワード失敗が 0 件で、存在しない利用者への試行が多い場合、"
echo "   パスワード認証そのものが無効になっています（＝鍵認証のみ）。"
echo "   攻撃者はパスワードを試す段階まで到達できていません。"
echo

echo "--- 狙われている利用者名 上位10 ---"
printf '%s\n' "$LOG" \
    | grep "Invalid user" \
    | sed -n 's/.*Invalid user \([^ ]*\) .*/\1/p' \
    | sort | uniq -c | sort -rn | head -10
echo

echo "--- 送信元 上位10 ---"
printf '%s\n' "$LOG" \
    | grep "Invalid user" \
    | grep -oE 'from [0-9a-fA-F:.]+' \
    | awk '{print $2}' \
    | sort | uniq -c | sort -rn | head -10
echo

echo "この一覧に自分が作ろうとしている利用者名が入っていないか確かめてください。"
echo "admin / ubuntu / user / test は、ほぼ必ず狙われます。"
