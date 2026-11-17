# ローカル採点（ハーネス用の追加物）

このディレクトリは公式配布ツール（`Cargo.toml`、`src/`、`in/`、`README.md` など）に、次の2つを加えたものである。

- `score_case.py`：1ケースを採点するアダプタ。ハーネスの評価と `quickcheck.py` の両方から呼ばれる。
- `bin/gen`、`bin/vis`、`bin/tester`：公式ツールのビルド済みバイナリ。`cargo` で再ビルドする必要はない。

## 1ケースの採点：`score_case.py`

```sh
python3 score_case.py --binary ./solver --seed 0 --result result.json [--time-limit 2.0] [--save-dir DIR]
```

1. 公式の `bin/gen` で seed の入力を生成する。seed 0〜99 の入力は `in/0000.txt`〜`in/0099.txt` と同じ。
2. ソルバーを1回実行する。入力は標準入力から渡し、**壁時計時間**を計る。`--time-limit`（既定2.0秒）を超えたらTLE。
3. 公式の `bin/vis` で出力を検証し、採点する。
4. `--result` に次のJSONを書く。
   - 有効：`{"status":"ok","valid":true,"score":22,"elapsed_sec":...,"cpu_sec":...,"max_rss_mib":...}`
   - 無効：`{"status":"invalid","valid":false,"score":null,"reason":"TLE: ..."}`
     - 理由は `TLE`、`RE`（実行時エラー）、`MLE`（RSSが1024 MiB超）、`WA`（`vis` が出力を拒否、または非UTF-8）のいずれか。
     - 無効は0点ではない。たとえば何もしない出力 `0` は有効で、得点は壁の数 $M$ になる。
   - ツールが無いなど環境側で失敗したときは、JSONを**書かずに**非0で終了する。こうすることで、ソルバーの無効と区別できる。

`--save-dir DIR` を付けると、そのケースの `input.txt`、`output.txt`、`solver_stderr.txt`（末尾64KB）、`vis.html`、`summary.json` を `DIR` に残す。

## workerから使う場合

`python3 quickcheck.py --seed 0` が、コンパイル、このアダプタでの採点、スコア表示までをまとめて行う。許可されていないseedは拒否される。実行後はワークスペースの `judge_last/` に、直前のケースの入力・出力・stderr・`vis.html`・`summary.json`（実行時間を含む）が残る。

## 手動で使う場合

```sh
bin/gen seeds.txt --dir in2                  # seeds.txt の各行のseedから in2/0000.txt, ... を生成
./main < in/0000.txt > out.txt
bin/vis in/0000.txt out.txt                  # "Score = ..." を表示し、カレントに vis.html を書く
bin/tester ./main < in/0000.txt > out.txt    # 実行と採点を一度に行う（スコアは標準エラー出力）
```

`vis` は不正な出力に対して、エラーの行と `Score = 0` を表示する。
