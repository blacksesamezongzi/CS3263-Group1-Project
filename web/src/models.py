
from dataclasses import dataclass

@dataclass(frozen=True)
class CourseRepresentation:
    """A representation of a NUS course with its relevant attributes."""
    index: int
    module_code: str
    module_credit: int
    semesters: list[dict]
    prereq_tree: str | dict
