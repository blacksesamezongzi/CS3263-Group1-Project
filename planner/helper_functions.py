from pycsp3 import *

def course_lookup(course_code, courses) -> CourseRepresentation | None:
    return next((course for course in courses if course.module_code == course_code), None)


def check_prereqs(prereq_tree, index, courses, semester):
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