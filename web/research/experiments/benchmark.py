"""Frozen exploratory benchmark. Never imports the CSP compiler in this process.

Run from the repository root with .venv/bin/python research/experiments/benchmark.py.
Inputs/responses are persisted before evaluation; completed requests are not rerun.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from backend.catalog import CATALOG, CATEGORIES, FOUNDATION, FOCUS_AREAS, course_info, math_entry_waived
from backend.defaults import default_cards
from backend.schemas import PlanRequest, ConstraintCard
from backend.validation import rule_satisfied, academic_audit, exam_pairs
from backend.attendance import semester_selection, lesson_groups
from backend.nusmods import minutes
from backend.minors import programmes, minor_prompt_cards, allowed_courses, audit_minors, MINORS, group_codes
from backend.llm import available_model_details, BASE_URL
import httpx

HERE = Path(__file__).resolve().parent
RUN = HERE / 'run-2026-11-09'
LEVELS = ['A', 'AP', 'APR']
PROFILES = {
 'base': {'instruction': 'I am a new NUS Computer Science student. Plan my complete degree.', 'extra': []},
 'math': {'instruction': 'I am a new NUS CS student. Complete a Mathematics minor. I prefer CS2102 in semester 3.',
          'extra': [dict(id='math-minor', title='Complete a Mathematics minor', strength='hard', rules=[dict(type='minor_programme',programme='mathematics')]),
                    dict(id='pin',title='Prefer CS2102 in semester 3',strength='soft',rules=[dict(type='course_in_semester',course='CS2102',semester=3)])]},
 'qf': {'instruction': 'I am a new NUS CS student. Complete a Quantitative Finance minor. I prefer CS2102 in semester 3.',
        'extra': [dict(id='qf-minor', title='Complete a Quantitative Finance minor', strength='hard', rules=[dict(type='minor_programme',programme='quantitative_finance')]),
                  dict(id='pin',title='Prefer CS2102 in semester 3',strength='soft',rules=[dict(type='course_in_semester',course='CS2102',semester=3)])]},
}

def dump(path, value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def request_for(profile):
 return PlanRequest(cards=default_cards()+[ConstraintCard(**c) for c in PROFILES[profile]['extra']],horizon=10)

def compact_catalogue():
 pools=[]; index={}; courses={}; days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
 for c in CATALOG:
  if not course_info(c)['planner_eligible']: continue
  semesters={}
  for s in (1,2):
   offer=next((x for x in CATALOG[c]['semesters'] if x['semester_number']==s),None)
   if not offer: continue
   groups,_=lesson_groups([c],s); packed=[]
   for _,kind,opts in groups:
    options=[]
    for lessons in opts.values():
     v=[[days.index(l['day']),minutes(l['startTime']),minutes(l['endTime']),sum(1<<w for w in l['weeks']) if isinstance(l['weeks'],list) else l['weeks']] for l in lessons]
     key=json.dumps(v,separators=(',',':'))
     if key not in index:index[key]=len(pools);pools.append(v)
     if index[key] not in options:options.append(index[key])
    packed.append(options)
   semesters[s]=[offer['exam_date_time'],offer['exam_duration'],packed]
  courses[c]=[int(CATALOG[c]['module_credit']),CATALOG[c]['prereq_tree'],semesters]
 return {'courses':courses,'packages':pools,'foundation':FOUNDATION,'categories':CATEGORIES,
         'focus_areas':{k:{kk:sorted(vv) if isinstance(vv,set) else vv for kk,vv in v.items()} for k,v in FOCUS_AREAS.items()},'minors':programmes(),
         'math_entry_waived':[c for c in courses if math_entry_waived(c)]}

def prompt(profile,level,context):
 req=request_for(profile)
 rules=[c.model_dump() for c in req.cards if c.strength=='hard']
 preferences=[c.model_dump() for c in req.cards if c.strength=='soft']
 text="""Produce a complete NUS CS degree course plan. Do not browse or use tools.
Return ONLY one JSON object: {"semesters":[["CS1101S",...], [...], ...]}.
Each array is the next chronological semester, starting Y1S1. Include at most 10 arrays.
Use real course codes once each, no placeholders or ellipses. Empty arrays are allowed.
Assumptions: AY2026/27 offerings, examination dates and all weekly lesson packages repeat
unchanged in future academic years. Start AY2026/27; no completed university courses;
student has H2 Mathematics and English entry eligibility; at most 10 semesters.
CS2101 shares the matching whole CS2103T teaching package, not an additional meeting.
Snapshot notation: courses[code]=[units,prerequisite_tree,semester_dictionary].
Each semester entry=[exam_ISO_datetime,exam_duration_minutes,lesson_type_groups].
Each lesson_type_group is a list of alternative package IDs; choose one complete package
per group. packages[id] is all its meetings [day0Monday,startMinute,endMinute,weeks].
Integer weeks is a bitmask (bit w means teaching week w); object weeks uses calendar dates.
Prerequisite strings before ':' denote courses taken in STRICTLY EARLIER semesters;
and/or/nOf trees retain their logical meaning. Only math_entry_waived entry conditions
are waived by this profile; this does not count the university courses as completed.
The catalogue supplies facts, not automatic degree requirements.
"""
 text+='\nSTUDENT TASK: '+PROFILES[profile]['instruction']
 if level in {'AP','APR'}:text+='\nEXPLICIT PREFERENCES: '+json.dumps(preferences,separators=(',',':'))
 if level=='APR':text+='\nEXPLICIT HARD REQUIREMENTS: '+json.dumps(rules,separators=(',',':'))
 text+='\nAllowed automatic course pool: '+','.join(sorted(c for c in allowed_courses(req) if course_info(c)['planner_eligible']))
 text+='\nFROZEN REFERENCE DATA:\n'+context
 return text

async def prepare():
 RUN.mkdir(parents=True,exist_ok=True)
 models=await available_model_details()
 dump(RUN/'models.json',models)
 canonical=[m['id'] for m in models if 'chat' in m.get('soclaas',{}).get('capabilities',[]) and not m.get('soclaas',{}).get('alias_of')]
 context=json.dumps(compact_catalogue(),separators=(',',':'))
 (RUN/'context.json').write_text(context)
 for profile in PROFILES:
  dump(RUN/'tasks'/f'{profile}.json',request_for(profile).model_dump())
  for level in LEVELS:
   p=RUN/'inputs'/f'{profile}-{level}.txt';p.parent.mkdir(exist_ok=True);p.write_text(prompt(profile,level,context))
 manifest={'frozen_at':datetime.now(timezone.utc).isoformat(),'protocol':'v1-exploratory-disclosure-ablation',
   'models_soclaas':canonical,'models_codex':['gpt-6-astra','gpt-6.1-sol'],
   'main_matrix':'base profile x A/AP/APR x all canonical models; one draw per cell',
   'human_extension':'math/qf APR x qwen3.6:35b,llama3.1:8b,gpt-6-astra,gpt-6.1-sol plus CSP',
   'human_selection':'These four direct methods and CSP, three tasks = 15 plans; if missing, use first available canonical model in models.json order, disclose replacement.',
   'temperature_soclaas':0,'max_tokens_soclaas':3500,'timeout_seconds_soclaas':180,
   'retries':0,'context_sha256':hashlib.sha256(context.encode()).hexdigest(),
   'no_tools':True,'codex_harness':'CLI --ignore-user-config --ignore-rules --ephemeral; read-only empty directory; medium reasoning. Hidden CLI instructions remain. Not API-equivalent; report separately.',
   'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
   'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
   'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'backend').glob('*.py'))},
   'data_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'assets/data').glob('*course_details.json'))}}
 dump(RUN/'manifest.json',manifest)
 print('Frozen',len(canonical),'SoCLaaS models; context bytes',len(context),flush=True)

def stem(model,profile,level):return re.sub(r'[^A-Za-z0-9_.-]','_',model)+'__'+profile+'__'+level

async def soc_run(model,profile,level,sem):
 name=stem(model,profile,level); target=RUN/'raw'/f'{name}.json'
 if target.exists():return
 async with sem:
  content=(RUN/'inputs'/f'{profile}-{level}.txt').read_text()
  payload={'model':model,'temperature':0,'max_tokens':3500,'messages':[{'role':'user','content':content}]}
  dump(RUN/'requests'/f'{name}.json',payload)
  started=time.monotonic();result={'model':model,'profile':profile,'level':level,'provider':'soclaas','started_at':datetime.now(timezone.utc).isoformat()}
  try:
   async with httpx.AsyncClient(timeout=httpx.Timeout(180,connect=15)) as client:
    r=await client.post(BASE_URL+'/chat/completions',headers={'Authorization':'Bearer '+os.environ['SOCLAAS_API_KEY']},json=payload)
    result['http_status']=r.status_code
    # Success bodies are research outputs. Gateway errors may contain routing secrets: retain safe status only.
    if r.is_success:result.update(status='received',response=r.json())
    else:result.update(status='service_error',error=f'HTTP {r.status_code}; body withheld to avoid internal routing/credential disclosure')
  except Exception as exc: result.update(status='transport_error',error=type(exc).__name__)
  result['elapsed_seconds']=round(time.monotonic()-started,3);dump(target,result)
  print(name,result['status'],result.get('http_status'),result['elapsed_seconds'],flush=True)

async def codex_run(model,profile,level,sem):
 name=stem(model,profile,level);target=RUN/'raw'/f'{name}.json'
 if target.exists():return
 async with sem:
  directory=RUN/'codex'/name;directory.mkdir(parents=True,exist_ok=True)
  empty=directory/'empty';empty.mkdir(exist_ok=True)
  out=directory/'answer.txt';prompt_path=RUN/'inputs'/f'{profile}-{level}.txt'
  command=['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check','-s','read-only','-C',str(empty),'-m',model,'-c','model_reasoning_effort="medium"','--json','-o',str(out),'-']
  dump(RUN/'requests'/f'{name}.json',{'command':command,'stdin_file':str(prompt_path.relative_to(RUN)),'temperature':'CLI default; not exposed','max_output_tokens':'CLI default; not equal to SoCLaaS cap'})
  started=time.monotonic();r={'model':model,'profile':profile,'level':level,'provider':'codex-cli','started_at':datetime.now(timezone.utc).isoformat()}
  proc=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  try:
   stdout,stderr=await asyncio.wait_for(proc.communicate(prompt_path.read_bytes()),timeout=300)
   (directory/'events.jsonl').write_bytes(stdout)
   # Do not publish internal stderr logs or authentication state.
   events=[json.loads(x) for x in stdout.decode().splitlines() if x.startswith('{')]
   items=[e.get('item',{}) for e in events if e.get('type')=='item.completed']
   tool_items=[i for i in items if i.get('type') not in {'agent_message','reasoning'}]
   r.update(status='received' if proc.returncode==0 and out.exists() and not tool_items else 'harness_error',
            returncode=proc.returncode,tool_item_types=[i.get('type') for i in tool_items],
            content=out.read_text() if out.exists() else '',usage=next((e.get('usage') for e in events if e.get('type')=='turn.completed'),None))
  except asyncio.TimeoutError:
   proc.kill();await proc.communicate();r.update(status='timeout')
  r['elapsed_seconds']=round(time.monotonic()-started,3);dump(target,r);print(name,r['status'],r['elapsed_seconds'],flush=True)

async def run_models():
 manifest=json.loads((RUN/'manifest.json').read_text());soc=asyncio.Semaphore(3);cod=asyncio.Semaphore(2)
 calls=[soc_run(m,'base',l,soc) for m in manifest['models_soclaas'] for l in LEVELS]
 calls += [codex_run(m,'base',l,cod) for m in manifest['models_codex'] for l in LEVELS]
 for p in ['math','qf']:
  calls += [soc_run(m,p,'APR',soc) for m in ['qwen3.6:35b','llama3.1:8b']]
  calls += [codex_run(m,p,'APR',cod) for m in manifest['models_codex']]
 await asyncio.gather(*calls)

def parse_output(raw):
 if raw['status']!='received':raise ValueError(raw['status'])
 content=raw.get('content')
 if content is None:content=raw['response']['choices'][0]['message'].get('content') or ''
 text=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip())
 obj=json.loads(text)
 if not isinstance(obj,dict) or set(obj)!={'semesters'}:raise ValueError('Expected exactly semesters key')
 semesters=obj['semesters']
 if not isinstance(semesters,list) or not 1<=len(semesters)<=10:raise ValueError('Expected 1..10 semester arrays')
 assignments={};unknown=[];duplicates=[]
 for s,codes in enumerate(semesters,1):
  if not isinstance(codes,list):raise ValueError('Semester must be an array')
  for c in codes:
   if not isinstance(c,str):raise ValueError('Course must be a string')
   if c in assignments:duplicates.append(c)
   if c not in CATALOG:unknown.append(c)
   assignments[c]=s
 if not assignments:raise ValueError('Empty schedule')
 return assignments,unknown,duplicates

def allocations_for(req,assignments):
 """Existential allocations, never require an LLM to output private solver variables.

 Enumerate minimal sufficient positive-credit subsets; supersets cannot improve
 disjointness/sharing. Time budget => explicitly unverified, never a proof of failure.
 """
 selected=set(assignments);started=time.monotonic();nodes=0
 def subsets(pool,units,count=None,exact=False,maxcount=None):
  pool=sorted(pool)
  for n in range(1,min(len(pool),maxcount or len(pool))+1):
   if count and n!=count:continue
   for sub in itertools.combinations(pool,n):
    credits=sum(int(CATALOG[c]['module_credit']) for c in sub)
    if credits<units or (exact and credits!=units):continue
    if not count and not exact and any(credits-int(CATALOG[c]['module_credit'])>=units for c in sub):continue
    yield list(sub)
 categories=[]
 for card in req.cards:
  for r in card.rules:
   if r.type!='category_units':continue
   pool=selected & (set(CATEGORIES['ID'])|set(CATEGORIES['CD']) if r.category=='ID_CD' else set(CATEGORIES[r.category]))
   opts=[sub for sub in subsets(pool,r.units) if r.category!='ID_CD' or (len(set(sub)&set(CATEGORIES['ID']))>=2 and len(set(sub)&(set(CATEGORIES['CD'])-set(CATEGORIES['ID'])))<=1)]
   categories.append((r.category,opts))
 # An unsatisfied category remains explicitly empty; continue to assess others.
 impossible=[k for k,v in categories if not v]
 categories=[(k,v or [[]]) for k,v in categories]
 minor_names=[r.programme for c in req.cards for r in c.rules if r.type=='minor_programme']
 group_options=[]
 for p in minor_names:
  for g in MINORS[p]['groups']:
   opts=list(subsets(selected & set(group_codes(g,CATALOG)),g['units'],g.get('count'),g.get('exact_units',False),g.get('max_count')))
   group_options.append(((p,g['id']),opts or [[]]))
 best=None
 for chosen in itertools.product(*(v for _,v in categories)):
  cat=dict(zip((k for k,_ in categories),chosen));flat=[c for v in cat.values() for c in v]
  if len(flat)!=len(set(flat)):continue
  if not minor_names:return cat,{},impossible,'verified'
  for minor_chosen in itertools.product(*(v for _,v in group_options)):
   nodes+=1
   if nodes>100000 or time.monotonic()-started>10:return cat,{},impossible,'allocation_timeout'
   alloc={p:{} for p in minor_names}
   for ((p,g),_),v in zip(group_options,minor_chosen):alloc[p][g]=v
   audit=audit_minors(req,assignments,alloc,cat)
   if best is None:best=(cat,alloc,impossible,'verified')
   if audit['status']=='passed':return cat,alloc,impossible,'verified'
 return best or ({},{},impossible,'verified')

def evaluate(raw):
 result={k:raw.get(k) for k in ['model','profile','level','provider','status','elapsed_seconds','http_status']}
 try:assignments,unknown,duplicates=parse_output(raw)
 except (ValueError,KeyError,TypeError,IndexError) as exc:
  return {**result,'evaluable':False,'parse_error':str(exc),'hard_types_failed':None}
 req=request_for(raw['profile']);known={c:s for c,s in assignments.items() if c in CATALOG}
 alloc,minor_alloc,missing_cats,alloc_status=allocations_for(req,known)
 details={};hard=[];soft=[];unverified=[]
 for card in req.cards:
  t=card.rules[0].type
  if t=='weekly_feasibility':
   checks={str(s):semester_selection([c for c,v in known.items() if v==s],(s-1)%2+1)['status'] for s in sorted(set(known.values()))}
   details['weekly_semesters']=checks
   if any(v in {'missing_data','timeout','conditional'} for v in checks.values()):unverified.append(card.id)
   passed=not any(v=='infeasible' for v in checks.values())
  elif t=='minor_programme':
   audit=audit_minors(req,known,minor_alloc,alloc);details['minor_audit']=audit;passed=audit['status']=='passed'
   if alloc_status!='verified':unverified.append(card.id);passed=True
  else:passed=all(rule_satisfied(r,known,req.horizon,alloc,req) for r in card.rules)
  if not passed:(hard if card.strength=='hard' else soft).append(card.id)
 if unknown:hard.append('unknown_courses')
 if duplicates:hard.append('duplicate_courses')
 ineligible=[c for c in known if not course_info(c)['planner_eligible']]
 if ineligible:hard.append('ineligible_courses')
 audit=academic_audit(known)
 details.update(academic_audit=audit,unknown_courses=unknown,duplicate_courses=duplicates,ineligible_courses=ineligible,
                category_allocations=alloc,minor_allocations=minor_alloc,allocation_status=alloc_status,
                exam_pairs=[(a,b,s) for a,b,s in exam_pairs() if a in known and b in known and known[a]==known[b] and (known[a]-1)%2+1==s])
 # One count per hard card (not all grounded CSP constraints); structural errors separate.
 return {**result,'evaluable':True,'assignments':assignments,'total_units':sum(int(CATALOG[c]['module_credit']) for c in known),
         'hard_card_failures':[c for c in hard if c in {x.id for x in req.cards}],
         'structural_failures':[c for c in hard if c not in {x.id for x in req.cards}],
         'hard_types_failed':len(hard),'unverified_hard_cards':unverified,'hard_pass':not hard and not unverified and alloc_status=='verified',
         'unmet_preferences':soft,'details':details}

def evaluate_all():
 results=[]
 for p in sorted((RUN/'raw').glob('*.json')):
  raw=json.loads(p.read_text());res=evaluate(raw);results.append(res);dump(RUN/'evaluated'/p.name,res)
 dump(RUN/'results.json',results)
 print('Evaluated',len(results),'responses',flush=True)

def run_csp():
 from backend.solver import generate_plan
 for profile in PROFILES:
  p=RUN/'csp'/f'{profile}.json'
  if p.exists():continue
  result=generate_plan(request_for(profile));dump(p,result);print('CSP',profile,result['status'],flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','models','evaluate','csp']);args=parser.parse_args()
 if args.action=='prepare':asyncio.run(prepare())
 elif args.action=='models':asyncio.run(run_models())
 elif args.action=='evaluate':evaluate_all()
 else:run_csp()
