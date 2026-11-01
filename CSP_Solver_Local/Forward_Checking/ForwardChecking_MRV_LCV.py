"""Planner-supported forward checking with MRV/LCV and explicit deadlines."""
from time import perf_counter
from ..Util import LCV, MRV, toRemove, verify


def ForwardChecking_MRV_LCV(obj, timeout):
    deadline = perf_counter() + timeout
    ordering = MRV(obj)
    solution = None

    def observe():
        # Optional invariant hook for tests/debugging. No planner dependency.
        hook = getattr(obj, "search_state_hook", None)
        if hook is not None:
            hook(obj, ordering)

    def expired():
        if perf_counter() >= deadline:
            obj.timed_out = True
            return True
        return False

    def search():
        nonlocal solution
        observe()
        if expired():
            return False
        if ordering.finished():
            if verify(obj):
                solution = obj.value[:]
                return True
            return False
        current = ordering.minimum()
        cur = current[1]
        if not obj.domains[cur]:
            return False
        ordering.remove(current)
        previous = obj.value[cur]
        try:
            for _, candidate in LCV(obj, cur):
                if expired():
                    return False
                obj.value[cur] = candidate
                obj.givenValue[cur] = True
                # Check fully assigned constraints as well as pruning future ones.
                valid = all(
                    not all(obj.givenValue[v] for v in scope)
                    or eval(constraint, {"value": obj.value, "__builtins__": {}})
                    for constraint, scope in obj.multivariateGraph[cur]
                )
                if not valid:
                    continue
                removed = toRemove(obj, cur, candidate)
                try:
                    for variable, value in removed:
                        obj.domains[variable].remove(value)
                        ordering.correct(variable, len(obj.domains[variable]))
                    if search():
                        return True
                    if obj.timed_out:
                        return False
                finally:
                    for variable, value in removed:
                        obj.domains[variable].add(value)
                        ordering.correct(variable, len(obj.domains[variable]))
        finally:
            obj.givenValue[cur] = False
            obj.value[cur] = previous
            ordering.add((len(obj.domains[cur]), cur))
            observe()
        return False

    obj.timed_out = False
    obj.stop = 0
    if search():
        obj.value = solution
        obj.stop = 1
