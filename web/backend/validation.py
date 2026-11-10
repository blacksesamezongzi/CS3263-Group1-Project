"""Independent, ordinary-Python checks of the solver's course assignments."""
from datetime import datetime, timedelta
from itertools import combinations
from backend.catalog import CATALOG, FOCUS_AREAS, CATEGORIES, FOUNDATION, MATH_BRIDGING_COURSES, math_entry_waived


def profile_violations(assignments, *, math_qualified):
    return [{'course': code, 'semester': semester,
             'requirement': 'H2 Mathematics qualification excludes MA1301 and MA1301X bridging courses.'}
            for code, semester in sorted(assignments.items())
            if math_qualified and semester > 0 and code in MATH_BRIDGING_COURSES]

def prerequisite_description(tree):
    if tree is None:
        return 'No course prerequisite'
    if isinstance(tree, str):
        return tree.split(':')[0]
    if isinstance(tree, dict) and len(tree) == 1:
        operator, children = next(iter(tree.items()))
        if operator in {'and', 'or'}:
            return '(' + f' {operator.upper()} '.join(prerequisite_description(t) for t in children) + ')'
        if operator == 'nOf':
            return f'At least {children[0]} of (' + ', '.join(prerequisite_description(t) for t in children[1]) + ')'
        if operator == 'cohort':
            return 'Applicable matriculation cohort'
    return 'Unsupported prerequisite; requires review'


def academic_audit(assignments, *, math_qualified=True, start_year=2026):
    """Always audit academic validity, even when a student deletes solver cards.

    Deleting a card still changes the CSP. It must not turn an invalid preview
    into an exportable study plan. Mathematics eligibility waives recognised
    bridging/entry qualifications; it never marks university courses taken.
    """
    selected = {code: s for code, s in assignments.items() if s > 0}
    violations = []
    for code, semester in selected.items():
        if math_qualified and math_entry_waived(code):
            continue
        tree = CATALOG[code].get('prereq_tree')
        if not prerequisite_met(tree, semester, assignments, start_year):
            violations.append({'course': code, 'semester': semester,
                               'requirement': prerequisite_description(tree),
                               'prerequisite_tree': tree})
    missing = sorted(set(FOUNDATION) - selected.keys())
    profile_errors = profile_violations(assignments, math_qualified=math_qualified)
    passed = not missing and not violations and not profile_errors
    return {'status': 'passed' if passed else 'failed',
            'scope': 'Foundation courses, course prerequisite order and H2 Mathematics bridging eligibility; not a complete graduation audit.',
            'missing_foundation_courses': missing, 'prerequisite_violations': violations,
            'profile_violations': profile_errors}


def cohort_applies(condition, start_year):
    in_range = all(start_year <= int(y[2:6]) if y.startswith('E:') else start_year >= int(y[2:6]) for y in condition['years'])
    return not in_range if condition['rule'] in {'IF_NOT_IN','MUST_NOT_BE_IN'} else in_range


def prerequisite_met(tree, semester, assignments, start_year=2026):
    if tree is None:
        return True
    if isinstance(tree, str):
        code = tree.split(":")[0]
        return 0 < assignments.get(code, 0) < semester
    if isinstance(tree, dict) and len(tree) == 1:
        operator, children = next(iter(tree.items()))
        if operator=='cohort':
            return cohort_applies(children,start_year)
        if operator=='nOf':
            number, trees = children
            return sum(prerequisite_met(t,semester,assignments,start_year) for t in trees)>=number
        checks = [prerequisite_met(t, semester, assignments,start_year) for t in children]
        if operator == "and":
            return all(checks)
        if operator == "or":
            return any(checks)
    return False  # Unknown prerequisite formats must never be silently ignored.


def exam_pairs():
    """Conflicts within each reference semester; reused across academic years."""
    for (a, am), (b, bm) in combinations(CATALOG.items(), 2):
        for sa in am.get("semesters", []):
            for sb in bm.get("semesters", []):
                if sa["semester_number"] != sb["semester_number"]:
                    continue
                if not all(s.get("exam_date_time") and s.get("exam_duration") for s in (sa, sb)):
                    continue
                ta, tb = [datetime.fromisoformat(s["exam_date_time"].replace("Z", "+00:00")) for s in (sa, sb)]
                if ta < tb + timedelta(minutes=sb["exam_duration"]) and tb < ta + timedelta(minutes=sa["exam_duration"]):
                    yield a, b, sa["semester_number"]


def rule_satisfied(rule, assignments, horizon, allocations=None, request=None):
    selected = {code: s for code, s in assignments.items() if s > 0}
    loads = {s: sum(int(CATALOG[c]["module_credit"]) for c, sem in selected.items() if sem == s)
             for s in range(1, horizon + 1)}
    t = rule.type
    if t == 'weekly_feasibility':
        from backend.attendance import semester_selection
        return all(semester_selection([c for c,v in selected.items() if v==s],(s-1)%2+1,
                    allow_unpublished=bool(request and request.allow_unpublished))['status'] in {'feasible','conditional'}
                   for s in range(1,horizon+1))
    if t == 'category_units':
        eligible = set(CATEGORIES['ID'])|set(CATEGORIES['CD']) if rule.category=='ID_CD' else set(CATEGORIES[rule.category])
        courses = set(allocations.get(rule.category,[])) if allocations is not None else eligible & selected.keys()
        if not courses <= eligible & selected.keys(): return False
        if sum(int(CATALOG[c]['module_credit']) for c in courses)<rule.units: return False
        if rule.category=='ID_CD':
            return len(courses & set(CATEGORIES['ID']))>=2 and len(courses & (set(CATEGORIES['CD'])-set(CATEGORIES['ID'])))<=1
        return True
    if t == "min_total_units":
        return sum(loads.values()) >= rule.units
    if t == "require_courses":
        return all(c in selected for c in rule.courses)
    if t == "exclude_courses":
        return all(c not in selected for c in rule.courses)
    if t == "course_in_semester":
        return assignments.get(rule.course, 0) == rule.semester
    if t == "finish_by":
        return all(s <= rule.semester for s in selected.values())
    if t == "blocked_semesters":
        return all(s not in rule.semesters for s in selected.values())
    if t == "semester_units":
        return all(load == 0 or rule.minimum <= load <= (min(rule.maximum, rule.first_semester_maximum) if s == 1 else rule.maximum)
                   for s, load in loads.items())
    if t == "workload_target":
        return all(load == rule.units for load in loads.values() if load)
    if t == "prerequisites":
        return all((request and request.math_qualified and math_entry_waived(c)) or
                   prerequisite_met(CATALOG[c].get("prereq_tree"), s, assignments,request.start_year if request else 2026)
                   for c, s in selected.items())
    if t == "corequisites":
        return assignments.get("CS2101", 0) == assignments.get("CS2103T", 0)
    if t == "semester_availability":
        return all((s - 1) % 2 + 1 in [x["semester_number"] for x in CATALOG[c].get("semesters", [])]
                   for c, s in selected.items())
    if t == "focus_area":
        codes = set(FOCUS_AREAS[rule.area]["primaries"]) & selected.keys()
        return len(codes) >= 3 and any(int(c[2]) >= 4 for c in codes)
    if t == "exam_clashes":
        return not any(a in selected and b in selected and selected[a] == selected[b]
                       and (selected[a] - 1) % 2 + 1 == sem for a, b, sem in exam_pairs())
    if t == 'minor_programme':
        return True  # Checked jointly with explicit minor allocations below.
    raise ValueError("Unimplemented rule: " + t)


def check_plan(request, assignments, allocations=None, minor_allocations=None):
    hard_failures, unmet_preferences = [], []
    if profile_violations(assignments, math_qualified=request.math_qualified):
        hard_failures.append({'id': 'math-profile', 'title': 'H2 Mathematics qualification excludes MA1301 and MA1301X.'})
    if allocations is not None:
        allocated = [c for group in allocations.values() for c in group]
        if len(allocated)!=len(set(allocated)):
            hard_failures.append({'id':'category-allocation','title':'A course was counted in multiple category allocations'})
    for card in request.cards:
        if not all(rule_satisfied(r, assignments, request.horizon, allocations,request) for r in card.rules):
            (hard_failures if card.strength == "hard" else unmet_preferences).append({"id": card.id, "title": card.title})
    from backend.minors import audit_minors
    minor_audit = audit_minors(request, assignments, minor_allocations, allocations)
    if minor_audit['status'] != 'passed':
        hard_failures.append({'id': 'minor-audit', 'title': '; '.join(minor_audit['violations'])})
    return hard_failures, unmet_preferences
