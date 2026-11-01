"""Run with python -m planner.run_foundation from the repository root."""
import argparse
from .foundation import solve_foundation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--out", default=None, metavar="DIR")
    args = parser.parse_args()
    result = solve_foundation(timeout=args.timeout, solution_dir=args.out)
    print(f"Status: {result.status} | Solver: {result.solver} | "
          f"Elapsed: {result.elapsed_seconds:.6f}s")
    if result.status == "FEASIBLE":
        for semester in range(1, 9):
            courses = sorted(c for c, s in result.assignment.items() if s == semester)
            print(f"Y{(semester + 1) // 2}S{(semester - 1) % 2 + 1}: "
                  + (", ".join(courses) if courses else "(empty)"))
        print("Conditional on encoded rules and the AY2026/27 snapshot; not a graduation audit.")
    for error in result.validation_errors:
        print(f"ERROR: {error}")
    return 0 if result.status == "FEASIBLE" else (2 if result.status == "ERROR" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
