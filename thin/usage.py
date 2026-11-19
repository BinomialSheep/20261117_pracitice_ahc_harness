"""Token usage of workers and interactive sessions. Read-only, except that a codex worker's own rollout
is moved out of ~/.codex/sessions into its job directory.

Categories are the same for both engines: in=uncached input, cw=cache write, cr=cache read,
out=output including thinking, think=the thinking part of out. Codex input_tokens includes the cached
part, so it is subtracted. ctx is the input read by one call (in+cw+cr). Limits are percentages of the
subscription's 5-hour and weekly windows. No dollar figures: the plans are subscriptions.
"""
from __future__ import annotations
import collections,datetime as dt,json,os,re,shutil
from pathlib import Path

KEYS=('in','cw','cr','out','think')
CODEX_WINDOWS={300:'five_hour',10080:'seven_day'}

def claude_home():return Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home()/'.claude')
def codex_home():return Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')

def parse_ts(s):
    if not s:return None
    if isinstance(s,(int,float)):return dt.datetime.fromtimestamp(s,dt.timezone.utc)
    try:return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    except ValueError:return dt.datetime.fromisoformat(s[:19]+'+00:00')

def lines(path):
    with open(path,encoding='utf-8',errors='replace') as f:
        for line in f:
            try:d=json.loads(line)
            except json.JSONDecodeError:continue
            if isinstance(d,dict):yield d

def claude_usage(u):
    return {'in':u.get('input_tokens') or 0,'cw':u.get('cache_creation_input_tokens') or 0,
            'cr':u.get('cache_read_input_tokens') or 0,'out':u.get('output_tokens') or 0,
            'think':(u.get('output_tokens_details') or {}).get('thinking_tokens') or 0}

def codex_usage(u):
    cached=u.get('cached_input_tokens') or 0
    return {'in':(u.get('input_tokens') or 0)-cached,'cw':u.get('cache_write_input_tokens') or 0,'cr':cached,
            'out':u.get('output_tokens') or 0,'think':u.get('reasoning_output_tokens') or 0}

def ctx(u):return u['in']+u['cw']+u['cr']

def total(usages):
    t={'calls':0,**{k:0 for k in KEYS},'peak_ctx':0}
    for u in usages:
        t['calls']+=1;t['peak_ctx']=max(t['peak_ctx'],ctx(u))
        for k in KEYS:t[k]+=u[k]
    return t

def _claude_limits(d):
    for name,w in ((d.get('rate_limit_info') or {}).get('unifiedWindows') or {}).items():
        if isinstance(w,dict) and w.get('utilization') is not None:
            yield name,w.get('resetsAt'),round(w['utilization']*100,1)

def _codex_limits(rl):
    for key in ('primary','secondary'):
        w=(rl or {}).get(key)
        if isinstance(w,dict) and w.get('used_percent') is not None:
            yield CODEX_WINDOWS.get(w.get('window_minutes'),key),w.get('resets_at'),w['used_percent']

def limit_spans(obs):
    """[(window, resets_at, percent)] in time order -> first and last percent per window period."""
    g={}
    for name,reset,pct in obs:g.setdefault((name,reset),[]).append(pct)
    return [{'window':n,'resets_at':r,'first':v[0],'last':v[-1]} for (n,r),v in g.items()]

def merge_spans(spans):
    """Spans from parallel workers -> lowest first and highest last per window period."""
    g={}
    for s in spans:
        k=(s['window'],s['resets_at']);x=g.setdefault(k,dict(s))
        x['first']=min(x['first'],s['first']);x['last']=max(x['last'],s['last'])
    return list(g.values())

def claude_calls(path):
    """[(time, usage)] per API call of a Claude Code transcript. One response is written as several lines
    carrying the same usage, so calls are deduplicated by message.id."""
    calls,meta={},{'title':None,'first':None,'last':None}
    for d in lines(path):
        t=d.get('timestamp')
        if t:meta['first']=meta['first'] or t;meta['last']=t
        if d.get('type')=='ai-title':meta['title']=d.get('aiTitle')
        m=d.get('message')
        if d.get('type')=='assistant' and isinstance(m,dict) and m.get('usage') and m.get('model')!='<synthetic>':
            calls.setdefault(m.get('id') or d.get('uuid'),(parse_ts(t),claude_usage(m['usage'])))
    return list(calls.values()),meta

def codex_calls(path):
    """[(time, usage)] per model call of a codex rollout (differences of the cumulative token_count),
    session metadata, and limit observations."""
    calls,limits,prev,meta=[],[],None,{}
    for d in lines(path):
        p=d.get('payload') if isinstance(d.get('payload'),dict) else {}
        if d.get('type')=='session_meta':
            meta={'cwd':p.get('cwd',''),'originator':p.get('originator'),'first':d.get('timestamp'),'last':d.get('timestamp')}
        if p.get('type')!='token_count':continue
        meta['last']=d.get('timestamp')
        limits+=_codex_limits(p.get('rate_limits'))
        if not p.get('info'):continue
        cum=codex_usage(p['info'].get('total_token_usage') or {})
        delta=cum if prev is None else {k:cum[k]-prev[k] for k in KEYS}
        if any(v<0 for v in delta.values()):delta=codex_usage(p['info'].get('last_token_usage') or {})
        prev=cum
        if any(delta.values()):calls.append((parse_ts(d.get('timestamp')),delta))
    return calls,meta,limits

def collect_codex_rollout(jdir):
    """Move this codex worker's rollout from ~/.codex/sessions to jobs/<id>/codex_rollout.jsonl.
    It holds per-call token counts even when the worker was killed, and later workers cannot read it there."""
    jdir=Path(jdir);out=jdir/'agent.stdout';dest=jdir/'codex_rollout.jsonl'
    if dest.exists() or not out.exists():return None
    tid=None
    for d in lines(out):
        if d.get('type')=='thread.started':tid=d.get('thread_id');break
    if not isinstance(tid,str) or not re.fullmatch(r'[0-9A-Za-z-]{8,64}',tid):return None
    found=sorted((codex_home()/'sessions').rglob(f'rollout-*{tid}.jsonl'))
    if not found:return None
    shutil.move(str(found[0]),str(dest))
    return dest

def worker_summary(jdir):
    """Usage of one worker from its own logs, or None when the logs hold none (claude text output)."""
    jdir=Path(jdir);rollout=jdir/'codex_rollout.jsonl';out=jdir/'agent.stdout'
    calls,limits,source=[],[],None
    if rollout.exists():
        calls,_,limits=codex_calls(rollout);calls=[u for _,u in calls];source='codex-rollout'
    elif out.exists():
        seen,turns=set(),[]
        for d in lines(out):
            t=d.get('type');m=d.get('message')
            if t=='turn.completed':turns.append(codex_usage(d.get('usage') or {}))
            elif t=='assistant' and isinstance(m,dict) and m.get('usage'):
                if m.get('id') not in seen:seen.add(m.get('id'));calls.append(claude_usage(m['usage']))
            elif t=='rate_limit_event':limits+=_claude_limits(d)
        if calls:source='claude-stream'
        elif turns:source='codex-turns'
    if source is None:return None
    if source=='codex-turns':  # only totals per turn: no call count, no context size
        return {'source':source,'calls':None,**{k:sum(u[k] for u in turns) for k in KEYS},'peak_ctx':None,'limits':[]}
    return {'source':source,**total(calls),'limits':limit_spans(limits)}

def last_message(jdir):
    """Final agent message from a JSON event log (claude stream-json or codex --json); None for plain text."""
    out=Path(jdir)/'agent.stdout'
    if not out.exists():return None
    msg,structured=None,False
    for d in lines(out):
        t=d.get('type');m=d.get('message');it=d.get('item') if isinstance(d.get('item'),dict) else {}
        if t=='result' and isinstance(d.get('result'),str):msg,structured=d['result'],True
        elif t=='assistant' and isinstance(m,dict):
            structured=True
            text=''.join(c.get('text','') for c in m.get('content') or [] if isinstance(c,dict) and c.get('type')=='text')
            if text:msg=text
        elif t=='item.completed' and it.get('type')=='agent_message':msg,structured=it.get('text'),True
    return msg if structured else None

def project_dir(root):
    return claude_home()/'projects'/re.sub(r'[^A-Za-z0-9]','-',str(Path(root).resolve()))

def sessions(root,since=None):
    """Interactive Claude Code / Codex sessions started in this repository (workers excluded).
    since: skip files last written before this POSIX time."""
    root=Path(root).resolve();res=[];pd=project_dir(root)
    old=lambda f:since is not None and f.stat().st_mtime<since
    if pd.is_dir():
        for f in sorted(pd.glob('*.jsonl')):
            if old(f):continue
            calls,meta=claude_calls(f);sid=f.stem[:8]
            res.append({'source':'claude:'+sid,'title':meta['title'],'first':meta['first'],'last':meta['last'],'calls':calls})
            subs=sorted((pd/f.stem/'subagents').glob('*.jsonl'))
            sub=[c for s in subs for c in claude_calls(s)[0]]
            if sub:res.append({'source':f'claude:{sid}/sub','title':f'subagents of {sid} ({len(subs)})',
                               'first':meta['first'],'last':meta['last'],'calls':sub})
    sd=codex_home()/'sessions';runs=str(root/'runs')+os.sep
    if sd.is_dir():
        for f in sorted(sd.rglob('rollout-*.jsonl')):
            if old(f):continue
            with open(f,encoding='utf-8',errors='replace') as h:head=h.readline()
            if str(root) not in head:continue  # session_meta (first line) holds cwd
            calls,meta,_=codex_calls(f);cwd=meta.get('cwd','')
            if not (cwd==str(root) or cwd.startswith(str(root)+os.sep)) or cwd.startswith(runs):continue
            res.append({'source':'codex:'+f.stem.split('-')[-1][:8],'title':f"{meta.get('originator')} {cwd[len(str(root)):] or '/'}",
                        'first':meta.get('first'),'last':meta.get('last'),'calls':calls})
    return res

def rounds(root):
    rs=[]
    for rd in sorted((Path(root)/'runs').glob('R[0-9]*')):
        try:plan=json.loads((rd/'plan.json').read_text());state=json.loads((rd/'state.json').read_text())
        except (OSError,ValueError):continue
        rs.append({'id':rd.name,'mode':plan.get('mode'),'created':parse_ts(plan.get('created_at')),
                   'closed':parse_ts(state.get('closed_at')),'dir':rd})
    return rs

def round_of(t,rs):
    """Round that an interactive call belongs to: R(n) covers (close of R(n-1), close of R(n)]."""
    if t is None or not rs:return '(不明)'
    if t<rs[0]['created']:return '(準備)'
    for r in rs:
        if r['closed'] is None or t<=r['closed']:return r['id']
    return '(次のラウンド)'

def worker_rows(rd):
    rows={}
    for jdir in sorted((Path(rd)/'jobs').glob('*')):
        try:job=json.loads((jdir/'job.json').read_text())
        except (OSError,ValueError):job={}
        u=job['usage'] if 'usage' in job else worker_summary(jdir)
        rows[jdir.name]={'engine':job.get('engine') or ({'claude-stream':'claude'}.get(u['source'],'codex') if u else None),
                         'model':job.get('model'),'effort':job.get('effort'),'outcome':job.get('agent_outcome'),
                         'minutes':round((job.get('agent_run') or {}).get('seconds',0)/60,1),'usage':u}
    return rows

def round_snapshot(root,rid):
    """Usage of one closed round, written to runs/<rid>/usage.json by close (transcripts expire later)."""
    rs=rounds(root);ids=[r['id'] for r in rs];i=ids.index(rid)
    start=rs[i-1]['closed'] if i else None
    sess={}
    for s in sessions(root,since=start.timestamp() if start else None):
        calls=[u for t,u in s['calls'] if round_of(t,rs)==rid]
        if calls:sess[s['source']]={**total(calls),'title':s['title']}
    workers=worker_rows(rs[i]['dir']);used=[w['usage'] for w in workers.values() if w['usage']]
    return {'round_id':rid,'mode':rs[i]['mode'],
            'window':{'from':start.isoformat() if start else rs[i]['created'].isoformat(),
                      'to':rs[i]['closed'].isoformat() if rs[i]['closed'] else None},
            'sessions':sess,
            'workers_total':{k:sum(u[k] for u in used) for k in KEYS},
            'workers_without_usage':sum(1 for w in workers.values() if not w['usage']),
            'worker_limits':merge_spans([s for u in used for s in u.get('limits') or []]),
            'workers':workers}
