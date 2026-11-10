"""Editable scientific diagrams using the Lucide icon set and SVG primitives."""
from pathlib import Path
import html
import re
import shutil

HERE=Path(__file__).resolve().parent
OUT=HERE/'figures';OUT.mkdir(exist_ok=True)
ICONS=Path('/tmp/cs3263-report-browser/node_modules/lucide-static')
NAVY='#103d67';GOLD='#d69a13';INK='#18324d';MUTED='#46617d'
def icon(name,x,y,size=54,color=NAVY):
 raw=(ICONS/'icons'/f'{name}.svg').read_text()
 inner=raw[raw.index('>',raw.index('<svg'))+1:raw.rindex('</svg>')]
 return f'<g transform="translate({x},{y}) scale({size/24})" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{inner}</g>'
def text(x,y,lines,size=30,color=INK,bold=False):
 return f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">'+''.join(f'<tspan x="{x}" dy="{0 if i==0 else 39}">{html.escape(t)}</tspan>' for i,t in enumerate(lines))+'</text>'
def start(h):
 return f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{h}" viewBox="0 0 1200 {h}"><rect width="1200" height="{h}" fill="white"/><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="none" stroke="{NAVY}" stroke-width="1.4"/></marker><marker id="gold" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="none" stroke="{GOLD}" stroke-width="1.4"/></marker></defs>'
def arrow(path,color=NAVY,dashed=False):
 return f'<path d="{path}" fill="none" stroke="{color}" stroke-width="4" '+('stroke-dasharray="8 6" ' if dashed else '')+f'marker-end="url(#{"gold" if color==GOLD else "arrow"})"/>'
def box(x,y,title,lines,symbol,fill='#eef4fb'):
 return f'<rect x="{x}" y="{y}" width="340" height="185" rx="18" fill="{fill}" stroke="#d5e1ef" stroke-width="2"/>'+icon(symbol,x+22,y+20,48)+text(x+88,y+52,[title],32,NAVY,True)+text(x+22,y+111,lines,30,MUTED)

s=start(735)
s+=text(20,40,['Natural language is translated; the solver constructs the plan.'],31,NAVY,True)
s+=box(20,85,'Student',['Course preferences','Inspect / edit cards'],'user-round')
s+=box(430,85,'LLM parser',['SoCLaaS model','Typed JSON proposal'],'bot','#fff6df')
s+=box(840,85,'Rule validator',['Pydantic schema','Known codes / types'],'list-checks')
s+=box(840,380,'CSP optimiser',['PyCSP3 + ACE','Hard rules + costs'],'cpu','#fff6df')
s+=box(430,380,'Weekly search',['Whole lesson groups','Check every week'],'calendar-clock')
s+=box(20,380,'Verified plan',['Audit + semester view','Planner JSON export'],'shield-check','#eef8f2')
s+=arrow('M360 175 H420')+arrow('M770 175 H830')+arrow('M1010 270 V370')+arrow('M840 470 H780')+arrow('M430 470 H370')
s+=arrow('M600 380 V325 H1090 V370',GOLD,True)+text(565,307,['Proven conflict: add a cut'],30,GOLD)
s+='<rect x="20" y="610" width="1160" height="100" rx="15" fill="#f6f8fb" stroke="#d5e1ef" stroke-width="2"/>'
s+=icon('database',44,630,48)+text(118,647,['Frozen reference data: NUSMods courses, lesson packages, exams', 'and official requirement / minor membership lists'],30,MUTED)
s+='</svg>'
(OUT/'architecture.svg').write_text(s)

s=start(500)
s+=text(20,40,['Task: turn a student request into a feasible semester assignment.'],31,NAVY,True)
for x,fill in [(20,'#eef4fb'),(430,'#fff6df'),(840,'#eef8f2')]:
 s+=f'<rect x="{x}" y="85" width="340" height="360" rx="18" fill="{fill}" stroke="#d5e1ef" stroke-width="2"/>'
s+=icon('user-round',42,105,48)+text(110,140,['Student'],32,NAVY,True)
s+=text(42,205,['CS major + QF minor', 'Prefer 8 semesters', 'Take CS2102 in S3'],30)
s+=text(42,400,['Natural-language input'],30,MUTED)
s+=icon('list-checks',452,105,48)+text(520,140,['Explicit rules'],32,NAVY,True)
s+=text(452,205,['160 units + core', 'Prerequisites first', 'Paired courses', 'Minor course groups'],30)
s+=text(452,400,['Hard rules / soft goals'],30,MUTED)
s+=icon('calendar-check',862,105,48)+text(930,140,['Study plan'],32,NAVY,True)
s+=text(862,205,['S1: CS1101S, ...', 'S2: CS2040S, ...', 'S3: CS2102, ...'],30)
s+=text(862,361,['Weekly selection', 'for every semester'],30,MUTED)
s+=arrow('M360 260 H420')+arrow('M770 260 H830')
s+=text(20,485,['Illustrative task and partial output only; the actual verified plan is shown separately.'],30,MUTED)
s+='</svg>'
(OUT/'task.svg').write_text(s)
shutil.copy2(ICONS/'LICENSE',OUT/'LUCIDE_LICENSE.txt')
print('Wrote editable task and architecture figures.')
