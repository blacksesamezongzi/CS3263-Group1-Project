"""Main code for implementing the CSP/COP logic."""

import traceback
from src.courses import COURSES, CS_FOUNDATION, CS_FOCUS_AREAS
from src.helper_functions import course_lookup, check_prereqs
from pycsp3 import *

def solve_csp(focus_area):
    try:
        #Set up the csp problem with the common domain
        courses_list = VarArray(size=len(COURSES), dom=list(range(0, 9)))

        #Intermediary variables needed to check constraints
        cs2101_index = course_lookup("CS2101", COURSES).index
        cs2103t_index = course_lookup("CS2103T", COURSES).index

        FOCUS_CODES = CS_FOCUS_AREAS[focus_area]["primaries"]
        FOCUS_COURSES = tuple(
                        course
                        for code in FOCUS_CODES
                        if (course := course_lookup(code, COURSES)) is not None
                    )

        #Constraints to be satisfied by the CSP solver
        satisfy(
            # Constraint 1: All CS foundation courses must be taken
            [courses_list[c.index] != 0 for c in CS_FOUNDATION],

            # Constraint 2: Prerequisites must be satisfied for all courses
            [check_prereqs(c.prereq_tree, c.index, COURSES, courses_list) for c in COURSES],

            # Constraint 3: Prerequisites must be satisfied
            [courses_list[cs2101_index] == courses_list[cs2103t_index]],

            # Constraint 4: Total credits must be at least 160
            [Sum(c.module_credit * (courses_list[c.index] != 0) for c in COURSES) >= 160],

            # Constraint 5: Total credits per semester must be between 18 and 24 for semesters 2-8, and between 18 and 20 for semester 1
            [Sum(c.module_credit * (courses_list[c.index] == s) for c in COURSES) >= 18
                for s in range(2, 9)],
            [Sum(c.module_credit * (courses_list[c.index] == s) for c in COURSES) <= 24
                for s in range(2, 9)],
            [Sum(c.module_credit * (courses_list[c.index] == 1) for c in COURSES) >= 18],
            [Sum(c.module_credit * (courses_list[c.index] == 1) for c in COURSES) <= 20],

            # Constraint 6: Courses that are only offered in one semester must be taken in that semester
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

            # Constraint 7: At least 3 courses from the chosen focus area primaries must be taken, including at least one 4000-level course
            [Sum(courses_list[c.index] != 0 for c in FOCUS_COURSES) >= 3],
            [AnyHold(courses_list[c.index] != 0 for c in FOCUS_COURSES if c.module_code.startswith("CS4"))],

        )

        result = solve()

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
        traceback.print_exc()
