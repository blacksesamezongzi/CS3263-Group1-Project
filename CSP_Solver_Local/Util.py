from sortedcontainers import SortedList
big = 100000000

class MRV:
    def __init__(self, obj):
        self.Ordering = SortedList()
        self.Help = dict()
        for i in range(1,obj.variables + 1):
            self.Ordering.add((len(obj.domains[i]),i))
            self.Help[i] = len(obj.domains[i])
    def finished(self):
        return len(self.Ordering) == 0
    def size(self):
        return len(self.Ordering)
    def minimum(self):
        return self.Ordering[0]
    def remove(self, element):
        self.Ordering.discard(element)
    def add(self, element):
        if element not in self.Ordering:
            self.Ordering.add(element)
    def decrease(self, rem):
        # rem = [length, variable]
        self.remove(rem)
        self.Help[rem[1]] -= 1
        self.add((rem[0]-1,rem[1]))
    def increase(self, rem):
        self.remove(rem)
        self.Help[rem[1]] += 1
        self.add((rem[0]+1,rem[1]))
    def correct(self, rem, newLen):
        self.remove((self.Help[rem], rem))
        self.Help[rem] = newLen
        self.add((self.Help[rem], rem))

def _removals(obj, cur, candidate):
    """Find unsupported values when exactly one scoped variable remains free."""
    previous = obj.value[:]
    removed = set()
    try:
        obj.value[cur] = candidate
        for constraint, scope in obj.multivariateGraph[cur]:
            remaining = [v for v in scope if v != cur and not obj.givenValue[v]]
            if len(remaining) != 1:
                continue
            variable = remaining[0]
            for value in obj.domains[variable]:
                obj.value[variable] = value
                if not eval(constraint, {"value": obj.value, "__builtins__": {}}):
                    removed.add((variable, value))
    finally:
        obj.value[:] = previous
    return sorted(removed)


def LCV(obj, cur):
    return sorted((len(_removals(obj, cur, value)), value)
                  for value in obj.domains[cur])


def toRemove(obj, cur, value):
    obj.value[cur] = value
    return _removals(obj, cur, value)


def verify(obj, getFault=False):
    return all(eval(constraint, {"value": obj.value, "__builtins__": {}})
               for constraint in obj.AllConstraints)
