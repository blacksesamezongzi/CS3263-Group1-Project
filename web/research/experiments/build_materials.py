"""Regenerate tables, blind rating packet, and timed presentation script.

No model calls are made here. Keep the private method key away from raters.
"""
from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path
import random
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from research.experiments.benchmark import RUN, ROOT, LEVELS, PROFILES, dump, request_for, evaluate_all
from backend.catalog import CATALOG, DETAILS, course_info
from backend.validation import prerequisite_description
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

OUT=ROOT/'output/pdf'; HUMAN=ROOT/'research/human-evaluation'; PRES=ROOT/'research/presentation'
BLUE='#103D67'; GOLD='#D9A51B'; MUTED='#4B5E70'
for p in [OUT,HUMAN,PRES]:p.mkdir(parents=True,exist_ok=True)
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
pdfmetrics.registerFont(TTFont('DV',font));pdfmetrics.registerFont(TTFont('DV-Bold',font.replace('.ttf','-Bold.ttf')))
styles=getSampleStyleSheet()
for name in ['Normal','BodyText']:styles[name].fontName='DV';styles[name].fontSize=10;styles[name].leading=14
styles.add(ParagraphStyle(name='TitleBlue',fontName='DV-Bold',fontSize=24,leading=29,textColor=colors.HexColor(BLUE),spaceAfter=15))
styles.add(ParagraphStyle(name='HeadingBlue',fontName='DV-Bold',fontSize=15,leading=20,textColor=colors.HexColor(BLUE),spaceBefore=10,spaceAfter=8))
styles.add(ParagraphStyle(name='Tiny',fontName='DV',fontSize=8,leading=11,textColor=colors.HexColor(MUTED)))
styles.add(ParagraphStyle(name='TableText',fontName='DV',fontSize=9,leading=12))

def P(text,style='BodyText'):return Paragraph(text,styles[style])
def footer(canvas,doc):
 canvas.setFont('DV',8);canvas.setFillColor(colors.HexColor(MUTED));canvas.drawString(42,25,'CS3263 Group 1  |  9 November 2026');canvas.drawRightString(A4[0]-42,25,str(doc.page))
def pdf(path,flow):
 SimpleDocTemplate(str(path),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=42).build(flow,onFirstPage=footer,onLaterPages=footer)
def table(rows,widths):
 t=Table(rows,colWidths=widths,hAlign='LEFT',repeatRows=1)
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF1F8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.8,colors.HexColor(BLUE)),('LINEBELOW',(0,1),(-1,-1),0.3,colors.HexColor('#D5DFE8')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
 return t
def tex(text):return str(text).replace('\\','\\textbackslash{}').replace('_','\\_').replace('%','\\%').replace('&','\\&').replace('#','\\#')

def summarise():
 evaluate_all();results=json.loads((RUN/'results.json').read_text());manifest=json.loads((RUN/'manifest.json').read_text())
 main=[r for r in results if r['profile']=='base'];models=manifest['models_soclaas']+manifest['models_codex']
 summary={'requested_main':len(main),'evaluable_main':sum(r['evaluable'] for r in main),'fully_verified_main':sum(r.get('hard_pass',False) for r in main),'levels':{},'models':[]}
 for level in LEVELS:
  rs=[r for r in main if r['level']==level];ev=[r for r in rs if r['evaluable']]
  summary['levels'][level]={'requested':len(rs),'evaluable':len(ev),'fully_verified':sum(r.get('hard_pass',False) for r in rs),'mean_hard_card_failures':statistics.mean(len(r['hard_card_failures']) for r in ev) if ev else None}
 rows=[]
 for model in models:
  rs=[r for r in main if r['model']==model];ev=[r for r in rs if r['evaluable']];cells=[]
  for l in LEVELS:
   r=next((r for r in rs if r['level']==l),None)
   if r is None:cell='pending'
   elif r['evaluable']:cell=str(len(r['hard_card_failures']))+('?' if r.get('unverified_hard_cards') else '')
   elif r['status']!='received':cell='E'+str(r.get('http_status') or '')
   else:cell='P'
   cells.append(cell)
  row={'model':model,'cells':cells,'evaluable':len(ev),'verified':sum(r.get('hard_pass',False) for r in rs)};summary['models'].append(row)
  rows.append(tex(model)+(' $^\\dagger$' if model.startswith('gpt-') else '')+' & '+' & '.join(cells)+f" & {len(ev)}/3 & {row['verified']}/3 \\\\")
 incidence=Counter(c for r in main if r['evaluable'] for c in r['hard_card_failures'])
 summary['hard_card_incidence']=dict(incidence.most_common())
 summary['service_errors']=sum(r['status']!='received' for r in main)
 summary['parse_errors']=sum(r['status']=='received' and not r['evaluable'] for r in main)
 summary['unverified_weekly']=sum('weekly' in r.get('unverified_hard_cards',[]) for r in main)
 summary['received_length_limited']=sum(json.loads(p.read_text()).get('response',{}).get('choices',[{}])[0].get('finish_reason')=='length' for p in (RUN/'raw').glob('*.json') if json.loads(p.read_text())['profile']=='base')
 dump(RUN/'summary.json',summary)
 with (RUN/'model_summary.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['model','A_hard_card_failures','AP_hard_card_failures','APR_hard_card_failures','evaluable_of_3','fully_verified_of_3'])
  for row in summary['models']:w.writerow([row['model'],*row['cells'],row['evaluable'],row['verified']])
 with (RUN/'violation_incidence.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['model','evaluable_main_runs']+[c.id for c in request_for('base').cards if c.strength=='hard'])
  for model in models:
   rs=[r for r in main if r['model']==model and r['evaluable']];counts=Counter(c for r in rs for c in r['hard_card_failures'])
   w.writerow([model,len(rs)]+[counts[c.id] for c in request_for('base').cards if c.strength=='hard'])
 with (RUN/'atomic_diagnostics.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['model','profile','level','missing_foundation_courses','prerequisite_violations','exam_conflict_pairs','proven_infeasible_semesters','unverified_semesters','unknown_courses','duplicate_courses'])
  for r in results:
   if not r['evaluable']:continue
   d=r['details'];a=d['academic_audit'];w.writerow([r['model'],r['profile'],r['level'],len(a['missing_foundation_courses']),len(a['prerequisite_violations']),len(d['exam_pairs']),sum(x=='infeasible' for x in d['weekly_semesters'].values()),sum(x in {'missing_data','timeout','conditional'} for x in d['weekly_semesters'].values()),len(d['unknown_courses']),len(d['duplicate_courses'])])
 lines=['\\begin{table}[h]\\centering','\\begin{tabular}{@{}lrrrrr@{}}\\toprule','Model & A & AP & APR & Evaluable & Verified\\\\\\midrule',*rows,'\\bottomrule\\end{tabular}',
        '\\caption{Base-task hard-card failures. A question mark means at least one hard check remains unverified. P: received but not parseable. E: service/transport failure (HTTP code where available). $\\dagger$: Codex CLI harness. Verified uses all three requests as denominator.}\\end{table}',
        f"Of {len(main)} main requests across {len(models)} model IDs, {summary['evaluable_main']} produced evaluable schedules and {summary['fully_verified_main']} passed all implemented hard checks. There were {summary['service_errors']} service/transport failures and {summary['parse_errors']} received but unparseable responses; all 19 of the latter reached the output limit. {summary['unverified_weekly']} evaluable schedules had unverified weekly checks. This evaluates the specified budget, not unconstrained model capability."]
 desc=[]
 titles={c.id:c.title for c in request_for('base').cards}
 for k,v in incidence.most_common(5):desc.append(f"{tex(titles[k])} ({v}/{summary['evaluable_main']})")
 lines.append('The most frequently failed hard cards among evaluable base schedules were '+', '.join(desc)+'. Denominators exclude unavailable or unparseable runs; the small sample does not estimate a model-population error rate.')
 lines.append('\\begin{table}[h]\\centering\\begin{tabular}{lrrrr}\\toprule Symbolic control & Units & Last semester & Seconds & Unmet soft cards\\\\\\midrule')
 for p in PROFILES:
  r=json.loads((RUN/'csp'/f'{p}.json').read_text());lines.append(f"{tex(p)} & {r.get('total_units','--')} & {r.get('last_semester','--')} & {r.get('elapsed_seconds','--')} & {len(r.get('unmet_preferences',[]))} \\\\")
 lines+=['\\bottomrule\\end{tabular}\\caption{Three typed-card CSP controls. All returned plans passed their active hard checks, weekly verification and academic/minor audits. These are not 45 independent model-parser trials.}\\end{table}',
 'The base control met both default preferences. The QF control completed in eight semesters with a workload-target deviation. The Mathematics control used nine semesters and missed both the duration and workload targets. This demonstrates that hard feasibility does not imply preference satisfaction. Sol produced a fully verified base APR plan; Astra had zero proved base APR hard-card failures but an unverified weekly check. Thus the data do not establish an exclusive correctness advantage for CSP.',
 'Separate production-parser probes correctly represented the two minor requests and the soft CS2102 pin, and their subsequent solver runs returned feasible plans. This is a two-example smoke test, not a parser accuracy benchmark. Exact messages, raw responses and actual generated cards are archived.']
 (ROOT/'research/report/results.tex').write_text('\n\n'.join(lines)+'\n')
 return results,summary

RUBRIC={
 'Preference satisfaction':[
 'Misses almost all stated preferences, or directly contradicts the main requested goal.',
 'Meets only a minority of preferences and leaves a major requested goal unmet.',
 'Meets several preferences but misses at least one important goal or requires a noticeable compromise.',
 'Meets almost all preferences, with only a small, clearly identifiable compromise.',
 'Meets all stated preferences, including the duration/workload targets and the course pin when requested.'],
 'Apparent feasibility and actionability':[
 'Contains obvious major problems, such as missing core courses, impossible prerequisite order or unresolved placeholders; cannot be used without major reconstruction.',
 'Several substantial academic or scheduling concerns require large changes before the plan could be followed.',
 'Broadly usable but at least one substantial concern needs verification or correction. Identify it rather than assuming it is resolved.',
 'No obvious major conflict in the supplied references; only minor practical checks or changes remain.',
 'All checks the rater can assess from the supplied references are consistent, and the plan can be acted on with routine registration checks. This rating is not official eligibility certification.'],
 'Workload and progression':[
 'Severely uneven workload or repeated progression problems make the plan difficult to follow.',
 'Several heavy/light semesters or poorly sequenced advanced subjects create substantial difficulty.',
 'Generally manageable progression, with one or two semesters that need rebalancing or closer review.',
 'Mostly balanced active semesters and sensible progression, with only a small concern.',
 'Consistently manageable loads with clear foundations before advanced study, judged against the stated student profile.'],
 'Clarity and verifiability':[
 'Course assignments or semester positions are missing/ambiguous enough that the schedule cannot be checked.',
 'Several assignments are unclear or hard to trace to a real course; extensive clarification is needed.',
 'The schedule is understandable but some choices or requirement coverage need additional work to verify.',
 'Assignments are clear and can mostly be checked from the common course references.',
 'Every semester and course is unambiguous, and the rater can readily trace requirement coverage using the common references.'],
 'Overall usefulness':[
 'Would not use this as a starting plan.',
 'Would use only after extensive replanning.',
 'A useful starting point with substantial revisions.',
 'Would use after a few targeted revisions and adviser checks.',
 'A strong starting plan requiring only routine confirmation.'],
}

def build_human(results):
 methods=['CSP','qwen3.6:35b','llama3.1:8b','gpt-6-astra','gpt-6.1-sol'];selected=[];replacements=[]
 # Replacement follows the frozen canonical order and must supply all three tasks.
 candidates=json.loads((RUN/'manifest.json').read_text())['models_soclaas']
 def valid(m,p):return next((r for r in results if r['model']==m and r['profile']==p and r['level']=='APR' and r['evaluable']),None)
 for i,m in enumerate(methods):
  if m=='CSP':continue
  if not all(valid(m,p) for p in PROFILES):
   replacement=next((c for c in candidates if c not in methods and all(valid(c,p) for p in PROFILES)),None)
   if replacement:replacements.append({'original':m,'replacement':replacement,'reason':'Original lacks evaluable APR output(s) across the three profiles.'});methods[i]=replacement
 for p in PROFILES:
  for m in methods:
   if m=='CSP':
    r=json.loads((RUN/'csp'/f'{p}.json').read_text());assign={c['code']:s['number'] for s in r.get('semesters',[]) for c in s['courses']}
   else:
    r=valid(m,p)
    if r is None:continue
    assign=r['assignments']
   selected.append({'method':m,'profile':p,'assignments':assign})
 rng=random.Random(32632026);rng.shuffle(selected)
 for i,r in enumerate(selected,1):r['anonymous_id']=f'Plan-{i:02d}'
 dump(HUMAN/'PRIVATE_method_key_DO_NOT_SHARE.json',{'seed':32632026,'methods':methods,'replacements':replacements,'plans':selected})
 dump(HUMAN/'availability.json',{'target':15,'available':len(selected),'ratings_collected':0,'replacement_count':len(replacements)})
 orders={}
 for i in (1,2):
  order=[r['anonymous_id'] for r in selected];random.Random(32632026+i).shuffle(order);orders[f'R{i}']=order
 with (HUMAN/'blank_ratings.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['rater_id','order','plan_id','preference_1_5','feasibility_1_5','workload_1_5','clarity_1_5','overall_1_5','uncertainty_low_medium_high','specific_concern','recognised_plan_yes_no'])
  for rater,order in orders.items():
   for i,name in enumerate(order,1):w.writerow([rater,i,name]+['']*8)
 with (HUMAN/'course_reference.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['code','title','units','offered_reference_semesters','prerequisite','nusmods_reference'])
  for c in sorted(CATALOG):
   info=course_info(c);w.writerow([c,info['title'],info['units'],','.join(map(str,info['semesters'])),prerequisite_description(CATALOG[c]['prereq_tree']),info['nusmods_url']])
 flow=[P('Course-plan evaluation','TitleBlue'),P('Independent internal rating packet','HeadingBlue'),P(f'{len(selected)} anonymised schedules. Do not open the private method key or benchmark results until both raters have submitted all scores.'),
 P('How to rate','HeadingBlue'),P('Use blank_ratings.csv. Identify yourself as R1 or R2 and follow your own order column. Work independently. Do not discuss scores, infer the method, or consult the automatic checker results. The task is to judge the schedule against the stated profile, not to guess which method produced it.'),
 P('Assign integer scores from 1 to 5 in each dimension using the following anchors. Record a concrete course/semester concern and your uncertainty. If you cannot assess a dimension, leave its score blank and explain why; never replace missing evidence with a neutral score. Do not treat all readable schedules as equally correct.'),
 P('Shared task and assumptions','HeadingBlue'),P('A new NUS CS student starts AY2026/27 with H2 Mathematics and English entry eligibility and no completed university courses. Offerings, exams and weekly teaching patterns repeat from AY2026/27. CS2101 and CS2103T share the matched teaching package and must be taken together. Maximum search horizon is 10 semesters.'),
 P('All tasks require at least 160 units, all 15 foundation courses, strict prerequisite order, offered semesters, exam compatibility and a feasible weekly lesson selection. Use 16-24 units per active semester, at most 20 initially. Complete three AI-focus primary courses including a level-4000+ course; GEC/GEA/GESS/GEN each need four units; ID/CD needs 12 distinct units with at least two ID and at most one CD-only course. Do not reuse a course between these common-curriculum groups.'),
 P('Preferences: finish within eight semesters and aim for 20 units in each active semester. The Mathematics and QF tasks additionally require their named minor and prefer CS2102 in semester 3. Minor groups and sharing limits appear in the task supplement. Preferences may legitimately remain unmet; evaluate that separately from feasibility.'),
 P('Reference files','HeadingBlue'),P('Use course_reference.csv for course titles, units, prerequisite trees and NUSMods links. Use the supplied task_supplement.json for the exact foundation list, AI membership, common-curriculum pools and minor groups. The frozen context.json contains the same complete weekly/exam data supplied to the generation methods. If a practical check remains uncertain, record that explicitly.'),PageBreak()]
 for k,(dimension,anchors) in enumerate(RUBRIC.items()):
  if k in (2,4):flow.append(PageBreak())
  flow.append(P(dimension,'HeadingBlue'))
  rows=[[P('Score','TableText'),P('Anchor','TableText')]]+[[P(str(i),'TableText'),P(a,'TableText')] for i,a in enumerate(anchors,1)]
  flow.extend([table(rows,[45,466]),Spacer(1,10)])
 flow+=[PageBreak(),P('Task supplement','TitleBlue')]
 foundation=', '.join(sorted(request_for('base').cards[1].rules[0].courses))
 flow.append(P('Foundation courses: '+foundation))
 for programme in json.loads((RUN/'context.json').read_text())['minors']:
  flow.append(P(programme['name']+' minor','HeadingBlue'));flow.append(P(programme['summary']))
  for g in programme['groups']:
   desc=g['name']+': '+('exactly ' if g.get('exact_units') else 'at least ')+str(g['units'])+' units'
   if g.get('count'):desc+=' in '+str(g['count'])+' course(s)'
   if g.get('max_count'):desc+=' in at most '+str(g['max_count'])+' courses'
   flow.append(P(html.escape(desc+'. Courses: '+', '.join(g['courses'])), 'Tiny'))
  flow.append(P('At least 12 distinct units outside CS foundation/common-curriculum and other selected minor pools. No more than eight shared units, no more than two programme uses per course. Total degree units count each course once. Programme/grade restrictions and registration must still be checked.','Tiny'))
 for item in selected:
  flow += [PageBreak(),P(item['anonymous_id'],'TitleBlue')]
  task='Base degree plan' if item['profile']=='base' else ('Degree plan with '+('Mathematics' if item['profile']=='math' else 'Quantitative Finance')+' minor')
  flow.append(P(task,'HeadingBlue'));flow.append(P('Preferences: finish within eight semesters; aim for 20 units per active semester.'+(' Prefer CS2102 in semester 3.' if item['profile']!='base' else '')))
  rows=[[P('Semester','TableText'),P('Courses','TableText'),P('Units','TableText')]]
  assign=item['assignments'];last=max(assign.values(),default=0)
  for s in range(1,last+1):
   codes=sorted(c for c,v in assign.items() if v==s)
   rows.append([P(f'Y{(s-1)//2+1} S{(s-1)%2+1}','TableText'),P(html.escape(', '.join(codes)) or '(empty)','TableText'),P(str(sum(int(CATALOG[c]['module_credit']) for c in codes if c in CATALOG)),'TableText')])
  flow.append(table(rows,[65,393,53]));flow.append(Spacer(1,15));flow.append(P('Judge this plan independently using the rubric. Record any uncertain check and any specific course/semester issue in your scoring sheet.','Tiny'))
 pdf(OUT/'human_evaluation_packet.pdf',flow)
 context=json.loads((RUN/'context.json').read_text());dump(HUMAN/'task_supplement.json',{k:v for k,v in context.items() if k not in {'courses','packages'}})
 return selected,replacements

def build_presentation(summary):
 n=summary['evaluable_main'];v=summary['fully_verified_main']
 slides=[
 ('0:00-0:35','A course plan needs more than plausible course names','Sun Jiaen',
  'Title, team names, one actual semester plan. Keep the title readable and omit a long agenda.',
  'We built Pathway, a course planner for NUS Computer Science students. Students describe what they want, inspect the resulting constraint cards, and generate a semester plan with weekly timetable checks. Our central question is whether direct language-model planning can satisfy the same explicit rules as a symbolic planner. We compare actual generated outputs rather than judging how convincing the explanations sound.'),
 ('0:35-1:25','The task combines academic rules and personal goals','Sun Jiaen',
  'Show one prerequisite relation, paired CS2101/CS2103T, and an eight-semester preference. Label requirements, preferences and assumptions distinctly.',
  'A valid plan must put prerequisites strictly before the courses that need them. For example, completing CS1231S in the same semester as a dependent course does not satisfy an earlier prerequisite. CS2101 and CS2103T must be taken together under our project mapping. Students may also prefer eight semesters or request a Mathematics or Quantitative Finance minor. We distinguish these hard commitments from preferences that can remain unmet. We assume all future years repeat the AY2026/27 offerings, exam dates and lesson patterns. That makes the task concrete, but it is also a major limitation.'),
 ('1:25-2:30','Language becomes inspectable rules before search','Shen Jingtao',
  'Use the report pipeline figure. Highlight the model/card boundary and the independent audit.',
  'The frontend sends a student instruction to our FastAPI backend. The SoCLaaS model returns a restricted JSON proposal. Pydantic checks the allowed rule types, known course codes, hard or soft strength, and semester bounds. The student sees the proposed cards before generating a plan. One card may represent several rules, so the interface does not need a one-to-one relationship with solver constraints. Deleting a card removes its active rules, and reset restores the defaults. The model does not execute code or search the degree plan. The next stage compiles the active rules into PyCSP3 and solves them with ACE. A separate Python checker reviews the result before export. Schema validation alone cannot prove that a card correctly reflects the student\'s intent, so visibility and correction remain important.'),
 ('2:30-3:45','Integer assignments express the degree plan','Achar Pavithra',
  'Show x_c in {0,...,H}, one prerequisite equation and a simple hard/soft objective. Avoid displaying the full compiler.',
  'Each course has one integer variable. Zero means the course is omitted, and a positive value is its semester. Semester units are the sum of credits assigned to that semester. Hard requirements constrain these variables, including foundation coverage, total units, availability, prerequisite order, and category allocations. Minor allocation variables track which courses fulfil which groups, while preventing invalid sharing. We support sixteen rule types and have fourteen hard cards plus two soft cards by default. Soft requests add penalties for missing a requested semester, placing courses after a target completion semester, and deviating from the workload target. These penalties form a weighted sum. We do not claim they are a proved lexicographic ordering, and a feasible result found within the search limit may not be globally optimal. The actual implementation uses bundled PyCSP3 2.6.1 and ACE, rather than the OR-Tools package suggested in our proposal.'),
 ('3:45-4:55','Weekly conflicts feed back into degree search','Shen Jingtao',
  'Show two alternative tutorial packages and a conflict cut. Include the CS2101 shared-package assumption as a small caption.',
  'A course-level plan can look valid while its weekly timetable is impossible. We therefore solve a second problem for each active semester: choose one complete class package for every lesson type. A class can contain several meetings, and we keep them together. Meetings conflict only if their days, time intervals and teaching weeks overlap. When the search proves that a set of courses cannot coexist, we shrink that set and add a cut to the degree solver for all matching semester parities. The solver then searches again. A timeout is unknown rather than a proof of infeasibility. Missing timetable data is also not treated as verified. We cap refinement attempts and use an outer process timeout. Finally, an academic audit checks foundation coverage and prerequisite order even if a user deleted those cards, so invalid exploratory previews cannot be exported.'),
 ('4:55-5:50','The interface connects requirements to a usable plan','Sun Jiaen',
  'Record a 45-50 second prepared screen capture: defaults, add QF minor/pin, cards appear, saved result, weekly view, native JSON export. Cut waiting time with a labelled transition.',
  'Here are the default requirements and preferences, with official source links where applicable. A student can request a minor or ask to take CS2102 in semester three. The assistant converts the instruction into visible cards. The generated plan shows real course codes rather than unresolved elective placeholders. We can inspect each semester\'s weekly selection and export a native NUSMods Planner JSON file. The planner contains 338 real reference courses, including supplementary Mathematics and QF options. For the video, the solve is prepared in advance and any skipped waiting time is labelled. We do not need to expose API keys or rely on a live model service during the recording.'),
 ('5:50-6:55','The benchmark varies explicit rule disclosure','Sun Jiaen',
  'Show three condition columns A/AP/APR, 15 model IDs, common reference snapshot and output checker. Label CLI versus API.',
  'Our main matrix tests fifteen model IDs under three conditions: assumptions only, assumptions plus preferences, and assumptions plus preferences plus hard requirements. All methods receive the same frozen course and timetable facts and must return the same JSON schedule format. We exclude aliases from the model count. The SoCLaaS requests use temperature zero and a 3500-token output cap without automatic repairs or retries. Astra and Sol use the Codex CLI because no separate API key is configured. That harness has different hidden instructions and generation limits, so we report it separately. We count hard-card failures on evaluable plans, while unavailable services, truncated or malformed outputs and unknown courses remain visible. A failed request never counts as a zero-violation plan.'),
 ('6:55-8:30','The results separate correctness from availability','Sun Jiaen',
  'Show the actual model table and the three CSP controls. Explicitly mark unverified weekly data and unavailable outputs. Include no human preference chart yet.',
  f'Across the 45 main requests, {n} produced evaluable schedules and {v} passed all implemented hard checks. The table distinguishes service errors, unparseable responses, proven rule failures and unresolved weekly checks. Full rule disclosure helped some models, but this small fixed-task study does not establish a universal ranking. Sol produced a fully verified base plan in the full-requirement condition. Astra had zero proven hard-card failures there, but its weekly check remained unverified. This matters: our evidence does not support saying that language models can never produce correct schedules. The three symbolic controls all passed their active hard checks and audits. The base control completed 160 units in eight semesters and met both default preferences. The QF minor control also finished in eight semesters, with a workload deviation. The Mathematics minor control used nine semesters and missed the duration and balance preferences. These are legitimate tradeoffs under a feasible hard model. We have also prepared fifteen anonymous schedules and an anchored rating rubric for two internal raters. We have not collected their scores, so we cannot claim a human preference advantage.'),
 ('8:30-9:20','Explicit constraints provide inspectable guarantees within scope','Achar Pavithra',
  'Three concise limitations, then one concrete conclusion. No Responsible AI section is needed in this video.',
  'Our main accomplishment is a working connection from student language to editable constraints, semester optimisation, weekly verification and NUSMods export. The guarantees apply to the implemented model and frozen data. Future offerings can change, and full graduation eligibility, registration quotas, arbitrary second majors and all preclusion rules remain outside the current scope. Bounded search can also time out or leave preferences unmet. Next we would expand curriculum coverage, measure parser fidelity on many independent instructions, and collect the blinded ratings from students beyond the development team. The project demonstrates how an LLM can make a constraint planner easier to use while preserving inspectable checks on the resulting plan.'),
 ]
 dump(PRES/'video_plan.json',{'duration_target':'9:20','maximum':'10:00','responsible_ai_in_video':False,'slides':[dict(time=t,title=title,speaker=speaker,visual=visual,narration=narration) for t,title,speaker,visual,narration in slides]})
 md=['# Presentation video: 10-minute maximum','', 'Target 9:20 including transitions. Latest user-provided video requirement supersedes the older 15-minute presentation guidance. Cover accomplishments, project understanding, technical depth, methodology and actual results. Responsible AI stays in the report.','', 'Suggested roles are a recording plan, not new claims about implementation ownership. Speak naturally and rehearse; timing depends on speech rate.']
 flow=[P('Presentation video plan','TitleBlue'),P('Target 9:20; hard maximum 10:00','HeadingBlue'),P('Nine slides with English narration and a short prepared demonstration. The latest video requirement takes precedence over the older presentation timing. Responsible AI remains in the report.'),P('Recording checklist','HeadingBlue'),P('Use 16:9 slides, a white background, navy headings and restrained gold accents matching Pathway. Use one readable figure or result table per slide. Keep body text at least 20 pt where possible. Add team names on the opening slide. Avoid displaying secrets, terminals with credentials or private method keys. Label any demo time skip. Test audio and export duration before submission. Aim for 9:20, leaving 40 seconds below the maximum.'),P('Evidence discipline','HeadingBlue'),P('Use only the archived results. Keep service failures and unverified checks visible. Do not show human score charts before collection. State that typed-card controls are not a full parser benchmark and that frontier CLI results are not identical API controls.')]
 for t,title,speaker,visual,narration in slides:
  md += ['',f'## {t} — {title}',f'**Suggested speaker:** {speaker}',f'**Visual:** {visual}','','**Narration:**',narration]
  flow += [PageBreak(),P(t,'HeadingBlue'),P(title,'TitleBlue'),P('Suggested speaker: '+speaker),P('Visual','HeadingBlue'),P(html.escape(visual)),P('Narration','HeadingBlue'),P(html.escape(narration))]
 md+=['','## Rehearsal and cuts','', '- Read once at a comfortable pace, then measure actual duration. Do not accelerate to make dense slides fit.', '- If the video exceeds 9:40, shorten the catalogue counts and minor details before cutting the experimental caveats.', '- Keep the method, weekly feedback and results sections. Omit a separate related-work survey, Responsible AI and detailed contribution table from the video; they remain in the report.', '- Verify that the exported video is at most 10:00. This file is the script/storyboard, not a recorded video.']
 (PRES/'video_script.md').write_text('\n'.join(md)+'\n');pdf(OUT/'presentation_video_plan.pdf',flow)

if __name__=='__main__':
 results,summary=summarise();selected,replacements=build_human(results);build_presentation(summary)
 dump(RUN/'evaluation_provenance.json',{'evaluator_sha256':hashlib.sha256((ROOT/'research/experiments/benchmark.py').read_bytes()).hexdigest(),'material_builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'rating_packet_plans':len(selected),'replacements':replacements})
 print('Material build:',len(selected),'blind plans;',summary['evaluable_main'],'evaluable main schedules')
