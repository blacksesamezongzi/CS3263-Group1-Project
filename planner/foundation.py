"""Stable planner interface; backend choice does not affect schedule checking."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Literal

from CSP_Solver_Local import CSP
from .cs_foundation import CS_FOUNDATION
from .checker import check_schedule
from .validation import validate_csp_assignment


@dataclass
class SolveResult:
    status: Literal["FEASIBLE", "INFEASIBLE", "UNKNOWN", "ERROR"]
    assignment: dict[str, int] | None
    elapsed_seconds: float
    validation_errors: list[str]
    solver: str


def build_foundation_problem(rules=CS_FOUNDATION) -> CSP:
    if len(set(rules.courses)) != len(rules.courses):
        raise ValueError("duplicate course in rules")
    problem = CSP(len(rules.courses), problem_name="CS AY2026/27 fixed-course baseline")
    for course in rules.courses:
        problem.separateDomain(course, rules.semesters)
    for course, prerequisites in rules.prerequisites.items():
        for prerequisite in prerequisites:
            problem.addConstraint(f"value[{prerequisite}] < value[{course}]")
    for first, second in rules.corequisites:
        problem.addConstraint(f"value[{first}] == value[{second}]")
    return problem


def solve_csp(csp, timeout=3.0, solver="fc_mrv_lcv") -> SolveResult:
    """Solve a generic instance and enforce solver postconditions."""
    start = perf_counter()
    try:
        if solver != "fc_mrv_lcv":
            raise ValueError(f"unsupported planner solver {solver!r}")
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("timeout must be finite and nonnegative")
        csp.solve_ForwardChecking_MRV_LCV(timeout=timeout)
        if csp.stop:
            assignment = {csp.variableConversion[i]: csp.value[i]
                          for i in range(1, csp.variables + 1)}
            errors = validate_csp_assignment(csp, assignment)
            status = "ERROR" if errors else "FEASIBLE"
        else:
            assignment, errors = None, []
            status = "UNKNOWN" if csp.timed_out else "INFEASIBLE"
    except Exception as error:
        status, assignment = "ERROR", None
        errors = [f"{type(error).__name__}: {error}"]
    return SolveResult(status, assignment, perf_counter() - start, errors, solver)


def solve_foundation(timeout=3.0, solution_dir=None, solver="fc_mrv_lcv", rules=CS_FOUNDATION) -> SolveResult:
    start = perf_counter()
    try:
        result = solve_csp(build_foundation_problem(rules), timeout, solver)
        if result.status == "FEASIBLE":
            result.validation_errors.extend(check_schedule(result.assignment, rules))
            if result.validation_errors:
                result.status = "ERROR"
    except Exception as error:
        result = SolveResult("ERROR", None, 0.0,
                             [f"{type(error).__name__}: {error}"], solver)
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
    return result
