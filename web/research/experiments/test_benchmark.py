import json
from research.experiments.benchmark import evaluate, parse_output, request_for
from backend.validation import prerequisite_met

def raw(semesters):
 return dict(model='test',profile='base',level='APR',provider='test',status='received',content=json.dumps({'semesters':semesters}))

def test_same_semester_is_not_prerequisite_completion():
 assert not prerequisite_met({'or':['CS1231S','CS1231']},2,{'CS1231S':2})
 assert prerequisite_met({'or':['CS1231S','CS1231']},2,{'CS1231S':1})

def test_service_failure_has_no_violation_count():
 r=evaluate({**raw([['CS1101S']]),'status':'service_error'})
 assert not r['evaluable'] and r['hard_types_failed'] is None

def test_unknown_and_duplicate_courses_are_structural_failures():
 r=evaluate(raw([['CS1101S','FAKE9999'],['CS1101S']]))
 assert set(r['structural_failures'])=={'unknown_courses','duplicate_courses'}
 assert not r['hard_pass']

def test_empty_schedule_cannot_count_as_verified():
 r=evaluate(raw([[],[]]))
 assert not r['evaluable']

def test_user_minor_task_really_adds_minor_and_soft_pin():
 req=request_for('qf')
 assert any(r.type=='minor_programme' and r.programme=='quantitative_finance' for c in req.cards for r in c.rules)
 assert any(c.strength=='soft' and r.type=='course_in_semester' and r.semester==3 for c in req.cards for r in c.rules)
