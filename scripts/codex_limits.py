#!/usr/bin/env python3
"""Codex CLI の利用上限（5時間枠・週間枠）を読む。

`codex app-server` に `initialize` と `account/rateLimits/read` だけを送る読み取り専用のスクリプト。
リセット権を消費する `account/rateLimitResetCredit/consume` などは、送れないように許可リストで止めている。

    python3 scripts/codex_limits.py          # 人間向けの表示
    python3 scripts/codex_limits.py --json   # 機械向け（used_percent, resets_at など）
    python3 scripts/codex_limits.py --raw    # app-server の応答そのまま
"""
import datetime
import json
import subprocess
import sys

ALLOWED_METHODS = {"initialize", "initialized", "account/rateLimits/read"}


def read_limits(timeout=60):
    p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)

    def send(obj):
        if obj["method"] not in ALLOWED_METHODS:
            raise RuntimeError("refusing to send non-read-only method: " + obj["method"])
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()

    def wait(id_):
        for line in p.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == id_:
                if "error" in msg:
                    raise RuntimeError("app-server error: " + json.dumps(msg["error"], ensure_ascii=False))
                return msg["result"]
        raise RuntimeError("app-server closed: " + p.stderr.read()[-2000:])

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "codex-limits", "version": "1"}}})
        wait(1)
        send({"jsonrpc": "2.0", "method": "initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read",
              "params": {"excludeResetCreditDetails": True}})
        return wait(2)
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


def summarize(result):
    snap = result.get("rateLimits") or {}
    out = {"plan": snap.get("planType"), "ordinary_usage_allowed": result.get("ordinaryUsageAllowed"),
           "limit_reached": snap.get("rateLimitReachedType")}
    for key, name in (("primary", "five_hour"), ("secondary", "weekly")):
        w = snap.get(key)
        if w:
            out[name] = {"used_percent": w.get("usedPercent"), "window_minutes": w.get("windowDurationMins"),
                         "resets_at": w.get("resetsAt")}
    return out


def main():
    result = read_limits()
    if "--raw" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return
    s = summarize(result)
    if "--json" in sys.argv:
        print(json.dumps(s, ensure_ascii=False))
        return
    print(f"plan: {s['plan']}  usage allowed: {s['ordinary_usage_allowed']}  limit reached: {s['limit_reached']}")
    for name, label in (("five_hour", "5時間枠"), ("weekly", "週間枠")):
        w = s.get(name)
        if w:
            reset = datetime.datetime.fromtimestamp(w["resets_at"]).strftime("%Y-%m-%d %H:%M") if w["resets_at"] else "?"
            print(f"{label}: {w['used_percent']}% 使用（{w['window_minutes']}分枠、{reset} にリセット）")


if __name__ == "__main__":
    main()
