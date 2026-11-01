"""Fixed CS AY2026/27 baseline, NOT the full foundation/degree curriculum.

Sources: repository nusmods_modules.json (AY2026-2027 snapshot), and
https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/ (CS2101/CS2103T).
Compared with the original notebook, add CS1231S -> CS3230 and
MA1521 -> ST2334. OR alternatives are restricted to the chosen in-scope
pathway; this is not a general equivalence/exemption model.

Assumptions: entry mathematics satisfies MA1301/MA1301X conditions for
CS1231S, MA1521 and MA1522. All planned courses are passed at the required
grade. ES2660 applicability is assumed for this cohort from the programme
requirements; the cached prerequisite's S:2016 cohort marker is a disclosed
metadata anomaly, not evidence that this condition has been satisfied.
The four prerequisite fields cleared during the constraints merge were restored
from commit 87408ad; the external conditions remain explicit planning assumptions.
"""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class FoundationRules:
    courses: tuple[str, ...]
    prerequisites: Mapping[str, tuple[str, ...]]
    corequisites: tuple[tuple[str, str], ...]
    semesters: tuple[int, ...] = tuple(range(1, 9))


CS_FOUNDATION = FoundationRules(
    courses=(
        "CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100",
        "CS2101", "CS2103T", "CS2106", "CS2109S", "CS3230",
        "MA1521", "MA1522", "IS1108", "ST2334", "ES2660",
    ),
    prerequisites={
        "CS2030S": ("CS1101S",),
        "CS2040S": ("CS1101S", "CS1231S"),
        "CS2100": ("CS1101S",),
        "CS2103T": ("CS2030S", "CS2040S"),
        "CS2106": ("CS2100",),
        "CS2109S": ("CS2040S", "MA1521"),
        "CS3230": ("CS2040S", "CS1231S"),
        "ST2334": ("MA1521",),
    },
    corequisites=(("CS2103T", "CS2101"),),
)

# Expected audit disclosures. Changed/unrecognized conditions must fail the audit.
EXTERNAL_ASSUMPTIONS = {
    "CS1231S": {"external courses: MA1301, MA1301X"},
    "MA1521": {"external courses: MA1301, MA1301X"},
    "MA1522": {"external courses: MA1301, MA1301X"},
    "ES2660": {'cohort condition: {"rule": "MUST_BE_IN", "years": ["S:2016"]}'},
}
