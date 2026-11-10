import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.main import app
from backend.schemas import ConstraintCard, ParseRequest, PlanRequest
from backend.defaults import default_cards
from backend.solver import generate_plan
from backend.validation import prerequisite_met, check_plan, academic_audit
from backend.nusmods import clashes, select_lessons, planner_export

client = TestClient(app)


def card(id, rules, strength="hard"):
    return ConstraintCard(id=id, title=id, rules=rules, strength=strength)


def test_contract_rejects_unknown_rules_courses_and_unsupported_soft_rules():
    for rule in ({"type": "python", "code": "pass"}, {"type": "course_in_semester", "course": "CS9999", "semester": 3}):
        response = client.post("/api/plans", json={"cards": [{"id": "bad", "title": "bad", "rules": [rule]}]})
        assert response.status_code == 422
    with pytest.raises(ValidationError):
        card("bad", [{"type": "prerequisites"}], "soft")
    with pytest.raises(ValidationError):
        PlanRequest(cards=[card("same", [{"type": "prerequisites"}])]*2)
    with pytest.raises(ValidationError):
        PlanRequest(horizon=8, cards=[card("too-late", [{"type": "course_in_semester", "course": "CS2102", "semester": 9}])])


def test_configuration_is_fresh_and_never_exposes_credentials(monkeypatch):
    monkeypatch.setenv("SOCLAAS_API_KEY", "test-secret-do-not-leak")
    config = client.get("/api/config").json()
    assert len(config["defaults"]) == 16
    assert config["defaults"][0]["rules"][0]["units"] == 160
    assert "test-secret-do-not-leak" not in client.get("/api/health").text
    config["defaults"].clear()
    assert len(client.get("/api/config").json()["defaults"]) == 16
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.post("/api/plans", json={"cards": []}, headers={"Origin": "https://unrelated.example"}).status_code == 403


def test_prerequisite_checker_handles_and_or_and_missing_branches():
    tree = {"and": [{"or": ["CS9999:D", "CS1101S:D"]}, "CS1231S:D"]}
    assert prerequisite_met(tree, 3, {"CS1101S": 1, "CS1231S": 2})
    assert not prerequisite_met(tree, 2, {"CS1101S": 1, "CS1231S": 2})
    assert not prerequisite_met({"and": ["CS1101S:D", "CS9999:D"]}, 3, {"CS1101S": 1})
    assert not prerequisite_met({"unsupported": []}, 3, {})


def test_multi_rule_card_removal_reaches_real_solver_and_requests_are_isolated():
    pin = card("pin", [{"type": "course_in_semester", "course": "CS2102", "semester": 3},
                       {"type": "require_courses", "courses": ["CS1231S"]}])
    exclude = card("exclude", [{"type": "exclude_courses", "courses": ["CS2102", "CS1231S"]}])
    conflict = generate_plan(PlanRequest(cards=[pin, exclude]))
    assert conflict["status"] == "infeasible"
    # Removing the box removes BOTH of its rules. Two workers must not share state.
    with ThreadPoolExecutor(max_workers=2) as pool:
        removed_future = pool.submit(generate_plan, PlanRequest(cards=[exclude]))
        pinned_future = pool.submit(generate_plan, PlanRequest(cards=[pin]))
        removed, pinned = removed_future.result(), pinned_future.result()
    assert removed["status"] == pinned["status"] == "feasible"
    assert not any(s["courses"] for s in removed["semesters"])
    assert any(c["code"] == "CS2102" for c in pinned["semesters"][2]["courses"])
    assert sum(c["code"] == "CS1231S" for s in pinned["semesters"] for c in s["courses"]) == 1


def test_real_default_plan_with_user_instruction_passes_independent_checker():
    cards = default_cards() + [card("user-pin", [{"type": "course_in_semester", "course": "CS2102", "semester": 3}])]
    request = PlanRequest(cards=cards)
    response = client.post("/api/plans", json=request.model_dump())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "feasible", result
    assert result["total_units"] >= 160
    assert result['weekly_verified']
    assert result['academic_audit']['status']=='passed'
    assert result['exportable'] is True
    assert all(t['status']=='feasible' for t in result['weekly_timetables'].values())
    assert any(c["code"] == "CS2102" for c in result["semesters"][2]["courses"])
    assignments = {c["code"]: s["number"] for s in result["semesters"] for c in s["courses"]}
    assert not {'MA1301', 'MA1301X'} & assignments.keys()
    assert check_plan(request, assignments,result['category_allocations'])[0] == []
    native = result["nusmods_planner"]
    assert native["minYear"] == "2026-2027"
    cs2102 = next(m for m in native["modules"].values() if m["moduleCode"] == "CS2102")
    assert cs2102["year"] == "2027-2028" and cs2102["semester"] == 1
    assert native['custom']=={}
    assert not any(c['placeholder'] for s in result['semesters'] for c in s['courses'])
    assert assignments['CS2101']==assignments['CS2103T']
    assert all(len(group)==len(set(group)) for group in result['category_allocations'].values())
    assert check_plan(request,assignments,result['category_allocations'])[0]==[]
    assert all(entry["id"] == key for key, entry in native["modules"].items())
    exported = client.post('/api/exports/nusmods',json={'assignments':assignments,
        'horizon':request.horizon,'start_year':request.start_year,'math_qualified':request.math_qualified})
    assert exported.status_code==200,exported.text
    assert exported.json()==native
    # Older/browser-modified plans must not bypass the profile restriction.
    for bridge in ('MA1301', 'MA1301X'):
        blocked = client.post('/api/exports/nusmods', json={
            'assignments': {**assignments, bridge: 10}, 'horizon': 10,
            'start_year': request.start_year, 'math_qualified': True})
        assert blocked.status_code == 409
        assert blocked.json()['detail']['academic_audit']['profile_violations'][0]['course'] == bridge


@pytest.mark.parametrize('bridge', ['MA1301', 'MA1301X'])
def test_h2_profile_excludes_bridging_even_with_explicit_pins_but_allows_unqualified_route(bridge):
    cards = [card('bridge-route', [
        {'type': 'course_in_semester', 'course': bridge, 'semester': 1},
        {'type': 'course_in_semester', 'course': 'CS1231S', 'semester': 2},
        {'type': 'course_in_semester', 'course': 'MA1521', 'semester': 2},
        {'type': 'course_in_semester', 'course': 'MA1522', 'semester': 2},
        {'type': 'exclude_courses', 'courses': ['MA1301X' if bridge == 'MA1301' else 'MA1301']},
        {'type': 'prerequisites'}])]
    qualified = PlanRequest(cards=cards, horizon=2, math_qualified=True)
    assert generate_plan(qualified)['status'] == 'infeasible'
    # The same cards remain meaningful for a student without H2 qualification.
    unqualified = qualified.model_copy(update={'math_qualified': False})
    result = generate_plan(unqualified)
    assert result['status'] == 'feasible', result
    assignments = {c['code']: s['number'] for s in result['semesters'] for c in s['courses']}
    assert assignments[bridge] == 1 and assignments['CS1231S'] == 2
    assert assignments['MA1521'] == assignments['MA1522'] == 2
    assert check_plan(unqualified, assignments)[0] == []
    # Profile eligibility is enforced independently of removable rule cards.
    empty = PlanRequest(cards=[], math_qualified=True)
    assert check_plan(empty, assignments)[0][0]['id'] == 'math-profile'
    assert academic_audit(assignments, math_qualified=True)['profile_violations'][0]['course'] == bridge
    assert academic_audit(assignments, math_qualified=False)['profile_violations'] == []
    # Pinning the foundation courses alongside the bridge is not completion first.
    same_semester = unqualified.model_dump()
    same_semester['cards'][0]['rules'][0]['semester'] = 2
    assert generate_plan(PlanRequest(**same_semester))['status'] == 'infeasible'


def test_without_h2_all_recognised_entry_courses_require_an_earlier_bridge():
    from backend.catalog import CATALOG, MATH_BRIDGING_COURSES, math_entry_waived
    from backend.validation import rule_satisfied
    prerequisite = card('entry', [{'type': 'prerequisites'}]).rules[0]
    request = PlanRequest(cards=[], math_qualified=False)
    courses = [c for c in CATALOG if math_entry_waived(c)]
    assert {'CS1231S', 'MA1521', 'MA1522', 'QF1100'} <= set(courses)
    for course in courses:
        for bridge in MATH_BRIDGING_COURSES:
            for bridge_semester in (0, 2, 3):
                assignments = {course: 2, bridge: bridge_semester}
                assert not rule_satisfied(prerequisite, assignments, 4, request=request), (course, assignments)
                assert course in {v['course'] for v in academic_audit(assignments, math_qualified=False)['prerequisite_violations']}
            assignments = {course: 2, bridge: 1}
            assert rule_satisfied(prerequisite, assignments, 4, request=request), (course, bridge)
            assert not academic_audit(assignments, math_qualified=False)['prerequisite_violations']


def test_academic_audit_catches_the_reported_cs1231s_and_advanced_course_case():
    assignments={'CS3264':1,'CS4243':1,'CS3234':4,'CS4277':4}
    audit=academic_audit(assignments,math_qualified=True)
    assert audit['status']=='failed'
    assert 'CS1231S' in audit['missing_foundation_courses']
    errors={v['course']:v for v in audit['prerequisite_violations']}
    assert errors.keys()==assignments.keys()
    assert 'CS1231S' in errors['CS3234']['requirement']
    assert 'CS2109S' in errors['CS3264']['requirement']
    # H2 Maths satisfies entry qualifications, not completion of CS1231S itself.
    assert academic_audit({'CS3234':2},math_qualified=True)['prerequisite_violations']
    assert not academic_audit({'CS1231S':1,'CS3234':2},math_qualified=True)['prerequisite_violations']
    assert academic_audit({'CS1231S':2,'CS3234':2},math_qualified=True)['prerequisite_violations']


def test_deleted_prerequisite_card_keeps_solver_semantics_but_invalid_preview_cannot_export():
    pin=card('too-early',[{'type':'course_in_semester','course':'CS3264','semester':1}])
    preview=client.post('/api/plans',json=PlanRequest(cards=[pin]).model_dump()).json()
    assert preview['status']=='feasible'  # The deleted rule is not silently reinserted.
    assert preview['academic_audit']['status']=='failed'
    assert preview['exportable'] is False
    assert 'nusmods_planner' not in preview
    assignments={c['code']:s['number'] for s in preview['semesters'] for c in s['courses']}
    exported=client.post('/api/exports/nusmods',json={'assignments':assignments,'horizon':10,'start_year':2026})
    assert exported.status_code==409
    assert exported.json()['detail']['academic_audit']['status']=='failed'
    # With the actual prerequisite card restored, semester 1 is impossible.
    enforced=generate_plan(PlanRequest(cards=[pin,card('prereqs',[{'type':'prerequisites'}])]))
    assert enforced['status']=='infeasible'


def test_export_rechecks_foundation_and_prerequisites_instead_of_trusting_the_browser():
    from backend.catalog import FOUNDATION
    assignments={c:1 for c in FOUNDATION}
    assert client.post('/api/exports/nusmods',json={'assignments':assignments,'horizon':10,'start_year':2026}).status_code==409
    unknown=client.post('/api/exports/nusmods',json={'assignments':{'CS9999':1},'horizon':10,'start_year':2026})
    assert unknown.status_code==422


def test_real_catalogue_has_official_categories_and_no_placeholder_entries():
    config=client.get('/api/config').json()
    courses={c['code']:c for c in config['catalogue']}
    assert len(courses)>=279
    assert not {'ID1','ID2','CD','GEC','GEA','GESS','GEN'} & courses.keys()
    assert 'ID' in courses['DTK1234']['categories']
    assert 'CD' in courses['EL1101E']['categories']
    assert 'GEA' in courses['GEA1000']['categories']
    assert courses['DTK1234']['source_urls']
    assert all(c['source_urls'] for c in courses.values() if c['categories'])
    assert client.get('/extension').status_code==404


def test_coupled_cs2101_cs2103t_have_one_shared_class_package():
    from backend.attendance import semester_selection
    single=semester_selection(['CS2103T'],1)
    paired=semester_selection(['CS2101','CS2103T'],1)
    assert paired['status']=='feasible'
    assert len(paired['lessons'])==len(single['lessons'])
    assert any(l.get('sharedWith')==['CS2101'] for l in paired['lessons'])
    same=generate_plan(PlanRequest(cards=[card('pair',[{'type':'corequisites'},{'type':'weekly_feasibility'},
        {'type':'course_in_semester','course':'CS2103T','semester':3}])]))
    assigned={c['code']:s['number'] for s in same['semesters'] for c in s['courses']}
    assert same['status']=='feasible'
    assert assigned['CS2101']==assigned['CS2103T']==3
    incompatible=generate_plan(PlanRequest(cards=[card('different',[{'type':'corequisites'},
        {'type':'course_in_semester','course':'CS2101','semester':2},
        {'type':'course_in_semester','course':'CS2103T','semester':3}])]))
    assert incompatible['status']=='infeasible'


def test_weekly_conflict_is_rejected_during_degree_solving():
    from backend.attendance import fixed_conflicts
    from backend.catalog import CATALOG,course_info
    a,b=fixed_conflicts([c for c in CATALOG if course_info(c)['planner_eligible']],1)[0]
    pinned=card('clash',[{'type':'course_in_semester','course':a,'semester':1},
                         {'type':'course_in_semester','course':b,'semester':1}])
    without=generate_plan(PlanRequest(cards=[pinned]))
    with_weekly=generate_plan(PlanRequest(cards=[pinned,card('weekly',[{'type':'weekly_feasibility'}])]))
    assert without['status']=='feasible'
    assert with_weekly['status']=='infeasible'


def test_pairwise_feasibility_does_not_prove_a_complete_weekly_plan():
    from itertools import combinations
    groups=[(code,'Tutorial',{'1':[lesson(code,'1000','1100')],
                             '2':[lesson(code,'1100','1200')]}) for code in ['A','B','C']]
    assert all(select_lessons(list(pair))[2]=='feasible' for pair in combinations(groups,2))
    assert select_lessons(groups)[2]=='infeasible'


def lesson(code, start="1000", end="1100", weeks=None, **extra):
    return {"course": code, "day": "Monday", "startTime": start, "endTime": end,
            "weeks": weeks if weeks is not None else [1, 2], **extra}


def test_class_selection_preserves_meetings_and_checks_weeks():
    a = lesson("CS1101S")
    b = lesson("CS1231S", "1030", "1130")
    assert clashes(a, b)
    assert not clashes(a, lesson("CS1231S", weeks=[3]))
    assert not clashes(a, lesson("CS1231S", "1100", "1200"))
    groups = [("CS1101S", "Lecture", {"1": [a, lesson("CS1101S", "1400", "1500")]}),
              ("CS1231S", "Tutorial", {"1": [b], "2": [lesson("CS1231S", "1200", "1300")]})]
    lessons, selected, status = select_lessons(groups)
    assert status == "feasible" and len(lessons) == 3
    assert selected[("CS1231S", "Tutorial")] == "2"
    assert select_lessons([(g[0], g[1], {"1": g[2]["1"]}) for g in groups])[2] == "infeasible"


def test_date_based_weeks():
    a = lesson("CS1101S", weeks={"start": "2026-08-10", "end": "2026-08-31", "weekInterval": 2})
    b = lesson("CS1231S", weeks={"start": "2026-08-17", "end": "2026-08-31", "weekInterval": 2})
    assert not clashes(a, b)
    assert clashes(a, {**b, "weeks": {"start": "2026-08-10", "end": "2026-08-31"}})


def test_model_output_is_validated_before_any_card_is_added(monkeypatch):
    from backend import llm
    monkeypatch.setenv("SOCLAAS_API_KEY", "test-key")
    monkeypatch.setenv("SOCLAAS_MODEL", "test-model")
    payload = {"reply": "已添加", "cards": [{"id": "new", "title": "第三学期上 CS2102", "rules": [
        {"type": "course_in_semester", "course": "CS2102", "semester": 3}]}], "needs_clarification": False}

    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            assert url.endswith("/v1/chat/completions")
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            return FakeResponse()

    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
    result = asyncio.run(llm.parse_preference(ParseRequest(message="第三学期上CS2102")))
    assert result.cards[0].id.startswith("user_")
    assert result.cards[0].rules[0].semester == 3
    payload["cards"][0]["rules"][0]["course"] = "CS9999"
    with pytest.raises(llm.ModelError, match="invalid constraint"):
        asyncio.run(llm.parse_preference(ParseRequest(message="bad")))
    payload["cards"][0]["rules"][0]["course"] = "CS2102"
    payload["needs_clarification"] = True
    with pytest.raises(llm.ModelError):
        asyncio.run(llm.parse_preference(ParseRequest(message="ambiguous")))
