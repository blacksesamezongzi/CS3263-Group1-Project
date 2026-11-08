"""One process and temporary working directory per PyCSP3 model."""
import json
from pathlib import Path
import sys


def main():
    input_path, output_path = map(Path, sys.argv[1:3])
    # PyCSP3 consumes command-line arguments on import. Use its console mode.
    sys.argv = [""]
    from backend.schemas import PlanRequest
    from backend.solver_adapter import solve_plan
    result = solve_plan(PlanRequest.model_validate_json(input_path.read_text()))
    output_path.write_text(json.dumps(result))


if __name__ == "__main__":
    main()
