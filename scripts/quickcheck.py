#!/usr/bin/env python3
"""Standalone per-worker debug gate. Never sees other candidates, history or full eval seeds."""
import argparse,json,math,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=0);a=p.parse_args()
w=Path(__file__).resolve().parent
meta=json.loads((w/'worker_config.json').read_text())
if a.seed not in meta['allowed_seeds']:
    sys.exit('Seed outside this worker debug allowance')
fmt={'source':str(w/'main.cpp'),'binary':str(w/'_quick_bin'),'workspace':str(w),'tools':str(w/'problem/tools'),
     'python':sys.executable,'seed':str(a.seed),'result':str(w/'_quick_result.json'),'workdir':str(w)}
def args(seq):return [x.format_map(fmt) for x in seq]
def remaining():  # the worker's own time limit, written by run-workers at launch
    d=meta.get('deadline_epoch')
    return {} if d is None else {'remaining_min':max(0.0,round((d-time.time())/60,1))}
try:
    build=subprocess.run(args(meta['build']),cwd=w,text=True,capture_output=True,timeout=120)
    if build.returncode:raise RuntimeError('compile failed: '+build.stderr[-1200:])
    judge=subprocess.run(args(meta['judge']),cwd=w,text=True,capture_output=True,timeout=meta['judge_timeout'])
    if judge.returncode:raise RuntimeError('judge process failed: '+judge.stderr[-1200:])
    result=json.loads(Path(fmt['result']).read_text());score=result.get('score')
    if result.get('status')!='ok' or result.get('valid') is not True or type(score) not in (int,float) or not math.isfinite(score):
        raise RuntimeError('invalid output or score: '+str(result))
    elapsed={'elapsed_sec':result['elapsed_sec']} if 'elapsed_sec' in result else {}
    print(json.dumps({'seed':a.seed,'valid':True,'score':score,**elapsed,**remaining()}))
except (OSError,KeyError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:
    r=remaining()
    print('quickcheck failed:',e,*([json.dumps(r)] if r else []),file=sys.stderr);sys.exit(2)
