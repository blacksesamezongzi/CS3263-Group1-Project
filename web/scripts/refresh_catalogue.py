"""Refresh official category membership and reference-year NUSMods course/lesson data.

Run from the repository root: .venv/bin/python scripts/refresh_catalogue.py
No credentials required. Existing team snapshot is retained as the legacy input.
"""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import httpx
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
YEAR = '2026-2027'
COMMON = 'https://www.comp.nus.edu.sg/cug/soc-22-23/'
GE = 'https://www.nus.edu.sg/registrar/academic-information-policies/undergraduate-students/general-education/list-of-courses-approved-under-the-ge-pillars'
CODE = re.compile(r'\b[A-Z]{2,4}\d{4}[A-Z]{0,2}\b')

async def main():
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(COMMON); response.raise_for_status()
        tree = html.fromstring(response.text)
        categories = {'ID':set(), 'CD':set(), 'GEA':{'GEA1000','BT1101','ST1131','DSA1101'},
            'GEC':{f'GEC{n}' for n in range(1000,1056) if n not in {1022,1047}},
            'GESS':{f'GESS{n}' for n in range(1000,1039)},
            'GEN':{f'GEN{n}' for n in range(2000,2010)} | {f'GEN{n}{s}' for n in (2002,2050,2060,2061,2062,2070,2072) for s in 'XY'} | {'CLC1101','CLC2204','CLC3301A','CLC3303','CLC3304A','CLC3307','CLC3308','CP3107','CP3110'}}
        # GE membership transcribed from the Registrar's approved list (see GE URL).
        # Exclude residential-college/other-faculty-only variants from the CS pool.
        category = None
        for element in tree.iter():
            text = (element.text or '').strip()
            if 'Appendix B:' in text: category = 'ID'
            elif 'Appendix C:' in text: category = 'CD'
            if element.tag == 'strong' and category:
                text = element.text_content().strip()
                if re.match(r'^[A-Z]{2,4}\d{4}',text):
                    categories[category].update(CODE.findall(text))
                    if text.startswith('ACC1701/'):
                        categories[category].update(['ACC1701X','ACC1701XA','ACC1701XB','ACC1701XC','ACC1701XD'])
        listing = await client.get(f'https://api.nusmods.com/v2/{YEAR}/moduleList.json'); listing.raise_for_status()
        available = {m['moduleCode'] for m in listing.json()}
        # Include explicitly approved non-prefix GE courses where open to SoC.
        categories['GEC'].add('HSA1000'); categories['GESS'].update(['HSS1000','CDE2501'])
        original = json.loads((ROOT/'assets/data/nusmods_modules.json').read_text())['modules']
        wanted = ({m['module_code'] for m in original} | {'MA1301','MA1301X'} | set().union(*categories.values())) & available
        path = ROOT/'assets/data/course_details.json'
        old = json.loads(path.read_text())['courses'] if path.exists() else {}
        slots = asyncio.Semaphore(6)
        courses, failures = {}, []
        async def fetch(code):
            async with slots:
                for attempt in range(3):
                    try:
                        r = await client.get(f'https://api.nusmods.com/v2/{YEAR}/modules/{code}.json');r.raise_for_status()
                        data=r.json()
                        data['plannerCategories']=[c for c,v in categories.items() if code in v]
                        data['categorySources']=[COMMON if c in {'ID','CD'} else GE for c in data['plannerCategories']]
                        courses[code]=data
                        return
                    except (httpx.HTTPError,ValueError):
                        if attempt == 2:
                            if code in old: courses[code]=old[code]
                            else: failures.append(code)
        await asyncio.gather(*(fetch(c) for c in sorted(wanted)))
        if failures: raise RuntimeError('Missing courses; previous snapshot left intact: '+', '.join(failures))
        payload={'academic_year':YEAR,'retrieved_at':datetime.now(timezone.utc).isoformat(),
                 'sources':{'common_curriculum':COMMON,'general_education':GE,'nusmods':f'https://api.nusmods.com/v2/{YEAR}/'},
                 'categories':{c:sorted(v & courses.keys()) for c,v in categories.items()},'courses':dict(sorted(courses.items()))}
        path.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')
        print('Saved',len(courses),'real courses:',{c:len(v) for c,v in payload['categories'].items()})
        print('Not currently offered:',sorted(set().union(*categories.values())-available))

if __name__=='__main__': asyncio.run(main())
