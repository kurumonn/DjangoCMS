#!/usr/bin/env bash
# 借りたばかりのサーバーに最初に行う設定。
#
#   sudo ./bootstrap.sh --dry-run          何をするか見るだけ
#   sudo ./bootstrap.sh --user deploy      実行する
#
# やること:
#   1. パッケージを最新にする
#   2. 作業用ユーザーを作り、sudo を使えるようにする
#   3. 自分のSSH公開鍵をその利用者へ引き継ぐ
#   4. セキュリティ更新の自動適用を有効にする
#   5. 時刻同期を有効にする
#   6. sudo の操作をログに残す
#
# やらないこと（この時点ではまだ危険なため）:
#   * SSH のパスワード認証を切る     -> 12日目。鍵で入れることを確かめてから
#   * ファイアウォールを有効にする   -> 13日目。閉じ方を間違えると入れなくなる
#
# 「入れなくなる変更」は、入れることを確かめてからにする。順序に意味がある。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/../lib/common.sh"

NEW_USER="deploy"

# 引数の解釈は1か所で終わらせる。
#
# ★ここで一度間違えた★
# 最初は「--user だけ自前のループで拾い、残りを parse_common_args へ渡す」
# と書いた。しかしループの中で shift しているので、
# parse_common_args に届く時点で $@ は空になっていた。
# その結果 --dry-run が無視され、**何も変更しないはずの実行が
# 実際にパッケージを入れていた**。
# 安全のための仕組みが黙って効かなくなるのが、いちばん危ない壊れ方。
while [ $# -gt 0 ]; do
    case "$1" in
        --user)    shift; NEW_USER="${1:?--user には利用者名が必要です}" ;;
        --user=*)  NEW_USER="${1#*=}" ;;
        --dry-run) DRY_RUN=1 ;;
        --help|-h) sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'; exit 0 ;;
        *) die "知らない引数です: $1" ;;
    esac
    shift
done

if [ "$DRY_RUN" -eq 1 ]; then
    log "--dry-run: 何も変更しません。"
fi
require_root
detect_os

log "OS: $OS_NAME (family=$OS_FAMILY)"
log "作業用ユーザー: $NEW_USER"

# ---------------------------------------------------------------------------
# 0. 先に「今どれだけ狙われているか」を数える
# ---------------------------------------------------------------------------
# 対策の前に現状を見る。数字を見ないと、後で何が減ったのか分からない。
if [ -x "$SCRIPT_DIR/audit-login-attempts.sh" ]; then
    log "現在のログイン試行を数えます..."
    "$SCRIPT_DIR/audit-login-attempts.sh" --quiet || true
fi

# ---------------------------------------------------------------------------
# 1. パッケージの更新
# ---------------------------------------------------------------------------
log "パッケージ一覧を更新します..."
pkg_update

log "基本的な道具を入れます..."
case "$OS_FAMILY" in
    debian) pkg_install sudo ca-certificates unattended-upgrades chrony ;;
    rhel)   pkg_install sudo ca-certificates dnf-automatic chrony ;;
esac
# curl はパッケージ名ではなくコマンドで判定する。
# AlmaLinux / Rocky Linux の最小構成には curl-minimal が入っていて、
# そこへ curl パッケージを入れようとすると conflicts で止まるため。
ensure_command curl curl

# ---------------------------------------------------------------------------
# 2. 作業用ユーザー
# ---------------------------------------------------------------------------
# root で日常作業をしない理由は3つ。
#   * 打ち間違いが致命傷になる（rm の対象を間違えても止まらない）
#   * 誰が何をしたかログに残らない（root は全員 root）
#   * 侵入されたときに、そこが最上位権限になる
if id -u "$NEW_USER" > /dev/null 2>&1; then
    log "ユーザー $NEW_USER は既にあります。"
else
    log "ユーザー $NEW_USER を作ります..."
    run useradd --create-home --shell /bin/bash "$NEW_USER"
    # パスワードは設定しない。設定しないと「パスワードでは入れない」状態になる。
    # ログインは鍵だけ、権限昇格は sudo だけ、という経路にする。
    run passwd --lock "$NEW_USER"
fi

# sudo を使えるグループはディストリビューションで名前が違う。
case "$OS_FAMILY" in
    debian) ADMIN_GROUP="sudo" ;;
    rhel)   ADMIN_GROUP="wheel" ;;
esac

if id -nG "$NEW_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$ADMIN_GROUP"; then
    log "$NEW_USER は既に $ADMIN_GROUP に入っています。"
else
    log "$NEW_USER を $ADMIN_GROUP へ追加します..."
    run usermod -aG "$ADMIN_GROUP" "$NEW_USER"
fi

# ---------------------------------------------------------------------------
# 3. SSH 公開鍵の引き継ぎ
# ---------------------------------------------------------------------------
# ★ここが最重要★
# これを飛ばすと、12日目に root ログインを止めた瞬間、
# 誰もサーバーへ入れなくなる。
ROOT_KEYS="/root/.ssh/authorized_keys"
USER_SSH="/home/$NEW_USER/.ssh"
USER_KEYS="$USER_SSH/authorized_keys"

if [ -s "$ROOT_KEYS" ]; then
    log "root の公開鍵を $NEW_USER へ引き継ぎます..."
    run install -d -m 0700 -o "$NEW_USER" -g "$NEW_USER" "$USER_SSH"
    if [ "$DRY_RUN" -eq 0 ]; then
        # 追記する。既にある鍵を消さない。
        # 重複した行は残しても害が無いので、sort -u で整えるだけにする。
        touch "$USER_KEYS"
        cat "$ROOT_KEYS" "$USER_KEYS" | grep -v '^\s*$' | sort -u > "$USER_KEYS.tmp"
        mv "$USER_KEYS.tmp" "$USER_KEYS"
        chown "$NEW_USER:$NEW_USER" "$USER_KEYS"
        chmod 0600 "$USER_KEYS"
    else
        printf '  [dry-run] %s を %s へ追記\n' "$ROOT_KEYS" "$USER_KEYS"
    fi
    KEY_COUNT="$(grep -c . "$USER_KEYS" 2>/dev/null || echo 0)"
    log "  $NEW_USER の鍵: $KEY_COUNT 件"
else
    warn "root に公開鍵がありません（$ROOT_KEYS）。"
    warn "このまま12日目で root ログインを止めると、サーバーへ入れなくなります。"
    warn "先に ssh-copy-id で鍵を登録してください。"
fi

# ---------------------------------------------------------------------------
# 4. セキュリティ更新の自動適用
# ---------------------------------------------------------------------------
# 自動で入れるのは**セキュリティ更新だけ**にする。
# 全部を自動更新にすると、動いているアプリの依存が勝手に上がって
# 深夜に落ちることがある。
#
# 自動再起動もしない。再起動が要る更新は通知だけ受けて、
# 自分のタイミングで行う。
log "セキュリティ更新の自動適用を設定します..."
case "$OS_FAMILY" in
    debian)
        write_file /etc/apt/apt.conf.d/51kururucms-unattended <<'EOF'
// KururuCMS: セキュリティ更新だけを自動で適用する。
// 全部を自動更新にすると、依存が勝手に上がってアプリが落ちることがある。
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
};

// 使わなくなった依存を掃除する。放っておくとディスクが埋まる。
Unattended-Upgrade::Remove-Unused-Dependencies "true";

// 自動で再起動しない。再起動が要ることだけ記録しておき、
// 停止させてよい時間帯に自分で行う。
Unattended-Upgrade::Automatic-Reboot "false";
EOF
        write_file /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
        run systemctl enable --now unattended-upgrades
        ;;
    rhel)
        write_file /etc/dnf/automatic.conf <<'EOF'
# KururuCMS: セキュリティ更新だけを自動で適用する。
[commands]
upgrade_type = security
random_sleep = 360
download_updates = yes
apply_updates = yes
# 再起動は自動でしない。再起動が要る更新は自分のタイミングで。
reboot = never

[emitters]
emit_via = stdio

[base]
debuglevel = 1
EOF
        run systemctl enable --now dnf-automatic.timer
        ;;
esac

# ---------------------------------------------------------------------------
# 5. 時刻同期
# ---------------------------------------------------------------------------
# ずれると困るものが多い。
#   * TLS 証明書の有効期限の判定
#   * TOTP（9日目で入れた認証アプリのコード。30秒ごとに変わる）
#   * ログの時刻（障害のとき、複数サーバーのログを突き合わせられなくなる）
log "時刻同期を有効にします..."
run systemctl enable --now chronyd 2>/dev/null \
    || run systemctl enable --now chrony 2>/dev/null \
    || warn "chrony の有効化に失敗しました。手動で確認してください。"

# ---------------------------------------------------------------------------
# 6. sudo の記録
# ---------------------------------------------------------------------------
# 誰がいつ何を実行したかを残す。
# 事故のとき「何をしたか」を思い出すのは本人でも難しい。
log "sudo の操作ログを設定します..."
write_file /etc/sudoers.d/10-kururucms-logging 0440 <<'EOF'
# KururuCMS: sudo で実行した内容を記録する。
Defaults log_input, log_output
Defaults iolog_dir=/var/log/sudo-io
# パスワードの入力猶予。既定(15分)より短くする。
Defaults timestamp_timeout=5
EOF

# sudoers を壊すと sudo が一切使えなくなる。必ず検査する。
if [ "$DRY_RUN" -eq 0 ]; then
    if ! visudo -c -f /etc/sudoers.d/10-kururucms-logging > /dev/null; then
        rm -f /etc/sudoers.d/10-kururucms-logging
        die "sudoers の書式が不正だったため取り消しました。"
    fi
    log "  sudoers の書式を確認しました。"
fi

# ---------------------------------------------------------------------------
# 終わりに
# ---------------------------------------------------------------------------
log ""
log "完了しました。次にやること:"
log "  1. **今の接続を閉じずに** 別の端末から次を試す"
log "       ssh $NEW_USER@<このサーバー>"
log "  2. 入れたら sudo が使えることを確かめる"
log "       sudo -v"
log "  3. どちらも確認できてから、12日目（SSHの制限）へ進む"
log ""
log "順序が大事です。入れることを確かめる前に root ログインを止めると、"
log "自分が締め出されます。"
