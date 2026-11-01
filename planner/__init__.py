"""Fixed-course baseline API; snapshot-based planner lives in course_planner."""
from .cs_foundation import CS_FOUNDATION, FoundationRules
from .foundation import SolveResult, build_foundation_problem, solve_foundation
from .courses import COURSES, CourseRepresentation

__all__ = ["CS_FOUNDATION", "FoundationRules", "COURSES", "CourseRepresentation",
           "SolveResult", "build_foundation_problem", "solve_foundation"]
