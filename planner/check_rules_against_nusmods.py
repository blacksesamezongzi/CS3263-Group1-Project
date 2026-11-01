"""Audit the fixed pathway against the cached snapshot, without network access.

Projection keeps OR semantics: alternative in-scope sets remain alternatives,
not an AND-list. External-only OR groups are disclosed assumptions. An external
alternative to a usable in-scope branch is not needed by this fixed pathway.
This audits prerequisite projection only, not all programme or NUSMods rules.
"""
import argparse
from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path

from .cs_foundation import CS_FOUNDATION, EXTERNAL_ASSUMPTIONS

SNAPSHOT = Path(__file__).resolve().parents[1] / "nusmods_modules.json"


def leaves(tree):
    if isinstance(tree, str):
        return {tree.split(":", 1)[0]}
    if isinstance(tree, list):
        return set().union(*(leaves(item) for item in tree))
    if isinstance(tree, dict):
        return set().union(*(leaves(value) for key, value in tree.items()
                             if key in {"and", "or", "nOf"}))
    return set()


def project_prerequisites(tree, courses):
    """Return DNF prerequisite sets and explicit external assumptions."""
    if tree is None:
        return {frozenset()}, set()
    if isinstance(tree, dict) and set(tree) == {"cohort"}:
        return {frozenset()}, {"cohort condition: " + json.dumps(tree["cohort"], sort_keys=True)}
    if isinstance(tree, str):
        code = tree.split(":", 1)[0]
        if code in courses:
            return {frozenset({code})}, set()
        return {frozenset()}, {f"external courses: {code}"}
    if not isinstance(tree, dict) or len(tree) != 1:
        raise ValueError(f"unsupported prerequisite node: {tree!r}")
    operator, children = next(iter(tree.items()))
    if operator not in {"and", "or", "nOf"} or not isinstance(children, list):
        raise ValueError(f"unsupported prerequisite operator: {operator!r}")
    if operator == "nOf":
        # Current selected pathway uses an in-scope alternative to external nOf.
        # Fail explicitly if a future snapshot needs actual in-scope nOf logic.
        if leaves(tree) & courses:
            raise ValueError("in-scope nOf is not supported by this fixed-pathway audit")
        if len(children) != 2 or type(children[0]) is not int:
            raise ValueError(f"malformed nOf: {tree!r}")
        return {frozenset()}, {"external courses: " + ", ".join(sorted(leaves(tree)))}
    branches = [project_prerequisites(child, courses) for child in children]
    if operator == "or":
        internal = [(terms, notes) for terms, notes in branches if any(terms)]
        if internal:
            return (set().union(*(terms for terms, _ in internal)),
                    set().union(*(notes for _, notes in internal)))
        notes = set().union(*(notes for _, notes in branches))
        external = leaves(tree)
        if notes and all(note.startswith("external courses: ") for note in notes):
            notes = {"external courses: " + ", ".join(sorted(external))}
        return {frozenset()}, notes
    terms = {frozenset().union(*combination)
             for combination in product(*(terms for terms, _ in branches))}
    return terms, set().union(*(notes for _, notes in branches))


@dataclass
class RuleAudit:
    mismatches: list[str]
    disclosures: list[str]


def audit_rules(snapshot=SNAPSHOT, rules=CS_FOUNDATION):
    data = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    errors, disclosures = [], []
    if data.get("academic_year") != "2026-2027":
        errors.append("Expected AY2026-2027 snapshot")
    modules = {module["module_code"]: module for module in data["modules"]}
    if len(modules) != len(data["modules"]):
        errors.append("Duplicate module codes in snapshot")
    if data.get("total_modules_fetched") != len(modules):
        disclosures.append(f"Snapshot metadata says {data.get('total_modules_fetched')} fetched; "
                           f"curated file contains {len(modules)} records.")
    for course in rules.courses:
        if course not in modules:
            errors.append(f"{course}: missing from snapshot")
            continue
        try:
            terms, notes = project_prerequisites(modules[course].get("prereq_tree"),
                                                 set(rules.courses))
        except ValueError as error:
            errors.append(f"{course}: {error}")
            continue
        expected = {frozenset(rules.prerequisites.get(course, ()))}
        if terms != expected:
            errors.append(f"{course}: snapshot alternatives {sorted(map(sorted, terms))} "
                          f"!= encoded {sorted(map(sorted, expected))}")
        accepted = EXTERNAL_ASSUMPTIONS.get(course, set())
        if notes != accepted:
            errors.append(f"{course}: external conditions changed: "
                          f"actual={sorted(notes)}, expected={sorted(accepted)}")
        for note in sorted(notes):
            disclosures.append(f"{course}: {note} (explicit assumption; see cs_foundation.py)")
    return RuleAudit(errors, disclosures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    result = audit_rules(args.snapshot)
    for message in result.disclosures:
        print(f"ASSUMPTION / DATA NOTE: {message}")
    for message in result.mismatches:
        print(f"MISMATCH: {message}")
    print(f"Unexplained mismatches: {len(result.mismatches)}")
    return int(bool(result.mismatches))


if __name__ == "__main__":
    raise SystemExit(main())
