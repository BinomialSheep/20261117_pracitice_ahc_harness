#!/usr/bin/env python3
"""Judge adapter for atcoder13live A "Painting the Floor": one seed per call (score-result-v1).

    python3 score_case.py --binary SOLVER --seed SEED --result RESULT.json [--time-limit 2.0] [--save-dir DIR]

1. The official generator bin/gen creates the input for SEED (seeds 0-99 equal in/0000.txt-in/0099.txt).
2. SOLVER runs once with that input on stdin. Wall-clock time above --time-limit is TLE.
3. The official visualizer bin/vis validates and scores the output.
4. RESULT.json receives
     valid:   {"status": "ok", "valid": true, "score": <int>, ...}
     invalid: {"status": "invalid", "valid": false, "score": null, "reason": "..."}  (TLE / RE / MLE / WA)
   Environment failures (missing tool binaries, generator or visualizer malfunction) exit non-zero
   WITHOUT writing RESULT.json, so the harness records a judge error instead of an invalid solver.

With --save-dir the case files (input.txt, output.txt, solver_stderr.txt, vis.html, summary.json) are
kept in that directory for debugging; otherwise everything is written to a temporary directory.
Runs on Python 3.8+ (workers may call it through the system python3).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent / 'bin'
GRACE_SEC = 0.5               # a slow solver is killed at time_limit + GRACE_SEC; it is TLE either way
MEMORY_LIMIT_MIB = 1024       # from the problem statement
MAX_OUTPUT_BYTES = 1 << 20    # a legal output (K <= 250 short lines) is far below this
STDERR_KEEP_BYTES = 64 << 10  # tail of the solver's stderr kept in --save-dir
ARTIFACTS = ('seeds.txt', 'input.txt', 'output.txt', 'solver_stderr.txt', 'vis.html', 'summary.json')


class JudgeError(Exception):
    """The adapter or the official tools failed; this is not the solver's fault."""


def tool(name):
    path = BIN / name
    if not os.access(path, os.X_OK):
        raise JudgeError(f'missing tool binary {path}; build it with scripts/build_tools.sh in the harness repository')
    return str(path)


def generate(seed, work):
    """Write the official input for `seed` to work/input.txt."""
    (work / 'seeds.txt').write_text(f'{seed}\n')
    with tempfile.TemporaryDirectory(dir=work, prefix='gen-') as out_dir:
        proc = subprocess.run([tool('gen'), 'seeds.txt', '--dir', out_dir], cwd=work,
                              capture_output=True, text=True, timeout=60)
        produced = Path(out_dir) / '0000.txt'
        if proc.returncode != 0 or not produced.is_file():
            raise JudgeError(f'gen failed for seed {seed}: {proc.stderr.strip()[-500:]}')
        os.replace(produced, work / 'input.txt')


def run_solver(binary, work, limit):
    """Run the solver once with a wall-clock limit. Not a sandbox: only the time limit is enforced by killing."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with open(work / 'input.txt', 'rb') as fin, open(work / 'output.txt', 'wb') as fout, \
            open(work / 'solver_stderr.txt', 'wb') as ferr:
        start = time.perf_counter()
        try:
            proc = subprocess.Popen([binary], stdin=fin, stdout=fout, stderr=ferr, cwd=work)
        except OSError as e:
            return {'launch_error': str(e)}
        killed = False
        try:
            returncode = proc.wait(timeout=limit + GRACE_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait()
            killed = True
        elapsed = time.perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    # RUSAGE_CHILDREN covers reaped children only: the generator (tiny) and the solver at this point.
    return {'returncode': returncode, 'killed': killed, 'elapsed_sec': elapsed,
            'cpu_sec': (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime),
            'max_rss_mib': after.ru_maxrss / 1024}


def score_output(work):
    """Official scoring. Returns (score, error_lines); error lines mean the output was rejected."""
    proc = subprocess.run([tool('vis'), 'input.txt', 'output.txt'], cwd=work,
                          capture_output=True, text=True, timeout=60)
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    match = re.fullmatch(r'Score = (-?\d+)', lines[-1]) if lines else None
    if proc.returncode != 0 or match is None:
        raise JudgeError(f'unexpected vis result (exit {proc.returncode}): '
                         f'{proc.stdout.strip()[-300:]} {proc.stderr.strip()[-300:]}')
    # vis prints the parse error and then "Score = 0" for a rejected output.
    return int(match.group(1)), lines[:-1]


def invalid(reason, info):
    return {'status': 'invalid', 'valid': False, 'score': None, 'reason': reason, **info}


def judge(binary, work, limit):
    run = run_solver(binary, work, limit)
    if 'launch_error' in run:
        return invalid(f'RE: solver could not be started: {run["launch_error"]}', {})
    info = {key: round(run[key], 3) for key in ('elapsed_sec', 'cpu_sec', 'max_rss_mib')}
    if run['killed'] or run['elapsed_sec'] > limit:
        return invalid(f'TLE: {run["elapsed_sec"]:.3f}s > {limit:g}s' + (' (killed)' if run['killed'] else ''), info)
    returncode = run['returncode']
    if returncode != 0:
        if returncode < 0:
            try:
                how = f'signal {signal.Signals(-returncode).name}'
            except ValueError:
                how = f'signal {-returncode}'
        else:
            how = f'exit code {returncode}'
        return invalid(f'RE: solver terminated with {how}', info)
    if run['max_rss_mib'] > MEMORY_LIMIT_MIB:
        return invalid(f'MLE: max RSS {run["max_rss_mib"]:.0f} MiB > {MEMORY_LIMIT_MIB} MiB', info)
    data = (work / 'output.txt').read_bytes()
    if len(data) > MAX_OUTPUT_BYTES:
        return invalid(f'WA: output too large ({len(data)} bytes)', info)
    try:
        data.decode('utf-8')  # vis misreports non-UTF-8 output as a missing file, so reject it here
    except UnicodeDecodeError:
        return invalid('WA: output is not valid UTF-8 text', info)
    score, errors = score_output(work)
    if errors:
        return invalid('WA: ' + ' / '.join(errors)[:300], info)
    return {'status': 'ok', 'valid': True, 'score': score, **info}


def run_case(seed, binary, work, limit, keep):
    generate(seed, work)
    record = {**judge(binary, work, limit), 'seed': seed, 'time_limit_sec': limit}
    if keep:
        err = work / 'solver_stderr.txt'
        if err.is_file() and err.stat().st_size > STDERR_KEEP_BYTES:
            with open(err, 'rb') as f:
                f.seek(-STDERR_KEEP_BYTES, os.SEEK_END)
                tail = f.read()
            err.write_bytes(b'...(truncated)...\n' + tail)
        (work / 'summary.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description='Score one seed of atcoder13live A with the official tools.')
    parser.add_argument('--binary', required=True, help='compiled solver')
    parser.add_argument('--seed', type=int, required=True, help='generator seed (nonnegative integer)')
    parser.add_argument('--result', required=True, help='where to write the score-result-v1 JSON')
    parser.add_argument('--time-limit', type=float, default=2.0, help='wall-clock seconds (default 2.0)')
    parser.add_argument('--save-dir', help='keep input/output/stderr/vis.html/summary.json of this case here')
    args = parser.parse_args(argv)
    if args.seed < 0:
        parser.error('--seed must be nonnegative')
    if not args.time_limit > 0:
        parser.error('--time-limit must be positive')
    binary = str(Path(args.binary).resolve())  # Popen resolves relative paths against cwd=work otherwise
    try:
        if args.save_dir:
            work = Path(args.save_dir).resolve()  # tools run with cwd=work, so every path must be absolute
            work.mkdir(parents=True, exist_ok=True)
            for name in ARTIFACTS:  # remove only our own files from a previous case, never the directory
                try:
                    (work / name).unlink()
                except FileNotFoundError:
                    pass
            record = run_case(args.seed, binary, work, args.time_limit, keep=True)
        else:
            with tempfile.TemporaryDirectory(prefix='painting-judge-') as tmp:
                record = run_case(args.seed, binary, Path(tmp).resolve(), args.time_limit, keep=False)
    except (JudgeError, OSError, subprocess.SubprocessError) as e:
        print(f'score_case.py: judge error (not a solver verdict): {e}', file=sys.stderr)
        return 2
    Path(args.result).write_text(json.dumps(record, ensure_ascii=False) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
