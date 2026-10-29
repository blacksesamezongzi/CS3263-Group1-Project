def course_lookup(course_code, courses) -> CourseRepresentation | None:
    return next((course for course in courses if course.module_code == course_code), None)

def check_prereqs(prereq_tree, problem, index, courses):
    
    if prereq_tree == None:
        return None

    # Base case: single prerequisite course
    if isinstance(prereq_tree, str):
        n = len(prereq_tree)
        if prereq_tree[n-2:] == ":D" :
            prereq_course = prereq_tree[:n-2]
        else:
            prereq_course = prereq_tree

        course = course_lookup(prereq_course, courses)
        if course is None:
            return None
        
        return f"(0 < value[{str(course.index)}] and value[{str(course.index)}] < value[{str(index)}])"

    # Recursive case: AND / OR combinations
    if isinstance(prereq_tree, dict):
        conditions = []

        for operator, prereqs in prereq_tree.items():
            subconditions = [
                check_prereqs(p, problem, index, courses)
                for p in prereqs
            ]

            # Remove None values
            subconditions = [c for c in subconditions if c is not None]

            if not subconditions:
                continue

            if operator == "and":
                conditions.append(f"({' and '.join(subconditions)})")

            elif operator == "or":
                conditions.append(f"({' or '.join(subconditions)})")

        # Multiple operators at the same level are combined with AND
        return f"({' and '.join(conditions)})" if conditions else None

    raise ValueError(f"Invalid prerequisite tree: {prereq_tree}")

def print_solution(csp, courses):
    for semester in range(1, 9):
        print(f"\nSemester {semester}:")
        for c in courses:
            if csp.value[c.index] == semester:
                print(c.module_code, end=" ")