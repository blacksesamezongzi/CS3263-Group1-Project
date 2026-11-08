"""SoCLaaS is called only by the server. Model output is data, never code."""
import json
import os
import re
from uuid import uuid4
import httpx
from pydantic import ValidationError
from backend.catalog import CATALOG, FOCUS_AREAS, CATEGORIES, course_info
from backend.schemas import ConstraintCard, ParseRequest, ParseResult

BASE_URL = os.getenv("SOCLAAS_BASE_URL", "https://soclaas-api.comp.nus.edu.sg/v1").rstrip("/")


class ModelError(Exception):
    pass


async def available_models():
    key = os.getenv("SOCLAAS_API_KEY")
    if not key:
        raise ModelError("Set SOCLAAS_API_KEY on the backend to enable preference chat.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{BASE_URL}/models", headers={"Authorization": f"Bearer {key}"})
            response.raise_for_status()
            return [m["id"] for m in response.json()["data"]]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ModelError("Cannot list SoCLaaS models. Check the backend key and gateway connectivity.") from exc


async def parse_preference(request: ParseRequest):
    key, model = os.getenv("SOCLAAS_API_KEY"), os.getenv("SOCLAAS_MODEL")
    if not key or not model:
        raise ModelError("Configure SOCLAAS_API_KEY and SOCLAAS_MODEL on the backend. Choose a chat model using /api/models.")
    system = """You translate a student's NUS course-planning instruction into strict JSON.
Return ONLY an object with reply (plain language in the user's language), cards (array),
and needs_clarification (boolean). Each card groups rules for one coherent intent
with the SAME strength. Split clauses into separate cards when their strengths differ.
Use the supplied JSON schema. Never return executable code or unknown rule types.
Cards must have id='new', source='user', title, description, strength and rules.
A requested definite assignment ('take CS2102 in semester 3') is HARD; explicit
preferences ('prefer', 'ideally', '更倾向', '尽量') are SOFT. ONLY course_in_semester,
finish_by and workload_target may be soft. workload_target must ALWAYS be soft.
All other types, including exclude_courses and require_courses, MUST be hard.
For 'prefer CS2102 in semester 3 and must avoid CS3244', return TWO cards:
a soft course_in_semester card and a hard exclude_courses card. Never put a hard
rule into a soft card. Default finish-by is soft
unless the student says must. Semester 3 means year 2 semester 1, NOT semester 2.
Convert Y2S1 to 3; convert year+semester pairs with (year-1)*2+semester.
The catalogue is a limited project snapshot: do NOT invent courses or equivalents.
CS1010S and CS1101S are not interchangeable without explicit student approval.
Use require_courses for inclusion, exclude_courses for avoidance, blocked_semesters
for no courses in certain semesters, focus_area for a selected focus area.
There are no placeholder courses such as ID1, ID2, CD, GEC or GESS. For a category
requirement use category_units with GEC, GEA, GESS, GEN (4 units) or ID_CD (12 units).
ID/CD category membership is the official list in the context, not a code prefix.
Courses marked browse_only cannot be added as course assignments; explain the reason.
CS2101 and CS2103T are paired in the same semester and share the matching teaching
group's tutorial/communication times. The default corequisites rule enforces pairing.
Changing existing rules is unsupported: ask the user to delete the existing card
and add a replacement. Do not claim you deleted/changed any existing card.
Do not add graduation, prerequisite, availability or other defaults on your own.
Only the current message creates new rules; existing cards are context to detect conflicts.
If any requested part cannot be represented, is ambiguous, outside the horizon,
asks a general question, or contains an unknown course, return cards=[] and explain
what needs clarification. Never silently drop an unsupported part of an instruction.
For competing hard rules, explain the conflict and return no new cards.
Keep reply concise. needs_clarification=true means cards must be empty.
"""
    context = {"horizon": request.horizon, "catalogue": sorted(CATALOG),
               "categories":CATEGORIES,
               "browse_only":{c:course_info(c)['eligibility_note'] for c in CATALOG if not course_info(c)['planner_eligible']},
               "focus_areas": sorted(FOCUS_AREAS),
               "current_cards": [c.model_dump() for c in request.cards],
               "output_schema": ParseResult.model_json_schema()}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            response = await client.post(f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": [
                    {"role": "system", "content": system + "\n" + json.dumps(context, ensure_ascii=False)},
                    {"role": "user", "content": request.message}],
                    "temperature": 0, "max_tokens": 3500})
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        result = ParseResult.model_validate_json(content)
        if result.needs_clarification and result.cards:
            raise ValueError("Clarification response contains rules")
        cards = []
        for card in result.cards:
            data = card.model_dump()
            data.update(id="user_" + uuid4().hex[:12], source="user")
            for rule in card.rules:
                if getattr(rule, "semester", 1) > request.horizon or any(
                    s > request.horizon for s in getattr(rule, "semesters", [])
                ):
                    raise ValueError("Semester outside planning horizon")
            cards.append(ConstraintCard.model_validate(data))
        result.cards = cards
        return result
    except httpx.TimeoutException as exc:
        raise ModelError("SoCLaaS timed out. Your existing constraints have been kept; please try again.") from exc
    except httpx.HTTPStatusError as exc:
        raise ModelError(f"SoCLaaS returned HTTP {exc.response.status_code}. Check the key, model and gateway.") from exc
    except httpx.HTTPError as exc:
        raise ModelError("Unable to reach SoCLaaS. Your existing constraints have been kept.") from exc
    except (ValidationError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ModelError("The model returned an invalid constraint. Nothing was added. Try a more specific instruction.") from exc
