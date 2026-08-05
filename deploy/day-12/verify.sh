#!/usr/bin/env bash
# harden-ssh.sh を、実際に sshd を動かして確かめる。
#
#   ./deploy/day-12/verify.sh
#
# 11日目の検証はファイルの中身を見るだけでした。
# 今日は**実際に SSH でログインできるか**まで見ます。
# 「入れることを確かめる」がこの日の主題なので、
# 検証もそこを確かめないと意味がありません。
#
# コンテナの中で sshd を起動し、127.0.0.1 へ自分でログインします。
#
#   確かめられること:
#     * 改行コードが LF か（CRLF だと以降の失敗が全部これのせいになる）
#     * 鍵ログインの記録が無いとき、実行を拒否するか
#     * 鍵ログインの記録があるとき、実行するか
#     * 反映後に鍵で入れるか
#     * 反映後に root で入れないか
#     * 反映後にパスワードで入れないか
#     * 壊れた設定を書いたとき、反映せずに巻き戻すか
#
#   確かめられないこと:
#     * systemd の timer による自動ロールバック（systemd が無いため）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if command -v cygpath > /dev/null 2>&1; then
    MOUNT_SRC="$(cygpath -w "$REPO_ROOT")"
    export MSYS_NO_PATHCONV=1
else
    MOUNT_SRC="$REPO_ROOT"
fi

IMAGES=(
    "ubuntu:ubuntu:24.04"
    "rhel:oraclelinux:9"
    "alma:almalinux:9"
)

pass=0
fail=0

read -r -d '' SCRIPT <<'INNER' || true
set -e

# --- 0. 改行コード --------------------------------------------------------
# ここが CRLF だと、以降の失敗が全部これのせいになる。
#
# 検査に awk を使うのは、シェルの引用に頼らずに済むため。
# 最初は grep のパターンで書いたが、そのパターン自身へ CR が実体で
# 紛れ込み、CRLF でないファイルを CRLF と誤検知した。
# 検査する対象と同じ落とし穴を、検査自身が踏んだ形になる。
echo "--- 0. 改行コード ---"
for f in /work/deploy/lib/common.sh /work/deploy/day-11/bootstrap.sh \
         /work/deploy/day-12/harden-ssh.sh /work/deploy/day-12/verify-login.sh; do
    if awk '/\r/ { found = 1 } END { exit !found }' "$f"; then
        echo "NG: $f が CRLF です"; exit 1
    fi
done
echo "すべて LF です"

# --- 準備 ---------------------------------------------------------------
if command -v apt-get > /dev/null 2>&1; then
    apt-get update -qq > /dev/null 2>&1
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        sudo passwd openssh-server openssh-client > /dev/null 2>&1
else
    dnf install -y -q sudo shadow-utils passwd openssh-server openssh-clients > /dev/null 2>&1
fi
SSHD=/usr/sbin/sshd

# systemctl の代わり。reload は sshd へ HUP を送る（実機と同じ効果）。
mkdir -p /usr/local/sbin
cat > /usr/local/sbin/systemctl <<'FAKE'
#!/bin/sh
echo "[fake systemctl] $*" >> /tmp/systemctl.log
case "$1" in
  reload) [ -f /run/sshd.pid ] && kill -HUP "$(cat /run/sshd.pid)" 2>/dev/null || true ;;
esac
exit 0
FAKE
chmod +x /usr/local/sbin/systemctl
export PATH=/usr/local/sbin:$PATH

ssh-keygen -A > /dev/null 2>&1
mkdir -p /run/sshd /etc/ssh/sshd_config.d

grep -qE '^\s*Include\s+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config \
  || sed -i '1i Include /etc/ssh/sshd_config.d/*.conf' /etc/ssh/sshd_config

# 検証中はパスワード認証を有効にしておく（それが止まることを後で確かめる）。
#
# UsePAM は既定(yes)のまま触らない。
# ★no にすると、パスワードをロックした利用者は鍵でも入れなくなる。
#   sshd が PAM を通さず自分で shadow を見て「ロック中」と判断するため。
#   実機の既定は yes なので、検証も yes で行う。
#   （no にして "User deploy not allowed because account is locked" を
#     出したのが、この検証を書いたときの最初のつまずきだった）
cat > /etc/ssh/sshd_config.d/00-verify-base.conf <<'BASE'
PasswordAuthentication yes
PermitRootLogin yes
BASE

# 11日目の初期設定を流す
mkdir -p /root/.ssh
ssh-keygen -q -t ed25519 -N '' -f /root/.ssh/id_ed25519
cp /root/.ssh/id_ed25519.pub /root/.ssh/authorized_keys
chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys
/work/deploy/day-11/bootstrap.sh --user deploy > /tmp/bootstrap.log 2>&1

# root にもパスワードを付けておく（パスワード認証が止まることの確認用）
echo 'root:verify-only-password-1234' | chpasswd

# sshd の記録は /tmp/sshd.log へ出る（コンテナには journald も rsyslog も無い）。
# 実機では journald か /var/log/auth.log を見る。
$SSHD -D -e > /tmp/sshd.log 2>&1 &
sleep 2

SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -i /root/.ssh/id_ed25519"
LOGOPT="--log-file /tmp/sshd.log"

# --- 1. 鍵ログインの記録が無い状態では拒否すること -----------------------
echo "--- 1. 未確認では拒否 ---"
if /work/deploy/day-12/harden-ssh.sh --user deploy $LOGOPT > /tmp/refuse.log 2>&1; then
    echo "NG: 確認が取れていないのに実行された"; cat /tmp/refuse.log; exit 1
fi
grep -q "設定を変更せずに終了" /tmp/refuse.log \
    || { echo "NG: 拒否の理由が違う"; cat /tmp/refuse.log; exit 1; }
test ! -e /etc/ssh/sshd_config.d/50-kururucms-hardening.conf \
    || { echo "NG: 拒否したのに設定を書いた"; exit 1; }
echo "拒否しました（設定は書かれていません）"

# --- 2. 実際に鍵でログインする -------------------------------------------
echo "--- 2. 鍵でログインする ---"
$SSH deploy@127.0.0.1 true || { echo "NG: 鍵ログインできない"; tail -20 /tmp/sshd.log; exit 1; }
echo "ログインできました"

/work/deploy/day-12/verify-login.sh --user deploy $LOGOPT > /tmp/verify.log 2>&1 \
    || { echo "NG: 記録を見つけられない"; cat /tmp/verify.log; exit 1; }
grep -q "鍵でログインした記録があります" /tmp/verify.log || { cat /tmp/verify.log; exit 1; }
echo "記録を確認しました"

# --- 3. 「判断できない」を「入れていない」と混同しないこと ----------------
echo "--- 3. ログが空のとき ---"
: > /tmp/empty.log
set +e
/work/deploy/day-12/verify-login.sh --user deploy --log-file /tmp/empty.log > /tmp/unknown.log 2>&1
unknown_status=$?
set -e
test "$unknown_status" -eq 2 || { echo "NG: 空ログの終了コードが $unknown_status（2のはず）"; cat /tmp/unknown.log; exit 1; }
grep -q "判断を保留" /tmp/unknown.log || { echo "NG: 保留と言っていない"; cat /tmp/unknown.log; exit 1; }
echo "空ログは「判断できない」として扱われました"

# --- 4. dry-run が何も変えないこと ---------------------------------------
echo "--- 4. dry-run ---"
/work/deploy/day-12/harden-ssh.sh --user deploy $LOGOPT --dry-run > /tmp/dry.log 2>&1
grep -q "何も変更しません" /tmp/dry.log || { echo "NG: dry-run と認識されていない"; exit 1; }
test ! -e /etc/ssh/sshd_config.d/50-kururucms-hardening.conf \
    || { echo "NG: dry-run が設定を書いた"; exit 1; }
echo "dry-run は何も変更しませんでした"

# --- 5. 実行 --------------------------------------------------------------
echo "--- 5. 実行 ---"
/work/deploy/day-12/harden-ssh.sh --user deploy $LOGOPT > /tmp/harden.log 2>&1 \
    || { cat /tmp/harden.log; exit 1; }
test -f /etc/ssh/sshd_config.d/50-kururucms-hardening.conf || { echo "NG: 設定が無い"; exit 1; }
test "$(stat -c %a /etc/ssh/sshd_config.d/50-kururucms-hardening.conf)" = "600" \
    || { echo "NG: 設定の権限が 600 でない"; exit 1; }
sleep 1

# --- 6. 反映後の挙動 ------------------------------------------------------
echo "--- 6. 反映後 ---"
$SSH deploy@127.0.0.1 true || { echo "NG: 反映後に deploy で入れない"; tail -20 /tmp/sshd.log; exit 1; }
echo "deploy: 鍵で入れる（正しい）"

if $SSH root@127.0.0.1 true 2>/dev/null; then
    echo "NG: root で入れてしまう"; exit 1
fi
echo "root: 入れない（正しい）"

if ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
       -o PreferredAuthentications=password -o PubkeyAuthentication=no \
       -o BatchMode=yes root@127.0.0.1 true 2>/dev/null; then
    echo "NG: パスワードで入れてしまう"; exit 1
fi
echo "パスワード: 入れない（正しい）"

# --- 7. 冪等性 ------------------------------------------------------------
echo "--- 7. 2回目 ---"
/work/deploy/day-12/harden-ssh.sh --user deploy $LOGOPT > /tmp/harden2.log 2>&1
grep -q "変更なし" /tmp/harden2.log || { echo "NG: 2回目も書き換えている"; exit 1; }
backups=$(ls -1 /etc/ssh/sshd_config.d/*.bak-* 2>/dev/null | wc -l)
test "$backups" -eq 0 || { echo "NG: 2回目で控えが $backups 件できた"; exit 1; }
echo "2回目は書き換えませんでした"

# --- 8. 壊れた設定は反映せず、直前の設定へ戻すこと ------------------------
echo "--- 8. 壊れた設定 ---"
# ツリーごと複製する。1ファイルだけ /tmp へ写すと
# ../lib/common.sh を読めなくなり、検査したい所まで到達しない。
cp -r /work/deploy /tmp/deploy-broken
sed -i 's/^MaxAuthTries 3$/ThisDirectiveDoesNotExist yes/' /tmp/deploy-broken/day-12/harden-ssh.sh

if /tmp/deploy-broken/day-12/harden-ssh.sh --user deploy $LOGOPT > /tmp/broken.log 2>&1; then
    echo "NG: 壊れた設定が通ってしまった"; cat /tmp/broken.log; exit 1
fi
grep -q "直前の設定へ戻しました" /tmp/broken.log \
    || { echo "NG: 直前の設定へ戻していない"; cat /tmp/broken.log; exit 1; }

# ★重要★ 戻したあと、鍵認証のみの設定が生きていること。
# 「消すだけ」で済ませると、ここでパスワード認証が復活している。
grep -q "^PasswordAuthentication no" /etc/ssh/sshd_config.d/50-kururucms-hardening.conf \
    || { echo "NG: 戻した設定に PasswordAuthentication no が無い"; exit 1; }
grep -q "ThisDirectiveDoesNotExist" /etc/ssh/sshd_config.d/50-kururucms-hardening.conf \
    && { echo "NG: 壊れた内容が残っている"; exit 1; }

$SSH deploy@127.0.0.1 true || { echo "NG: 巻き戻した後に入れない"; exit 1; }
echo "壊れた設定は反映されず、直前の設定が復元されました"

echo "OK"
INNER

for entry in "${IMAGES[@]}"; do
    key="${entry%%:*}"
    image="${entry#*:}"

    echo
    echo "======================================================================"
    echo " $key ($image)"
    echo "======================================================================"

    if docker run --rm -v "$MOUNT_SRC:/work:ro" "$image" bash -c "$SCRIPT"; then
        echo "[$key] 成功"
        pass=$((pass + 1))
    else
        echo "[$key] 失敗"
        fail=$((fail + 1))
    fi
done

echo
echo "======================================================================"
echo " 成功 $pass / 失敗 $fail"
echo "======================================================================"
[ "$fail" -eq 0 ]
