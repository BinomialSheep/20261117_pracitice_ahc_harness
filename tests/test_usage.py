"""Token usage parsing of worker logs and interactive sessions (thin/usage.py)."""
import json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from thin import usage as U
from thin.core import _engine_settings,_record_usage

def jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))

def claude_msg(mid,inp,cw,cr,out,text=None):
    content=[{'type':'text','text':text}] if text else [{'type':'tool_use'}]
    return {'type':'assistant','message':{'id':mid,'model':'m','content':content,
            'usage':{'input_tokens':inp,'cache_creation_input_tokens':cw,'cache_read_input_tokens':cr,'output_tokens':out}}}

def rate(five,week):
    return {'type':'rate_limit_event','rate_limit_info':{'unifiedWindows':{
        'five_hour':{'utilization':five,'resetsAt':100},'seven_day':{'utilization':week,'resetsAt':200}}}}

def token_count(ts,inp,cached,out,five):
    return {'timestamp':ts,'type':'event_msg','payload':{'type':'token_count',
            'info':{'total_token_usage':{'input_tokens':inp,'cached_input_tokens':cached,'output_tokens':out}},
            'rate_limits':{'primary':{'used_percent':five,'window_minutes':300,'resets_at':100}}}}

class Usage(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name)
        self.env={k:os.environ.get(k) for k in ('CODEX_HOME','CLAUDE_CONFIG_DIR')}
        os.environ['CODEX_HOME']=str(self.d/'codex');os.environ['CLAUDE_CONFIG_DIR']=str(self.d/'claude')
    def tearDown(self):
        for k,v in self.env.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
        self.tmp.cleanup()

    def test_claude_stream_dedupes_calls_and_reads_limits(self):
        j=self.d/'job'
        jsonl(j/'agent.stdout',[rate(.5,.2),claude_msg('a',2,100,1000,10),claude_msg('a',2,100,1000,10),
                                rate(.52,.21),claude_msg('b',3,50,1100,20,'done'),{'type':'result','result':'final text'}])
        u=U.worker_summary(j)
        self.assertEqual((u['source'],u['calls'],u['in'],u['cw'],u['cr'],u['out'],u['peak_ctx']),('claude-stream',2,5,150,2100,30,1153))
        self.assertEqual({(s['window'],s['first'],s['last']) for s in u['limits']},{('five_hour',50.0,52.0),('seven_day',20.0,21.0)})
        self.assertEqual(U.last_message(j),'final text')

    def test_killed_codex_worker_is_measured_from_moved_rollout(self):
        j=self.d/'job';tid='01a1ede9-7b19-72f0-8eb6-dadfbc475056'
        jsonl(j/'agent.stdout',[{'type':'thread.started','thread_id':tid},{'type':'item.completed','item':{'type':'agent_message','text':'hi'}}])
        src=self.d/'codex/sessions/2026/11/19'/f'rollout-2026-11-19T00-00-00-{tid}.jsonl'
        jsonl(src,[{'type':'session_meta','payload':{'cwd':'/w'}},token_count('2026-11-19T00:00:01Z',100,60,5,10),
                   token_count('2026-11-19T00:00:02Z',100,60,5,10),token_count('2026-11-19T00:00:03Z',250,180,12,11)])
        self.assertIsNone(U.worker_summary(j))  # no turn.completed: nothing in agent.stdout
        self.assertEqual(U.collect_codex_rollout(j),j/'codex_rollout.jsonl')
        self.assertFalse(src.exists())  # later workers cannot find it in ~/.codex/sessions
        u=U.worker_summary(j)
        self.assertEqual((u['source'],u['calls'],u['in'],u['cr'],u['out'],u['peak_ctx']),('codex-rollout',2,70,180,12,150))
        self.assertEqual(u['limits'],[{'window':'five_hour','resets_at':100,'first':10,'last':11}])
        self.assertEqual(U.last_message(j),'hi')

    def test_codex_turns_and_plain_text(self):
        j=self.d/'a';jsonl(j/'agent.stdout',[{'type':'turn.completed','usage':{'input_tokens':500,'cached_input_tokens':400,'output_tokens':9}}])
        u=U.worker_summary(j);self.assertEqual((u['source'],u['calls'],u['in'],u['cr']),('codex-turns',None,100,400))
        t=self.d/'t';t.mkdir();(t/'agent.stdout').write_text('457\nplain final message\n')
        self.assertIsNone(U.worker_summary(t));self.assertIsNone(U.last_message(t))

    def test_record_usage_never_raises(self):
        j=self.d/'job';j.mkdir();(j/'agent.stdout').write_bytes(b'\xff\xfe not json');job={}
        _record_usage(j,job);self.assertIsNone(job['usage'])

    def test_engine_settings(self):
        self.assertEqual(_engine_settings(['claude','-p','--model','x','--effort','high']),{'model':'x','effort':'high'})
        self.assertEqual(_engine_settings(['codex','exec','-m','y','-c','model_reasoning_effort="low"']),{'model':'y','effort':'low'})

    def _repo(self,rounds):
        root=self.d/'repo'
        for rid,created,closed in rounds:
            (root/'runs'/rid/'jobs').mkdir(parents=True)
            (root/'runs'/rid/'plan.json').write_text(json.dumps({'mode':'B','created_at':created}))
            (root/'runs'/rid/'state.json').write_text(json.dumps({'phase':'closed','closed_at':closed}))
        return root

    def _session(self,root,name,events):
        """events: ('prompt', ts, text) | ('call', ts, id, cache_read, bash_command_or_None)"""
        rows=[]
        for e in events:
            if e[0]=='prompt':rows.append({'type':'user','timestamp':e[1],'message':{'role':'user','content':e[2]}})
            else:
                m=claude_msg(e[2],1,0,e[3],1);m['timestamp']=e[1]
                if e[4]:m['message']['content']=[{'type':'tool_use','name':'Bash','input':{'command':e[4]}}]
                rows+=[m,m]
        jsonl(U.project_dir(root)/f'{name}.jsonl',rows)

    def test_only_round_work_of_the_running_session_counts(self):
        root=self._repo([('R0001','2026-11-19T01:00:30+00:00','2026-11-19T02:00:00+00:00'),
                         ('R0002','2026-11-19T04:00:30+00:00','2026-11-19T05:00:00+00:00')])
        py='.venv/bin/python -m thin.cli '
        self._session(root,'orch',[
            ('prompt','2026-11-19T00:50:00Z','understand the repo'),('call','2026-11-19T00:51:00Z','a',100,None),
            ('prompt','2026-11-19T01:00:00Z','start'),('call','2026-11-19T01:00:10Z','b',200,py+'prepare B --idea x'),
            ('call','2026-11-19T01:59:00Z','c',300,py+'close R0001'),('call','2026-11-19T02:00:30Z','d',400,None),
            ('prompt','2026-11-19T03:00:00Z','check the docs'),('call','2026-11-19T03:01:00Z','e',500,None),
            ('prompt','2026-11-19T04:00:00Z','next'),('call','2026-11-19T04:00:10Z','f',600,py+'prepare B --idea y'),
            ('call','2026-11-19T04:59:00Z','g',700,py+'close R0002')])
        self._session(root,'other',[('prompt','2026-11-19T01:30:00Z','measure tokens'),('call','2026-11-19T01:31:00Z','h',800,None)])
        # compaction summary: written after later prompts but stamped earlier; it is not a turn
        jsonl(U.project_dir(root)/'late.jsonl',[{'type':'user','timestamp':'2026-11-19T04:30:00Z','message':{'content':'q'}},
              {'type':'user','isCompactSummary':True,'timestamp':'2026-11-19T00:00:00Z','message':{'content':'summary'}}])
        rs=U.rounds(root);sess=U.sessions(root);info=U.round_spans(rs,sess)
        got={(src,u['cr']):r for r,src,_,_,u in U.attribute(rs,sess,info)}
        self.assertEqual(info['R0001']['owners'],{'claude:orch'})
        self.assertEqual(got,{('claude:orch',100):'R0001',  # first turns of a session started for R0001
                              ('claude:orch',200):'R0001',('claude:orch',300):'R0001',
                              ('claude:orch',400):'R0001',  # report after close, same turn
                              ('claude:orch',500):U.OUTSIDE,  # another task between rounds
                              ('claude:orch',600):'R0002',('claude:orch',700):'R0002',
                              ('claude:other',800):U.OUTSIDE})  # another session during the round
        self.assertEqual([t[1] for t in next(s for s in sess if s['source']=='claude:late')['turns']],['q'])
        snap=U.round_snapshot(root,'R0001')
        self.assertEqual((snap['final'],snap['orchestrator']['claude:orch']['cr']),(True,1000))
        self.assertFalse(U.round_snapshot(root,'R0002')['final'])
        self.assertEqual(U.save_snapshots(root),['R0001','R0002']);self.assertEqual(U.save_snapshots(root),['R0002'])

if __name__=='__main__':unittest.main()
