# AHC ハーネス実験 20261117

## 解く問題

https://atcoder.jp/contests/atcoder13live

## 人間による説明

with AI練習。
ここでは
https://www.youtube.com/watch?v=8HT49Qb9dYA
を基に作った「ahc_thin_harness_v0_1_0」の試し切りと、その改善を目的としている。

### 結果

- SNAPSHOT_2026-11-18.html：現時点の解法
- HUMAN_MEMO.md：人間によるメモ
- TEMPLATE_FEEDBACK.md：ハーネス改善に向けたフィードバック

---

以降はAIが勝手に書いてるもの。

## この実験のルール

- 過去問なので、**この問題の解法・解説・順位表・提出コードをWebで調べない**。一般的なアルゴリズムやライブラリを調べるのは構わない。
- worker にも同じルールを適用する。問題文の付記にこのルールを書いてあり、`claude` engine では WebSearch と WebFetch を無効にしている。

## 構成

ハーネス（ahc_thin_harness v0.1.0）をリポジトリ直下に展開し、`problem/` にこの問題をつないだ。

| パス                                                                                                  | 内容                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AGENTS.md`                                                                                           | オーケストレーター向けの指示。毎回読み込まれるので、行動に必要なことだけを書く                                                                                                                                                                                                                                                                                                                                          |
| `HARNESS.md`                                                                                          | ハーネスのREADME（配布物の `README.md` を改名）                                                                                                                                                                                                                                                                                                                                                                         |
| `config.json`                                                                                         | この問題用の設定（Git管理する）                                                                                                                                                                                                                                                                                                                                                                                         |
| `problem/statement.md`                                                                                | 問題文。`問題文.html` から変換し、末尾にローカル評価の付記を加えた                                                                                                                                                                                                                                                                                                                                                      |
| `problem/statement.html`                                                                              | 問題文の原本（元の `問題文.html`）                                                                                                                                                                                                                                                                                                                                                                                      |
| `problem/tools/`                                                                                      | 公式ツール一式、judgeアダプタ `score_case.py`、説明 `LOCAL_JUDGE.md`                                                                                                                                                                                                                                                                                                                                                    |
| `problem/tools/bin/`                                                                                  | 公式ツールのビルド済みバイナリ（Git管理外、`scripts/build_tools.sh` で生成）                                                                                                                                                                                                                                                                                                                                            |
| `scripts/build_tools.sh`                                                                              | 公式ツールをビルドして `problem/tools/bin/` に置く                                                                                                                                                                                                                                                                                                                                                                      |
| `scripts/codex_limits.py`, `scripts/codex_audit.py`                                                   | Codex の利用上限を読む／codex worker の行動を監査する                                                                                                                                                                                                                                                                                                                                                                   |
| `scripts/token_report.py`, `thin/usage.py` | トークン使用量をラウンド別・発生源別に集計する（読み取りだけ）。worker ごとの記録と、close 時の `runs/R####/usage.json` も `thin/usage.py` が作る |
| `tests/test_problem.py`                                                                               | judgeアダプタとハーネス接続のテスト                                                                                                                                                                                                                                                                                                                                                                                     |
| `docs/TEMPLATE_FEEDBACK.md`                                                                           | 雛形作成担当に渡す、問題によらないフィードバック                                                                                                                                                                                                                                                                                                                                                                        |
| `thin/`, `scripts/quickcheck.py`, `tests/test_thin.py`, `docs/` の他の文書, `examples/`, `templates/` | ハーネス本体。評価をケース単位で並列化するため、`thin/scoring.py`・`thin/config.py`・`tests/test_thin.py` を変更した（R0003から）。コマンドを制限できない codex の worker のため、`thin/core.py` の task.md に「採点は quickcheck.py だけで行う」の1行を足した（R0007から）。codex が親ディレクトリの `AGENTS.md` を読みにいくので、各作業場所に短い `AGENTS.md` を置き、task.md に外を読まない1行を足した（R0009から）。トークンを記録するため `thin/usage.py` を足し、`thin/core.py` の worker 終了時と close に記録を加えた（R0012から）。codex の worker が10秒ほどかかる quickcheck を1秒ごとに見に行き、結果を取りに行くだけの呼び出しが5時間枠の消費の約2割を占めたので、task.md に長いコマンドを1回で待つ1行を足し、`scripts/quickcheck.py` が実行時間と残り時間（run-workers が `worker_config.json` に書く締め切りから）を出すようにした（R0013から） |
| `FILE_MANIFEST.json`                                                                                  | ハーネス v0.1.0 配布時のハッシュ一覧。展開後の変更は反映していない                                                                                                                                                                                                                                                                                                                                                      |
| `runs/`, `best/`                                                                                      | ラウンド実行時に作られる（Git管理外）                                                                                                                                                                                                                                                                                                                                                                                   |

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
- **評価時間の目安**：現bestと全候補のケースを1つの待ち行列に混ぜ、`evaluation.parallelism` 本ずつ並列に採点する（R0003から。それまでは候補内のケースを1つずつ実行していた）。並列度は12にしている（CPUは16コア32スレッド）。1.8秒使い切るソルバーで、Bラウンド（2000ケース）は約5分、Aラウンド（11000ケース）は約27分。
- **評価の偏り**：現bestと候補のケースは交互に並ぶので、同じ負荷で採点される。1.77秒使うソルバーを12並列・16並列で動かしても、実測時間は単独のときと同じ（最大1.767秒）で、TLEの誤判定は出なかった。

## worker の起動設定

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
- `--output-format stream-json --verbose`：トークンを記録するため（R0012から）。`agent.stdout` は、API呼び出しごとの usage と利用上限の使用率（`rate_limit_event`）を含む JSONL になる。最終メッセージは `agent.last_message.md` に書き出す。

R0001（Bラウンド1体）で動作を確かめ、R0002から10並列のAも使っている。サブスクの利用上限に注意する（[docs/TEMPLATE_FEEDBACK.md](docs/TEMPLATE_FEEDBACK.md) の9）。

`workers.engines.codex`（Codex CLI 0.169.1、ChatGPTのPlusプランでログイン）には次のフラグを付けている。R0006から使う。

- `--ignore-user-config`：個人の `~/.codex/config.toml` を読まない。認証はそのまま使える。
- `-m gpt-6.2-sol`、`-c model_reasoning_effort="high"`：モデルとeffortを固定する。不正な値は終了コード1で止まる。
- `-c web_search="disabled"` と `--disable apps plugins remote_plugin browser_use browser_use_external in_app_browser`（実際は1つずつ `--disable` を付ける）：Webに届く道具を外す。`web_search` を切るだけでは、ChatGPTの連携アプリ（`codex_apps` のMCP）の検索で調べられた。全部付けると、モデルは「Webの道具が無い」と答えた。
- `--disable multi_agent`：効果は確かめていない。セッション記録のツール一覧には `spawn_agent` などが残った。
- `--disable memories`：過去のセッションの要約を次の worker に渡さないため。既定でも無効だが、セッション記録を残すようにしたので明示した（R0012から）。
- `--sandbox workspace-write`：書き込めるのは workspace と `/tmp` だけで、ネットワークも使えない（`codex sandbox` で確認済み）。読み取りはディスク全体でできる。
- `--ephemeral` は外した（R0012から）。付けると、20分の上限で止められた worker のトークンが何も残らない。worker が終わると、`run-workers` がそのセッション記録を `~/.codex/sessions` から `jobs/<id>/codex_rollout.jsonl` へ移す。ただし Codex の SQLite（`~/.codex/state_5.sqlite` と `thread_history_1.sqlite`）には、スレッドのタイトル（task.md の冒頭）と中身が残る。worker は読み取りを制限されないので読もうと思えば読めるが、`runs/` も同じく読める。
- `--json`：行動のイベント列を `agent.stdout` に残す。

worker と同じ形（`git init` した workspace）では、リポジトリの `AGENTS.md` は渡らない。リポジトリ直下から起動すると渡る。どちらもセッション記録（`~/.codex/sessions`）で確認した。

claude の `--allowedTools` に当たるコマンド制限は無い。seed0だけ（A）という制限は task.md の指示だけなので、`run-workers` のあとに監査する。

```sh
python3 scripts/codex_audit.py R0006             # 終了状態・エラー・トークン・許可外seedや公式ツールの直接実行など
python3 scripts/codex_audit.py R0006 --commands  # 全コマンドも表示
python3 scripts/codex_limits.py                  # 5時間枠と週間枠の使用率（読み取りだけ）
```

`codex_limits.py` は `codex app-server` に読み取りのメソッドしか送らない。リセット権を消費するメソッドは送れないようにしてある。

### トークンの記録

R0012 から、どちらの engine でも worker のトークンが呼び出しごとに残る。

- `job.json`：engine・モデル・effort と `usage`（呼び出し回数、区分ごとのトークン、最大の文脈、利用上限の使用率の始めと終わり。codex は、実行中のコマンドを待つだけの呼び出し `waits` と時刻を見るだけの呼び出し `clock_checks` の回数も）
- `runs/R####/usage.json`：close のときに、そのラウンドのオーケストレーターと worker の消費を書く。`~/.claude` の記録は既定で30日で消えるため。close のあとの報告を含めるため、次のラウンドの close のときに確定する（`final`）
- 対話セッションの呼び出しは、ラウンドの作業のときだけ、そのラウンドに数える。そのラウンドの `thin.cli` コマンドを実行したセッションで、「prepare を実行したターンの開始」から「close を実行したターンの終わり」までの呼び出しが対象。そのラウンドのために始めたセッション（それより前のラウンドを実行していないセッション）は、最初のターンから数える。それ以外（ラウンドの合間の相談、ドキュメント整備、別セッションの作業）は「ラウンド外」に数える
- 区分は in（キャッシュなし入力）・cw（キャッシュ書き込み）・cr（キャッシュ読み出し）・out（出力、思考を含む）・think（そのうち思考）。ドル換算はしない

```sh
python3 scripts/token_report.py               # ラウンド×発生源の表
python3 scripts/token_report.py --jobs R0012  # worker ごと
python3 scripts/token_report.py --outside     # ラウンド外をターンごとに
python3 scripts/token_report.py --save        # usage.json を書く（無いもの、確定していないもの）
```

R0001〜R0012 の集計結果と、R0012 の worker の消費の内訳は [docs/レポート/トークン計測レポート.html](docs/レポート/トークン計測レポート.html) にある。

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
