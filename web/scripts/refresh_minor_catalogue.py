"""Fetch real reference-year minor courses and supporting prerequisite options.

Keeps the existing general catalogue unchanged. No API credentials are used.
"""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.minors import MINORS, eligible_codes, prerequisite_codes


async def main():
    baseline = json.loads((ROOT / 'assets/data/course_details.json').read_text())
    year = baseline['academic_year']
    original = baseline['courses']
    courses = {}
    slots = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f'https://api.nusmods.com/v2/{year}/moduleList.json')
        response.raise_for_status()
        available = {m['moduleCode'] for m in response.json()}
        pending = set().union(*(eligible_codes(p, available) for p in MINORS)) - original.keys()
        seen = set(original)
        async def fetch(code):
            async with slots:
                response = await client.get(f'https://api.nusmods.com/v2/{year}/modules/{code}.json')
                response.raise_for_status()
                return code, response.json()
        while pending:
            batch = await asyncio.gather(*(fetch(c) for c in sorted(pending)))
            seen.update(pending)
            for code, data in batch:
                data['plannerCategories'] = []
                data['categorySources'] = []
                courses[code] = data
            dependencies = set().union(*(prerequisite_codes(d.get('prereqTree')) for _, d in batch))
            # Existing CS courses supply programming alternatives. Avoid pulling
            # every variant of every faculty's programming-entry requirement.
            pending = {c for c in dependencies if c in available and c not in seen
                       and c.startswith(('MA', 'QF', 'ST', 'DSA', 'EC', 'FIN', 'PC'))}
            if len(courses) + len(pending) > 180:
                raise RuntimeError('Prerequisite pool unexpectedly large; review before replacing snapshot')
    all_codes = set(original) | courses.keys()
    memberships = {c: [p for p in MINORS if c in eligible_codes(p, all_codes)] for c in sorted(all_codes)}
    memberships = {c: p for c, p in memberships.items() if p}
    payload = {'academic_year': year, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
               'sources': {p: d['source_urls'] for p, d in MINORS.items()},
               'memberships': memberships, 'courses': dict(sorted(courses.items()))}
    (ROOT / 'assets/data/minor_course_details.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    print('Added', len(courses), 'real courses; minor pools:', {p: sum(p in values for values in memberships.values()) for p in MINORS})


if __name__ == '__main__':
    asyncio.run(main())
