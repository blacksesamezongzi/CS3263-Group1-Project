"""Small, separately labelled end-to-end parser probes using production code."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from research.experiments.benchmark import RUN, dump, request_for
from backend.llm import parse_preference
from backend.schemas import ParseRequest, PlanRequest
from backend.defaults import default_cards
from backend.solver import generate_plan
import httpx

async def main():
 real=httpx.AsyncClient
 messages={'base':'I prefer finishing within 8 semesters and about 20 units per active semester.',
           'math':'Complete a Mathematics minor. I prefer CS2102 in semester 3.',
           'qf':'Complete a Quantitative Finance minor. I prefer CS2102 in semester 3.'}
 for profile,message in messages.items():
  target=RUN/'parser'/f'{profile}.json'
  if target.exists():continue
  recorded={}
  class Recorder:
   def __init__(self,*a,**kw):self.client=real(*a,**kw)
   async def __aenter__(self):await self.client.__aenter__();return self
   async def __aexit__(self,*a):return await self.client.__aexit__(*a)
   async def post(self,url,**kw):
    recorded['request']=kw['json']
    response=await self.client.post(url,**kw)
    recorded['http_status']=response.status_code
    if response.is_success:recorded['response']=response.json()
    return response
  # Existing defaults are context. The base instruction should not need duplicate goals.
  try:
   with patch('backend.llm.httpx.AsyncClient',Recorder):
    parsed=await parse_preference(ParseRequest(message=message,cards=default_cards(),horizon=10))
   recorded['parsed']=parsed.model_dump()
   oracle=[(r.type,getattr(r,'programme',None),getattr(r,'course',None),getattr(r,'semester',None),c.strength)
           for c in request_for(profile).cards for r in c.rules if c.source=='user']
   actual=[(r.type,getattr(r,'programme',None),getattr(r,'course',None),getattr(r,'semester',None),c.strength)
           for c in parsed.cards for r in c.rules]
   recorded['expected_extra_semantics']=oracle
   recorded['extra_semantics_match']=sorted(actual)==sorted(oracle) if profile!='base' else None
   if profile!='base' and not parsed.needs_clarification:
    # Persist actual produced cards and solve once, without changing them to the oracle.
    req=PlanRequest(cards=default_cards()+parsed.cards,horizon=10)
    recorded['plan_request']=req.model_dump()
    recorded['solver_result']=await asyncio.to_thread(generate_plan,req)
  except Exception as exc:recorded['error_type']=type(exc).__name__
  dump(target,recorded);print(profile,recorded.get('extra_semantics_match'),recorded.get('solver_result',{}).get('status'),flush=True)

asyncio.run(main())
