"""Checks for the atcoder13live A judge adapter and its wiring into the harness.

The adapter tests need the official tool binaries (scripts/build_tools.sh); they are skipped otherwise.
`simulate` re-implements the statement's rules independently, only to cross-check the adapter's reading of
the official visualizer; the harness itself never uses it.
"""
import json, os, random, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from thin import core as C, scoring as E
from thin.config import load as config_load
from thin.util import ThinError, read_json, write_json

TOOLS = ROOT / 'problem' / 'tools'
ADAPTER = TOOLS / 'score_case.py'
HAVE_TOOLS = all(os.access(TOOLS / 'bin' / name, os.X_OK) for name in ('gen', 'vis'))
NEED_TOOLS = unittest.skipUnless(HAVE_TOOLS, 'official tools not built; run scripts/build_tools.sh')
SAMPLE_OUTPUT = '9\n1 R\n2 R\n1 D\n2 D\n1 L\n2 L\n1 U\n2 U\n3\n'


def simulate(inp, out):
    """Score of `out` for `inp` following the statement (assumes a well-formed output)."""
    tok = inp.split()
    n, m, t, si, sj = map(int, tok[:5])
    board = tok[5:5 + n]
    words = out.split()
    k, ops, i = int(words[0]), [], 1
    while i < len(words):
        if words[i] in ('1', '2'):
            ops.append((words[i], words[i + 1]))
            i += 2
        else:
            ops.append((words[i], None))
            i += 1
    assert len(ops) == k
    step = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}
    floor = lambda x, y: 0 <= x < n and 0 <= y < n and board[x][y] != '#'
    x, y, power, painted = si, sj, 0, set()
    for kind, d in ops:
        if kind == '1':
            dx, dy = step[d]
            if floor(x + dx, y + dy):
                x, y = x + dx, y + dy
            power += 1
        elif kind == '2':
            dx, dy = step[d]
            for s in range(power + 1):
                if not floor(x + dx * s, y + dy * s):
                    break
                painted.add((x + dx * s, y + dy * s))
            power = power // 2 + 1
        else:
            power += 1
    unpainted = n * n - m - len(painted)
    return n * n - unpainted if unpainted > 0 else n * n + t - k


@NEED_TOOLS
class Adapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='painting adapter ')
        self.dir = Path(self.tmp.name)
        self.count = 0

    def tearDown(self):
        self.tmp.cleanup()

    def solver(self, body):
        """An executable Python script standing in for a compiled solver."""
        self.count += 1
        path = self.dir / f'solver{self.count}.py'
        path.write_text(f'#!{sys.executable}\nimport sys\n{body}\n')
        path.chmod(0o755)
        return path

    def judge(self, solver, seed=0, time_limit=2.0, save=None):
        result = self.dir / 'result.json'
        if result.exists():
            result.unlink()
        cmd = [sys.executable, str(ADAPTER), '--binary', str(solver), '--seed', str(seed),
               '--result', str(result), '--time-limit', str(time_limit)]
        if save:
            cmd += ['--save-dir', str(save)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(result.read_text())

    def test_generator_reproduces_distributed_inputs(self):
        (self.dir / 'seeds.txt').write_text('0\n1\n50\n99\n')
        subprocess.run([str(TOOLS / 'bin' / 'gen'), 'seeds.txt', '--dir', 'in'], cwd=self.dir, check=True,
                       capture_output=True)
        for index, seed in enumerate((0, 1, 50, 99)):
            self.assertEqual((self.dir / 'in' / f'{index:04d}.txt').read_bytes(),
                             (TOOLS / 'in' / f'{seed:04d}.txt').read_bytes())

    def test_sample_output_scores_22(self):
        record = self.judge(self.solver(f'sys.stdout.write({SAMPLE_OUTPUT!r})'))
        self.assertEqual(record['status'], 'ok')
        self.assertIs(record['valid'], True)
        self.assertEqual(record['score'], 22)
        self.assertEqual(simulate((TOOLS / 'in' / '0000.txt').read_text(), SAMPLE_OUTPUT), 22)

    def test_empty_plan_scores_wall_count_not_invalid(self):
        record = self.judge(self.solver('print(0)'), seed=3)
        m = int((TOOLS / 'in' / '0003.txt').read_text().split()[1])
        self.assertEqual((record['valid'], record['score']), (True, m))

    def test_random_plans_match_independent_simulation(self):
        body = ('import random\nr = random.Random(int(sys.stdin.readline().split()[3]) * 7 + 1)\n'
                'ops = [r.choice(["1 U", "1 D", "1 L", "1 R", "2 U", "2 D", "2 L", "2 R", "3"]) for _ in range(250)]\n'
                'print(len(ops)); print("\\n".join(ops))')
        solver = self.solver(body)
        for seed in (2, 7, 1234):
            save = self.dir / f'case{seed}'
            record = self.judge(solver, seed=seed, save=save)
            self.assertTrue(record['valid'], record)
            expected = simulate((save / 'input.txt').read_text(), (save / 'output.txt').read_text())
            self.assertEqual(record['score'], expected)
            self.assertEqual(read_json(save / 'summary.json')['score'], expected)
            self.assertTrue((save / 'vis.html').is_file())

    def test_rejected_outputs_are_invalid_not_zero(self):
        cases = {'length mismatch': 'print("2\\n1 R")', 'bad direction': 'print("1\\n1 X")',
                 'K above T': 'print(251); print("\\n".join(["3"] * 251))', 'garbage': 'print("hello")',
                 'empty': 'pass', 'not UTF-8': 'sys.stdout.buffer.write(b"\\xff\\xfe\\n")'}
        for name, body in cases.items():
            with self.subTest(name):
                record = self.judge(self.solver(body))
                self.assertEqual((record['status'], record['valid'], record['score']), ('invalid', False, None))
                self.assertTrue(record['reason'].startswith('WA: '), record['reason'])

    def test_runtime_error_and_tle_are_invalid(self):
        record = self.judge(self.solver('print(0); sys.exit(3)'))
        self.assertEqual((record['valid'], record['reason']), (False, 'RE: solver terminated with exit code 3'))
        record = self.judge(self.solver('import time; time.sleep(3); print(0)'), time_limit=0.3)
        self.assertFalse(record['valid'])
        self.assertTrue(record['reason'].startswith('TLE: '), record['reason'])

    def test_missing_tools_is_a_judge_error_without_result(self):
        lonely = self.dir / 'lonely'
        lonely.mkdir()
        shutil.copyfile(ADAPTER, lonely / 'score_case.py')
        result = self.dir / 'never.json'
        proc = subprocess.run([sys.executable, str(lonely / 'score_case.py'), '--binary', str(self.solver('print(0)')),
                               '--seed', '0', '--result', str(result)], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('missing tool binary', proc.stderr)
        self.assertFalse(result.exists())


class ProblemConfig(unittest.TestCase):
    def test_config_targets_this_problem(self):
        config = config_load(ROOT)
        self.assertEqual(config['problem']['tools'], 'problem/tools')
        self.assertIn('{tools}/score_case.py', config['judge']['command'])
        self.assertEqual(config['judge']['direction'], 'maximize')
        self.assertGreater(config['judge']['timeout_sec'], 2.0 + 0.5)  # solver TL + kill grace must fit
        self.assertTrue((ROOT / 'problem' / 'statement.md').read_text(encoding='utf-8').startswith('# A - Painting the Floor'))


@NEED_TOOLS
class HarnessWiring(unittest.TestCase):
    """init-best -> B round with a manual worker -> quickcheck -> evaluate -> promote, on a small seed count."""

    def test_round_trip_with_real_adapter(self):
        with tempfile.TemporaryDirectory(prefix='painting harness ') as td:
            root = Path(td) / 'project'
            (root / 'problem').mkdir(parents=True)
            shutil.copyfile(ROOT / 'problem' / 'statement.md', root / 'problem' / 'statement.md')
            shutil.copytree(TOOLS, root / 'problem' / 'tools', ignore=shutil.ignore_patterns('target', '__pycache__'))
            config = read_json(ROOT / 'config.json')
            config['evaluation'].update(count=3, parallelism=2)
            write_json(root / 'config.json', config)
            (root / 'zero.cpp').write_text('#include <cstdio>\nint main(){std::puts("0");}\n')
            C.init_best(root, root / 'zero.cpp')

            prepared = C.prepare(root, 'B', idea_text='Wait for power, then shoot in all four directions')
            rid = prepared['round_id']
            w = root / 'runs' / rid / 'jobs' / 'B01' / 'workspace'
            self.assertTrue(os.access(w / 'problem' / 'tools' / 'bin' / 'vis', os.X_OK))
            self.assertFalse((w / 'runs').exists() or (w / 'best').exists())
            (w / 'main.cpp').write_text(
                '#include <iostream>\nint main(){std::cout<<14<<"\\n";for(int i=0;i<10;i++)std::cout<<"3\\n";'
                'for(char d:{\'U\',\'D\',\'L\',\'R\'})std::cout<<"2 "<<d<<"\\n";}\n')
            quick = subprocess.run([sys.executable, 'quickcheck.py', '--seed', '0'], cwd=w, capture_output=True,
                                   text=True, timeout=120)
            self.assertEqual(quick.returncode, 0, quick.stderr)
            out = json.loads(quick.stdout)
            self.assertTrue(out['valid'])
            self.assertIn('elapsed_sec', out)
            self.assertNotIn('remaining_min', out)  # a manual worker has no deadline
            cfg = json.loads((w / 'worker_config.json').read_text())
            (w / 'worker_config.json').write_text(json.dumps({**cfg, 'deadline_epoch': time.time() + 600}))
            quick = subprocess.run([sys.executable, 'quickcheck.py', '--seed', '0'], cwd=w, capture_output=True,
                                   text=True, timeout=120)
            self.assertTrue(9.0 <= json.loads(quick.stdout)['remaining_min'] <= 10.0)
            self.assertTrue((w / 'judge_last' / 'vis.html').is_file())
            refused = subprocess.run([sys.executable, 'quickcheck.py', '--seed', '1000'], cwd=w, capture_output=True,
                                     text=True, timeout=60)
            self.assertNotEqual(refused.returncode, 0)

            C.submit(root, rid, 'B01')
            C.mark_workers_done(root, rid)
            result = E.evaluate(root, rid)
            self.assertTrue(result['baseline']['valid'])
            candidate = result['candidates'][0]
            self.assertTrue(candidate['valid'], candidate)
            self.assertEqual(candidate['n'], 3)
            self.assertGreater(candidate['effect'], 0)
            E.promote(root, rid, 'B01')
            self.assertEqual(C.read_best(root)['job'], 'B01')
            C.close(root, rid)
            with self.assertRaises(ThinError):  # a closed round cannot promote anything any more
                E.promote(root, rid, 'B01')


if __name__ == '__main__':
    unittest.main()
