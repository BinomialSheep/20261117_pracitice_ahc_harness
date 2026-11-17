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
| `AGENTS.md` | オーケストレーター向けの指示（ハーネス）。末尾にこのリポジトリ固有の注意を追記 |
| `HARNESS.md` | ハーネスのREADME（配布物の `README.md` を改名） |
| `config.json` | この問題用の設定（Git管理する） |
| `problem/statement.md` | 問題文。`問題文.html` から変換し、末尾にローカル評価の付記を加えた |
| `problem/statement.html` | 問題文の原本（元の `問題文.html`） |
| `problem/tools/` | 公式ツール一式、judgeアダプタ `score_case.py`、説明 `LOCAL_JUDGE.md` |
| `problem/tools/bin/` | 公式ツールのビルド済みバイナリ（Git管理外、`scripts/build_tools.sh` で生成） |
| `scripts/build_tools.sh` | 公式ツールをビルドして `problem/tools/bin/` に置く |
| `tests/test_problem.py` | judgeアダプタとハーネス接続のテスト |
| `thin/`, `scripts/quickcheck.py`, `tests/test_thin.py`, `docs/`, `examples/`, `templates/` | ハーネス本体（無改変） |
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
- **評価時間の目安**：制限時間いっぱい（1.8秒）まで探索するソルバーだと、1候補1000ケースで約31分かかる（候補内のケースは逐次実行）。Bラウンドは現bestと候補を順に測るので約1時間。Aラウンドは、現best 31分の後に10候補を8並列（2回に分かれる）で測るので約1.5時間。`evaluation.parallelism`（最大10）で調整できる。
- **評価の偏り**：ハーネスは現bestを単独で、候補を並列で採点する。そのため時間いっぱい探索する解法では、Aラウンドの候補がわずかに不利になる（昇格が保守的になる方向）。並列8で1.8秒のソルバーを動かしたときの実測時間は1.817秒で、TLEの誤判定は出なかった。

## worker の起動設定（まだ実行していない）

`config.json` の `workers.engines.claude` には次のフラグを付けている。

- `--safe-mode`：CLAUDE.md・MCP・skills・hooks を読み込まない。親ディレクトリの情報がworkerに伝わらないようにするため。
- `--permission-mode acceptEdits --permission-prompts none`：ファイル編集は許可する。許可リストにないコマンドは確認せずに拒否する。
- `--allowedTools`：`python3 quickcheck.py` と `g++` だけを許可する。Aでseed0以外を走らせないため。
- `--disallowedTools WebSearch WebFetch`：過去問のルールを守るため。

`claude -p` を実際に使ったworkerの実行は課金を伴うので、まだ試していない。最初はBラウンド1体などで動作を確かめ、それから10並列のAに進む。`codex` はこのマシンに入っていない。

## 進め方

[AGENTS.md](AGENTS.md) と [docs/SETUP.md](docs/SETUP.md) に沿って、オーケストレーターがA/Bラウンドを回す。概要は [HARNESS.md](HARNESS.md) を参照。

```sh
.venv/bin/python -m thin.cli status
.venv/bin/python -m thin.cli prepare A --ideas proposals.json      # または prepare B --idea '...'
.venv/bin/python -m thin.cli run-workers R0001 --engine claude     # 手作業なら --engine manual
.venv/bin/python -m thin.cli evaluate R0001
.venv/bin/python -m thin.cli promote R0001 A03                     # 改善したときだけ
.venv/bin/python -m thin.cli close R0001
```
