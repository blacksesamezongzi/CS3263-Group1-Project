"""Bounded process isolation prevents PyCSP3 global state leaking across users."""
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from backend.catalog import ROOT, CATALOG, course_info
from backend.validation import check_plan, academic_audit


class SolverError(Exception):
    pass


def generate_plan(request):
    started = time.monotonic()
    from backend.catalog import DETAILS
    weekly = any(r.type=='weekly_feasibility' for c in request.cards for r in c.rules)
    if weekly and not request.allow_unpublished:
        required = {code for card in request.cards if card.strength=='hard' for rule in card.rules
                    for code in (rule.courses if rule.type=='require_courses' else [rule.course] if rule.type=='course_in_semester' else [])}
        from backend.attendance import lesson_groups
        missing = sorted(c for c in required if all(lesson_groups([c],sem)[1] for sem in (1,2)))
        if missing:
            return {'status':'missing_data','semesters':[], 'unpublished_courses':missing,
                    'message':'Cannot fully verify weekly feasibility: no lesson times are published for '+', '.join(missing)+'. Supply published times or explicitly enable conditional plans. No fully verified plan has been returned.'}
    with TemporaryDirectory(prefix="cs3263-") as directory:
        input_path, output_path = Path(directory) / "input.json", Path(directory) / "result.json"
        input_path.write_text(request.model_dump_json())
        env = {k: v for k, v in os.environ.items() if not k.startswith("SOCLAAS_")}
        env["PYTHONPATH"] = str(ROOT)
        process = subprocess.Popen([sys.executable, "-m", "backend.solver_worker", str(input_path), str(output_path)],
                                   cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=110)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            return {"status": "timeout", "message": "Search reached its time limit. Try relaxing constraints.", "semesters": []}
        if process.returncode or not output_path.exists():
            logging.getLogger(__name__).error("Isolated CSP worker failed:\n%s\n%s", stdout.decode(errors="replace")[-4000:], stderr.decode(errors="replace")[-4000:])
            # Avoid exposing file paths, environment values or solver internals to clients.
            raise SolverError("The solver could not run. Verify Java 11+ and the Python dependencies; see the integration guide.")
        result = json.loads(output_path.read_text())
    if result["status"] != "feasible":
        return {"status": result["status"], "semesters": [], "message":
                "No feasible plan satisfies all active requirements. Remove or relax a card and try again."
                if result["status"] == "infeasible" else "Search timed out without a feasible solution. Try relaxing constraints."}
    assignments = result.pop("assignments")
    failures, unmet = check_plan(request, assignments, result.get('category_allocations'), result.get('minor_allocations'))
    if failures:
        raise SolverError("The independent checker rejected the solver result. No invalid plan was returned.")
    semesters = []
    for s in range(1, request.horizon + 1):
        courses = [course_info(code) for code, assigned in assignments.items() if assigned == s]
        year = request.start_year + (s - 1) // 2
        semesters.append({"number": s, "year_of_study": (s - 1) // 2 + 1,
                          "semester": (s - 1) % 2 + 1, "academic_year": f"{year}-{year+1}",
                          "units": sum(c["units"] for c in courses), "courses": courses})
    total = sum(s["units"] for s in semesters)
    warnings = ["Prototype plan: only the active cards were checked. This is not a complete graduation audit.",
                "Reference offerings and exam dates repeat from AY2026/27; future years are assumptions.",
                "Preclusions, internship eligibility and full degree-category rules are not yet implemented by this adapter."]
    if assignments.get('CS2101',0):
        warnings.append('Project mapping confirmed by the user: CS2101 shares the CS2103T tutorial times and class selection.')
    if not result.get('weekly_verified'):
        warnings.append('The weekly timetable requirement was removed; weekly feasibility has not been guaranteed.')
    weekly_timetables = {}
    if result.get('weekly_verified'):
        from backend.attendance import semester_selection
        for s in semesters:
            if s['courses']:
                weekly_timetables[str(s['number'])] = semester_selection([c['code'] for c in s['courses']],s['semester'],request.allow_unpublished)
    unpublished = sorted({c for t in weekly_timetables.values() for c in t.get('unpublished',[])})
    if unpublished:
        result['status']='conditional'
        result['weekly_verified']=False
        warnings.append('Unpublished lesson times were explicitly allowed: '+', '.join(unpublished)+'. Only the published lessons have been verified; this is a conditional plan.')
    warnings.append('Student profile assumes English placement eligibility and '+('H2/A-level Mathematics qualification.' if request.math_qualified else 'no H2 Mathematics exemption.'))
    placeholders = [c["code"] for s in semesters for c in s["courses"] if c["placeholder"]]
    if placeholders:
        warnings.append("Replace elective placeholders with real courses before finalising: " + ", ".join(placeholders))
    audit = academic_audit(assignments, math_qualified=request.math_qualified, start_year=request.start_year)
    from backend.minors import audit_minors
    minor_audit = audit_minors(request, assignments, result.get('minor_allocations'), result.get('category_allocations'))
    if minor_audit['programmes']:
        warnings.append('Selected minor course groups, distinct units, sharing caps and explicit course preclusions were checked. Declaration, exemptions and programme/grade-based CourseReg eligibility still require confirmation.')
    if audit['status'] != 'passed':
        warnings.append('Exploratory preview only: foundation, prerequisite or student-profile requirements failed. Review the academic checks and regenerate. NUSMods export is disabled.')
    return {**result, "semesters": semesters, "total_units": total,
            'academic_audit': audit, 'exportable': audit['status'] == 'passed',
            'minor_audit': minor_audit,
            'student_profile': {'math_qualified': request.math_qualified, 'start_year': request.start_year},
            'weekly_timetables':weekly_timetables,
            'unpublished_courses':unpublished,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "last_semester": max((s["number"] for s in semesters if s["courses"]), default=0),
            "unmet_preferences": unmet, "warnings": warnings,
            "checked_card_ids": [c.id for c in request.cards if c.strength == "hard"]}
