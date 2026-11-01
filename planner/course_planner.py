"""Stable planner interface; backend choice does not affect schedule checking."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from time import perf_counter
import traceback
from typing import Literal
from .courses import COURSES, CS_FOUNDATION
from .checker import check_schedule
from .validation import validate_csp_assignment
from planner import courses, helper_functions
from pycsp3 import *

@dataclass
class SolveResult:
    status: Literal["FEASIBLE", "INFEASIBLE", "UNKNOWN", "ERROR"]
    assignment: dict[str, int] | None
    elapsed_seconds: float
    validation_errors: list[str]
    solver: str


def solve_foundation(focus_area, timeout=3.0, solution_dir=None, solver="fc_mrv_lcv", rules=COURSES) -> SolveResult:
    try:
        common_domain = list(range(0, 9))
        courses_list = VarArray(size=len(COURSES), dom=common_domain)

        cs2101_index = helper_functions.course_lookup("CS2101", COURSES).index
        cs2103t_index = helper_functions.course_lookup("CS2103T", COURSES).index

        FOCUS_CODES = courses.CS_FOCUS_AREAS[focus_area]["primaries"]
        FOCUS_COURSES = tuple(
                        course
                        for code in FOCUS_CODES
                        if (course := helper_functions.course_lookup(code, COURSES)) is not None
                    )

        satisfy(
            [courses_list[c.index] != 0 for c in CS_FOUNDATION],
            [helper_functions.check_prereqs(c.prereq_tree, c.index, COURSES, courses_list) for c in COURSES],
            [courses_list[cs2101_index] == courses_list[cs2103t_index]],
            [Sum(c.module_credit * (courses_list[c.index] != 0) for c in COURSES) >= 160],
            [Sum(c.module_credit * (courses_list[c.index] == s) for c in COURSES) >= 18
                for s in range(2, 9)],
            [Sum(c.module_credit * (courses_list[c.index] == s) for c in COURSES) <= 24
                for s in range(2, 9)],
            [Sum(c.module_credit * (courses_list[c.index] == 1) for c in COURSES) >= 18],
            [Sum(c.module_credit * (courses_list[c.index] == 1) for c in COURSES) <= 20],
            [
                (courses_list[c.index] == 0) | courses_list[c.index] % 2 != 0
                for c in COURSES
                if len(c.semesters) == 1
                and c.semesters[0]["semester_number"] == 1
            ],
            [
                courses_list[c.index] % 2 == 0
                for c in COURSES
                if len(c.semesters) == 1
                and c.semesters[0]["semester_number"] == 2
            ],
            [Sum(courses_list[c.index] != 0 for c in FOCUS_COURSES) >= 3],
            [AnyHold(courses_list[c.index] != 0 for c in FOCUS_COURSES if c.module_code.startswith("CS4"))],

        )

        result = solve()
        print(result)

        if result is SAT:
            for i in range(1, 9):
                print("Semester:" + str(i))
                sum = 0
                for c, v in enumerate(values(courses_list)):
                    if v == i:
                        print(COURSES[c].module_code)
                        sum += COURSES[c].module_credit
                
                print("Total creds:" + str(sum))

            #helper_functions.print_solution(fd_courses_list, courses_list, COURSES)


    except Exception as error:
        result = SolveResult("ERROR", None, 0.0,
                             [f"{type(error).__name__}: {error}"], solver)
        traceback.print_exc()

