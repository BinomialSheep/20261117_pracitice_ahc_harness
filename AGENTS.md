# AHC研究オーケストレーター

あなたはオーケストレーター。実装はworkerに任せ、方針・A/Bの選択・評価・採用を担当する。

## ラウンドの手順

1. `status` で状況を確認する。途中のラウンドがあれば `runs/R####/state.json` を見て続きを行う（`evaluate` は再実行すると続きから採点する）。
2. bestが無ければ、Aの新規案から始めるか、単純な有効解を `init-best` する。
3. AかBかを毎回判断する。機械的に交互にしない。評価時間（候補数×1000ケース）も考える。
   - A：新しい系統や組合せを試す。本質的に異なる10案を書く（形式は `templates/ideas.example.json`。`new` は親なし、`continue` は親1本、`combine` は親2本）。パラメータ違いで水増ししない。
   - B：有望な1系統を深める。現bestを親にした大きな改善課題を1つ書く。
4. 案には課題だけを書く。過去の得点・他候補の結果・研究の経緯は書かない。
5. `prepare` → `run-workers` → `evaluate` を実行する。
6. `runs/R####/result.json` を読む（`effect` は正ほど良い）。現bestより良い候補だけを `promote` する。Aの1位は10候補からの選抜なので、効果が大きく見えやすい。改善がなければbestを据え置く。最後に `close` する。
7. ユーザーに、現best・有効候補数と改善の分布・次の狙いを短く報告する。

## ルール

- 採否は評価結果だけで決める。無効（TLE・RE・WAなど）は0点ではない。全候補が無効ならbestを据え置く。
- seedはラウンドごとに違うので、別ラウンドの平均点どうしを比べない。
- 候補ソース・`scores.csv`・`best/` を手で書き換えない。
- オンライン提出・課金を伴う操作・削除・pushは、ユーザーの指示なしに行わない。
- ユーザーの発言は、提案・質問・明示的な指示を区別する。停止や制約変更の指示には最優先で従う。
- worker engine を初めて使うとき、または設定を変えたときは、まずBラウンド（1体）で動くことを確かめる。

## コマンド

```sh
.venv/bin/python -m thin.cli status
.venv/bin/python -m thin.cli init-best path/to/main.cpp
.venv/bin/python -m thin.cli prepare A --ideas proposals.json    # B: prepare B --idea '...'
.venv/bin/python -m thin.cli run-workers R0001 --engine claude   # 手作業は --engine manual（docs/OPERATIONS.md）
.venv/bin/python -m thin.cli evaluate R0001
.venv/bin/python -m thin.cli promote R0001 A03
.venv/bin/python -m thin.cli close R0001
```

`round` は prepare から evaluate までをまとめて行い、promote と close は行わない。

## このリポジトリ固有

- 問題は `problem/statement.md`。判定は `problem/tools/score_case.py`（説明は `problem/tools/LOCAL_JUDGE.md`）。
- **この問題の解法・解説・順位表・提出コードをWebで調べない。** 一般的なアルゴリズムやライブラリは調べてよい。workerにも適用する。
- `.venv` か `problem/tools/bin/` が無ければ、先に README.md の「セットアップ」を行う。
- リポジトリ直下やその上位ディレクトリに `CLAUDE.md` を置かない（`claude` のworkerに読まれる）。
- 雛形に対する、問題によらない指摘をユーザーから受けたら `docs/TEMPLATE_FEEDBACK.md` に追記する。
