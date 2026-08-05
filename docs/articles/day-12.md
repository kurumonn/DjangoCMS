# 【12日目】SSH を鍵認証だけにする――締め出されない手順と、戻れる作り方

> 連載「10日で学ぶ Django 本番デプロイ」の2日目（通算12日目）です。
> 成果物: <https://github.com/kurumonn/DjangoCMS>（タグ `day-12`）

---

## 1. 今日の結論

**今日やること**は、次の4つです。

1. 手元で SSH 鍵を作り、サーバーへ登録する
2. **その鍵で実際に入れたことを確かめる**
3. パスワード認証と root ログインを止める
4. 間違えたときに戻れる経路を用意しておく

**今日いちばん大事なのは 2 です。**

11日目にも「入れることを確かめてから」と書きました。
しかし、文章で書いた注意は急いでいるときに読み飛ばされます。
今日は**確かめていなければスクリプトが動かない**ようにします。

サーバーの設定変更で最も多い事故は、
「設定は正しかったが、自分が入れなくなった」です。
攻撃者を締め出す作業は、手順を1つ間違えると自分を締め出す作業になります。

---

## 2. 今日の完成状態

作業が終わると、こうなります。

```text
攻撃者                          あなた
  │ パスワードで総当たり           │ 手元の秘密鍵
  │                              │
  ▼                              ▼
  ✕ PasswordAuthentication no    ○ PubkeyAuthentication yes
  ✕ PermitRootLogin no           ○ AllowUsers deploy
  ✕ 3回で切断 (MaxAuthTries 3)
```

---

## 3. 今日変更するファイル

```text
DjangoCMS/
├── .gitattributes                    新規  ← 改行コードの固定
└── deploy/
    ├── lib/common.sh                 変更なし（11日目のものを使う）
    └── day-12/
        ├── verify-login.sh           新規  ← 鍵で入れたかを確かめる
        ├── harden-ssh.sh             新規  ← 鍵認証だけにする
        └── verify.sh                 新規  ← 上の2つを検証する
```

サーバー側で変わるのは1ファイルだけです。

```text
/etc/ssh/sshd_config.d/50-kururucms-hardening.conf   新規
```

**`/etc/ssh/sshd_config` 本体は書き換えません。** 理由は6章で説明します。

---

## 4. 完成コード

### 4.1 手元で鍵を作る

<div class="env-block env-windows">

**Windows (PowerShell)**

Windows 10 以降には OpenSSH が標準で入っています。

```powershell
ssh-keygen -t ed25519 -C "kururucms-deploy"
```

</div>

<div class="env-block env-macos env-linux">

**macOS / Linux**

```bash
ssh-keygen -t ed25519 -C "kururucms-deploy"
```

</div>

3回聞かれます。

| 質問 | 答え方 |
| --- | --- |
| `Enter file in which to save the key` | そのまま Enter（既定の場所でよい） |
| `Enter passphrase` | **必ず設定する**（後述） |
| `Enter same passphrase again` | 同じものを入力 |

`-t ed25519` を指定するのは、既定の RSA より短く速く、
かつ現在の推奨だからです。鍵の長さを自分で決める必要もありません。

**パスフレーズを空にしないでください。**
鍵ファイルは、手元の PC を紛失したり、バックアップから抜き取られたりします。
パスフレーズは「鍵ファイルを手に入れただけでは使えない」ようにする2つ目の壁です。

毎回入力するのが面倒であれば、エージェントに預けます。

<div class="env-block env-windows">

```powershell
Get-Service ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

</div>

<div class="env-block env-macos env-linux">

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

</div>

### 4.2 公開鍵をサーバーへ渡す

公開鍵は `id_ed25519.pub`（`.pub` が付く方）です。
**`.pub` が付かない方は秘密鍵なので、絶対に渡しません。**

<div class="env-block env-macos env-linux">

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub deploy@<サーバーのIP>
```

</div>

<div class="env-block env-windows">

Windows の OpenSSH には `ssh-copy-id` がありません。
同じことを手で行います。

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh deploy@<サーバーのIP> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

`>>` であることを確認してください。`>` にすると、
**既にある鍵を全部消して**上書きします。
自分以外の鍵が登録されている環境では、その人を締め出します。

</div>

### 4.3 入れたことを確かめる

ここが今日の中心です。

```bash
ssh -o PreferredAuthentications=publickey deploy@<サーバーのIP>
```

`-o PreferredAuthentications=publickey` を付けるのが要点です。
これを付けないと、鍵が効いていなくても
**パスワードを聞かれて、入力すれば入れてしまいます。**
「入れた」という結果だけを見ると、鍵で入れたと錯覚します。

このオプションを付けた状態でパスワードを聞かれたら、鍵は効いていません。

### 4.4 「入れたこと」を機械に確かめさせる

人間の確認は忘れます。サーバー側の記録を見て判断させます。

```bash
# deploy/day-12/verify-login.sh（抜粋）

# 終了コードの意味
#   0 = 鍵ログインの記録があった
#   1 = 記録が無かった（＝まだ入れていない）
#   2 = 判断できなかった（ログが読めない・空・sshd の記録が1行も無い）
EXIT_FOUND=0
EXIT_NOT_FOUND=1
EXIT_UNKNOWN=2

matches="$(printf '%s\n' "$LOG" \
    | grep -E "Accepted (publickey|hostbased) for ${TARGET_USER}( |$)" || true)"
```

なぜ `authorized_keys` の中身を見るだけでは足りないのか。
ファイルが存在し、権限も 600 で、中身も鍵の形をしていて、
それでも入れないことがあるからです。実際の原因の例を挙げます。

* 貼り付けたのが**公開鍵ではなく秘密鍵**だった
* 改行が混ざって1つの鍵が2行に割れていた
* ホームディレクトリの権限が緩く、sshd が `.ssh` ごと無視した
* SELinux のラベルが違って sshd から読めなかった（RHEL 系）
* 鍵は正しいが、手元の端末が別の鍵を送っていた

どれも「ファイルは正しく見える」状態です。
**実際に入れたという事実**だけが根拠になります。

### 4.5 鍵認証だけにする

```bash
# /etc/ssh/sshd_config.d/50-kururucms-hardening.conf

# root で直接ログインさせない。
# root は名前が決まっているので、利用者名を推測する手間が要らない。
PermitRootLogin no

# パスワード認証を止める。
# 総当たりは「いつか当たる」攻撃なので、時間をかければ成立する。
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no

PubkeyAuthentication yes

# ログインできる利用者を絞る。
# 新しい利用者が増えても、ここに書かない限り SSH では入れない。
AllowUsers deploy

# 1接続あたりの認証試行回数。既定(6)より減らす。
MaxAuthTries 3

# 認証を終えるまでの猶予。既定(2m)は長い。
LoginGraceTime 20

# 未認証のまま同時に張れる接続数。
# "10:30:60" = 10本を超えたら30%の確率で落とし、60本で全部落とす。
MaxStartups 10:30:60

# 使わない機能を止める。攻撃面はコード量に比例する。
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no

# どの鍵で入ったかがログに残るよう詳細度を上げる。
LogLevel VERBOSE
```

`UsePAM` を書いていないことに注意してください。
既定の `yes` のままにします。理由は8章の2番です。

### 4.6 実行する

```bash
sudo ./deploy/day-12/harden-ssh.sh --user deploy --dry-run
```

問題が無ければ、**今の接続を開いたまま**、自動で戻る予約を付けて実行します。

```bash
sudo ./deploy/day-12/harden-ssh.sh --user deploy --rollback-in 10
```

**別の端末**を開き、次の3つを確かめます。

```bash
ssh deploy@<サーバーのIP>                                    # 入れる
ssh root@<サーバーのIP>                                      # 入れない
ssh -o PreferredAuthentications=password deploy@<サーバーのIP>  # 入れない
```

確かめてから、10分以内に予約を取り消します。

```bash
sudo ./deploy/day-12/harden-ssh.sh --confirm
```

---

## 5. コードの意味

### 関所を作る

```bash
set +e
"$SCRIPT_DIR/verify-login.sh" "${VERIFY_ARGS[@]}"
verify_status=$?
set -e

# 0 = 確認できた / 1 = 記録が無い / 2 = 判断できない
# 2 のときも進めない。「分からない」は「大丈夫」ではない。
if [ "$verify_status" -eq 0 ]; then
    :
elif [ "$ALLOW_UNVERIFIED" -eq 1 ]; then
    warn "--allow-unverified が指定されたため、確認できないまま続行します。"
else
    die "確認が取れないため、設定を変更せずに終了します。"
fi
```

`set +e` で一時的にエラー終了を止めているのは、
`verify-login.sh` が 1 や 2 を返すのは**想定内**だからです。
`set -e` のままだと、判定する前にスクリプトが終わります。

`--allow-unverified` という逃げ道は用意してあります。
ログが本当に取れない環境が存在するためです。
ただし**既定では通らない**ようにしてあります。
逃げ道は、選んだことが記録に残る形にしておきます。

### `Include` が無ければ何もしない

```bash
if ! grep -qE '^\s*Include\s+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config; then
    die "/etc/ssh/sshd_config に Include /etc/ssh/sshd_config.d/*.conf がありません。
     このままファイルを置いても読み込まれません。"
fi
```

`sshd_config.d/` にファイルを置く方式は、
`sshd_config` 本体に `Include` 行がある場合にしか効きません。

Ubuntu 24.04 と RHEL 9 系はどちらも既定で書かれていますが、
古い環境や、誰かが手で書き換えた環境では消えていることがあります。

その場合、ファイルを置いても**何も起きません**。
そして「設定した」という認識だけが残ります。
これはエラーが出ないぶん、設定を間違えるより危険です。

### 反映前に検査する

```bash
if ! sshd -t 2>/tmp/sshd-test.err; then
    cat /tmp/sshd-test.err >&2
    previous="$(ls -1t "${CONF_PATH}".bak-* 2>/dev/null | head -1 || true)"
    if [ -n "$previous" ]; then
        mv -f "$previous" "$CONF_PATH"
        die "sshd の設定に誤りがあったため、直前の設定へ戻しました。"
    fi
    rm -f "$CONF_PATH"
    die "sshd の設定に誤りがあったため、書いたファイルを削除しました。"
fi
```

`sshd -t` は設定の書式を検査するだけで、何も反映しません。
書式が不正なまま reload すると sshd の起動に失敗し、以後入れなくなります。

**戻し方が2通りある**のが要点です。
「消す」だけでは足りません。詳しくは8章の3番で説明します。

---

## 6. 内部で起きていること

### なぜ `sshd_config` 本体を書き換えないのか

理由は3つあります。

**1つ目**は、OS の更新で上書きされることがあるからです。
本体は OS が管理するファイルなので、更新時に
「設定ファイルが変更されています」と聞かれたり、
`.rpmnew` / `.dpkg-dist` として新しい版が横に置かれたりします。
そのたびに手作業の差分確認が要ります。

**2つ目**は、元に戻すのが簡単だからです。
`sshd_config.d/` の中の1ファイルを消せば、元の状態に戻ります。
本体を書き換えていると、どこを直したかを覚えていないと戻せません。

**3つ目**は、何を変えたかが1ファイルに集まるからです。
半年後の自分が「この設定は誰がなぜ入れたのか」を追えます。

### 番号の意味

`50-kururucms-hardening.conf` の `50` は読み込み順です。
`sshd_config.d/*.conf` は名前順に読まれます。

そして **sshd は「最初に見つかった値」を採用します。**
後から書いた方が勝つ、ではありません。
これは多くの設定ファイルと逆なので、間違えやすいところです。

クラウド事業者が置く設定（`60-cloudimg-settings.conf` など）より
前に読ませたいので、`50` にしています。

### なぜ `restart` ではなく `reload` なのか

```bash
systemctl reload sshd
```

`restart` は sshd を落として起動し直すので、
**今つながっている接続が切れます**。

設定を間違えていた場合、その接続だけが唯一の復旧経路です。
自分でそれを切ることになります。

`reload` は設定を読み直すだけで、既存の接続はそのまま残ります。
新しい接続だけが新しい設定で処理されます。

これは「万一のため」ではなく、**手順の一部**です。
新しい設定が正しいかどうかは、
既存の接続を保ったまま別の端末で試して初めて分かります。

---

## 7. コマンドの説明

### `ssh-keygen -t ed25519`

| 項目 | 内容 |
| --- | --- |
| 目的 | 鍵の組（秘密鍵・公開鍵）を作る |
| 実行場所 | **手元の PC**（サーバーではない） |
| 正常例 | `~/.ssh/id_ed25519` と `~/.ssh/id_ed25519.pub` ができる |
| 異常例 | `id_ed25519 already exists.` （既にある。上書きすると前の鍵で入れなくなる） |
| 判断方法 | `ssh-keygen -l -f ~/.ssh/id_ed25519.pub` で指紋が出る |

サーバー上で鍵を作らないでください。
秘密鍵はサーバーへ置かないものです。置いた時点で、
そのサーバーに入れた人が鍵を持ち出せます。

### `sshd -t`

| 項目 | 内容 |
| --- | --- |
| 目的 | 設定ファイルの書式を検査する |
| 実行場所 | サーバー（root 権限が要る） |
| 正常例 | 何も表示されない |
| 異常例 | `/etc/ssh/sshd_config.d/50-....conf line 12: Bad configuration option` |
| 判断方法 | 終了コードが 0 |

`-t` は「テスト」です。何も反映しません。
**反映前に必ず通してください。**

### `systemctl reload sshd`

| 項目 | 内容 |
| --- | --- |
| 目的 | 設定を読み直させる（接続は切らない） |
| 正常例 | 何も表示されない |
| 異常例 | `Unit sshd.service not found.` |
| 判断方法 | `systemctl status sshd` が `active (running)` |

<div class="env-block env-ubuntu">

Ubuntu ではサービス名が `ssh` です（`sshd` ではありません）。

```bash
sudo systemctl reload ssh
```

</div>

<div class="env-block env-rhel env-alma">

RHEL 系ではサービス名が `sshd` です。

```bash
sudo systemctl reload sshd
```

</div>

スクリプトでは、どちらでも動くようにしてあります。

```bash
run systemctl reload sshd 2>/dev/null || run systemctl reload ssh
```

---

## 8. よくあるエラー

### 8.1 `Permission denied (publickey)` で入れない

鍵の場所・権限・中身のどこかが違います。順に見ます。

**サーバー側の権限**を確認します。

```bash
ls -ld ~ ~/.ssh && ls -l ~/.ssh/authorized_keys
```

| 対象 | 必要な権限 |
| --- | --- |
| ホームディレクトリ | 他人に書き込み権が無いこと（`755` 以下） |
| `~/.ssh` | `700` |
| `~/.ssh/authorized_keys` | `600` |

権限が緩いと、sshd は**エラーを出さずにその鍵を無視します**。
これは仕様です。他人が書き込める場所にある鍵は信用できないためです。

**手元がどの鍵を送っているか**を確認します。

```bash
ssh -v deploy@<サーバーのIP> 2>&1 | grep -i "offering\|send_pubkey"
```

`Offering public key: /home/you/.ssh/id_ed25519` のように出ます。
意図した鍵でなければ、`-i` で明示します。

```bash
ssh -i ~/.ssh/id_ed25519 deploy@<サーバーのIP>
```

**サーバー側のログ**を見ます。これが一番早いことが多いです。

<div class="env-block env-ubuntu">

```bash
sudo journalctl -u ssh -n 50 --no-pager
```

</div>

<div class="env-block env-rhel env-alma">

```bash
sudo journalctl -u sshd -n 50 --no-pager
```

</div>

### 8.2 `User deploy not allowed because account is locked`

鍵は正しいのに、ロックされていると言われます。

11日目で `passwd --lock deploy` を実行しているためです。
これは `/etc/shadow` のパスワード欄の先頭に `!` を付けます。
「パスワードでは入れない」という意図ですが、
**アカウント全体のロックとしても解釈されます**。

その判定を行うのが PAM です。
`UsePAM yes`（既定）なら、鍵で入った場合は
「パスワードは使わないので `!` は無関係」と扱われます。

`UsePAM no` を書くと、sshd が自分でロック状態を見に行き、
`!` を「このアカウントは使用不可」と読んで拒否します。

**対処**: `UsePAM no` を書かない。既定の `yes` のままにします。

これは「明示しておいた方が親切だろう」と思って書いた1行が
締め出しの原因になった例です。
**既定値を明示的に書き直す変更は、それ自体が変更です。**

### 8.3 設定ミスを弾いたはずが、防御が外れていた

これはエラーメッセージが出ません。テストを書いていて見つけました。

`harden-ssh.sh` は2回目以降も実行されます。
1回目で `PasswordAuthentication no` が入った状態のサーバーに対し、
2回目の実行が `sshd -t` の検査に落ちたとします。

このとき、最初の実装は書いたファイルを消すだけでした。

```bash
rm -f "$CONF_PATH"    # ← これだけだと足りない
```

消えるのは新しいファイルだけではありません。
**1回目に入れた設定ごと**消えます。
そして reload していないので、その場では何も起きません。

次に何かの理由で sshd が再読み込みされた瞬間、
`PermitRootLogin` も `PasswordAuthentication` も既定値へ戻ります。
**パスワード認証と root ログインが、無言で復活します。**

**対処**: 直前の控えがあれば戻します。

```bash
previous="$(ls -1t "${CONF_PATH}".bak-* 2>/dev/null | head -1 || true)"
if [ -n "$previous" ]; then
    mv -f "$previous" "$CONF_PATH"
    die "直前の設定へ戻しました。"
fi
rm -f "$CONF_PATH"
```

検証では、**壊れた設定で失敗させた後に**
`PasswordAuthentication no` が残っていることを確かめています。
終了コードだけを見ていると通ってしまいます。

### 8.4 `/usr/bin/env: 'bash\r': No such file or directory`

Windows で書いたスクリプトの改行が CRLF になっています。

シェバングは1行目の `#!/usr/bin/env bash` を読みますが、
行末に `\r` が付くと `bash\r` という名前の実行ファイルを探します。

メッセージに `\r` が見えているので原因は書いてあるのですが、
**エディターの画面上では CRLF も LF も同じに見えます。**

**対処**: `.gitattributes` で固定します。

```text
* text=auto eol=lf

*.sh   text eol=lf
*.conf text eol=lf
```

そのうえで、検証スクリプトの最初の手順として機械的に確かめます。

```bash
if awk '/\r/ { found = 1 } END { exit !found }' "$script"; then
    echo "CR が混ざっています: $script"
    exit 1
fi
```

`grep -q $'\r'` と書かないのが要点です。
そう書くと、**その検査スクリプト自身に本物の CR が入り込み**、
CR の無いファイルまで「CR あり」と報告するようになります。
実際にこれを踏みました。

---

## 9. 動作確認

- [ ] `ssh -o PreferredAuthentications=publickey deploy@サーバー` で、パスワードを聞かれずに入れる
- [ ] `sudo ./deploy/day-12/verify-login.sh --user deploy` が 0 を返す
- [ ] `sudo ./deploy/day-12/harden-ssh.sh --user deploy --dry-run` が何も変更しない
- [ ] 適用後、**別の端末**で `deploy` として入れる
- [ ] 適用後、`ssh root@サーバー` が `Permission denied` になる
- [ ] 適用後、`ssh -o PreferredAuthentications=password deploy@サーバー` が `Permission denied` になる
- [ ] `sudo sshd -T | grep -E "permitrootlogin|passwordauthentication"` が両方 `no`

最後の1つは、**設定ファイルではなく sshd の実効値**を見ます。
`sshd -T` は、複数のファイルを読み込んだ後の最終的な値を出力します。
ファイルを読んで確認するより確実です。

---

## 10. セキュリティ上の注意

### 鍵を作った端末が、そのまま鍵の保管場所になる

秘密鍵は手元の PC にあります。
つまり**手元の PC の安全性が、サーバーの安全性の上限**になります。

* ディスクは暗号化しておく（BitLocker / FileVault / LUKS）
* パスフレーズを空にしない
* 鍵をクラウドストレージの同期対象に置かない

3つ目は見落としやすい項目です。
`~/.ssh` を同期フォルダーの中に置くと、
サーバーの鍵が事業者のサーバー上にも存在することになります。

### `AllowUsers` は増やすときに忘れる

`AllowUsers deploy` と書くと、**そこに書いた人しか入れません**。
これは狙った動作ですが、後で利用者を増やしたときに、
「鍵は登録したのに入れない」で必ず一度つまずきます。

利用者を増やしたら、この行も更新します。
増やす側に手間がかかるのは、この設定の欠点ではなく目的です。

### `MaxAuthTries 3` は攻撃を止めない

1接続あたりの試行回数を減らすだけなので、
攻撃側は接続を張り直せば何度でも試せます。

これは総当たりを**止める**設定ではなく、
1接続あたりの効率を下げてログを読みやすくする設定です。
接続そのものを止めるのは、13日目のファイアウォールと fail2ban の役目です。

「設定したから安全」と考えないでください。
何を防いでいて何を防いでいないかを、設定ごとに分けて理解します。

### 港（ポート）を変えることについて

`--port` で SSH のポートを変更できるようにしてあります。
ただし**既定では変更しません**。

ポート変更は、無差別に 22番だけを叩く走査を減らします。
ログが静かになるという実利はあります。

しかし、これは**認証を強くする設定ではありません**。
ポート走査をすれば見つかります。
「ポートを変えたから鍵認証は後でいい」という順序にしないでください。

---

## 11. 今日の復習問題

<details markdown="1">
<summary>問1. `sshd_config.d/` に設定ファイルを置いたのに、設定が効きません。最初に何を確認しますか。</summary>

`/etc/ssh/sshd_config` に次の行があるかを確認します。

```text
Include /etc/ssh/sshd_config.d/*.conf
```

この行が無いと、`sshd_config.d/` の中身は読み込まれません。
ファイルを置いてもエラーは出ないので、
「設定した」という認識だけが残ります。

`sshd -T` で実効値を見ると、置いたはずの値になっていないことが分かります。
</details>

<details markdown="1">
<summary>問2. 設定を反映するとき、`restart` ではなく `reload` を使うのはなぜですか。</summary>

`restart` は今つながっている接続を切るためです。

設定を間違えていた場合、その接続が唯一の復旧経路になります。
`restart` はそれを自分で切ることになります。

`reload` は設定を読み直すだけで、既存の接続は残ります。
新しい設定が正しいかどうかは、
既存の接続を保ったまま別の端末で試して初めて分かります。
</details>

<details markdown="1">
<summary>問3. `authorized_keys` の中身が正しいことを確認できれば、パスワード認証を止めてよいですか。</summary>

いけません。

ファイルが正しく見えても入れないことがあります。
ホームディレクトリの権限が緩い、SELinux のラベルが違う、
手元の端末が別の鍵を送っている、などが実際に起きます。

根拠になるのは**実際に入れたという事実**だけです。
認証ログの `Accepted publickey for <利用者>` を確認します。
</details>

<details markdown="1">
<summary>問4. `verify-login.sh` が終了コードを 0/1 の2つではなく 0/1/2 の3つにしているのはなぜですか。</summary>

「記録が無い」と「判断できない」を区別するためです。

ログが空になる理由は、ログインしていないこと以外にもあります
（ローテーション直後、記録先が別、journald が未起動など）。

「分からない」を「駄目」に寄せると、入れている人の作業が止まります。
「分からない」を「大丈夫」に寄せると、締め出しを防げません。
どちらにも寄せられないので、第三の返り値が必要になります。
</details>

<details markdown="1">
<summary>問5. `sshd -t` の検査に失敗したとき、書いたファイルを削除するだけでは不十分なのはなぜですか。</summary>

2回目以降の実行では、そのファイルに**前回入れた設定**が含まれているためです。

削除すると `PermitRootLogin` と `PasswordAuthentication` の指定ごと消え、
次に sshd が設定を読み直したときに既定値へ戻ります。
つまりパスワード認証と root ログインが復活します。

設定ミスを弾いたつもりの処理が、防御を外します。
直前の控え（`.bak-*`）があれば、それを戻す必要があります。
</details>

---

## 12. Git の差分

```bash
git diff day-11 day-12
```

```text
 .gitattributes                    |  24 ++++
 deploy/day-12/harden-ssh.sh       | 274 ++++++++++++++++++++++++++++++
 deploy/day-12/verify-login.sh     | 156 ++++++++++++++++++
 deploy/day-12/verify.sh           | ...
 docs/articles/day-12.md           | ...
 docs/errors/day-12.md             | ...
```

`verify.sh` は、本物の sshd を動かしたコンテナに対して
次の順で検証します。

1. スクリプトに CR が混ざっていないこと
2. 確認が取れていない状態では実行を拒否すること
3. 実際に鍵でログインできること
4. ログが空のとき 2（判断できない）を返すこと
5. `--dry-run` が何も変更しないこと
6. 適用後に deploy で入れ、root とパスワードでは入れないこと
7. 2回実行しても結果が変わらないこと
8. **壊れた設定で失敗させた後も、前回の設定が残っていること**

8 が今日いちばん重要な検証です。

---

## 13. 次回予告

13日目は**ファイアウォール**です。

今日は「SSH に入れる条件」を絞りました。
明日は「そもそも何番の港を開けておくか」を決めます。

SSH を鍵認証だけにしても、22番が世界中から見えていることは変わりません。
ログには毎日数千件の試行が残り続けます。
そこを減らします。

あわせて、Docker が iptables を直接書き換えるせいで
**ファイアウォールの設定が効かない**という、
落とし穴としてよく知られた挙動を扱います。
`ufw` で塞いだつもりのポートが外から見えている、という状態です。
