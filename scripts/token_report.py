#!/usr/bin/env python3
"""トークン使用量を、ラウンド別・発生源別に集計する（読み取りだけ。--save のときだけ usage.json を書く）。

読む記録（集計の中身は thin/usage.py）:
- 対話セッション（オーケストレーターなど）
  - Claude Code: ~/.claude/projects/<このリポジトリ>/*.jsonl と <セッション>/subagents/*.jsonl
  - Codex: ~/.codex/sessions/**/rollout-*.jsonl のうち、cwd がこのリポジトリの中（runs/ を除く）のもの
- worker: runs/R####/jobs/*/
  - job.json の usage（run-workers が終了時に書く）。無ければ次から読む
  - codex_rollout.jsonl（codex の呼び出しごとの記録。run-workers が ~/.codex/sessions から移す）
  - agent.stdout（claude の stream-json、codex の --json。claude のテキスト出力は「記録なし」）

対話セッションの消費は時刻でラウンドに割り当てる。R(n) の区間は「R(n-1) を close してから R(n) を close するまで」。
区分は in=キャッシュなし入力、cw=キャッシュ書き込み、cr=キャッシュ読み出し、out=出力（思考を含む）、think=out のうち思考、
ctx=1回の呼び出しで読んだ入力の最大値。ドル換算はしない。

    python3 scripts/token_report.py               # ラウンド×発生源の表と、セッションの凡例
    python3 scripts/token_report.py --jobs R0009  # そのラウンドの worker ごと
    python3 scripts/token_report.py --json        # 機械向け
    python3 scripts/token_report.py --save        # usage.json の無い閉じたラウンドに書き出す（close は自動で書く）
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from thin import usage as U  # noqa: E402
from thin.util import write_json  # noqa: E402

KEYS = U.KEYS


def collect():
    rs = U.rounds(ROOT)
    rows = collections.defaultdict(lambda: {"calls": 0, **{k: 0 for k in KEYS}, "peak_ctx": 0})
    notes = collections.defaultdict(list)
    legend = []
    for s in U.sessions(ROOT):
        by_round = collections.defaultdict(list)
        for t, u in s["calls"]:
            by_round[U.round_of(t, rs)].append(u)
        for rid, us in by_round.items():
            rows[(rid, s["source"])] = U.total(us)
        legend.append((s["source"], s["first"], s["last"], s["title"] or ""))
    jobs = []
    for r in rs:
        workers = U.worker_rows(r["dir"])
        spans = collections.defaultdict(list)
        for jid, w in workers.items():
            jobs.append({"round": r["id"], "job": jid, **w})
            src = f"worker:{w['engine']}" if w["usage"] else "worker:記録なし"
            row = rows[(r["id"], src)]
            row["jobs"] = row.get("jobs", 0) + 1
            if w["usage"]:
                u = w["usage"]
                row["calls"] += u["calls"] or 0
                for k in KEYS:
                    row[k] += u[k]
                row["peak_ctx"] = max(row["peak_ctx"], u["peak_ctx"] or 0)
                spans[src] += u.get("limits") or []
        for src, sp in spans.items():
            for s in U.merge_spans(sp):
                notes[(r["id"], src)].append(f"{s['window']} {s['first']:.0f}→{s['last']:.0f}%")
    return rs, rows, notes, legend, jobs


def fmt(n):
    if not n:
        return "-" if n is None else "0"
    return f"{n / 1e6:.2f}M" if n >= 1e6 else (f"{n / 1e3:.0f}k" if n >= 1e3 else str(n))


def print_table(rs, rows, notes, legend):
    order = {r["id"]: i + 1 for i, r in enumerate(rs)}
    modes = {r["id"]: r["mode"] for r in rs}
    key = lambda k: (order.get(k[0], 0 if k[0] == "(準備)" else 10**6), k[1])
    hdr = f"{'round':<8}{'source':<22}{'calls':>6}{'in':>8}{'cw':>8}{'cr':>9}{'out':>8}{'think':>8}{'ctx':>7}  note"
    print(hdr)
    print("-" * len(hdr))
    last, total = None, collections.defaultdict(collections.Counter)
    for rid, src in sorted(rows, key=key):
        r = rows[(rid, src)]
        note = " ".join(([f"jobs={r['jobs']}"] if "jobs" in r else []) + notes.get((rid, src), []))
        label = f"{rid} {modes.get(rid, '')}".strip() if rid != last else ""
        if src == "worker:記録なし":
            print(f"{label:<8}{src:<22}{'-':>6}{'':>48}  {note}")
        else:
            print(f"{label:<8}{src:<22}{r['calls'] or '-':>6}{fmt(r['in']):>8}{fmt(r['cw']):>8}{fmt(r['cr']):>9}"
                  f"{fmt(r['out']):>8}{fmt(r['think']):>8}{fmt(r['peak_ctx'] or None):>7}  {note}")
        last = rid
        kind = src.split(":")[0] + (":sub" if src.endswith("/sub") else "")
        total[kind].update({k: r[k] for k in ("calls",) + KEYS})
    print("\n合計（codex の worker は呼び出し回数が分からない分を含まない）")
    for kind, c in sorted(total.items()):
        print(f"  {kind:<12} calls={c['calls']} " + " ".join(f"{k}={fmt(c[k])}" for k in KEYS))
    print("\n凡例")
    for src, first, last_, title in legend:
        print(f"  {src:<20} {str(first)[:16]} → {str(last_)[:16]}  {title}")


def main():
    rs, rows, notes, legend, jobs = collect()
    if "--save" in sys.argv:
        for r in rs:
            p = r["dir"] / "usage.json"
            if r["closed"] and not p.exists():
                write_json(p, U.round_snapshot(ROOT, r["id"]))
                print(f"wrote {p.relative_to(ROOT)}")
    elif "--json" in sys.argv:
        print(json.dumps({"rows": [{"round": k[0], "source": k[1], **v, "notes": notes.get(k, [])} for k, v in rows.items()],
                          "workers": jobs, "legend": legend}, ensure_ascii=False, indent=1, default=str))
    elif "--jobs" in sys.argv:
        rid = sys.argv[sys.argv.index("--jobs") + 1]
        for j in jobs:
            if j["round"] == rid:
                u = j["usage"]
                head = f"{j['job']:<5}{j['engine'] or '?':<8}{j['outcome'] or '':<9}{j['minutes']:>6}分 "
                print(head + (f"calls={u['calls'] or '-'} " + " ".join(f"{k}={fmt(u[k])}" for k in KEYS)
                              + f" ctx={fmt(u['peak_ctx'])}" if u else "記録なし"))
    else:
        print_table(rs, rows, notes, legend)


if __name__ == "__main__":
    main()
