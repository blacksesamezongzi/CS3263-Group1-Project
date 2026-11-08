"""Finite lesson-choice feasibility shared by degree solving and weekly display."""
from collections import defaultdict
from itertools import combinations
from backend.catalog import DETAILS
from backend.nusmods import clashes, select_lessons


def lesson_groups(codes, semester):
    groups, missing = [], []
    for code in codes:
        data = DETAILS[code]
        offer = next((s for s in data.get('semesterData',[]) if s['semester']==semester),None)
        if code=='CS2101':
            # Explicit project mapping confirmed by the user: the communication
            # course shares exactly the CS2103T tutorial, not a second meeting.
            paired = next((s for s in DETAILS['CS2103T'].get('semesterData',[]) if s['semester']==semester),{})
            tutorials = [l for l in paired.get('timetable',[]) if l['lessonType']=='Tutorial']
            # AY2026/27 publishes the integrated Gxx package under "Lecture"
            # (including tutorial/communication meetings). Keep the entire
            # package intact; do not guess a subset from venues or durations.
            tutorials = tutorials or paired.get('timetable',[])
            if tutorials:
                if 'CS2103T' in codes:
                    continue
                offer = {'timetable':[{**l,'lessonType':'Sectional Teaching'} for l in tutorials]}
        if not offer or not offer.get('timetable'):
            missing.append(code)
            continue
        types = defaultdict(lambda:defaultdict(list))
        for lesson in offer['timetable']:
            shared = ['CS2101'] if code=='CS2103T' and 'CS2101' in codes else []
            types[lesson['lessonType']][lesson['classNo']].append({**lesson,'course':code,'title':data.get('title',code),'sharedWith':shared})
        groups.extend((code,kind,dict(options)) for kind,options in types.items())
    return groups, missing


def semester_selection(codes, semester, allow_unpublished=False):
    groups, missing = lesson_groups(codes, semester)
    if missing and not allow_unpublished:
        return {'status':'missing_data','missing':missing,'lessons':[],'selection':[]}
    lessons, choices, status = select_lessons(groups)
    return {'status':'conditional' if missing and status=='feasible' else status,'unpublished':missing,'lessons':lessons,
            'selection':[{'course':c,'type':t,'class':n} for (c,t),n in choices.items()]}


def fixed_conflicts(codes, semester):
    """Cheap initial cuts for lectures/classes with no alternative class number."""
    groups, _ = lesson_groups(codes, semester)
    mandatory = defaultdict(list)
    for code, _, options in groups:
        if len(options)==1:
            mandatory[code].extend(next(iter(options.values())))
    return [(a,b) for a,b in combinations(sorted(mandatory),2)
            if any(clashes(x,y) for x in mandatory[a] for y in mandatory[b])]


def conflict_core(codes, semester, allow_unpublished=False):
    """Shrink a proven infeasible course set; a timeout is never a proof."""
    core = list(codes)
    for code in list(core):
        candidate = [c for c in core if c!=code]
        if candidate and semester_selection(candidate,semester,allow_unpublished)['status']=='infeasible':
            core = candidate
    return core
