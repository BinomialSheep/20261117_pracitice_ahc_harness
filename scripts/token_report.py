#!/usr/bin/env python3
"""トークン使用量を、ラウンド別・発生源別に集計する（読み取りだけ）。

読む記録:
- 対話セッション（オーケストレーターなど）
  - Claude Code: ~/.claude/projects/<このリポジトリ>/*.jsonl と <セッション>/subagents/*.jsonl
  - Codex: ~/.codex/sessions/**/rollout-*.jsonl のうち、cwd がこのリポジトリの中のもの
- worker: runs/R####/jobs/*/agent.stdout
  - codex exec --json（turn.completed の usage。途中で止められた worker には残らない）
  - claude -p --output-format stream-json --verbose（API呼び出しごとの usage と利用上限の使用率）
  - claude -p のテキスト出力（usage が無いので「記録なし」に数える）

対話セッションの消費は時刻でラウンドに割り当てる。R(n) の区間は「R(n-1) を close してから R(n) を close するまで」。
トークンの区分は両 engine で揃える。in=キャッシュなし入力、cw=キャッシュ書き込み、cr=キャッシュ読み出し、
out=出力（思考を含む）、think=out のうち思考。Codex の input_tokens はキャッシュ分を含むので、差し引いて in にする。
ctx は1回の呼び出しで読んだ入力（in+cw+cr）の最大値。ドル換算はしない。

    python3 scripts/token_report.py               # ラウンド×発生源の表と、セッションの凡例
    python3 scripts/token_report.py --jobs R0009  # そのラウンドの worker ごと
    python3 scripts/token_report.py --json        # 機械向け
"""
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_DIR = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(ROOT))
CODEX_DIR = Path.home() / ".codex" / "sessions"
KEYS = ("in", "cw", "cr", "out", "think")


def ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return dt.datetime.fromisoformat(s[:19] + "+00:00")


def lines(path):
    with open(path, errors="replace") as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def claude_usage(u):
    return {"in": u.get("input_tokens", 0) or 0, "cw": u.get("cache_creation_input_tokens", 0) or 0,
            "cr": u.get("cache_read_input_tokens", 0) or 0, "out": u.get("output_tokens", 0) or 0,
            "think": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0}


def codex_usage(u):
    cached = u.get("cached_input_tokens", 0) or 0
    return {"in": (u.get("input_tokens", 0) or 0) - cached, "cw": u.get("cache_write_input_tokens", 0) or 0,
            "cr": cached, "out": u.get("output_tokens", 0) or 0, "think": u.get("reasoning_output_tokens", 0) or 0}


def claude_calls(path):
    """API呼び出しごとの (時刻, usage)。1つの応答が content block ごとに複数行になるので message.id で重複を除く。"""
    calls, meta = {}, {"title": None, "first": None, "last": None}
    for d in lines(path):
        t = d.get("timestamp")
        if t:
            meta["first"] = meta["first"] or t
            meta["last"] = t
        if d.get("type") == "ai-title":
            meta["title"] = d.get("aiTitle")
        m = d.get("message")
        if d.get("type") != "assistant" or not isinstance(m, dict) or not m.get("usage"):
            continue
        if m.get("model") == "<synthetic>":
            continue
        calls.setdefault(m.get("id") or d.get("uuid"), (ts(t), claude_usage(m["usage"])))
    return list(calls.values()), meta


def codex_rollout_calls(path):
    """rollout の token_count（累積）の差分を、呼び出しごとの usage として返す。"""
    calls, prev, meta = [], None, {}
    for d in lines(path):
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        if d.get("type") == "session_meta":
            meta = {"cwd": p.get("cwd", ""), "originator": p.get("originator"), "first": d.get("timestamp")}
        if p.get("type") != "token_count" or not p.get("info"):
            continue
        meta["last"] = d.get("timestamp")
        total = codex_usage(p["info"]["total_token_usage"])
        if prev is None:
            delta = total
        else:
            delta = {k: total[k] - prev[k] for k in KEYS}
            if any(v < 0 for v in delta.values()):
                delta = codex_usage(p["info"].get("last_token_usage") or {})
        prev = total
        if any(delta.values()):
            calls.append((ts(d.get("timestamp")), delta))
    return calls, meta


def worker_usage(jdir):
    """(usage合計 or None, 呼び出し数, 利用上限の観測 [(窓, resetsAt, 使用率)])。"""
    out = jdir / "agent.stdout"
    if not out.exists():
        return None, 0, []
    usage, calls, limits, seen, kind = collections.Counter(), 0, [], set(), None
    for d in lines(out):
        t = d.get("type")
        if t == "turn.completed":  # codex exec --json
            kind = "codex"
            usage.update(codex_usage(d.get("usage", {})))
        elif t == "assistant" and isinstance(d.get("message"), dict) and d["message"].get("usage"):
            kind = "claude"
            mid = d["message"].get("id")
            if mid not in seen:
                seen.add(mid)
                calls += 1
                usage.update(claude_usage(d["message"]["usage"]))
        elif t == "rate_limit_event":
            for name, w in ((d.get("rate_limit_info") or {}).get("unifiedWindows") or {}).items():
                if w.get("utilization") is not None:
                    limits.append((name, w.get("resetsAt"), w["utilization"]))
    if kind is None:
        return None, 0, limits
    return dict(usage), calls, limits


def rounds():
    rs = []
    for rd in sorted((ROOT / "runs").glob("R[0-9]*")):
        if (rd / "plan.json").exists() and (rd / "state.json").exists():
            plan, state = json.loads((rd / "plan.json").read_text()), json.loads((rd / "state.json").read_text())
            rs.append({"id": rd.name, "mode": plan["mode"], "created": ts(plan["created_at"]),
                       "closed": ts(state.get("closed_at")), "dir": rd})
    return rs


def round_of(t, rs):
    if t is None or not rs:
        return "(不明)"
    if t < rs[0]["created"]:
        return "(準備)"
    for r in rs:
        if r["closed"] is None or t <= r["closed"]:
            return r["id"]
    return "(次のラウンド)"


def collect():
    rs = rounds()
    rows = collections.defaultdict(lambda: {"calls": 0, "ctx": 0, **{k: 0 for k in KEYS}})
    legend, notes = [], collections.defaultdict(collections.Counter)

    def add(rid, source, usage, ctx=0, calls=1):
        r = rows[(rid, source)]
        r["calls"] += calls
        r["ctx"] = max(r["ctx"], ctx)
        for k in KEYS:
            r[k] += usage.get(k, 0)

    if CLAUDE_DIR.exists():
        for f in sorted(CLAUDE_DIR.glob("*.jsonl")):
            sid = f.stem[:8]
            calls, meta = claude_calls(f)
            subs = sorted((CLAUDE_DIR / f.stem / "subagents").glob("*.jsonl"))
            for t, u in calls:
                add(round_of(t, rs), f"claude:{sid}", u, u["in"] + u["cw"] + u["cr"])
            for sf in subs:
                for t, u in claude_calls(sf)[0]:
                    add(round_of(t, rs), f"claude:{sid}/sub", u, u["in"] + u["cw"] + u["cr"])
            legend.append((f"claude:{sid}", meta["first"], meta["last"],
                           (meta["title"] or "") + (f"（サブエージェント{len(subs)}本）" if subs else "")))
    if CODEX_DIR.exists():
        for f in sorted(CODEX_DIR.rglob("rollout-*.jsonl")):
            with open(f, errors="replace") as fh:
                head = fh.readline()
            if str(ROOT) not in head:  # 1行目の session_meta に cwd がある
                continue
            calls, meta = codex_rollout_calls(f)
            if not meta.get("cwd", "").startswith(str(ROOT)):
                continue
            sid = f.stem.split("-")[-1][:8]  # UUIDv7 の先頭は時刻なので、末尾のグループを使う
            for t, u in calls:
                add(round_of(t, rs), f"codex:{sid}", u, u["in"] + u["cw"] + u["cr"])
            rel = meta["cwd"][len(str(ROOT)):] or "/"
            legend.append((f"codex:{sid}", meta.get("first"), meta.get("last"), f"{meta.get('originator')} {rel}"))
    jobs = []
    for r in rs:
        limits = []
        for jdir in sorted((r["dir"] / "jobs").glob("*")):
            usage, calls, lim = worker_usage(jdir)
            limits += lim
            job = json.loads((jdir / "job.json").read_text()) if (jdir / "job.json").exists() else {}
            engine = "codex" if usage is not None and calls == 0 else ("claude" if usage is not None else "?")
            jobs.append({"round": r["id"], "job": jdir.name, "engine": engine, "calls": calls, "usage": usage,
                         "outcome": job.get("agent_outcome"), "minutes": round(job.get("agent_run", {}).get("seconds", 0) / 60, 1)})
            src = f"worker:{engine}" if usage is not None else "worker:記録なし"
            add(r["id"], src, usage or {}, 0, calls)
            notes[(r["id"], src)]["jobs"] += 1
        spans = collections.defaultdict(list)
        for name, reset, u in limits:
            spans[(name, reset)].append(u)
        for (name, reset), v in spans.items():
            notes[(r["id"], "worker:claude")][f"{name} {min(v) * 100:.0f}→{max(v) * 100:.0f}%"] += 1
    return rs, rows, legend, notes, jobs


def fmt(n):
    if n is None:
        return "-"
    return f"{n / 1e6:.2f}M" if n >= 1e6 else (f"{n / 1e3:.0f}k" if n >= 1e3 else str(n))


def print_table(rs, rows, legend, notes):
    order = [r["id"] for r in rs]
    modes = {r["id"]: r["mode"] for r in rs}
    key = lambda k: ((order.index(k[0]) + 1) if k[0] in order else (0 if k[0] == "(準備)" else 10**6), k[1])
    hdr = f"{'round':<8}{'source':<22}{'calls':>6}{'in':>8}{'cw':>8}{'cr':>9}{'out':>8}{'think':>8}{'ctx':>7}  note"
    print(hdr)
    print("-" * len(hdr))
    last, total = None, collections.defaultdict(collections.Counter)
    for (rid, src) in sorted(rows, key=key):
        r = rows[(rid, src)]
        note = " ".join(f"{k}={v}" if k == "jobs" else k for k, v in notes.get((rid, src), {}).items())
        label = f"{rid} {modes.get(rid, '')}".strip() if rid != last else ""
        if src == "worker:記録なし":
            print(f"{label:<8}{src:<22}{'-':>6}{'':>48}  {note}")
        else:
            print(f"{label:<8}{src:<22}{r['calls'] or '-':>6}{fmt(r['in']):>8}{fmt(r['cw']):>8}{fmt(r['cr']):>9}"
                  f"{fmt(r['out']):>8}{fmt(r['think']):>8}{fmt(r['ctx']) if r['ctx'] else '-':>7}  {note}")
        last = rid
        kind = src.split(":")[0] + (":sub" if src.endswith("/sub") else "")
        total[kind].update({k: r[k] for k in ("calls",) + KEYS})
    print("\n合計（worker の calls は claude の分だけ）")
    for kind, c in sorted(total.items()):
        print(f"  {kind:<12} calls={c['calls']} " + " ".join(f"{k}={fmt(c[k])}" for k in KEYS))
    print("\n凡例")
    for src, first, last_, title in legend:
        print(f"  {src:<18} {str(first)[:16]} → {str(last_)[:16]}  {title}")


def main():
    rs, rows, legend, notes, jobs = collect()
    if "--json" in sys.argv:
        print(json.dumps({"rows": [{"round": k[0], "source": k[1], **v, "note": dict(notes.get(k, {}))}
                                   for k, v in rows.items()],
                          "workers": jobs,
                          "legend": legend}, ensure_ascii=False, indent=1, default=str))
    elif "--jobs" in sys.argv:
        rid = sys.argv[sys.argv.index("--jobs") + 1]
        for j in jobs:
            if j["round"] == rid:
                u = j["usage"]
                print(f"{j['job']:<5}{j['engine']:<8}{j['outcome'] or '':<9}{j['minutes']:>6}分 calls={j['calls'] or '-':<4} "
                      + (" ".join(f"{k}={fmt(u[k])}" for k in KEYS) if u else "記録なし"))
    else:
        print_table(rs, rows, legend, notes)


if __name__ == "__main__":
    main()
