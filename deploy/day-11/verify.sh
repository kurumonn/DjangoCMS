#!/usr/bin/env bash
# bootstrap.sh が3つの環境で実際に動くことを確かめる。
#
#   ./deploy/day-11/verify.sh
#
# 実サーバーを3台借りずに検証するため、コンテナで流す。
#
# コンテナで確かめられること・確かめられないことを、はっきり分けておく。
#
#   確かめられる:
#     * OS の判定が正しいか
#     * パッケージ名がその環境に存在するか
#     * ユーザー・グループ・鍵の配置が意図どおりか
#     * sudoers の書式が壊れていないか
#     * 2回流しても結果が変わらないか（冪等）
#
#   確かめられない（systemd が動いていないため）:
#     * systemctl enable --now が実際にサービスを起動するか
#     * 自動更新が本当に走るか
#     * 時刻同期が効くか
#
# 後者は「コンテナでは確認できていない」と明記して、実機で見る。
# 検証できていないものを、できたことにしない。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Windows の Git Bash から実行したときの2つの対処。
#
#   1. cygpath: Docker へ渡すのは Windows 形式のパス。
#      /e/PycharmProjects/... のまま渡すとマウントされず、
#      コンテナの中で「そんなファイルはない」と言われる。
#   2. MSYS_NO_PATHCONV: -v "...:/work:ro" の /work まで
#      Windows のパスへ書き換えられるのを止める。
#
# Linux / macOS では cygpath が無いので、そのままのパスを使う。
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

for entry in "${IMAGES[@]}"; do
    key="${entry%%:*}"
    image="${entry#*:}"

    echo
    echo "======================================================================"
    echo " $key ($image)"
    echo "======================================================================"

    # systemd が無いので systemctl は失敗する。
    # そこを本題にしないため、ダミーの systemctl を置いて先へ進ませる。
    # ★これはコンテナ検証のための細工であって、実機の挙動ではない★
    script='
set -e
if command -v apt-get > /dev/null 2>&1; then
    apt-get update -qq > /dev/null 2>&1
    apt-get install -y -qq sudo passwd > /dev/null 2>&1
else
    dnf install -y -q sudo shadow-utils passwd > /dev/null 2>&1
fi

# systemctl の代わり。呼ばれたことだけ記録して成功を返す。
mkdir -p /usr/local/sbin
printf "#!/bin/sh\necho \"[fake systemctl] \$*\" >> /tmp/systemctl.log\nexit 0\n" > /usr/local/sbin/systemctl
chmod +x /usr/local/sbin/systemctl
export PATH=/usr/local/sbin:$PATH

# root の鍵があることにする（引き継ぎ処理を通すため）
mkdir -p /root/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIVERIFYONLYnotarealkey verify@example" > /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

echo "--- dry-run ---"
/work/deploy/day-11/bootstrap.sh --dry-run --user deploy > /tmp/dry.log 2>&1 || { cat /tmp/dry.log; exit 1; }
head -3 /tmp/dry.log

# ★dry-run が本当に何も変えていないかを確かめる★
# ここを見ていなかったせいで、--dry-run が無視されて
# 実際にパッケージが入っていたことに気づけなかった。
grep -q "何も変更しません" /tmp/dry.log || { echo "NG: dry-run と認識されていない"; exit 1; }
id deploy > /dev/null 2>&1 && { echo "NG: dry-run が利用者を作った"; exit 1; }
test ! -e /home/deploy || { echo "NG: dry-run がホームを作った"; exit 1; }
test ! -e /etc/sudoers.d/10-kururucms-logging || { echo "NG: dry-run が設定を書いた"; exit 1; }
test ! -e /tmp/systemctl.log || { echo "NG: dry-run が systemctl を呼んだ"; exit 1; }
echo "dry-run は何も変更しませんでした。"

echo "--- 1回目 ---"
/work/deploy/day-11/bootstrap.sh --user deploy > /tmp/run1.log 2>&1 || { cat /tmp/run1.log; exit 1; }
tail -3 /tmp/run1.log

echo "--- 検査 ---"
id deploy
getent group sudo wheel 2>/dev/null | grep deploy || true
test -f /home/deploy/.ssh/authorized_keys || { echo "NG: 鍵が引き継がれていない"; exit 1; }
test "$(stat -c %a /home/deploy/.ssh/authorized_keys)" = "600" || { echo "NG: 鍵の権限が 600 でない"; exit 1; }
test "$(stat -c %U /home/deploy/.ssh/authorized_keys)" = "deploy" || { echo "NG: 鍵の所有者が deploy でない"; exit 1; }
test "$(stat -c %a /home/deploy/.ssh)" = "700" || { echo "NG: .ssh の権限が 700 でない"; exit 1; }
grep -q VERIFYONLY /home/deploy/.ssh/authorized_keys || { echo "NG: 鍵の中身が違う"; exit 1; }
visudo -c -f /etc/sudoers.d/10-kururucms-logging
passwd -S deploy | grep -qE " L | LK " || { echo "NG: パスワードがロックされていない"; exit 1; }

echo "--- 2回目（冪等性）---"
/work/deploy/day-11/bootstrap.sh --user deploy > /tmp/run2.log 2>&1 || { cat /tmp/run2.log; exit 1; }
grep -c "変更なし" /tmp/run2.log
# 2回目に控えが増えていないこと。増えるなら毎回書き換えている。
backups=$(ls -1 /etc/sudoers.d/*.bak-* 2>/dev/null | wc -l)
test "$backups" -eq 0 || { echo "NG: 2回目で控えが $backups 件できた"; exit 1; }
# 鍵が二重に登録されていないこと。
lines=$(grep -c . /home/deploy/.ssh/authorized_keys)
test "$lines" -eq 1 || { echo "NG: 鍵が $lines 行に増えた"; exit 1; }

echo "--- systemctl は何を呼ばれたか（実機では実際に動く部分）---"
cat /tmp/systemctl.log
echo "OK"
'

    if docker run --rm -v "$MOUNT_SRC:/work:ro" "$image" bash -c "$script"; then
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
