"""Stable planner interface; backend choice does not affect schedule checking."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from time import perf_counter
import traceback
from typing import Literal

import CSP_Solver_Local as CS
from .courses import COURSES, CS_FOUNDATION
from .checker import check_schedule
from .validation import validate_csp_assignment
from planner import courses, helper_functions


@dataclass
class SolveResult:
    status: Literal["FEASIBLE", "INFEASIBLE", "UNKNOWN", "ERROR"]
    assignment: dict[str, int] | None
    elapsed_seconds: float
    validation_errors: list[str]
    solver: str

#Add all constraints here
def build_foundation_problem(courses=COURSES, fd=CS_FOUNDATION):
    common_domain = list(range(0, 9))
    fd_domain = list(range(1, 9))
    problem = CS.CSP(len(courses), problem_name="CS3263CoursePlannerV1", solution_path='./Solution')
    problem.commonDomain(common_domain)
    for course in fd:
        problem.separateDomain(course.index, fd_domain)

    
    # Add prerequisite constraints
    for c in courses:
        course_index = c.index
        prereq_tree = c.prereq_tree
        constraint = helper_functions.check_prereqs(prereq_tree, problem, course_index, courses)
        if constraint is not None:
            problem.addConstraint(f"(value[{str(course_index)}] == 0) or ({constraint})")
            
    #Add corequisite constraints
    cs2101_index = helper_functions.course_lookup("CS2101", courses).index
    cs2103t_index = helper_functions.course_lookup("CS2103T", courses).index
    problem.addConstraint(f"(value[{str(cs2101_index)}] == value[{str(cs2103t_index)}])")

    return problem


def solve_csp(csp, timeout=3.0, solver="fc_mrv_lcv") -> SolveResult:
    """Solve a generic instance and enforce solver postconditions."""
    start = perf_counter()
    try:        
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("timeout must be finite and nonnegative")
        
        csp.solve_ForwardChecking_MRV_LCV(timeout=timeout)
        
        if csp.stop:
            helper_functions.print_solution(csp, COURSES)
            assignment = {i: csp.value[i]
                          for i in range(1, csp.variables + 1)}
            errors = validate_csp_assignment(csp, assignment)
            status = "ERROR" if errors else "FEASIBLE"
        else:
            assignment, errors = None, []
            status = "INFEASIBLE"

    except Exception as error:
        status, assignment = "ERROR", None
        errors = [f"{type(error).__name__}: {error}"]
        traceback.print_exc()

    return SolveResult(status, assignment, perf_counter() - start, errors, solver)


def solve_foundation(timeout=3.0, solution_dir=None, solver="fc_mrv_lcv", rules=COURSES) -> SolveResult:
    start = perf_counter()
    try:
        result = solve_csp(build_foundation_problem(rules), timeout, solver)
    except Exception as error:
        result = SolveResult("ERROR", None, 0.0,
                             [f"{type(error).__name__}: {error}"], solver)
        traceback.print_exc()

    result.elapsed_seconds = perf_counter() - start
    # Planner output is written only after both validators have run.
    if solution_dir is not None:
        try:
            directory = Path(solution_dir)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "foundation_result.json").write_text(
                json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            result.status = "ERROR"
            result.validation_errors.append(f"Cannot write output: {error}")
            traceback.print_exc()
    return result
