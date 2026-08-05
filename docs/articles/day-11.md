# 【11日目】Linux サーバー初期設定――借りた直後にやること・やってはいけない順序

> 連載「10日で学ぶ Django 本番デプロイ」の1日目（通算11日目）です。
> 成果物: <https://github.com/kurumonn/DjangoCMS>（タグ `day-11`）

---

## 1. 今日の結論

ここから第2部です。10日目までは全部、自分の開発機の中の話でした。
今日からは**インターネットに繋がったサーバー**を扱います。

今日やることは5つです。

1. 作業用ユーザーを作り、root で日常作業をしないようにする
2. 自分の SSH 公開鍵を、その利用者へ引き継ぐ
3. セキュリティ更新だけを自動で適用する
4. 時刻同期を有効にする
5. sudo の操作をログに残す

**今日いちばん大事なのは、やらないことの方です。**

- SSH のパスワード認証を切る → **やらない**（12日目）
- ファイアウォールを有効にする → **やらない**（13日目）

どちらも「やった方が安全」な設定です。それでも今日はやりません。
**新しい入口が使えることを確かめる前に、古い入口を塞ぐと、
自分が締め出されるから**です。

VPS によってはコンソールから復旧できますが、できない契約もあります。
順序を守れば、そもそも復旧が要りません。

---

## 2. 今日の完成画面

画面ではなく、ターミナルの出力です。

```text
$ sudo ./deploy/day-11/bootstrap.sh --dry-run
[14:31:02] --dry-run: 何も変更しません。
[14:31:02] OS: Ubuntu 24.04.4 LTS (family=debian)
[14:31:02] 作業用ユーザー: deploy
[14:31:02] 現在のログイン試行を数えます...
  ログイン試行: 存在しない利用者=1330 / パスワード失敗=0 / 成功=3（24 hours ago以降）
```

**存在しない利用者への試行が、24時間で 1,330 件。**
これは実際に稼働しているサーバーの数字です。

---

## 3. 今日変更するファイル

Django のコードは1行も触りません。今日はサーバー側です。

| ファイル | 何をするか |
| --- | --- |
| `deploy/README.md` | デプロイ編の資材の説明 |
| `deploy/lib/common.sh` | OS 判定・冪等な書き込み・控えの保存 |
| `deploy/day-11/bootstrap.sh` | 初期設定の本体 |
| `deploy/day-11/audit-login-attempts.sh` | ログイン試行を数える |
| `deploy/day-11/verify.sh` | 3環境のコンテナで確かめる |

---

## 4. 完成コード

### 4.1 まず、狙われている量を数える

対策の話をする前に、自分のサーバーの数字を見ます。

<div class="env-block env-ubuntu">

**Ubuntu 24.04 LTS**

```bash
sudo journalctl _COMM=sshd --since "24 hours ago" --no-pager | grep -c "Invalid user"
```

</div>

<div class="env-block env-rhel env-alma">

**Oracle Linux / AlmaLinux / Rocky Linux**

```bash
sudo journalctl _COMM=sshd --since "24 hours ago" --no-pager | grep -c "Invalid user"
```

`journalctl` が使えない場合は、こちらを見ます。

```bash
sudo grep -c "Invalid user" /var/log/secure
```

</div>

`deploy/day-11/audit-login-attempts.sh` は、これをまとめて出します。

```bash
sudo ./deploy/day-11/audit-login-attempts.sh
```

このサイト（kurutann.com）を動かしているサーバーで実行した結果です。

```text
=== 24 hours ago 以降のログイン試行 ===

存在しない利用者への試行: 1330 件
パスワード認証の失敗　　: 0 件
ログイン成功　　　　　　: 3 件

--- 狙われている利用者名 上位10 ---
    387 admin
    198 ubuntu
     93 user
     70 test
     47 postgres
     42 debian
     41 dev
     38 ftpuser
     35 git
     32 oracle
```

**`admin` が 387 回、`ubuntu` が 198 回。**
これから作ろうとしている利用者名が、この一覧に入っていないか確かめてください。

もうひとつ見てほしいのが、**パスワード認証の失敗が 0 件**であることです。
1,330 回試されているのに、パスワードを試す段階にすら到達していません。
このサーバーはパスワード認証を無効にしているためです（12日目でやります）。

対策の効果が、数字で見えます。

### 4.2 共通部分

`deploy/lib/common.sh` から、要点だけ。

```bash
# エラーで止める。未定義変数も止める。パイプの途中の失敗も見逃さない。
#
# set -e だけでは足りない。
#   set -u  … 打ち間違えた変数名が空文字として通ってしまうのを防ぐ
#             （rm -rf "$PREFIX/" の PREFIX が空だと / を消しに行く）
#   set -o pipefail … a | b で a が失敗しても b が成功すれば成功になるのを防ぐ
set -euo pipefail
```

OS の判定は `/etc/os-release` を使います。

```bash
detect_os() {
    [ -r /etc/os-release ] || die "/etc/os-release が読めません。対応していない環境です。"
    . /etc/os-release

    OS_ID="${ID:-unknown}"
    OS_NAME="${PRETTY_NAME:-$OS_ID}"

    # ID_LIKE は「どの系統か」。AlmaLinux なら "rhel centos fedora" が入る。
    # 個々のディストリビューション名で分岐すると、
    # Rocky や Miracle Linux が出るたびに条件が増えていく。
    case " ${ID_LIKE:-$OS_ID} $OS_ID " in
        *" debian "*|*" ubuntu "*) OS_FAMILY="debian" ;;
        *" rhel "*|*" fedora "*)   OS_FAMILY="rhel" ;;
        *) die "対応していない OS です: $OS_NAME" ;;
    esac
}
```

`uname` を使わないのは、Ubuntu と Debian を区別できないためです。

パッケージの導入は「入っていないものだけ」にします。

```bash
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
    ...
}
```

毎回 `install` を呼んでも害はありませんが、
**今回このスクリプトが何を変えたのか**がログから読めなくなります。

ファイルの書き込みは、同じ内容なら何もしません。

```bash
write_file() {
    local path="$1" mode="${2:-0644}"
    local content
    content="$(cat)"

    if [ -f "$path" ] && [ "$(cat "$path")" = "$content" ]; then
        log "  変更なし: $path"
        return 0
    fi

    backup_file "$path"       # .bak-YYYYmmdd-HHMMSS を残す
    ...
}
```

これが無いと、実行するたびに控えファイルが増え続けます。

### 4.3 作業用ユーザー

```bash
if id -u "$NEW_USER" > /dev/null 2>&1; then
    log "ユーザー $NEW_USER は既にあります。"
else
    log "ユーザー $NEW_USER を作ります..."
    run useradd --create-home --shell /bin/bash "$NEW_USER"
    # パスワードは設定しない。設定しないと「パスワードでは入れない」状態になる。
    # ログインは鍵だけ、権限昇格は sudo だけ、という経路にする。
    run passwd --lock "$NEW_USER"
fi
```

sudo が使えるグループの名前は、系統で違います。

<div class="env-block env-ubuntu">

**Ubuntu 24.04 LTS**

グループ名は `sudo` です。

```bash
sudo usermod -aG sudo deploy
```

</div>

<div class="env-block env-rhel env-alma">

**Oracle Linux / AlmaLinux / Rocky Linux**

グループ名は `wheel` です。

```bash
sudo usermod -aG wheel deploy
```

</div>

スクリプトはこれを自動で振り分けます。

```bash
case "$OS_FAMILY" in
    debian) ADMIN_GROUP="sudo" ;;
    rhel)   ADMIN_GROUP="wheel" ;;
esac
```

### 4.4 公開鍵の引き継ぎ（今日いちばん重要）

```bash
if [ -s "$ROOT_KEYS" ]; then
    log "root の公開鍵を $NEW_USER へ引き継ぎます..."
    run install -d -m 0700 -o "$NEW_USER" -g "$NEW_USER" "$USER_SSH"
    # 追記する。既にある鍵を消さない。
    touch "$USER_KEYS"
    cat "$ROOT_KEYS" "$USER_KEYS" | grep -v '^\s*$' | sort -u > "$USER_KEYS.tmp"
    mv "$USER_KEYS.tmp" "$USER_KEYS"
    chown "$NEW_USER:$NEW_USER" "$USER_KEYS"
    chmod 0600 "$USER_KEYS"
else
    warn "root に公開鍵がありません（$ROOT_KEYS）。"
    warn "このまま12日目で root ログインを止めると、サーバーへ入れなくなります。"
    warn "先に ssh-copy-id で鍵を登録してください。"
fi
```

`sort -u` で追記しているのは、
**何度実行しても鍵が二重に登録されない**ようにするためです。

権限は `.ssh` が `700`、`authorized_keys` が `600`。
ここが緩いと、SSH は鍵を**無視します**（エラーではなく黙って無視するので気づきにくい）。

### 4.5 セキュリティ更新の自動適用

<div class="env-block env-ubuntu">

**Ubuntu 24.04 LTS** — `unattended-upgrades`

```bash
sudo apt-get install -y unattended-upgrades
```

`/etc/apt/apt.conf.d/51kururucms-unattended`:

```text
// セキュリティ更新だけを自動で適用する。
// 全部を自動更新にすると、依存が勝手に上がってアプリが落ちることがある。
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
};

Unattended-Upgrade::Remove-Unused-Dependencies "true";

// 自動で再起動しない。再起動が要ることだけ記録しておき、
// 停止させてよい時間帯に自分で行う。
Unattended-Upgrade::Automatic-Reboot "false";
```

```bash
sudo systemctl enable --now unattended-upgrades
```

</div>

<div class="env-block env-rhel env-alma">

**Oracle Linux / AlmaLinux / Rocky Linux** — `dnf-automatic`

```bash
sudo dnf install -y dnf-automatic
```

`/etc/dnf/automatic.conf`:

```ini
[commands]
upgrade_type = security
random_sleep = 360
download_updates = yes
apply_updates = yes
# 再起動は自動でしない。再起動が要る更新は自分のタイミングで。
reboot = never
```

```bash
sudo systemctl enable --now dnf-automatic.timer
```

`random_sleep` は、同じ時刻に一斉にアクセスしないための待ち時間です。

</div>

どちらも共通しているのは次の2点です。

- **セキュリティ更新だけ**を自動にする
- **自動で再起動しない**

全部を自動更新にすると、動いているアプリの依存が勝手に上がって
深夜に落ちることがあります。再起動も同じで、
「気づいたら再起動されていた」は事故として扱われます。

### 4.6 sudo の操作ログ

`/etc/sudoers.d/10-kururucms-logging`:

```text
Defaults log_input, log_output
Defaults iolog_dir=/var/log/sudo-io
# パスワードの入力猶予。既定(15分)より短くする。
Defaults timestamp_timeout=5
```

**書式を間違えると sudo が一切使えなくなります。** 必ず検査します。

```bash
if ! visudo -c -f /etc/sudoers.d/10-kururucms-logging > /dev/null; then
    rm -f /etc/sudoers.d/10-kururucms-logging
    die "sudoers の書式が不正だったため取り消しました。"
fi
```

自分で書いたファイルを、自分で検査して、駄目なら自分で消します。
`sudo` が壊れた状態は、`sudo` では直せません。

---

## 5. コードの意味

| 書き方 | 意味 |
| --- | --- |
| `set -euo pipefail` | 失敗・未定義変数・パイプ途中の失敗で止める |
| `id -u "$USER"` | その利用者が存在するか（存在すれば UID を返す） |
| `useradd --create-home` | ホームディレクトリも作る |
| `passwd --lock` | パスワードでのログインを不可にする |
| `usermod -aG グループ` | **追加**する（`-a` を忘れると他のグループから外れる） |
| `install -d -m 0700 -o u -g g` | ディレクトリを権限と所有者ごと作る |
| `sort -u` | 重複を除く（鍵の二重登録を防ぐ） |
| `visudo -c -f ファイル` | sudoers の書式検査（適用はしない） |
| `${ID_LIKE:-$OS_ID}` | `ID_LIKE` が無ければ `ID` を使う |

`usermod -aG` の `-a` は特に危険です。付け忘れると、
**指定しなかったグループから全部外れます**。

---

## 6. 内部で起きていること

### なぜ「見つかってから狙われる」のではないのか

サーバーを借りて、まだ誰にも URL を教えていないのに、
数十分で試行が始まります。

理由は単純で、**攻撃者は IPv4 の全アドレスを常に走査している**からです。
IPv4 は約 43 億個しかなく、1台のサーバーから全空間を走査するのに
それほど時間はかかりません。

つまり「見つからないようにする」戦略は成立しません。
**見つかっている前提**で、入れないようにします。

`admin` `ubuntu` `user` `test` `postgres` が狙われるのも同じ理屈です。
どこかのサーバーにありそうな名前を順に試しているだけで、
こちらのサーバーを個別に調べたわけではありません。

### なぜ root で作業しないのか

3つあります。

**1. 打ち間違いが致命傷になる**

一般利用者なら「権限がありません」で止まる操作が、root では実行されます。

**2. 誰が何をしたか分からなくなる**

root は全員 root です。複数人で運用していると、
ログを見ても誰の操作か特定できません。

**3. 侵入されたときの被害が違う**

一般利用者として侵入されれば、そこから権限昇格が必要です。
root として侵入されれば、その時点で終わりです。

### 順序に意味がある理由

今日やらないことを、もう一度整理します。

```text
【正しい順序】
11日目 作業ユーザーを作り、鍵を引き継ぐ
        ↓ 別の端末から入れることを確かめる ★ここが関所★
12日目 root ログインとパスワード認証を止める
        ↓
13日目 ファイアウォールで入口を絞る

【やってはいけない順序】
借りた直後にパスワード認証を切る
        ↓
鍵の登録が間違っていた
        ↓
誰も入れない
```

「入れることを確かめる」を飛ばすと、
**間違いに気づく手段が無くなります**。
そして気づくのは、次にログインしようとしたときです。

スクリプトの最後がこうなっているのは、そのためです。

```text
完了しました。次にやること:
  1. **今の接続を閉じずに** 別の端末から次を試す
       ssh deploy@<このサーバー>
  2. 入れたら sudo が使えることを確かめる
       sudo -v
  3. どちらも確認できてから、12日目（SSHの制限）へ進む
```

「今の接続を閉じずに」が要点です。
今つながっている接続は、設定を間違えても切れません。
それが唯一の復旧経路になります。

---

## 7. コマンドの説明

### `sudo ./deploy/day-11/bootstrap.sh --dry-run`

| 項目 | 内容 |
| --- | --- |
| 目的 | 何を変更するつもりかだけ表示する |
| 実行場所 | サーバー上（転送してから） |
| 正常例 | `--dry-run: 何も変更しません。` が最初に出る |
| 異常例 | この行が出ないまま処理が進む |
| 判断方法 | 実行後に `id deploy` が「そんな利用者はいない」と言うこと |

**最初の行が出ているかを必ず見てください。**
出ていなければ dry-run として認識されていません（実際にそうなりました。8.1 参照）。

### `sudo ./deploy/day-11/bootstrap.sh --user deploy`

| 項目 | 内容 |
| --- | --- |
| 目的 | 初期設定を実際に適用する |
| 正常例 | 最後に「次にやること」が出る |
| 異常例 | `root に公開鍵がありません` の警告 |
| 判断方法 | `id deploy` と `sudo -l -U deploy` |

警告が出た場合、**12日目へ進んではいけません**。先に鍵を登録します。

### `ssh-copy-id`

| 項目 | 内容 |
| --- | --- |
| 目的 | 手元の公開鍵をサーバーへ登録する |
| 実行場所 | **手元の端末**（サーバーではない） |
| 正常例 | `Number of key(s) added: 1` |
| 異常例 | `Permission denied (publickey)` |
| 判断方法 | `ssh deploy@サーバー` でパスワードを聞かれずに入れること |

<div class="env-block env-linux env-macos">

**Linux / macOS**

```bash
ssh-copy-id deploy@サーバー
```

</div>

<div class="env-block env-windows">

**Windows (PowerShell)**

`ssh-copy-id` は標準では入っていません。同じことを手で行います。

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | ssh deploy@サーバー "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

`chmod` を含めているのが要点です。権限が緩いと SSH は鍵を黙って無視します。

</div>

### `sudo ./deploy/day-11/audit-login-attempts.sh`

| 項目 | 内容 |
| --- | --- |
| 目的 | 実際に来ているログイン試行を数える |
| 正常例 | 件数と、狙われている利用者名の一覧 |
| 異常例 | `ログを読めませんでした` |
| 判断方法 | root で実行しているか。ログは一般利用者から読めない |

---

## 8. よくあるエラー

実際に手が止まったものだけを書きます。全3件は
[`docs/errors/day-11.md`](https://github.com/kurumonn/DjangoCMS/blob/main/docs/errors/day-11.md)
にあります。

### 8.1 `--dry-run` が黙って無視され、本当にパッケージが入っていた

「何も変更しない」はずの実行が、実際にパッケージを入れていました。

```text
[14:27:11] OS: Ubuntu 24.04.4 LTS (family=debian)
[14:27:13]   導入します: ca-certificates unattended-upgrades chrony
Unpacking libpython3.12-minimal:amd64 (3.12.3-1ubuntu0.15) ...
Setting up python3.12-minimal (3.12.3-1ubuntu0.15) ...
```

原因は、引数を2か所で解釈していたことです。

```bash
# --user を先に自前で拾う
while [ $# -gt 0 ]; do
    case "$1" in
        --user) shift; NEW_USER="${1:-$NEW_USER}" ;;
    esac
    shift || true
done

parse_common_args "$@"     # ← ここに届く時点で $@ は空
```

上のループが `$@` を最後まで `shift` し尽くしていました。
`--dry-run` は誰にも読まれず、`DRY_RUN` は 0 のままです。

**気づきにくいのは、失敗しないからです。**
出力は正常で、終了コードも 0。
「dry-run したから安全」と思ったまま、本番のサーバーを書き換えます。

しかも検証スクリプトは `--dry-run` の直後に本実行をしていました。
本実行は冪等なので、dry-run が既に適用済みでも結果は同じになります。
**検証も通ってしまいました。**

直し方は、引数の解釈を1か所にまとめることです。

```bash
while [ $# -gt 0 ]; do
    case "$1" in
        --user)    shift; NEW_USER="${1:?--user には利用者名が必要です}" ;;
        --user=*)  NEW_USER="${1#*=}" ;;
        --dry-run) DRY_RUN=1 ;;
        *) die "知らない引数です: $1" ;;
    esac
    shift
done
```

知らない引数で止めるようにしたのも同じ理由です。
`--dryrun` と打ち間違えたときに、黙って本番実行されないようにします。

そして検証側に、**dry-run が何も変えていないこと**を確かめる行を足しました。

```bash
grep -q "何も変更しません" /tmp/dry.log || { echo "NG: dry-run と認識されていない"; exit 1; }
id deploy > /dev/null 2>&1 && { echo "NG: dry-run が利用者を作った"; exit 1; }
test ! -e /etc/sudoers.d/10-kururucms-logging || { echo "NG: dry-run が設定を書いた"; exit 1; }
```

**「実行しない」機能は、実行しなかったことを確かめないと意味がありません。**

### 8.2 同じ RHEL 系なのに、AlmaLinux だけ `curl` が入らない

```text
Error:
 Problem: problem with installed package curl-minimal-7.76.1-40.el9.x86_64
  - package curl-minimal-7.76.1-40.el9.x86_64 from @System conflicts with curl
    provided by curl-7.76.1-40.el9.x86_64 from baseos
```

RHEL 9 系には `curl` と `curl-minimal` があり、両方は入れられません。
AlmaLinux 9 の公式イメージには `curl-minimal` が入っていました。

紛らわしいのは、**同じ RHEL 系の Oracle Linux 9 では通る**ことです。
あちらのイメージには `curl` の方が入っていました。

「RHEL 系かどうか」で分岐しても足りません。
同じ系統でも、最初から何が入っているかは違います。

直し方は、パッケージ名ではなく**コマンドの有無**で判定することです。

```bash
ensure_command() {
    local cmd="$1"
    shift
    if command -v "$cmd" > /dev/null 2>&1; then
        log "  導入済み: $cmd ($(command -v "$cmd"))"
        return 0
    fi
    pkg_install "$@"
}
```

判定の基準は、**何が満たされていれば目的を達成したことになるか**で決めます。
`curl` は「コマンドが使えればよい」もの、
`chrony` は「そのパッケージが要る」もの、という違いです。

---

## 9. 動作確認

### 3つの環境で実際に流す

サーバーを3台借りずに確かめるため、コンテナで流します。

```bash
./deploy/day-11/verify.sh
```

```text
======================================================================
 ubuntu (ubuntu:24.04)
======================================================================
--- dry-run ---
dry-run は何も変更しませんでした。
--- 1回目 ---
--- 検査 ---
--- 2回目（冪等性）---
OK
[ubuntu] 成功
...
======================================================================
 成功 3 / 失敗 0
======================================================================
```

確かめている内容です。

- OS の判定が正しいか
- パッケージ名がその環境に存在するか
- 利用者・グループ・鍵の配置が意図どおりか（権限 `700` / `600` まで）
- パスワードがロックされているか
- sudoers の書式が壊れていないか
- **dry-run が本当に何も変更しないか**
- 2回流しても控えが増えないか、鍵が二重登録されないか

### コンテナでは確かめられないこと

正直に書きます。コンテナには systemd が動いていないので、
次は**確認できていません**。

- `systemctl enable --now` が実際にサービスを起動するか
- 自動更新が本当に走るか
- 時刻同期が効くか

検証スクリプトはダミーの `systemctl` を置いて、
「何が呼ばれたか」だけを記録しています。

```text
--- systemctl は何を呼ばれたか（実機では実際に動く部分）---
[fake systemctl] enable --now unattended-upgrades
[fake systemctl] enable --now chronyd
```

呼ばれたことは確かめられますが、動いたことは確かめられません。
**検証できていないものを、できたことにしない**のが大事です。

実機では次で確認します。

```bash
systemctl is-enabled unattended-upgrades chrony
```

```bash
timedatectl status | grep "System clock synchronized"
```

### チェックリスト

- [ ] `--dry-run` の1行目に「何も変更しません」が出る
- [ ] 実行後 `id deploy` が UID を返す
- [ ] `sudo -l -U deploy` で sudo が使える
- [ ] `deploy` のパスワードがロックされている（`passwd -S deploy` が `L`）
- [ ] `/home/deploy/.ssh` が `700`、`authorized_keys` が `600`
- [ ] **今の接続を閉じずに** 別の端末から `ssh deploy@サーバー` で入れる
- [ ] 入った先で `sudo -v` が通る
- [ ] `systemctl is-enabled` で自動更新と時刻同期が enabled
- [ ] 2回実行しても `.bak-` が増えない

**下から3つ目までが確認できるまで、12日目へ進まないでください。**

---

## 10. セキュリティ上の注意

### 今日入れた防御

| 対策 | 何を防ぐか |
| --- | --- |
| 作業用ユーザー + sudo | root での操作ミスと、侵入時の即時全権取得 |
| パスワードのロック | パスワード総当たりでの侵入 |
| セキュリティ更新の自動適用 | 公表済み脆弱性の放置 |
| 自動再起動しない | 気づかないうちのサービス停止 |
| 時刻同期 | 証明書判定・TOTP・ログ突合の破綻 |
| sudo の操作ログ | 何をしたか分からなくなること |
| `timestamp_timeout=5` | 席を離れた隙の権限流用 |

### 利用者名について

`admin` `ubuntu` `user` `test` `deploy` — どれも狙われます。
`deploy` も例外ではありません。

ただし**利用者名を隠すのは対策ではありません**。
鍵認証のみにすれば、名前が当たっても入れません。
名前を変えるのは、ログのノイズが少し減る程度の効果です。

このサーバーの実測で、パスワード失敗が 0 件だったのがその証拠です。
1,330 回試されても、パスワードを試す段階に到達していません。

### 時刻同期がセキュリティの話である理由

ずれると壊れるものが具体的にあります。

- **TLS 証明書の有効期限**の判定（数分ずれただけで「期限切れ」になる）
- **TOTP**（9日目で入れた認証アプリ。30秒ごとに変わるので、ずれると通らない）
- **ログの時刻**（複数サーバーのログを突き合わせられなくなる）

3つ目は障害対応で効きます。
「Nginx のログの 12:03 と Django のログの 12:03 が同じ瞬間か」が
分からないと、原因を追えません。

### まだ足りないもの

今日の時点では、**まだパスワード認証で root に入れます**。
これは意図的です。12日目で塞ぎます。

ファイアウォールも入れていません。13日目です。

---

## 11. 今日の復習問題

**問1.** 借りた直後にパスワード認証を切ってはいけないのはなぜですか。
切ってよくなるのはいつですか。

**問2.** `usermod -aG sudo deploy` の `-a` を忘れると何が起きますか。

**問3.** `/home/deploy/.ssh/authorized_keys` の権限が `644` だとどうなりますか。
エラーは出ますか。

**問4.** セキュリティ更新は自動適用するのに、自動再起動はしないのはなぜですか。

**問5.** 「存在しない利用者への試行が 1,330 件、パスワード認証の失敗が 0 件」
という数字は、何を意味していますか。

<details>
<summary>解答</summary>

**問1.**
鍵で入れることをまだ確かめていないためです。
鍵の登録や権限が間違っていた場合、パスワードを切った瞬間に
誰もサーバーへ入れなくなります。
別の端末から `ssh deploy@サーバー` で入れることと、
そこで `sudo -v` が通ることを確認してから切ります。
確認は「今つながっている接続を閉じずに」行います。
その接続が唯一の復旧経路になるためです。

**問2.**
`-a` は追加（append）の意味です。忘れると **指定しなかったグループから全部外れます**。
たとえば `docker` グループに入っていた利用者が外れて、
Docker が使えなくなります。

**問3.**
SSH はその鍵を**無視します**。エラーは出ません。
「鍵を登録したのにパスワードを聞かれる」という形で現れるので、
原因に気づきにくい部類です。
`.ssh` は `700`、`authorized_keys` は `600` にします。

**問4.**
再起動はサービスの停止を伴うためです。
自動再起動を有効にすると、深夜に予告なくサイトが落ちます。
更新そのものは早く当てたいので自動にし、
停止を伴う操作だけ自分のタイミングに残します。

**問5.**
パスワード認証そのものが無効になっている、という意味です。
攻撃者は「そんな利用者はいない」で弾かれていて、
パスワードを試す段階まで到達していません。
1,330 回狙われていること自体は防げませんが、
入口が閉じているので実害がありません。

</details>

---

## 12. Git の差分

```text
ブランチ: main
タグ　　: day-11
コミット: day-11: サーバーの初期設定を3つの環境で作る
```

```bash
git diff day-10 day-11
```

```bash
git checkout day-11
```

主な変更:

```text
新規  deploy/README.md
新規  deploy/lib/common.sh
新規  deploy/day-11/bootstrap.sh
新規  deploy/day-11/audit-login-attempts.sh
新規  deploy/day-11/verify.sh
新規  docs/errors/day-11.md
```

Django のコードは変更していません。

---

## 13. 次回予告

明日は SSH の鍵と、root ログインの制限です。

- 鍵の種類は何を選ぶか（ed25519 と RSA の違い）
- 秘密鍵にパスフレーズを付けるか
- **鍵を無くしたときにどうするか**（今日の「順序」と同じ話です）
- root ログインとパスワード認証を止める

今日作った利用者で入れることを確かめてから読んでください。
明日の作業は、確認を飛ばすと締め出されます。

---

*この記事のコードは <https://github.com/kurumonn/DjangoCMS>（タグ `day-11`）にあります。*
