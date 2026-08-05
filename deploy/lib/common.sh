#!/usr/bin/env bash
# デプロイ編のスクリプトが共通で使う道具。
#
#   . "$(dirname "$0")/../lib/common.sh"
#
# ここに置くのは「どの日でも要るもの」だけにする。
# 便利そうだからと詰め込むと、1日目の記事で説明できない関数が増えていく。

# エラーで止める。未定義変数も止める。パイプの途中の失敗も見逃さない。
#
# set -e だけでは足りない。
#   set -u  … 打ち間違えた変数名が空文字として通ってしまうのを防ぐ
#             （rm -rf "$PREFIX/" の PREFIX が空だと / を消しに行く）
#   set -o pipefail … a | b で a が失敗しても b が成功すれば成功になるのを防ぐ
set -euo pipefail

DRY_RUN=0

log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '[%s] 注意: %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die()  { printf '[%s] 中止: %s\n' "$(date +%H:%M:%S)" "$*" >&2; exit 1; }

# --dry-run のときは実行せず、何をするつもりかだけ出す。
run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '  [dry-run] %s\n' "$*"
        return 0
    fi
    "$@"
}

require_root() {
    [ "$(id -u)" -eq 0 ] || die "root で実行してください（sudo を付ける）"
}

# ---------------------------------------------------------------------------
# OS の判定
# ---------------------------------------------------------------------------
# /etc/os-release は systemd 以降のほぼ全ディストリビューションにある。
# `uname` では Ubuntu と Debian の区別が付かないので使わない。
detect_os() {
    [ -r /etc/os-release ] || die "/etc/os-release が読めません。対応していない環境です。"
    # shellcheck disable=SC1091
    . /etc/os-release

    OS_ID="${ID:-unknown}"
    OS_VERSION="${VERSION_ID:-unknown}"
    OS_NAME="${PRETTY_NAME:-$OS_ID $OS_VERSION}"

    # ID_LIKE は「どの系統か」。AlmaLinux なら "rhel centos fedora" が入る。
    # 個々のディストリビューション名で分岐すると、
    # Rocky や Miracle Linux が出るたびに条件が増えていく。
    case " ${ID_LIKE:-$OS_ID} $OS_ID " in
        *" debian "*|*" ubuntu "*) OS_FAMILY="debian" ;;
        *" rhel "*|*" fedora "*)   OS_FAMILY="rhel" ;;
        *) die "対応していない OS です: $OS_NAME" ;;
    esac

    case "$OS_FAMILY" in
        debian) PKG="apt-get"; FIREWALL="ufw" ;;
        rhel)   PKG="dnf";     FIREWALL="firewalld" ;;
    esac
}

pkg_update() {
    case "$OS_FAMILY" in
        debian) run env DEBIAN_FRONTEND=noninteractive "$PKG" update -qq ;;
        rhel)   run "$PKG" -q makecache ;;
    esac
}

# 入っていないパッケージだけ入れる。
# 毎回 install を呼んでも害は無いが、
# 「今回このスクリプトが何を変えたか」がログから読めなくなる。
pkg_install() {
    local missing=()
    for name in "$@"; do
        if ! pkg_installed "$name"; then
            missing+=("$name")
        fi
    done
    if [ ${#missing[@]} -eq 0 ]; then
        log "  すべて導入済み: $*"
        return 0
    fi
    log "  導入します: ${missing[*]}"
    case "$OS_FAMILY" in
        debian) run env DEBIAN_FRONTEND=noninteractive "$PKG" install -y -qq "${missing[@]}" ;;
        rhel)   run "$PKG" install -y -q "${missing[@]}" ;;
    esac
}

# 「そのコマンドが使えればよい」ものは、パッケージ名ではなくコマンドで判定する。
#
#   ensure_command curl curl
#
# パッケージ名で判定すると、別のパッケージが同じコマンドを提供している環境で
# 二重に入れようとして失敗する。実例:
#   AlmaLinux 9 / Rocky Linux 9 の最小構成には curl-minimal が入っていて、
#   そこへ curl を入れようとすると conflicts で止まる。
#   （Oracle Linux 9 には curl が入っているので、同じ RHEL 系でも挙動が違う）
ensure_command() {
    local cmd="$1"
    shift
    if command -v "$cmd" > /dev/null 2>&1; then
        log "  導入済み: $cmd ($(command -v "$cmd"))"
        return 0
    fi
    pkg_install "$@"
}

pkg_installed() {
    case "$OS_FAMILY" in
        debian) dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "^install ok installed$" ;;
        rhel)   rpm -q "$1" > /dev/null 2>&1 ;;
    esac
}

# ---------------------------------------------------------------------------
# ファイルの書き換え
# ---------------------------------------------------------------------------
# 上書きする前に控えを取る。
# 「戻せばいいや」と思っていた設定を、戻せなくなってから気づく。
backup_file() {
    local path="$1"
    [ -f "$path" ] || return 0
    local backup="${path}.bak-$(date +%Y%m%d-%H%M%S)"
    log "  控え: $backup"
    run cp -a "$path" "$backup"
}

# 内容が既に同じなら何もしない。
# 何度実行しても控えが増え続けるのを防ぐ。
write_file() {
    local path="$1" mode="${2:-0644}"
    local content
    content="$(cat)"

    if [ -f "$path" ] && [ "$(cat "$path")" = "$content" ]; then
        log "  変更なし: $path"
        return 0
    fi

    backup_file "$path"
    log "  書き込み: $path"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '  [dry-run] %s へ %d バイト書き込み\n' "$path" "${#content}"
        return 0
    fi
    install -D -m "$mode" /dev/null "$path"
    printf '%s\n' "$content" > "$path"
}

parse_common_args() {
    for arg in "$@"; do
        case "$arg" in
            --dry-run) DRY_RUN=1 ;;
            --help|-h)
                sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
                exit 0
                ;;
        esac
    done
    if [ "$DRY_RUN" -eq 1 ]; then
        log "--dry-run: 何も変更しません。"
    fi
}
