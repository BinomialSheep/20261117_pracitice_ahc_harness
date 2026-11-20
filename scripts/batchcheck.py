#!/usr/bin/env python3
"""Per-worker batch scorer for hyperparameter tuning. Only seeds in this worker's tuning range (or debug seeds)."""
import argparse,concurrent.futures,json,math,os,shutil,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser(description='Compile once and score many allowed seeds in parallel.')
p.add_argument('--seeds',required=True,help='e.g. 1000000-1000199 or 0,1,2 (ranges are inclusive)')
p.add_argument('--binary',help='prebuilt solver to score; default: build main.cpp with the official command')
p.add_argument('--env',action='append',default=[],metavar='KEY=VALUE',help='environment for the solver (repeatable)')
p.add_argument('--jobs',type=int,help='parallel cases (default and maximum: the configured tuning parallelism)')
p.add_argument('--out',help='write per-seed results as JSON here')
p.add_argument('--time-limit',type=float,help='wall-clock limit per case in seconds, at most 600, for long-run experiments (default: the evaluation limit)')
p.add_argument('--keep',metavar='DIR',help="keep each case's input.txt, output.txt, solver_stderr.txt and summary.json in DIR/<seed>/")
a=p.parse_args()
w=Path(__file__).resolve().parent
meta=json.loads((w/'worker_config.json').read_text())
tune=meta.get('tuning')
if not tune:sys.exit('Batch scoring is not enabled for this worker')
lo,hi=tune['seed_start'],tune['seed_start']+tune['seed_count']-1
def parse(spec):
    out=[]
    for part in spec.split(','):
        part=part.strip()
        if not part:continue
        if '-' in part:
            x,y=part.split('-',1);out.extend(range(int(x),int(y)+1))
        else:out.append(int(part))
    return out
try:seeds=parse(a.seeds)
except ValueError:sys.exit('Bad --seeds')
bad=[s for s in seeds if not (lo<=s<=hi or s in meta['allowed_seeds'])]
if not seeds or bad:sys.exit(f'Seeds outside this worker allowance (tuning {lo}-{hi}, debug {meta["allowed_seeds"]}): {bad[:5]}')
jobs=min(a.jobs or tune['parallelism'],tune['parallelism'])
if jobs<1:sys.exit('--jobs must be positive')
env=os.environ.copy()
judge=list(meta['judge']);judge_timeout=meta['judge_timeout']
if a.time_limit is not None:
    if not 0<a.time_limit<=600:sys.exit('--time-limit must be in (0, 600]')
    if '--time-limit' in judge:
        i=judge.index('--time-limit');base=float(judge[i+1]);judge[i+1]=str(a.time_limit)
    else:base=2.0;judge+=['--time-limit',str(a.time_limit)]
    judge_timeout+=max(0.0,a.time_limit-base)
keep=Path(a.keep).resolve() if a.keep else None
if keep:
    keep.mkdir(parents=True,exist_ok=True)
    if '--save-dir' not in judge:judge+=['--save-dir','{workdir}/judge_last']
for kv in a.env:
    if '=' not in kv:sys.exit('Bad --env (need KEY=VALUE): '+kv)
    k,v=kv.split('=',1);env[k]=v
def remaining():
    d=meta.get('deadline_epoch')
    return {} if d is None else {'remaining_min':max(0.0,round((d-time.time())/60,1))}
root=w/'_batch'/str(os.getpid());root.mkdir(parents=True,exist_ok=True)
fmt={'source':str(w/'main.cpp'),'binary':str(root/'bin'),'workspace':str(w),'tools':str(w/'problem/tools'),'python':sys.executable}
if a.binary:
    binary=Path(a.binary).resolve()
    if not binary.is_file():sys.exit('No such binary: '+a.binary)
else:
    build=subprocess.run([x.format_map(fmt) for x in meta['build']],cwd=w,text=True,capture_output=True,timeout=120)
    if build.returncode:sys.exit('compile failed: '+build.stderr[-1200:])
    binary=root/'bin'
def case(seed):
    d=root/str(seed);d.mkdir(exist_ok=True)
    f={**fmt,'binary':str(binary),'seed':str(seed),'result':str(d/'result.json'),'workdir':str(d)}
    try:
        r=subprocess.run([x.format_map(f) for x in judge],cwd=w,text=True,capture_output=True,timeout=judge_timeout,env=env)
        if keep:
            src=Path(judge[judge.index('--save-dir')+1].format_map(f));dst=keep/str(seed);dst.mkdir(exist_ok=True)
            for name in ('input.txt','output.txt','solver_stderr.txt','summary.json'):
                if (src/name).is_file():shutil.copyfile(src/name,dst/name)
        if r.returncode:return {'seed':seed,'valid':False,'reason':'judge process failed: '+r.stderr[-300:]}
        res=json.loads((d/'result.json').read_text());score=res.get('score')
        if res.get('status')!='ok' or res.get('valid') is not True or type(score) not in (int,float) or not math.isfinite(score):
            return {'seed':seed,'valid':False,'reason':str(res.get('reason',res))[:300]}
        return {'seed':seed,'valid':True,'score':score,'elapsed_sec':res.get('elapsed_sec')}
    except (OSError,ValueError,subprocess.TimeoutExpired) as e:return {'seed':seed,'valid':False,'reason':str(e)[:300]}
    finally:shutil.rmtree(d,ignore_errors=True)
try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:rows=list(pool.map(case,seeds))
finally:shutil.rmtree(root,ignore_errors=True)
ok=[r for r in rows if r['valid']];el=[r['elapsed_sec'] for r in ok if r.get('elapsed_sec') is not None]
summary={'n':len(rows),'valid':len(ok),'mean_score':round(sum(r['score'] for r in ok)/len(ok),4) if ok else None,
         'max_elapsed_sec':max(el) if el else None,'invalid':[{'seed':r['seed'],'reason':r['reason']} for r in rows if not r['valid']][:10],**remaining()}
if a.out:Path(a.out).write_text(json.dumps(rows))
print(json.dumps(summary))
sys.exit(0 if len(ok)==len(rows) else 3)
