import importlib
import itertools
import json
import random
import re

import pytest

from CSP_Solver_Local import CSP
from planner import CS_FOUNDATION, build_foundation_problem, solve_foundation
from planner.checker import check_schedule
from planner.foundation import solve_csp
from planner.validation import validate_csp_assignment
from planner.check_rules_against_nusmods import audit_rules, project_prerequisites


def problem(domains, constraints=()):
    csp = CSP(len(domains))
    for name, domain in domains.items():
        csp.separateDomain(name, domain)
    for constraint in constraints:
        csp.addConstraint(constraint)
    return csp


def test_foundation():
    csp = build_foundation_problem()
    assert csp.variables == 15
    assert len(csp.AllConstraints) == 13
    result = solve_foundation()
    assert result.status == "FEASIBLE", result.validation_errors
    assert not validate_csp_assignment(csp, result.assignment)
    assert not check_schedule(result.assignment)


@pytest.mark.parametrize("domains,constraints", [
    ({"A": [1], "B": [1]}, ["value[A] < value[B]"]),
    ({"A": [1, 2, 3], "B": [1, 2, 3]}, ["value[A] < value[B]", "value[B] < value[A]"]),
    ({"A": [1]}, ["value[A] > 1"]),
    ({"A": [1, 2], "B": [3, 4]}, ["value[A] == value[B]"]),
])
def test_impossible(domains, constraints):
    csp = problem(domains, constraints)
    assert solve_csp(csp).status == "INFEASIBLE"
    assert not csp.timed_out


def test_unary_filtering_and_backtrack():
    csp = problem({"A": [1]}, ["value[A] > 1"])
    assert csp.domains[1] == set()
    assert csp.domainHelp[1] == []
    csp.solve_BackTrack()
    assert not csp.stop
    csp.reset()
    assert csp.domains[1] == set()


def test_overlapping_names():
    result = solve_csp(problem({"CS2103": [1, 2], "CS2103T": [1, 2]},
                               ["value[ CS2103 ] < value[CS2103T]"]))
    assert result.status == "FEASIBLE"
    assert result.assignment == {"CS2103": 1, "CS2103T": 2}


@pytest.mark.parametrize("count", [1, 2])
def test_unknown_name(count):
    csp = CSP(count)
    csp.separateDomain("A", [1])
    with pytest.raises(ValueError, match="unknown variable 'B'"):
        csp.addConstraint("value[A] < value[B]")


def test_numeric_api():
    csp = CSP(2)
    csp.commonDomain([1, 2])
    csp.addConstraint("value[1] < value[2]")
    assert solve_csp(csp).assignment == {1: 1, 2: 2}
    with pytest.raises(ValueError, match="unknown variable"):
        csp.addConstraint("value[3] == 1")


def test_distinct_scope():
    csp = problem({"A": [1, 2], "B": [1, 2]},
                  ["value[A] < value[B] and value[A] >= 1"])
    assert not csp.multivariate
    assert csp.graph[1] == {2}
    assert csp.graph[2] == {1}
    assert csp.multivariateGraph[1][0][1] == (1, 2)
    assert solve_csp(csp).status == "FEASIBLE"


def test_ternary_registration_and_restoration():
    csp = problem({"A": [1, 2], "B": [1, 2], "C": [1, 2]},
                  ["value[A] == 2 and value[B] != value[C]"])
    assert csp.multivariate
    assert all(len(csp.multivariateGraph[i]) == 1 for i in range(1, 4))
    visited = []

    def invariant(obj, mrv):
        visited.append(tuple(obj.value))
        for i in range(1, obj.variables + 1):
            assert mrv.Help[i] == len(obj.domains[i])
        assert set(mrv.Ordering) == {
            (len(obj.domains[i]), i) for i in range(1, obj.variables + 1)
            if not obj.givenValue[i]}

    csp.search_state_hook = invariant
    result = solve_csp(csp)
    assert result.status == "FEASIBLE", result.validation_errors
    assert result.assignment["A"] == 2
    assert any(state[1] == 1 for state in visited)  # First LCV branch failed.
    assert not validate_csp_assignment(csp, result.assignment)
    csp.reset()
    assert csp.domains == [set(domain) for domain in csp.domainHelp]
    assert not any(csp.givenValue)


def test_deduplicated_removals():
    from CSP_Solver_Local.Util import toRemove
    csp = problem({"A": [1, 2], "B": [1, 2], "C": [1, 2]}, [
        "value[A] == 2 and value[B] != value[C]",
        "value[A] >= 2 and value[B] != value[C]",
    ])
    csp.givenValue[1] = csp.givenValue[2] = True
    csp.value[1] = csp.value[2] = 1
    removals = toRemove(csp, 2, 1)
    assert len(removals) == len(set(removals)) == 2
    assert solve_csp(csp).status == "FEASIBLE"


def test_solve_twice():
    csp = build_foundation_problem()
    for _ in range(2):
        result = solve_csp(csp)
        assert result.status == "FEASIBLE"
        assert not validate_csp_assignment(csp, result.assignment)
        assert not check_schedule(result.assignment)


def test_explicit_timeout(monkeypatch):
    module = importlib.import_module("CSP_Solver_Local.Forward_Checking.ForwardChecking_MRV_LCV")
    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(module, "perf_counter", lambda: next(ticks))
    csp = problem({"A": [1, 2]})
    assert solve_csp(csp, timeout=1).status == "UNKNOWN"
    assert csp.timed_out
    assert not csp.stop
    csp.reset()
    assert not csp.timed_out


def test_broken_schedule():
    assignment = solve_foundation().assignment
    assignment["CS2101"] = 1 if assignment["CS2103T"] != 1 else 2
    assert any("same semester" in error for error in check_schedule(assignment))
    del assignment["CS1101S"]
    assignment["EXTRA"] = 1
    assignment["MA1521"] = True
    errors = check_schedule(assignment)
    assert any("Missing course" in error for error in errors)
    assert any("Unexpected course" in error for error in errors)
    assert any("MA1521" in error for error in errors)


def test_postcondition_rejects_invalid_assignment():
    csp = problem({"A": [1, 2], "B": [1, 2]}, ["value[A] < value[B]"])
    assert validate_csp_assignment(csp, {"A": 1})
    assert validate_csp_assignment(csp, {"A": 0, "B": 2})
    assert validate_csp_assignment(csp, {"A": 2, "B": 1})


def test_solver_corruption_never_reported_feasible(monkeypatch):
    def corrupt(self, timeout):
        self.stop = 1
        self.value = [None] + [1] * self.variables
    monkeypatch.setattr(CSP, "solve_ForwardChecking_MRV_LCV", corrupt)
    result = solve_foundation()
    assert result.status == "ERROR"
    assert result.validation_errors


def test_independent_checker_failure_never_reported_feasible(monkeypatch):
    module = importlib.import_module("planner.foundation")
    monkeypatch.setattr(module, "check_schedule", lambda assignment, rules: ["broken rule"])
    result = solve_foundation()
    assert result.status == "ERROR"
    assert "broken rule" in result.validation_errors


def test_tiny_random_instances_against_exhaustive():
    rng = random.Random(3263)
    for _ in range(25):
        names = list("ABCD"[:rng.randint(1, 4)])
        domains = {name: rng.sample([1, 2, 3], rng.randint(1, 3)) for name in names}
        constraints = []
        for _ in range(rng.randint(1, 6)):
            a = rng.choice(names)
            if len(names) == 1 or rng.random() < 0.3:
                constraints.append(f"value[{a}] > {rng.randint(0, 3)}")
            else:
                a, b = rng.sample(names, 2)
                constraints.append(f"value[{a}] {rng.choice(['<', '=='])} value[{b}]")
        # Independent enumeration evaluates the original name-keyed expressions.
        expressions = [re.sub(r'value\[([A-Z])\]', r'value["\1"]', text)
                       for text in constraints]
        feasible = any(
            all(eval(expression, {"value": dict(zip(names, values)), "__builtins__": {}})
                for expression in expressions)
            for values in itertools.product(*(domains[name] for name in names)))
        csp = problem(domains, constraints)
        result = solve_csp(csp)
        assert result.status == ("FEASIBLE" if feasible else "INFEASIBLE")
        if feasible:
            assert not validate_csp_assignment(csp, result.assignment)


def test_rule_audit():
    result = audit_rules()
    assert result.mismatches == []
    assert any("S:2016" in note for note in result.disclosures)
    assert any("177" in note and "6733" in note for note in result.disclosures)


def test_audit_keeps_or_semantics():
    terms, notes = project_prerequisites({"or": ["A:D", "B:D", "EXTERNAL:D"]}, {"A", "B"})
    assert terms == {frozenset({"A"}), frozenset({"B"})}
    assert not notes


def test_rule_audit_detects_missing_edge(tmp_path):
    from planner.check_rules_against_nusmods import SNAPSHOT
    data = json.loads(SNAPSHOT.read_text())
    next(m for m in data["modules"] if m["module_code"] == "CS3230")["prereq_tree"] = "CS2040S:D"
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(data))
    assert any("CS3230" in error for error in audit_rules(path).mismatches)


def test_output_optional_and_directory_created(tmp_path):
    destination = tmp_path / "new" / "nested"
    result = solve_foundation(solution_dir=destination)
    assert result.status == "FEASIBLE"
    assert json.loads((destination / "foundation_result.json").read_text())["status"] == "FEASIBLE"
    csp = CSP(1, solution_path=tmp_path / "legacy")
    csp.commonDomain([1])
    csp.solve_ForwardChecking_MRV_LCV()
    assert (tmp_path / "legacy" / "ForwardChecking_MRV_LCV_Solution.txt").exists()


@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf")])
def test_invalid_timeout(timeout):
    assert solve_foundation(timeout=timeout).status == "ERROR"


def test_unsupported_solver():
    assert solve_foundation(solver="unimplemented").status == "ERROR"
