#!/usr/bin/env python3
"""トークン使用量を、ラウンド別・発生源別に集計する（読み取りだけ。--save のときだけ usage.json を書く）。

読む記録（集計の中身は thin/usage.py）:
- 対話セッション：Claude Code の ~/.claude/projects/<このリポジトリ>/*.jsonl（subagents/ を含む）と、
  Codex の ~/.codex/sessions/**/rollout-*.jsonl（cwd がこのリポジトリの中。runs/ を除く）
- worker：runs/R####/jobs/*/ の job.json の usage。無ければ codex_rollout.jsonl か agent.stdout

対話セッションの呼び出しは、ラウンドの作業のときだけそのラウンドに数える。条件は2つ。
1. そのラウンドの thin.cli コマンド（prepare〜close）を実行したセッションであること
2. 「prepare を実行したターンの開始」から「close を実行したターンの終わり」までの呼び出しであること
それ以外（ラウンドの合間の質問、ドキュメント整備、別セッションでの作業など）は「ラウンド外」に数え、
--outside でターンごとに見られる。

区分は in=キャッシュなし入力、cw=キャッシュ書き込み、cr=キャッシュ読み出し、out=出力（思考を含む）、
think=out のうち思考、ctx=1回の呼び出しで読んだ入力の最大値。ドル換算はしない。

    python3 scripts/token_report.py               # ラウンド×発生源の表、ラウンド外のセッション別合計、凡例
    python3 scripts/token_report.py --outside     # ラウンド外をターンごとに
    python3 scripts/token_report.py --jobs R0012  # そのラウンドの worker ごと
    python3 scripts/token_report.py --json        # 機械向け
    python3 scripts/token_report.py --save        # usage.json を書く（無いもの、確定していないもの）
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from thin import usage as U  # noqa: E402

KEYS = U.KEYS


def fmt(n):
    if not n:
        return "-" if n is None else "0"
    return f"{n / 1e6:.2f}M" if n >= 1e6 else (f"{n / 1e3:.0f}k" if n >= 1e3 else str(n))


def local(t):
    return t.astimezone().strftime("%m-%d %H:%M") if t else "?"


def collect():
    rs = U.rounds(ROOT)
    sess = U.sessions(ROOT)
    info = U.round_spans(rs, sess)
    calls = U.attribute(rs, sess, info)
    rows = collections.defaultdict(lambda: {"calls": 0, **{k: 0 for k in KEYS}, "peak_ctx": 0})
    notes = collections.defaultdict(list)
    grouped = collections.defaultdict(list)
    for rid, src, k, t, u in calls:
        grouped[(rid, src)].append(u)
    for key, us in grouped.items():
        rows[key] = U.total(us)
    jobs = []
    for r in rs:
        spans = collections.defaultdict(list)
        for jid, w in U.worker_rows(r["dir"]).items():
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
    # ラウンド外をターンごとに
    by = {s["source"]: s for s in sess}
    turns = collections.defaultdict(list)
    for rid, src, k, t, u in calls:
        if rid == U.OUTSIDE:
            turns[(by[src]["owner"], k)].append((t, u))
    outside = []
    for (owner, k), tu in turns.items():
        tl = by[owner]["turns"]
        start, prompt = tl[k] if 0 <= k < len(tl) else (min(t for t, _ in tu), "")
        outside.append({"session": owner, "start": start, "prompt": prompt, **U.total([u for _, u in tu])})
    outside.sort(key=lambda x: (x["start"] is None, x["start"]))
    legend = [(s["source"], s["first"], s["last"], s["title"] or "") for s in sess]
    return rs, info, rows, notes, legend, jobs, outside


def line(label, src, r, note=""):
    return (f"{label:<8}{src:<22}{r['calls'] or '-':>6}{fmt(r['in']):>8}{fmt(r['cw']):>8}{fmt(r['cr']):>9}"
            f"{fmt(r['out']):>8}{fmt(r['think']):>8}{fmt(r['peak_ctx'] or None):>7}  {note}")


def print_table(rs, info, rows, notes, legend):
    hdr = f"{'round':<8}{'source':<22}{'calls':>6}{'in':>8}{'cw':>8}{'cr':>9}{'out':>8}{'think':>8}{'ctx':>7}  note"
    print(hdr)
    print("-" * len(hdr))
    for r in rs:
        keys = sorted(k for k in rows if k[0] == r["id"])
        x = info[r["id"]]
        span = f"{local(x['begin'])}〜{local(x['end'])}"
        if not any(not k[1].startswith("worker:") for k in keys):
            span += " オーケストレーター不明"
        print(f"{r['id']} {r['mode']}  {span}")
        for _, src in keys:
            row = rows[(r["id"], src)]
            note = " ".join(([f"jobs={row['jobs']}"] if "jobs" in row else []) + notes.get((r["id"], src), []))
            if src == "worker:記録なし":
                print(f"{'':<8}{src:<22}{'-':>6}{'':>48}  {note}")
            else:
                print(line("", src, row, note))
    out = sorted(k for k in rows if k[0] == U.OUTSIDE)
    print(f"\n{U.OUTSIDE}（ラウンドの作業でない呼び出し。--outside でターンごと）")
    for _, src in out:
        print(line("", src, rows[(U.OUTSIDE, src)]))
    total = collections.defaultdict(collections.Counter)
    for (rid, src), r in rows.items():
        kind = ("ラウンド外" if rid == U.OUTSIDE else ("worker" if src.startswith("worker:") else "ラウンド内の対話"))
        total[kind].update({k: r[k] for k in ("calls",) + KEYS})
    print("\n合計（codex の worker の旧形式は呼び出し回数が分からない）")
    for kind, c in total.items():
        print(f"  {kind:<12} calls={c['calls']} " + " ".join(f"{k}={fmt(c[k])}" for k in KEYS))
    print("\n凡例")
    for src, first, last_, title in legend:
        print(f"  {src:<20} {str(first)[:16]} → {str(last_)[:16]}  {title}")


def main():
    if "--save" in sys.argv:
        for rid in U.save_snapshots(ROOT):
            print(f"wrote runs/{rid}/usage.json")
        return
    rs, info, rows, notes, legend, jobs, outside = collect()
    if "--json" in sys.argv:
        print(json.dumps({"rows": [{"round": k[0], "source": k[1], **v, "notes": notes.get(k, [])} for k, v in rows.items()],
                          "spans": {k: {**v, "owners": sorted(v["owners"])} for k, v in info.items()},
                          "workers": jobs, "outside": outside, "legend": legend}, ensure_ascii=False, indent=1, default=str))
    elif "--outside" in sys.argv:
        for o in outside:
            print(f"{local(o['start'])}  {o['session']:<18}{o['calls']:>4}回 cr={fmt(o['cr']):<7} out={fmt(o['out']):<6} "
                  f"ctx={fmt(o['peak_ctx']):<6} {o['prompt']}")
    elif "--jobs" in sys.argv:
        rid = sys.argv[sys.argv.index("--jobs") + 1]
        for j in jobs:
            if j["round"] == rid:
                u = j["usage"]
                head = f"{j['job']:<5}{j['engine'] or '?':<8}{j['outcome'] or '':<9}{j['minutes']:>6}分 "
                waits = f" 待つだけ={u['waits']} 時刻={u['clock_checks']}" if u and "waits" in u else ""
                print(head + (f"calls={u['calls'] or '-'} " + " ".join(f"{k}={fmt(u[k])}" for k in KEYS)
                              + f" ctx={fmt(u['peak_ctx'])}{waits}" if u else "記録なし"))
    else:
        print_table(rs, info, rows, notes, legend)


if __name__ == "__main__":
    main()
