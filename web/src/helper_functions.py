"""Helper functions for NUS 4-year course planner."""

from pycsp3 import *
from src.models import CourseRepresentation

def course_lookup(course_code, courses) -> CourseRepresentation | None:
    """Given a course code in string format (e.g., "CS1101S")
       and the list of courses, returns the corresponding
       CourseRepresentation object if found, otherwise returns None."""

    return next((course for course in courses if course.module_code == course_code), None)

def check_prereqs(prereq_tree, index, courses, semester):
    """Helper function to check prerequisites for a given course based on its prerequisite tree.
       Returns a boolean expression that can be read by the csp solver."""
    if prereq_tree is None:
        return None

    # Base case: a single prerequisite course
    if isinstance(prereq_tree, str):
        prereq_course = prereq_tree.removesuffix(":D").removesuffix(":A-")
        course = course_lookup(prereq_course, courses)

        if course is None:
            return None

        prereq_index = course.index

        return (
            (semester[index] == 0)
            | (
                (semester[prereq_index] > 0)
                & (semester[prereq_index] < semester[index])
            )
        )

    # Recursive case: AND / OR combinations
    if isinstance(prereq_tree, dict):
        conditions = []

        for operator, prereqs in prereq_tree.items():
            subconditions = [
                check_prereqs(p, index, courses, semester)
                for p in prereqs
            ]

            # Ignore missing / unsupported prerequisite entries
            subconditions = [
                condition for condition in subconditions
                if condition is not None
            ]

            if not subconditions:
                continue

            if operator == "and":
                combined = subconditions[0]
                for condition in subconditions[1:]:
                    combined = combined & condition

            elif operator == "or":
                combined = subconditions[0]
                for condition in subconditions[1:]:
                    combined = combined | condition

            else:
                continue

            conditions.append(combined)

        if not conditions:
            return None

        # Combine multiple operator groups at this node
        combined = conditions[0]
        for condition in conditions[1:]:
            combined = combined & condition

        return combined

    return None

# def print_solution(fd_courses_list, courses_list, courses):
#     # for semester in range(1, 9):
#         # print(f"\nSemester {semester}:")
#     print(values(fd_courses_list))
#     print(values(courses_list))
