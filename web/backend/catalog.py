"""Read the team's snapshot without importing PyCSP3 into the API process."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = json.loads((ROOT / "assets/data/course_details.json").read_text())
DETAILS = SNAPSHOT["courses"]
CATEGORIES = SNAPSHOT["categories"]
CATALOG = {code: {"module_code":code, "module_credit":m["moduleCredit"],
    "prereq_tree":m.get("prereqTree"), "semesters":[{"semester_number":s["semester"],
    "exam_date_time":s.get("examDate"), "exam_duration":s.get("examDuration")}
    for s in m.get("semesterData",[])]} for code,m in DETAILS.items()}
# Read the existing declarations; importing courses would initialise PyCSP3.
DECLARATIONS = ast.parse((ROOT / "src/courses.py").read_text())
CONSTANTS = {
    n.targets[0].id: ast.literal_eval(n.value)
    for n in DECLARATIONS.body
    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
    and n.targets[0].id in {"CS_FOUNDATION_CODES", "CS_FOCUS_AREAS"}
}
FOUNDATION = sorted(CONSTANTS["CS_FOUNDATION_CODES"] & CATALOG.keys())
FOCUS_AREAS = CONSTANTS["CS_FOCUS_AREAS"]
PLACEHOLDER = re.compile(r"^[A-Z]+\d?$")
TITLES = {
    "CS1101S": "Programming Methodology", "CS1231S": "Discrete Structures",
    "CS2030S": "Programming Methodology II", "CS2040S": "Data Structures and Algorithms",
    "CS2100": "Computer Organisation", "CS2101": "Effective Communication for Computing Professionals",
    "CS2102": "Database Systems", "CS2103T": "Software Engineering", "CS2105": "Introduction to Computer Networks",
    "CS2106": "Introduction to Operating Systems", "CS2107": "Introduction to Information Security",
    "CS2109S": "Introduction to AI and Machine Learning", "CS3230": "Design and Analysis of Algorithms",
    "CS3243": "Introduction to Artificial Intelligence", "CS3244": "Machine Learning",
    "CS3263": "Foundations of Artificial Intelligence", "CS4248": "Natural Language Processing",
    "MA1521": "Calculus for Computing", "MA1522": "Linear Algebra for Computing",
    "ST2334": "Probability and Statistics", "IS1108": "Digital Ethics and Data Privacy",
    "ES2660": "Communicating in the Information Age",
    "GEC": "Cultures and Connections elective", "GEA": "Data Literacy elective",
    "GESS": "Singapore Studies elective", "GEN": "Communities and Engagement elective",
    "ID1": "Interdisciplinary elective I", "ID2": "Interdisciplinary elective II",
    "CD": "Cross-disciplinary elective",
}


def course_info(code):
    module = CATALOG[code]
    details = DETAILS[code]
    categories = details.get("plannerCategories", [])
    multi_semester = code.startswith("GEN") and code.endswith(("X", "Y"))
    graduate = bool(re.match(r"^[A-Z]+[5-9]", code))
    return {"code": code,
            "units": int(module["module_credit"]),
            "placeholder": bool(PLACEHOLDER.fullmatch(code)),
            "semesters": [s["semester_number"] for s in module.get("semesters", [])],
            "title": details.get("title", TITLES.get(code,code)), "categories":categories,
            "source_urls":list(dict.fromkeys(details.get("categorySources", []))),
            "nusmods_url":f"https://nusmods.com/courses/{code}",
            "planner_eligible":not multi_semester and not graduate,
            "eligibility_note":"Year-long service learning: requires two-semester modelling; browse only." if multi_semester else
                "Graduate-level course: not included in the undergraduate automatic pool." if graduate else ""}
