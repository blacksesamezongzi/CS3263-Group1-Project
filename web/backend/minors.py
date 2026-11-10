"""Cohort AY2021/22+ minor rules, transcribed from the linked NUS tables.

Course groups are distinct allocation buckets. Eligibility is matched against
real reference-year codes; programme rules never create placeholder courses.
"""
import re

MATH_URL = 'https://www.math.nus.edu.sg/ug/majmin/minors/mamin/'
QF_URL = 'https://www.math.nus.edu.sg/ug/majmin/minors/qfmin/'
MATH_PDF = 'https://www.math.nus.edu.sg/wp-content/uploads/sites/4/2026/07/MAmin_2122_14102025.pdf'
QF_PDF = 'https://www.math.nus.edu.sg/wp-content/uploads/sites/4/2025/12/QFmin_2122_01122025.pdf'
POLICY_URL = 'https://www.comp.nus.edu.sg/programmes/ug/minorc/'

MINORS = {
    'mathematics': {
        'name': 'Mathematics', 'tag': 'MATH_MINOR', 'source_urls': [MATH_URL, MATH_PDF, POLICY_URL],
        'summary': '20+ units: 8 foundation units, two approved intermediate courses and one approved advanced course. At least 12 distinct units; at most 8 shared units.',
        'groups': [
            {'id': 'foundation', 'name': 'Foundation', 'units': 8, 'exact_units': True,
             'patterns': [r'^MA1\d{3}[A-Z]*$', r'^MA20\d{2}[A-Z]*$'], 'codes': ['CS1231', 'CS1231S'],
             'exclude': [r'^MA1301', r'^MA\d99\d']},
            {'id': 'intermediate', 'name': 'Intermediate', 'units': 8, 'count': 2,
             'patterns': [r'^MA22\d{2}[A-Z]*$'],
             'codes': ['MA2101', 'MA2101S', 'MA2104', 'MA2311', 'MA2108', 'MA2108S', 'MA2116', 'MA2116T', 'MA2216', 'ST2131', 'ST2334'],
             'exclude': [r'^MA228[89]', r'^MA\d99\d']},
            {'id': 'advanced', 'name': 'Advanced', 'units': 4, 'count': 1,
             'patterns': [r'^MA32\d{2}[A-Z]*$'], 'codes': ['ST3236', 'PC3274A'],
             'exclude': [r'^MA328[89]', r'^MA\d99\d']},
        ],
    },
    'quantitative_finance': {
        'name': 'Quantitative Finance', 'tag': 'QF_MINOR', 'source_urls': [QF_URL, QF_PDF, MATH_URL, POLICY_URL],
        'summary': '20 units: QF1100, QF2104, QF3101, a 4-unit mathematics option and an approved advanced elective. At least 12 distinct units; at most 8 shared units.',
        'groups': [
            {'id': 'introduction', 'name': 'Introduction', 'units': 4, 'count': 1, 'codes': ['QF1100']},
            {'id': 'mathematics', 'name': 'Mathematics option B', 'units': 4, 'exact_units': True, 'max_count': 2,
             'patterns': [r'^MA15\d{2}[A-Z]*$'],
             'codes': ['MA1312', 'MA2001', 'MA2002', 'MA2104', 'MA2213', 'MA2216', 'MA2116', 'MA2116T', 'ST2131', 'MA2311', 'DSA2102', 'QF2103', 'ST2334']},
            {'id': 'fundamentals', 'name': 'Fundamentals', 'units': 4, 'count': 1, 'codes': ['QF2104']},
            {'id': 'investment', 'name': 'Investment and risk', 'units': 4, 'count': 1, 'codes': ['QF3101']},
            {'id': 'advanced', 'name': 'Advanced elective', 'units': 4, 'count': 1,
             'codes': ['QF3103', 'ST3131', 'EC3303', 'FIN3702', 'FIN3702A', 'FIN3702B', 'FIN3702C', 'FIN3702D', 'FIN3716']},
        ],
    },
}


def group_codes(group, codes):
    return sorted(code for code in codes
                  if (code in group.get('codes', []) or any(re.match(p, code) for p in group.get('patterns', [])))
                  and not any(re.match(p, code) for p in group.get('exclude', [])))


def eligible_codes(programme, codes):
    return set().union(*(set(group_codes(g, codes)) for g in MINORS[programme]['groups']))


def programmes():
    from backend.catalog import CATALOG
    return [{'id': key, 'name': p['name'], 'summary': p['summary'], 'source_urls': p['source_urls'],
             'cohort_from': 2021, 'minimum_units': 20, 'minimum_distinct_units': 12, 'maximum_shared_units': 8,
             'declaration_note': 'Declare in EduRec before the start of semester 5. This planner does not declare the minor.',
             'offering_note': 'MA2301 is no longer offered from AY2025/26; this reference-year template uses Option B.' if key == 'quantitative_finance' else '',
             'groups': [{**{k: v for k, v in g.items() if k not in {'patterns', 'exclude', 'codes'}},
                         'courses': group_codes(g, CATALOG)} for g in p['groups']]}
            for key, p in MINORS.items()]


def selected_minors(request):
    return sorted({r.programme for c in request.cards for r in c.rules if r.type == 'minor_programme'})


def prerequisite_codes(tree):
    if isinstance(tree, str):
        return {tree.split(':')[0]}
    if isinstance(tree, dict):
        return set().union(*(prerequisite_codes(v) for v in tree.values()))
    if isinstance(tree, list):
        return set().union(*(prerequisite_codes(v) for v in tree))
    return set()


def allowed_courses(request):
    from backend.catalog import CATALOG, MINOR_SUPPLEMENT
    allowed = set(CATALOG) - MINOR_SUPPLEMENT
    extra = set().union(*(eligible_codes(p, CATALOG) for p in selected_minors(request)))
    for card in request.cards:
        for rule in card.rules:
            if rule.type in {'require_courses', 'exclude_courses'}:
                extra.update(rule.courses)
            elif rule.type == 'course_in_semester':
                extra.add(rule.course)
    pending = list(extra)
    while pending:
        code = pending.pop()
        if code not in CATALOG or code in allowed:
            continue
        allowed.add(code)
        pending.extend(prerequisite_codes(CATALOG[code].get('prereq_tree')) - allowed)
    return allowed


def minor_preclusions():
    from backend.catalog import CATALOG, DETAILS, MINOR_SUPPLEMENT
    pairs = set()
    for code in MINOR_SUPPLEMENT:
        # Read explicit course preclusions; programme/grade restrictions still
        # require CourseReg/adviser review and are not inferred as equivalences.
        for text in re.findall(r'must not have completed\s+(.*?)(?:at a grade|\))', DETAILS[code].get('preclusion') or '', re.I):
            for other in re.findall(r'\b[A-Z]{2,4}\d{4}[A-Z]{0,2}\b', text):
                if other in CATALOG and other != code:
                    pairs.add(tuple(sorted((code, other))))
    return sorted(pairs)


def minor_prompt_cards():
    cards = []
    for programme in programmes():
        groups = '; '.join(f"{g['name']}: {'exactly ' if g.get('exact_units') else 'at least '}{g['units']} units"
                           + (f" in {g['count']} course(s)" if g.get('count') else '')
                           + ' from ' + ', '.join(g['courses']) for g in programme['groups'])
        cards.append({'id': 'minor_' + programme['id'], 'title': 'Complete a ' + programme['name'] + ' minor',
                      'description': programme['summary'], 'strength': 'hard', 'prompt_category': 'minor',
                      'prompt': 'Include a Minor in ' + programme['name'] + ' under the AY2021/22-onwards requirements. '
                                + groups + '. Use distinct courses within its groups, count units only once in the degree total, '
                                'share no more than 8 units with other programmes and keep at least 12 units outside the entire '
                                'CS-major/other-selected-minor course pools. Respect prerequisites and preclusions. '
                                'Declaration is required before semester 5. Reference: ' + programme['source_urls'][0]})
    return cards


def audit_minors(request, assignments, allocations, category_allocations=None):
    from backend.catalog import CATALOG, FOUNDATION
    selected = {c for c, s in assignments.items() if s > 0}
    declared = selected_minors(request)
    errors, results = [], []
    allocations = allocations or {}
    used = {p: {c for pool in allocations.get(p, {}).values() for c in pool} for p in declared}
    category_courses = {c for pool in (category_allocations or {}).values() for c in pool}
    units = lambda pool: sum(int(CATALOG[c]['module_credit']) for c in pool if c in CATALOG)
    for p in declared:
        spec, groups = MINORS[p], allocations.get(p, {})
        failures, checks = [], []
        flat = [c for pool in groups.values() for c in pool]
        if len(flat) != len(set(flat)):
            failures.append('A course was counted in more than one minor group.')
        if set(groups) != {g['id'] for g in spec['groups']}:
            failures.append('Minor group allocations are incomplete or contain unknown groups.')
        for group in spec['groups']:
            pool = groups.get(group['id'], [])
            credits = units(pool)
            valid = set(pool) <= set(group_codes(group, CATALOG)) & selected
            valid = valid and (credits == group['units'] if group.get('exact_units') else credits >= group['units'])
            valid = valid and (len(pool) == group['count'] if group.get('count') else True)
            valid = valid and (len(pool) <= group['max_count'] if group.get('max_count') else True)
            if not valid:
                failures.append(group['name'] + ' does not meet its course/unit requirement.')
            checks.append({'id': group['id'], 'name': group['name'], 'courses': pool, 'units': credits, 'passed': bool(valid)})
        outside = set(CATALOG) - set(FOUNDATION) - category_courses
        other_uses = set()
        for other in declared:
            if other != p:
                outside -= eligible_codes(other, CATALOG)
                other_uses.update(used[other])
        distinct = units(used[p] & outside)
        shared = units(used[p] & (set(FOUNDATION) | category_courses | other_uses))
        if units(used[p]) < 20:
            failures.append('At least 20 minor units are required.')
        if distinct < 12:
            failures.append('At least 12 units must be outside the CS-major and other selected minor pools, without common-curriculum reuse.')
        if shared > 8:
            failures.append('More than 8 units were reused with other programmes.')
        if any(int(c in FOUNDATION) + int(c in category_courses) + sum(c in used[x] for x in declared) > 2 for c in used[p]):
            failures.append('A course was counted towards more than two programme requirements.')
        conflicts = [(a, b) for a, b in minor_preclusions() if a in selected and b in selected]
        if conflicts:
            failures.append('Precluded courses selected together: ' + '; '.join(f'{a}/{b}' for a, b in conflicts))
        errors.extend(f"{spec['name']}: {message}" for message in failures)
        results.append({'id': p, 'name': spec['name'], 'status': 'failed' if failures else 'passed',
                        'units': units(used[p]), 'distinct_units': distinct, 'shared_units': shared,
                        'groups': checks, 'violations': failures, 'source_urls': spec['source_urls']})
    return {'status': 'failed' if errors else 'passed', 'programmes': results, 'violations': errors,
            'scope': 'AY2021/22-onwards templates; assumed NUS-earned courses. Declaration, personal exemptions, second majors and CourseReg access require separate confirmation.'}
