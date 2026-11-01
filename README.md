# CS course scheduling baseline

This is a reproducible **CS major, AY2026/27, 15 fixed-course** semester-assignment
baseline. It finds a feasible assignment over eight regular semesters; it does
not optimize a preference score. The fixed list includes selected CS foundation,
mathematics and common-curriculum courses, not the complete degree curriculum.

## Run from a fresh clone

Use Python 3.10 or newer. From the `CS3263-Group1-Project` repository root:

```sh
python -m venv .venv
```

Activate it on Windows PowerShell with `.\.venv\Scripts\Activate.ps1`, or on
macOS/Linux with `source .venv/bin/activate`. Then run:

```sh
python -m pip install -r requirements.txt
python -m planner.run_foundation
python -m pytest -q
python -m planner.check_rules_against_nusmods
```

The planner has no network dependency at runtime. An optional output directory
is created automatically:

```sh
python -m planner.run_foundation --timeout 3 --out Solutions
```

The command prints status and courses grouped by semester. With `--out`, it also
writes `foundation_result.json` after validation. No file is written by default.
Exit codes are 0 for FEASIBLE, 1 for INFEASIBLE/UNKNOWN, and 2 for ERROR.
`--timeout 0` deterministically returns UNKNOWN. Deadlines are checked inside
search; this is a cooperative deadline, not a hard process execution limit.

`Scheduler.ipynb` calls the same planner interface. Its data-fetching cell is
unchanged and optional: install `requests>=2.31.0` separately if rerunning it.
That cell fetches broadly and overwrites the snapshot; normal runs should use
the cached data and do not need requests or Jupyter.

## Model and source assumptions

`planner/cs_foundation.py` is the single source for the 15-course list,
prerequisites and co-requisites. Each course occurs once with semester in 1..8.
There are 12 strict prerequisite inequalities and one co-requisite equality.
Compared with the original notebook, the cached data requires two extra edges:
CS1231S before CS3230, and MA1521 before ST2334.

Rules are based on the repository's AY2026/27 NUSMods snapshot and the
[NUS CS AY2026/27 cohort requirements](https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/).
The audit reads the local snapshot, projects prerequisites onto this fixed course
pathway and compares them with the encoded AND-lists. In-scope OR alternatives
remain alternatives; they are not incorrectly converted to an AND. A future
in-scope `nOf` node is explicitly unsupported and fails the audit.

The audit always discloses these assumptions/data issues:

- Entry mathematics is assumed to satisfy MA1301/MA1301X conditions for CS1231S,
  MA1521 and MA1522. This baseline does not model qualification verification.
- Planned courses are assumed passed with the grades required by prerequisites.
- ES2660 is assumed applicable based on the selected programme requirements.
  The cached prerequisite contains the cohort marker `S:2016`; this is an
  unresolved metadata anomaly, not a verified eligibility condition. Its exact
  current form is acknowledged by the audit; changes require review.
- The file contains 176 curated records, but `total_modules_fetched` is 6733.
  The audit reports this discrepancy; the snapshot is not silently rewritten.
- Out-of-scope alternatives to a usable in-scope prerequisite branch are not
  necessary for this fixed pathway. Entirely external prerequisite groups must
  match an explicit declared assumption; unknown conditions fail the audit.

Passing this audit means **no unexplained prerequisite-projection mismatch**.
It does not validate all programme rules or establish the assumptions as facts.

## Results and validation

`build_foundation_problem(rules=CS_FOUNDATION)` builds a solver instance.
`solve_foundation(timeout=3.0, solution_dir=None, solver="fc_mrv_lcv")` returns a
`SolveResult` with status, assignment, elapsed time, validation errors and solver.
A custom rules object may be supplied with `rules=`. Assignments are keyed by
course code, so duplicate occurrences cannot be represented; missing and extra
courses are rejected.

Every FEASIBLE planner result passes both:

1. Generic CSP postconditions: all variables assigned, values in the original
   domains, and all registered expressions true.
2. An independent schedule checker: course coverage, integer semester domains,
   strict prerequisite ordering and co-requisite equality, using curriculum data
   without solver objects or generated expression strings.

Search exhaustion means INFEASIBLE; timeout without a solution means UNKNOWN.
A validator, backend, input or output error means ERROR. An ERROR result may
retain the rejected candidate assignment for diagnosis; it is not a valid plan.
The existing vendored expression API is for trusted code only, not arbitrary
student or LLM input. Only FC-MRV-LCV is supported as a planner backend. Other
vendored algorithms have import fixes but are not tested or supported planners.

Tests cover impossible instances, unary filtering, identifiers, distinct scopes,
ternary pruning, backtracking/MRV invariants, repeated solves, deterministic
clock-based timeout, both validation gates, output paths and exhaustive comparison
on seeded random tiny instances. The notebook data-fetching cell is preserved.

## Scope limits

Results are conditional on the encoded rules and the AY2026/27 NUSMods snapshot.
This baseline does not cover units, semester workload, offering semesters,
electives, focus areas, completed courses, internships/SEP, or timetable clashes.
It does not establish graduation eligibility. Course placement may be uneven and
some semesters may be empty. No LLM integration or website is included.

## Integration note after the constraints merge

The fixed-course commands use `planner.foundation` and `planner.cs_foundation`.
The newer snapshot-based implementation remains in `planner.course_planner`
and `planner.courses`; its `CS_FOUNDATION` is a tuple of course records, distinct
from the fixed-baseline rule object exported by `planner`.

The constraints merge cleared `prereq_tree` fields for CS1231S, MA1521,
MA1522 and ES2660. Those four fields have been restored from commit `87408ad`,
without changing other merged snapshot data. The audit again reports zero
unexplained mismatches. Entry mathematics and the ES2660 cohort marker remain
explicit assumptions/data notes; restoring cached metadata does not verify
student eligibility or resolve the S:2016 anomaly.
