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
        index = index,
        module_code=(module["module_code"].removesuffix(":D").removesuffix(":A-")),
        module_credit=int(module["module_credit"]),
        semesters=module.get("semesters", []),
        prereq_tree=module.get("prereq_tree", None)
    )
    for index, module in enumerate(modules)
]

CS_FOUNDATION_CODES = {
        "CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100",
        "CS2101", "CS2103T", "CS2106", "CS2109S", "CS3230",
        "MA1521", "MA1522", "IS1108", "ST2334", "ES2660", "GEC", "GEA", "GESS", "GEN", "ID1", "ID2", "CD"
}

CS_FOUNDATION = tuple(
    course
    for code in CS_FOUNDATION_CODES
    if (course := helper_functions.course_lookup(code, COURSES)) is not None
)

General_Education_Codes = {
    "GEC", "GEA", "GESS", "GEN", "ID1", "ID2", "CD", 
}


CS_FOCUS_AREAS = {
    "Algorithms & Theory": {
        "primaries": {
            "CS3230", "CS3231", "CS3236", "CS4231",
            "CS4232", "CS4234", "CS4330", "CS4430",
        },
        "electives": {
            "CS3233", "CS4257", "CS4261", "CS4268",
            "CS4269", "CS4330", "CS5230", "CS5234",
            "CS5236", "CS5237", "CS5238", "CS5330",
        },
    },

    "Artificial Intelligence": {
        "primaries": {
            "CS2109S", "CS3243", "CS3244", "CS3263",
            "CS3264", "CS3268", "CS4243", "CS4244",
            "CS4246", "CS4248", "CS4262",
        },
        "electives": {
            "CS4220", "CS4261", "CS4269", "CS4277",
            "CS4278", "CS4354", "CS5215", "CS5228",
            "CS5242", "CS5260", "CS5340", "CS5339",
        },
    },

    "Computer Graphics and Games": {
        "primaries": {
            "CS3241", "CS3242", "CS3247",
            "CS4247", "CS4350",
        },
        "electives": {
            "CS3218", "CS3240", "CS3249", "CS4240",
            "CS4243", "CS4249", "CS4351", "CS5237",
            "CS5240", "CS5343", "CS5346",
        },
    },

    "Computer Security": {
        "primaries": {
            "CS2107", "CS3235", "CS4236",
            "CS4230", "CS4238", "CS4239",
        },
        "electives": {
            "CS3221", "CS4257", "CS4276", "CS5231",
            "CS5250", "CS5321", "CS5322", "CS5331",
            "CS5332", "IFS4101", "IFS4102", "IFS4103",
        },
    },

    "Database Systems": {
        "primaries": {
            "CS2102", "CS3223", "CS4221",
            "CS4224", "CS4225",
        },
        "electives": {
            "CS4220", "CS5226", "CS5228", "CS5322",
        },
    },

    "Human-Computer Interaction": {
        "primaries": {
            "CS2111", "CS3240", "CS3249",
            "CS4249", "CS4353",
        },
        "electives": {
            "CS4240", "CS5346",
        },
    },

    "Multimedia Information Retrieval": {
        "primaries": {
            "CS2108", "CS3245", "CS4242",
            "CS4248", "CS4347",
        },
        "electives": {
            "CS5246", "CS5241",
        },
    },

    "Networking and Distributed Systems": {
        "primaries": {
            "CS2105", "CS3103", "CS4222",
            "CS4226", "CS4231",
        },
        "electives": {
            "CS3237", "CS4344", "CS5223",
            "CS5224", "CS5229", "CS5248", "CS5321",
        },
    },

    "Parallel Computing": {
        "primaries": {
            "CS3210", "CS3211", "CS4231",
            "CS4223", "CS4310",
        },
        "electives": {
            "CS5222", "CS5223", "CS5224",
            "CS5239", "CS5250",
        },
    },

    "Programming Languages": {
        "primaries": {
            "CS2104", "CS3211", "CS4212", "CS4215",
        },
        "electives": {
            "CS3234", "CS4216", "CS5232",
            "CS5214", "CS5215", "CS5218",
        },
    },

    "Software Engineering": {
        "primaries": {
            "CS2103T", "CS3213", "CS3217", "CS3219",
            "CS3227", "CS3282", "CS4211", "CS4218",
            "CS4239",
        },
        "electives": {
            "CS3203", "CS3281", "CS3216", "CS3226",
            "CS3234", "CS4354", "CS5219", "CS5232",
            "CS5272",
        },
    },
}

# CS breadth-and-depth electives outside the focus areas
CS_OTHER_ELECTIVES = {
    "CS2220", "CS5233",
}

