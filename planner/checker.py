"""Schedule checks using only curriculum data, independent of the CSP library."""
from .courses import COURSES, CS_FOUNDATION


def check_schedule(assignment, rules=CS_FOUNDATION):
    errors = []
    expected = set(rules)
    for course in sorted(expected - assignment.keys()):
        errors.append(f"Missing course {course}")
    for course in sorted(assignment.keys() - expected):
        errors.append(f"Unexpected course {course}")
    valid = set()
    for course in rules:
        if course in assignment:
            semester = assignment[course]
            if type(semester) is not int or semester not in rules.semesters:
                errors.append(f"{course}: semester {semester!r} must be in {rules.semesters}")
            else:
                valid.add(course)
    for course, prerequisites in rules.prerequisites.items():
        for prerequisite in prerequisites:
            if course in valid and prerequisite in valid:
                if assignment[prerequisite] >= assignment[course]:
                    errors.append(
                        f"{course} (sem {assignment[course]}) must come after "
                        f"{prerequisite} (sem {assignment[prerequisite]})")
    for first, second in rules.corequisites:
        if first in valid and second in valid and assignment[first] != assignment[second]:
            errors.append(f"{first} and {second} must be in the same semester "
                          f"(got {assignment[first]} and {assignment[second]})")
    return errors
