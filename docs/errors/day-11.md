# 11日目に実際に起きたエラー

形式は 症状 / 再現条件 / 原因 / 直し方 / 判断方法。

---

## 1. `--dry-run` が黙って無視され、本当にパッケージが入っていた

### 症状

「何も変更しない」はずの実行が、実際にパッケージを入れていた。

```text
[14:27:11] OS: Ubuntu 24.04.4 LTS (family=debian)
[14:27:13]   導入します: ca-certificates unattended-upgrades chrony
Unpacking libpython3.12-minimal:amd64 (3.12.3-1ubuntu0.15) ...
Setting up python3.12-minimal (3.12.3-1ubuntu0.15) ...
```

`--dry-run` を付けているのに `Unpacking` が出ています。
エラーは1つも出ていません。

### 再現条件

引数を2か所で解釈し、片方で `shift` する。

```bash
# --user を先に自前で拾う
while [ $# -gt 0 ]; do
    case "$1" in
        --user) shift; NEW_USER="${1:-$NEW_USER}" ;;
    esac
    shift || true
done

# 残りを共通処理へ渡す……つもり
parse_common_args "$@"
```

### 原因

上のループが `$@` を最後まで `shift` し尽くしています。
`parse_common_args "$@"` に届く時点で **`$@` は空**でした。

そのため `--dry-run` は誰にも読まれず、`DRY_RUN` は 0 のまま。
`run` はそのまま本当のコマンドを実行します。

### 気づき方が難しい理由

**失敗しないからです。**

`--dry-run` を付けた実行が、付けなかった実行と同じ結果になる。
出力は正常で、終了コードも 0。
「dry-run したから安全」と思ったまま、本番のサーバーを書き換えます。

しかもこの検証スクリプトは、`--dry-run` の直後に本実行をしていました。
本実行は冪等なので、dry-run が既に適用済みでも結果は同じになります。
**検証が通ってしまった**わけです。

安全のための仕組みが黙って効かなくなるのは、
機能が壊れるより悪い形の壊れ方です。
壊れていることに気づく機会が無いまま、安全だと思って使い続けます。

### 直し方

引数の解釈を1か所に集約します。

```bash
while [ $# -gt 0 ]; do
    case "$1" in
        --user)    shift; NEW_USER="${1:?--user には利用者名が必要です}" ;;
        --user=*)  NEW_USER="${1#*=}" ;;
        --dry-run) DRY_RUN=1 ;;
        --help|-h) ...; exit 0 ;;
        *) die "知らない引数です: $1" ;;
    esac
    shift
done
```

知らない引数で `die` するようにしたのも同じ理由です。
`--dryrun` と打ち間違えたときに、黙って本番実行されないようにします。

### 判断方法

「dry-run が何も変えていないこと」を、検証側で確かめます。

```bash
grep -q "何も変更しません" /tmp/dry.log || { echo "NG: dry-run と認識されていない"; exit 1; }
id deploy > /dev/null 2>&1 && { echo "NG: dry-run が利用者を作った"; exit 1; }
test ! -e /etc/sudoers.d/10-kururucms-logging || { echo "NG: dry-run が設定を書いた"; exit 1; }
test ! -e /tmp/systemctl.log || { echo "NG: dry-run が systemctl を呼んだ"; exit 1; }
```

```text
--- dry-run ---
dry-run は何も変更しませんでした。
```

### 学び

**「実行しない」機能は、実行しなかったことを確かめないと意味がありません。**

`--dry-run` を実装したときに検証したのは「エラーなく終わること」でした。
それは何も保証していませんでした。

---

## 2. 同じ RHEL 系なのに、AlmaLinux だけ `curl` が入らない

### 症状

Ubuntu と Oracle Linux 9 では通ったスクリプトが、AlmaLinux 9 で止まった。

```text
[14:23:06]   導入します: curl dnf-automatic chrony
Error:
 Problem: problem with installed package curl-minimal-7.76.1-40.el9.x86_64
  - package curl-minimal-7.76.1-40.el9.x86_64 from @System conflicts with curl
    provided by curl-7.76.1-40.el9.x86_64 from baseos
  - conflicting requests
```

### 再現条件

AlmaLinux 9 または Rocky Linux 9 の最小構成に、`dnf install curl` する。

### 原因

RHEL 9 系には `curl` と `curl-minimal` の2つのパッケージがあり、
**両方は入れられない**（互いに conflicts）。

AlmaLinux 9 の公式イメージには `curl-minimal` が入っています。
そこへ `curl` を入れようとすると、片方を消す必要が出るため止まります。

紛らわしいのは、**同じ RHEL 系の Oracle Linux 9 では通る**ことです。
あちらのイメージには `curl` の方が入っていました。

つまり「RHEL 系かどうか」で分岐しても足りません。
同じ系統でも、どのパッケージが最初から入っているかは違います。

### 直し方

`curl` は「そのコマンドが使えればよい」ものなので、
パッケージ名ではなく**コマンドの有無**で判定します。

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

```bash
ensure_command curl curl
```

`sudo` や `chrony` のように「そのパッケージが要る」ものは、
今までどおりパッケージ名で判定します。判定の基準は、
**何が満たされていれば目的を達成したことになるか**で決めます。

### 判断方法

3つの環境すべてで流す。1つで通ったことは、他の2つで通る根拠になりません。

```bash
./deploy/day-11/verify.sh
```

```text
 成功 3 / 失敗 0
```

---

## 2. コンテナへリポジトリをマウントできず「ファイルが無い」と言われる

### 症状

```text
--- dry-run ---
bash: line 22: /work/deploy/day-11/bootstrap.sh: No such file or directory
```

ファイルは確かにある。改行コードも LF で正しい。

### 再現条件

Windows の Git Bash から、`docker run -v` にパスを渡す。

```bash
REPO_ROOT="$(pwd)"          # /e/PycharmProjects/DjangoCMS
docker run --rm -v "$REPO_ROOT:/work:ro" ubuntu:24.04 ls /work
```

```text
ls: cannot access '/work': No such file or directory
```

### 原因

10日目の7番と同じ、MSYS のパス変換です。
ただし今回は**マウント先の `/work` まで**書き換えられるので、
症状が「スクリプトが無い」という別の形で出ました。

10日目に学んだつもりでいたのに、
`docker run -v` という違う文脈で同じ罠を踏んでいます。
**教訓は「その書き方をしない」ではなく「その環境ではパスが書き換わる」**
という形で覚えないと、次の文脈で再発します。

### 直し方

パスを Windows 形式に直し、変換そのものを止めます。
Linux / macOS では何もしません。

```bash
if command -v cygpath > /dev/null 2>&1; then
    MOUNT_SRC="$(cygpath -w "$REPO_ROOT")"
    export MSYS_NO_PATHCONV=1
else
    MOUNT_SRC="$REPO_ROOT"
fi

docker run --rm -v "$MOUNT_SRC:/work:ro" ...
```

### 判断方法

まず切り分けます。中身の問題か、渡し方の問題か。

```bash
docker run --rm -v "/e/PycharmProjects/DjangoCMS:/work:ro" ubuntu:24.04 ls /work
```

これで `/work` 自体が見えなければ、スクリプトの中身は関係ありません。
`file` で改行コードを確かめたのは、それを先に否定するためでした。

```text
deploy/day-11/bootstrap.sh: Bourne-Again shell script, Unicode text, UTF-8 text executable
```

（CRLF なら `with CRLF line terminators` と出ます。今回は出なかったので別の原因）

---

## 3. テンプレートの注釈が、記事本文にそのまま表示された

> これは KururuCMS ではなく、この連載を載せているブログ側で起きたものです。
> 8日目に記録した罠を、自分で再発させました。

### 症状

記事の先頭に、書いた覚えのない文字列が出た。

```text
なる。 #}
```

### 原因

Django テンプレートの `{# #}` は**1行専用**です。
複数行に書くと、2行目以降がコメントとして扱われず本文に出ます。

8日目の記事でまったく同じ内容を書いています。
それでも再発したのは、**書いている最中は「これはコメント」と思っている**からで、
知識の有無の問題ではありませんでした。

### 直し方

```django
{% comment %}
複数行の注釈はこちらを使う。
{% endcomment %}
```

### 判断方法

知識で防げなかったので、テストで防ぐことにしました。

```python
def test_template_comment_does_not_leak_into_the_page(self):
    response = self.get(self.make_article(UBUNTU))
    html = response.content.decode()

    self.assertNotIn("#}", html)
```

### 学び

**同じ間違いを2回したら、それは覚え方の問題ではなく、
気づく仕組みが無いことの問題**です。

3回目を防ぐのは注意力ではなく、`#}` が出力に混ざったら落ちるテストです。
