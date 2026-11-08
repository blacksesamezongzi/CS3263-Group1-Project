"""Native Planner export plus live lesson selection and timetable share links."""
import asyncio
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
import time
from urllib.parse import urlencode
import httpx
from backend.catalog import PLACEHOLDER, course_info, DETAILS, SNAPSHOT

REFERENCE_YEAR = "2026-2027"
ABBREVIATIONS = {"Design Lecture": "DLEC", "Laboratory": "LAB", "Lecture": "LEC",
    "Packaged Laboratory": "PLAB", "Packaged Lecture": "PLEC", "Packaged Tutorial": "PTUT",
    "Recitation": "REC", "Sectional Teaching": "SEC", "Seminar-Style Module Class": "SEM",
    "Tutorial": "TUT", "Tutorial Type 2": "TUT2", "Tutorial Type 3": "TUT3", "Workshop": "WS"}
_cache = {}
_fetch_slots = asyncio.Semaphore(6)


def planner_export(plan):
    modules, custom = {}, {}
    active = [s for s in plan["semesters"] if s["courses"]]
    all_semesters = plan["semesters"]
    for semester in all_semesters:
        for index, course in enumerate(semester["courses"]):
            key = str(len(modules))
            modules[key] = {"id": key, "year": semester["academic_year"],
                            "semester": semester["semester"], "index": index,
                            "moduleCode": course["code"]}
            if course["placeholder"]:
                custom[course["code"]] = {"title": "Unresolved placeholder: " + course["title"],
                                          "moduleCredit": course["units"]}
    return {"minYear": all_semesters[0]["academic_year"],
            "maxYear": (active[-1] if active else all_semesters[-1])["academic_year"],
            "iblocs": False, "ignorePrereqCheck": False, "modules": modules, "custom": custom}


async def fetch_module(client, year, code):
    if year == SNAPSHOT['academic_year'] and code in DETAILS:
        return DETAILS[code]
    cache_key = (year, code)
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < 21600:
        return cached[1]
    async with _fetch_slots:
        response = await client.get(f"https://api.nusmods.com/v2/{year}/modules/{code}.json")
        response.raise_for_status()
        data = response.json()
    _cache[cache_key] = (time.monotonic(), data)
    return data


def minutes(value):
    return int(value[:2]) * 60 + int(value[2:])


@lru_cache(maxsize=2000)
def week_dates(start, end, interval, week_numbers, day):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    # NUSMods WeekRange.start/end describe actual calendar dates.
    weekdays = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6}
    cursor, dates = first, set()
    while cursor <= last:
        week = (cursor - first).days // 7
        if cursor.weekday() == weekdays[day] and week % interval == 0 and (not week_numbers or week + 1 in week_numbers):
            dates.add(cursor)
        cursor += timedelta(days=1)
    return dates


def clashes(a, b):
    if a["day"] != b["day"] or not (minutes(a["startTime"]) < minutes(b["endTime"]) and minutes(b["startTime"]) < minutes(a["endTime"])):
        return False
    aw, bw = a.get("weeks"), b.get("weeks")
    if isinstance(aw, list) and isinstance(bw, list):
        return bool(set(aw) & set(bw))
    if isinstance(aw, dict) and isinstance(bw, dict):
        def expand(w, day):
            return week_dates(w["start"], w["end"], w.get("weekInterval", 1), tuple(w.get("weeks", [])), day)
        return bool(expand(aw, a["day"]) & expand(bw, b["day"]))
    # Unknown/mixed week formats are conservatively treated as overlapping.
    return True


def select_lessons(groups, max_nodes=100000):
    """Choose a whole class per lesson type; all sessions of a class stay together."""
    groups = sorted(groups, key=lambda group: len(group[2]))
    chosen, selected, nodes = [], {}, 0

    def search(index):
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            return False
        if index == len(groups):
            return True
        code, lesson_type, options = groups[index]
        for class_no, sessions in sorted(options.items()):
            if any(clashes(a, b) for a in sessions for b in chosen):
                continue
            # A single class may have multiple meetings, which must also be compatible.
            if any(clashes(a, b) for i, a in enumerate(sessions) for b in sessions[i+1:]):
                continue
            chosen.extend(sessions)
            selected[(code, lesson_type)] = class_no
            if search(index + 1):
                return True
            del selected[(code, lesson_type)]
            if sessions:
                del chosen[-len(sessions):]
        return False

    success = search(0)
    return (chosen, selected, "feasible") if success else ([], {}, "timeout" if nodes > max_nodes else "infeasible")


async def build_timetable(request):
    from backend.attendance import semester_selection
    if request.academic_year != SNAPSHOT['academic_year']:
        return {'status':'missing_data','lessons':[],'share_url':None,'exams':[],
                'warnings':['Use the reference academic year '+SNAPSHOT['academic_year']+'.']}
    result = await asyncio.to_thread(semester_selection,request.courses,request.semester)
    warnings, exams = [], []
    for code in request.courses:
        offer=next((s for s in DETAILS[code].get('semesterData',[]) if s['semester']==request.semester),{})
        if offer.get('examDate'):
            exams.append({'course':code,'date':offer['examDate'],'duration':offer.get('examDuration')})
    if 'CS2101' in request.courses:
        warnings.append('CS2101 shares CS2103T tutorial times and class selection, as confirmed for this project.')
    if result['status']!='feasible':
        missing=result.get('missing',[])
        warnings.append('No published lesson times: '+', '.join(missing) if missing else 'No complete clash-free lesson selection exists for this course set.')
        return {**result,'warnings':warnings,'share_url':None,'exams':exams}
    query, supported = [], True
    for code in request.courses:
        parts=[]
        for choice in result['selection']:
            if choice['course']==code:
                if choice['type'] not in ABBREVIATIONS: supported=False
                else: parts.append(f"{ABBREVIATIONS[choice['type']]}:{choice['class']}")
        # CS2101 is present in the share link; NUSMods has no class IDs for it.
        # Its shared tutorial is encoded under CS2103T and labelled in our view.
        query.append((code,','.join(parts)))
    share_url=f'https://nusmods.com/timetable/sem-{request.semester}/share?'+urlencode(query,safe=':,') if supported else None
    return {**result,'share_url':share_url,'warnings':warnings,'exams':exams,
            'academic_year':request.academic_year,'note':'Reference-year lessons; future offering patterns are assumed to repeat.'}
