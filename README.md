# AHC ハーネス実験 20261117

## 概要

with AI練習。
ここでは
https://www.youtube.com/watch?v=8HT49Qb9dYA
を基に作った「ahc_thin_harness_v0_1_0」

## 解く問題

https://atcoder.jp/contests/atcoder13live

## この実験のルール

- 過去問なので、**この問題の解法・解説・順位表・提出コードをWebで調べない**。一般的なアルゴリズムやライブラリを調べるのは構わない。
- worker にも同じルールを適用する。問題文の付記にこのルールを書いてあり、`claude` engine では WebSearch と WebFetch を無効にしている。

## 構成

ハーネス（ahc_thin_harness v0.1.0）をリポジトリ直下に展開し、`problem/` にこの問題をつないだ。

| パス | 内容 |
|---|---|
| `AGENTS.md` | オーケストレーター向けの指示。毎回読み込まれるので、行動に必要なことだけを書く |
| `HARNESS.md` | ハーネスのREADME（配布物の `README.md` を改名） |
| `config.json` | この問題用の設定（Git管理する） |
| `problem/statement.md` | 問題文。`問題文.html` から変換し、末尾にローカル評価の付記を加えた |
| `problem/statement.html` | 問題文の原本（元の `問題文.html`） |
| `problem/tools/` | 公式ツール一式、judgeアダプタ `score_case.py`、説明 `LOCAL_JUDGE.md` |
| `problem/tools/bin/` | 公式ツールのビルド済みバイナリ（Git管理外、`scripts/build_tools.sh` で生成） |
| `scripts/build_tools.sh` | 公式ツールをビルドして `problem/tools/bin/` に置く |
| `tests/test_problem.py` | judgeアダプタとハーネス接続のテスト |
| `docs/TEMPLATE_FEEDBACK.md` | 雛形作成担当に渡す、問題によらないフィードバック |
| `thin/`, `scripts/quickcheck.py`, `tests/test_thin.py`, `docs/` の他の文書, `examples/`, `templates/` | ハーネス本体（無改変） |
| `FILE_MANIFEST.json` | ハーネス v0.1.0 配布時のハッシュ一覧。展開後の変更は反映していない |
| `runs/`, `best/` | ラウンド実行時に作られる（Git管理外） |

## セットアップ（クローン直後に1回）

```sh
uv venv --python 3.12 .venv      # ハーネスは Python 3.11 以上が前提。このマシンの python3 は 3.10
scripts/build_tools.sh            # 公式ツール（Rust）をビルドして problem/tools/bin/ に置く
.venv/bin/python -m unittest discover -s tests -v   # 25件
.venv/bin/python -m thin.cli demo
```

ハーネスの文書にある `python3 -m thin.cli ...` は、このリポジトリでは `.venv/bin/python -m thin.cli ...` と読み替える。
（システムの Python 3.10 でも25件のテストは通るが、ハーネスが前提とするバージョンに合わせている。）

## 問題とのつなぎ方

- **judge**：`problem/tools/score_case.py` が1ケースを採点する。
  1. 公式の `gen` で入力を作る
  2. ソルバーを実行し、壁時計時間2.0秒を超えたらTLEにする
  3. 公式の `vis` で検証・採点する

  無効（TLE・RE・MLE・WA）と環境エラーは区別して扱う。詳しくは [problem/tools/LOCAL_JUDGE.md](problem/tools/LOCAL_JUDGE.md)。
- **スコア**：1ケースの得点（最大650）を `maximize`・`paired_difference` で比べる。
- **コンパイル**：`g++ -std=gnu++23 -O2 -DONLINE_JUDGE -DATCODER`。AtCoderに合わせて `-DNDEBUG` は付けない（`assert` が有効）。AtCoder Library はローカルに無い。
- **seed**：ラウンド r の評価には seed `1000r`〜`1000r+999` を使う。workerのdebug seedは、Aが0だけ、Bが0〜9。
- **評価時間の目安**：制限時間いっぱい（1.8秒）まで探索するソルバーだと、1候補1000ケースで約31分かかる（候補内のケースは逐次実行）。Bラウンドは現bestと候補を順に測るので約1時間。Aラウンドは、現best 31分の後に10候補を10並列（1回）で測るので約1時間。`evaluation.parallelism`（最大10）で調整できる。CPUは16コア32スレッドなので、R0002から8並列を10並列にした。
- **評価の偏り**：ハーネスは現bestを単独で、候補を並列で採点する。そのため時間いっぱい探索する解法では、Aラウンドの候補がわずかに不利になる（昇格が保守的になる方向）。並列8で1.8秒のソルバーを動かしたときの実測時間は1.817秒で、TLEの誤判定は出なかった。

## worker の起動設定（まだ実行していない）

`config.json` の `workers.engines.claude` には次のフラグを付けている。

- `--model claude-opus-5-5`：workerのモデルを個人の設定（`~/.claude/settings.json`）に左右させないため。このモデルには Claude Code 2.1.280 以上が必要。端末の `claude`（2.1.260、自動更新オフ）では使えないので、`run-workers` は VS Code 拡張に同梱のCLIを PATH の先頭に置いて実行している（端末のCLIを更新すれば不要）。

  ```sh
  PATH="$(ls -d ~/.vscode-server/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary | sort -V | tail -1):$PATH" \
    .venv/bin/python -m thin.cli run-workers R0001 --engine claude
  ```
- `--effort high`：effortを個人の設定に左右させず、サブスクの利用上限を節約するため（R0003から）。
- `--safe-mode`：CLAUDE.md・MCP・skills・hooks・自動メモリを読み込まない。親ディレクトリの情報がworkerに伝わらないようにするため。workerと同じ構成で何も読み込まれないことは確認済み（[docs/TEMPLATE_FEEDBACK.md](docs/TEMPLATE_FEEDBACK.md) の8）。
- `--permission-mode acceptEdits --permission-prompts none`：ファイル編集は許可する。許可リストにないコマンドは確認せずに拒否する。
- `--allowedTools`：`python3 quickcheck.py` と `g++` だけを許可する。Aでseed0以外を走らせないため。
- `--disallowedTools WebSearch WebFetch`：過去問のルールを守るため。

`claude -p` を実際に使ったworkerの実行は課金を伴うので、まだ試していない。最初はBラウンド1体などで動作を確かめ、それから10並列のAに進む。`codex` はこのマシンに入っていない。

## 進め方

オーケストレーターは [AGENTS.md](AGENTS.md) に沿ってA/Bラウンドを回す。ハーネスの全体像は [HARNESS.md](HARNESS.md)、細かい運用は [docs/OPERATIONS.md](docs/OPERATIONS.md) にある。

```sh
.venv/bin/python -m thin.cli status
.venv/bin/python -m thin.cli prepare A --ideas proposals.json      # または prepare B --idea '...'
.venv/bin/python -m thin.cli run-workers R0001 --engine claude     # 手作業なら --engine manual
.venv/bin/python -m thin.cli evaluate R0001
.venv/bin/python -m thin.cli promote R0001 A03                     # 改善したときだけ
.venv/bin/python -m thin.cli close R0001
```
