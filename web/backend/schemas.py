"""The versioned, allow-listed contract shared by the LLM, UI and solver."""
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from backend.catalog import CATALOG, FOCUS_AREAS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MinUnits(StrictModel):
    type: Literal["min_total_units"]
    units: int = Field(ge=0, le=240)


class CourseSet(StrictModel):
    type: Literal["require_courses", "exclude_courses"]
    courses: list[str] = Field(min_length=1, max_length=160)

    @field_validator("courses")
    @classmethod
    def known(cls, codes):
        codes = list(dict.fromkeys(c.upper() for c in codes))
        unknown = set(codes) - CATALOG.keys()
        if unknown:
            raise ValueError("Courses outside the project catalogue: " + ", ".join(sorted(unknown)))
        return codes


class ToggleRule(StrictModel):
    type: Literal["prerequisites", "corequisites", "semester_availability", "exam_clashes", "weekly_feasibility"]


class CategoryUnits(StrictModel):
    type: Literal["category_units"]
    category: Literal["GEC", "GEA", "GESS", "GEN", "ID_CD"]
    units: int = Field(ge=4, le=24)


class CourseSemester(StrictModel):
    type: Literal["course_in_semester"]
    course: str
    semester: int = Field(ge=1, le=12)

    @field_validator("course")
    @classmethod
    def known(cls, code):
        code = code.upper()
        if code not in CATALOG:
            raise ValueError(f"{code} is outside the project catalogue")
        return code


class FinishBy(StrictModel):
    type: Literal["finish_by"]
    semester: int = Field(ge=1, le=12)


class SemesterUnits(StrictModel):
    type: Literal["semester_units"]
    minimum: int = Field(ge=0, le=40)
    maximum: int = Field(ge=0, le=40)
    first_semester_maximum: int = Field(default=20, ge=0, le=40)

    @model_validator(mode="after")
    def band(self):
        if self.minimum > self.maximum or self.minimum > self.first_semester_maximum:
            raise ValueError("Minimum workload exceeds maximum")
        return self


class WorkloadTarget(StrictModel):
    type: Literal["workload_target"]
    units: int = Field(ge=4, le=32)


class Blocked(StrictModel):
    type: Literal["blocked_semesters"]
    semesters: list[Annotated[int, Field(ge=1, le=12)]] = Field(min_length=1, max_length=12)


class Focus(StrictModel):
    type: Literal["focus_area"]
    area: str

    @field_validator("area")
    @classmethod
    def known(cls, area):
        if area not in FOCUS_AREAS:
            raise ValueError("Unknown focus area")
        return area


Rule = Annotated[Union[MinUnits, CourseSet, ToggleRule, CourseSemester, FinishBy,
                       SemesterUnits, WorkloadTarget, Blocked, Focus, CategoryUnits], Field(discriminator="type")]


class ConstraintCard(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=800)
    strength: Literal["hard", "soft"] = "hard"
    source: Literal["default", "user"] = "user"
    rules: list[Rule] = Field(min_length=1, max_length=30)
    source_urls: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("source_urls")
    @classmethod
    def official_sources(cls, urls):
        from urllib.parse import urlparse
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not (parsed.hostname == "nus.edu.sg" or
                    (parsed.hostname or "").endswith(".nus.edu.sg") or parsed.hostname in {"nusmods.com", "api.nusmods.com"}):
                raise ValueError("Requirement sources must link to NUS or NUSMods")
        return list(dict.fromkeys(urls))

    @model_validator(mode="after")
    def supported_strength(self):
        soft_types = {"course_in_semester", "finish_by", "workload_target"}
        if self.strength == "soft" and any(r.type not in soft_types for r in self.rules):
            raise ValueError("This rule has no soft-constraint implementation")
        if self.strength == "hard" and any(r.type == "workload_target" for r in self.rules):
            raise ValueError("Use semester_units for hard workload limits")
        return self


class PlanRequest(StrictModel):
    schema_version: Literal[1] = 1
    cards: list[ConstraintCard] = Field(max_length=80)
    horizon: int = Field(default=10, ge=2, le=12)
    start_year: int = Field(default=2026, ge=2020, le=2040)
    math_qualified: bool = True
    allow_unpublished: bool = False

    @model_validator(mode="after")
    def unique_ids(self):
        if len({c.id for c in self.cards}) != len(self.cards):
            raise ValueError("Constraint card IDs must be unique")
        if any(getattr(r, "semester", 1) > self.horizon or
               any(s > self.horizon for s in getattr(r, "semesters", []))
               for c in self.cards for r in c.rules):
            raise ValueError("A semester is beyond the selected planning horizon")
        return self


class ParseRequest(StrictModel):
    message: str = Field(min_length=1, max_length=3000)
    cards: list[ConstraintCard] = Field(default_factory=list, max_length=80)
    horizon: int = Field(default=10, ge=2, le=12)


class ParseResult(StrictModel):
    reply: str = Field(min_length=1, max_length=1200)
    cards: list[ConstraintCard] = Field(default_factory=list, max_length=10)
    needs_clarification: bool = False


class TimetableRequest(StrictModel):
    courses: list[str] = Field(min_length=1, max_length=12)
    semester: int = Field(ge=1, le=2)
    academic_year: str = Field(default="2026-2027", pattern=r"^20\d{2}-20\d{2}$")

    @field_validator("courses")
    @classmethod
    def known(cls, codes):
        return CourseSet(type="require_courses", courses=codes).courses


class ExportRequest(StrictModel):
    assignments: dict[str, Annotated[int, Field(ge=0, le=12)]] = Field(max_length=400)
    horizon: int = Field(ge=2, le=12)
    start_year: int = Field(ge=2020, le=2040)
    math_qualified: bool = True

    @model_validator(mode='after')
    def valid_assignments(self):
        if set(self.assignments) - CATALOG.keys():
            raise ValueError('Unknown course in exported assignments')
        if any(s > self.horizon for s in self.assignments.values()):
            raise ValueError('Exported semester exceeds the planning horizon')
        return self
