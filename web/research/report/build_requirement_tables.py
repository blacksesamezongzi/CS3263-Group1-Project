"""Report necessary-requirement compliance from saved, independently checked plans.

Only aggregation/presentation changes: no new model calls and no invented scores.
"""
from pathlib import Path
import csv
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from research.experiments.benchmark import RUN, request_for, evaluate
from backend.catalog import CATALOG
from backend.validation import rule_satisfied

HERE=Path(__file__).resolve().parent
results=json.loads((RUN/'results.json').read_text())
short={'qwen3.6:35b':'Qwen 3.6','qwen3-coder-next':'Qwen Coder','qwen3-vl:32b':'Qwen VL','gpt-6-astra':'Astra','gpt-6.1-sol':'Sol'}
ORDER=list(short)
GE={'gec','gea','gess','gen','idcd'}
def metrics(r):
 d=r['details'];a=d['academic_audit'];failed=set(r['hard_card_failures']);assign={c:s for c,s in r['assignments'].items() if c in CATALOG}
 req=request_for('base');loads={s:sum(int(CATALOG[c]['module_credit']) for c,v in assign.items() if v==s) for s in range(1,11)}
 return {'model':r['model'],'condition':r['level'],
  'prerequisite_courses_failed':len(a['prerequisite_violations']),
  'foundation_courses_missing':len(a['missing_foundation_courses']),
  'degree_units_shortfall':max(0,160-r['total_units']),
  'focus_requirement_failed':int('focus' in failed),
  'ge_id_buckets_failed':len(GE&failed),
  'corequisite_pair_failed':int('coreqs' in failed),
  'unavailable_course_assignments':sum((s-1)%2+1 not in [x['semester_number'] for x in CATALOG[c]['semesters']] for c,s in assign.items()),
  'exam_conflict_pairs':len(d['exam_pairs']),
  'weekly_semesters_infeasible':sum(v=='infeasible' for v in d['weekly_semesters'].values()),
  'weekly_semesters_unverified':sum(v in {'missing_data','timeout','conditional'} for v in d['weekly_semesters'].values()),
  'semester_load_violations':sum(v>0 and not 16<=v<=(20 if s==1 else 24) for s,v in loads.items()),
  'fully_verified':r['hard_pass']}
base=[r for r in results if r['profile']=='base' and r['evaluable']]
records=[]
for model in ORDER:
 for level in ['A','AP','APR']:
  r=next((r for r in base if r['model']==model and r['level']==level),None)
  if r:records.append(metrics(r))
csp=json.loads((RUN/'csp-evaluated/base.json').read_text());control=metrics(csp);control['condition']='APR';control['model']='Pathway CSP'
records.append(control)
(RUN/'requirement_compliance.json').write_text(json.dumps(records,indent=2)+'\n')
with (RUN/'requirement_compliance.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)

def val(v):return r'\okzero' if v==0 else r'\badcount{'+str(v)+'}'
lines=[r'\begin{table}[htbp]\centering',r'\begin{tabular}{@{}llrrrrrr@{}}\toprule',
 r'Method & Input & Prereq. & Core & Units & Focus & GE/ID & Pair\\\midrule']
last=None
for r in records:
 model=r['model'];name=short.get(model,model)
 if last is not None and last!=model:lines.append(r'\addlinespace[2pt]')
 if model=='Pathway CSP':lines.append(r'\midrule')
 values=[r[k] for k in ['prerequisite_courses_failed','foundation_courses_missing','degree_units_shortfall','focus_requirement_failed','ge_id_buckets_failed','corequisite_pair_failed']]
 lines.append(name+' & '+r['condition']+' & '+' & '.join(val(v) for v in values)+r' \\')
 last=model
lines += [r'\bottomrule\end{tabular}',r'\caption{Violations of implemented academic requirements; lower is better. Prereq.: courses with an unsatisfied earlier-prerequisite tree. Core: missing foundation courses. Units: deficit below 160. Focus: failed AI-focus rule (0/1). GE/ID: failed GEC, GEA, GESS, GEN or ID/CD buckets (0--5). Pair: failed CS2101/CS2103T pairing (0/1). Every row is one actual generated plan; no error response is scored as a plan.}\label{tab:academic}',r'\end{table}']
(HERE/'academic_results.tex').write_text('\n'.join(lines)+'\n')

lines=[r'\begin{table}[htbp]\centering',r'\begin{tabular}{@{}lrrrrr@{}}\toprule',r'Method (APR) & Offering & Exams & Weekly & Unknown & Load\\\midrule']
for r in records:
 if r['condition']!='APR':continue
 values=[r[k] for k in ['unavailable_course_assignments','exam_conflict_pairs','weekly_semesters_infeasible','weekly_semesters_unverified','semester_load_violations']]
 cells=[(r'\unknowncount{'+str(v)+'}' if j==3 and v else val(v)) for j,v in enumerate(values)]
 lines.append(short.get(r['model'],r['model'])+' & '+' & '.join(cells)+r' \\')
lines += [r'\bottomrule\end{tabular}',r'\caption{Schedule-level checks under full rule disclosure. Offering counts courses assigned to an unavailable semester; Exams counts overlapping pairs; Weekly counts semesters with proven lesson incompatibility; Unknown counts semesters with missing lesson data or timeout; Load counts semesters outside the editable project workload bounds. Unknown is not a proven violation.}\label{tab:temporal}',r'\end{table}']
(HERE/'temporal_results.tex').write_text('\n'.join(lines)+'\n')

lines=[r'\begin{table}[htbp]\centering',r'\begin{tabular}{@{}lrrrrrr@{}}\toprule',r'Method & $n$ & Pref. & Feasib. & Progress & Clarity & Overall\\\midrule']
for name in ['Pathway CSP','Qwen 3.6','Qwen Coder','Astra','Sol']:
 lines.append(name+r' & 0/6 & TBC & TBC & TBC & TBC & TBC \\')
lines += [r'\bottomrule\end{tabular}',r'\caption{Qualitative results template, not measured outcomes. TBC means to be collected; no numerical placeholder is a participant score. Each method has three tasks and two independent raters, giving six planned ratings per dimension. Final cells will report median [minimum, maximum] on the anchored 1--5 scale.}\label{tab:qualitative}',r'\end{table}']
(HERE/'qualitative_results.tex').write_text('\n'.join(lines)+'\n')

# Keep complete coverage visible in the separate raw-data appendix, not the main compliance table.
models=json.loads((RUN/'manifest.json').read_text())
coverage=[]
for model in models['models_soclaas']+models['models_codex']:
 rs=[r for r in results if r['profile']=='base' and r['model']==model]
 coverage.append({'model':model,'requested':len(rs),'evaluable':sum(r['evaluable'] for r in rs),'APR_evaluable':any(r['level']=='APR' and r['evaluable'] for r in rs)})
(RUN/'requirement_coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
print('Built academic, timetable and explicitly pending qualitative tables from',len(base),'actual base plans.')
