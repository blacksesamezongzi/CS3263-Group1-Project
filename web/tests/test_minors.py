import copy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.defaults import default_cards
from backend.schemas import ConstraintCard, PlanRequest
from backend.catalog import CATALOG, MINOR_SUPPLEMENT
from backend.minors import MINORS, audit_minors, selected_minors
from backend.solver import generate_plan
from backend.validation import check_plan

client = TestClient(app)


def minor_card(programme):
    return ConstraintCard(id='minor_' + programme, title=programme,
                          rules=[{'type': 'minor_programme', 'programme': programme}])


def test_minor_contract_catalogue_and_plain_model_prompts_share_the_official_templates():
    config = client.get('/api/config').json()
    assert len(config['defaults']) == 16  # Minors are opt-in.
    assert {p['id'] for p in config['minors']} == set(MINORS)
    assert len(MINOR_SUPPLEMENT) == 57
    assert all(c in CATALOG for c in ['QF1100', 'QF2104', 'QF3101', 'MA2101', 'MA2108'])
    maths = next(p for p in config['minors'] if p['id'] == 'mathematics')
    assert 'CS1231S' in maths['groups'][0]['courses']
    assert 'MA1301' not in maths['groups'][0]['courses']
    assert 'MA3288' not in maths['groups'][2]['courses']
    qf = next(p for p in config['minors'] if p['id'] == 'quantitative_finance')
    assert 'MA2301' not in qf['groups'][1]['courses']
    assert 'ST2334' in qf['groups'][1]['courses']
    prompts = client.get('/api/chat/config').json()['minor_prompt_cards']
    assert len(prompts) == 2 and all(p['prompt_category'] == 'minor' for p in prompts)
    assert all('12 units' in p['prompt'] and '8 units' in p['prompt'] for p in prompts)
    with pytest.raises(ValidationError):
        ConstraintCard(id='soft', title='minor', strength='soft', rules=[{'type': 'minor_programme', 'programme': 'mathematics'}])
    with pytest.raises(ValidationError):
        PlanRequest(start_year=2020, cards=[minor_card('mathematics')])
    with pytest.raises(ValidationError):
        ConstraintCard(id='unsupported', title='minor', rules=[{'type': 'minor_programme', 'programme': 'financial_mathematics'}])


@pytest.fixture(scope='module')
def two_minor_plan():
    request = PlanRequest(cards=default_cards() + [minor_card(p) for p in MINORS])
    result = generate_plan(request)
    assert result['status'] == 'feasible', result
    assignments = {c['code']: s['number'] for s in result['semesters'] for c in s['courses']}
    return request, result, assignments


def test_real_csp_supports_two_minors_with_prerequisites_and_clash_free_weeks(two_minor_plan):
    request, result, assignments = two_minor_plan
    assert result['academic_audit']['status'] == 'passed'
    assert result['minor_audit']['status'] == 'passed'
    assert result['weekly_verified'] is True
    assert all(t['status'] == 'feasible' for t in result['weekly_timetables'].values())
    assert result['total_units'] == sum(int(CATALOG[c]['module_credit']) for c in assignments)
    assert check_plan(request, assignments, result['category_allocations'], result['minor_allocations'])[0] == []
    for p in result['minor_audit']['programmes']:
        assert p['units'] >= 20 and p['distinct_units'] >= 12 and p['shared_units'] <= 8
    assert assignments['QF1100'] < assignments['QF2104'] < assignments['QF3101']
    assert not {'MA1301', 'MA1301X'} & assignments.keys()  # H2 profile also excludes bridging electives.
    assert all(p in result['minor_allocations'] for p in MINORS)


def test_checker_rejects_missing_groups_reuse_and_forged_minor_exports(two_minor_plan):
    request, result, assignments = two_minor_plan
    broken = copy.deepcopy(result['minor_allocations'])
    broken['quantitative_finance']['fundamentals'] = []
    audit = audit_minors(request, assignments, broken, result['category_allocations'])
    assert audit['status'] == 'failed'
    duplicate = copy.deepcopy(result['minor_allocations'])
    duplicate['mathematics']['advanced'] += duplicate['mathematics']['foundation'][:1]
    assert audit_minors(request, assignments, duplicate, result['category_allocations'])['status'] == 'failed'
    payload = {'assignments': assignments, 'horizon': request.horizon, 'start_year': request.start_year,
               'minors': selected_minors(request), 'minor_allocations': result['minor_allocations'],
               'category_allocations': result['category_allocations']}
    assert client.post('/api/exports/nusmods', json=payload).status_code == 200
    payload['minor_allocations'] = broken
    response = client.post('/api/exports/nusmods', json=payload)
    assert response.status_code == 409
    assert response.json()['detail']['minor_audit']['status'] == 'failed'


def test_removing_a_minor_card_removes_that_programme_from_joint_checks(two_minor_plan):
    _, result, assignments = two_minor_plan
    remaining = PlanRequest(cards=[minor_card('quantitative_finance')])
    audit = audit_minors(remaining, assignments, {'quantitative_finance': result['minor_allocations']['quantitative_finance']}, result['category_allocations'])
    assert audit['status'] == 'passed'
    assert [p['id'] for p in audit['programmes']] == ['quantitative_finance']


def test_math_minor_cannot_reuse_three_cs_foundation_courses_as_twelve_shared_units():
    request = PlanRequest(cards=[minor_card('mathematics')])
    allocation = {'mathematics': {'foundation': ['CS1231S', 'MA1521'],
                                'intermediate': ['ST2334', 'MA2101'], 'advanced': ['MA3210']}}
    assignments = {c: 1 for pool in allocation['mathematics'].values() for c in pool}
    audit = audit_minors(request, assignments, allocation)
    assert audit['status'] == 'failed'
    assert audit['programmes'][0]['shared_units'] == 12
    assert any('More than 8 units' in error for error in audit['violations'])
