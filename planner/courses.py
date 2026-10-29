from dataclasses import dataclass
import json

from planner import helper_functions

@dataclass(frozen=True)
class CourseRepresentation:
    index: int
    module_code: str
    module_credit: int
    semesters: list[dict]
    prereq_tree: str | dict

with open("nusmods_modules.json") as f:
    modules = json.load(f).get("modules", [])

COURSES = [
    CourseRepresentation(
        index = index + 1,
        module_code=module["module_code"],
        module_credit=int(module["module_credit"]),
        semesters=module.get("semesters", []),
        prereq_tree=module.get("prereq_tree", None)
    )
    for index, module in enumerate(modules)
]

CS_FOUNDATION_CODES = {
        "CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100",
        "CS2101", "CS2103T", "CS2106", "CS2109S", "CS3230",
        "MA1521", "MA1522", "IS1108", "ST2334", "ES2660",
}

CS_FOUNDATION = tuple(
    course
    for code in CS_FOUNDATION_CODES
    if (course := helper_functions.course_lookup(code, COURSES)) is not None
)

