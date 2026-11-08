"""Integration seam: translate active UI rules into the team's PyCSP3 engine.

This module is imported ONLY inside the isolated worker. Algorithm owners can
replace solve_plan(request) while preserving the HTTP and UI contract.
"""
from pycsp3 import Var, VarArray, Sum, satisfy, minimize, solve, values, SAT, OPTIMUM
from pycsp3 import abs as cp_abs
from backend.catalog import CATALOG, FOCUS_AREAS, CATEGORIES, course_info
from backend.validation import exam_pairs, cohort_applies
from backend.attendance import semester_selection, fixed_conflicts, conflict_core, lesson_groups
import time


def solve_plan(request):
    codes = list(CATALOG)
    indices = {code: i for i, code in enumerate(codes)}
    assignment = VarArray(size=len(codes), dom=range(request.horizon + 1))
    maximum_units = sum(int(m["module_credit"]) for m in CATALOG.values())
    loads = VarArray(size=request.horizon, dom=range(maximum_units + 1))
    total = Var(dom=range(maximum_units + 1))
    satisfy([loads[s-1] == Sum(int(CATALOG[c]["module_credit"]) * (assignment[i] == s)
                              for i, c in enumerate(codes)) for s in range(1, request.horizon + 1)],
            total == Sum(int(CATALOG[c]["module_credit"]) * (assignment[i] > 0) for i, c in enumerate(codes)))
    # A low-priority tie-break avoids gratuitous additional courses.
    penalties = [total]
    category_ids = {'GEC':1,'GEA':2,'GESS':3,'GEN':4,'ID_CD':5}
    def allocation_domain(i):
        code = codes[i]
        return {0} | {key for name,key in category_ids.items()
            if code in (set(CATEGORIES['ID'])|set(CATEGORIES['CD']) if name=='ID_CD' else CATEGORIES[name])}
    allocations = VarArray(size=len(codes), dom=allocation_domain)
    satisfy([(allocations[i]==0) | (assignment[i]>0) for i in range(len(codes))])
    satisfy([assignment[i]==0 for i,c in enumerate(codes) if not course_info(c)['planner_eligible']])
    weekly = any(r.type=='weekly_feasibility' for c in request.cards for r in c.rules)
    explicit = set()
    for card in request.cards:
        for rule in card.rules:
            if rule.type=='require_courses': explicit.update(rule.courses)
            elif rule.type=='course_in_semester': explicit.add(rule.course)
    if weekly:
        for semester in (1,2):
            for i,code in enumerate(codes):
                offered = semester in course_info(code)['semesters']
                if lesson_groups([code],semester)[1] and not (offered and request.allow_unpublished and code in explicit):
                    satisfy([assignment[i]!=s for s in range(semester,request.horizon+1,2)])
            for a,b in fixed_conflicts(codes,semester):
                satisfy([(assignment[indices[a]]!=s) | (assignment[indices[b]]!=s)
                         for s in range(semester,request.horizon+1,2)])

    def prereq(tree, semester):
        if tree is None:
            return True
        if isinstance(tree, str):
            index = indices.get(tree.split(":")[0])
            return False if index is None else (assignment[index] > 0) & (assignment[index] < semester)
        if isinstance(tree, dict) and len(tree) == 1:
            op, children = next(iter(tree.items()))
            if op=='cohort':
                return cohort_applies(children,request.start_year)
            if op=='nOf':
                number,trees=children
                parts=[prereq(child,semester) for child in trees]
                constants=sum(p is True for p in parts)
                parts=[p for p in parts if not isinstance(p,bool)]
                if constants>=number: return True
                if len(parts)+constants<number: return False
                return Sum(parts)>=number-constants
            parts = [prereq(child, semester) for child in children]
            if op not in {"and", "or"}:
                return False
            identity, absorbing = (True, False) if op == "and" else (False, True)
            if any(isinstance(p, bool) and p == absorbing for p in parts):
                return absorbing
            parts = [p for p in parts if not isinstance(p, bool)]
            if not parts:
                return identity
            expression = parts[0]
            for part in parts[1:]:
                expression = expression & part if op == "and" else expression | part
            return expression
        return False

    for card in request.cards:
        for rule in card.rules:
            t = rule.type
            if card.strength == "soft":
                if t == "course_in_semester":
                    penalties.append(100000 * (assignment[indices[rule.course]] != rule.semester))
                elif t == "finish_by":
                    penalties.extend(10000 * (x > rule.semester) for x in assignment)
                elif t == "workload_target":
                    # Zero-load semesters are allowed; do not invent courses to fill them.
                    penalties.extend(100 * ((load > 0) * cp_abs(load - rule.units)) for load in loads)
                continue
            if t == "min_total_units":
                satisfy(total >= rule.units)
            elif t == "require_courses":
                satisfy([assignment[indices[c]] > 0 for c in rule.courses])
            elif t == "exclude_courses":
                satisfy([assignment[indices[c]] == 0 for c in rule.courses])
            elif t == "course_in_semester":
                satisfy(assignment[indices[rule.course]] == rule.semester)
            elif t == "finish_by":
                satisfy([x <= rule.semester for x in assignment])
            elif t == "blocked_semesters":
                satisfy([x != s for x in assignment for s in rule.semesters])
            elif t == "semester_units":
                satisfy([(load == 0) | (load >= rule.minimum) for load in loads],
                        [load <= (min(rule.maximum, rule.first_semester_maximum) if i == 0 else rule.maximum)
                         for i, load in enumerate(loads)])
            elif t == "prerequisites":
                for i, code in enumerate(codes):
                    if request.math_qualified and code in {'CS1231S','MA1521','MA1522'}: continue
                    expression = prereq(CATALOG[code].get("prereq_tree"), assignment[i])
                    if isinstance(expression, bool):
                        if not expression:
                            satisfy(assignment[i] == 0)
                    else:
                        satisfy((assignment[i] == 0) | expression)
            elif t == "corequisites":
                satisfy(assignment[indices["CS2101"]] == assignment[indices["CS2103T"]])
            elif t == "semester_availability":
                for i, code in enumerate(codes):
                    offered = {s["semester_number"] for s in CATALOG[code].get("semesters", [])}
                    satisfy([assignment[i] != s for s in range(1, request.horizon + 1) if (s - 1) % 2 + 1 not in offered])
            elif t == "focus_area":
                primary = [indices[c] for c in FOCUS_AREAS[rule.area]["primaries"] if c in indices]
                advanced = [i for i in primary if int(codes[i][2]) >= 4]
                satisfy(Sum(assignment[i] > 0 for i in primary) >= 3,
                        Sum(assignment[i] > 0 for i in advanced) >= 1)
            elif t == "exam_clashes":
                for a, b, semester in exam_pairs():
                    satisfy([(assignment[indices[a]] != s) | (assignment[indices[b]] != s)
                             for s in range(semester, request.horizon + 1, 2)])
            elif t == 'category_units':
                bucket = category_ids[rule.category]
                satisfy(Sum(int(CATALOG[c]['module_credit'])*(allocations[i]==bucket) for i,c in enumerate(codes)) >= rule.units)
                if rule.category=='ID_CD':
                    ids = [indices[c] for c in CATEGORIES['ID']]
                    cds = [indices[c] for c in CATEGORIES['CD'] if c not in CATEGORIES['ID']]
                    satisfy(Sum(allocations[i]==bucket for i in ids)>=2,
                            Sum(allocations[i]==bucket for i in cds)<=1)
            elif t == 'weekly_feasibility':
                pass  # The complete lesson-choice subproblem is verified below.
            else:
                raise ValueError("Unimplemented rule: " + t)
    minimize(Sum(penalties))
    started = time.monotonic()
    for attempt in range(12):
        result = solve(solver='[ace,limit=4s]', verbose=-1)
        if result not in (SAT,OPTIMUM):
            return {'status':'infeasible' if str(result)=='UNSAT' else 'timeout','assignments':{}}
        selected = dict(zip(codes,values(assignment)))
        if not weekly:
            break
        conflicts = []
        for s in range(1,request.horizon+1):
            courses = [c for c,v in selected.items() if v==s]
            if not courses: continue
            selection = semester_selection(courses,(s-1)%2+1,request.allow_unpublished)
            if selection['status']=='timeout':
                return {'status':'timeout','assignments':{}}
            if selection['status'] not in {'feasible','conditional'}:
                conflicts.append((s,conflict_core(courses,(s-1)%2+1,request.allow_unpublished)))
        if not conflicts:
            break
        for semester,core in conflicts:
            for s in range((semester-1)%2+1,request.horizon+1,2):
                satisfy(Sum(assignment[indices[c]]==s for c in core)<len(core))
        if time.monotonic()-started>80:
            return {'status':'timeout','assignments':{}}
    else:
        return {'status':'timeout','assignments':{}}
    allocated = values(allocations)
    return {'status':'feasible','optimal':result==OPTIMUM,'assignments':selected,
            'category_allocations':{name:[c for i,c in enumerate(codes) if allocated[i]==bucket]
                                    for name,bucket in category_ids.items()},
            'weekly_verified':weekly,'refinement_rounds':attempt}
