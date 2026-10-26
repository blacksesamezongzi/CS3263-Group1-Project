"""Generic solver postconditions, separate from the curriculum checker."""


def validate_csp_assignment(csp, assignment):
    errors = []
    values = [None] * (csp.variables + 1)
    expected = {csp.variableConversion[i] for i in range(1, csp.variables + 1)}
    for extra in assignment.keys() - expected:
        errors.append(f"Unexpected variable {extra!r}")
    for index in range(1, csp.variables + 1):
        name = csp.variableConversion[index]
        if name not in assignment:
            errors.append(f"Missing variable {name!r}")
            continue
        value = assignment[name]
        values[index] = value
        if value not in csp.domainHelp[index]:
            errors.append(f"{name}: {value!r} is outside its original domain")
    if not errors:
        for number, constraint in enumerate(csp.AllConstraints, 1):
            try:
                if not eval(constraint, {"value": values, "__builtins__": {}}):
                    errors.append(f"CSP constraint {number} is false")
            except Exception as error:
                errors.append(f"CSP constraint {number}: {type(error).__name__}: {error}")
    return errors
