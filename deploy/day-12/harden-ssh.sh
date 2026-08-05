#!/usr/bin/env bash
# SSH を鍵認証だけにし、root での直接ログインを止める。
#
#   sudo ./harden-ssh.sh --user deploy --dry-run
#   sudo ./harden-ssh.sh --user deploy
#   sudo ./harden-ssh.sh --user deploy --rollback-in 10   10分後に自動で元へ戻す
#
# ------------------------------------------------------------------------
# このスクリプトは、条件を満たさない限り実行を拒否します
# ------------------------------------------------------------------------
# 11日目に「入れることを確かめてから」と書きました。
# しかし文章で書いた注意は、急いでいるときに読み飛ばされます。
#
# そこで**確認できていなければ動かない**ようにしてあります。
# 具体的には、認証ログに
#     Accepted publickey for <利用者>
# が残っていることを確かめます。実際に鍵で入った記録です。
#
# 記録が無ければ、設定を1文字も書き換えずに終了します。
#
# ------------------------------------------------------------------------
# それでも残す退路
# ------------------------------------------------------------------------
#   1. 変更前の設定は .bak-... に残す
#   2. sshd -t で書式を検査してから反映する（壊れた設定を読ませない）
#   3. restart ではなく reload を使う（今つながっている接続を切らない）
#   4. --rollback-in N で、N分後に自動で元へ戻す予約を入れられる
#      入れたら、別の端末で入れることを確かめてから
#      ./harden-ssh.sh --confirm で予約を取り消す
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/../lib/common.sh"

TARGET_USER="deploy"
ROLLBACK_MIN=0
CONFIRM=0
ALLOW_UNVERIFIED=0
SSH_PORT=""
LOG_FILE=""

CONF_PATH="/etc/ssh/sshd_config.d/50-kururucms-hardening.conf"
ROLLBACK_UNIT="kururucms-ssh-rollback"

while [ $# -gt 0 ]; do
    case "$1" in
        --user)        shift; TARGET_USER="${1:?--user には利用者名が必要です}" ;;
        --user=*)      TARGET_USER="${1#*=}" ;;
        --rollback-in) shift; ROLLBACK_MIN="${1:?--rollback-in には分数が必要です}" ;;
        --port)        shift; SSH_PORT="${1:?--port には番号が必要です}" ;;
        --log-file)    shift; LOG_FILE="${1:?--log-file にはパスが必要です}" ;;
        --confirm)     CONFIRM=1 ;;
        --dry-run)     DRY_RUN=1 ;;
        # 認証ログが消えている等、どうしても確認できない場合の逃げ道。
        # 使うときは、必ず別の端末でログインしたまま実行すること。
        --allow-unverified) ALLOW_UNVERIFIED=1 ;;
        --help|-h) sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'; exit 0 ;;
        *) die "知らない引数です: $1" ;;
    esac
    shift
done

require_root
detect_os

# ---------------------------------------------------------------------------
# --confirm: 自動ロールバックの予約を取り消す
# ---------------------------------------------------------------------------
if [ "$CONFIRM" -eq 1 ]; then
    if systemctl list-timers --all 2>/dev/null | grep -q "$ROLLBACK_UNIT"; then
        log "自動ロールバックの予約を取り消します..."
        run systemctl stop "${ROLLBACK_UNIT}.timer" 2>/dev/null || true
        log "取り消しました。この設定は今後も残ります。"
    else
        log "取り消す予約はありませんでした。"
    fi
    exit 0
fi

[ "$DRY_RUN" -eq 1 ] && log "--dry-run: 何も変更しません。"

log "OS: $OS_NAME"
log "鍵認証だけにする利用者: $TARGET_USER"

# ---------------------------------------------------------------------------
# 関所: 実際に鍵で入れたことを確かめる
# ---------------------------------------------------------------------------
log ""
log "=== 実行前の確認 ==="

if ! id -u "$TARGET_USER" > /dev/null 2>&1; then
    die "利用者 $TARGET_USER がいません。先に11日目の bootstrap.sh を実行してください。"
fi

KEYS="$(getent passwd "$TARGET_USER" | cut -d: -f6)/.ssh/authorized_keys"
if [ ! -s "$KEYS" ]; then
    die "$KEYS が空か存在しません。鍵を登録してください。"
fi
log "認証鍵ファイル: $KEYS（$(grep -c . "$KEYS") 件）"

VERIFY_ARGS=(--user "$TARGET_USER")
[ -n "$LOG_FILE" ] && VERIFY_ARGS+=(--log-file "$LOG_FILE")

set +e
"$SCRIPT_DIR/verify-login.sh" "${VERIFY_ARGS[@]}"
verify_status=$?
set -e

# 0 = 確認できた / 1 = 記録が無い / 2 = 判断できない
# 2 のときも進めない。「分からない」は「大丈夫」ではない。
if [ "$verify_status" -eq 0 ]; then
    :
elif [ "$ALLOW_UNVERIFIED" -eq 1 ]; then
    warn ""
    warn "--allow-unverified が指定されたため、確認できないまま続行します。"
    warn "**今つながっている接続を絶対に閉じないでください。**"
    warn "設定を間違えた場合、その接続だけが復旧経路になります。"
    warn ""
else
    log ""
    die "確認が取れないため、設定を変更せずに終了します。
     （どうしても進める場合は --allow-unverified を付けますが、
       その場合は別の端末でログインしたまま実行してください）"
fi

# ---------------------------------------------------------------------------
# sshd_config.d が読まれるか
# ---------------------------------------------------------------------------
# Ubuntu 24.04 と RHEL 9 系はどちらも sshd_config の先頭付近で
# Include /etc/ssh/sshd_config.d/*.conf を読む。
# ただし古い環境や、手で書き換えた環境では Include が無いことがある。
# その場合ファイルを置いても**何も起きない**ので、先に確かめる。
if ! grep -qE '^\s*Include\s+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config; then
    die "/etc/ssh/sshd_config に Include /etc/ssh/sshd_config.d/*.conf がありません。
     このままファイルを置いても読み込まれません。
     sshd_config の先頭へ Include 行を足すか、直接編集してください。"
fi
log "Include 行を確認しました。"

# ---------------------------------------------------------------------------
# 設定を書く
# ---------------------------------------------------------------------------
log ""
log "=== 設定 ==="

PORT_LINE=""
if [ -n "$SSH_PORT" ]; then
    PORT_LINE="Port $SSH_PORT"
fi

write_file "$CONF_PATH" 0600 <<EOF
# KururuCMS: SSH を鍵認証のみにする（12日目）
#
# このファイルは /etc/ssh/sshd_config.d/ に置かれ、
# sshd_config の Include から読み込まれる。
# 元の sshd_config は書き換えていない。

# root で直接ログインさせない。
# root は名前が決まっているので、利用者名を推測する手間が要らない。
# 作業は $TARGET_USER で入って sudo する。
PermitRootLogin no

# パスワード認証を止める。
# 総当たりは「いつか当たる」攻撃なので、時間をかければ成立する。
# 鍵なら現実的な時間では当たらない。
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no

# 鍵認証を明示的に有効にする。
PubkeyAuthentication yes

# ログインできる利用者を絞る。
# 新しい利用者が増えても、ここに書かない限り SSH では入れない。
AllowUsers $TARGET_USER

# 1接続あたりの認証試行回数。既定(6)より減らす。
MaxAuthTries 3

# 認証を終えるまでの猶予。既定(2m)は長い。
# 接続だけ張って放置する攻撃の枠を減らす。
LoginGraceTime 20

# 未認証のまま同時に張れる接続数。
# "10:30:60" = 10本を超えたら30%の確率で落とし、60本で全部落とす。
MaxStartups 10:30:60

# 使わない機能を止める。攻撃面はコード量に比例する。
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no

# 使っていない鍵の種類を無効にはしない（互換のため）。
# 代わりに、どの鍵で入ったかがログに残るよう詳細度を上げる。
LogLevel VERBOSE
$PORT_LINE
EOF

# ---------------------------------------------------------------------------
# 書式の検査（反映前）
# ---------------------------------------------------------------------------
# ★これを飛ばしてはいけない★
# 書式が不正なまま reload すると sshd が起動に失敗し、
# 以後 SSH で入れなくなる。検査してから反映する。
if [ "$DRY_RUN" -eq 0 ]; then
    log ""
    log "=== 反映前の検査 ==="
    if ! sshd -t 2>/tmp/sshd-test.err; then
        cat /tmp/sshd-test.err >&2

        # ★ここは「消す」では足りない★
        # write_file は上書き前に控えを取っている。
        # 新しいファイルを消すだけだと、**それまで効いていた設定まで消える**。
        # 前回の実行で鍵認証のみにしていた場合、
        # 誤った設定を弾いたつもりが、パスワード認証が復活した状態になる。
        # 直前の控えがあれば、それを戻す。
        previous="$(ls -1t "${CONF_PATH}".bak-* 2>/dev/null | head -1 || true)"
        if [ -n "$previous" ]; then
            mv -f "$previous" "$CONF_PATH"
            die "sshd の設定に誤りがあったため、直前の設定へ戻しました（$CONF_PATH）。"
        fi
        rm -f "$CONF_PATH"
        die "sshd の設定に誤りがあったため、書いたファイルを削除しました。"
    fi
    log "sshd -t: 問題なし"
fi

# ---------------------------------------------------------------------------
# 自動ロールバックの予約
# ---------------------------------------------------------------------------
# 反映して入れなくなった場合の最後の保険。
# 予約しておき、入れることを確かめたら --confirm で取り消す。
if [ "$ROLLBACK_MIN" -gt 0 ]; then
    log ""
    log "=== 自動ロールバックの予約（${ROLLBACK_MIN}分後）==="
    run systemd-run \
        --unit="$ROLLBACK_UNIT" \
        --on-active="${ROLLBACK_MIN}min" \
        --description="KururuCMS: SSH設定の自動巻き戻し" \
        /bin/sh -c "rm -f '$CONF_PATH' && systemctl reload sshd 2>/dev/null || systemctl reload ssh"
    log "  ${ROLLBACK_MIN}分後に $CONF_PATH を削除して sshd を reload します。"
    log "  別の端末で入れることを確かめたら、必ず次を実行してください:"
    log "      sudo $0 --confirm"
fi

# ---------------------------------------------------------------------------
# 反映
# ---------------------------------------------------------------------------
# restart ではなく reload。
# restart は今つながっている接続を切ります。設定を間違えていた場合、
# その接続が唯一の復旧経路だったのに、自分で切ることになります。
log ""
log "=== 反映 ==="
run systemctl reload sshd 2>/dev/null || run systemctl reload ssh

log ""
log "反映しました。**今の接続は閉じないでください。**"
log ""
log "別の端末で、次の3つを確かめてください:"
log "  1. $TARGET_USER で鍵ログインできる"
log "       ssh $TARGET_USER@<このサーバー>"
log "  2. root では入れない"
log "       ssh root@<このサーバー>        -> Permission denied になるのが正しい"
log "  3. パスワードでは入れない"
log "       ssh -o PreferredAuthentications=password $TARGET_USER@<このサーバー>"
log "                                       -> Permission denied になるのが正しい"
if [ "$ROLLBACK_MIN" -gt 0 ]; then
    log ""
    log "確かめたら、${ROLLBACK_MIN}分以内に予約を取り消してください:"
    log "    sudo $0 --confirm"
fi
